"""System audio loopback (v1.5.7) — захват того что играет в колонках.

Использует библиотеку `soundcard` (PyPI) для cross-platform loopback:
- Windows: WASAPI loopback через `mic.isloopback=True`
- macOS: BlackHole / Soundflower / встроенный loopback (только если установлен)
- Linux: PulseAudio monitor sources

**Только одно активное** в каждый момент (single instance lock в server.py).
"""
from __future__ import annotations

import logging
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger("autrau.system_audio")

# Sample rate для ASR (16kHz моно — стандарт для whisper/parakeet)
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM


def is_available() -> tuple[bool, str]:
    """Check if soundcard is installed and at least one loopback device exists."""
    try:
        import soundcard  # noqa: F401
    except ImportError as e:
        return False, f"soundcard не установлен: {e}. Поставь: pip install soundcard"
    try:
        loopbacks = list_loopback_devices()
    except Exception as e:
        return False, f"Ошибка при перечислении устройств: {e}"
    if not loopbacks:
        return False, "Нет loopback-устройств. На Windows: включите Stereo Mix или используйте наушники с loopback."
    return True, ""


def list_loopback_devices() -> list[dict]:
    """List available loopback (output) audio devices.

    Returns: [{"id": int, "name": str}, ...]
    """
    import soundcard
    devices = []
    for i, mic in enumerate(soundcard.all_microphones(include_loopback=True)):
        if mic.isloopback:
            devices.append({"id": i, "name": mic.name})
    return devices


class SystemAudioRecorder:
    """Single recording session.

    Usage:
        rec = SystemAudioRecorder(device_id=0)
        rec.start()
        ... wait ...
        wav_path = rec.stop()  # Path to saved WAV
    """
    def __init__(self, device_id: int = 0, sample_rate: int = SAMPLE_RATE):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self._recorder = None
        self._thread: Optional[threading.Thread] = None
        self._frames: list[bytes] = []
        self._wav_path: Optional[Path] = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._error: Optional[str] = None
        self._stop_requested = threading.Event()

    def start(self) -> None:
        """Start recording in background thread."""
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("Already recording")
            self._frames = []
            self._wav_path = None
            self._error = None
            self._stop_requested.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(target=self._run, daemon=True, name="system-audio-rec")
            self._thread.start()
            log.info("System audio recording started: device=%d rate=%d", self.device_id, self.sample_rate)

    def _run(self) -> None:
        """Background recording loop."""
        try:
            import soundcard
            import numpy as np
            mics = soundcard.all_microphones(include_loopback=True)
            if self.device_id >= len(mics):
                self._error = f"device_id {self.device_id} out of range (have {len(mics)} devices)"
                return
            mic = mics[self.device_id]
            if not mic.isloopback:
                self._error = f"device {self.device_id} ({mic.name}) is not a loopback — cannot capture system audio"
                return
            # recorder context manager
            with mic.recorder(samplerate=self.sample_rate) as rec:
                # Read in 100ms chunks (~0.1s @ 16kHz = 1600 frames)
                chunk_size = self.sample_rate // 10
                while not self._stop_requested.is_set():
                    try:
                        data = rec.record(numframes=chunk_size)
                    except Exception as e:
                        self._error = f"record failed: {e}"
                        log.error("record failed: %s", e)
                        break
                    if data is None or len(data) == 0:
                        continue
                    # soundcard может вернуть (N, channels) или (N,)
                    if hasattr(data, 'tobytes'):
                        if data.ndim == 2:
                            # микс в моно если стерео
                            data_mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
                        else:
                            data_mono = data
                        # convert to int16 PCM
                        if data_mono.dtype != 'int16':
                            data_mono = (data_mono * 32767).astype('int16')
                        self._frames.append(data_mono.tobytes())
        except Exception as e:
            self._error = f"recording thread crashed: {e}"
            log.exception("recording thread crashed")
        finally:
            # Save WAV
            if self._frames:
                try:
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".wav", prefix="autrau-sys-",
                    ) as tf:
                        self._wav_path = Path(tf.name)
                    with wave.open(str(self._wav_path), "wb") as wf:
                        wf.setnchannels(CHANNELS)
                        wf.setsampwidth(SAMPLE_WIDTH)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes(b"".join(self._frames))
                    log.info("System audio WAV saved: %s (%d bytes, %.1fs)",
                             self._wav_path, self._wav_path.stat().st_size,
                             (time.time() - (self._started_at or time.time())))
                except Exception as e:
                    log.error("Failed to save WAV: %s", e)
                    self._error = f"Failed to save WAV: {e}"

    def stop(self) -> Optional[Path]:
        """Stop recording, return path to WAV file (or None on error)."""
        with self._lock:
            if self._thread is None:
                return None
            self._stop_requested.set()
            self._thread.join(timeout=15)
            self._thread = None
            if self._error:
                log.warning("Recording stopped with error: %s", self._error)
            return self._wav_path

    def elapsed_sec(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at
