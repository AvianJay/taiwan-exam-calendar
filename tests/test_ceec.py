import datetime as dt

import pytest

from src.models import EventType, ScraperError
from src.pdf_utils import OCRUnavailable, ocr_available, open_pdf
from src.scrapers import ceec
from tests.conftest import FixtureFetcher, by_id, fixture_bytes, fixture_text, fixture_url

D = dt.date
BROCHURE = "116學年度簡章.pdf"
DATES_PDF = "116學年度考試重要試務日期.pdf"


@pytest.fixture(scope="module")
def brochure() -> bytes:
    return fixture_bytes(BROCHURE)


@pytest.fixture(scope="module")
def matrix(brochure):
    page, _, year = ceec._find_pages(brochure)
    assert year == 116
    return ceec.parse_matrix(brochure, page, 116, "https://example/brochure.pdf", "116學年度考試簡章")


class TestDiscover:
    def test_homepage_block(self):
        links = ceec.discover(fixture_text(ceec.HOME_URL), ceec.HOME_URL)
        assert links.academic_year == 116
        assert links.brochure_url == fixture_url(BROCHURE)
        assert links.dates_url == fixture_url(DATES_PDF)

    def test_fallback_scans_file_pool_names_and_picks_latest_year(self):
        html = """
        <a href="https://www.ceec.edu.tw/files/file_pool/1/0p1/115%e5%ad%b8%e5%b9%b4%e5%ba%a6%e7%b0%a1%e7%ab%a0.pdf">x</a>
        <a href="https://www.ceec.edu.tw/files/file_pool/1/0q2/117%e5%ad%b8%e5%b9%b4%e5%ba%a6%e7%b0%a1%e7%ab%a0.pdf">y</a>
        """
        links = ceec.discover(html)
        assert links.academic_year == 117
        assert "0q2" in links.brochure_url

    def test_no_links_fails_loudly(self):
        with pytest.raises(ScraperError, match="網站結構可能已改變"):
            ceec.discover("<html><body>維護中</body></html>")


class TestMatrix:
    def test_core_dates(self, matrix):
        ev = matrix.events
        assert (ev["ceec-gsat-116"].start_date, ev["ceec-gsat-116"].end_date) == (D(2027, 1, 22), D(2027, 1, 24))
        assert (ev["ceec-gsat-116-registration"].start_date, ev["ceec-gsat-116-registration"].end_date) == (
            D(2026, 10, 27), D(2026, 11, 10))
        assert ev["ceec-gsat-116-result"].start_date == D(2027, 2, 25)
        assert ev["ceec-gsat-116-score-report"].start_date == D(2027, 2, 26)
        assert (ev["ceec-gsat-116-review"].start_date, ev["ceec-gsat-116-review"].end_date) == (D(2027, 2, 26), D(2027, 3, 4))
        assert (ev["ceec-ast-116"].start_date, ev["ceec-ast-116"].end_date) == (D(2027, 7, 10), D(2027, 7, 11))
        assert ev["ceec-ast-116-result"].start_date == D(2027, 7, 29)
        assert ev["ceec-english-listening-116-1"].start_date == D(2026, 10, 17)
        assert ev["ceec-english-listening-116-2"].start_date == D(2026, 12, 12)
        assert ev["ceec-english-listening-116-2-registration"].end_date == D(2026, 11, 10)
        assert ev["ceec-brochure-116"].start_date == D(2026, 8, 4)

    def test_academic_year_116_spans_2026_and_2027(self, matrix):
        years = {e.start_date.year for e in matrix.events.values()}
        assert years == {2026, 2027}
        assert all(e.academic_year == 116 for e in matrix.events.values())

    def test_types_and_ids(self, matrix):
        ev = matrix.events
        assert ev["ceec-gsat-116"].type is EventType.EXAM
        assert ev["ceec-gsat-116-registration"].type is EventType.REGISTRATION
        assert ev["ceec-gsat-116-result"].type is EventType.RESULT
        assert ev["ceec-gsat-116-review"].type is EventType.REVIEW
        # 英聽沒有「參考答案」（表格中為 --）
        assert "ceec-english-listening-116-1-answers" not in ev
        # 身心障礙應考服務列刻意略過
        assert not any("身心障礙" in (e.source_text or "") for e in ev.values())
        assert len(ev) == 35
        assert matrix.warnings == []

    def test_merged_cells_are_expanded(self, matrix):
        # 英聽「公布成績」與「寄發成績通知單」在表格中是同一個合併儲存格
        ev = matrix.events
        assert ev["ceec-english-listening-116-1-result"].start_date == ev["ceec-english-listening-116-1-score-report"].start_date

    def test_calendar_page_agrees(self, brochure, matrix):
        _, cal_page, _ = ceec._find_pages(brochure)
        with open_pdf(brochure) as pdf:
            calendar = ceec.parse_calendar_lines(pdf.pages[cal_page].extract_text(), 116)
        assert len(calendar) >= 20
        assert ceec.compare_with_calendar(matrix.events, calendar) == []

    def test_calendar_disagreement_is_detected(self, matrix):
        bad = {"ceec-gsat-116": ceec.DateRange(D(2027, 1, 23), D(2027, 1, 25))}
        errors = ceec.compare_with_calendar(matrix.events, bad)
        assert errors and "ceec-gsat-116" in errors[0]

    def test_standalone_dates_pdf_matches_brochure(self, matrix):
        grid = ceec.matrix_dates_only(fixture_bytes(DATES_PDF))
        assert ceec.compare_grids(matrix.grid_dates, grid) == []


class TestScrape:
    def test_scrape_from_fixtures(self, fetcher):
        [result] = ceec.scrape(fetcher)
        assert result.academic_year == 116
        assert len(result.events) == 35
        assert result.warnings == []
        ev = by_id(result.events)
        assert ev["ceec-gsat-116"].source_url == fixture_url(BROCHURE)
        assert "重要試務日期" in ev["ceec-gsat-116"].source_title

    def test_brochure_is_html_and_no_ocr_fails_loudly(self, monkeypatch):
        def no_ocr(*_args, **_kwargs):
            raise OCRUnavailable("測試：無 OCR")

        monkeypatch.setattr(ceec, "ocr_region", no_ocr)
        fetcher = FixtureFetcher({fixture_url(BROCHURE): b"<html>404</html>"})
        with pytest.raises(ScraperError, match="OCR"):
            ceec.scrape(fetcher)

    def test_all_pdfs_missing_fails(self):
        fetcher = FixtureFetcher({fixture_url(BROCHURE): None, fixture_url(DATES_PDF): None})
        with pytest.raises(ScraperError):
            ceec.scrape(fetcher)


@pytest.mark.skipif(not ocr_available(), reason="未安裝 rapidocr-onnxruntime（requirements-ocr.txt）")
def test_ocr_fallback_matches_brochure(matrix):
    """獨立「重要日程」PDF 的中文缺少文字層；以 OCR 辨識列標題後，日期必須與簡章一致。"""
    parsed = ceec.parse_matrix(fixture_bytes(DATES_PDF), 0, 116, "https://example/dates.pdf", "OCR", ocr=True)
    required = [r.format(y=116) for r in ceec.SPEC.required]
    assert all(r in parsed.events for r in required)
    for eid, ev in parsed.events.items():
        ref = matrix.events[eid]
        assert (ev.start_date, ev.end_date) == (ref.start_date, ref.end_date), eid
