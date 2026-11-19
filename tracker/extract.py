from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from pypdf import PdfReader

DEADLINE_KEYWORDS = ("締切", "締め切り", "応募期限", "提出期限", "必着", "deadline")
SUFFIX_KEYWORDS = ("必着",)  # always written after the date: "2026年1月15日必着"
WINDOW = 80  # characters after a keyword to look for a date
MIN_CHARS_PER_PAGE = 30  # below this a PDF page is treated as a scanned image

_DATE_PATTERNS = (
    (re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日"), "ad"),
    (re.compile(r"令和\s*(\d{1,2}|元)年\s*(\d{1,2})月\s*(\d{1,2})日"), "reiwa"),
    (re.compile(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})"), "ad"),
)


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
    html = raw.decode("utf-8", errors="replace")
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    return Document(normalize(text), sha, False)


def normalize(text: str) -> str:
    # NFKC turns full-width digits and punctuation (２０２６／１／１５) into ASCII.
    return unicodedata.normalize("NFKC", text)


def iter_dates(s: str) -> list[tuple[int, date]]:
    """All valid dates in s with their positions, in reading order."""
    out = []
    for pat, era in _DATE_PATTERNS:
        for m in pat.finditer(s):
            y, mo, d = m.groups()
            year = (2018 + (1 if y == "元" else int(y))) if era == "reiwa" else int(y)
            try:
                out.append((m.start(), date(year, int(mo), int(d))))
            except ValueError:
                continue
    return sorted(out)


def parse_date(s: str) -> date | None:
    dates = iter_dates(s)
    return dates[0][1] if dates else None


def _line_of(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start : end if end != -1 else len(text)].strip()


def find_deadline(text: str) -> tuple[date | None, str | None, bool]:
    """Return (deadline, evidence line, ambiguous). Ambiguous if keywords point at different dates."""
    found: dict[date, str] = {}
    for kw in DEADLINE_KEYWORDS:
        for m in re.finditer(re.escape(kw), text, flags=re.IGNORECASE):
            # Prefer the first date after the keyword ("締切: 2026年1月15日");
            # otherwise the nearest one just before it ("2026年1月15日(必着)").
            after = [] if kw in SUFFIX_KEYWORDS else iter_dates(text[m.end() : m.end() + WINDOW])
            before = iter_dates(text[max(0, m.start() - 30) : m.start()])
            d = after[0][1] if after else (before[-1][1] if before else None)
            if d:
                found.setdefault(d, _line_of(text, m.start()))
    if not found:
        return None, None, False
    first = min(found)
    return first, found[first], len(found) > 1


def find_stipend(text: str) -> tuple[int | None, str | None]:
    m = re.search(r"月額\s*(\d+(?:\.\d+)?)\s*万円", text)
    if m:
        return int(float(m.group(1)) * 10_000), _line_of(text, m.start())
    m = re.search(r"月額\s*([\d,]+)\s*円", text)
    if m:
        return int(m.group(1).replace(",", "")), _line_of(text, m.start())
    return None, None


def find_age_limit(text: str) -> tuple[int | None, str | None]:
    """Oldest eligible age. 35歳以下 -> 35, 35歳未満 -> 34."""
    m = re.search(r"(\d{2})\s*歳\s*(以下|未満)", text)
    if not m:
        return None, None
    n = int(m.group(1))
    return (n if m.group(2) == "以下" else n - 1), _line_of(text, m.start())
