"""事件正規化與 JSON canonicalization。

- 把 scraper 的 Event 轉成輸出用 dict（固定欄位順序）
- 考試事件自動帶入同組的報名期間與成績公布日（registration_* / result_date）
- canonical()：移除 updated_at / last_verified_at 後排序輸出，用於變更偵測
"""

from __future__ import annotations

import json
import re

from .models import SCHEMA_VERSION, Event, EventType

VOLATILE_TOP = ("updated_at",)
VOLATILE_EVENT = ("last_verified_at",)
EVENT_KEYS = (
    "id", "academic_year", "category", "type", "exam", "name", "organizer",
    "start_date", "end_date", "registration_start", "registration_end", "result_date",
    "note", "source_url", "source_title", "source_text", "last_verified_at",
)


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def event_to_dict(ev: Event, verified_at: str) -> dict:
    d = ev.to_dict(verified_at)
    for k in ("name", "organizer", "note", "source_title", "source_text", "exam"):
        d[k] = _clean(d[k])
    return d


def _sibling(by_id: dict[str, dict], exam_id: str, suffix: str) -> dict | None:
    """考試事件 X 的報名／成績事件：X-registration，或去掉結尾 -exam 後的 base-registration。"""
    for base in (exam_id, re.sub(r"-exam$", "", exam_id)):
        sib = by_id.get(f"{base}-{suffix}")
        if sib:
            return sib
    return None


def link_summary_fields(events: list[dict]) -> list[dict]:
    """為 type=exam 的事件填入報名期間與成績公布日（只取自同一來源的官方事件，不推測）。"""
    by_id = {e["id"]: e for e in events}
    for e in events:
        if e["type"] != EventType.EXAM.value:
            continue
        reg = _sibling(by_id, e["id"], "registration")
        if reg and reg["academic_year"] == e["academic_year"]:
            e["registration_start"] = reg["start_date"]
            e["registration_end"] = reg["end_date"]
        res = _sibling(by_id, e["id"], "result")
        if res and res["academic_year"] == e["academic_year"]:
            e["result_date"] = res["start_date"]
    return events


def order_event(e: dict) -> dict:
    return {k: e.get(k) for k in EVENT_KEYS}


def sort_events(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda e: (e["start_date"], e["end_date"], e["id"]))


def build_document(events: list[dict], updated_at: str) -> dict:
    events = sort_events([order_event(e) for e in link_summary_fields(events)])
    return {"schema_version": SCHEMA_VERSION, "updated_at": updated_at, "events": events}


def canonical(doc: dict | None) -> str:
    """去除時間戳記後的穩定字串；只有這個字串改變才算「資料有變更」。"""
    if not doc:
        return ""
    top = {k: v for k, v in doc.items() if k not in VOLATILE_TOP and k != "events"}
    events = sorted(
        ({k: v for k, v in e.items() if k not in VOLATILE_EVENT} for e in doc.get("events", [])),
        key=lambda e: e.get("id", ""),
    )
    return json.dumps({**top, "events": events}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dumps(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
