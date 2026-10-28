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
