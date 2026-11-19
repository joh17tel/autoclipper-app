"""Turn a horizontal stream clip into a vertical 1080x1920 short.

Built around what top gaming clip accounts do:
  * stacked layout: streamer facecam on top, gameplay below (when a webcam is found)
  * karaoke captions: the spoken word lights up, hype words turn green
  * a title bar hook for the first seconds
  * a quick punch-in zoom on the hype moment
  * optional cold open: flash the payoff first, then the build-up
"""
import os
import shutil
import subprocess

_NVENC = None

HYPE = {"no", "way", "what", "bro", "omg", "insane", "crazy", "clutch", "clutched", "go",
        "yes", "wtf", "dead", "ace", "holy", "how", "why", "wait", "stop", "help", "run"}

CAM_H = 768                 # stacked layout: facecam strip height (top 40%)
GAME_H = 1920 - CAM_H       # gameplay below it (bottom 60%)


def _has_nvenc() -> bool:
    global _NVENC
    if _NVENC is None:
        try:
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2",
                 "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True)
            _NVENC = out.returncode == 0
        except FileNotFoundError:
            _NVENC = False
        print(f"   GPU encoding (NVENC): {'on' if _NVENC else 'off, using CPU'}")
    return _NVENC


def _ts(t: float) -> str:
    t = max(t, 0)
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(t: str) -> str:
    return t.replace("{", "").replace("}", "").replace("\\", "")


def _ass_header(styles: list[str]) -> list[str]:
    return [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def write_ass(words: list[dict], path: str, hook: str | None = None,
              split: bool = False, hook_seconds: float = 3.0,
              disclosure: str | None = None, disclosure_seconds: float = 3.0) -> None:
    """3 words on screen; the spoken word turns yellow (hype words green) and pops."""
    cap_margin = 330 if split else 520
    hook_margin = CAM_H - 60 if split else 260
    lines = _ass_header([
        f"Style: Cap,Arial Black,92,&H00FFFFFF,&H00000000,&H78000000,1,1,7,3,2,50,50,{cap_margin}",
        # black text on a yellow box = the classic clip-channel title bar
        f"Style: Hook,Arial Black,74,&H00000000,&H0000F6FF,&H0000F6FF,1,3,16,0,8,60,60,{hook_margin}",
        # campaign disclosure: white text on a dark tag, top-left, first seconds
        "Style: Disc,Arial,46,&H00FFFFFF,&HB4000000,&HB4000000,1,3,10,0,7,48,48,48",
    ])
    if disclosure:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(disclosure_seconds)},Disc,,0,0,0,,{_esc(disclosure)}")
    if hook:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(hook_seconds)},Hook,,0,0,0,,{_esc(hook.upper())}")
    for i in range(0, len(words), 3):
        chunk = words[i:i + 3]
        for j, w in enumerate(chunk):
            start = w["start"]
            end = chunk[j + 1]["start"] if j + 1 < len(chunk) else w["end"]
            if end <= start:
                continue
            parts = []
            for k, x in enumerate(chunk):
                word = _esc(x["word"].strip().upper())
                plain = "".join(c for c in word.lower() if c.isalpha() or c == "'")
                if k == j:
                    col = "&H0000FF00&" if plain in HYPE else "&H0000F6FF&"
                    parts.append("{\\c" + col + "\\fscx112\\fscy112}" + word + "{\\r}")
                else:
                    parts.append(word)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{' '.join(parts)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_thumb_ass(path: str, hook: str, streamer: str, split: bool = False) -> None:
    """Big cover text (where the eye lands) + streamer name tag."""
    hook = _esc(hook.upper())
    words, rows, cur = hook.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 14 and cur:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        rows.append(cur)
    text = "\\N".join(rows[:4])
    big_margin = CAM_H - 150 if split else 230
    lines = _ass_header([
        f"Style: Big,Arial Black,128,&H0000F6FF,&H00000000,&H96000000,1,1,11,6,8,50,50,{big_margin}",
        "Style: Name,Arial Black,64,&H00FFFFFF,&H00000000,&H96000000,1,3,4,0,2,50,50,220",
    ])
    lines += [f"Dialogue: 0,0:00:00.00,0:00:10.00,Big,,0,0,0,,{text}",
              f"Dialogue: 0,0:00:00.00,0:00:10.00,Name,,0,0,0,,{_esc(streamer.upper())}"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _zoom_expr(peak: float | None) -> str:
    """Punch-in zoom around the hype moment (eases in and out)."""
    if peak is None:
        return "1"
    return f"(1+0.14*exp(-pow(t-{peak:.2f},2)/0.35))"


def _scale_zoom(out_w: int, out_h: int, z: str) -> str:
    if z == "1":
        return ""
    return (f",scale=w='trunc({out_w}*{z}/2)*2':h='trunc({out_h}*{z}/2)*2':eval=frame,"
            f"crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})/2")


def _watermark(wm: dict | None) -> str:
    """Overlay the campaign logo (input #1) on the finished frame."""
    if not wm:
        return ""
    size = int(1080 * float(wm.get("size", 0.18))) // 2 * 2
    op = float(wm.get("opacity", 0.9))
    pos = {"top-left": "40:40", "top-right": "W-w-40:40",
           "bottom-left": "40:H-h-260", "bottom-right": "W-w-40:H-h-260"}.get(
        wm.get("position", "top-right"), "W-w-40:40")
    return (f"[base];[1:v]scale={size}:-2,format=rgba,colorchannelmixer=aa={op}[wm];"
            f"[base][wm]overlay={pos}:shortest=1")


def build_filter(w: int, h: int, cam: tuple | None, peak: float | None,
                 ass_path: str | None, thumb: bool = False, wm: dict | None = None,
                 follow_x: float | None = None) -> str:
    z = "1" if thumb else _zoom_expr(peak)
    pop = ",eq=contrast=1.12:saturation=1.3,unsharp=5:5:0.8" if thumb else ""
    if follow_x is not None and not cam and w / h > 0.75:
        # IRL / talk: fill the whole screen with the person (crop around their face)
        cw = int(h * 9 / 16) // 2 * 2
        x = int(min(max(follow_x * w - cw / 2, 0), w - cw)) // 2 * 2
        vf = (f"[0:v]crop={cw}:{h}:{x}:0,scale=1080:1920,unsharp=3:3:0.4"
              f"{_scale_zoom(1080, 1920, z)}{pop}")
    elif cam:
        x, y, cw, chh = cam
        target = 1080 / GAME_H
        gw = min(w, int(h * target)) // 2 * 2
        gh = min(h, int(gw / target)) // 2 * 2
        vf = (f"[0:v]split=2[c][g];"
              f"[c]crop={cw}:{chh}:{x}:{y},scale=1080:{CAM_H}:force_original_aspect_ratio=increase,"
              f"crop=1080:{CAM_H}{pop}[cs];"
              f"[g]crop={gw}:{gh}:{(w - gw) // 2}:{(h - gh) // 2},scale=1080:{GAME_H}"
              f"{_scale_zoom(1080, GAME_H, z)}{pop}[gs];"
              f"[cs][gs]vstack=inputs=2")
    else:
        fh = int(1080 * h / w) // 2 * 2
        vf = ("[0:v]split=2[bg][fg];"
              "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              f"boxblur=20:2{',eq=brightness=-0.15' if thumb else ''}[bgb];"
              f"[fg]scale=1080:{fh}{_scale_zoom(1080, fh, z)}{pop}[fgs];"
              "[bgb][fgs]overlay=(W-w)/2:(H-h)/2")
    if not thumb:
        vf += _watermark(wm)
    if ass_path and os.path.exists(ass_path):
        p = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
        vf += f",ass='{p}'"
    return vf + "[v]"


def make_vertical(src: str, dst: str, ass_path: str | None = None,
                  cam: tuple | None = None, peak: float | None = None,
                  wm: dict | None = None, follow_x: float | None = None) -> None:
    from .layout import probe_size
    w, h = probe_size(src)
    if wm and not os.path.exists(wm.get("file", "")):
        wm = None
    vf = build_filter(w, h, cam, peak, ass_path, wm=wm, follow_x=follow_x)
    logo_in = ["-loop", "1", "-i", wm["file"]] if wm else []
    # gaming looks best at the source's 60fps; high quality, platform-friendly bitrate
    enc = (["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20",
            "-b:v", "12M", "-maxrate", "16M", "-bufsize", "24M"] if _has_nvenc()
           else ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "16M", "-bufsize", "24M"])
    fps = str(_fps(src))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, *logo_in, "-filter_complex", vf,
                    "-map", "[v]", "-map", "0:a?", *enc, "-r", fps, "-g", str(int(fps) * 2), "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst], check=True)


def make_thumbnail(src: str, t: float, dst: str, ass_path: str, cam: tuple | None = None,
                   follow_x: float | None = None) -> None:
    from .layout import probe_size
    w, h = probe_size(src)
    vf = build_filter(w, h, cam, None, ass_path, thumb=True, follow_x=follow_x)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", src,
                    "-filter_complex", vf, "-map", "[v]", "-frames:v", "1", "-q:v", "2", dst],
                   check=True)


def cold_open(src: str, peak: float, dst: str, length: float = 1.4) -> float:
    """Flash the payoff first, then play the build-up. Returns seconds added."""
    a = max(0.0, peak - 0.3)
    b = a + length
    fc = (f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[tv];[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[ta];"
          f"[0:v]setpts=PTS-STARTPTS[mv];[0:a]asetpts=PTS-STARTPTS[ma];"
          f"[tv][ta][mv][ma]concat=n=2:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-c:a", "aac", dst], check=True)
    return b - a


def cut(src: str, start: float, end: float, dst: str, normalize: bool = False) -> None:
    """Frame-accurate cut. normalize=True evens out loudness (-14 LUFS, what TikTok/Shorts use)."""
    af = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] if normalize else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                    *af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst], check=True)


def _fps(path: str) -> int:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=avg_frame_rate", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.strip()
        n, d = out.split("/")
        f = float(n) / float(d)
        return 60 if f >= 50 else 30
    except Exception:
        return 30


def keep_segments(src: str, segs: list[tuple[float, float]], dst: str) -> None:
    """Join only the listed parts of a clip (used to cut out dead air)."""
    parts, labels = [], ""
    for i, (a, b) in enumerate(segs):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];"
                     f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}][a{i}]"
    fc = ";".join(parts) + f";{labels}concat=n={len(segs)}:v=1:a=1[v][a]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "16", "-c:a", "aac", "-b:a", "192k", dst], check=True)


def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None
