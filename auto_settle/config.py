from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DAMAGE_TYPES = ("scratch", "dent", "crack", "broken")
SEVERITIES = ("minor", "moderate", "severe")
STRUCTURAL = ("roof", "quarter_panel")


@dataclass(frozen=True)
class Guardrails:
    floor_pct: float = 0.60  # lowest cash offer, share of garage estimate
    ceiling_pct: float = 0.85  # highest cash offer, share of garage estimate
    auto_limit: float = 60_000  # above this estimate a human must decide
    min_confidence: float = 0.55
    max_components: int = 5
    gst: float = 0.18
    labour_rate: float = 600  # INR per hour
    # Offer ladder as a position inside [floor, ceiling]; last step is the final offer.
    schedule: tuple = (0.30, 0.55, 0.80, 1.0)
