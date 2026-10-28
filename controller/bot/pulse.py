import os
import asyncio
import logging

log = logging.getLogger("pulse")

PULSE_ENV = {**os.environ, "PULSE_SERVER": "unix:/tmp/pulse.sock"}
_current_mute_state = None
_mute_lock = asyncio.Lock()

async def set_audio_mute(mute: bool) -> bool:
    """
    Instantly mutes or unmutes the PulseAudio 'music' sink and 'music.monitor' source.
    Provides immediate, hardware-level silence in TeamSpeak with zero delay.
    Includes state caching and concurrency locking to eliminate redundant subprocess calls.
    """
    global _current_mute_state

    if _current_mute_state is mute:
        return True

    async with _mute_lock:
        if _current_mute_state is mute:
            return True

        val = "1" if mute else "0"
        try:
            proc1 = await asyncio.create_subprocess_exec(
                "pactl", "set-sink-mute", "music", val,
                env=PULSE_ENV,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            proc2 = await asyncio.create_subprocess_exec(
                "pactl", "set-source-mute", "music.monitor", val,
                env=PULSE_ENV,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.gather(proc1.wait(), proc2.wait())
            _current_mute_state = mute
            log.debug("PulseAudio mute set to %s (val=%s)", mute, val)
            return True
        except Exception as e:
            log.warning("Failed to set PulseAudio mute state (%s): %s", mute, e)
            return False

_current_duck_state = None
_duck_lock = asyncio.Lock()

async def set_audio_duck(duck: bool, duck_pct: int = 30) -> bool:
    """
    Hardware-level voice ducking via PulseAudio sink volume.
    When duck=True, reduces sink volume to duck_pct (default 30%).
    When duck=False, restores sink volume to 100%.
    """
    global _current_duck_state

    desired_pct = max(5, min(duck_pct, 95)) if duck else 100
    state_key = (duck, desired_pct)
    if _current_duck_state == state_key:
        return True

    async with _duck_lock:
        if _current_duck_state == state_key:
            return True

        val = f"{desired_pct}%"
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "set-sink-volume", "music", val,
                env=PULSE_ENV,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            _current_duck_state = state_key
            log.debug("PulseAudio ducking set to %s (val=%s)", duck, val)
            return True
        except Exception as e:
            log.warning("Failed to set PulseAudio ducking state (%s): %s", duck, e)
            return False

