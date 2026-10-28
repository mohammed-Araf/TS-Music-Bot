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

    async def _post(self, path, json=None, timeout=25):
        async with self.s.post(self.base + path, json=json,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status >= 400:
                raise RuntimeError(f"{path} -> HTTP {r.status}: {await r.text()}")

    async def status(self):
        async with self.s.get(self.base + "/status", timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 204:
                return None
            r.raise_for_status()
            return await r.json()

    async def auth_code(self):
        async with self.s.get(self.base + "/auth/code", timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 204:
                return None
            r.raise_for_status()
            return await r.json()

    async def play(self, uri):    await self._post("/player/play", {"uri": uri})
    async def resume(self):       await self._post("/player/resume")
    async def pause(self):        await self._post("/player/pause")
    async def playpause(self):    await self._post("/player/playpause")
    async def next(self):         await self._post("/player/next")
    async def prev(self):         await self._post("/player/prev")
    async def volume(self, v):    await self._post("/player/volume", {"volume": int(v)})
    async def enqueue(self, uri): await self._post("/player/add_to_queue", {"uri": uri})

class SpotifyRateLimitError(Exception):
    def __init__(self, retry_after=30):
        self.retry_after = retry_after
        super().__init__(f"Rate limited by Spotify API (retry after {retry_after}s)")

class SpotifyAuthError(Exception):
    pass

class Search:
    """Spotify Web API, client-credentials flow, search only."""
    def __init__(self, cid, secret, session):
        self.cid, self.secret, self.s = cid, secret, session
        self._tok, self._exp = None, 0

    def set_credentials(self, cid, secret):
        self.cid, self.secret = cid, secret
        self._tok, self._exp = None, 0

    async def verify(self, cid=None, secret=None):
        """Test if credentials can successfully obtain an access token."""
        test_cid = cid or self.cid
        test_secret = secret or self.secret
        if not test_cid or not test_secret:
            raise SpotifyAuthError("Missing Client ID or Secret.")
        try:
            async with self.s.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(test_cid, test_secret),
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 429:
                    retry_after = int(r.headers.get("Retry-After", 30))
                    raise SpotifyRateLimitError(retry_after)
                if r.status in (400, 401):
                    raise SpotifyAuthError("Invalid Client ID or Client Secret.")
                r.raise_for_status()
                d = await r.json()
                return d.get("access_token")
        except (SpotifyRateLimitError, SpotifyAuthError):
            raise
        except Exception as e:
            raise SpotifyAuthError(f"Spotify connection error: {e}")

    async def _token(self):
        if self._tok and time.time() < self._exp - 30:
            return self._tok
        if not self.cid or not self.secret:
            raise SpotifyAuthError("No Spotify API credentials configured.")
        async with self.s.post("https://accounts.spotify.com/api/token",
                               data={"grant_type": "client_credentials"},
                               auth=aiohttp.BasicAuth(self.cid, self.secret),
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 429:
                retry_after = int(r.headers.get("Retry-After", 30))
                raise SpotifyRateLimitError(retry_after)
            if r.status in (400, 401):
                raise SpotifyAuthError("Invalid Spotify Client ID or Client Secret.")
            r.raise_for_status()
            d = await r.json()
        self._tok, self._exp = d["access_token"], time.time() + d["expires_in"]
        return self._tok

    async def tracks(self, query, limit=5):
        tok = await self._token()
        async with self.s.get("https://api.spotify.com/v1/search",
                              params={"q": query, "type": "track", "limit": limit},
                              headers={"Authorization": f"Bearer {tok}"},
                              timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 429:
                retry_after = int(r.headers.get("Retry-After", 30))
                raise SpotifyRateLimitError(retry_after)
            r.raise_for_status()
            d = await r.json()
        return [{"uri": t["uri"], "name": t["name"],
                 "artists": ", ".join(a["name"] for a in t["artists"])}
                for t in d.get("tracks", {}).get("items", [])]
