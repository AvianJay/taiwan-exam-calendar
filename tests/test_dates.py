import datetime as dt

import pytest

from src.dates import (
    DateParseError,
    DateRange,
    academic_year_of,
    current_roc_year,
    extract_time_note,
    find_roc_dates,
    gregorian_to_roc,
    infer_year_from_weekdays,
    parse_roc_range,
    roc_date,
    roc_to_gregorian,
    strip_side_notes,
)

D = dt.date


class TestRocYear:
    def test_conversion(self):
        assert roc_to_gregorian(116) == 2027
        assert gregorian_to_roc(2026) == 115
        assert current_roc_year(D(2026, 10, 7)) == 115

    def test_non_positive_roc_year_rejected(self):
        with pytest.raises(DateParseError):
            roc_to_gregorian(0)

    def test_roc_date_checks_weekday(self):
        assert roc_date(116, 1, 22, "五") == D(2027, 1, 22)
        with pytest.raises(DateParseError, match="星期"):
            roc_date(116, 1, 22, "六")


class TestAcademicYear:
    def test_academic_year_spans_two_gregorian_years(self):
        # 學年度從 8 月開始：115 學年度 = 2026-08 ~ 2027-07
        assert academic_year_of(D(2026, 8, 1)) == 115
        assert academic_year_of(D(2027, 7, 31)) == 115
        assert academic_year_of(D(2027, 8, 1)) == 116

    def test_exam_year_is_not_academic_year_plus_1911(self):
        # 116 學年度的大學入學考試：英聽在 2026、學測在 2027；
        # 若用 116 + 1911 = 2027 推算英聽日期就會錯。日期一律以官方文件為準。
        listening = find_roc_dates("115.10.17(六)")[0].date
        gsat = find_roc_dates("116.01.22(五)")[0].date
        assert listening.year == 2026 and gsat.year == 2027
        assert academic_year_of(listening) == academic_year_of(gsat) == 115


class TestFindDates:
    def test_ceec_style_range_without_year_on_end(self):
        tokens = find_roc_dates("115.09.03(四)~09.10(四)")
        assert [t.date for t in tokens] == [D(2026, 9, 3), D(2026, 9, 10)]
        assert tokens[1].had_year is False

    def test_range_crossing_gregorian_year(self):
        dr = parse_roc_range("115.12.24(四)~01.05(二)")
        assert dr == DateRange(D(2026, 12, 24), D(2027, 1, 5))

    def test_various_official_formats(self):
        assert parse_roc_range("115年09月03日(四)~ 115年09月10日(四)") == DateRange(D(2026, 9, 3), D(2026, 9, 10))
        assert parse_roc_range("115年11 月04日(三)~") == DateRange.single(D(2026, 11, 4))
        assert parse_roc_range("115/06/03~115/06/16") == DateRange(D(2026, 6, 3), D(2026, 6, 16))
        assert parse_roc_range("115.5.15 (星期五)10:00 起 115.5.22 (星期五)17:00 止") == DateRange(
            D(2026, 5, 15), D(2026, 5, 22)
        )
        assert parse_roc_range("115.03.11（三）至 115.03.12（四）") == DateRange(D(2026, 3, 11), D(2026, 3, 12))

    def test_weekday_mismatch_is_an_error(self):
        with pytest.raises(DateParseError, match="星期"):
            find_roc_dates("115.09.03(五)")

    def test_invalid_calendar_date_is_an_error(self):
        with pytest.raises(DateParseError):
            find_roc_dates("115.02.30")

    def test_no_date(self):
        assert parse_roc_range("--") is None
        assert parse_roc_range("各校自訂【詳見招生學校甄選辦法】") is None
        # 沒有年份可承接的「月.日」不當成日期
        assert find_roc_dates("第 6-7 頁，版本 2.3") == []

    def test_strip_side_notes_removes_dates_inside_notes(self):
        text = "115.7.17 (星期五) 10：00起 115.7.22 (星期三) 24：00止 (便利商店繳費僅至115.7.18止)"
        assert parse_roc_range(text) == DateRange(D(2026, 7, 17), D(2026, 7, 18))  # 錯誤示範
        assert parse_roc_range(strip_side_notes(text)) == DateRange(D(2026, 7, 17), D(2026, 7, 22))
        assert parse_roc_range(strip_side_notes("115.02.25（三） 【115.02.26（四）寄發成績單】")) == DateRange.single(
            D(2026, 2, 25)
        )

    def test_date_range_rejects_reversed(self):
        with pytest.raises(DateParseError):
            DateRange(D(2027, 1, 2), D(2027, 1, 1))


class TestInferYear:
    def test_infer_from_weekdays(self):
        # 會考日程表只印「5 月 15 日 星期六」，用星期反推年份
        assert infer_year_from_weekdays([(5, 15, "六"), (5, 16, "日")], [2026, 2027, 2028]) == 2027

    def test_ambiguous_or_missing_match_raises(self):
        # 2026/2027/2028 的 5/15 分別是星期五/六/一，沒有星期三
        with pytest.raises(DateParseError, match="吻合 \\[\\]"):
            infer_year_from_weekdays([(5, 15, "三")], [2026, 2027, 2028])
        # 相隔 28 年的日曆相同 → 不唯一，必須報錯而不是隨便挑一個
        with pytest.raises(DateParseError, match="2027, 2055"):
            infer_year_from_weekdays([(5, 15, "六")], [2027, 2055])
        with pytest.raises(DateParseError):
            infer_year_from_weekdays([], [2027])


def test_extract_time_note():
    assert extract_time_note("115.03.11（三）至 115.03.12（四） 每日上午 9 時起至下午 5 時止") == "每日上午9時起至下午5時止"
    assert extract_time_note("114.12.05(五)上午9時起 ～ 114.12.17(三)下午5時止") == "上午9時起；下午5時止"
    assert extract_time_note("115.04.25(六)") is None
