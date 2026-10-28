import time
from collections import deque
import logging

log = logging.getLogger("ratelimit")

class RateLimiter:
    """
    Multi-user rate limiter designed for active, high-traffic voice servers.
    Provides per-user cooldowns, burst-spam detection with temporary penalty timeouts,
    and a global throughput brake to protect background services.
    """
    def __init__(self, user_cooldown=1.2, burst_max=4, burst_window=4.0, penalty_duration=5.0, global_max_per_sec=4):
        self.user_cooldown = user_cooldown
        self.burst_max = burst_max
        self.burst_window = burst_window
        self.penalty_duration = penalty_duration
        self.global_max_per_sec = global_max_per_sec

        self._last_user_cmd = {}     # uid -> float (timestamp of last command)
        self._user_bursts = {}       # uid -> deque of recent timestamps
        self._user_penalties = {}    # uid -> float (expiry of spam penalty)
        self._user_warned = set()    # uid set (to send warning once per penalty)
        self._global_timestamps = deque()

    def check(self, uid: str, is_admin: bool = False) -> tuple[bool, str]:
        """
        Check whether a user command is permitted.
        Returns: (allowed: bool, user_message: str)
        If allowed is False and user_message is non-empty, the bot will notify the user.
        If user_message is empty, the command is silently dropped to avoid chat spam.
        """
        if is_admin:
            return True, ""

        now = time.time()

        # 1. Check if user is currently in penalty box for spamming
        penalty_until = self._user_penalties.get(uid, 0.0)
        if now < penalty_until:
            if uid not in self._user_warned:
                self._user_warned.add(uid)
                rem = max(1, int(penalty_until - now))
                return False, f"⏳ [b]Slow down![/b] Command access paused for {rem}s due to rapid spam."
            return False, "" # Silent drop subsequent spam while penalized

        # Penalty expired
        if uid in self._user_warned:
            self._user_warned.remove(uid)

        # 2. Check per-user cooldown between single commands
        last_time = self._last_user_cmd.get(uid, 0.0)
        if now - last_time < self.user_cooldown:
            return False, "" # Silent drop to prevent command spam war filling chat

        # 3. Check burst queue (e.g. max 4 commands within 4 seconds)
        burst_queue = self._user_bursts.setdefault(uid, deque())
        while burst_queue and (now - burst_queue[0] > self.burst_window):
            burst_queue.popleft()

        burst_queue.append(now)
        if len(burst_queue) > self.burst_max:
            # Trigger penalty box
            self._user_penalties[uid] = now + self.penalty_duration
            self._user_warned.add(uid)
            log.warning("User %s triggered command burst limit; penalized for %ss", uid, self.penalty_duration)
            return False, f"⚠️ [b]Spam protection triggered:[/b] Please wait {int(self.penalty_duration)}s before sending more commands."

        # 4. Check global channel throughput brake
        while self._global_timestamps and (now - self._global_timestamps[0] > 1.0):
            self._global_timestamps.popleft()

        if len(self._global_timestamps) >= self.global_max_per_sec:
            log.info("Global command throughput reached limit (%s/s)", self.global_max_per_sec)
            return False, "⏳ Bot is currently busy handling server requests. Please wait a second."

        # Command accepted
        self._last_user_cmd[uid] = now
        self._global_timestamps.append(now)

        # Periodic cleanup of old dictionary entries to prevent memory leaks
        if len(self._last_user_cmd) > 200:
            cutoff = now - 60.0
            self._last_user_cmd = {u: t for u, t in self._last_user_cmd.items() if t > cutoff}
            self._user_bursts = {u: q for u, q in self._user_bursts.items() if q and q[-1] > cutoff}
            self._user_penalties = {u: p for u, p in self._user_penalties.items() if p > now}

        return True, ""
