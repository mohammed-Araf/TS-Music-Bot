import re, time, aiohttp

URI_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist|artist)/([A-Za-z0-9]+)"
    r"|spotify:(track|album|playlist|artist):([A-Za-z0-9]+)"
)

def to_uri(text: str):
    m = URI_RE.search(text)
    if not m:
        return None
    kind, sid = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return f"spotify:{kind}:{sid}"

class Librespot:
    """Client for go-librespot local HTTP control API."""
    def __init__(self, base, session):
        self.base, self.s = base, session

    async def _post(self, path, json=None):
        async with self.s.post(self.base + path, json=json,
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status >= 400:
                raise RuntimeError(f"{path} -> HTTP {r.status}: {await r.text()}")

    async def status(self):
        async with self.s.get(self.base + "/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            r.raise_for_status()
            return await r.json()

    async def play(self, uri):    await self._post("/player/play", {"uri": uri})
    async def resume(self):       await self._post("/player/resume")
    async def pause(self):        await self._post("/player/pause")
    async def next(self):         await self._post("/player/next")
    async def prev(self):         await self._post("/player/prev")
    async def volume(self, v):    await self._post("/player/volume", {"volume": int(v)})
    async def enqueue(self, uri): await self._post("/player/add_to_queue", {"uri": uri})

class Search:
    """Spotify Web API, client-credentials flow, search only."""
    def __init__(self, cid, secret, session):
        self.cid, self.secret, self.s = cid, secret, session
        self._tok, self._exp = None, 0

    async def _token(self):
        if self._tok and time.time() < self._exp - 30:
            return self._tok
        async with self.s.post("https://accounts.spotify.com/api/token",
                               data={"grant_type": "client_credentials"},
                               auth=aiohttp.BasicAuth(self.cid, self.secret)) as r:
            r.raise_for_status()
            d = await r.json()
        self._tok, self._exp = d["access_token"], time.time() + d["expires_in"]
        return self._tok

    async def tracks(self, query, limit=5):
        tok = await self._token()
        async with self.s.get("https://api.spotify.com/v1/search",
                              params={"q": query, "type": "track", "limit": limit},
                              headers={"Authorization": f"Bearer {tok}"}) as r:
            r.raise_for_status()
            d = await r.json()
        return [{"uri": t["uri"], "name": t["name"],
                 "artists": ", ".join(a["name"] for a in t["artists"])}
                for t in d.get("tracks", {}).get("items", [])]
