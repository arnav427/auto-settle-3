from dataclasses import dataclass, field

from .config import STRUCTURAL, Guardrails
from .costs import price, settlement_range
from .models import CostResult, Flag


@dataclass
class Assessment:
    detections: list
    cost: CostResult
    flags: list
    reasons: list = field(default_factory=list)  # why a human is needed
    floor: float = 0.0
    ceiling: float = 0.0

    @property
    def escalate(self) -> bool:
        return bool(self.reasons)


def evaluate(detections: list, flags: list, g: Guardrails = Guardrails()) -> Assessment:
    """Price the damage and decide whether the claim is safe to settle automatically."""
    cost = price(detections, g)
    floor, ceiling = settlement_range(cost.estimate, g)
    reasons = [f.message for f in flags if f.blocking]

    if not detections:
        reasons.append("No damage could be identified.")
    for d in detections:
        if d.confidence < g.min_confidence:
            reasons.append(f"Low confidence ({d.confidence:.0%}) for {d.component} {d.damage_type}.")
        if d.component in STRUCTURAL and d.severity == "severe":
            reasons.append(f"Severe damage to structural part ({d.component}).")
    if len(detections) > g.max_components:
        reasons.append(f"{len(detections)} damaged areas exceed the {g.max_components}-area limit.")
    if cost.estimate > g.auto_limit:
        reasons.append(f"Estimate ₹{cost.estimate:,.0f} exceeds the auto-settle limit ₹{g.auto_limit:,.0f}.")

    return Assessment(detections, cost, flags, reasons, floor, ceiling)
