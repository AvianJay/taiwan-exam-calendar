"""技職體系：統一入學測驗（TCTE）與技專校院招生委員會聯合會（JCTV）各招生管道。

資料來源（皆為官方）：
- 統測：技專校院入學測驗中心「四技二專資訊」頁的「XXX學年度四技二專統一入學測驗重要日程表」
  （HTML 表格）。
- 四技二專甄選入學、技優甄審、日間部聯合登記分發：JCTV 各管道網站「重要日程」頁所連結的
  「招生重要日程表(簡章版)」PDF。學年度由各管道首頁標題取得；若最新學年度尚未公布日程
  （頁面顯示「目前尚無資訊」），退回上一學年度並記錄警告。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit

from ..dates import extract_time_note, parse_roc_range, strip_side_notes
from ..fetch import Fetcher
from ..models import Category, CrossCheck, EventType, ScrapeResult, ScraperError
from ..pdf_utils import open_pdf, ruled_table_rows
from .base import (
    CrossRule,
    EventBuilder,
    Rule,
    ScraperSpec,
    absolute_links,
    html_table_grid,
    match_rule,
    require_ids,
    soup_of,
    squash,
    tidy,
)

E = EventType

# ====================================================================== TCTE 統測

TCTE_URL = "https://www.tcte.edu.tw/index.php?mod=TVETest/info4y"

TCTE_RULES: list[Rule] = [
    Rule(r"報名費繳費", None),
    Rule(r"^報名$", "registration", E.REGISTRATION, "四技二專統一入學測驗 報名"),
    Rule(r"報名結果網路查詢及確認", "registration-check", E.OTHER, "四技二專統一入學測驗 報名結果網路查詢及確認"),
    Rule(r"寄發准考證", "admission-ticket", E.ANNOUNCEMENT, "四技二專統一入學測驗 寄發准考證"),
    Rule(r"考試地點公告", "seat-announcement", E.ANNOUNCEMENT, "四技二專統一入學測驗 考試地點公告與查詢"),
    Rule(r"^統一入學測驗考試$|^統測考試$", "", E.EXAM, "四技二專統一入學測驗（統測）"),
    Rule(r"公布參考答案", "answers", E.ANNOUNCEMENT, "四技二專統一入學測驗 公布參考答案"),
    Rule(r"成績複查結果查詢", "review-result", E.REVIEW, "四技二專統一入學測驗 成績複查結果查詢"),
    Rule(r"申請成績複查", "review", E.REVIEW, "四技二專統一入學測驗 申請成績複查"),
    Rule(r"成績單寄發", "score-report", E.RESULT, "四技二專統一入學測驗 成績單寄發"),
    Rule(r"成績公告與查詢成績查詢$", "result", E.RESULT, "四技二專統一入學測驗 成績公告與查詢"),
]


def parse_tcte(html: str, url: str) -> tuple[int, str, list[tuple[str, str]]]:
    """回傳 (學年度, 標題, [(項目, 日期文字)])。"""
    soup = soup_of(html)
    heading = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "caption", "p", "div", "span"]):
        text = tag.get_text(strip=True)
        if re.fullmatch(r"\d{3}學年度四技二專統一入學測驗重要日程表", text):
            heading = tag
            break
    if heading is None:
        raise ScraperError(f"統測網站找不到「XXX學年度四技二專統一入學測驗重要日程表」標題（{url}）")
    title = heading.get_text(strip=True)
    year = int(title[:3])
    table = heading.find_next("table")
    if table is None:
        raise ScraperError("統測重要日程表標題之後找不到表格")
    grid = html_table_grid(table)
    if not grid or "重要日程" not in "".join(grid[0]):
        raise ScraperError(f"統測重要日程表表頭不符：{grid[:1]}")
    rows = []
    for row in grid[1:]:
        if len(row) < 2:
            continue
        labels = []
        for cell in row[:-1]:
            if cell and cell not in labels:
                labels.append(cell)
        rows.append(("".join(labels), row[-1]))
    return year, title, rows


def scrape_tcte(fetcher: Fetcher) -> list[ScrapeResult]:
    resp = fetcher.get(TCTE_URL)
    year, title, rows = parse_tcte(resp.text(), resp.url)
    builder = EventBuilder(year, f"tech-test-{year}", Category.TECHNICAL, "TCTE", "tcte",
                           "四技二專統一入學測驗", TCTE_URL, title)
    skipped = []
    for label, date_text in rows:
        dr = parse_roc_range(strip_side_notes(date_text), f"統測 {label}")
        rule = match_rule(TCTE_RULES, label)
        if dr is None:
            continue
        if rule is None or rule.suffix is None:
            skipped.append(f"{dr.start.isoformat()} {tidy(label)}")
            continue
        builder.add(rule, dr, source_text=f"{tidy(label)}｜{tidy(date_text)}", note=extract_time_note(date_text))
    result = ScrapeResult(
        source_key="tcte", name="技專校院入學測驗中心", organizer="TCTE", academic_year=year,
        source_url=TCTE_URL, source_title=title, id_prefixes=("tech-test-",),
        events=list(builder.events.values()), skipped_items=skipped,
    )
    require_ids(result, TCTE_SPEC.required)
    return [result]


TCTE_SPEC = ScraperSpec(
    key="tcte",
    name="技專校院入學測驗中心（TCTE）",
    organizer="TCTE",
    exams="四技二專統一入學測驗（統測）",
    homepage="https://www.tcte.edu.tw/",
    run=scrape_tcte,
    required=("tech-test-{y}", "tech-test-{y}-registration", "tech-test-{y}-result"),
    min_events=5,
)

# ====================================================================== JCTV

JCTV_BASE = "https://www.jctv.ntut.edu.tw/"
PDF_COLUMNS = {"date": ("日期",), "item": ("作業項目", "項目"), "note": ("備註",)}


@dataclass(frozen=True)
class JctvChannel:
    key: str
    path: str
    exam: str
    name: str
    link_pattern: str  # 「重要日程」頁中 PDF 連結文字
    rules: tuple[Rule, ...]
    cross_rules: tuple[CrossRule, ...]
    required: tuple[str, ...]


_TECH_CROSS = (
    CrossRule(r"統一入學測驗\(?統測\)?報名|統一入學測驗報名|報名四技二專統一入學測驗", "tech-test-{y}-registration"),
    CrossRule(r"參加四技二專統一入學測驗.*考試|^四技二專統一入學測驗$", "tech-test-{y}"),
)

APPLY = JctvChannel(
    key="jctv-apply",
    path="enter42/apply",
    exam="tvet-apply",
    name="四技二專甄選入學",
    link_pattern=r"招生重要日程表.*簡章版",
    rules=(
        Rule(r"簡章網路公告", "brochure", E.ANNOUNCEMENT, "四技二專甄選入學 簡章網路公告與下載"),
        Rule(r"第一階段考生個別報名", "registration", E.REGISTRATION, "四技二專甄選入學 第一階段個別報名"),
        Rule(r"第一階段學校集體報名", "group-registration", E.REGISTRATION, "四技二專甄選入學 第一階段學校集體報名及繳費"),
        Rule(r"第一階段篩選結果.*複查", "screening-review", E.REVIEW, "四技二專甄選入學 第一階段篩選結果複查"),
        Rule(r"第一階段篩選結果公告", "screening-result", E.RESULT, "四技二專甄選入學 第一階段篩選結果公告"),
        Rule(r"第二階段報名", "stage2-registration", E.REGISTRATION, "四技二專甄選入學 第二階段報名（含學習歷程備審資料上傳）"),
        Rule(r"辦理第二階段指定項目甄試", "stage2-exam", E.EXAM, "四技二專甄選入學 第二階段指定項目甄試（日期各校自訂）"),
        Rule(r"查詢甄選總成績", "stage2-result", E.RESULT, "四技二專甄選入學 甄選總成績查詢"),
        Rule(r"甄選總成績複查", "stage2-review", E.REVIEW, "四技二專甄選入學 甄選總成績複查"),
        Rule(r"公告錄取正\(備\)取生名單", "admission-list", E.ADMISSION, "四技二專甄選入學 公告正（備）取生名單"),
        Rule(r"登記就讀志願序", "preference-registration", E.ADMISSION, "四技二專甄選入學 登記就讀志願序"),
        Rule(r"統一分發放榜", "release", E.ADMISSION, "四技二專甄選入學 統一分發放榜"),
        Rule(r"統一分發結果複查", "release-review", E.REVIEW, "四技二專甄選入學 統一分發結果複查"),
        Rule(r"分發錄取生.*報到", "enrollment", E.ADMISSION, "四技二專甄選入學 報到", exclude=r"函告"),
    ),
    cross_rules=_TECH_CROSS,
    required=("jctv-apply-{y}-registration", "jctv-apply-{y}-release"),
)

SKILL = JctvChannel(
    key="jctv-skill",
    path="enter42/skill",
    exam="tvet-skill",
    name="四技二專技優甄審入學",
    link_pattern=r"甄審招生重要日程表",
    rules=(
        Rule(r"簡章網路公告", "brochure", E.ANNOUNCEMENT, "四技二專技優甄審 簡章網路公告與下載"),
        Rule(r"資格審查結果.*複查", None),
        Rule(r"繳交報名費.*資格審查", "eligibility-registration", E.REGISTRATION, "四技二專技優甄審 繳交報名費及資格審查登錄"),
        Rule(r"資格審查結果查詢", "eligibility-result", E.ANNOUNCEMENT, "四技二專技優甄審 資格審查結果查詢"),
        Rule(r"^網路報名$", "registration", E.REGISTRATION, "四技二專技優甄審 網路報名"),
        Rule(r"辦理指定項目甄審$", "exam", E.EXAM, "四技二專技優甄審 指定項目甄審（日期各校自訂）"),
        Rule(r"查詢甄審總成績", "result", E.RESULT, "四技二專技優甄審 甄審總成績查詢"),
        Rule(r"甄審總成績複查", "result-review", E.REVIEW, "四技二專技優甄審 甄審總成績複查"),
        Rule(r"公告甄審結果", "admission-list", E.ADMISSION, "四技二專技優甄審 公告正取生、備取生名單"),
        Rule(r"登記就讀志願序", "preference-registration", E.ADMISSION, "四技二專技優甄審 登記就讀志願序"),
        Rule(r"統一分發放榜", "release", E.ADMISSION, "四技二專技優甄審 統一分發放榜"),
        Rule(r"統一分發複查", "release-review", E.REVIEW, "四技二專技優甄審 統一分發複查"),
        Rule(r"報到或聲明放棄錄取", "enrollment", E.ADMISSION, "四技二專技優甄審 報到或聲明放棄錄取"),
    ),
    cross_rules=(),
    required=("jctv-skill-{y}-registration", "jctv-skill-{y}-release"),
)

UNION = JctvChannel(
    key="jctv-union",
    path="union42",
    exam="tvet-union",
    name="四技二專日間部聯合登記分發",
    link_pattern=r"招生重要日程表.*簡章版",
    rules=(
        Rule(r"簡章網路公告", "brochure", E.ANNOUNCEMENT, "四技二專聯合登記分發 簡章網路公告與下載"),
        Rule(r"個別登記資格.*審查登錄", "eligibility-registration", E.REGISTRATION, "四技二專聯合登記分發 個別登記資格審查登錄及繳件"),
        Rule(r"資格審查結果複查", "eligibility-review", E.REVIEW, "四技二專聯合登記分發 資格審查結果複查"),
        Rule(r"資格審查結果公告", "eligibility-result", E.ANNOUNCEMENT, "四技二專聯合登記分發 資格審查結果公告"),
        Rule(r"練習版", "preference-practice", E.OTHER, "四技二專聯合登記分發 網路選填登記志願（練習版）"),
        Rule(r"集體繳費", "group-payment", E.REGISTRATION, "四技二專聯合登記分發 集體繳費"),
        Rule(r"個別繳費", "payment", E.REGISTRATION, "四技二專聯合登記分發 個別繳費"),
        Rule(r"^公告實際招生名額$", "quota-announcement", E.ANNOUNCEMENT, "四技二專聯合登記分發 公告實際招生名額"),
        Rule(r"個人總成績複查", "score-review", E.REVIEW, "四技二專聯合登記分發 個人總成績複查"),
        Rule(r"個人總成績查詢", "score", E.RESULT, "四技二專聯合登記分發 個人總成績查詢"),
        Rule(r"^網路選填登記志願$", "preference-registration", E.ADMISSION, "四技二專聯合登記分發 網路選填登記志願"),
        Rule(r"錄取公告及分發結果查詢", "release", E.ADMISSION, "四技二專聯合登記分發 錄取公告及分發結果查詢"),
        Rule(r"分發結果複查", "release-review", E.REVIEW, "四技二專聯合登記分發 分發結果複查"),
    ),
    cross_rules=_TECH_CROSS,
    required=("jctv-union-{y}-preference-registration", "jctv-union-{y}-release"),
)

JCTV_CHANNELS = (APPLY, SKILL, UNION)


def jctv_landing(html: str, url: str) -> tuple[int, str]:
    """各管道首頁 → (最新學年度, 「重要日程」頁 subId)。"""
    soup = soup_of(html)
    title = soup.title.get_text(strip=True) if soup.title else ""
    m = re.search(r"(\d{3})\s*學年度", title)
    if not m:
        raise ScraperError(f"JCTV 管道首頁標題找不到學年度：{title!r}（{url}）")
    for link, _, text in absolute_links(soup, url):
        if text == "重要日程" and "contents.php" in link:
            sub = parse_qs(urlsplit(link).query).get("subId")
            if sub:
                return int(m.group(1)), sub[0]
    raise ScraperError(f"JCTV 管道首頁找不到「重要日程」連結（{url}）")


def jctv_schedule_pdf(html: str, url: str, pattern: str) -> tuple[str, str] | None:
    """「重要日程」頁 → (PDF URL, 連結文字)；尚未公布時回傳 None。"""
    for link, decoded, text in absolute_links(soup_of(html), url):
        if decoded.lower().endswith(".pdf") and re.search(pattern, squash(text)):
            return link, text
    return None


def parse_jctv_pdf(pdf_bytes: bytes, channel: JctvChannel, academic_year: int, url: str, title: str,
                   ) -> tuple[list, list[CrossCheck], list[str]]:
    with open_pdf(pdf_bytes) as pdf:
        head = squash(pdf.pages[0].extract_text() or "")
        m = re.search(r"(\d{3})學年度", head)
        if not m or int(m.group(1)) != academic_year:
            raise ScraperError(f"{channel.name} 日程表 PDF 標示 {m.group(1) if m else '?'} 學年度，與網頁 {academic_year} 不一致")
        rows = []
        for i, page in enumerate(pdf.pages):
            try:
                rows += ruled_table_rows(page, i + 1, PDF_COLUMNS)
            except ValueError as exc:
                raise ScraperError(f"{channel.name} 日程表：{exc}") from exc
    if len(rows) < 8:
        raise ScraperError(f"{channel.name} 日程表只解析出 {len(rows)} 列，版面可能已改變")

    builder = EventBuilder(academic_year, f"{channel.key}-{academic_year}", Category.TECHNICAL, "JCTV",
                           channel.exam, channel.name, url, title)
    checks: list[CrossCheck] = []
    skipped: list[str] = []
    for row in rows:
        date_text, item = row.cells["date"], row.cells["item"]
        dr = parse_roc_range(strip_side_notes(date_text), f"{channel.name} {tidy(item)[:30]}")
        if dr is None:
            continue
        key = squash(item)
        cross = next((c for c in channel.cross_rules if c.matches(key)), None)
        if cross:
            checks.append(CrossCheck(cross.target.format(y=academic_year), dr.start, dr.end, url, f"{channel.name}日程表：{tidy(item)[:40]}"))
            continue
        rule = match_rule(list(channel.rules), item)
        if rule is None or rule.suffix is None:
            skipped.append(f"{dr.start.isoformat()} {tidy(item)[:60]}")
            continue
        note = extract_time_note(date_text)
        if "各校自訂" in date_text:
            note = "日期由各校自訂（詳見簡章）" + (f"；{note}" if note else "")
        builder.add(rule, dr, source_text=f"{tidy(date_text)}｜{tidy(item)[:80]}", note=note)
    return list(builder.events.values()), checks, skipped


def scrape_jctv_channel(fetcher: Fetcher, channel: JctvChannel) -> ScrapeResult:
    landing_url = urljoin(JCTV_BASE, channel.path + "/")
    landing = fetcher.get(landing_url)
    latest, sub_id = jctv_landing(landing.text(), landing.url)
    warnings = []
    for year in (latest, latest - 1):
        page_url = urljoin(landing_url, f"contents.php?academicYear={year}&subId={sub_id}")
        page = fetcher.get(page_url)
        found = jctv_schedule_pdf(page.text(), page.url, channel.link_pattern)
        if found is None:
            warnings.append(f"{channel.name} {year} 學年度重要日程尚未公布（{page_url}）")
            continue
        pdf_url, link_text = found
        title = f"{year}學年度{channel.name}{tidy(link_text)}"
        pdf = fetcher.get(pdf_url).expect_pdf()
        events, checks, skipped = parse_jctv_pdf(pdf, channel, year, pdf_url, title)
        result = ScrapeResult(
            source_key=channel.key, name=channel.name, organizer="JCTV", academic_year=year,
            source_url=pdf_url, source_title=title, id_prefixes=(f"{channel.key}-",),
            events=events, cross_checks=checks, warnings=warnings, skipped_items=skipped,
        )
        require_ids(result, channel.required)
        return result
    raise ScraperError(f"{channel.name}：{latest} 與 {latest - 1} 學年度都找不到重要日程表 PDF")


def _channel_spec(channel: JctvChannel) -> ScraperSpec:
    return ScraperSpec(
        key=channel.key,
        name=f"技專校院招生委員會聯合會（JCTV）{channel.name}",
        organizer="JCTV",
        exams=channel.name,
        homepage=urljoin(JCTV_BASE, channel.path + "/"),
        run=lambda f, c=channel: [scrape_jctv_channel(f, c)],
        required=channel.required,
        min_events=5,
    )


SPECS = [TCTE_SPEC] + [_channel_spec(c) for c in JCTV_CHANNELS]
