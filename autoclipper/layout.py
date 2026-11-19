"""Find the streamer's webcam box so clips can use the stacked layout:
facecam on top, gameplay below (the default format of top gaming clip accounts).
"""
import subprocess
import json


def probe_size(path: str) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def probe_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def from_fractions(frac: list, w: int, h: int) -> tuple[int, int, int, int]:
    """config gives [x, y, width, height] as fractions of the frame (0–1)."""
    x, y, fw, fh = frac
    return _even(x * w), _even(y * h), _even(fw * w), _even(fh * h)


def detect_facecam(path: str, samples: int = 12) -> tuple[int, int, int, int] | None:
    """Look for a face that sits in the SAME small spot across the clip = a webcam.
    Returns (x, y, w, h) in pixels, or None (then the gameplay-only layout is used)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total <= 0 or W == 0:
        return None
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        return None
    if cascade.empty():
        print("   (face detector missing - set facecam manually in config.yaml)")
        cap.release()
        return None
    boxes = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                         minSize=(int(H * 0.06), int(H * 0.06)))
        for (x, y, w, h) in faces:
            if w < W * 0.30:  # webcam faces are smallish; skip huge in-game faces
                boxes.append((x, y, w, h))
    cap.release()
    if len(boxes) < samples * 0.4:
        return None
    arr = np.array(boxes, dtype=float)
    cx, cy = np.median(arr[:, 0] + arr[:, 2] / 2), np.median(arr[:, 1] + arr[:, 3] / 2)
    fw = np.median(arr[:, 2])
    # the face must stay put (a webcam doesn't move around the screen)
    centres = np.stack([arr[:, 0] + arr[:, 2] / 2, arr[:, 1] + arr[:, 3] / 2], axis=1)
    stable = np.linalg.norm(centres - [cx, cy], axis=1) < fw * 0.6
    if stable.sum() < samples * 0.4:
        return None
    # grow the face box into a webcam-shaped box (about 4:3)
    bw = fw * 3.0
    bh = bw * 0.75
    x0 = min(max(cx - bw / 2, 0), W - bw)
    y0 = min(max(cy - bh * 0.45, 0), H - bh)
    return _even(x0), _even(y0), _even(min(bw, W)), _even(min(bh, H))


def face_center_x(path: str, samples: int = 10) -> float | None:
    """Where the main person is, left-to-right (0..1). Used to crop IRL/talk clips on the person."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    if total <= 0 or W == 0:
        return None
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        return None
    if cascade.empty():
        return None
    xs, ws = [], []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])   # biggest face = main person
            xs.append((x + w / 2) / W)
            ws.append(w)
    cap.release()
    if len(xs) < max(2, samples // 4):
        return None
    return float(np.median(xs))
