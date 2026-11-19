from __future__ import annotations

from .schema import TRACKED_FIELDS


def diff_records(old: dict | None, new: dict) -> list[tuple[str, object, object]]:
    """Field-level changes between two stored records. A new record diffs against all-None."""
    old = old or {}
    return [(f, old.get(f), new.get(f)) for f in TRACKED_FIELDS if old.get(f) != new.get(f)]


def render_pr_body(record: dict, changes: list[tuple[str, object, object]]) -> str:
    lines = [
        f"## {record['name']} ({record['foundation']})",
        "",
        f"Source: {record['source_url']}",
        "",
        "| field | before | after |",
        "|---|---|---|",
    ]
    lines += [f"| {f} | {old} | {new} |" for f, old, new in changes]
    evidence = record.get("evidence") or {}
    quoted = [(f, evidence[f]) for f, _, _ in changes if f in evidence]
    if quoted:
        lines += ["", "### Exact source lines", ""]
        lines += [f"- **{f}**: > {line}" for f, line in quoted]
    if record.get("internal_deadline_estimate"):
        lines += [
            "",
            f"Estimated internal (university) cutoff: **{record['internal_deadline_estimate']}** "
            "(from historical lead time; verify on your university portal).",
        ]
    if record.get("needs_verification"):
        lines += ["", "### Needs human verification", ""]
        lines += [f"- [ ] {item}" for item in record["needs_verification"]]
    return "\n".join(lines) + "\n"
