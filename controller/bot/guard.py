import asyncio
import time
import logging
from collections import deque
from .pulse import set_audio_mute

log = logging.getLogger("guard")

ACTION_NONE = 0
ACTION_PLAY = 1
ACTION_PAUSE = 2
ACTION_STOP = 3

class PlayerGuard:
    """
    Guards the audio player against multi-user abuse, play/pause wars,
    concurrent request thrashing, and rapid spam in TeamSpeak.
    """
    def __init__(self, anti_thrash_cooldown=1.0, skip_cooldown=0.8, vol_cooldown=0.5, max_queue_per_min=5):
        self.lock = asyncio.Lock()
        self.anti_thrash_cooldown = anti_thrash_cooldown
        self.skip_cooldown = skip_cooldown
        self.vol_cooldown = vol_cooldown
        self.max_queue_per_min = max_queue_per_min

        self.last_action_type = ACTION_NONE
        self.last_action_time = 0.0
        self.last_skip_time = 0.0
        self.last_vol_time = 0.0
        self.last_volume = None

        self._user_queue_history = {}    # uid -> deque of timestamps
        self._recent_queued_uris = deque() # deque of (uri, timestamp)

    def can_toggle_state(self, new_action: int, is_admin: bool = False) -> tuple[bool, str]:
        """
        Prevents multi-user play/pause fighting in voice channels.
        If playback was just started, prevents instant pausing.
        If playback was just paused/stopped, prevents instant resuming.
        """
        if is_admin:
            return True, ""

        now = time.time()
        time_since_last = now - self.last_action_time

        if time_since_last < self.anti_thrash_cooldown:
            if new_action in (ACTION_PAUSE, ACTION_STOP) and self.last_action_type == ACTION_PLAY:
                rem = round(self.anti_thrash_cooldown - time_since_last, 1)
                return False, f"⏳ Playback just started. Please wait {rem}s before pausing."
            if new_action == ACTION_PLAY and self.last_action_type in (ACTION_PAUSE, ACTION_STOP):
                rem = round(self.anti_thrash_cooldown - time_since_last, 1)
                return False, f"⏳ Playback was just paused. Please wait {rem}s before resuming."

        return True, ""

    def mark_state(self, action: int):
        self.last_action_type = action
        self.last_action_time = time.time()

    def can_skip(self, is_admin: bool = False) -> tuple[bool, str]:
        if is_admin:
            return True, ""
        now = time.time()
        if now - self.last_skip_time < self.skip_cooldown:
            return False, "⏳ Skip is on cooldown or track is currently loading. Please wait."
        return True, ""

    def mark_skip(self):
        self.last_skip_time = time.time()

    def can_adjust_volume(self, is_admin: bool = False) -> tuple[bool, str]:
        if is_admin:
            return True, ""
        now = time.time()
        if now - self.last_vol_time < self.vol_cooldown:
            return False, "⏳ Volume was just adjusted. Please wait a moment."
        return True, ""

    def mark_volume(self, vol: int):
        self.last_vol_time = time.time()
        self.last_volume = vol

    def can_queue_track(self, uid: str, uri: str, is_admin: bool = False) -> tuple[bool, str]:
        if is_admin:
            return True, ""
        now = time.time()

        # Check user queue rate limit (e.g. max 3 tracks per minute)
        q = self._user_queue_history.setdefault(uid, deque())
        while q and (now - q[0] > 60.0):
            q.popleft()

        if len(q) >= self.max_queue_per_min:
            return False, f"⚠️ You can queue up to {self.max_queue_per_min} tracks per minute. Please wait for current tracks to play."

        # Check duplicate URI recently added (within 15s)
        while self._recent_queued_uris and (now - self._recent_queued_uris[0][1] > 15.0):
            self._recent_queued_uris.popleft()

        for recent_uri, _ in self._recent_queued_uris:
            if recent_uri == uri:
                return False, "⚠️ This track was just queued a moment ago."

        return True, ""

    def mark_queued(self, uid: str, uri: str):
        now = time.time()
        q = self._user_queue_history.setdefault(uid, deque())
        q.append(now)
        self._recent_queued_uris.append((uri, now))

GUARD = PlayerGuard()
