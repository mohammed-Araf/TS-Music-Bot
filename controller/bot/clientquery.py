import asyncio, logging
from .tsescape import escape, parse_line

log = logging.getLogger("clientquery")

class QueryError(Exception):
    pass

class ClientQuery:
    def __init__(self, host, port, apikey, on_event):
        self.host, self.port, self.apikey = host, port, apikey
        self.on_event = on_event            # async callable(name, fields)
        self._r = self._w = None
        self._lock = asyncio.Lock()
        self._pending = None                # future for current command
        self._buf = []
        self._task = None
        self.connected = False

    async def connect(self):
        self._r, self._w = await asyncio.open_connection(self.host, self.port)
        self._task = asyncio.create_task(self._read_loop())
        await asyncio.sleep(0.5)            # let the banner arrive
        await self.cmd(f"auth apikey={self.apikey}")
        self.connected = True

    async def close(self):
        self.connected = False
        if self._task:
            self._task.cancel()
        if self._w:
            self._w.close()

    async def _read_loop(self):
        try:
            while True:
                raw = await self._r.readuntil(b"\n")
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith("notify"):
                    name, fields = parse_line(line)
                    asyncio.create_task(self.on_event(name, fields))
                elif line.startswith("error "):
                    _, f = parse_line(line)
                    if self._pending and not self._pending.done():
                        self._pending.set_result((list(self._buf), f))
                    self._buf.clear()
                else:
                    self._buf.append(line)
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.connected = False
            if self._pending and not self._pending.done():
                self._pending.set_exception(ConnectionError("ClientQuery closed"))

    async def cmd(self, text: str, timeout: float = 8.0):
        """Send one command. Returns the list of data lines. Raises QueryError on error id != 0."""
        async with self._lock:
            self._buf.clear()
            self._pending = asyncio.get_running_loop().create_future()
            self._w.write((text + "\n").encode())
            await self._w.drain()
            lines, err = await asyncio.wait_for(self._pending, timeout)
            if err.get("id") != "0":
                raise QueryError(f"{text.split(' ')[0]}: id={err.get('id')} msg={err.get('msg')}")
            return lines

    # ---- helpers ----
    async def kv(self, text):
        lines = await self.cmd(text)
        return parse_line("x " + lines[0])[1] if lines else {}

    async def say(self, cid: str, msg: str):
        # TS chat limit is about 1024 bytes per message
        for chunk in _chunks(msg, 900):
            await self.cmd(f"sendtextmessage targetmode=2 target={cid} msg={escape(chunk)}")

def _chunks(s, n):
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]
