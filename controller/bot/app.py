import asyncio, logging, time
import aiohttp
from aiohttp import web
from .config import CFG
from .clientquery import ClientQuery, QueryError
from .spotify import Librespot, Search
from .tsescape import strip_bbcode
from .commands import REGISTRY, Ctx

log = logging.getLogger("app")

class App:
    def __init__(self):
        self.session = None
        self.cq = None
        self.lr = None
        self.search = None
        self.my_clid = None
        self.my_cid = None
        self.last_cmd = {}          # uid -> timestamp (rate limit)
        self.ts_ok = False
        self.spotify_ok = False

    async def on_event(self, name, f):
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
        uid, nick = f.get("invokeruid", ""), f.get("invokername", "?")
        if admin_only and uid not in CFG.admin_uids:
            await self.cq.say(self.my_cid, "Admins only.")
            return
        now = time.time()
        if now - self.last_cmd.get(uid, 0) < CFG.cooldown:
            return
        self.last_cmd[uid] = now
        ctx = Ctx(CFG, self.cq, self.lr, self.search, uid, nick, self.my_cid)
        try:
            reply = await handler(ctx, arg.strip())
        except Exception as e:
            log.exception("command failed: %s", cmd)
            reply = f"Error: {e}"
        if reply:
            await self.cq.say(self.my_cid, reply)

    async def _ts_session(self):
        """Connect to ClientQuery, register for chat events, keep the connection alive."""
        self.cq = ClientQuery(CFG.cq_host, CFG.cq_port, CFG.cq_apikey, self.on_event)
        await self.cq.connect()
        sch = (await self.cq.kv("currentschandlerid")).get("schandlerid", "1")
        await self.cq.cmd(f"clientnotifyregister schandlerid={sch} event=notifytextmessage")
        while self.cq.connected:
            try:
                who = await self.cq.kv("whoami")      # fails if not connected to a server
                self.my_clid, self.my_cid = who.get("clid"), who.get("cid")
                self.ts_ok = bool(self.my_clid)
            except (QueryError, asyncio.TimeoutError):
                self.ts_ok = False
            await asyncio.sleep(10)

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
        while True:
            try:
                await self.lr.status()
                self.spotify_ok = True
            except Exception:
                self.spotify_ok = False
            await asyncio.sleep(15)

    async def health(self, request):
        ok = self.ts_ok and self.spotify_ok
        return web.json_response({"ts": self.ts_ok, "spotify": self.spotify_ok},
                                 status=200 if ok else 503)

    async def run(self):
        self.session = aiohttp.ClientSession()
        self.lr = Librespot(CFG.lr_url, self.session)
        self.search = Search(CFG.sp_client_id, CFG.sp_client_secret, self.session)

        app = web.Application()
        app.router.add_get("/health", self.health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", CFG.health_port).start()

        # best-effort: set initial volume once go-librespot is up
        asyncio.create_task(self._init_volume())
        await asyncio.gather(self.ts_loop(), self.spotify_loop())

    async def _init_volume(self):
        for _ in range(30):
            try:
                await self.lr.volume(CFG.initial_volume)
                return
            except Exception:
                await asyncio.sleep(2)
