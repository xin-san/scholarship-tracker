"""Weekly run: fetch every source, extract fields, write data/<id>.json, and one change report per changed scholarship.

    uv run python -m tracker.run --sources sources.yaml --data data --out changes
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .diff import diff_records, render_pr_body
from .extract import fetch, find_age_limit, find_deadline, find_stipend, to_document
from .schema import NEEDS_VERIFICATION, Scholarship, apply_nomination_rule

REQUIRED_KEYS = ("id", "name", "foundation", "url", "nomination_required")


def build_record(src: dict, raw: bytes, old: dict | None) -> Scholarship:
    doc = to_document(raw)
    s = Scholarship(
        id=src["id"],
        name=src["name"],
        foundation=src["foundation"],
        source_url=src["url"],
        nomination_required=bool(src["nomination_required"]),
        source_hash=doc.sha256,
    )
    if doc.image_only:
        s.needs_verification.append(
            "image-only PDF: text could not be extracted, check deadline, stipend and age limit on the scan"
        )
    else:
        deadline, line, ambiguous = find_deadline(doc.text)
        if deadline:
            s.public_deadline = deadline.isoformat()
            s.evidence["public_deadline"] = line
        else:
            s.needs_verification.append("public_deadline: no date found near a deadline keyword")
        if ambiguous:
            s.needs_verification.append(
                "public_deadline: several different dates near deadline keywords, earliest one used"
            )
        s.stipend_jpy_month, line = find_stipend(doc.text)
        if line:
            s.evidence["stipend_jpy_month"] = line
        s.age_limit, line = find_age_limit(doc.text)
        if line:
            s.evidence["age_limit"] = line

    # Keep an internal deadline a human already filled in, as long as the public date hasn't moved.
    if (
        old
        and old.get("internal_deadline") not in (None, NEEDS_VERIFICATION)
        and old.get("public_deadline") == s.public_deadline
    ):
        s.internal_deadline = old["internal_deadline"]
    apply_nomination_rule(s, src.get("typical_internal_lead_days"))
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.yaml")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="changes")
    args = ap.parse_args(argv)

    sources = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8")) or []
    data_dir, out_dir = Path(args.data), Path(args.out)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    changed, errors = [], {}
    for src in sources:
        missing = [k for k in REQUIRED_KEYS if k not in src]
        if missing:
            errors[src.get("id", "?")] = f"missing keys in sources: {missing}"
            continue
        path = data_dir / f"{src['id']}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        try:
            raw = fetch(src["url"])
        except Exception as e:  # one dead site must not stop the others
            errors[src["id"]] = f"fetch failed: {e}"
            continue
        if old and old.get("source_hash") and old["source_hash"] == to_document(raw).sha256:
            continue  # page unchanged since last run
        record = build_record(src, raw, old).to_dict()
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changes = diff_records(old, record)
        if changes:
            (out_dir / f"{src['id']}.md").write_text(render_pr_body(record, changes), encoding="utf-8")
            changed.append(src["id"])

    (out_dir / "changed.json").write_text(json.dumps(changed) + "\n", encoding="utf-8")
    (out_dir / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for sid, msg in errors.items():
        print(f"ERROR {sid}: {msg}", file=sys.stderr)
    print(f"{len(sources)} sources, {len(changed)} changed, {len(errors)} errors")
    return 2 if sources and len(errors) == len(sources) else 0


if __name__ == "__main__":
    sys.exit(main())
