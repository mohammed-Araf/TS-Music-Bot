import os, json, asyncio, logging, time
import aiohttp
from aiohttp import web
from .config import CFG
from .clientquery import ClientQuery, QueryError
from .spotify import Librespot, Search
from .tsescape import strip_bbcode, escape
from .commands import REGISTRY, Ctx
from .ratelimit import RateLimiter
from .pulse import set_audio_mute, set_audio_duck
from .guard import GUARD, ACTION_PLAY, ACTION_PAUSE, ACTION_STOP

log = logging.getLogger("app")

class App:
    def __init__(self):
        self.session = None
        self.cq = None
        self.lr = None
        self.search = None
        self.my_clid = None
        self.my_cid = None
        self.limiter = RateLimiter(user_cooldown=CFG.cooldown)
        self.ts_ok = False
        self.spotify_ok = False
        self.ducking_enabled = CFG.auto_ducking
        self.duck_percent = CFG.duck_percent
        self.duck_hold_time = CFG.duck_hold_time
        self.channel_clients = set()
        self.speaking_clients = set()
        self._is_ducked: bool = False
        self._unduck_timer_task = None
        self._paused_by_empty_channel: bool = False
        self._empty_channel_time: float = None
        self._ready_for_ambient_autoplay: bool = False

    def _cancel_unduck_timer(self):
        """Cancels any pending hysteresis hold timer."""
        if self._unduck_timer_task and not self._unduck_timer_task.done():
            self._unduck_timer_task.cancel()
        self._unduck_timer_task = None

    def _schedule_unduck(self):
        """
        Schedules unducking with a hold window (hysteresis delay).
        During a conversation between multiple people, brief pauses between
        sentences or speakers will not cause volume to bounce back up until
        everyone has remained silent for the full hold duration.
        """
        self._cancel_unduck_timer()
        if not self._is_ducked:
            return

        async def _delayed_unduck():
            try:
                await asyncio.sleep(self.duck_hold_time)
                # Confirm everyone is still silent before releasing
                if not self.speaking_clients and self._is_ducked:
                    log.debug("Hold window (%.1fs) elapsed with zero talkers; releasing duck fader.", self.duck_hold_time)
                    await set_audio_duck(False)
                    self._is_ducked = False
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.warning("Delayed unduck error: %s", e)

        self._unduck_timer_task = asyncio.create_task(_delayed_unduck())

    async def _handle_talk_status(self, f):
        clid = f.get("clid")
        status = f.get("status")
        if not clid or clid == self.my_clid:
            return
        if clid not in self.channel_clients:
            return

        if status == "1":
            # Talker started: cancel any pending hold timer immediately!
            self._cancel_unduck_timer()
            self.speaking_clients.add(clid)
            if self.ducking_enabled:
                self._is_ducked = True
                await set_audio_duck(True, self.duck_percent)
        elif status == "0":
            self.speaking_clients.discard(clid)
            # Talker stopped: if nobody else is talking, wait for the hold window
            if not self.speaking_clients:
                if self.ducking_enabled and self._is_ducked:
                    self._schedule_unduck()
                else:
                    self._cancel_unduck_timer()
                    await set_audio_duck(False)
                    self._is_ducked = False

    async def _handle_channel_empty(self):
        """Immediately pauses playback and sets bot away when the last user leaves."""
        if not CFG.eco_mode:
            return
        if self._empty_channel_time is None:
            self._empty_channel_time = time.time()
            self._cancel_unduck_timer()
            await set_audio_duck(False)
            self._is_ducked = False
            st = None
            try:
                st = await self.lr.status()
            except Exception:
                pass

            was_playing = bool(st and not st.get("paused") and not st.get("stopped") and st.get("track"))
            self._paused_by_empty_channel = was_playing

            if was_playing:
                log.info("Channel emptied. Instantly pausing audio and setting away status.")
                try:
                    await self.lr.pause()
                except Exception:
                    pass
                await set_audio_mute(True)

            away_msg = "⏸️ Paused (Empty Channel)" if was_playing else "⏸️ Idle (Empty Channel)"
            try:
                await self.cq.cmd(f"clientupdate client_away=1 client_away_message={escape(away_msg)}")
            except Exception:
                pass

    async def _handle_channel_active(self):
        """Called when a user enters the channel."""
        if not CFG.eco_mode:
            return

        was_empty = (self._empty_channel_time is not None)
        empty_duration = time.time() - self._empty_channel_time if was_empty else 0
        self._empty_channel_time = None

        # Clear away status immediately
        try:
            await self.cq.cmd("clientupdate client_away=0 client_away_message=")
        except Exception:
            pass

        # Case 1: User returned within 5 minutes (auto-resume their saved track!)
        if was_empty and self._paused_by_empty_channel and (empty_duration <= CFG.eco_resume_window):
            self._paused_by_empty_channel = False
            self._ready_for_ambient_autoplay = False
            log.info("User returned within %.1fs. Auto-resuming saved playback.", empty_duration)
            await set_audio_mute(False)
            try:
                await self.lr.resume()
                if self.my_cid:
                    await self.cq.say(
                        self.my_cid,
                        "👋 [b]Welcome back![/b] Resuming music right where you left off."
                    )
            except Exception as e:
                log.warning("Failed to auto-resume: %s", e)
            return

        # Case 2: 5 minutes have passed or bot was idle -> Auto-play chill background beats on low volume!
        should_autoplay_chill = (
            (was_empty and (self._ready_for_ambient_autoplay or empty_duration > CFG.eco_resume_window))
            or self._ready_for_ambient_autoplay
        )
        self._paused_by_empty_channel = False
        self._ready_for_ambient_autoplay = False

        if should_autoplay_chill and self.spotify_ok:
            try:
                st = await self.lr.status()
                # Only autoplay chill beats if nothing is currently playing
                if not st or st.get("paused") or st.get("stopped") or not st.get("track"):
                    log.info("Channel joined after timeout. Starting chill background music at %d%% vol.", CFG.chill_volume)
                    await self.lr.volume(CFG.chill_volume)
                    await set_audio_mute(False)
                    await self.lr.play(CFG.chill_autoplay_uri)
                    if self.my_cid:
                        await self.cq.say(
                            self.my_cid,
                            f"👋 [b]Welcome to the channel![/b] Playing background chill beats at low volume ({CFG.chill_volume}%).\n"
                            f"👉 Type [b]{CFG.prefix}play <song>[/b] anytime to play your own music!"
                        )
            except Exception as e:
                log.debug("Chill autoplay exception: %s", e)

    async def _handle_client_change(self, name, f):
        clid = f.get("clid")
        if not clid or clid == self.my_clid:
            return

        if name == "notifycliententerview":
            ctid = f.get("ctid")
            if ctid == self.my_cid:
                prev_count = len(self.channel_clients)
                self.channel_clients.add(clid)
                if prev_count == 0:
                    asyncio.create_task(self._handle_channel_active())
        elif name == "notifyclientleftview":
            self.channel_clients.discard(clid)
            self.speaking_clients.discard(clid)
            if not self.channel_clients:
                self._cancel_unduck_timer()
                await set_audio_duck(False)
                self._is_ducked = False
                asyncio.create_task(self._handle_channel_empty())
            elif not self.speaking_clients:
                if self.ducking_enabled and self._is_ducked:
                    self._schedule_unduck()
                else:
                    self._cancel_unduck_timer()
                    await set_audio_duck(False)
                    self._is_ducked = False
        elif name == "notifyclientmoved":
            ctid = f.get("ctid")
            if ctid == self.my_cid:
                prev_count = len(self.channel_clients)
                self.channel_clients.add(clid)
                if prev_count == 0:
                    asyncio.create_task(self._handle_channel_active())
            else:
                self.channel_clients.discard(clid)
                self.speaking_clients.discard(clid)
                if not self.channel_clients:
                    self._cancel_unduck_timer()
                    await set_audio_duck(False)
                    self._is_ducked = False
                    asyncio.create_task(self._handle_channel_empty())
                elif not self.speaking_clients:
                    if self.ducking_enabled and self._is_ducked:
                        self._schedule_unduck()
                    else:
                        self._cancel_unduck_timer()
                        await set_audio_duck(False)
                        self._is_ducked = False

    async def _sync_channel_clients(self):
        if not self.my_cid:
            return
        try:
            clines = await self.cq.cmd(f"channelclientlist cid={self.my_cid}")
            raw = " ".join(clines)
            curr = set()
            for chunk in raw.split("|"):
                parts = dict(kv.split("=", 1) for kv in chunk.split() if "=" in kv)
                cid = parts.get("clid")
                ctype = parts.get("client_type")
                if cid and cid != self.my_clid and ctype != "1":
                    curr.add(cid)
            prev_speaking = bool(self.speaking_clients)
            prev_empty = (len(self.channel_clients) == 0)
            self.channel_clients = curr
            self.speaking_clients &= self.channel_clients
            if not self.channel_clients:
                self._cancel_unduck_timer()
                await set_audio_duck(False)
                self._is_ducked = False
            elif prev_speaking and not self.speaking_clients:
                if self.ducking_enabled and self._is_ducked:
                    self._schedule_unduck()
                else:
                    self._cancel_unduck_timer()
                    await set_audio_duck(False)
                    self._is_ducked = False

            if len(self.channel_clients) == 0 and not prev_empty:
                asyncio.create_task(self._handle_channel_empty())
            elif len(self.channel_clients) > 0 and prev_empty:
                asyncio.create_task(self._handle_channel_active())
        except Exception as e:
            log.debug("Failed to sync channel clients: %s", e)

    async def on_event(self, name, f):
        if name == "notifytalkstatuschange":
            await self._handle_talk_status(f)
            return
        if name in ("notifyclientmoved", "notifyclientleftview", "notifycliententerview"):
            await self._handle_client_change(name, f)
            return
        if name != "notifytextmessage" or f.get("targetmode") != "2":
            return
        if f.get("invokerid") == self.my_clid:
            return
        msg = strip_bbcode(f.get("msg", ""))
        if not msg.startswith(CFG.prefix):
            return
        cmd, _, arg = msg[len(CFG.prefix):].partition(" ")
        entry = REGISTRY.get(cmd.lower())
        if not entry:
            return
        handler, admin_only = entry
        clid = f.get("invokerid")
        uid, nick = f.get("invokeruid", ""), f.get("invokername", "?")

        # Query user's server groups and channel group from client cache
        user_groups = set()
        ch_group = ""
        if clid:
            try:
                cv = await self.cq.kv(f"clientvariable clid={clid} client_servergroups client_channel_group_id")
                raw_groups = cv.get("client_servergroups", "")
                user_groups = set(g.strip() for g in raw_groups.split(",") if g.strip())
                ch_group = cv.get("client_channel_group_id", "")
            except Exception:
                pass

        is_admin = (uid in CFG.admin_uids) or bool(user_groups & CFG.admin_server_groups)
        cmd_lower = cmd.lower()

        if admin_only and not is_admin:
            await self.cq.say(self.my_cid, "Admins only.")
            return

        # Check playback role requirement (exempt admins and info commands)
        if (
            CFG.allowed_server_groups
            and not is_admin
            and cmd_lower not in ("myroles", "roles", "help", "h")
            and not bool(user_groups & CFG.allowed_server_groups)
        ):
            await self.cq.say(self.my_cid, "You need the music role to use this bot.")
            return

        allowed, reason = self.limiter.check(uid, is_admin=is_admin)
        if not allowed:
            if reason:
                await self.cq.say(self.my_cid, reason)
            return
        ctx = Ctx(CFG, self.cq, self.lr, self.search, uid, nick, self.my_cid,
                  server_groups=user_groups, channel_group=ch_group, is_admin=is_admin, cmd=cmd_lower, app=self)
        try:
            reply = await handler(ctx, arg.strip())
        except Exception as e:
            log.exception("command failed: %s", cmd)
            reply = f"Error: {e}"
        if reply:
            await self.cq.say(self.my_cid, reply)

    async def _resolve_target_cid(self):
        if not CFG.ts_channel:
            return None
        target = CFG.ts_channel.strip()
        leaf = target.split("/")[-1].strip()
        try:
            lines = await self.cq.cmd("channellist")
            raw = " ".join(lines)
            for part in raw.split("|"):
                parts = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
                cname = parts.get("channel_name", "").replace("\\s", " ").replace("\\/", "/")
                if cname == leaf or cname == target:
                    return parts.get("cid")
        except Exception as e:
            log.warning("Failed to resolve target channel: %s", e)
        return None

    async def _ensure_channel(self):
        if not CFG.ts_channel or not self.my_clid:
            return
        cid = await self._resolve_target_cid()
        if cid and self.my_cid != cid:
            cmd = f"clientmove cid={cid} clid={self.my_clid}"
            if CFG.ts_channel_password:
                cmd += f" cpw={CFG.ts_channel_password}"
            try:
                await self.cq.cmd(cmd)
                self.my_cid = cid
                log.info("Moved bot to channel cid=%s", cid)
            except Exception as e:
                log.warning("Failed to move bot to channel cid=%s: %s", cid, e)

    async def _ts_session(self):
        """Connect to ClientQuery, register for chat events, keep the connection alive."""
        self.cq = ClientQuery(CFG.cq_host, CFG.cq_port, CFG.cq_apikey, self.on_event)
        await self.cq.connect()
        sch = (await self.cq.kv("currentschandlerid")).get("schandlerid", "1")
        for ev in ("notifytextmessage", "notifytalkstatuschange", "notifyclientmoved", "notifyclientleftview", "notifycliententerview"):
            try:
                await self.cq.cmd(f"clientnotifyregister schandlerid={sch} event={ev}")
            except Exception as e:
                log.warning("Failed to register %s: %s", ev, e)
        while self.cq.connected:
            try:
                who = await self.cq.kv("whoami")      # fails if not connected to a server
                self.my_clid, self.my_cid = who.get("clid"), who.get("cid")
                self.ts_ok = bool(self.my_clid)
                if self.ts_ok:
                    await self._ensure_channel()
                    await self._sync_channel_clients()
            except (QueryError, asyncio.TimeoutError):
                self.ts_ok = False
            await asyncio.sleep(5)

    async def ts_loop(self):
        delay = 2
        while True:
            try:
                await self._ts_session()
            except Exception as e:
                log.warning("ClientQuery session ended: %s", e)
            self.ts_ok = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def spotify_loop(self):
        was_ok = False
        consecutive_failures = 0
        while True:
            try:
                st = await self.lr.status()
                now_ok = bool(st and st.get("username"))
                if now_ok:
                    consecutive_failures = 0
                    self.spotify_ok = True
                    was_ok = True
                else:
                    consecutive_failures += 1
                    # Explicit 204 No Content returned repeatedly: real logout
                    if consecutive_failures >= 3:
                        self.spotify_ok = False
                        if was_ok and self.my_cid:
                            try:
                                await self.cq.say(
                                    self.my_cid,
                                    f"⚠️ [b]Spotify Session Ended:[/b] The linked account disconnected or Premium subscription ended.\n"
                                    f"👉 Type [b]{CFG.prefix}login[/b] in chat to reconnect or pair an active Premium account!"
                                )
                            except Exception:
                                pass
                            was_ok = False
            except Exception as e:
                # Backend is busy loading a track or processing a command: do not panic
                log.debug("spotify_loop probe exception: %s", e)
                consecutive_failures += 1
                if consecutive_failures >= 4:
                    self.spotify_ok = False
            await asyncio.sleep(15)

    async def health(self, request):
        ok = self.ts_ok
        return web.json_response({"ts": self.ts_ok, "spotify": self.spotify_ok},
                                 status=200 if ok else 503)

    async def run(self):
        self.session = aiohttp.ClientSession()
        self.lr = Librespot(CFG.lr_url, self.session)
        custom_keys = None
        if os.path.exists("/data/spotify_keys.json"):
            try:
                with open("/data/spotify_keys.json") as f:
                    custom_keys = json.load(f)
            except Exception:
                pass
        cid = (custom_keys.get("client_id") if custom_keys else None) or CFG.sp_client_id
        secret = (custom_keys.get("client_secret") if custom_keys else None) or CFG.sp_client_secret
        self.search = Search(cid, secret, self.session)

        app = web.Application()
        app.router.add_get("/health", self.health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", CFG.health_port).start()

        # best-effort: set initial volume once go-librespot is up
        asyncio.create_task(self._init_volume())
        await asyncio.gather(
            self.ts_loop(),
            self.spotify_loop(),
            self.spotify_events_loop(),
            self._ui_ticker_loop(),
        )

    async def _ui_ticker_loop(self):
        """
        Updates the live TeamSpeak away message every 5s with progress bar,
        track metadata, volume, and ducking status. Also enforces Eco Mode auto-pause.
        """
        last_away_msg = None
        while True:
            try:
                if self.ts_ok and self.cq and self.cq.connected:
                    # While channel is empty, maintain away state and check 5m resume window expiration
                    if CFG.eco_mode and not self.channel_clients:
                        if self._paused_by_empty_channel and self._empty_channel_time:
                            if time.time() - self._empty_channel_time > CFG.eco_resume_window:
                                log.info("Eco Mode: 5-minute resume window expired. Armed chill ambient beats for next join.")
                                self._paused_by_empty_channel = False
                                self._ready_for_ambient_autoplay = True
                        await asyncio.sleep(CFG.ticker_interval)
                        continue

                    # Fetch Spotify state for UI
                    st = None
                    try:
                        st = await self.lr.status()
                    except Exception:
                        pass

                    duck_tag = "Duck:ON" if self.ducking_enabled else "Duck:OFF"
                    new_msg = None
                    away_flag = 1

                    if not st or not st.get("username"):
                        new_msg = f"⚠️ Disconnected | Type {CFG.prefix}login"
                        away_flag = 1
                    elif st and not st.get("paused") and not st.get("stopped") and st.get("track"):
                        track = st.get("track", {})
                        title = track.get("name", "Unknown Track")
                        artists_raw = track.get("artist_names", [])
                        artists = ", ".join(artists_raw) if isinstance(artists_raw, list) else str(artists_raw)
                        dur_ms = track.get("duration", 0)
                        pos_ms = track.get("position", 0)
                        pos_s, dur_s = pos_ms // 1000, dur_ms // 1000
                        if dur_s > 0:
                            pct = min(max(pos_s / dur_s, 0.0), 1.0)
                            filled = int(round(pct * 8))
                            bar = "█" * filled + "░" * (8 - filled)
                            time_str = f"{pos_s // 60}:{pos_s % 60:02d}/{dur_s // 60}:{dur_s % 60:02d}"
                        else:
                            bar = "░" * 8
                            time_str = "0:00"

                        base_len = len(f"▶  [{bar}] {time_str} [{duck_tag}]")
                        rem = 80 - base_len - 1
                        track_name = f"{title} - {artists}" if artists else title
                        if len(track_name) > rem:
                            track_name = track_name[:rem - 1] + "…"
                        new_msg = f"▶ {track_name} [{bar}] {time_str} [{duck_tag}]"
                        away_flag = 0
                    elif st and st.get("paused"):
                        vol = st.get("volume", CFG.initial_volume)
                        new_msg = f"⏸️ Paused ({vol}%) [{duck_tag}]"
                        away_flag = 0
                    else:
                        new_msg = ""
                        away_flag = 0

                    if new_msg != last_away_msg:
                        try:
                            cmd = f"clientupdate client_away={away_flag}"
                            if new_msg:
                                cmd += f" client_away_message={escape(new_msg)}"
                            else:
                                cmd += " client_away_message="
                            await self.cq.cmd(cmd)
                            last_away_msg = new_msg
                        except Exception as e:
                            log.debug("Failed to update away message: %s", e)
            except Exception as e:
                log.debug("UI ticker error: %s", e)
            await asyncio.sleep(CFG.ticker_interval)

    async def spotify_events_loop(self):
        """
        Listens to go-librespot WebSocket /events to sync real-time playback
        state when controlled directly from mobile/desktop Spotify Connect apps.
        """
        ws_url = CFG.lr_url.replace("http://", "ws://") + "/events"
        while True:
            try:
                async with self.session.ws_connect(ws_url, timeout=10) as ws:
                    log.info("Connected to go-librespot event stream")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                ev = json.loads(msg.data)
                                etype = ev.get("type")
                                data = ev.get("data") or {}
                                if etype == "playing":
                                    await set_audio_mute(False)
                                    GUARD.mark_state(ACTION_PLAY)
                                elif etype in ("paused", "stopped"):
                                    await set_audio_mute(True)
                                    GUARD.mark_state(ACTION_PAUSE if etype == "paused" else ACTION_STOP)
                                elif etype == "volume":
                                    vol = data.get("value")
                                    if vol is not None:
                                        GUARD.mark_volume(int(vol))
                            except Exception as ex:
                                log.debug("Error processing player event: %s", ex)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except Exception as e:
                log.debug("Event stream reconnecting: %s", e)
            await asyncio.sleep(5)

    async def _init_volume(self):
        for _ in range(30):
            try:
                await self.lr.volume(CFG.initial_volume)
                return
            except Exception:
                await asyncio.sleep(2)
