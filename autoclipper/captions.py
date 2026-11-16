"""Word-level captions with faster-whisper. Uses the GPU if it can, else CPU."""
_model = None


def _load(model_name: str):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        try:
            # GTX 16xx cards run int8 on CUDA well
            _model = WhisperModel(model_name, device="cuda", compute_type="int8")
            print("   Captions: using GPU")
        except Exception:
            _model = WhisperModel(model_name, device="cpu", compute_type="int8")
            print("   Captions: using CPU (slower, still fine for short clips)")
    return _model


def transcribe_words(path: str, model_name: str = "small") -> list[dict]:
    try:
        model = _load(model_name)
        segments, _ = model.transcribe(path, word_timestamps=True, vad_filter=True)
        words = []
        for seg in segments:
            for w in seg.words or []:
                words.append({"word": w.word, "start": w.start, "end": w.end})
        return words
    except Exception as e:
        print(f"   (captions skipped: {e})")
        return []


def hook_from_words(words: list[dict], max_words: int = 6) -> str | None:
    """Use the first spoken words as an on-screen hook line."""
    if not words:
        return None
    text = " ".join(w["word"].strip() for w in words[:max_words]).strip(" .,")
    return text or None
