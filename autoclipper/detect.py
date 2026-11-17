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
                    min_score: float = 1.5, extra: np.ndarray | None = None, max_len: float = 30,
                    min_before: int = 8, min_after: int = 4) -> list[tuple[int, int, float, int]]:
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

    return pick_windows(score, n, before, after, min_gap, min_score, max_len, min_before, min_after)


def pick_windows(score: np.ndarray, n: int, max_before: int, max_after: int, min_gap: int,
                 min_score: float, max_len: float = 30, min_before: int = 8,
                 min_after: int = 4) -> list[tuple[int, int, float, int]]:
    """Build each clip around its peak, but let it GROW while the action stays above normal:
    keeps the whole build-up and the full reaction (up to max_len), and prefers windows with
    several exciting beats over a single loud spike. Returns (start, end, quality, peak)."""
    dur = len(score)
    order = np.argsort(score)[::-1]
    cands = []
    used_peaks: list[int] = []
    for peak in order[: max(60, n * 12)]:
        peak = int(peak)
        if score[peak] < min_score:
            break
        if any(abs(peak - p) < 6 for p in used_peaks):
            continue  # same moment
        used_peaks.append(peak)
        s0 = max(0, peak - min_before)
        e0 = min(dur, peak + min_after)
        # grow backwards through the build-up while it's clearly above normal
        # (short dips of up to 2s are allowed: a pause before the play is part of it)
        lo_lim, dip = max(0, peak - max_before), 0
        i = s0 - 1
        while i >= lo_lim:
            dip = 0 if score[i] > 0.35 else dip + 1
            if dip > 2:
                break
            if dip == 0:
                s0 = i
            i -= 1
        # grow forwards through the reaction the same way
        hi_lim, dip = min(dur, peak + max_after), 0
        i = e0
        while i < hi_lim:
            dip = 0 if score[i] > 0.35 else dip + 1
            if dip > 2:
                break
            if dip == 0:
                e0 = i + 1
            i += 1
        # respect the overall length cap (trim the build-up first, keep the reaction)
        while e0 - s0 > max_len and s0 < peak - min_before:
            s0 += 1
        while e0 - s0 > max_len and e0 > peak + min_after:
            e0 -= 1
        if e0 - s0 < 10:
            continue
        w = score[s0:e0]
        beats = int(np.sum(w > 1.5))                 # how many exciting seconds
        body = float(np.mean(np.sort(w)[-max(3, len(w) // 3):]))   # how strong the best third is
        quality = 0.55 * float(score[peak]) + 0.30 * body + 0.15 * min(beats, 8)
        cands.append((s0, e0, quality, peak))
    cands.sort(key=lambda c: c[2], reverse=True)
    picks: list[tuple[int, int, float, int]] = []
    for c in cands:
        if len(picks) >= n:
            break
        if any(not (c[1] + min_gap / 3 <= p[0] or c[0] >= p[1] + min_gap / 3) for p in picks):
            continue  # overlaps a better clip
        picks.append(c)
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


def silences(path: str, noise_db: int = -38, min_len: float = 1.2) -> list[tuple[float, float]]:
    """Quiet stretches (no talking, no game action) inside a clip."""
    import re
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))
