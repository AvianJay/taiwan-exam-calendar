import datetime as dt

import pytest

from src.models import Category, EventType, ScraperError
from src.scrapers import admission
from tests.conftest import by_id, fixture_text

D = dt.date


def test_portal_lists_latest_years():
    assert admission.cac_latest_years(fixture_text("cacportal")) == {"star": 116, "apply": 116}


def test_unpublished_schedule_returns_none():
    assert admission.parse_cac_schedule(fixture_text("star116/schedule.php")) is None


def test_changed_layout_fails_loudly():
    with pytest.raises(ScraperError, match="結構可能已改變"):
        admission.parse_cac_schedule("<html><table><tr><td>新版首頁</td></tr></table></html>")


def test_star(fetcher):
    [result] = admission.scrape_cac(fetcher, admission.STAR)
    assert result.academic_year == 115
    assert any("116 學年度重要時程尚未公布" in w for w in result.warnings)
    ev = by_id(result.events)
    reg = ev["cac-star-115-registration"]
    assert (reg.start_date, reg.end_date) == (D(2026, 3, 11), D(2026, 3, 12))
    assert reg.category is Category.ADMISSION and reg.type is EventType.REGISTRATION
    assert ev["cac-star-115-release"].start_date == D(2026, 3, 18)
    interview = ev["cac-star-115-group8-interview"]
    # 「大學自訂（115.05.14 至 115.05.31）」括號內的日期是有效區間
    assert (interview.start_date, interview.end_date) == (D(2026, 5, 14), D(2026, 5, 31))
    assert interview.note.startswith("日期由各大學自訂")
    # 學測日期只作為交叉驗證，不產生 CAC 事件
    assert not any("學科能力測驗" == e.name for e in result.events)
    claims = {c.target_id: (c.start_date, c.end_date) for c in result.cross_checks}
    assert claims["ceec-gsat-115"] == (D(2026, 1, 17), D(2026, 1, 19))
    # 「115.02.25（三） 【115.02.26（四）寄發成績單】」只取主要日期
    assert claims["ceec-gsat-115-result"] == (D(2026, 2, 25), D(2026, 2, 25))


def test_apply(fetcher):
    [result] = admission.scrape_cac(fetcher, admission.APPLY)
    ev = by_id(result.events)
    assert (ev["cac-apply-115-registration"].start_date, ev["cac-apply-115-registration"].end_date) == (
        D(2026, 3, 24), D(2026, 3, 25))
    assert ev["cac-apply-115-screening-result"].start_date == D(2026, 3, 31)
    assert ev["cac-apply-115-release"].start_date == D(2026, 6, 11)
    assert (ev["cac-apply-115-preference-registration"].start_date, ev["cac-apply-115-preference-registration"].end_date) == (
        D(2026, 6, 4), D(2026, 6, 5))


def test_uac(fetcher):
    [result] = admission.scrape_uac(fetcher)
    assert result.academic_year == 115
    ev = by_id(result.events)
    assert ev["uac-115-release"].start_date == D(2026, 8, 17)
    pref = ev["uac-115-preference-registration"]
    assert (pref.start_date, pref.end_date) == (D(2026, 8, 5), D(2026, 8, 8))
    assert pref.note == "下午04:30止"
    claims = {c.target_id: (c.start_date, c.end_date) for c in result.cross_checks}
    assert claims["ceec-ast-115"] == (D(2026, 7, 13), D(2026, 7, 14))
    assert claims["cac-star-115-waiver"] == (D(2026, 3, 18), D(2026, 3, 20))


def test_uac_missing_heading_fails():
    with pytest.raises(ScraperError, match="重要時程"):
        admission.parse_uac("<html><h2>其他頁面</h2></html>")
