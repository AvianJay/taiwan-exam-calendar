"""嚴格驗證：JSON Schema + 語意檢查 + 交叉驗證。

errors 會讓 pipeline 失敗（不寫入資料）；warnings 會出現在 Actions 摘要中但不阻擋更新；
infos 僅供參考。

用法：python -m src.validate data/exams.json
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .dates import current_roc_year
from .fetch import utf8_stdio
from .models import ID_PATTERN, CrossCheck

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "exams.schema.json"


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: "ValidationReport") -> None:
        self.errors += other.errors
        self.warnings += other.warnings
        self.infos += other.infos


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _date(value) -> dt.date | None:
    if value is None:
        return None
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def schema_errors(doc: dict) -> list[str]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"schema：{path}：{err.message}")
    return out


def check_events(events: list[dict], today: dt.date | None = None) -> ValidationReport:
    report = ValidationReport()
    today = today or dt.date.today()
    max_year = current_roc_year(today) + 2

    if not events:
        report.errors.append("沒有任何事件；拒絕產生空的資料檔")
        return report

    seen: dict[str, int] = {}
    for i, e in enumerate(events):
        eid = e.get("id") or f"#{i}"
        if eid in seen:
            report.errors.append(f"重複的 event id：{eid}")
        seen[eid] = i
        if not isinstance(e.get("id"), str) or not ID_PATTERN.match(e["id"]):
            report.errors.append(f"{eid}：id 格式不符（只允許小寫英數與連字號）")

        for key in ("name", "organizer", "source_url", "source_title", "exam"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                report.errors.append(f"{eid}：{key} 不得為空")
        url = e.get("source_url") or ""
        if url and not url.startswith(("https://", "http://")):
            report.errors.append(f"{eid}：source_url 不是有效網址：{url}")

        dates = {}
        for key in ("start_date", "end_date", "registration_start", "registration_end", "result_date"):
            value = e.get(key)
            if value is None and key not in ("start_date", "end_date"):
                continue
            d = _date(value)
            if d is None:
                report.errors.append(f"{eid}：{key} 必須是 YYYY-MM-DD 的有效日期，實際為 {value!r}")
            dates[key] = d

        ay = e.get("academic_year")
        if not isinstance(ay, int) or not 100 <= ay <= max_year:
            report.errors.append(f"{eid}：academic_year {ay!r} 不合理（應介於 100 與 {max_year}）")
            continue

        start, end = dates.get("start_date"), dates.get("end_date")
        if start and end and start > end:
            report.errors.append(f"{eid}：start_date {start} 晚於 end_date {end}")
        rs, re_ = dates.get("registration_start"), dates.get("registration_end")
        if (rs is None) != (re_ is None):
            report.errors.append(f"{eid}：registration_start 與 registration_end 必須同時存在或同時為 null")
        if rs and re_ and rs > re_:
            report.errors.append(f"{eid}：報名開始 {rs} 晚於報名截止 {re_}")
        if re_ and start and e.get("type") == "exam" and re_ > start:
            report.errors.append(f"{eid}：報名截止 {re_} 晚於考試開始 {start}（日期互相衝突）")
        res = dates.get("result_date")
        if res and end and e.get("type") == "exam" and res < end:
            report.errors.append(f"{eid}：成績公布 {res} 早於考試結束 {end}（日期互相衝突）")

        # 學年度與實際日期的合理範圍：N 學年度的事件應落在西元 (N+1909)～(N+1912) 年
        for key, d in dates.items():
            if d and not (ay + 1909 <= d.year <= ay + 1912):
                report.errors.append(f"{eid}：{key} {d} 與 {ay} 學年度不相符（年份超出合理範圍）")
        span = (end - start).days if start and end else 0
        if span > 400:
            report.errors.append(f"{eid}：日期區間長達 {span} 天，疑似解析錯誤")

    # 同一考試的報名摘要欄位必須與報名事件一致
    by_id = {e.get("id"): e for e in events}
    for e in events:
        if e.get("type") != "exam" or not e.get("registration_start"):
            continue
        for reg_id in (f"{e['id']}-registration", f"{e['id'].removesuffix('-exam')}-registration"):
            reg = by_id.get(reg_id)
            if reg:
                if (reg["start_date"], reg["end_date"]) != (e["registration_start"], e["registration_end"]):
                    report.errors.append(f"{e['id']}：registration 欄位與 {reg_id} 日期不一致")
                break
    return report


def check_cross(events: list[dict], checks: Iterable[CrossCheck]) -> ValidationReport:
    """次要來源的宣稱與 primary 事件比對：不一致只發警告，不覆蓋。"""
    report = ValidationReport()
    by_id = {e["id"]: e for e in events}
    for c in checks:
        ev = by_id.get(c.target_id)
        claim = f"{c.start_date}~{c.end_date}"
        if ev is None:
            report.infos.append(f"交叉驗證略過：{c.target_id} 不在資料中（{c.label}：{claim}）")
            continue
        actual = f"{ev['start_date']}~{ev['end_date']}"
        if (ev["start_date"], ev["end_date"]) != (c.start_date.isoformat(), c.end_date.isoformat()):
            report.warnings.append(
                f"交叉驗證不一致：{c.target_id} 官方主要來源為 {actual}，但 {c.label} 寫 {claim}（{c.source_url}）"
            )
        else:
            report.infos.append(f"交叉驗證一致：{c.target_id} {actual}（{c.label}）")
    return report


def validate_document(doc: dict, *, cross_checks: Iterable[CrossCheck] = (), today: dt.date | None = None
                      ) -> ValidationReport:
    report = ValidationReport()
    report.errors += schema_errors(doc)
    events = doc.get("events") if isinstance(doc, dict) else None
    if not isinstance(events, list):
        report.errors.append("events 必須是陣列")
        return report
    report.extend(check_events(events, today))
    report.extend(check_cross(events, cross_checks))
    return report


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0] if argv else "data/exams.json")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::無法讀取 {path}：{exc}")
        return 1
    report = validate_document(doc)
    for w in report.warnings:
        print(f"::warning::{w}")
    for e in report.errors:
        print(f"::error::{e}")
    if report.ok:
        print(f"{path}：驗證通過（{len(doc.get('events', []))} 筆事件）")
        return 0
    print(f"{path}：驗證失敗（{len(report.errors)} 個錯誤）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
