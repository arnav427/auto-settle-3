import hashlib
import json
import random

from . import llm
from .config import DAMAGE_TYPES, SEVERITIES
from .costs import load_parts
from .models import Detection

PROMPT = """You are a motor-insurance damage inspector. Look at the vehicle photo and list every visible damage.
Return JSON only: {{"damages": [{{"component": str, "damage_type": str, "severity": str, "confidence": number}}]}}
component must be one of: {components}
damage_type must be one of: {types}
severity must be one of: {severities}
confidence is 0 to 1. If no damage is visible or the photo is not a vehicle, return {{"damages": []}}."""


def _norm(s) -> str:
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def parse_response(text: str) -> tuple:
    """Return (detections, dropped) keeping only values from the known vocabulary."""
    try:
        raw = json.loads(text).get("damages", [])
    except (json.JSONDecodeError, AttributeError):
        return [], ["unparseable model output"]
    kept, dropped = [], []
    for r in raw if isinstance(raw, list) else []:
        try:
            d = Detection(
                _norm(r["component"]),
                _norm(r["damage_type"]),
                _norm(r["severity"]),
                max(0.0, min(1.0, float(r["confidence"]))),
            )
        except (KeyError, TypeError, ValueError):
            dropped.append(str(r))
            continue
        if d.component in load_parts() and d.damage_type in DAMAGE_TYPES and d.severity in SEVERITIES:
            kept.append(d)
        else:
            dropped.append(f"{d.component}/{d.damage_type}/{d.severity}")
    return kept, dropped


def merge(per_frame: list) -> list:
    """Combine per-frame detections: highest severity wins, confidence is averaged."""
    groups: dict = {}
    for dets in per_frame:
        for d in dets:
            groups.setdefault((d.component, d.damage_type), []).append(d)
    merged = []
    for (comp, dtype), ds in groups.items():
        sev = max((d.severity for d in ds), key=SEVERITIES.index)
        conf = sum(d.confidence for d in ds) / len(ds)
        merged.append(Detection(comp, dtype, sev, round(conf, 2), frames=len(ds)))
    return sorted(merged, key=lambda d: -d.confidence)


def detect_ollama(media: list, model: str, host: str = llm.DEFAULT_HOST) -> tuple:
    prompt = PROMPT.format(
        components=", ".join(load_parts()), types=", ".join(DAMAGE_TYPES), severities=", ".join(SEVERITIES)
    )
    per_frame, dropped = [], []
    for m in media:
        kept, drop = parse_response(llm.chat(model, prompt, [m.jpeg], host, as_json=True))
        per_frame.append(kept)
        dropped += drop
    return merge(per_frame), dropped


def detect_demo(media: list) -> tuple:
    """Offline stand-in so the pipeline can be shown without a vision model. Not real inference."""
    rng = random.Random(hashlib.sha256(media[0].jpeg).hexdigest())
    comps = rng.sample(list(load_parts()), k=rng.choice([1, 2]))
    dets = [
        Detection(c, rng.choice(DAMAGE_TYPES), rng.choice(SEVERITIES), round(rng.uniform(0.7, 0.95), 2))
        for c in comps
    ]
    return dets, []
