import json
from datetime import datetime, timedelta

from PIL import Image

from .models import Flag

EDITORS = ("photoshop", "gimp", "canva", "snapseed", "lightroom", "pixlr", "facetune")
MAX_PHOTO_AGE = timedelta(days=30)


def ahash(img: Image.Image) -> int:
    """64-bit average hash; near-identical images differ in only a few bits."""
    px = list(img.convert("L").resize((8, 8)).getdata())
    avg = sum(px) / 64
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def _load(path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def register(media: list, claim_id: str, path) -> None:
    seen = _load(path)
    for m in media:
        seen[f"{ahash(m.image):016x}"] = claim_id
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(seen, f)


def check(media: list, seen_path=None, now: datetime | None = None) -> list:
    now = now or datetime.now()
    seen = _load(seen_path) if seen_path else {}
    flags = []

    for m in media:
        h = ahash(m.image)
        for old_hex, claim in seen.items():
            if bin(h ^ int(old_hex, 16)).count("1") <= 4:
                flags.append(Flag("duplicate_image", f"{m.name} matches an image from earlier claim {claim}.", True))
                break

        if m.from_video:
            continue
        software = str(m.exif.get("software") or "").lower()
        if any(e in software for e in EDITORS):
            flags.append(Flag("edited_image", f"{m.name} was saved by editing software ({software}).", True))
        if not m.exif.get("taken"):
            flags.append(Flag("no_metadata", f"{m.name} has no capture date (screenshot or stripped metadata)."))
            continue
        try:
            taken = datetime.strptime(str(m.exif["taken"]), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            flags.append(Flag("bad_metadata", f"{m.name} has an unreadable capture date."))
            continue
        if now - taken > MAX_PHOTO_AGE:
            flags.append(Flag("old_photo", f"{m.name} was taken {(now - taken).days} days ago.", True))
        elif taken > now + timedelta(hours=1):
            flags.append(Flag("future_photo", f"{m.name} has a capture date in the future.", True))
    return flags
