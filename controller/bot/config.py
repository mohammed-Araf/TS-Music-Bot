import os
from dataclasses import dataclass

def _f(name, default): return float(os.environ.get(name, default))
def _i(name, default): return int(os.environ.get(name, default))

@dataclass(frozen=True)
class Config:
    prefix: str = os.environ.get("CMD_PREFIX", "!")
    cooldown: float = _f("CMD_COOLDOWN", 1.5)

    cq_host: str = "127.0.0.1"
    cq_port: int = 25639
    cq_apikey: str = os.environ.get("TS_CLIENTQUERY_APIKEY", "musicbot_default_clientquery_key")
    ts_channel: str = os.environ.get("TS_CHANNEL", "")
    ts_channel_password: str = os.environ.get("TS_CHANNEL_PASSWORD", "")

    admin_uids: frozenset = frozenset(
        u.strip() for u in os.environ.get("ADMIN_UIDS", "").split(",") if u.strip()
    )
    admin_server_groups: frozenset = frozenset(
        g.strip() for g in os.environ.get("ADMIN_SERVER_GROUPS", "").split(",") if g.strip()
    )
    allowed_server_groups: frozenset = frozenset(
        g.strip() for g in os.environ.get("ALLOWED_SERVER_GROUPS", "").split(",") if g.strip()
    )

    lr_url: str = "http://127.0.0.1:3678"
    sp_client_id: str = os.environ.get("SPOTIFY_CLIENT_ID", "")
    sp_client_secret: str = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

    max_volume: int = _i("MAX_VOLUME", 80)
    initial_volume: int = _i("INITIAL_VOLUME", 40)

    auto_ducking: bool = os.environ.get("AUTO_DUCKING", "true").lower() in ("true", "1", "yes")
    duck_percent: int = _i("DUCK_PERCENT", 30)
    duck_hold_time: float = _f("DUCK_HOLD_TIME", 1.8)
    eco_mode: bool = os.environ.get("ECO_MODE", "true").lower() in ("true", "1", "yes")
    eco_resume_window: int = _i("ECO_RESUME_WINDOW", 300)
    chill_autoplay_uri: str = os.environ.get("CHILL_AUTOPLAY_URI", "spotify:playlist:37i9dQZF1DWWQRwui0ExPn")
    chill_volume: int = _i("CHILL_VOLUME", 20)
    ticker_interval: float = _f("TICKER_INTERVAL", 2.0)

    health_port: int = 8080

CFG = Config()
