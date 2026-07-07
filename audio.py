"""Microphone recorder for push-to-talk.

start() opens a 16 kHz mono input stream and buffers samples; stop() returns
the captured audio as a 1-D float32 numpy array ready for Whisper. A live RMS
level is throttled to ~33 fps and pushed through `on_level`.
"""
import time

import numpy as np
import sounddevice as sd

import config


class AudioRecorder:
    def __init__(self, on_level=None):
        self.on_level = on_level
        self._stream = None
        self._chunks = []
        self._recording = False
        self._last_level_ts = 0.0

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self):
        if self._recording:
            return
        self._chunks = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if not self._recording:
            return np.array([], dtype=np.float32)
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        audio = (np.concatenate(self._chunks, axis=0).flatten()
                 if self._chunks else np.array([], dtype=np.float32))
        self._chunks = []
        return audio

    def _callback(self, indata, frames, time_info, status):
        if not self._recording:
            return
        self._chunks.append(indata.copy())  # indata buffer is reused -> copy
        if self.on_level is None:
            return
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        now = time.monotonic()
        if now - self._last_level_ts > 0.03:   # ~33 fps
            self._last_level_ts = now
            self.on_level(rms)
