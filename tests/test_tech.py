import datetime as dt

import pytest

from src.models import Category, EventType, ScraperError
from src.scrapers import tech
from tests.conftest import FixtureFetcher, by_id, fixture_bytes, fixture_text

D = dt.date


class TestTcte:
    def test_parse_table_with_rowspans(self):
        year, title, rows = tech.parse_tcte(fixture_text("TVETest/info4y"), tech.TCTE_URL)
        assert year == 115
        assert title == "115學年度四技二專統一入學測驗重要日程表"
        labels = [label for label, _ in rows]
        assert "報名費繳費學校集體報名" in labels  # rowspan 的上層項目會帶入
        assert "成績公告與查詢成績查詢" in labels

    def test_events(self, fetcher):
        [result] = tech.scrape_tcte(fetcher)
        ev = by_id(result.events)
        exam = ev["tech-test-115"]
        assert (exam.start_date, exam.end_date) == (D(2026, 4, 25), D(2026, 4, 26))
        assert exam.type is EventType.EXAM and exam.category is Category.TECHNICAL
        reg = ev["tech-test-115-registration"]
        # 115 學年度統測：報名在 2025 年、考試在 2026 年
        assert (reg.start_date, reg.end_date) == (D(2025, 12, 5), D(2025, 12, 17))
        assert reg.note == "上午9時起；下午5時止"
        assert ev["tech-test-115-result"].start_date == D(2026, 5, 14)
        assert (ev["tech-test-115-review"].start_date, ev["tech-test-115-review"].end_date) == (D(2026, 5, 14), D(2026, 5, 18))

    def test_missing_heading_fails_loudly(self):
        with pytest.raises(ScraperError, match="重要日程表"):
            tech.parse_tcte("<html><h3>網站改版中</h3><table></table></html>", tech.TCTE_URL)


class TestJctv:
    def test_landing_gives_latest_year_and_sub_id(self):
        year, sub_id = tech.jctv_landing(fixture_text("https://www.jctv.ntut.edu.tw/enter42/apply/"), "https://www.jctv.ntut.edu.tw/enter42/apply/")
        assert (year, sub_id) == (116, "181")

    def test_unpublished_year_has_no_pdf(self):
        assert tech.jctv_schedule_pdf(fixture_text("academicYear=116&subId=181"), "https://x/", tech.APPLY.link_pattern) is None
        url, text = tech.jctv_schedule_pdf(fixture_text("academicYear=115&subId=181"), "https://x/", tech.APPLY.link_pattern)
        assert url.endswith("115_apply_date1.pdf") and "簡章版" in text

    def test_apply_falls_back_to_previous_year(self, fetcher):
        result = tech.scrape_jctv_channel(fetcher, tech.APPLY)
        assert result.academic_year == 115
        assert any("116 學年度重要日程尚未公布" in w for w in result.warnings)
        ev = by_id(result.events)
        reg = ev["jctv-apply-115-registration"]
        assert (reg.start_date, reg.end_date) == (D(2026, 5, 15), D(2026, 5, 22))
        assert ev["jctv-apply-115-release"].start_date == D(2026, 7, 14)
        stage2 = ev["jctv-apply-115-stage2-exam"]
        assert (stage2.start_date, stage2.end_date) == (D(2026, 6, 13), D(2026, 6, 28))
        assert stage2.note.startswith("日期由各校自訂")
        # 「函告未報到名單」不是考生報到
        assert (ev["jctv-apply-115-enrollment"].start_date, ev["jctv-apply-115-enrollment"].end_date) == (
            D(2026, 7, 16), D(2026, 7, 20))
        targets = {c.target_id: (c.start_date, c.end_date) for c in result.cross_checks}
        assert targets["tech-test-115"] == (D(2026, 4, 25), D(2026, 4, 26))

    def test_skill(self, fetcher):
        result = tech.scrape_jctv_channel(fetcher, tech.SKILL)
        ev = by_id(result.events)
        assert (ev["jctv-skill-115-registration"].start_date, ev["jctv-skill-115-registration"].end_date) == (
            D(2026, 5, 18), D(2026, 5, 22))
        assert ev["jctv-skill-115-release"].start_date == D(2026, 7, 7)

    def test_union_ignores_dates_inside_side_notes(self, fetcher):
        result = tech.scrape_jctv_channel(fetcher, tech.UNION)
        ev = by_id(result.events)
        # 「(便利商店繳費僅至115.7.18止)」不能變成區間結束日
        assert (ev["jctv-union-115-payment"].start_date, ev["jctv-union-115-payment"].end_date) == (
            D(2026, 7, 17), D(2026, 7, 22))
        assert ev["jctv-union-115-release"].start_date == D(2026, 8, 6)
        assert ev["jctv-union-115-preference-practice"].type is EventType.OTHER

    def test_pdf_year_mismatch_rejected(self):
        with pytest.raises(ScraperError, match="學年度"):
            tech.parse_jctv_pdf(fixture_bytes("115_apply_date1.pdf"), tech.APPLY, 116, "u", "t")

    def test_no_schedule_in_two_years_fails(self):
        empty = b"<html><body>\xe7\x9b\xae\xe5\x89\x8d\xe5\xb0\x9a\xe7\x84\xa1\xe8\xb3\x87\xe8\xa8\x8a!!</body></html>"
        fetcher = FixtureFetcher({
            "https://www.jctv.ntut.edu.tw/enter42/apply/contents.php?academicYear=115&subId=181": empty,
        })
        with pytest.raises(ScraperError, match="都找不到"):
            tech.scrape_jctv_channel(fetcher, tech.APPLY)
