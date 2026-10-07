import datetime as dt

from src.models import Category, Event, EventType, ScrapeResult
from src.normalize import build_document, canonical, link_summary_fields
from src.store import has_changes, merge

D = dt.date


def ev(eid: str, year: int, start: dt.date, end: dt.date | None = None, etype=EventType.EXAM) -> Event:
    return Event(
        id=eid, academic_year=year, category=Category.UNIVERSITY, type=etype, exam="gsat",
        name=eid, organizer="CEEC", start_date=start, end_date=end or start,
        source_url="https://www.ceec.edu.tw/x.pdf", source_title="簡章",
    )


def result(year: int, events: list[Event], prefix: str = "ceec-") -> ScrapeResult:
    return ScrapeResult(source_key="ceec", name="CEEC", organizer="CEEC", academic_year=year,
                        source_url="https://www.ceec.edu.tw/", source_title="簡章", id_prefixes=(prefix,), events=events)


def gsat_events(year: int, n: int = 6) -> list[Event]:
    base = D(year + 1911, 1, 20)
    return [ev(f"ceec-gsat-{year}" + ("" if i == 0 else f"-x{i}"), year, base + dt.timedelta(days=i)) for i in range(n)]


def doc_from(results, old=None, now="2026-10-07T00:00:00Z"):
    events, report = merge(old, results, now)
    return build_document(events, now), report


class TestChangeDetection:
    def test_only_timestamps_differ_means_no_change(self):
        a, _ = doc_from([result(116, gsat_events(116))], now="2026-10-07T00:00:00Z")
        b, _ = doc_from([result(116, gsat_events(116))], now="2026-10-14T00:00:00Z")
        assert a["updated_at"] != b["updated_at"]
        assert a["events"][0]["last_verified_at"] != b["events"][0]["last_verified_at"]
        assert canonical(a) == canonical(b)
        assert not has_changes(a, b)

    def test_date_change_is_detected(self):
        a, _ = doc_from([result(116, gsat_events(116))])
        changed = gsat_events(116)
        changed[0].end_date = changed[0].start_date + dt.timedelta(days=1)
        b, report = doc_from([result(116, changed)], old=a)
        assert has_changes(a, b)
        assert report.changed == ["ceec-gsat-116"]

    def test_event_order_does_not_matter(self):
        a, _ = doc_from([result(116, gsat_events(116))])
        b = dict(a, events=list(reversed(a["events"])))
        assert not has_changes(a, b)


class TestMerge:
    def test_same_year_replaced_other_years_kept(self):
        old, _ = doc_from([result(115, gsat_events(115)), result(116, gsat_events(116))])
        new_116 = gsat_events(116, n=5)  # 官方刪除了一筆
        merged, report = doc_from([result(116, new_116)], old=old)
        ids = {e["id"] for e in merged["events"]}
        assert "ceec-gsat-115" in ids  # 歷史年度保留
        assert "ceec-gsat-116-x5" not in ids
        assert report.removed == ["ceec-gsat-116-x5"]

    def test_older_year_never_overwrites_newer(self):
        old, _ = doc_from([result(117, gsat_events(117))])
        merged, report = doc_from([result(116, gsat_events(116))], old=old)
        ids = {e["id"] for e in merged["events"]}
        assert "ceec-gsat-117" in ids and "ceec-gsat-116" in ids
        assert any("不以舊年度覆蓋" in w for w in report.warnings)
        old_117 = next(e for e in old["events"] if e["id"] == "ceec-gsat-117")
        new_117 = next(e for e in merged["events"] if e["id"] == "ceec-gsat-117")
        assert old_117 == new_117

    def test_sudden_drop_in_events_is_an_error(self):
        old, _ = doc_from([result(116, gsat_events(116, n=10))])
        _, report = doc_from([result(116, gsat_events(116, n=3))], old=old)
        assert any("驟減" in e for e in report.errors)

    def test_retention_keeps_recent_years_only(self):
        old, _ = doc_from([result(y, gsat_events(y)) for y in (113, 114, 115)])
        merged, report = doc_from([result(116, gsat_events(116))], old=old)
        years = {e["academic_year"] for e in merged["events"]}
        assert years == {114, 115, 116}
        assert "ceec-gsat-113" in report.removed

    def test_id_outside_prefix_rejected(self):
        bad = result(116, [ev("cap-116", 116, D(2027, 5, 15))])
        _, report = doc_from([bad])
        assert any("不屬於" in e for e in report.errors)

    def test_two_sources_same_id_rejected(self):
        a = result(116, [ev("ceec-gsat-116", 116, D(2027, 1, 22))])
        b = result(116, [ev("ceec-gsat-116", 116, D(2027, 1, 23))])
        _, report = doc_from([a, b])
        assert any("同時由" in e for e in report.errors)


def test_exam_summary_fields_are_linked_from_siblings():
    events = [
        {"id": "cap-116", "type": "exam", "academic_year": 116, "start_date": "2027-05-15", "end_date": "2027-05-16",
         "registration_start": None, "registration_end": None, "result_date": None},
        {"id": "cap-116-registration", "type": "registration", "academic_year": 116,
         "start_date": "2027-03-04", "end_date": "2027-03-06"},
        {"id": "cap-116-result", "type": "result", "academic_year": 116, "start_date": "2027-06-04", "end_date": "2027-06-04"},
        {"id": "k12ea-116-sports-class-exam", "type": "exam", "academic_year": 116, "start_date": "2027-05-22",
         "end_date": "2027-05-22", "registration_start": None, "registration_end": None, "result_date": None},
        {"id": "k12ea-116-sports-class-registration", "type": "registration", "academic_year": 116,
         "start_date": "2027-05-17", "end_date": "2027-05-19"},
    ]
    out = {e["id"]: e for e in link_summary_fields(events)}
    assert (out["cap-116"]["registration_start"], out["cap-116"]["registration_end"]) == ("2027-03-04", "2027-03-06")
    assert out["cap-116"]["result_date"] == "2027-06-04"
    assert out["k12ea-116-sports-class-exam"]["registration_end"] == "2027-05-19"
    assert out["k12ea-116-sports-class-exam"]["result_date"] is None  # 官方沒有就不推測
