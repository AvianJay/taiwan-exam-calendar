import datetime as dt

import pytest

from src.dates import DateParseError
from src.models import Category, EventType, ScraperError
from src.pdf_utils import open_pdf
from src.scrapers import cap
from tests.conftest import FixtureFetcher, by_id, fixture_bytes, fixture_text, fixture_url

D = dt.date
SCHEDULE = "重要日程表.pdf"


@pytest.fixture(scope="module")
def schedule_pdf() -> bytes:
    return fixture_bytes(SCHEDULE)


@pytest.fixture(scope="module")
def rows(schedule_pdf):
    with open_pdf(schedule_pdf) as pdf:
        return cap.extract_rows(pdf.pages[0])


@pytest.fixture(scope="module")
def events(schedule_pdf):
    evs, skipped = cap.parse_schedule(schedule_pdf, 116, "https://example/cap.pdf", "116 日程表")
    return by_id(evs), skipped


def test_discover_latest_schedule_link():
    year, url, title = cap.discover(fixture_text(cap.HOME_URL), cap.HOME_URL)
    assert year == 116
    assert url == fixture_url(SCHEDULE)
    assert title.startswith("116學年度國中教育會考")


def test_rows_are_grouped_by_month_blocks(rows):
    months = sorted({r.month for r in rows})
    assert months == [2, 3, 4, 5, 6, 7]
    # 同一列跨多天（15、16 日共用一格）
    exam_row = next(r for r in rows if any("國中教育會考" == ln.split(":")[-1] for ln in r.lines))
    assert exam_row.days == [(15, "六"), (16, "日")]


def test_year_is_inferred_from_printed_weekdays(rows):
    years = cap.resolve_years(rows, 116)
    assert set(years.values()) == {2027}


def test_wrong_academic_year_cannot_match_weekdays(rows):
    with pytest.raises(DateParseError):
        cap.resolve_years(rows, 120)


def test_cap_core_events(events):
    ev, _ = events
    assert (ev["cap-116"].start_date, ev["cap-116"].end_date) == (D(2027, 5, 15), D(2027, 5, 16))
    assert ev["cap-116"].type is EventType.EXAM
    assert ev["cap-116"].category is Category.JUNIOR_HIGH
    assert (ev["cap-116-registration"].start_date, ev["cap-116-registration"].end_date) == (D(2027, 3, 4), D(2027, 3, 6))
    assert ev["cap-116-admission-ticket"].start_date == D(2027, 4, 9)
    assert ev["cap-116-result"].start_date == D(2027, 6, 4)
    assert "cap-116-make-up" not in ev  # 116 學年度官方未公布補考


def test_admission_events(events):
    ev, skipped = events
    assert ev["k12ea-116-free-admission-release"].start_date == D(2027, 7, 6)
    assert ev["k12ea-116-free-admission-release"].category is Category.HIGH_SCHOOL
    assert ev["k12ea-116-free-admission-choice-deadline"].start_date == D(2027, 6, 24)
    assert (ev["k12ea-116-five-year-joint-registration"].start_date, ev["k12ea-116-five-year-joint-registration"].end_date) == (
        D(2027, 6, 18), D(2027, 6, 24))
    # 跨月的項目日期（2月18日-3月3日）
    assert (ev["k12ea-116-science-class-registration"].start_date, ev["k12ea-116-science-class-registration"].end_date) == (
        D(2027, 2, 18), D(2027, 3, 3))
    # 多個編號項目在同一列，且各自帶日期（4月12日-5月3日 屬於 10~12 日那一列）
    assert ev["k12ea-116-vocational-special-exam"].start_date == D(2027, 4, 10)
    # 沒有對應規則的項目會被透明記錄，而不是默默丟掉
    assert any("運動績優生" in s for s in skipped)


def test_item_date_outside_row_is_rejected():
    row = cap.Row(month=5, days=[(15, "六")], lines=["20日-21日:技優甄審入學報名"], half=0)
    with pytest.raises(ScraperError, match="錯位"):
        cap.split_items(row)


def test_title_year_mismatch_is_rejected(schedule_pdf):
    with pytest.raises(ScraperError, match="學年度"):
        cap.parse_schedule(schedule_pdf, 115, "u", "t")


def test_history_cross_check():
    checks = cap.parse_history_cross_checks(fixture_text("history.html"), 116, cap.HISTORY_URL)
    assert len(checks) == 1
    assert (checks[0].target_id, checks[0].start_date, checks[0].end_date) == ("cap-116", D(2027, 5, 15), D(2027, 5, 16))


def test_scrape(fetcher):
    [result] = cap.scrape(fetcher)
    assert result.academic_year == 116
    assert result.id_prefixes == ("cap-", "k12ea-")
    assert len(result.events) >= 30
    assert result.cross_checks


def test_missing_schedule_link_fails_loudly():
    fetcher = FixtureFetcher({cap.HOME_URL: b"<html>empty</html>", cap.HISTORY_URL: b"<html>empty</html>"})
    with pytest.raises(ScraperError, match="重要日程表"):
        cap.scrape(fetcher)


def test_schedule_link_returns_html_fails_loudly():
    from src.fetch import FetchError

    fetcher = FixtureFetcher({fixture_url(SCHEDULE): b"<html>not found</html>"})
    with pytest.raises(FetchError, match="預期 PDF"):
        cap.scrape(fetcher)
