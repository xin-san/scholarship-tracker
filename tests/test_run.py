"""End-to-end: fictional foundation pages written to tmp, run twice, check records and change reports."""
import io
import json

import yaml
from pypdf import PdfWriter

from tracker.run import main

PAGE_V1 = """<html><body><h1>Example Foundation Scholarship</h1>
<p>支給額: 月額10万円</p><p>対象: 35歳以下の留学生</p>
<p>応募締切: 2026年1月15日(大学推薦が必要)</p></body></html>"""
PAGE_V2 = PAGE_V1.replace("2026年1月15日", "2026年1月8日")


def _setup(tmp_path, page: str, nomination=True):
    page_path = tmp_path / "page.html"
    page_path.write_text(page, encoding="utf-8")
    sources = [{
        "id": "example",
        "name": "Example Scholarship",
        "foundation": "Example Foundation",
        "url": str(page_path),
        "nomination_required": nomination,
        "typical_internal_lead_days": 21,
    }]
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")
    return ["--sources", str(tmp_path / "sources.yaml"), "--data", str(tmp_path / "data"),
            "--out", str(tmp_path / "changes")]


def _record(tmp_path):
    return json.loads((tmp_path / "data" / "example.json").read_text(encoding="utf-8"))


def _changed(tmp_path):
    return json.loads((tmp_path / "changes" / "changed.json").read_text())


def test_first_run_creates_record_and_flags_nomination(tmp_path):
    args = _setup(tmp_path, PAGE_V1)
    assert main(args) == 0
    r = _record(tmp_path)
    assert r["public_deadline"] == "2026-01-15"
    assert r["stipend_jpy_month"] == 100_000
    assert r["age_limit"] == 35
    assert r["internal_deadline"] == "NEEDS_VERIFICATION"
    assert r["internal_deadline_estimate"] == "2025-12-25"  # 21 days before public deadline
    assert _changed(tmp_path) == ["example"]
    body = (tmp_path / "changes" / "example.md").read_text(encoding="utf-8")
    assert "応募締切: 2026年1月15日" in body  # exact source line quoted
    assert "- [ ] internal_deadline" in body


def test_unchanged_page_produces_no_change(tmp_path):
    args = _setup(tmp_path, PAGE_V1)
    main(args)
    main(args)
    assert _changed(tmp_path) == []


def test_moved_deadline_is_reported_and_resets_human_internal_date(tmp_path):
    args = _setup(tmp_path, PAGE_V1)
    main(args)
    # A student fills in the real internal date from the portal.
    path = tmp_path / "data" / "example.json"
    r = _record(tmp_path)
    r["internal_deadline"] = "2025-12-20"
    path.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")

    _setup(tmp_path, PAGE_V2)
    main(args)
    r = _record(tmp_path)
    assert r["public_deadline"] == "2026-01-08"
    # Public date moved, so the old internal date can't be trusted any more.
    assert r["internal_deadline"] == "NEEDS_VERIFICATION"
    body = (tmp_path / "changes" / "example.md").read_text(encoding="utf-8")
    assert "| public_deadline | 2026-01-15 | 2026-01-08 |" in body


def test_human_internal_date_kept_when_public_date_unchanged(tmp_path):
    args = _setup(tmp_path, PAGE_V1)
    main(args)
    path = tmp_path / "data" / "example.json"
    r = _record(tmp_path)
    r["internal_deadline"] = "2025-12-20"
    path.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    # Page edited elsewhere (new hash), deadline unchanged.
    _setup(tmp_path, PAGE_V1.replace("留学生", "外国人留学生"))
    main(args)
    assert _record(tmp_path)["internal_deadline"] == "2025-12-20"


def test_image_only_pdf_is_flagged_not_guessed(tmp_path):
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(buf.getvalue())
    args = _setup(tmp_path, PAGE_V1, nomination=False)
    src = yaml.safe_load((tmp_path / "sources.yaml").read_text())
    src[0]["url"] = str(pdf)
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(src), encoding="utf-8")
    main(args)
    r = _record(tmp_path)
    assert r["public_deadline"] is None
    assert any("image-only PDF" in item for item in r["needs_verification"])


def test_dead_source_does_not_stop_others(tmp_path):
    args = _setup(tmp_path, PAGE_V1)
    src = yaml.safe_load((tmp_path / "sources.yaml").read_text())
    src.append({**src[0], "id": "dead", "url": str(tmp_path / "missing.html")})
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(src), encoding="utf-8")
    assert main(args) == 0
    assert _changed(tmp_path) == ["example"]
    errors = json.loads((tmp_path / "changes" / "errors.json").read_text())
    assert "dead" in errors
