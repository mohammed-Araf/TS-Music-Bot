import os, re, json, asyncio, logging, time, subprocess
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

_CLOCK_RE = re.compile(r"\d+:\d{2}|[━─●]+")

def _strip_clock(text: str) -> str:
    """Description text with the moving parts (times, progress bar) removed."""
    return _CLOCK_RE.sub("", text or "")

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
        # channel_clients = active LISTENERS (humans who are not deafened) in the bot's
        # current channel; this drives BGM / eco pause. channel_present = every human
        # in the channel, deafened or not (used for voice ducking).
        self.channel_clients = set()
        self.channel_present = set()
        self.speaking_clients = set()
        # Home channel + drag-follow state
        self.home_cid = None
        self._home_resolved_at: float = 0.0
        self._been_home: bool = False          # reached home since this ClientQuery session began
        self._visit_empty_since: float = None  # when the visited channel last ran out of listeners
        self._quiet_next_welcome: bool = False
        self._chan_lock = asyncio.Lock()       # serialises channel moves and listener syncs
        self._is_ducked: bool = False
        self._unduck_timer_task = None
        self._paused_by_empty_channel: bool = False
        self._empty_channel_time: float = None
        self._ready_for_ambient_autoplay: bool = False
        self.is_ambient_autoplay: bool = False
        self.user_volume: int = CFG.initial_volume
        # Zombie-connection watchdog: the TS3 client can silently lose its server
        # link while ClientQuery keeps answering reads from a frozen cache (whoami,
        # channelclientlist). Writes then fail with id=1796 "currently not possible"
        # and no events arrive, so the channel never looks empty and BGM loops forever.
        self._ts_last_write_ok: float = time.time()
        self._ts_healing: bool = False
        self._ts_last_heal: float = 0.0
        self._empty_away_msg: str = ""
        # Player display: line 2 = away status (song), line 3 = client description (progress).
        self.requested_by: str = ""             # nick of whoever started the current !play
        self._my_dbid = None                    # bot's client database id (for clientdbedit)
        self._desc_ok = None                    # None = untested, False = no permission (fallback)
        self._last_desc = None
        self._last_desc_sent: float = 0.0

    async def _cq_update(self, cmd: str):
        """Run a server-bound ClientQuery write and feed the zombie watchdog."""
        try:
            await self.cq.cmd(cmd)
            self._ts_last_write_ok = time.time()
        except QueryError as e:
            if "id=1796" in str(e):
                self._maybe_auto_heal(f"server writes refused for {time.time() - self._ts_last_write_ok:.0f}s")
            raise

    def _maybe_auto_heal(self, reason: str):
        """Auto-restart the TS client once the link has been bad for ts_zombie_timeout,
        at most once every 5 minutes (rapid reconnects can trip server anti-flood)."""
        now = time.time()
        if (CFG.ts_zombie_timeout > 0
                and now - self._ts_last_write_ok > CFG.ts_zombie_timeout
                and now - self._ts_last_heal > 300):
            asyncio.create_task(self.heal_ts_connection(reason))

    async def heal_ts_connection(self, reason: str):
        """Stop audio, forget the stale channel cache and restart the TS3 client."""
        if self._ts_healing:
            return
        self._ts_healing = True
        try:
            log.warning("TeamSpeak connection looks dead (%s). Pausing audio and restarting ts3client.", reason)
            try:
                await self.lr.pause()
            except Exception:
                pass
            await set_audio_mute(True)
            self.channel_clients.clear()
            self.channel_present.clear()
            self.speaking_clients.clear()
            self.is_ambient_autoplay = False
            self._paused_by_empty_channel = False
            self._empty_channel_time = None
            self.ts_ok = False
            # ts3client_runscript.sh runs the binary as a child (no exec), so a plain
            # supervisorctl restart only kills the wrapper and leaves the old binary
            # orphaned, still holding the ClientQuery port. Kill the binary explicitly.
            def _restart():
                sv = ["supervisorctl", "-c", "/opt/bot/docker/supervisord.conf"]
                subprocess.run(sv + ["stop", "ts3client"], capture_output=True, timeout=60)
                subprocess.run(["pkill", "-f", "ts3client_linux_amd64"], capture_output=True, timeout=10)
                time.sleep(2)
                subprocess.run(["pkill", "-9", "-f", "ts3client_linux_amd64"], capture_output=True, timeout=10)
                return subprocess.run(sv + ["start", "ts3client"], capture_output=True, text=True, timeout=60)
            self._ts_last_heal = time.time()
            r = await asyncio.to_thread(_restart)
            log.info("ts3client restart: rc=%s %s", r.returncode, (r.stdout or r.stderr).strip())
            if self.cq:
                await self.cq.close()   # ts_loop reconnects ClientQuery once the client is back
        except Exception as e:
            log.warning("ts3client restart failed: %s", e)
        finally:
            self._ts_last_write_ok = time.time()   # grace period before the next check
            self._ts_healing = False

    def _cancel_unduck_timer(self):
        """Cancels any pending hysteresis hold timer."""
        if self._unduck_timer_task and not self._unduck_timer_task.done():
            self._unduck_timer_task.cancel()
        self._unduck_timer_task = None

    async def _return_to_bgm(self):
        """Returns to default ambient background music at chill_volume."""
        if not self.spotify_ok or not self.channel_clients:
            return
        self.is_ambient_autoplay = True
        self.requested_by = ""
        self._paused_by_empty_channel = False
        self._ready_for_ambient_autoplay = False
        try:
            await self.lr.volume(CFG.chill_volume)
            GUARD.mark_volume(CFG.chill_volume)
            await set_audio_mute(False)
            await self.lr.play(CFG.chill_autoplay_uri)
            GUARD.mark_state(ACTION_PLAY)
            log.info("Started default BGM at %d%% vol.", CFG.chill_volume)
        except Exception as e:
            log.warning("Failed to start default BGM: %s", e)

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
        if clid not in self.channel_present:
            return

        if status == "1":
            # Talker started: cancel any pending hold timer immediately!
            self._cancel_unduck_timer()
            self.speaking_clients.add(clid)
            # Strictly NO ducking during background chill music (BGM)
            if self.ducking_enabled and not self.is_ambient_autoplay:
                self._is_ducked = True
                await set_audio_duck(True, self.duck_percent)
        elif status == "0":
            self.speaking_clients.discard(clid)
            # Talker stopped: if nobody else is talking, wait for the hold window
            if not self.speaking_clients:
                if self.ducking_enabled and not self.is_ambient_autoplay and self._is_ducked:
                    self._schedule_unduck()
                elif self._is_ducked:
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
            was_bgm = self.is_ambient_autoplay
            self.is_ambient_autoplay = False
            st = None
            try:
                st = await self.lr.status()
            except Exception:
                pass

            was_playing = bool(st and not st.get("paused") and not st.get("stopped") and st.get("track"))

            # Only consider it a savable/resumable user track if it was NOT background music
            self._paused_by_empty_channel = was_playing and not was_bgm

            if was_playing:
                log.info("Channel emptied. Instantly pausing audio and setting away status (was_bgm=%s).", was_bgm)
                try:
                    await self.lr.pause()
                except Exception:
                    pass
                await set_audio_mute(True)

            away_msg = "⏸️ Paused (Empty Channel)" if self._paused_by_empty_channel else "⏸️ Idle (Empty Channel)"
            self._empty_away_msg = away_msg
            try:
                await self._cq_update(f"clientupdate client_away=1 client_away_message={escape(away_msg)}")
            except Exception:
                pass

    async def _handle_channel_active(self):
        """Called when a user enters the channel."""
        if not CFG.eco_mode or self._ts_healing:
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
            self.is_ambient_autoplay = False
            log.info("User returned within %.1fs. Auto-resuming saved playback.", empty_duration)
            await set_audio_mute(False)
            try:
                await self.lr.volume(self.user_volume)
                GUARD.mark_volume(self.user_volume)
                await self.lr.resume()
                if self.my_cid:
                    await self.cq.say(
                        self.my_cid,
                        "👋 [b]Welcome back![/b] Resuming music right where you left off."
                    )
            except Exception as e:
                log.warning("Failed to auto-resume: %s", e)
            return

        # Case 2: No saved user track (or expired) -> Default state: play background chill music!
        self._paused_by_empty_channel = False
        self._ready_for_ambient_autoplay = False
        quiet = self._quiet_next_welcome
        self._quiet_next_welcome = False

        if self.spotify_ok:
            try:
                st = await self.lr.status()
                # If nothing is actively playing, start background chill music
                if not st or st.get("paused") or st.get("stopped") or not st.get("track"):
                    await self._return_to_bgm()
                    if self.my_cid and not quiet:
                        if self._is_visiting():
                            greet = ("📍 [b]Dragged in![/b] Playing background chill beats "
                                     f"({CFG.chill_volume}%). I'll head back home once nobody here is listening.\n")
                        else:
                            greet = ("👋 [b]Welcome to the channel![/b] Playing background chill beats "
                                     f"at low volume ({CFG.chill_volume}%).\n")
                        await self.cq.say(
                            self.my_cid,
                            greet + f"👉 Type [b]{CFG.prefix}play <song>[/b] anytime to play your own music!"
                        )
            except Exception as e:
                log.debug("Chill autoplay exception: %s", e)

    # ------------------------------------------------------------------
    # Listener tracking
    # ------------------------------------------------------------------
    def _is_visiting(self) -> bool:
        """True while the bot sits in a channel it was dragged into."""
        return bool(self.home_cid and self.my_cid and self.my_cid != self.home_cid)

    async def _handle_client_change(self, name, f):
        clid = f.get("clid")
        if not clid:
            return
        if clid == self.my_clid:
            # The bot itself was moved (dragged by a user, or our own clientmove).
            if name == "notifyclientmoved" and f.get("ctid"):
                await self._on_bot_channel(f.get("ctid"))
            return
        ctid = f.get("ctid")
        if ctid == self.my_cid or clid in self.channel_present:
            if name == "notifyclientleftview" or (name == "notifyclientmoved" and ctid != self.my_cid):
                self.speaking_clients.discard(clid)
            await self.refresh_listeners()

    async def _handle_client_updated(self, f):
        """Someone toggled deafen (speaker mute) or their output device: recount listeners."""
        clid = f.get("clid")
        if not clid or clid == self.my_clid or clid not in self.channel_present:
            return
        if "client_output_muted" in f or "client_output_hardware" in f:
            await self.refresh_listeners()

    async def _sync_listeners_locked(self):
        """Re-read who is in the bot's channel. Returns (became_active, became_empty)."""
        clines = await self.cq.cmd(f"channelclientlist cid={self.my_cid} -voice")
        raw = " ".join(clines)
        present, listening = set(), set()
        for chunk in raw.split("|"):
            parts = dict(kv.split("=", 1) for kv in chunk.split() if "=" in kv)
            cid = parts.get("clid")
            if not cid or cid == self.my_clid or parts.get("client_type") == "1":
                continue
            present.add(cid)
            deaf = parts.get("client_output_muted") == "1" or parts.get("client_output_hardware") == "0"
            if not (CFG.ignore_deafened and deaf):
                listening.add(cid)

        prev_speaking = bool(self.speaking_clients)
        prev_empty = not self.channel_clients
        self.channel_present = present
        self.channel_clients = listening
        self.speaking_clients &= present
        if not listening:
            self._cancel_unduck_timer()
            if self._is_ducked:
                await set_audio_duck(False)
            self._is_ducked = False
        elif prev_speaking and not self.speaking_clients:
            if self.ducking_enabled and not self.is_ambient_autoplay and self._is_ducked:
                self._schedule_unduck()
            elif self._is_ducked:
                self._cancel_unduck_timer()
                await set_audio_duck(False)
                self._is_ducked = False

        became_empty = not listening and (not prev_empty or self._empty_channel_time is None)
        became_active = bool(listening) and prev_empty
        return became_active, became_empty

    async def _refresh_locked(self):
        """Sync listeners, return home from an abandoned visit, then run eco empty/active logic."""
        if not self.my_cid or self._ts_healing:
            return
        became_active, became_empty = await self._sync_listeners_locked()
        if self._is_visiting() and CFG.follow_drag:
            if self.channel_clients:
                self._visit_empty_since = None
            else:
                now = time.time()
                if self._visit_empty_since is None:
                    self._visit_empty_since = now
                if now - self._visit_empty_since >= CFG.return_home_delay:
                    log.info("Nobody listening in visited channel cid=%s. Returning home.", self.my_cid)
                    if await self._move_home_locked():
                        return
        if became_empty:
            await self._handle_channel_empty()
        elif became_active:
            await self._handle_channel_active()

    async def refresh_listeners(self):
        try:
            async with self._chan_lock:
                await self._refresh_locked()
        except Exception as e:
            log.debug("Failed to sync channel clients: %s", e)

    # ------------------------------------------------------------------
    # Channel moves (drag-follow / return home)
    # ------------------------------------------------------------------
    async def _reset_for_channel_change(self):
        """Drop whatever was playing: a dragged bot never carries the old channel's music along."""
        self._cancel_unduck_timer()
        if self._is_ducked:
            await set_audio_duck(False)
        self._is_ducked = False
        try:
            await self.lr.pause()
        except Exception:
            pass
        await set_audio_mute(True)
        self.is_ambient_autoplay = False
        self._paused_by_empty_channel = False
        self._ready_for_ambient_autoplay = False
        self._empty_channel_time = None
        self._empty_away_msg = ""
        self._visit_empty_since = None
        self.channel_clients = set()
        self.channel_present = set()
        self.speaking_clients = set()

    async def _apply_bot_channel_locked(self, cid):
        """Record the bot's (possibly new) channel and react to it."""
        old = self.my_cid
        self.my_cid = cid
        if cid and cid == self.home_cid:
            self._been_home = True
        # Not home yet since (re)connecting, or drag-follow disabled: go straight home.
        if self._is_visiting() and (not CFG.follow_drag or not self._been_home):
            if await self._move_home_locked(quiet=False):
                return
        if old is not None and old != cid:
            log.info("Bot moved from channel cid=%s to cid=%s (%s). Resetting playback.",
                     old, cid, "visiting" if self._is_visiting() else "home")
            await self._reset_for_channel_change()
        await self._refresh_locked()

    async def _on_bot_channel(self, cid):
        try:
            async with self._chan_lock:
                if cid != self.my_cid:
                    await self._apply_bot_channel_locked(cid)
        except Exception as e:
            log.warning("Channel change handling failed: %s", e)

    async def _move_home_locked(self, quiet: bool = True) -> bool:
        if not self.home_cid or not self.my_clid:
            return False
        cmd = f"clientmove cid={self.home_cid} clid={self.my_clid}"
        if CFG.ts_channel_password:
            cmd += f" cpw={escape(CFG.ts_channel_password)}"
        try:
            await self.cq.cmd(cmd)
        except Exception as e:
            log.warning("Failed to move bot home to cid=%s: %s", self.home_cid, e)
            return False
        was_elsewhere = self.my_cid is not None and self.my_cid != self.home_cid
        self.my_cid = self.home_cid
        self._been_home = True
        log.info("Moved bot to home channel cid=%s", self.home_cid)
        if was_elsewhere:
            await self._reset_for_channel_change()
        self._quiet_next_welcome = quiet
        await self._refresh_locked()
        return True

    async def go_home(self) -> bool:
        """Public: send the bot back to its home channel (used by !home)."""
        async with self._chan_lock:
            if not self._is_visiting():
                return False
            return await self._move_home_locked()

    async def on_event(self, name, f):
        if name == "notifytalkstatuschange":
            await self._handle_talk_status(f)
            return
        if name in ("notifyclientmoved", "notifyclientleftview", "notifycliententerview"):
            await self._handle_client_change(name, f)
            return
        if name == "notifyclientupdated":
            await self._handle_client_updated(f)
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

    async def _update_home_cid(self, current_cid):
        """Resolve TS_CHANNEL to a cid (cached for 60s). Without TS_CHANNEL the first
        channel the bot lands in becomes home."""
        if not CFG.ts_channel:
            if self.home_cid is None:
                self.home_cid = current_cid
            return
        if self.home_cid and time.time() - self._home_resolved_at < 60:
            return
        cid = await self._resolve_target_cid()
        if cid:
            self.home_cid = cid
            self._home_resolved_at = time.time()

    async def _ts_session(self):
        """Connect to ClientQuery, register for chat events, keep the connection alive."""
        self.cq = ClientQuery(CFG.cq_host, CFG.cq_port, CFG.cq_apikey, self.on_event)
        await self.cq.connect()
        self._been_home = False
        self._my_dbid = None          # client db id can change if the identity changes
        self._desc_ok = None          # re-test permissions on every new session
        self._last_desc = None
        sch = (await self.cq.kv("currentschandlerid")).get("schandlerid", "1")
        for ev in ("notifytextmessage", "notifytalkstatuschange", "notifyclientmoved",
                   "notifyclientleftview", "notifycliententerview", "notifyclientupdated"):
            try:
                await self.cq.cmd(f"clientnotifyregister schandlerid={sch} event={ev}")
            except Exception as e:
                log.warning("Failed to register %s: %s", ev, e)
        failures = 0
        while self.cq.connected:
            try:
                who = await self.cq.kv("whoami")      # fails if not connected to a server
                self.my_clid = who.get("clid")
                cid = who.get("cid")
                self.ts_ok = bool(self.my_clid)
                failures = 0 if self.ts_ok else failures + 1
                if self.ts_ok and not self._ts_healing:
                    await self._update_home_cid(cid)
                    async with self._chan_lock:
                        await self._apply_bot_channel_locked(cid)
            except (QueryError, asyncio.TimeoutError) as e:
                self.ts_ok = False
                failures += 1
                if failures == 1:
                    log.info("whoami failed: %s", e)
                # The client never auto-reconnects after a server drop (autoreconnect=0),
                # so a lasting "not connected" needs a restart too.
                if "id=1794" in str(e):
                    self._maybe_auto_heal("TS client not connected to server")
            # A ClientQuery session opened while the TS client was still starting can stay
            # bound to a dead server tab forever. Open a fresh session after ~30s of failures.
            if failures >= 6 and not self._ts_healing:
                log.warning("whoami failing for %ds on this ClientQuery session. Reconnecting.", failures * 5)
                await self.cq.close()
                return
            await asyncio.sleep(5)

    async def ts_loop(self):
        delay = 2
        while True:
            started = time.time()
            try:
                await self._ts_session()
            except Exception as e:
                log.warning("ClientQuery session ended: %s", e)
            self.ts_ok = False
            if time.time() - started > 60:
                delay = 2   # a healthy session ran; don't carry old backoff into this reconnect
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
        last_away_sent = 0.0
        while True:
            try:
                if self.ts_ok and self.cq and self.cq.connected:
                    # Heartbeat: re-send the status at least every 30s so a dead
                    # server link is noticed even when nothing on screen changes.
                    if time.time() - last_away_sent > 30:
                        last_away_msg = None
                    # While channel is empty, maintain away state and check 5m resume window expiration
                    if CFG.eco_mode and not self.channel_clients:
                        if last_away_msg is None and self._empty_away_msg:
                            last_away_sent = time.time()
                            try:
                                await self._cq_update(
                                    f"clientupdate client_away=1 client_away_message={escape(self._empty_away_msg)}")
                                last_away_msg = self._empty_away_msg
                            except Exception:
                                pass
                        # Safety net: the one-shot pause in _handle_channel_empty can miss
                        # (status probe failed, or BGM restarted in a race). Never let BGM
                        # run into an empty channel. User tracks are left alone.
                        try:
                            st = await self.lr.status()
                            if (st and st.get("context_uri") == CFG.chill_autoplay_uri
                                    and not st.get("paused") and not st.get("stopped")):
                                log.info("BGM playing into an empty channel. Pausing.")
                                await self.lr.pause()
                                await set_audio_mute(True)
                                self.is_ambient_autoplay = False
                        except Exception:
                            pass
                        await self._set_description(f"Type {CFG.prefix}play <song> to start the music")
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

                    # Guard against race condition while user track is buffering
                    recent_play = (GUARD.last_action_type == ACTION_PLAY and (time.time() - GUARD.last_action_time < 10.0))

                    # Detect if currently playing chill background beats vs user track
                    if not recent_play:
                        if st and st.get("context_uri") == CFG.chill_autoplay_uri:
                            self.is_ambient_autoplay = True
                        elif st and (not st.get("context_uri") or st.get("context_uri") != CFG.chill_autoplay_uri):
                            self.is_ambient_autoplay = False
                    else:
                        self.is_ambient_autoplay = False

                    # Enforce 20% volume ceiling strictly while in BGM mode (never during user play transition)
                    if self.is_ambient_autoplay and not recent_play and st:
                        curr_vol = st.get("volume", CFG.chill_volume)
                        if curr_vol > CFG.chill_volume:
                            log.info("Enforcing %d%% volume ceiling during BGM (was %d%%)", CFG.chill_volume, curr_vol)
                            try:
                                await self.lr.volume(CFG.chill_volume)
                                GUARD.mark_volume(CFG.chill_volume)
                            except Exception:
                                pass

                    # Auto-return to default ambient BGM state if channel has active users and user queue finished
                    is_user_paused = (GUARD.last_action_type == ACTION_PAUSE and (time.time() - GUARD.last_action_time < 180.0))
                    is_buffering = bool(st and st.get("buffering"))
                    if (
                        CFG.eco_mode
                        and bool(self.channel_clients)
                        and self.spotify_ok
                        and not self.is_ambient_autoplay
                        and not self._paused_by_empty_channel
                        and not is_user_paused
                        and not recent_play
                        and not is_buffering
                    ):
                        if not st or st.get("stopped") or not st.get("track"):
                            log.info("Playback ended or stopped with users in channel. Returning to default ambient chill music.")
                            await self._return_to_bgm()

                    away_flag, new_msg, desc = self._build_display(st)
                    await self._set_description(desc)

                    if new_msg != last_away_msg:
                        last_away_sent = time.time()
                        try:
                            cmd = f"clientupdate client_away={away_flag}"
                            if new_msg:
                                cmd += f" client_away_message={escape(new_msg)}"
                            else:
                                cmd += " client_away_message="
                            await self._cq_update(cmd)
                            last_away_msg = new_msg
                        except Exception as e:
                            log.warning("Failed to update away message (%s): %s", new_msg, e)
            except Exception as e:
                log.debug("UI ticker error: %s", e)
            await asyncio.sleep(CFG.ticker_interval)

    # ------------------------------------------------------------------
    # Player display (info panel)
    # ------------------------------------------------------------------
    # TeamSpeak shows the bot's panel as: name / [away status] / description.
    # Away status (80 chars) carries what is playing; the description (plain text,
    # one line, BBCode not rendered) carries the progress bar, volume and requester.
    AWAY_MAX = 78
    DESC_MAX = 190

    @staticmethod
    def _fit(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[:limit - 1] + "…"

    @staticmethod
    def _clock(sec: int) -> str:
        return f"{sec // 60}:{sec % 60:02d}"

    @staticmethod
    def _progress_bar(pos_s: int, dur_s: int, width: int = 16) -> str:
        if dur_s <= 0:
            return "●" + "─" * (width - 1)
        filled = int(round(min(max(pos_s / dur_s, 0.0), 1.0) * (width - 1)))
        return "━" * filled + "●" + "─" * (width - 1 - filled)

    def _build_display(self, st):
        """Return (away_flag, away_message, description) for the current Spotify state."""
        p = CFG.prefix
        if not st or not st.get("username"):
            return 1, "⚠️ Spotify disconnected", f"Type {p}login to link a Spotify Premium account"

        track = st.get("track") or {}
        title = track.get("name") or "Unknown track"
        artists_raw = track.get("artist_names", [])
        artists = ", ".join(artists_raw) if isinstance(artists_raw, list) else str(artists_raw or "")
        song = f"{title} — {artists}" if artists else title
        pos_s = int(track.get("position", 0)) // 1000
        dur_s = int(track.get("duration", 0)) // 1000
        times = f"{self._clock(pos_s)} / {self._clock(dur_s)}" if dur_s > 0 else self._clock(pos_s)
        vol = st.get("volume", CFG.initial_volume)
        bgm = self.is_ambient_autoplay

        if track and not st.get("paused") and not st.get("stopped"):
            if self.combined_status_line:
                # No description permission: squeeze everything into the away status.
                tail = f" {self._progress_bar(pos_s, dur_s, 8)} {times}"
                head = "♫ " if bgm else "▶ "
                return 0, head + self._fit(song, self.AWAY_MAX - len(head) - len(tail)) + tail, ""
            bits = [f"{self._progress_bar(pos_s, dur_s)} {times}"]
            if bgm:
                bits += [f"BGM {vol}%", f"type {p}play <song>"]
            else:
                bits.append(f"Vol {vol}%")
                if self._is_ducked or not self.ducking_enabled:
                    bits.append("ducking off" if not self.ducking_enabled else "ducked")
                if self.requested_by:
                    bits.append(f"req. by {self.requested_by}")
            head = "♫ " if bgm else "▶ "
            return 0, head + self._fit(song, self.AWAY_MAX - len(head)), self._fit(" · ".join(bits), self.DESC_MAX)

        if track and st.get("paused"):
            away = "⏸️ " + self._fit(song, self.AWAY_MAX - 3)
            if self.combined_status_line:
                return 0, self._fit(f"{away} · {times}", self.AWAY_MAX), ""
            return 0, away, f"Paused at {times} · type {p}resume"

        return 0, "🎵 Ready", f"Type {p}play <song> to start the music"

    @property
    def combined_status_line(self) -> bool:
        """True when the description can't be written, so the away line must carry everything."""
        return not CFG.player_description or self._desc_ok is False

    async def _set_description(self, text: str):
        """Write the bot's client description (throttled; disables itself without permission)."""
        if self.combined_status_line or not self.my_clid:
            return
        now = time.time()
        if text == self._last_desc and now - self._last_desc_sent < 60:
            return
        # Progress ticks change the text every second; only rewrite every desc_interval,
        # but react immediately when the song or state (not just the clock) changes.
        if (self._last_desc is not None and now - self._last_desc_sent < CFG.desc_interval
                and _strip_clock(text) == _strip_clock(self._last_desc)):
            return
        try:
            if self._my_dbid is None:
                self._my_dbid = (await self.cq.kv(
                    f"clientvariable clid={self.my_clid} client_database_id")).get("client_database_id")
            if not self._my_dbid:
                return
            await self._cq_update(f"clientdbedit cldbid={self._my_dbid} client_description={escape(text)}")
            self._desc_ok = True
            self._last_desc, self._last_desc_sent = text, now
        except QueryError as e:
            if "id=2568" in str(e):
                self._desc_ok = False
                log.warning("No permission to edit the bot's description (%s). Falling back to a "
                            "single status line. Grant the bot 'Modify all Client Descriptions' "
                            "(b_client_modify_description) to enable the player panel.", e)
            else:
                log.debug("Description update failed: %s", e)
        except Exception as e:
            log.debug("Description update failed: %s", e)

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
                                    if not self.is_ambient_autoplay:
                                        target_vol = getattr(self, "user_volume", CFG.initial_volume)
                                        log.info("Track playing event. Ensuring playback is at user target volume: %d%%", target_vol)
                                        try:
                                            await self.lr.volume(target_vol)
                                            GUARD.mark_volume(target_vol)
                                        except Exception:
                                            pass
                                elif etype in ("paused", "stopped"):
                                    if etype == "paused":
                                        GUARD.mark_state(ACTION_PAUSE)
                                        await set_audio_mute(True)
                                    else:
                                        GUARD.mark_state(ACTION_STOP)
                                        if bool(self.channel_clients) and not self.is_ambient_autoplay:
                                            log.info("Track stopped event with users in channel. Returning to default BGM.")
                                            asyncio.create_task(self._return_to_bgm())
                                        else:
                                            await set_audio_mute(True)
                                elif etype == "volume":
                                    vol = data.get("value")
                                    if vol is not None:
                                        if not self.is_ambient_autoplay:
                                            self.user_volume = int(vol)
                                            GUARD.mark_volume(int(vol))
                                        else:
                                            if int(vol) > CFG.chill_volume:
                                                log.info("Clamping external volume to %d%% during BGM", CFG.chill_volume)
                                                asyncio.create_task(self.lr.volume(CFG.chill_volume))
                                                GUARD.mark_volume(CFG.chill_volume)
                            except Exception as ex:
                                log.debug("Error processing player event: %s", ex)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except Exception as e:
                log.debug("Event stream reconnecting: %s", e)
            await asyncio.sleep(5)

    async def _init_volume(self):
        self.user_volume = CFG.initial_volume
        for _ in range(30):
            try:
                vol = CFG.chill_volume if self.is_ambient_autoplay else self.user_volume
                await self.lr.volume(vol)
                return
            except Exception:
                await asyncio.sleep(2)
