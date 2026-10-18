import io
import os
import tempfile
from dataclasses import dataclass, field

from PIL import Image

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv"}


@dataclass
class Media:
    name: str
    image: Image.Image
    jpeg: bytes  # downscaled copy sent to the vision model
    from_video: bool = False
    exif: dict = field(default_factory=dict)


def _prepare(name: str, img: Image.Image, from_video: bool = False) -> Media:
    exif = {}
    if not from_video:
        raw = img.getexif()
        sub = raw.get_ifd(0x8769) if raw else {}
        exif = {"software": raw.get(305) if raw else None, "taken": sub.get(36867) or (raw.get(306) if raw else None)}
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return Media(name, img, buf.getvalue(), from_video, exif)


def _video_frames(name: str, data: bytes, n: int) -> list:
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError("Video support needs opencv-python-headless") from e

    fd, path = tempfile.mkstemp(suffix=os.path.splitext(name)[1])
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        candidates = []
        for idx in sorted({int(total * (i + 0.5) / (n * 3)) for i in range(n * 3)}):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                sharp = cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
                candidates.append((sharp, idx, frame))
        cap.release()
    finally:
        os.remove(path)

    best = sorted(sorted(candidates, key=lambda c: -c[0])[:n], key=lambda c: c[1])
    return [
        _prepare(f"{name}#frame{idx}", Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), True)
        for _, idx, frame in best
    ]


def load_uploads(files: list, max_frames: int = 6) -> list:
    """files: list of (filename, bytes). Videos are reduced to their sharpest sampled frames."""
    media = []
    for name, data in files:
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXT:
            media.append(_prepare(name, Image.open(io.BytesIO(data))))
        elif ext in VIDEO_EXT:
            media.extend(_video_frames(name, data, max_frames))
        else:
            raise ValueError(f"Unsupported file type: {name}")
    return media
