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

_current_sink_volume: int = 100
_fade_task = None
_duck_lock = asyncio.Lock()

async def _fade_worker(target: int, duck: bool):
    global _current_sink_volume
    start = _current_sink_volume
    if start == target:
        return

    # 300ms for ducking down (6 steps of 50ms)
    # 500ms for releasing back up (8 steps of 60ms)
    steps = 6 if duck else 8
    step_delay = 0.05 if duck else 0.06
    diff = target - start

    try:
        for i in range(1, steps + 1):
            vol = int(start + (diff * (i / steps)))
            proc = await asyncio.create_subprocess_exec(
                "pactl", "set-sink-volume", "music", f"{vol}%",
                env=PULSE_ENV,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            _current_sink_volume = vol
            await asyncio.sleep(step_delay)
        _current_sink_volume = target
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("Fade worker error: %s", e)

async def set_audio_duck(duck: bool, duck_pct: int = 30) -> bool:
    """
    Smooth, broadcast-grade voice ducking via progressive volume interpolation.
    Fades down to duck_pct over ~300ms when someone speaks, and smoothly fades
    back up to 100% over ~500ms when they stop.
    """
    global _fade_task

    target = max(5, min(duck_pct, 95)) if duck else 100

    async with _duck_lock:
        if _fade_task and not _fade_task.done():
            _fade_task.cancel()
            try:
                await _fade_task
            except asyncio.CancelledError:
                pass
        _fade_task = asyncio.create_task(_fade_worker(target, duck))
    return True

