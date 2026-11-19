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


def test_pdf_spacing_between_digits_and_kanji():
    # Real PDF extraction output, e.g. Rotary Yoneyama: "締切：2026 年 10 月 15 日"
    d, _, _ = find_deadline(normalize("締切：2026 年 10 月 15 日"))
    assert d == date(2026, 10, 15)


def test_period_deadline_is_range_end():
    # Iwatani style: full-width digits and a full date on both ends
    text = normalize("募集期間 ２０２６年１２月１日（火）～２０２６年１２月２０日（日）")
    assert find_deadline(text)[0] == date(2026, 12, 20)


def test_period_end_without_year_and_with_time():
    # Otsuka style: "Web提出：2026年3月5日（木）9時～4月20日（月）17時"
    text = normalize("Web提出：2026年3月5日（木）9時～4月20日（月）17時")
    assert find_deadline(text)[0] == date(2026, 4, 20)


def test_range_end_may_lie_past_the_search_window():
    # Otsuka: the keyword "応募締切" is ~70 chars before the date, the range end falls past the window
    text = normalize(
        "※新規申請者と継続申請者で応募締切日が異なりますので注意してください。\n"
        "新規申請者（当財団から奨学金の給付を受けたことのない者）\n"
        "Web提出：2026年3月5日（木）9時～4月20日（月）17時"
    )
    d, _, ambiguous = find_deadline(text)
    assert d == date(2026, 4, 20)
    assert not ambiguous


def test_suffix_keyword_after_a_range_takes_range_end():
    # Otsuka mail-in: the start date has a year, the end date doesn't
    text = normalize("郵送：2026年4月1日（水）～4月23日（木）15時（事務局必着）")
    assert find_deadline(text)[0] == date(2026, 4, 23)


def test_period_crossing_new_year():
    assert find_deadline("受付期間 2026年12月20日〜1月10日")[0] == date(2027, 1, 10)


def test_no_deadline():
    assert find_deadline("奨学金の概要") == (None, None, False)


def test_stipend():
    assert find_stipend("支給額 月額10万円")[0] == 100_000
    assert find_stipend("月額 80,000円")[0] == 80_000
    assert find_stipend("月額4.8万円")[0] == 48_000
    assert find_stipend("一時金のみ")[0] is None
    assert find_stipend("月額10 万円")[0] == 100_000  # PDF spacing


def test_stipend_skips_threshold_rules():
    # Iwatani: an exclusion rule appears before the real amount
    text = "(但し、大学からの月額10万円未満の奨学金等は除く)\n奨学金 月額15万円"
    assert find_stipend(text)[0] == 150_000


def test_age_limit():
    assert find_age_limit("35歳以下の者")[0] == 35
    assert find_age_limit("35歳未満")[0] == 34
    assert find_age_limit("年齢制限なし")[0] is None
