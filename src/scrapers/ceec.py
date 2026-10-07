"""大學入學考試中心（CEEC）：高中英語聽力測驗、學科能力測驗、分科測驗。

資料來源（皆為官方）：
1. 首頁 https://www.ceec.edu.tw/ 的「XXX學年度考試簡章」區塊（div.IndexExamForm），
   用來找出最新學年度，以及「簡章」與「重要日程」兩個 file_pool PDF 連結。
   file_pool URL 每年都不同，因此一律從首頁動態取得，不寫死。
2. 簡章 PDF 第 II 頁「考試重要試務日期」矩陣表（primary）。
3. 簡章 PDF 第 I 頁「考試重要行事曆」逐行列表（同文件交叉驗證；不一致即失敗）。
4. 獨立的「重要日程」PDF（第二份官方文件，比對不一致時發出警告）。
   這份 PDF 的中文字型缺少 Unicode 對照，無法抽出中文；若簡章無法使用，
   會改用它並以 OCR 辨識列標題（OCR fallback）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..dates import DateParseError, DateRange, find_roc_dates, normalize_text, parse_roc_range
from ..fetch import FetchError, Fetcher
from ..models import Category, Event, EventType, ScrapeResult, ScraperError
from ..pdf_utils import (
    OCRUnavailable,
    has_cjk,
    largest_table,
    normalize_ocr,
    ocr_region,
    open_pdf,
    table_cells,
)
from .base import ScraperSpec, absolute_links, require_ids, soup_of, squash

HOME_URL = "https://www.ceec.edu.tw/"
ORGANIZER = "CEEC"

# (exam key, session) → 顯示名稱
EXAM_NAMES = {
    ("english-listening", 1): "高中英語聽力測驗（第一次考試）",
    ("english-listening", 2): "高中英語聽力測驗（第二次考試）",
    ("gsat", None): "學科能力測驗",
    ("ast", None): "分科測驗",
}

# 矩陣表列標題 → 事件種類。順序有意義（先比對較特定的）。
ROW_KINDS: list[tuple[str, str | None]] = [
    (r"簡章發售", "brochure"),
    (r"身心障礙|重大傷病", None),
    (r"報名結果檢核|確認報名資料", "registration-check"),
    (r"^報名$", "registration"),
    (r"試場分配表|應考資訊查詢", "seat-announcement"),
    (r"^考試$", "exam"),
    (r"參考答案", "answers"),
    (r"複查結果", "review-result"),
    (r"申請成績複查", "review"),
    (r"公布成績|開放成績查詢", "result"),
    (r"寄發成績通知單", "score-report"),
]

# OCR 模式的寬鬆比對（OCR 可能漏字，例如「報名」只辨識出「名」）
OCR_ROW_KINDS: list[tuple[str, str | None]] = [
    (r"簡章|發售", "brochure"),
    (r"身心|障|傷病", None),
    (r"檢核|名結果.?核", "registration-check"),
    (r"^[報服极]?名$", "registration"),
    (r"試場|分配|應考資|應試號", "seat-announcement"),
    (r"^考?試$", "exam"),
    (r"答案", "answers"),
    (r"查結果|複查結果", "review-result"),
    (r"申.?成績複查|^申.*複查", "review"),
    (r"公布成績|統計|成績查", "result"),
    (r"成績通知", "score-report"),
]

KIND_META: dict[str, tuple[EventType, str]] = {
    "registration": (EventType.REGISTRATION, "報名"),
    "registration-check": (EventType.OTHER, "報名結果檢核"),
    "seat-announcement": (EventType.ANNOUNCEMENT, "公布試場分配表、開放應考資訊查詢"),
    "exam": (EventType.EXAM, ""),
    "answers": (EventType.ANNOUNCEMENT, "公布選擇（填）題參考答案"),
    "result": (EventType.RESULT, "公布成績"),
    "score-report": (EventType.RESULT, "寄發成績通知單"),
    "review": (EventType.REVIEW, "申請成績複查"),
    "review-result": (EventType.REVIEW, "寄發成績複查結果通知書、開放複查結果查詢"),
}

# 行事曆（第 I 頁）的項目文字 → 事件種類
CALENDAR_KINDS: list[tuple[str, str]] = [
    (r"考試簡章發售$", "brochure"),
    (r"公布試場分配表$", "seat-announcement"),
    (r"寄發成績通知單$", "score-report"),
    (r"申請成績複查$", "review"),
    (r"公布成績$", "result"),
    (r"報名$", "registration"),
    (r"考試$", "exam"),
]


@dataclass
class CeecLinks:
    academic_year: int
    title: str
    brochure_url: str | None
    dates_url: str | None


@dataclass
class MatrixParse:
    events: dict[str, Event]
    grid_dates: list[list[DateRange | None]]
    warnings: list[str] = field(default_factory=list)


def event_id(exam: str, session: int | None, year: int, kind: str) -> str:
    if kind == "brochure":
        return f"ceec-brochure-{year}"
    base = f"ceec-{exam}-{year}" + (f"-{session}" if session else "")
    return base if kind == "exam" else f"{base}-{kind}"


# ---------------------------------------------------------------- discovery


def discover(home_html: str, base_url: str = HOME_URL) -> CeecLinks:
    """從首頁找出最新學年度與簡章／重要日程 PDF 連結。"""
    soup = soup_of(home_html)
    candidates: list[CeecLinks] = []

    for box in soup.select("div.IndexExamForm"):
        h = box.find(["h2", "h3", "h4"])
        m = re.search(r"(\d{3})\s*學年度\s*考試簡章", h.get_text(strip=True) if h else "")
        if not m:
            continue
        brochure = dates = None
        for url, _, text in absolute_links(box, base_url):
            if text == "簡章" and url.lower().endswith(".pdf"):
                brochure = url
            elif "重要日程" in text and url.lower().endswith(".pdf"):
                dates = url
        candidates.append(CeecLinks(int(m.group(1)), h.get_text(strip=True), brochure, dates))

    # 後備：全頁搜尋檔名（首頁改版時仍有機會找到）
    by_year: dict[int, CeecLinks] = {}
    for url, decoded, _ in absolute_links(soup, base_url):
        name = decoded.rsplit("/", 1)[-1]
        mb = re.fullmatch(r"(\d{3})學年度簡章\.pdf", name)
        md = re.fullmatch(r"(\d{3})學年度考試重要試務日期\.pdf", name)
        if mb or md:
            y = int((mb or md).group(1))
            link = by_year.setdefault(y, CeecLinks(y, f"{y}學年度考試簡章", None, None))
            if mb:
                link.brochure_url = url
            else:
                link.dates_url = url

    if candidates:
        best = max(candidates, key=lambda c: c.academic_year)
        fallback = by_year.get(best.academic_year)
        if fallback:
            best.brochure_url = best.brochure_url or fallback.brochure_url
            best.dates_url = best.dates_url or fallback.dates_url
        newer = [y for y in by_year if y > best.academic_year]
        if newer:
            raise ScraperError(f"CEEC 首頁簡章區塊為 {best.academic_year} 學年度，但頁面上另有更新年度 {newer} 的簡章檔案")
    elif by_year:
        best = by_year[max(by_year)]
    else:
        raise ScraperError("CEEC 首頁找不到「XXX學年度考試簡章」區塊或簡章 PDF 連結，網站結構可能已改變")

    if not best.brochure_url and not best.dates_url:
        raise ScraperError(f"CEEC {best.academic_year} 學年度找不到簡章或重要日程 PDF 連結")
    return best


# ---------------------------------------------------------------- 矩陣表


def _classify_columns(headers: list[str], ocr: bool) -> dict[int, tuple[str, int | None]]:
    cols: dict[int, tuple[str, int | None]] = {}
    for ci, h in enumerate(headers):
        h = normalize_ocr(h) if ocr else squash(h)
        if not h:
            continue
        listening = "聽力" in h or ("英語" in h and ("第一" in h or "第二" in h))
        if listening and "第一" in h:
            cols[ci] = ("english-listening", 1)
        elif listening and "第二" in h:
            cols[ci] = ("english-listening", 2)
        elif "學科" in h or "能力測" in h:
            cols[ci] = ("gsat", None)
        elif "分科" in h:
            cols[ci] = ("ast", None)
    found = sorted(cols.values(), key=str)
    expected = sorted(EXAM_NAMES, key=str)
    if found != expected:
        raise ScraperError(f"CEEC 重要試務日期表的欄位標題無法對應到四項考試：{headers}")
    return cols


def _classify_row(label: str, ocr: bool) -> tuple[bool, str | None]:
    """回傳 (是否辨識, 種類)；種類 None 代表刻意略過的列。"""
    key = normalize_ocr(label) if ocr else squash(label).replace("⚫", "").replace("●", "")
    for pattern, kind in (OCR_ROW_KINDS if ocr else ROW_KINDS):
        if re.search(pattern, key):
            return True, kind
    return False, None


def parse_matrix(
    pdf_bytes: bytes,
    page_index: int,
    academic_year: int,
    source_url: str,
    source_title: str,
    *,
    ocr: bool = False,
) -> MatrixParse:
    """解析「考試重要試務日期」矩陣表。

    ocr=True 時，表頭與列標題的中文改由 OCR 取得（日期仍來自文字層）。
    """
    with open_pdf(pdf_bytes) as pdf:
        page = pdf.pages[page_index]
        table = largest_table(page)
        if table is None:
            raise ScraperError(f"CEEC 重要試務日期頁找不到表格（{source_url}）")
        cells = table_cells(page, table)
        page_bbox = page.bbox

    def label_text(text: str, bbox) -> str:
        if not ocr or has_cjk(text) or bbox is None:
            return text
        return ocr_region(pdf_bytes, page_index, page_bbox, bbox)

    # 表頭：第一個「含日期」的列之前都是表頭
    first_data = next(
        (ri for ri, row in enumerate(cells) if any(find_roc_dates(t) for t, _ in row[1:])),
        None,
    )
    if first_data is None or first_data == 0:
        raise ScraperError("CEEC 重要試務日期表找不到日期資料列")
    ncols = len(cells[0])
    headers = []
    seen_bbox: dict[int, set] = {ci: set() for ci in range(ncols)}
    for ci in range(1, ncols):
        parts = []
        for ri in range(first_data):
            text, bbox = cells[ri][ci]
            if bbox in seen_bbox[ci]:
                continue
            seen_bbox[ci].add(bbox)
            t = label_text(text, bbox)
            if t:
                parts.append(t)
        headers.append(" ".join(parts))
    columns = {ci + 1: v for ci, v in _classify_columns(headers, ocr).items()}

    warnings: list[str] = []
    events: dict[str, Event] = {}
    grid_dates: list[list[DateRange | None]] = []
    for ri in range(first_data, len(cells)):
        row = cells[ri]
        raw_label, label_bbox = row[0]
        label = label_text(raw_label, label_bbox)
        recognised, kind = _classify_row(label, ocr)
        row_dates = [parse_roc_range(row[ci][0], f"CEEC {squash(label)} 第{ci}欄") for ci in range(1, ncols)]
        grid_dates.append(row_dates)
        if not recognised:
            if any(row_dates):
                warnings.append(f"CEEC 重要試務日期表有未對應的列：{squash(label) or '(空白)'}")
            continue
        if kind is None:
            continue
        if kind == "brochure":
            dr = next((d for d in row_dates if d), None)
            if dr:
                events[event_id("", None, academic_year, kind)] = Event(
                    id=event_id("", None, academic_year, kind),
                    academic_year=academic_year,
                    category=Category.UNIVERSITY,
                    type=EventType.ANNOUNCEMENT,
                    exam="ceec",
                    name=f"{academic_year}學年度考試簡章發售（英聽、學測、分科測驗）",
                    organizer=ORGANIZER,
                    start_date=dr.start,
                    end_date=dr.end,
                    source_url=source_url,
                    source_title=source_title,
                    source_text=f"簡章發售｜{row[1][0]}",
                )
            continue
        etype, kname = KIND_META[kind]
        for ci, (exam, session) in columns.items():
            dr = row_dates[ci - 1]
            if dr is None:
                continue
            eid = event_id(exam, session, academic_year, kind)
            exam_name = EXAM_NAMES[(exam, session)]
            ev = Event(
                id=eid,
                academic_year=academic_year,
                category=Category.UNIVERSITY,
                type=etype,
                exam=exam,
                name=f"{exam_name} {kname}".strip(),
                organizer=ORGANIZER,
                start_date=dr.start,
                end_date=dr.end,
                source_url=source_url,
                source_title=source_title,
                note="試務系統開放時間為開放日上午9時起至結束日下午5時止" if etype in (EventType.REGISTRATION, EventType.REVIEW) else None,
                source_text=f"{squash(label)}｜{squash(row[ci][0])}",
            )
            if eid in events and (events[eid].start_date, events[eid].end_date) != (dr.start, dr.end):
                raise ScraperError(f"CEEC 重要試務日期表中 {eid} 出現兩個不同日期")
            events.setdefault(eid, ev)
    return MatrixParse(events, grid_dates, warnings)


# ---------------------------------------------------------------- 行事曆（交叉驗證）

_CAL_LINE = re.compile(
    r"^(?P<dates>\d{3}\.\d{1,2}\.\d{1,2}\([一二三四五六日]\)(?:~(?:\d{3}\.)?\d{1,2}\.\d{1,2}\([一二三四五六日]\))?)\s*(?P<label>.+)$"
)


def parse_calendar_lines(text: str, academic_year: int) -> dict[str, DateRange]:
    """解析「考試重要行事曆」：每行「日期 項目」，例如「115.09.03(四)~09.10(四) 英 1 報名」。"""
    out: dict[str, DateRange] = {}
    for line in normalize_text(text).splitlines():
        line = line.strip()
        m = _CAL_LINE.match(line)
        if not m:
            continue
        label = re.sub(r"\s+", "", m.group("label"))
        dr = parse_roc_range(m.group("dates"), f"CEEC 行事曆：{line}")
        if dr is None:
            continue
        exam: tuple[str, int | None] | None = None
        if mm := re.match(r"英([12])", label):
            exam = ("english-listening", int(mm.group(1)))
            rest = label[mm.end():]
        elif label.startswith("學測"):
            exam, rest = ("gsat", None), label[2:]
        elif label.startswith("分科"):
            exam, rest = ("ast", None), re.sub(r"^分科(測驗)?", "", label)
        else:
            rest = label
        kind = next((k for p, k in CALENDAR_KINDS if re.search(p, rest)), None)
        if kind is None:
            continue
        if kind == "brochure":
            out[event_id("", None, academic_year, kind)] = dr
        elif exam:
            out[event_id(exam[0], exam[1], academic_year, kind)] = dr
    return out


def compare_with_calendar(events: dict[str, Event], calendar: dict[str, DateRange]) -> list[str]:
    errors = []
    for eid, dr in calendar.items():
        ev = events.get(eid)
        if ev is None:
            errors.append(f"行事曆有 {eid}（{dr.start}~{dr.end}），重要試務日期表卻沒有")
        elif (ev.start_date, ev.end_date) != (dr.start, dr.end):
            errors.append(f"{eid}：重要試務日期表 {ev.start_date}~{ev.end_date}，行事曆 {dr.start}~{dr.end}")
    return errors


# ---------------------------------------------------------------- 獨立「重要日程」PDF


def matrix_dates_only(pdf_bytes: bytes) -> list[list[DateRange | None]]:
    """只取矩陣表的日期格（不需要中文），用於與簡章表格逐格比對。"""
    with open_pdf(pdf_bytes) as pdf:
        page = pdf.pages[0]
        table = largest_table(page)
        if table is None:
            raise ScraperError("重要日程 PDF 找不到表格")
        cells = table_cells(page, table)
    rows = []
    started = False
    for row in cells:
        dates = [parse_roc_range(t) for t, _ in row[1:]]
        if any(dates):
            started = True
        if started:
            rows.append(dates)
    return rows


def compare_grids(a: list[list[DateRange | None]], b: list[list[DateRange | None]]) -> list[str]:
    if len(a) != len(b) or any(len(x) != len(y) for x, y in zip(a, b, strict=True)):
        return [f"表格結構不同（{len(a)} 列 vs {len(b)} 列），略過逐格比對"]
    diffs = []
    for ri, (ra, rb) in enumerate(zip(a, b, strict=True)):
        for ci, (da, db) in enumerate(zip(ra, rb, strict=True)):
            if da != db:
                diffs.append(f"第{ri + 1}列第{ci + 1}欄：簡章 {da} vs 重要日程 {db}")
    return diffs


# ---------------------------------------------------------------- 主流程


def _find_pages(pdf_bytes: bytes, max_pages: int = 12) -> tuple[int | None, int | None, int | None]:
    """回傳 (矩陣表頁, 行事曆頁, 頁面標示的學年度)。"""
    matrix = calendar = year = None
    with open_pdf(pdf_bytes) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            text = squash(page.extract_text() or "")
            if matrix is None and (m := re.search(r"(\d{3})學年度考試重要試務日期", text)):
                matrix, year = i, int(m.group(1))
            if calendar is None and "重要行事曆" in text:
                calendar = i
            if matrix is not None and calendar is not None:
                break
    return matrix, calendar, year


def scrape(fetcher: Fetcher) -> list[ScrapeResult]:
    home = fetcher.get(HOME_URL)
    links = discover(home.text(), home.url)
    y = links.academic_year
    result = ScrapeResult(
        source_key="ceec",
        name="大學入學考試中心",
        organizer=ORGANIZER,
        academic_year=y,
        source_url=links.brochure_url or links.dates_url or HOME_URL,
        source_title=links.title,
        id_prefixes=("ceec-",),
    )

    events: dict[str, Event] | None = None
    brochure_grid = None
    brochure_error = None
    if links.brochure_url:
        try:
            pdf = fetcher.get(links.brochure_url).expect_pdf()
            matrix_page, calendar_page, page_year = _find_pages(pdf)
            if matrix_page is None:
                raise ScraperError("簡章 PDF 前 12 頁找不到「考試重要試務日期」表（可能缺少文字層）")
            if page_year != y:
                raise ScraperError(f"簡章內頁標示 {page_year} 學年度，與首頁 {y} 學年度不一致")
            title = f"{y}學年度考試簡章（考試重要試務日期）"
            parsed = parse_matrix(pdf, matrix_page, y, links.brochure_url, title)
            result.warnings += parsed.warnings
            events, brochure_grid = parsed.events, parsed.grid_dates
            if calendar_page is None:
                result.warnings.append("簡章找不到「考試重要行事曆」頁，略過同文件交叉驗證")
            else:
                with open_pdf(pdf) as doc:
                    cal_text = doc.pages[calendar_page].extract_text() or ""
                calendar = parse_calendar_lines(cal_text, y)
                if len(calendar) < 10:
                    raise ScraperError(f"簡章行事曆只解析出 {len(calendar)} 筆，格式可能改變")
                errors = compare_with_calendar(events, calendar)
                if errors:
                    raise ScraperError("簡章內「重要試務日期」與「重要行事曆」不一致：\n" + "\n".join(errors))
        except (FetchError, ScraperError) as exc:
            brochure_error = exc

    if links.dates_url:
        try:
            dates_pdf = fetcher.get(links.dates_url).expect_pdf()
        except FetchError as exc:
            result.warnings.append(f"無法下載重要日程 PDF：{exc}")
            dates_pdf = None
        if dates_pdf is not None and brochure_grid is not None:
            try:
                diffs = compare_grids(brochure_grid, matrix_dates_only(dates_pdf))
            except (ScraperError, DateParseError) as exc:
                diffs = [f"重要日程 PDF 解析失敗：{exc}"]
            result.warnings += [f"簡章與獨立重要日程 PDF 不一致：{d}" for d in diffs]
        elif dates_pdf is not None and events is None:
            # OCR fallback：簡章不可用時，改用獨立重要日程 PDF，列標題以 OCR 辨識
            try:
                title = f"{y}學年度考試重要試務日期（OCR）"
                parsed = parse_matrix(dates_pdf, 0, y, links.dates_url, title, ocr=True)
                events = parsed.events
                result.source_url = links.dates_url
                result.warnings += parsed.warnings
                result.warnings.append(f"簡章無法使用（{brochure_error}），已改用重要日程 PDF + OCR")
            except OCRUnavailable as exc:
                raise ScraperError(f"簡章無法使用（{brochure_error}），且 OCR fallback 不可用：{exc}") from exc

    if events is None:
        raise ScraperError(f"CEEC {y} 學年度日程解析失敗：{brochure_error or '找不到可用的官方 PDF'}")

    result.events = list(events.values())
    require_ids(result, SPEC.required)
    return [result]


SPEC = ScraperSpec(
    key="ceec",
    name="大學入學考試中心（CEEC）",
    organizer=ORGANIZER,
    exams="高中英語聽力測驗、學科能力測驗、分科測驗",
    homepage=HOME_URL,
    run=scrape,
    required=(
        "ceec-english-listening-{y}-1",
        "ceec-english-listening-{y}-1-registration",
        "ceec-english-listening-{y}-2",
        "ceec-english-listening-{y}-2-registration",
        "ceec-gsat-{y}",
        "ceec-gsat-{y}-registration",
        "ceec-gsat-{y}-result",
        "ceec-ast-{y}",
        "ceec-ast-{y}-registration",
        "ceec-ast-{y}-result",
    ),
    min_events=20,
)
