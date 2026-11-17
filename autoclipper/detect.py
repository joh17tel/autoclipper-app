"""Find hype moments in a stream using audio loudness + chat activity."""
import subprocess
import numpy as np


def audio_energy_per_second(media_path: str) -> np.ndarray:
    """Return loudness (RMS) for each second of audio."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", media_path,
        "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    sr = 8000
    n = len(samples) // sr
    if n == 0:
        return np.zeros(0)
    frames = samples[: n * sr].reshape(n, sr)
    return np.sqrt((frames ** 2).mean(axis=1))


def chat_counts_per_second(url: str, duration: int) -> np.ndarray:
    """Messages per second from the VOD chat replay (Twitch/YouTube). Optional."""
    counts = np.zeros(max(duration, 1))
    try:
        from chat_downloader import ChatDownloader
        chat = ChatDownloader().get_chat(url)
        for msg in chat:
            t = msg.get("time_in_seconds")
            if t is not None and 0 <= t < duration:
                counts[int(t)] += 1
    except Exception as e:  # chat not available (e.g. Kick) — audio only
        print(f"   (chat not used: {type(e).__name__})")
    return counts


def _zscore_rolling(x: np.ndarray, window: int = 300) -> np.ndarray:
    """How unusual each second is compared to the ~5 minutes around it."""
    if len(x) == 0:
        return x
    k = np.ones(window) / window
    pad = window // 2
    xp = np.pad(x, pad, mode="edge")
    mean = np.convolve(xp, k, mode="same")[pad: pad + len(x)]
    sq = np.convolve(xp ** 2, k, mode="same")[pad: pad + len(x)]
    std = np.sqrt(np.maximum(sq - mean ** 2, 1e-6))
    return (x - mean) / std


def _smooth(x: np.ndarray, w: int = 3) -> np.ndarray:
    if len(x) < w:
        return x
    return np.convolve(x, np.ones(w) / w, mode="same")


def clip_count(duration_s: int, per_hour: float, lo: int, hi: int) -> int:
    """More clips from longer streams: e.g. 4h stream x 3/hour = 12 (capped)."""
    return int(max(lo, min(hi, round(duration_s / 3600 * per_hour))))


def find_highlights(audio: np.ndarray, chat: np.ndarray | None, n: int,
                    before: int, after: int, min_gap: int,
                    min_score: float = 1.5, extra: np.ndarray | None = None) -> list[tuple[int, int, float]]:
    """Return up to n (start, end, score) windows, best first, non-overlapping."""
    dur = len(audio)
    if dur == 0:
        return []
    score = _smooth(_zscore_rolling(audio))
    if chat is not None and chat.sum() > 20:
        chat = chat[:dur] if len(chat) >= dur else np.pad(chat, (0, dur - len(chat)))
        # chat reacts a few seconds late, so shift it back
        shifted = np.roll(_smooth(chat, 5), -4)
        score = 0.6 * score + 0.4 * _zscore_rolling(shifted)
    if extra is not None and len(extra) and np.max(extra) > 0:
        ex = extra[:dur] if len(extra) >= dur else np.pad(extra, (0, dur - len(extra)))
        ex = (ex - ex.mean()) / (ex.std() + 1e-6)   # viewers re-watching = proven moment
        score = 0.55 * score + 0.45 * ex

    order = np.argsort(score)[::-1]
    picks: list[tuple[int, int, float]] = []
    peaks: list[int] = []
    for peak in order:
        if len(picks) >= n:
            break
        if score[peak] < min_score:  # nothing unusual left
            break
        if any(abs(int(peak) - p) < min_gap for p in peaks):
            continue
        start = max(0, int(peak) - before)
        end = min(dur, int(peak) + after)
        if end - start < 10:
            continue
        peaks.append(int(peak))
        picks.append((start, end, float(score[peak])))
    return picks


def heatmap_per_second(heatmap: list | None, duration: int) -> np.ndarray | None:
    """YouTube 'Most replayed' graph -> one value per second."""
    if not heatmap or duration <= 0:
        return None
    arr = np.zeros(duration)
    for h in heatmap:
        a, b = int(h.get("start_time", 0)), int(h.get("end_time", 0))
        arr[max(0, a):min(duration, max(b, a + 1))] = float(h.get("value", 0))
    return arr
