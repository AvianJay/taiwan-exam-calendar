"""國中教育會考（CAP）與國中升高中職／五專「適性入學」重要日程。

資料來源（官方）：
1. 會考網站首頁 https://cap.rcpet.edu.tw/ 的「XXX學年度國中教育會考及全國高級中等學校
   與專科學校五年制適性入學重要日程表(PDF)」——由教育部國教署函頒。
2. 會考網站「歷史訊息」中「XXX年國中教育會考考試日期訂於…」公告（交叉驗證用）。

日程表 PDF 為「月份區塊 × (日, 星期, 辦理事項)」的雙欄版面，且**不印年份**。
解析方式：
- 以「辦理事項」表頭定位每個月份區塊與欄位位置；
- 以橫跨「辦理事項」欄的格線切出每一列（同一列可能涵蓋多天，例如 15、16 日）；
- 以每個區塊內印出的「星期」反推西元年（不使用學年度 + 1911 硬算）；
- 項目若自帶日期（例如「4日-6日：國中教育會考報名」）以項目日期為準，
  且其起始日必須落在該列的日期內，否則視為版面解析錯誤。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from itertools import pairwise

from ..dates import DateRange, infer_year_from_weekdays, make_date, normalize_text, roc_date
from ..fetch import FetchError, Fetcher
from ..models import Category, CrossCheck, Event, EventType, ScrapeResult, ScraperError
from ..pdf_utils import open_pdf, region_text, region_words, rule_ys_spanning, thin_rules
from .base import EventBuilder, Rule, ScraperSpec, absolute_links, match_rule, require_ids, soup_of, squash, tidy

HOME_URL = "https://cap.rcpet.edu.tw/"
HISTORY_URL = "https://cap.rcpet.edu.tw/history.html"

E = EventType
_K12 = dict(category=Category.HIGH_SCHOOL, organizer="K12EA")

# suffix 以 "k12ea:" 開頭者屬於適性入學（id 前綴 k12ea-{y}），其餘屬於會考（cap-{y}）。
RULES: list[Rule] = [
    Rule(r"^國中教育會考報名$", "registration", E.REGISTRATION, "國中教育會考 報名"),
    Rule(r"寄發國中教育會考准考證", "admission-ticket", E.ANNOUNCEMENT, "國中教育會考 寄發准考證"),
    Rule(r"^國中教育會考$", "", E.EXAM, "國中教育會考"),
    Rule(r"^國中教育會考補考$", "make-up", E.EXAM, "國中教育會考 補考"),
    Rule(r"寄發國中教育會考成績通知單", "result", E.RESULT, "國中教育會考 寄發成績通知單並開放網路查詢"),
    Rule(r"國中教育會考.*複查", "review", E.REVIEW, "國中教育會考 成績複查"),
    # ---- 適性入學（國教署）
    Rule(r"各就學區免試入學開放個人序位查詢及志願選填", "k12ea:free-admission-choice-open", E.ADMISSION,
         "免試入學 開放個人序位查詢及志願選填", exam="free-admission", **_K12),
    Rule(r"志願選填截止", "k12ea:free-admission-choice-deadline", E.ADMISSION,
         "免試入學及特色招生考試分發入學 志願選填截止", exam="free-admission", **_K12),
    Rule(r"免試入學、?特色招生考試分發入學報名截止", "k12ea:free-admission-registration-deadline", E.REGISTRATION,
         "免試入學、特色招生考試分發入學 報名截止", exam="free-admission", **_K12),
    Rule(r"各就學區免試入學公告實際招生名額", "k12ea:free-admission-quota", E.ANNOUNCEMENT,
         "免試入學 公告實際招生名額", exam="free-admission", **_K12),
    Rule(r"^各就學區免試入學及特色招生考試分發入學放榜$", "k12ea:free-admission-release", E.ADMISSION,
         "免試入學及特色招生考試分發入學 放榜", exam="free-admission", **_K12),
    Rule(r"^各就學區免試入學及特色招生考試分發入學報到$", "k12ea:free-admission-enrollment", E.ADMISSION,
         "免試入學及特色招生考試分發入學 報到", exam="free-admission", **_K12),
    Rule(r"^免試入學變更就學區申請$", "k12ea:free-admission-district-change", E.OTHER,
         "免試入學 變更就學區申請", exam="free-admission", **_K12),
    Rule(r"^各就學區辦理優先免試入學開始日$", "k12ea:priority-admission-start", E.ADMISSION,
         "優先免試入學 開始", exam="priority-admission", **_K12),
    Rule(r"^各就學區優先免試入學放榜", "k12ea:priority-admission-release", E.ADMISSION,
         "優先免試入學 放榜、報到截止", exam="priority-admission", **_K12),
    Rule(r"^特色招生考試分發入學學科測驗報名$", "k12ea:special-exam-registration", E.REGISTRATION,
         "特色招生考試分發入學 學科測驗報名", exam="special-exam", **_K12),
    Rule(r"^特色招生考試分發入學學科測驗$", "k12ea:special-exam", E.EXAM,
         "特色招生考試分發入學 學科測驗", exam="special-exam", **_K12),
    Rule(r"特色招生考試分發入學開放網路查詢學科測驗分數", "k12ea:special-exam-result", E.RESULT,
         "特色招生考試分發入學 學科測驗分數查詢", exam="special-exam", **_K12),
    Rule(r"^特色招生專業群科甄選入學報名$", "k12ea:vocational-special-registration", E.REGISTRATION,
         "特色招生專業群科甄選入學 報名", exam="vocational-special", **_K12),
    Rule(r"^特色招生專業群科甄選入學術科測驗$", "k12ea:vocational-special-exam", E.EXAM,
         "特色招生專業群科甄選入學 術科測驗", exam="vocational-special", **_K12),
    Rule(r"^特色招生專業群科甄選入學放榜$", "k12ea:vocational-special-release", E.ADMISSION,
         "特色招生專業群科甄選入學 放榜", exam="vocational-special", **_K12),
    Rule(r"^五專優先免試入學報名$", "k12ea:five-year-priority-registration", E.REGISTRATION,
         "五專優先免試入學 報名", exam="five-year", **_K12),
    Rule(r"^五專優先免試入學放榜$", "k12ea:five-year-priority-release", E.ADMISSION,
         "五專優先免試入學 放榜", exam="five-year", **_K12),
    Rule(r"^五專完全免試入學報名$", "k12ea:five-year-full-registration", E.REGISTRATION,
         "五專完全免試入學 報名", exam="five-year", **_K12),
    Rule(r"^五專完全免試入學放榜$", "k12ea:five-year-full-release", E.ADMISSION,
         "五專完全免試入學 放榜", exam="five-year", **_K12),
    Rule(r"^五專聯合免試入學報名$", "k12ea:five-year-joint-registration", E.REGISTRATION,
         "五專聯合免試入學 報名", exam="five-year", **_K12),
    Rule(r"^技優甄審入學報名$", "k12ea:skill-registration", E.REGISTRATION,
         "技優甄審入學（高中職） 報名", exam="skill-admission", **_K12),
    Rule(r"^技優甄審入學放榜$", "k12ea:skill-release", E.ADMISSION,
         "技優甄審入學（高中職） 放榜", exam="skill-admission", **_K12),
    Rule(r"^各校直升入學報名$", "k12ea:direct-promotion-registration", E.REGISTRATION,
         "各校直升入學 報名", exam="direct-promotion", **_K12),
    Rule(r"^學習區完全免試入學報名$", "k12ea:learning-area-registration", E.REGISTRATION,
         "學習區完全免試入學 報名", exam="learning-area", **_K12),
    Rule(r"^學習區完全免試入學放榜$", "k12ea:learning-area-release", E.ADMISSION,
         "學習區完全免試入學 放榜", exam="learning-area", **_K12),
    Rule(r"^科學班甄選入學報名$", "k12ea:science-class-registration", E.REGISTRATION,
         "科學班甄選入學 報名", exam="science-class", **_K12),
    Rule(r"^科學班甄選入學科學能力檢定$", "k12ea:science-class-exam", E.EXAM,
         "科學班甄選入學 科學能力檢定", exam="science-class", **_K12),
    Rule(r"^藝才班甄選入學.*術科測驗報名$", "k12ea:art-class-registration", E.REGISTRATION,
         "藝才班甄選入學 術科測驗報名", exam="art-class", **_K12),
    Rule(r"^體育班甄選入學術科測驗報名$", "k12ea:sports-class-registration", E.REGISTRATION,
         "體育班甄選入學 術科測驗報名", exam="sports-class", **_K12),
    Rule(r"^體育班甄選入學術科測驗$", "k12ea:sports-class-exam", E.EXAM,
         "體育班甄選入學 術科測驗", exam="sports-class", **_K12),
    Rule(r"^建教合作班報名開始日$", "k12ea:coop-class-registration-start", E.REGISTRATION,
         "建教合作班 報名開始", exam="coop-class", **_K12),
]

_ITEM_DATE = re.compile(
    r"^(?:(?P<m1>\d{1,2})月)?(?P<d1>\d{1,2})日(?:[-~至](?:(?P<m2>\d{1,2})月)?(?P<d2>\d{1,2})日)?[:：]"
)


@dataclass
class Row:
    month: int
    days: list[tuple[int, str]]  # (日, 星期)
    lines: list[str]
    half: int


@dataclass
class Item:
    start: tuple[int, int]  # (月, 日)
    end: tuple[int, int]
    text: str
    row: Row


# ---------------------------------------------------------------- discovery


def discover(html: str, base_url: str) -> tuple[int, str, str] | None:
    best: tuple[int, str, str] | None = None
    for url, decoded, text in absolute_links(soup_of(html), base_url):
        hay = f"{text} {decoded.rsplit('/', 1)[-1]}"
        m = re.search(r"(\d{3})學年度國中教育會考.*?重要日程表", hay)
        if m and decoded.lower().endswith(".pdf"):
            y = int(m.group(1))
            title = re.sub(r"\(PDF\)$", "", text).strip() or decoded.rsplit("/", 1)[-1]
            if best is None or y > best[0]:
                best = (y, url, title)
    return best


# ---------------------------------------------------------------- 版面解析


def _nearest_left(words: list[dict], text: str, right: float) -> dict | None:
    cands = [w for w in words if w["text"] == text and w["x1"] <= right + 0.5]
    return max(cands, key=lambda w: w["x1"]) if cands else None


def _header_columns(page) -> list[dict]:
    """找出每個「月 日 星期 辦理事項」表頭與欄位 x 範圍。"""
    words = page.extract_words()
    headers = []
    for h in (w for w in words if w["text"] == "辦理事項"):
        same = [w for w in words if abs(w["top"] - h["top"]) < 3 and w["x1"] <= h["x0"]]

        wk = _nearest_left(same, "星期", h["x0"])
        dy = _nearest_left(same, "日", wk["x0"]) if wk else None
        mo = _nearest_left(same, "月", dy["x0"]) if dy else None
        if not (wk and dy and mo):
            raise ScraperError("會考日程表表頭缺少「月／日／星期」欄，版面可能已改變")
        headers.append({
            "top": h["top"], "bottom": h["bottom"],
            "month_x0": mo["x0"] - 8, "day_x0": (mo["x1"] + dy["x0"]) / 2,
            "wd_x0": (dy["x1"] + wk["x0"]) / 2, "text_x0": wk["x1"] + 1.5,
        })
    if not headers:
        raise ScraperError("會考日程表找不到「辦理事項」表頭，版面可能已改變")
    return headers


def extract_rows(page) -> list[Row]:
    headers = _header_columns(page)
    # 依 x 位置分成左右兩半（或更多欄）
    halves: list[list[dict]] = []
    for h in sorted(headers, key=lambda h: h["month_x0"]):
        if halves and abs(halves[-1][0]["month_x0"] - h["month_x0"]) < 30:
            halves[-1].append(h)
        else:
            halves.append([h])
    hrules, _ = thin_rules(page)
    rows: list[Row] = []
    for hi, group in enumerate(halves):
        right = halves[hi + 1][0]["month_x0"] - 2 if hi + 1 < len(halves) else page.bbox[2]
        group.sort(key=lambda h: h["top"])
        text_x0 = group[0]["text_x0"]
        ys = rule_ys_spanning(hrules, text_x0, text_x0 + 0.85 * (right - text_x0), tol=6)
        for bi, h in enumerate(group):
            block_top = h["bottom"]
            block_bottom = group[bi + 1]["top"] if bi + 1 < len(group) else page.bbox[3]
            month_text = region_text(page, (h["month_x0"], block_top, h["day_x0"], block_bottom))
            mm = re.search(r"(\d{1,2})", month_text)
            if not mm or not 1 <= int(mm.group(1)) <= 12:
                raise ScraperError(f"會考日程表區塊無法辨識月份：{month_text!r}")
            month = int(mm.group(1))
            band_ys = [y for y in ys if block_top - 1 <= y <= block_bottom + 1]
            for y0, y1 in pairwise(band_ys):
                days = [w for w in region_words(page, (h["day_x0"], y0, h["wd_x0"], y1)) if w["text"].isdigit()]
                if not days:
                    continue
                wds = [w for w in region_words(page, (h["wd_x0"], y0, h["text_x0"], y1))
                       if w["text"] in "一二三四五六日"]
                if len(wds) != len(days):
                    raise ScraperError(f"會考日程表 {month} 月某列的日期與星期數量不符（{[d['text'] for d in days]}）")
                pairs = []
                for d in sorted(days, key=lambda w: w["top"]):
                    wd = min(wds, key=lambda w: abs(w["top"] - d["top"]))
                    pairs.append((int(d["text"]), wd["text"]))
                text = region_text(page, (text_x0, y0, right, y1))
                lines = [ln.strip() for ln in normalize_text(text).splitlines() if ln.strip() and ln.strip() != "…"]
                rows.append(Row(month, pairs, lines, hi))
    return rows


def split_items(row: Row) -> list[Item]:
    """一列可能有多個編號項目（1. 2. 3.），並處理換行接續。"""
    chunks: list[str] = []
    for ln in row.lines:
        if re.match(r"^\d+\.\s*", ln) or not chunks:
            chunks.append(re.sub(r"^\d+\.\s*", "", ln))
        else:
            chunks[-1] += ln
    items = []
    row_days = [(row.month, d) for d, _ in row.days]
    for chunk in chunks:
        text = squash(chunk)
        m = _ITEM_DATE.match(text)
        if m:
            m1 = int(m.group("m1") or row.month)
            d1 = int(m.group("d1"))
            m2 = int(m.group("m2") or m1)
            d2 = int(m.group("d2") or d1)
            if (m1, d1) not in row_days:
                raise ScraperError(
                    f"會考日程表項目「{chunk}」自帶日期 {m1}/{d1}，但所在列的日期是 {row_days}；版面解析可能錯位"
                )
            items.append(Item((m1, d1), (m2, d2), text[m.end():], row))
        else:
            items.append(Item(row_days[0], row_days[-1], text, row))
    return items


def resolve_years(rows: list[Row], academic_year: int) -> dict[tuple[int, int], int]:
    """以星期反推每個 (欄, 月份) 區塊的西元年。"""
    blocks: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
    for r in rows:
        blocks.setdefault((r.half, r.month), []).extend((r.month, d, w) for d, w in r.days)
    base = academic_year + 1911
    candidates = [base - 1, base, base + 1]
    return {
        key: infer_year_from_weekdays(entries, candidates, f"會考日程表 {key[1]} 月")
        for key, entries in blocks.items()
    }


def parse_schedule(pdf_bytes: bytes, academic_year: int, source_url: str, source_title: str
                   ) -> tuple[list[Event], list[str]]:
    with open_pdf(pdf_bytes) as pdf:
        page = pdf.pages[0]
        text = squash(page.extract_text() or "")
        m = re.search(r"(\d{3})學年度國中教育會考", text)
        if not m or int(m.group(1)) != academic_year:
            raise ScraperError(f"會考日程表標題學年度與連結不一致（{m.group(1) if m else '找不到'} vs {academic_year}）")
        rows = extract_rows(page)
    if len(rows) < 15:
        raise ScraperError(f"會考日程表只解析出 {len(rows)} 列，版面可能已改變")
    years = resolve_years(rows, academic_year)

    cap = EventBuilder(academic_year, f"cap-{academic_year}", Category.JUNIOR_HIGH, "CAP", "cap",
                       "國中教育會考", source_url, source_title)
    k12 = EventBuilder(academic_year, f"k12ea-{academic_year}", Category.HIGH_SCHOOL, "K12EA", "admission",
                       "適性入學", source_url, source_title)
    skipped: list[str] = []
    for row in rows:
        year = years[(row.half, row.month)]
        for item in split_items(row):
            start = make_date(year, *item.start, context=item.text)
            end_year = year + 1 if item.end < item.start else year
            end = make_date(end_year, *item.end, context=item.text)
            rule = match_rule(RULES, item.text)
            if rule is None or rule.suffix is None:
                skipped.append(f"{start.isoformat()} {tidy(item.text)}")
                continue
            dr = DateRange(start, end)
            source_text = f"{row.month}月 {','.join(f'{d}({w})' for d, w in row.days)}｜{item.text}"
            if rule.suffix.startswith("k12ea:"):
                k12.add(replace(rule, suffix=rule.suffix.split(":", 1)[1]), dr, source_text=source_text)
            else:
                cap.add(rule, dr, source_text=source_text)
    return list(cap.events.values()) + list(k12.events.values()), skipped


# ---------------------------------------------------------------- 交叉驗證


def parse_history_cross_checks(html: str, academic_year: int, url: str) -> list[CrossCheck]:
    """「116年國中教育會考考試日期訂於116年5月15、16日(星期六、日)」→ cap-116 的宣稱。"""
    text = squash(soup_of(html).get_text(" "))
    checks = []
    pat = re.compile(
        r"(?P<y>\d{3})年國中教育會考考試日期訂於(?P<ry>\d{3})年(?P<m>\d{1,2})月(?P<d1>\d{1,2})日?"
        r"(?:[、,~-](?P<d2>\d{1,2}))?日"
    )
    for m in pat.finditer(text):
        if int(m.group("y")) != academic_year:
            continue
        ry, mo, d1 = int(m.group("ry")), int(m.group("m")), int(m.group("d1"))
        d2 = int(m.group("d2") or d1)
        checks.append(CrossCheck(f"cap-{academic_year}", roc_date(ry, mo, d1), roc_date(ry, mo, d2), url,
                                 "會考網站歷史訊息公告之考試日期"))
    return checks


def scrape(fetcher: Fetcher) -> list[ScrapeResult]:
    home = fetcher.get(HOME_URL)
    found = discover(home.text(), home.url)
    history_html = None
    try:
        history = fetcher.get(HISTORY_URL)
        history_html = history.text()
    except FetchError:
        pass
    if found is None and history_html:
        found = discover(history_html, HISTORY_URL)
    if found is None:
        raise ScraperError("會考網站首頁與歷史訊息都找不到「學年度…重要日程表」PDF 連結")
    year, url, title = found
    pdf = fetcher.get(url).expect_pdf()
    events, skipped = parse_schedule(pdf, year, url, title)
    result = ScrapeResult(
        source_key="cap",
        name="國中教育會考／適性入學",
        organizer="CAP",
        academic_year=year,
        source_url=url,
        source_title=title,
        id_prefixes=("cap-", "k12ea-"),
        events=events,
        skipped_items=skipped,
    )
    if history_html:
        result.cross_checks = parse_history_cross_checks(history_html, year, HISTORY_URL)
    else:
        result.warnings.append("無法取得會考歷史訊息頁，略過考試日期交叉驗證")
    require_ids(result, SPEC.required)
    return [result]


SPEC = ScraperSpec(
    key="cap",
    name="國中教育會考（CAP）／國中適性入學",
    organizer="CAP",
    exams="國中教育會考、免試入學、特色招生、五專入學等",
    homepage=HOME_URL,
    run=scrape,
    required=("cap-{y}", "cap-{y}-registration", "cap-{y}-result"),
    min_events=10,
)
