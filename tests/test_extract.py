from datetime import date

from tracker.extract import find_age_limit, find_deadline, find_stipend, normalize, parse_date


def test_parse_date_formats():
    assert parse_date("2026年1月15日") == date(2026, 1, 15)
    assert parse_date("令和8年1月15日") == date(2026, 1, 15)
    assert parse_date("令和元年5月1日") == date(2019, 5, 1)
    assert parse_date("2026/01/15") == date(2026, 1, 15)
    assert parse_date(normalize("２０２６年１月１５日")) == date(2026, 1, 15)  # full-width
    assert parse_date("2026年2月30日") is None  # invalid date is rejected, not guessed


def test_deadline_prefers_date_after_keyword():
    text = "募集開始 2025年10月1日\n応募締切: 2025年11月30日"
    d, line, ambiguous = find_deadline(text)
    assert d == date(2025, 11, 30)
    assert "応募締切" in line
    assert not ambiguous


def test_suffix_keyword_does_not_grab_next_line():
    text = "書類は2026年1月15日必着\n奨学金支給開始 2026年4月1日"
    d, _, ambiguous = find_deadline(text)
    assert d == date(2026, 1, 15)
    assert not ambiguous


def test_conflicting_deadlines_are_flagged():
    text = "応募締切 2026年1月15日\n(注) 提出期限 2026年1月31日"
    d, _, ambiguous = find_deadline(text)
    assert d == date(2026, 1, 15)
    assert ambiguous


def test_no_deadline():
    assert find_deadline("奨学金の概要") == (None, None, False)


def test_stipend():
    assert find_stipend("支給額 月額10万円")[0] == 100_000
    assert find_stipend("月額 80,000円")[0] == 80_000
    assert find_stipend("月額4.8万円")[0] == 48_000
    assert find_stipend("一時金のみ")[0] is None


def test_age_limit():
    assert find_age_limit("35歳以下の者")[0] == 35
    assert find_age_limit("35歳未満")[0] == 34
    assert find_age_limit("年齢制限なし")[0] is None
