"""scraper 共用元件：規格宣告、事件建構與文字比對規則。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from ..dates import DateRange, normalize_text
from ..fetch import Fetcher
from ..models import Category, Event, EventType, ScrapeResult, ScraperError


@dataclass(frozen=True)
class ScraperSpec:
    """scraper 規格：給 registry、README 與 sources.json 使用。"""

    key: str
    name: str
    organizer: str
    exams: str  # 人類可讀的考試／管道名稱
    homepage: str
    run: Callable[[Fetcher], list[ScrapeResult]]
    # 必須存在的 event id 後綴（{y} 會換成學年度），缺任何一個就視為解析失敗
    required: tuple[str, ...] = ()
    min_events: int = 1


@dataclass(frozen=True)
class Rule:
    """把官方項目文字對應到統一事件的規則。

    pattern 以 `re.search` 比對正規化後（去空白、NFKC）的項目文字；
    suffix 為空字串代表事件本體（例如 cap-116）；name 為完整顯示名稱。
    """

    pattern: str
    suffix: str | None  # None 代表明確略過
    type: EventType = EventType.OTHER
    name: str = ""
    category: Category | None = None
    organizer: str | None = None
    exam: str | None = None
    exclude: str | None = None

    def matches(self, text: str) -> bool:
        if self.exclude and re.search(self.exclude, text):
            return False
        return re.search(self.pattern, text) is not None


@dataclass(frozen=True)
class CrossRule:
    """次要來源（例如分發會時程表上的「學測考試」）→ primary event id 的對應。"""

    pattern: str
    target: str  # 例如 "ceec-gsat-{y}"
    exclude: str | None = None

    def matches(self, text: str) -> bool:
        if self.exclude and re.search(self.exclude, text):
            return False
        return re.search(self.pattern, text) is not None


def squash(text: str) -> str:
    """比對用：NFKC、去所有空白。"""
    return re.sub(r"\s+", "", normalize_text(text or ""))


def tidy(text: str) -> str:
    """顯示用：NFKC、合併多餘空白（保留中文標點）。"""
    t = normalize_text(text or "").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    # 中文字之間的換行或空白通常只是 PDF 斷行
    return re.sub(r"(?<=[一-鿿）」】])\s+(?=[一-鿿（「【])", "", t)


def match_rule(rules: list[Rule], text: str) -> Rule | None:
    key = squash(text)
    for rule in rules:
        if rule.matches(key):
            return rule
    return None


@dataclass
class EventBuilder:
    """收集事件並阻擋同一 id 重複出現（同一來源內的重複代表規則或解析有誤）。"""

    academic_year: int
    id_prefix: str  # 例如 "jctv-apply-116"
    category: Category
    organizer: str
    exam: str
    exam_name: str
    source_url: str
    source_title: str
    events: dict[str, Event] = field(default_factory=dict)

    def add(self, rule: Rule, dr: DateRange, *, source_text: str, note: str | None = None,
            id_override: str | None = None) -> Event:
        assert rule.suffix is not None
        eid = id_override or (f"{self.id_prefix}-{rule.suffix}" if rule.suffix else self.id_prefix)
        if eid in self.events:
            prev = self.events[eid]
            if (prev.start_date, prev.end_date) == (dr.start, dr.end):
                return prev
            raise ScraperError(
                f"{eid} 在同一份官方文件中出現兩次且日期不同："
                f"{prev.start_date}~{prev.end_date} vs {dr.start}~{dr.end}"
            )
        ev = Event(
            id=eid,
            academic_year=self.academic_year,
            category=rule.category or self.category,
            type=rule.type,
            exam=rule.exam or self.exam,
            name=rule.name or self.exam_name,
            organizer=rule.organizer or self.organizer,
            start_date=dr.start,
            end_date=dr.end,
            source_url=self.source_url,
            source_title=self.source_title,
            note=note,
            source_text=source_text,
        )
        self.events[eid] = ev
        return ev


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def absolute_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str, str]]:
    """回傳 (絕對 URL, 解碼後 URL, 連結文字)。"""
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "#", "mailto:")):
            continue
        url = urljoin(base_url, href)
        out.append((url, unquote(url), a.get_text(" ", strip=True)))
    return out


def html_table_grid(table) -> list[list[str]]:
    """把 HTML table 展開成矩陣（處理 rowspan / colspan），每格為去空白後的文字。

    只處理該 table 自己的列（不深入巢狀 table）。
    """
    rows = []
    body_rows = table.find_all("tr")
    nested = {id(tr) for inner in table.find_all("table") for tr in inner.find_all("tr")}
    pending: dict[int, tuple[str, int]] = {}  # 欄位 → (文字, 剩餘列數)
    for tr in body_rows:
        if id(tr) in nested:
            continue
        cells = tr.find_all(["td", "th"], recursive=False)
        row: list[str] = []
        col = 0
        it = iter(cells)
        while True:
            if col in pending:
                text, left = pending[col]
                row.append(text)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (text, left - 1)
                col += 1
                continue
            cell = next(it, None)
            if cell is None:
                break
            text = cell.get_text(" ", strip=True)
            span = int(cell.get("colspan", 1) or 1)
            rspan = int(cell.get("rowspan", 1) or 1)
            for _ in range(span):
                if rspan > 1:
                    pending[col] = (text, rspan - 1)
                row.append(text)
                col += 1
        while col in pending:  # 行尾的 rowspan
            text, left = pending.pop(col)
            row.append(text)
            if left > 1:
                pending[col] = (text, left - 1)
            col += 1
        rows.append(row)
    return rows


def require_ids(result: ScrapeResult, required: tuple[str, ...]) -> None:
    ids = {e.id for e in result.events}
    missing = [r.format(y=result.academic_year) for r in required if r.format(y=result.academic_year) not in ids]
    if missing:
        raise ScraperError(
            f"[{result.source_key}] {result.academic_year} 學年度缺少必要事件：{', '.join(missing)}；"
            "官方文件格式可能已改變，請檢查 parser。"
        )
