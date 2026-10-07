"""讀寫資料檔、與舊資料合併、變更偵測。

合併規則（每個 ScrapeResult = 一個來源的一個學年度）：
1. 以 (id 前綴, 學年度) 為單位整批替換：官方文件是唯一真實來源，同年度舊事件全部以新解析結果取代
   （官方刪除的項目也會跟著刪除）。
2. 其他學年度的舊事件保留作為歷史資料（最多保留 KEEP_YEARS 個學年度）。
3. 防止「舊資料覆蓋新資料」：若官方網站目前只提供比資料檔更舊的學年度
   （例如 117 已存在，網站卻退回顯示 116），較新年度的資料保持不動並發出警告。
4. 防止解析退化：同一來源同一學年度的事件數若比上次少超過 40%，視為錯誤。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import ScrapeResult
from .normalize import canonical, dumps, event_to_dict

KEEP_YEARS = 3
MIN_KEEP_RATIO = 0.6


@dataclass
class MergeReport:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(doc), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _owned(event_id: str, prefixes: tuple[str, ...]) -> bool:
    return any(event_id.startswith(p) for p in prefixes)


def _comparable(e: dict) -> dict:
    return {k: v for k, v in e.items() if k not in ("last_verified_at", "registration_start", "registration_end", "result_date")}


def merge(old_doc: dict | None, results: list[ScrapeResult], now: str) -> tuple[list[dict], MergeReport]:
    report = MergeReport()
    old_events: dict[str, dict] = {e["id"]: e for e in (old_doc or {}).get("events", [])}
    merged = dict(old_events)
    new_ids: dict[str, str] = {}

    for r in results:
        owned_old = [e for e in old_events.values() if _owned(e["id"], r.id_prefixes)]
        newer = sorted({e["academic_year"] for e in owned_old if e["academic_year"] > r.academic_year})
        if newer:
            report.warnings.append(
                f"[{r.source_key}] 官方網站目前提供 {r.academic_year} 學年度，但資料檔已有 {newer} 學年度；"
                "保留較新年度資料，不以舊年度覆蓋"
            )
        same_year = [e for e in owned_old if e["academic_year"] == r.academic_year]
        if len(same_year) >= 5 and len(r.events) < MIN_KEEP_RATIO * len(same_year):
            report.errors.append(
                f"[{r.source_key}] {r.academic_year} 學年度事件數由 {len(same_year)} 驟減為 {len(r.events)}，"
                "疑似官方網站改版或解析失敗，拒絕更新"
            )
            continue
        for e in same_year:
            merged.pop(e["id"], None)
        for ev in r.events:
            if ev.academic_year != r.academic_year:
                report.errors.append(f"[{r.source_key}] {ev.id} 的學年度 {ev.academic_year} 與來源學年度 {r.academic_year} 不同")
            if not _owned(ev.id, r.id_prefixes):
                report.errors.append(f"[{r.source_key}] {ev.id} 不屬於此來源的 id 前綴 {r.id_prefixes}")
            if ev.id in new_ids:
                report.errors.append(f"{ev.id} 同時由 {new_ids[ev.id]} 與 {r.source_key} 產生")
            new_ids[ev.id] = r.source_key
            merged[ev.id] = event_to_dict(ev, now)

    # 保留期限：每個來源只保留最近 KEEP_YEARS 個學年度
    for r in results:
        owned = [e for e in merged.values() if _owned(e["id"], r.id_prefixes)]
        if not owned:
            continue
        latest = max(e["academic_year"] for e in owned)
        for e in owned:
            if e["academic_year"] <= latest - KEEP_YEARS:
                merged.pop(e["id"], None)

    for eid in sorted(set(merged) - set(old_events)):
        report.added.append(eid)
    for eid in sorted(set(old_events) - set(merged)):
        report.removed.append(eid)
    for eid in sorted(set(merged) & set(old_events)):
        if _comparable(merged[eid]) != _comparable(old_events[eid]):
            report.changed.append(eid)
    return list(merged.values()), report


def has_changes(old_doc: dict | None, new_doc: dict) -> bool:
    return canonical(old_doc) != canonical(new_doc)


# ---------------------------------------------------------------- sources.json


def sources_canonical(doc: dict | None) -> str:
    if not doc:
        return ""
    items = [{k: v for k, v in s.items() if k != "last_success_at"} for s in doc.get("sources", [])]
    return json.dumps(items, ensure_ascii=False, sort_keys=True)
