from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

NEEDS_VERIFICATION = "NEEDS_VERIFICATION"

# Fields compared between runs. Anything else (hash, timestamps) is bookkeeping.
TRACKED_FIELDS = (
    "public_deadline",
    "internal_deadline",
    "stipend_jpy_month",
    "age_limit",
    "nomination_required",
)


@dataclass
class Scholarship:
    id: str
    name: str
    foundation: str
    source_url: str
    nomination_required: bool
    public_deadline: str | None = None  # ISO date
    internal_deadline: str | None = None  # ISO date or NEEDS_VERIFICATION
    internal_deadline_estimate: str | None = None  # ISO date, from historical lead time
    stipend_jpy_month: int | None = None
    age_limit: int | None = None
    source_hash: str | None = None
    needs_verification: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)  # field -> exact source line

    def to_dict(self) -> dict:
        return asdict(self)


def apply_nomination_rule(s: Scholarship, typical_lead_days: int | None) -> None:
    """Never show only the public date when a university nomination is required."""
    if not s.nomination_required:
        return
    if s.internal_deadline is None:
        s.internal_deadline = NEEDS_VERIFICATION
        s.needs_verification.append(
            "internal_deadline: nomination required, real cutoff is on the university portal"
        )
    if s.public_deadline and typical_lead_days:
        est = date.fromisoformat(s.public_deadline) - timedelta(days=typical_lead_days)
        s.internal_deadline_estimate = est.isoformat()
