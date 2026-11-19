from __future__ import annotations

import hashlib
import html
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from pypdf import PdfReader

DEADLINE_KEYWORDS = (
    "締切", "締め切り", "応募期限", "提出期限", "必着", "deadline",
    "募集期間", "応募期間", "受付期間", "申請期間", "提出期間", "Web提出",  # periods: deadline = end
)
SUFFIX_KEYWORDS = ("必着",)  # always written after the date: "2026年1月15日必着"
WINDOW = 80  # characters after a keyword to look for a date
MIN_CHARS_PER_PAGE = 30  # below this a PDF page is treated as a scanned image

# PDFs often extract as "2026 年 10 月 15 日", so whitespace is allowed everywhere.
_DATE_PATTERNS = (
    (re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "ad"),
    (re.compile(r"令和\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "reiwa"),
    (re.compile(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})"), "ad"),
)
# "…1日(火)9時~12月20日": weekday, time, then a range separator, then the end date (year optional).
_RANGE_TAIL = re.compile(
    r"\s*(?:\([^)]{1,4}\))?\s*(?:\d{1,2}\s*[時:]\s*(?:\d{1,2}\s*分?)?)?\s*[~〜\-－–]\s*"
)
_MONTH_DAY = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")


@dataclass
class Document:
    text: str
    sha256: str
    image_only: bool  # scanned PDF: text extraction can't be trusted


def fetch(url: str, timeout: int = 30) -> bytes:
    if url.startswith(("http://", "https://")):
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "scholarship-tracker/0.1"})
        r.raise_for_status()
        return r.content
    return Path(url).read_bytes()  # local file, used for fixtures and offline runs


def to_document(raw: bytes) -> Document:
    sha = hashlib.sha256(raw).hexdigest()
    if raw[:5] == b"%PDF-":
        pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages]
        image_only = bool(pages) and all(len(p.strip()) < MIN_CHARS_PER_PAGE for p in pages)
        return Document(normalize("\n".join(pages)), sha, image_only)
    page = raw.decode("utf-8", errors="replace")
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", page))
    return Document(normalize(text), sha, False)


def normalize(text: str) -> str:
    # NFKC turns full-width digits and punctuation (２０２６／１／１５) into ASCII.
    return unicodedata.normalize("NFKC", text)


def _all_dates(s: str) -> list[tuple[int, int, date]]:
    """All valid full dates in s as (start, end, date), in reading order."""
    out = []
    for pat, era in _DATE_PATTERNS:
        for m in pat.finditer(s):
            y, mo, d = m.groups()
            year = (2018 + (1 if y == "元" else int(y))) if era == "reiwa" else int(y)
            try:
                out.append((m.start(), m.end(), date(year, int(mo), int(d))))
            except ValueError:
                continue
    return sorted(out)


def iter_dates(s: str) -> list[tuple[int, date]]:
    return [(start, d) for start, _, d in _all_dates(s)]


def parse_date(s: str) -> date | None:
    dates = iter_dates(s)
    return dates[0][1] if dates else None


def _first_date_or_range_end(text: str, lo: int, hi: int) -> tuple[date, int] | None:
    """(date, absolute end) of the first date in text[lo:hi]; if it starts a range ("A~B"),
    of the end B. B may omit the year and may lie past hi: only the start must be in the window."""
    found = _all_dates(text[lo:hi])
    if not found:
        return None
    _, rel_end, start_date = found[0]
    end = lo + rel_end
    tail = _RANGE_TAIL.match(text, end)
    if tail:
        m = _MONTH_DAY.match(text, tail.end())
        if m:
            y, mo, d = m.groups()
            year = int(y) if y else start_date.year
            try:
                end_date = date(year, int(mo), int(d))
            except ValueError:
                return start_date, end
            if end_date < start_date and not y:  # "12月20日~1月10日" crosses the year
                end_date = date(year + 1, int(mo), int(d))
            return end_date, m.end()
    return start_date, end


def _snippet(text: str, start: int, end: int, cap: int = 160) -> str:
    """The source text from the line holding `start` to the line holding `end`, on one line.
    Labels and values often sit on separate lines ("応募締切" / "2026年10月15日")."""
    lo = text.rfind("\n", 0, start) + 1
    hi = text.find("\n", end)
    s = " ".join(text[lo : hi if hi != -1 else len(text)].split())
    return s if len(s) <= cap else s[: cap - 1] + "…"


def _line_of(text: str, pos: int) -> str:
    return _snippet(text, pos, pos)


def find_deadline(text: str) -> tuple[date | None, str | None, bool]:
    """Return (deadline, evidence line, ambiguous). Ambiguous if keywords point at different dates."""
    found: dict[date, str] = {}
    for kw in DEADLINE_KEYWORDS:
        for m in re.finditer(re.escape(kw), text, flags=re.IGNORECASE):
            # Prefer the first date after the keyword ("締切: 2026年1月15日");
            # otherwise the nearest one just before it ("2026年1月15日(必着)").
            after = None if kw in SUFFIX_KEYWORDS else _first_date_or_range_end(text, m.end(), m.end() + WINDOW)
            if after:
                d, end = after
                found.setdefault(d, _snippet(text, m.start(), end))
                continue
            lo = max(0, m.start() - 40)
            before = iter_dates(text[lo : m.start()])
            if before:
                pos, _ = before[-1]
                # "2026年4月1日(水)~4月23日(木)15時(事務局必着)": the deadline is the range end.
                d, _ = _first_date_or_range_end(text, lo + pos, m.start())
                found.setdefault(d, _snippet(text, lo + pos, m.end()))
    if not found:
        return None, None, False
    first = min(found)
    return first, found[first], len(found) > 1


_STIPEND = re.compile(r"月額\s*(?:(\d+(?:\.\d+)?)\s*万\s*円|([\d,]+)\s*円)")
_THRESHOLD = re.compile(r"\s*(?:未満|以上|以下|を超え|超)")  # "月額10万円未満の奨学金は除く" is a rule, not a payment


def find_stipend(text: str) -> tuple[int | None, str | None]:
    for m in _STIPEND.finditer(text):
        if _THRESHOLD.match(text, m.end()):
            continue
        man, yen = m.groups()
        amount = int(float(man) * 10_000) if man else int(yen.replace(",", ""))
        return amount, _snippet(text, m.start(), m.end())
    return None, None


def find_age_limit(text: str) -> tuple[int | None, str | None]:
    """Oldest eligible age. 35歳以下 -> 35, 35歳未満 -> 34."""
    m = re.search(r"(\d{2})\s*歳\s*(以下|未満)", text)
    if not m:
        return None, None
    n = int(m.group(1))
    return (n if m.group(2) == "以下" else n - 1), _snippet(text, m.start(), m.end())
