import os
import asyncio
import logging

log = logging.getLogger("pulse")

PULSE_ENV = {**os.environ, "PULSE_SERVER": "unix:/tmp/pulse.sock"}

async def set_audio_mute(mute: bool) -> bool:
    """
    Instantly mutes or unmutes the PulseAudio 'music' sink and 'music.monitor' source.
    This provides immediate, hardware-level silence in TeamSpeak without waiting on
    daemon buffers or network latency.
    """
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
        log.debug("PulseAudio mute set to %s (val=%s)", mute, val)
        return True
    except Exception as e:
        log.warning("Failed to set PulseAudio mute state (%s): %s", mute, e)
        return False
