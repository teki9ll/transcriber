"""Whisper wrapper with a switchable backend (faster-whisper or vanilla openai-whisper).

Both backends accept a 16 kHz mono float32 numpy array and return plain text.
Models are cached after first load so switching between them is instant.
"""
import numpy as np

import config


class Transcriber:
    def __init__(self):
        self.backend = config.BACKEND
        self.device = config.DEVICE
        self._cache = {}          # canonical name -> loaded model
        self.current = None       # canonical name currently loaded

    # -- loading -----------------------------------------------------------
    def _load(self, name: str):
        fw_name, ow_name = config.MODELS[name]
        if self.backend == "openai":
            import whisper
            return whisper.load_model(ow_name, device=self.device)
        from faster_whisper import WhisperModel
        return WhisperModel(fw_name, device=self.device, compute_type=config.COMPUTE_TYPE)

    def load(self, name: str) -> str:
        """Load (or switch to) a model by canonical name. Returns the loaded name."""
        name = name if name in config.MODELS else config.DEFAULT_MODEL
        if name not in self._cache:
            self._cache[name] = self._load(name)
        self.current = name
        return name

    # -- inference ---------------------------------------------------------
    def transcribe(self, audio: np.ndarray) -> str:
        if self.current is None:
            self.load(config.DEFAULT_MODEL)
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        if audio.size == 0:
            return ""
        model = self._cache[self.current]

        if self.backend == "openai":
            result = model.transcribe(audio, fp16=config.CUDA, verbose=False)
            return (result.get("text") or "").strip()

        segments, _info = model.transcribe(
            audio,
            beam_size=1,
            vad_filter=True,                      # trim leading/trailing silence
            condition_on_previous_text=False,    # avoids repetition hallucinations
        )
        return " ".join(s.text for s in segments).strip()
