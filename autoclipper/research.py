"""Watches what OTHER clippers post about your streamers (YouTube Shorts search, free via yt-dlp).

For each streamer it looks at recent clip uploads and their view counts, then works out:
  * how long the top-performing clips are  -> nudges your clip length
  * which words show up in the best titles -> those words count as "hooky" in your quotes
  * the top titles themselves             -> shown on the Insights page as inspiration
                                             (never copied: copying titles looks like a duplicate)
"""
import re
import statistics
from collections import Counter
from datetime import datetime

STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "it", "this", "that", "at",
        "his", "her", "he", "she", "i", "you", "my", "me", "be", "was", "are", "shorts", "short", "clip", "clips",
        "stream", "streamer", "twitch", "kick", "fyp", "viral", "live", "funny", "moments", "best", "full"}


def scan(streamer: str, limit: int = 40) -> dict | None:
    import yt_dlp
    query = f"ytsearch{limit}:{streamer} clips"
    opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(query, download=False)
    vids = []
    for e in info.get("entries") or []:
        if not e:
            continue
        d, v, t = e.get("duration"), e.get("view_count"), e.get("title") or ""
        if d and v and d <= 75 and streamer.lower().split()[0][:5] in (t + " " + str(e.get("channel"))).lower():
            vids.append({"title": t, "duration": float(d), "views": int(v), "url": e.get("url"),
                         "channel": e.get("channel") or e.get("uploader")})
    if len(vids) < 5:
        return None
    vids.sort(key=lambda x: x["views"], reverse=True)
    top = vids[: max(3, len(vids) // 4)]
    words = Counter()
    for v in top:
        for w in re.findall(r"[a-z']+", v["title"].lower()):
            if len(w) > 2 and w not in STOP and w not in streamer.lower():
                words[w] += 1
    return {
        "scanned": datetime.now().isoformat(timespec="minutes"),
        "videos": len(vids),
        "top_median_seconds": round(statistics.median([v["duration"] for v in top]), 1),
        "all_median_seconds": round(statistics.median([v["duration"] for v in vids]), 1),
        "top_median_views": int(statistics.median([v["views"] for v in top])),
        "hot_words": [w for w, c in words.most_common(12) if c >= 2],
        "top_titles": [{"title": v["title"], "views": v["views"], "seconds": v["duration"]} for v in top[:8]],
    }


def hot_words_for(streamer: str, research: dict) -> set:
    r = (research or {}).get(streamer.lower()) or {}
    return set(r.get("hot_words") or [])
