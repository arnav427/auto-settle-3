import re
from dataclasses import dataclass

from .config import Guardrails
from .costs import settlement_range

INJECTION = re.compile(
    r"ignore (all |any |the |your )?(previous |prior )?(instructions|rules|limits)|system prompt|"
    r"you are now|jailbreak|developer mode|override (the )?(limit|rule|guardrail)|disregard",
    re.I,
)
WANTS_HUMAN = re.compile(r"\b(human|agent|adjuster|adjustor|manager|supervisor|real person)\b", re.I)
ACCEPT = re.compile(r"\b(accept|accepted|agree|agreed|deal|ok|okay|fine|yes|done)\b", re.I)
AMOUNT = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lac)?", re.I)
MULTIPLIER = {"k": 1_000, "thousand": 1_000, "lakh": 100_000, "lac": 100_000}


def parse_amount(text: str) -> float | None:
    """First figure of at least Rs 100 in the message, or None."""
    for m in AMOUNT.finditer(text):
        value = float(m.group(1).replace(",", ""))
        value *= MULTIPLIER.get((m.group(2) or "").lower(), 1)
        if value >= 100:
            return value
    return None


def inr(x: float) -> str:
    return f"₹{x:,.0f}"


@dataclass
class Reply:
    text: str
    status: str  # open | accepted | escalated
    offer: float | None = None
    final_offer: bool = False


class Settlement:
    """Deterministic negotiation. Every amount comes from the ladder, never from free text."""

    def __init__(self, estimate: float, g: Guardrails = Guardrails()):
        self.estimate = estimate
        self.floor, self.ceiling = settlement_range(estimate, g)
        span = self.ceiling - self.floor
        self.ladder = [min(self.ceiling, max(self.floor, round((self.floor + span * s) / 50) * 50)) for s in g.schedule]
        self.ladder[-1] = self.ceiling
        self.step = 0
        self.status = "open"
        self.final_amount: float | None = None
        self.reason = ""

    @property
    def offer(self) -> float:
        return self.ladder[self.step]

    @property
    def at_final(self) -> bool:
        return self.step == len(self.ladder) - 1

    def opening(self) -> Reply:
        return Reply(
            f"Based on the damage assessment, we can settle your claim right now with a cash payment of "
            f"{inr(self.offer)}. You can accept, or tell me the amount you expect.",
            "open",
            self.offer,
        )

    def respond(self, text: str) -> Reply:
        if self.status != "open":
            return Reply("This claim is already closed.", self.status, self.final_amount)
        if INJECTION.search(text):
            return self._escalate("Customer message tried to change the settlement rules.")
        if WANTS_HUMAN.search(text):
            return self._escalate("Customer asked for a human adjuster.")

        amount = parse_amount(text)
        if amount is None:
            if ACCEPT.search(text):
                return self._accept(self.offer)
            return self._concede()
        if amount <= self.offer:
            return self._accept(self.offer)
        if self.at_final:
            return self._escalate("Customer did not accept the final offer.")
        if amount <= self.ladder[self.step + 1]:
            return self._accept(amount)
        return self._concede(asked=amount)

    def _concede(self, asked: float | None = None) -> Reply:
        if self.at_final:
            return self._escalate("Customer did not accept the final offer.")
        self.step += 1
        prefix = f"I can't go as high as {inr(asked)}. " if asked and asked > self.ceiling else ""
        if self.at_final:
            return Reply(
                f"{prefix}My best and final offer is {inr(self.offer)}. This is the maximum I'm authorised to pay.",
                "open",
                self.offer,
                final_offer=True,
            )
        return Reply(f"{prefix}I can improve the offer to {inr(self.offer)}.", "open", self.offer)

    def _accept(self, amount: float) -> Reply:
        if not (self.floor <= amount <= self.ceiling):
            return self._escalate("Computed settlement fell outside the approved range.")
        self.status, self.final_amount = "accepted", amount
        return Reply(f"Agreed. Your cash settlement of {inr(amount)} is approved.", "accepted", amount)

    def _escalate(self, reason: str) -> Reply:
        self.status, self.reason = "escalated", reason
        return Reply(
            "I'm passing your claim to a human claims adjuster who will contact you shortly.",
            "escalated",
        )
