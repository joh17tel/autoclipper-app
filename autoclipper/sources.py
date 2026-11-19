"""Find new VODs and download only what's needed (audio first, then the clip parts)."""
import os
import yt_dlp


def latest_vods(channel_url: str, limit: int) -> list[dict]:
    opts = {"quiet": True, "extract_flat": True, "playlistend": limit, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    entries = info.get("entries") or [info]
    vods = []
    for e in entries[:limit]:
        if not e:
            continue
        url = e.get("url") or e.get("webpage_url")
        if url and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        vods.append({"id": str(e.get("id")), "url": url, "title": e.get("title") or ""})
    return vods


def vod_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False)


def download_audio(url: str, out_dir: str, vod_id: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    tmpl = os.path.join(out_dir, f"{vod_id}_audio.%(ext)s")
    opts = {"quiet": True, "format": "bestaudio/worst", "outtmpl": tmpl,
            "concurrent_fragment_downloads": 8}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def download_section(url: str, start: int, end: int, out_path: str) -> str:
    """Download just one part of the VOD (up to 1080p)."""
    from yt_dlp.utils import download_range_func
    base, _ = os.path.splitext(out_path)
    opts = {
        "quiet": True,
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "outtmpl": base + ".%(ext)s",
        "merge_output_format": "mp4",
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    mp4 = base + ".mp4"
    return mp4 if os.path.exists(mp4) else path


def twitch_login(url: str) -> str | None:
    import re
    m = re.match(r"https?://(?:www\.|m\.)?twitch\.tv/([A-Za-z0-9_]+)", url or "")
    return m.group(1) if m and m.group(1).lower() not in ("videos", "directory") else None


def twitch_top_clips(channel_url: str, rng: str = "7d", limit: int = 40) -> list[dict]:
    """Most-viewed clips that viewers made of this streamer (best first)."""
    login = twitch_login(channel_url)
    if not login:
        return []
    url = f"https://www.twitch.tv/{login}/clips?filter=clips&range={rng}"
    opts = {"quiet": True, "extract_flat": True, "playlistend": limit, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out = []
    for e in (info.get("entries") or [])[:limit]:
        if e and e.get("url"):
            out.append({"id": str(e.get("id")), "url": e["url"], "title": e.get("title") or "",
                        "view_count": e.get("view_count") or 0, "duration": e.get("duration") or 0,
                        "timestamp": e.get("timestamp")})
    out.sort(key=lambda c: c["view_count"], reverse=True)
    return out


def download_clip(url: str, out_path: str) -> str:
    base, _ = os.path.splitext(out_path)
    opts = {"quiet": True, "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
            "outtmpl": base + ".%(ext)s", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    mp4 = base + ".mp4"
    return mp4 if os.path.exists(mp4) else path


def kick_slug(url: str) -> str | None:
    import re
    m = re.match(r"https?://(?:www\.)?kick\.com/([\w-]+)", url or "")
    return m.group(1).lower() if m and m.group(1).lower() not in ("video", "categories", "search") else None


def kick_top_clips(channel_url: str, rng: str = "7d", limit: int = 40) -> list[dict]:
    """Most-viewed clips Kick viewers made of this streamer."""
    slug = kick_slug(channel_url)
    if not slug:
        return []
    r = {"24hr": "day", "1d": "day", "7d": "week", "30d": "month", "all": "all"}.get(rng, "week")
    url = f"https://kick.com/{slug}/clips?sort=view&range={r}"
    opts = {"quiet": True, "extract_flat": True, "playlistend": limit, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out = []
    for e in (info.get("entries") or [])[:limit]:
        if e and e.get("url"):
            out.append({"id": str(e.get("id")), "url": e["url"], "title": e.get("title") or "",
                        "view_count": e.get("view_count") or 0, "duration": e.get("duration") or 0})
    out.sort(key=lambda c: c["view_count"], reverse=True)
    return out


def has_viewer_clips(url: str) -> bool:
    return bool(twitch_login(url) or kick_slug(url))


def top_viewer_clips(url: str, rng: str = "7d", limit: int = 40) -> list[dict]:
    if twitch_login(url):
        return twitch_top_clips(url, rng, limit)
    if kick_slug(url):
        return kick_top_clips(url, rng, limit)
    return []
