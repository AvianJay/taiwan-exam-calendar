"""大學入學管道：繁星推薦、個人申請（CAC）與分發入學（UAC）。

資料來源（皆為官方）：
- 大學甄選入學委員會 https://www.cac.edu.tw/ ：入口頁連結到 `star{學年度}`、`apply{學年度}`
  子網站，各自的「重要時程」頁（schedule.php）為 HTML 表格。最新學年度若尚未公布
  （頁面顯示「目前尚無資料」），退回上一學年度並記錄警告。
- 大學考試入學分發委員會 https://www.uac.edu.tw/flow.htm 「XXX學年度分發入學重要時程」。

這兩個網站也列出大考中心考試（學測、分科、英聽）的日期，這些只作為 CEEC 資料的
交叉驗證（CrossCheck），不會產生或覆蓋事件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from ..dates import extract_time_note, parse_roc_range, strip_side_notes
from ..fetch import Fetcher
from ..models import Category, CrossCheck, EventType, ScrapeResult, ScraperError
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

# ====================================================================== CAC

CAC_PORTAL = "https://www.cac.edu.tw/cacportal/index.php"
CAC_BASE = "https://www.cac.edu.tw/"

_CEEC_CROSS = (
    CrossRule(r"大學入學考試中心基金會學科能力測驗$", "ceec-gsat-{y}"),
    CrossRule(r"公告學科能力測驗成績", "ceec-gsat-{y}-result"),
)


@dataclass(frozen=True)
class CacChannel:
    key: str
    slug: str  # 網址前綴 star / apply
    exam: str
    name: str
    rules: tuple[Rule, ...]
    required: tuple[str, ...]


STAR = CacChannel(
    key="cac-star",
    slug="star",
    exam="star",
    name="大學繁星推薦",
    rules=(
        Rule(r"^招生簡章公告$", "brochure", E.ANNOUNCEMENT, "大學繁星推薦 招生簡章公告"),
        Rule(r"推薦學校向甄選委員會辦理報名", "registration", E.REGISTRATION, "大學繁星推薦 推薦學校辦理報名"),
        Rule(r"推薦學校向甄選委員會辦理繳費", "payment", E.REGISTRATION, "大學繁星推薦 推薦學校辦理繳費"),
        Rule(r"第一類至第七類學群.*公告錄取名單", "release", E.ADMISSION, "大學繁星推薦 第一至七類學群 公告錄取名單"),
        Rule(r"第一類至第七類學群.*錄取結果複查", "release-review", E.REVIEW, "大學繁星推薦 第一至七類學群 錄取結果複查截止"),
        Rule(r"第一類至第七類學群.*聲明放棄", "waiver", E.ADMISSION, "大學繁星推薦 第一至七類學群 錄取生聲明放棄入學資格"),
        Rule(r"第八類學群.*第一階段篩選結果複查", "group8-screening-review", E.REVIEW, "大學繁星推薦 第八類學群 第一階段篩選結果複查截止"),
        Rule(r"第八類學群.*公告第一階段篩選結果", "group8-screening", E.RESULT, "大學繁星推薦 第八類學群 第一階段篩選結果"),
        Rule(r"第八類學群.*指定項目甄試.*日期", "group8-interview", E.EXAM, "大學繁星推薦 第八類學群 第二階段指定項目甄試（日期由各大學自訂）"),
        Rule(r"第八類學群.*甄選委員會公告錄取名單", "group8-release", E.ADMISSION, "大學繁星推薦 第八類學群 公告錄取名單"),
        Rule(r"第八類學群.*聲明放棄", "group8-waiver", E.ADMISSION, "大學繁星推薦 第八類學群 錄取生聲明放棄入學資格"),
    ),
    required=("cac-star-{y}-registration", "cac-star-{y}-release"),
)

APPLY = CacChannel(
    key="cac-apply",
    slug="apply",
    exam="apply",
    name="大學個人申請",
    rules=(
        Rule(r"^招生簡章公告$", "brochure", E.ANNOUNCEMENT, "大學個人申請 招生簡章公告"),
        Rule(r"第一階段.*個別報名考生向甄選委員會辦理報名", "registration", E.REGISTRATION, "大學個人申請 第一階段個別報名"),
        Rule(r"第一階段.*集體報名學校向甄選委員會辦理報名", "group-registration", E.REGISTRATION, "大學個人申請 第一階段集體報名"),
        Rule(r"第一階段.*個別報名考生向甄選委員會辦理繳費", "payment", E.REGISTRATION, "大學個人申請 第一階段個別報名繳費"),
        Rule(r"第一階段.*篩選結果複查", "screening-review", E.REVIEW, "大學個人申請 第一階段篩選結果複查截止"),
        Rule(r"第一階段.*公告篩選結果", "screening-result", E.RESULT, "大學個人申請 第一階段篩選結果公告"),
        Rule(r"第二階段.*指定項目甄試日期", "interview", E.EXAM, "大學個人申請 第二階段指定項目甄試（日期由各大學自訂）"),
        Rule(r"第二階段.*大學公告錄取名單", "admission-list", E.ADMISSION, "大學個人申請 各大學公告錄取名單（最晚日期）"),
        Rule(r"統一分發.*登記就讀志願序", "preference-registration", E.ADMISSION, "大學個人申請 錄取生登記就讀志願序"),
        Rule(r"統一分發.*統一分發結果複查", "release-review", E.REVIEW, "大學個人申請 統一分發結果複查截止"),
        Rule(r"統一分發.*公告統一分發結果", "release", E.ADMISSION, "大學個人申請 公告統一分發結果"),
        Rule(r"統一分發.*聲明放棄", "waiver", E.ADMISSION, "大學個人申請 錄取生聲明放棄入學資格"),
    ),
    required=("cac-apply-{y}-registration", "cac-apply-{y}-screening-result", "cac-apply-{y}-release"),
)

CAC_CHANNELS = (STAR, APPLY)


def cac_latest_years(html: str) -> dict[str, int]:
    """入口頁 → {"star": 116, "apply": 116}。"""
    years: dict[str, int] = {}
    for url, _, _ in absolute_links(soup_of(html), CAC_PORTAL):
        m = re.search(r"/(star|apply)(\d{3})/", url)
        if m:
            years[m.group(1)] = max(years.get(m.group(1), 0), int(m.group(2)))
    return years


def parse_cac_schedule(html: str) -> list[tuple[str, str]] | None:
    """重要時程頁 → [(項目（含階段／學群前綴）, 日期文字)]；尚未公布回傳 None。"""
    soup = soup_of(html)
    for table in soup.find_all("table"):
        grid = html_table_grid(table)
        if grid and list(dict.fromkeys(grid[0])) == ["項目", "日期"]:
            rows = []
            for row in grid[1:]:
                if len(row) < 2 or squash(row[-1]) == "[TOP]":
                    continue
                labels = list(dict.fromkeys(c for c in row[:-1] if c))
                rows.append(("｜".join(labels), row[-1]))
            return rows
    if "目前尚無資料" in soup.get_text():
        return None
    raise ScraperError("大學甄選入學委員會重要時程頁找不到「項目／日期」表格，網站結構可能已改變")


def _cac_range(text: str, context: str):
    # 「大學自訂（115.05.14 至 115.05.31）」的日期在括號內，不能當附註移除
    if "大學自訂" in text:
        return parse_roc_range(text, context)
    return parse_roc_range(strip_side_notes(text), context)


def scrape_cac_channel(fetcher: Fetcher, channel: CacChannel, latest: int) -> ScrapeResult:
    warnings = []
    for year in (latest, latest - 1):
        url = urljoin(CAC_BASE, f"{channel.slug}{year}/schedule.php")
        rows = parse_cac_schedule(fetcher.get(url).text())
        if rows is None:
            warnings.append(f"{channel.name} {year} 學年度重要時程尚未公布（{url}）")
            continue
        title = f"{year}學年度{channel.name}重要時程"
        builder = EventBuilder(year, f"{channel.key}-{year}", Category.ADMISSION, "CAC", channel.exam,
                               channel.name, url, title)
        checks, skipped = [], []
        for label, date_text in rows:
            dr = _cac_range(date_text, f"{channel.name} {label[:30]}")
            if dr is None:
                continue
            key = squash(label)
            cross = next((c for c in _CEEC_CROSS if c.matches(key)), None)
            if cross:
                checks.append(CrossCheck(cross.target.format(y=year), dr.start, dr.end, url, f"{title}：{tidy(label)}"))
                continue
            rule = match_rule(list(channel.rules), key)
            if rule is None or rule.suffix is None:
                skipped.append(f"{dr.start.isoformat()} {tidy(label)[:60]}")
                continue
            note = extract_time_note(date_text)
            if "大學自訂" in date_text:
                note = "日期由各大學自訂（詳校系分則）" + (f"；{note}" if note else "")
            builder.add(rule, dr, source_text=f"{tidy(label)}｜{tidy(date_text)}", note=note)
        result = ScrapeResult(
            source_key=channel.key, name=channel.name, organizer="CAC", academic_year=year,
            source_url=url, source_title=title, id_prefixes=(f"{channel.key}-",),
            events=list(builder.events.values()), cross_checks=checks, warnings=warnings, skipped_items=skipped,
        )
        require_ids(result, channel.required)
        return result
    raise ScraperError(f"{channel.name}：{latest} 與 {latest - 1} 學年度都找不到重要時程")


def scrape_cac(fetcher: Fetcher, channel: CacChannel) -> list[ScrapeResult]:
    years = cac_latest_years(fetcher.get(CAC_PORTAL).text())
    if channel.slug not in years:
        raise ScraperError(f"大學甄選入學委員會入口頁找不到 {channel.slug}XXX 子網站連結，網站結構可能已改變")
    return [scrape_cac_channel(fetcher, channel, years[channel.slug])]


# ====================================================================== UAC

UAC_URL = "https://www.uac.edu.tw/flow.htm"

UAC_RULES: list[Rule] = [
    Rule(r"^發售-「分發入學招生簡章」", "brochure", E.ANNOUNCEMENT, "大學分發入學 招生簡章發售"),
    Rule(r"^受理-「登記分發相關證明文件」審查", "document-review", E.OTHER, "大學分發入學 受理登記分發相關證明文件審查"),
    Rule(r"^公布-「文件審查結果」", "document-review-result", E.ANNOUNCEMENT, "大學分發入學 公布文件審查結果"),
    Rule(r"^公布-「招生名額", "quota-announcement", E.ANNOUNCEMENT, "大學分發入學 公布招生名額、組合成績人數累計表及最低登記標準"),
    Rule(r"^繳費-「分發入學登記費」", "payment", E.REGISTRATION, "大學分發入學 繳交登記費"),
    Rule(r"^登記-「分發志願」", "preference-registration", E.ADMISSION, "大學分發入學 登記分發志願"),
    Rule(r"^公布-「大學分發入學錄取名單」", "release", E.ADMISSION, "大學分發入學 公布錄取名單（放榜）"),
    Rule(r"^受理-「分發結果」複查", "release-review", E.REVIEW, "大學分發入學 受理分發結果複查"),
    Rule(r"^公布-「分發複查結果」", "review-result", E.REVIEW, "大學分發入學 公布分發複查結果"),
]

UAC_CROSS: list[CrossRule] = [
    CrossRule(r"^報名-「高中英語聽力測驗\(第一次考試\)」", "ceec-english-listening-{y}-1-registration"),
    CrossRule(r"^考試-「高中英語聽力測驗\(第一次考試\)」", "ceec-english-listening-{y}-1"),
    CrossRule(r"^報名-「高中英語聽力測驗\(第二次考試\)」", "ceec-english-listening-{y}-2-registration"),
    CrossRule(r"^考試-「高中英語聽力測驗\(第二次考試\)」", "ceec-english-listening-{y}-2"),
    CrossRule(r"^報名-「學科能力測驗」", "ceec-gsat-{y}-registration"),
    CrossRule(r"^考試-「學科能力測驗」", "ceec-gsat-{y}"),
    CrossRule(r"^報名-「分科測驗」", "ceec-ast-{y}-registration"),
    CrossRule(r"^考試-「分科測驗」", "ceec-ast-{y}"),
    CrossRule(r"^公布-「分科測驗成績」", "ceec-ast-{y}-result"),
    CrossRule(r"^放棄-「繁星推薦\(第一至七類學群\)」", "cac-star-{y}-waiver"),
    CrossRule(r"^放棄-「繁星推薦\(第八類學群\)」", "cac-star-{y}-group8-waiver"),
    CrossRule(r"^放棄-.*「申請入學」", "cac-apply-{y}-waiver"),
]

_UAC_ROW = re.compile(r"^(?P<dates>\d{3}/\d{1,2}/\d{1,2}(?:~\d{3}/\d{1,2}/\d{1,2})?)(?P<extra>\([^)]*\))?\s*(?P<item>.+)$")


def parse_uac(html: str) -> tuple[int, str, list[tuple[str, str, str]]]:
    """回傳 (學年度, 標題, [(日期文字, 事項, 備註)])。"""
    soup = soup_of(html)
    heading = next(
        (t for t in soup.find_all(["h1", "h2", "h3"]) if re.fullmatch(r"\d{3}學年度分發入學重要時程", t.get_text(strip=True))),
        None,
    )
    if heading is None:
        raise ScraperError("分發會網站找不到「XXX學年度分發入學重要時程」標題，網站結構可能已改變")
    title = heading.get_text(strip=True)
    for table in soup.find_all("table"):
        grid = html_table_grid(table)
        if grid and [squash(c) for c in grid[0][:3]] == ["月份", "事項", "備註"]:
            rows = []
            for row in grid[1:]:
                if len(row) < 3:
                    continue
                cell = squash(row[1])
                m = _UAC_ROW.match(cell)
                if not m:
                    raise ScraperError(f"分發會重要時程有無法解析的列：{row[1]!r}")
                rows.append((m.group("dates") + (m.group("extra") or ""), m.group("item"), row[2]))
            return int(title[:3]), title, rows
    raise ScraperError("分發會重要時程頁找不到「月份／事項／備註」表格")


def scrape_uac(fetcher: Fetcher) -> list[ScrapeResult]:
    year, title, rows = parse_uac(fetcher.get(UAC_URL).text())
    builder = EventBuilder(year, f"uac-{year}", Category.ADMISSION, "UAC", "uac", "大學分發入學", UAC_URL, title)
    checks, skipped = [], []
    for date_text, item, _note in rows:
        dr = parse_roc_range(strip_side_notes(date_text), f"分發會 {item}")
        if dr is None:
            continue
        crosses = [c for c in UAC_CROSS if c.matches(item)]
        if crosses:
            checks += [CrossCheck(c.target.format(y=year), dr.start, dr.end, UAC_URL, f"{title}：{item}") for c in crosses]
            continue
        rule = match_rule(UAC_RULES, item)
        if rule is None or rule.suffix is None:
            skipped.append(f"{dr.start.isoformat()} {item}")
            continue
        builder.add(rule, dr, source_text=f"{date_text} {item}", note=extract_time_note(date_text))
    result = ScrapeResult(
        source_key="uac", name="大學考試入學分發委員會", organizer="UAC", academic_year=year,
        source_url=UAC_URL, source_title=title, id_prefixes=("uac-",),
        events=list(builder.events.values()), cross_checks=checks, skipped_items=skipped,
    )
    require_ids(result, UAC_SPEC.required)
    return [result]


UAC_SPEC = ScraperSpec(
    key="uac",
    name="大學考試入學分發委員會（UAC）",
    organizer="UAC",
    exams="大學分發入學",
    homepage="https://www.uac.edu.tw/",
    run=scrape_uac,
    required=("uac-{y}-preference-registration", "uac-{y}-release"),
    min_events=4,
)


def _cac_spec(channel: CacChannel) -> ScraperSpec:
    return ScraperSpec(
        key=channel.key,
        name=f"大學甄選入學委員會（CAC）{channel.name}",
        organizer="CAC",
        exams=channel.name,
        homepage=CAC_PORTAL,
        run=lambda f, c=channel: scrape_cac(f, c),
        required=channel.required,
        min_events=4,
    )


SPECS = [_cac_spec(c) for c in CAC_CHANNELS] + [UAC_SPEC]
