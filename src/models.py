"""資料模型：統一的事件格式、交叉驗證宣稱、scraper 結果。"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import Enum

SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Category(str, Enum):
    UNIVERSITY = "university"  # 大學入學考試（英聽、學測、分科）
    HIGH_SCHOOL = "high_school"  # 高中職／五專入學管道（免試入學、特色招生…）
    JUNIOR_HIGH = "junior_high"  # 國中教育會考
    TECHNICAL = "technical"  # 技職體系（統測、四技二專甄選、技優甄審、聯合登記分發）
    ADMISSION = "admission"  # 大學入學管道（繁星推薦、個人申請、分發入學）
    OTHER = "other"


class EventType(str, Enum):
    EXAM = "exam"  # 考試／甄試
    REGISTRATION = "registration"  # 報名、繳費
    RESULT = "result"  # 成績公布、成績單寄發、篩選結果
    REVIEW = "review"  # 成績複查、結果複查
    ADMISSION = "admission"  # 放榜、志願選填、分發、報到、聲明放棄
    ANNOUNCEMENT = "announcement"  # 簡章發售、准考證、試場分配、參考答案
    OTHER = "other"


@dataclass
class Event:
    id: str
    academic_year: int
    category: Category
    type: EventType
    exam: str
    name: str
    organizer: str
    start_date: dt.date
    end_date: dt.date
    source_url: str
    source_title: str
    registration_start: dt.date | None = None
    registration_end: dt.date | None = None
    result_date: dt.date | None = None
    note: str | None = None
    source_text: str | None = None

    def to_dict(self, verified_at: str) -> dict:
        def iso(d: dt.date | None) -> str | None:
            return d.isoformat() if d else None

        return {
            "id": self.id,
            "academic_year": self.academic_year,
            "category": self.category.value,
            "type": self.type.value,
            "exam": self.exam,
            "name": self.name,
            "organizer": self.organizer,
            "start_date": iso(self.start_date),
            "end_date": iso(self.end_date),
            "registration_start": iso(self.registration_start),
            "registration_end": iso(self.registration_end),
            "result_date": iso(self.result_date),
            "note": self.note,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_text": self.source_text,
            "last_verified_at": verified_at,
        }


@dataclass(frozen=True)
class CrossCheck:
    """其他（次要）來源對某個 event 日期的宣稱。

    只用來比對與發出警告，**永遠不會覆蓋** primary 來源的日期。
    """

    target_id: str
    start_date: dt.date
    end_date: dt.date
    source_url: str
    label: str


@dataclass
class ScrapeResult:
    """一個 scraper（一個官方來源、一個學年度）的輸出。"""

    source_key: str
    name: str
    organizer: str
    academic_year: int
    source_url: str
    source_title: str
    id_prefixes: tuple[str, ...]
    events: list[Event] = field(default_factory=list)
    cross_checks: list[CrossCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # 官方文件中有日期、但不在對照規則內而略過的項目（透明記錄，不算錯誤）
    skipped_items: list[str] = field(default_factory=list)


class ScraperError(RuntimeError):
    """官方資料抓不到、結構改變或解析結果不合理。會讓整個 pipeline 失敗。"""
