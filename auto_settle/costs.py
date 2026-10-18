import csv
from functools import lru_cache

from .config import DATA_DIR, SEVERITIES, Guardrails
from .models import CostResult, Detection, LineItem


@lru_cache(maxsize=1)
def load_parts() -> dict:
    with open(DATA_DIR / "parts_costs.csv", newline="") as f:
        return {
            r["component"]: {
                "category": r["category"],
                "part_cost": float(r["part_cost"]),
                "paint_cost": float(r["paint_cost"]),
                "labour_factor": float(r["labour_factor"]),
            }
            for r in csv.DictReader(f)
        }


@lru_cache(maxsize=1)
def load_matrix() -> dict:
    with open(DATA_DIR / "repair_matrix.csv", newline="") as f:
        return {
            (r["damage_type"], r["severity"]): (
                float(r["part_frac"]),
                float(r["paint_frac"]),
                float(r["labour_hrs"]),
            )
            for r in csv.DictReader(f)
        }


def _shift(severity: str, step: int) -> str:
    i = SEVERITIES.index(severity) + step
    return SEVERITIES[max(0, min(len(SEVERITIES) - 1, i))]


def _line(d: Detection, g: Guardrails, shift: int = 0) -> LineItem:
    part = load_parts()[d.component]
    sev = _shift(d.severity, shift)
    part_frac, paint_frac, hrs = load_matrix()[(d.damage_type, sev)]
    return LineItem(
        component=d.component,
        damage_type=d.damage_type,
        severity=sev,
        parts=part_frac * part["part_cost"],
        paint=paint_frac * part["paint_cost"],
        labour=hrs * part["labour_factor"] * g.labour_rate,
    )


def _total(detections, g: Guardrails, shift: int) -> float:
    return sum(_line(d, g, shift).total for d in detections) * (1 + g.gst)


def price(detections: list, g: Guardrails = Guardrails()) -> CostResult:
    items = [_line(d, g) for d in detections]
    subtotal = sum(i.total for i in items)
    return CostResult(
        items=items,
        subtotal=subtotal,
        gst=subtotal * g.gst,
        estimate=subtotal * (1 + g.gst),
        low=_total(detections, g, -1),
        high=_total(detections, g, 1),
    )


def settlement_range(estimate: float, g: Guardrails = Guardrails()) -> tuple:
    """Whole-rupee (floor, ceiling); floor rounds up and ceiling rounds down to the nearest 100."""
    floor = -(-estimate * g.floor_pct // 100) * 100
    ceiling = (estimate * g.ceiling_pct // 100) * 100
    return float(floor), float(max(floor, ceiling))
