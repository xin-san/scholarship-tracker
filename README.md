# scholarship-tracker

International students in Japan hunt scholarships across dozens of private foundation sites. Each one posts its deadline and eligibility in a Japanese page or PDF that changes every year. Many also need a **university-internal nomination** whose cutoff is weeks earlier and lives on a login-only portal. Students miss money because one date moved.

This repo watches those pages and opens **one pull request per changed scholarship**, with the exact source line quoted, so a human can check it in seconds.

## What v1 does

- One JSON record per scholarship in `data/<id>.json`: `public_deadline`, `internal_deadline`, `stipend_jpy_month`, `age_limit`, `nomination_required`, `source_url`, `source_hash`.
- Reads HTML and PDF. Normalizes full-width digits. Parses `2026年1月15日`, `令和8年1月15日`, `2026/1/15`.
- Field-level diffs, not text diffs. Each change report quotes the source line it came from.
- **Never shows only the public date when a nomination is required.** `internal_deadline` defaults to `NEEDS_VERIFICATION`, and an estimate from `typical_internal_lead_days` is shown as a warning window until a human fills in the real portal date. A filled-in date is kept until the public date moves.
- Scanned (image-only) PDFs are flagged for a human instead of guessed.
- Conflicting dates near deadline keywords are flagged, not silently picked.
- A dead site is logged in `changes/errors.json` and does not stop the others.
- Weekly GitHub Action (Mondays 09:00 JST): one PR per change on `update/<id>`, labelled `needs-human-verification` when a check is open.

## First real scan (2026-11-19)

8 official foundation and agency pages (see `sources.yaml`), 8 read, 0 errors. Baseline records are in `data/`.

| scholarship | public deadline | monthly | flags |
|---|---|---|---|
| 岩谷国際留学生奨学助成 | 2026-12-20 (period 12/1~12/20) | 150,000 | none, the only round open now |
| ロータリー米山記念奨学金 | 2026-10-15 | 100,000 | past; nomination, internal date needed; several dates on page |
| 市原国際奨学財団 | 2026-10-15 | 50,000 | past; nomination, internal date needed |
| 大塚敏美育英奨学財団 | 2026-04-13 | (yearly) | past; 4 different cutoffs (web/mail × new/continuing) |
| 似鳥国際奨学財団 | 2026-04-20 | 45,000 | past: page still shows last year's period |
| 佐藤陽国際奨学財団 | none on page | 180,000 | nomination, cutoff set by each university |
| JASSO 学習奨励費 | none on page | 48,000 | nomination, cutoff set by each university |
| 平和中島財団 | none on page | none on page | nomination; 要項 is mailed to universities |

Bugs the real pages exposed and that are now fixed with tests: `2026 年 10 月 15 日` spacing in PDFs, periods whose end date has no year (`3月5日~4月20日`), a `必着` after a period, an exclusion rule read as the stipend (`月額10万円未満…は除く`), HTML entities, and an AES-encrypted PDF.

## Not yet

- OCR for scanned PDFs, and a crop of the date region attached to the PR.
- Per-university checklist issues for internal nomination dates.
- Computing `typical_internal_lead_days` from past years automatically.

## Run

```bash
uv sync
uv run pytest
uv run python -m tracker.run --sources sources.yaml --data data --out changes
```

Add scholarships to `sources.yaml` (format is in the file). For the Action to open PRs, enable *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests*.

## License

MIT
