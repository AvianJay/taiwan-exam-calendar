import copy
import datetime as dt
import json

import pytest

from src import validate
from src.models import CrossCheck

TODAY = dt.date(2026, 10, 7)
TS = "2026-10-07T00:00:00Z"


def event(**overrides) -> dict:
    base = {
        "id": "ceec-gsat-116",
        "academic_year": 116,
        "category": "university",
        "type": "exam",
        "exam": "gsat",
        "name": "學科能力測驗",
        "organizer": "CEEC",
        "start_date": "2027-01-22",
        "end_date": "2027-01-24",
        "registration_start": "2026-10-27",
        "registration_end": "2026-11-10",
        "result_date": "2027-02-25",
        "note": None,
        "source_url": "https://www.ceec.edu.tw/files/file_pool/1/x/116.pdf",
        "source_title": "116學年度考試簡章",
        "source_text": "考試｜116.01.22(五)~116.01.24(日)",
        "last_verified_at": TS,
    }
    base.update(overrides)
    return base


def registration(**overrides) -> dict:
    return event(id="ceec-gsat-116-registration", type="registration", name="學科能力測驗 報名",
                 start_date="2026-10-27", end_date="2026-11-10",
                 registration_start=None, registration_end=None, result_date=None, **overrides)


def doc(*events) -> dict:
    return {"schema_version": 1, "updated_at": TS, "events": list(events)}


def errors_of(d) -> list[str]:
    return validate.validate_document(d, today=TODAY).errors


def test_valid_document_passes():
    report = validate.validate_document(doc(event(), registration()), today=TODAY)
    assert report.ok, report.errors


def test_empty_events_rejected():
    errs = errors_of(doc())
    assert any("沒有任何事件" in e for e in errs)


def test_duplicate_id():
    assert any("重複的 event id" in e for e in errors_of(doc(event(), event())))


@pytest.mark.parametrize("bad", ["2027/01/22", "2027-1-22", "2027-02-30", "", None])
def test_date_format(bad):
    errs = errors_of(doc(event(start_date=bad)))
    assert any("start_date" in e for e in errs)


def test_start_after_end():
    assert any("晚於 end_date" in e for e in errors_of(doc(event(start_date="2027-01-25"))))


@pytest.mark.parametrize("year", [99, 118, "116", None])
def test_academic_year_range(year):
    # 2026 年（民國 115 年）時，最多接受到 117 學年度
    assert any("academic_year" in e for e in errors_of(doc(event(academic_year=year))))


def test_dates_must_match_academic_year():
    errs = errors_of(doc(event(start_date="2035-01-22", end_date="2035-01-24", registration_start=None,
                               registration_end=None, result_date=None)))
    assert any("不相符" in e for e in errs)


@pytest.mark.parametrize("field", ["source_url", "name", "organizer", "source_title"])
def test_required_text_fields(field):
    assert any(field in e for e in errors_of(doc(event(**{field: ""}))))


def test_source_url_must_be_http():
    assert any("source_url" in e for e in errors_of(doc(event(source_url="file:///tmp/x.pdf"))))


def test_registration_after_exam_is_conflict():
    errs = errors_of(doc(event(registration_end="2027-01-23")))
    assert any("衝突" in e for e in errs)


def test_result_before_exam_end_is_conflict():
    assert any("衝突" in e for e in errors_of(doc(event(result_date="2027-01-23"))))


def test_summary_fields_must_match_registration_event():
    errs = errors_of(doc(event(registration_start="2026-10-26"), registration()))
    assert any("不一致" in e for e in errs)


def test_half_registration_fields_rejected():
    assert any("同時" in e for e in errors_of(doc(event(registration_end=None))))


def test_schema_rejects_unknown_fields_and_enums():
    errs = errors_of(doc(event(category="kindergarten", extra="x")))
    assert any("schema" in e and "kindergarten" in e for e in errs)
    assert any("schema" in e and "extra" in e for e in errs)


def test_bad_id_format():
    assert any("id" in e for e in errors_of(doc(event(id="CEEC_GSAT_116"))))


def test_cross_check_mismatch_is_warning_not_error():
    claim = CrossCheck("ceec-gsat-116", dt.date(2027, 1, 23), dt.date(2027, 1, 25), "https://www.uac.edu.tw/flow.htm", "分發會")
    report = validate.validate_document(doc(event(), registration()), cross_checks=[claim], today=TODAY)
    assert report.ok
    assert any("交叉驗證不一致" in w for w in report.warnings)


def test_cross_check_match_and_missing_target_are_info():
    ok = CrossCheck("ceec-gsat-116", dt.date(2027, 1, 22), dt.date(2027, 1, 24), "u", "分發會")
    missing = CrossCheck("ceec-gsat-115", dt.date(2026, 1, 17), dt.date(2026, 1, 19), "u", "分發會")
    report = validate.validate_document(doc(event(), registration()), cross_checks=[ok, missing], today=TODAY)
    assert not report.warnings
    assert len(report.infos) == 2


def test_cli(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(doc(event(), registration()), ensure_ascii=False), encoding="utf-8")
    bad = tmp_path / "bad.json"
    broken = copy.deepcopy(doc(event()))
    broken["events"][0]["end_date"] = "2027-01-01"
    bad.write_text(json.dumps(broken), encoding="utf-8")
    assert validate.main([str(good)]) == 0
    assert validate.main([str(bad)]) == 1
    assert validate.main([str(tmp_path / "missing.json")]) == 1
