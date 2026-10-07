"""民國／西元日期與學年度處理。

原則：
- 官方文件上印的是「民國年」與「星期」。只要文件有印星期，就一律拿來驗證
  （日期與星期不符就是解析錯誤，直接丟例外）。
- 文件沒寫年份時（例如會考日程表只寫「月／日／星期」），用星期反推西元年，
  而不是用「學年度 + 1911」硬算。學年度會跨西元年：116 學年度的英聽在
  2026 年 10 月，學測在 2027 年 1 月。
- 跨年的區間（例如 115.12.24~01.05）在結束日月份小於開始日時自動進位一年。
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

ROC_OFFSET = 1911
WEEKDAY_CHARS = "一二三四五六日"  # 對應 date.weekday() 0..6
_WEEKDAY_ALIASES = {"天": "日", "ㄧ": "一", "壹": "一"}


class DateParseError(ValueError):
    """日期無法解析或與星期不一致。"""


def roc_to_gregorian(roc_year: int) -> int:
    if roc_year <= 0:
        raise DateParseError(f"民國年必須為正數：{roc_year}")
    return roc_year + ROC_OFFSET


def gregorian_to_roc(year: int) -> int:
    return year - ROC_OFFSET


def current_roc_year(today: dt.date | None = None) -> int:
    return gregorian_to_roc((today or dt.date.today()).year)


def academic_year_of(date: dt.date) -> int:
    """日期所在的「學年度」（8 月 1 日起算新學年）。

    注意：這只是「該日期屬於哪個學年度」的行政定義，**不能**用來推算某學年度
    考試在哪一年舉行。116 學年度的大學入學考試（英聽、學測、分科）
    是在 115 學年度期間舉辦的；考試年份一律以官方文件上的實際日期為準。
    """
    roc = gregorian_to_roc(date.year)
    return roc if date.month >= 8 else roc - 1


def normalize_text(text: str) -> str:
    """NFKC（全形數字／括號／波浪號轉半形）並統一常見異體字元。"""
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("～", "~").replace("〜", "~").replace("–", "-").replace("—", "-")


def weekday_index(char: str) -> int:
    char = _WEEKDAY_ALIASES.get(char, char)
    if char not in WEEKDAY_CHARS:
        raise DateParseError(f"無法辨識的星期字元：{char!r}")
    return WEEKDAY_CHARS.index(char)


def check_weekday(date: dt.date, char: str | None, context: str = "") -> None:
    if not char:
        return
    expected = weekday_index(char)
    if date.weekday() != expected:
        actual = WEEKDAY_CHARS[date.weekday()]
        raise DateParseError(
            f"日期 {date.isoformat()} 實際為星期{actual}，但官方文件標示星期{char}"
            + (f"（{context}）" if context else "")
        )


def make_date(year: int, month: int, day: int, weekday: str | None = None, context: str = "") -> dt.date:
    try:
        d = dt.date(year, month, day)
    except ValueError as exc:
        raise DateParseError(f"不存在的日期 {year}-{month}-{day}（{context}）") from exc
    check_weekday(d, weekday, context)
    return d


def roc_date(roc_year: int, month: int, day: int, weekday: str | None = None, context: str = "") -> dt.date:
    return make_date(roc_to_gregorian(roc_year), month, day, weekday, context)


def infer_year_from_weekdays(
    entries: Iterable[tuple[int, int, str]],
    candidate_years: Iterable[int],
    context: str = "",
) -> int:
    """以 (月, 日, 星期) 反推西元年。

    在候選年份中找出「所有 entries 的星期都吻合」的唯一年份；
    找不到或不唯一都視為錯誤，避免默默猜錯年份。
    """
    entries = list(entries)
    if not entries:
        raise DateParseError(f"沒有可用來推算年份的星期資訊（{context}）")
    matches = []
    for year in candidate_years:
        ok = True
        for month, day, wd in entries:
            try:
                d = dt.date(year, month, day)
            except ValueError:
                ok = False
                break
            if d.weekday() != weekday_index(wd):
                ok = False
                break
        if ok:
            matches.append(year)
    if len(matches) != 1:
        raise DateParseError(
            f"無法由星期唯一判定年份（候選 {list(candidate_years)}，吻合 {matches}；{context}）"
        )
    return matches[0]


@dataclass(frozen=True)
class DateRange:
    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise DateParseError(f"結束日 {self.end} 早於開始日 {self.start}")

    @classmethod
    def single(cls, d: dt.date) -> "DateRange":
        return cls(d, d)


# 民國日期 token：115.09.03(四)、115/06/03、115年09月03日(四)、115.5.15 (星期五)。
# 年份可省略（區間後半段常寫成 09.10(四)），由前一個 token 承接。
_DATE_TOKEN = re.compile(
    r"""
    (?:(?P<y>\d{2,3})\s*(?:[./]|年)\s*)?
    (?P<m>\d{1,2})\s*(?:[./]|月)\s*
    (?P<d>\d{1,2})(?!\d)\s*日?
    (?:\s*\(\s*(?:星期|週|周)?\s*(?P<w>[一二三四五六日天ㄧ])\s*\))?
    """,
    re.X,
)


@dataclass(frozen=True)
class DateToken:
    date: dt.date
    weekday: str | None
    start: int
    end: int
    had_year: bool


def find_roc_dates(text: str, context: str = "", default_roc_year: int | None = None) -> list[DateToken]:
    """找出字串中所有民國日期（含星期驗證）。

    沒寫年份的 token 承接前一個 token 的年份；若月日小於前一個 token，
    視為跨年（例如 115.12.24~01.05）。
    """
    text = normalize_text(text)
    tokens: list[DateToken] = []
    prev: dt.date | None = None
    for m in _DATE_TOKEN.finditer(text):
        month, day = int(m.group("m")), int(m.group("d"))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        if m.group("y"):
            year = roc_to_gregorian(int(m.group("y")))
            had_year = True
        elif prev is not None:
            year = prev.year
            if (month, day) < (prev.month, prev.day):
                year += 1
            had_year = False
        elif default_roc_year is not None:
            year = roc_to_gregorian(default_roc_year)
            had_year = False
        else:
            # 沒有年份可承接的「月.日」不視為日期（避免誤抓版本號、電話等）
            continue
        d = make_date(year, month, day, m.group("w"), context or text[:60])
        tokens.append(DateToken(d, m.group("w"), m.start(), m.end(), had_year))
        prev = d
    return tokens


_NON_WEEKDAY_PARENS = re.compile(r"\((?!\s*(?:星期|週|周)?\s*[一二三四五六日天ㄧ]\s*\))[^()]*\)")
_LENTICULAR = re.compile(r"【[^】]*】")


def strip_side_notes(text: str) -> str:
    """移除括號附註（保留星期括號），例如「(便利商店繳費僅至115.7.18止)」「【115.02.26寄發成績單】」。

    日期欄位的括號附註常含有另一個日期，若不移除會被誤當成區間端點。
    """
    return _LENTICULAR.sub(" ", _NON_WEEKDAY_PARENS.sub(" ", normalize_text(text)))


def parse_roc_range(text: str, context: str = "") -> DateRange | None:
    """把日期欄位文字轉成區間；沒有日期（例如「--」、「各校自訂」）回傳 None。

    欄位內若有超過兩個日期，取第一個與最後一個為區間端點。
    """
    tokens = find_roc_dates(text, context)
    if not tokens:
        return None
    return DateRange(tokens[0].date, tokens[-1].date)


# 由長到短：先吃掉「每日上午9時起至下午5時止」整段，避免再被拆成片段重複記錄
_TIME_PATTERNS = [
    r"每日[^,，。；]*?時[^,，。；]*?(?:止|前)",
    r"(?:上午|下午|中午|晚上)?\s*\d{1,2}\s*[:：]\s*\d{2}\s*(?:起|止|前|後)?",
    r"(?:上午|下午|中午|晚上)\s*\d{1,2}\s*時\s*(?:起|止|前|後)?",
]


def extract_time_note(text: str) -> str | None:
    """從日期欄位擷取時間描述（例如「上午9時起；下午5時止」），供 note 欄位使用。"""
    text = normalize_text(text)
    spans: list[tuple[int, int, str]] = []
    for pat in _TIME_PATTERNS:
        for m in re.finditer(pat, text):
            if any(s < m.end() and m.start() < e for s, e, _ in spans):
                continue
            spans.append((m.start(), m.end(), re.sub(r"\s+", "", m.group(0))))
    if not spans:
        return None
    return "；".join(frag for _, _, frag in sorted(spans))
