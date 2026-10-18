from dataclasses import dataclass, field


@dataclass
class Detection:
    component: str
    damage_type: str
    severity: str
    confidence: float
    frames: int = 1


@dataclass
class Flag:
    code: str
    message: str
    blocking: bool = False


@dataclass
class LineItem:
    component: str
    damage_type: str
    severity: str
    parts: float
    paint: float
    labour: float

    @property
    def total(self) -> float:
        return self.parts + self.paint + self.labour


@dataclass
class CostResult:
    items: list = field(default_factory=list)
    subtotal: float = 0.0
    gst: float = 0.0
    estimate: float = 0.0
    low: float = 0.0  # estimate if every severity were one level lower
    high: float = 0.0  # estimate if every severity were one level higher
