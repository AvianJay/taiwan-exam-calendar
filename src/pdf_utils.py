"""PDF 解析共用工具。

處理順序（對應需求）：
1. 文字層 extraction（pdfplumber）
2. 表格 extraction：`table_grid()` 會把合併儲存格展開成完整矩陣
3. 依格線切 row band：`ruled_bands()`，給沒有完整表格結構、但有畫格線的日程表用
4. OCR fallback：`ocr_region()`，只在文字層缺少中文時使用（需安裝 requirements-ocr.txt）
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from typing import Iterable

import pdfplumber
from pdfplumber import utils as pdf_text
from pdfplumber.page import Page

_CJK = re.compile(r"[一-鿿]")


class OCRUnavailable(RuntimeError):
    pass


def open_pdf(data: bytes) -> pdfplumber.PDF:
    return pdfplumber.open(io.BytesIO(data))


def has_cjk(text: str | None) -> bool:
    return bool(text and _CJK.search(text))


def clean_lines(text: str | None) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _mid_in(obj: dict, bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    mx = (obj["x0"] + obj["x1"]) / 2
    my = (obj["top"] + obj["bottom"]) / 2
    return x0 <= mx < x1 and top <= my < bottom


def region_chars(page: Page, bbox: tuple[float, float, float, float]) -> list[dict]:
    """只取「中心點落在 bbox 內」的字元（與 pdfplumber 表格判定 cell 歸屬的方式一致）。"""
    return [c for c in page.chars if _mid_in(c, bbox)]


def region_text(page: Page, bbox: tuple[float, float, float, float]) -> str:
    chars = region_chars(page, bbox)
    return pdf_text.extract_text(chars) if chars else ""


def region_words(page: Page, bbox: tuple[float, float, float, float]) -> list[dict]:
    chars = region_chars(page, bbox)
    return pdf_text.extract_words(chars) if chars else []


def find_words(page: Page, pattern: str) -> list[dict]:
    rx = re.compile(pattern)
    return [w for w in page.extract_words() if rx.fullmatch(w["text"])]


# ---------------------------------------------------------------- 表格矩陣


Bbox = tuple[float, float, float, float]


def table_cells(page: Page, table) -> list[list[tuple[str, Bbox | None]]]:
    """把 pdfplumber 的 Table 轉成「合併儲存格已展開」的 (文字, bbox) 矩陣。

    pdfplumber 對被合併儲存格覆蓋的位置回傳 None；這裡找出覆蓋該位置的
    實際 cell，填入同一段文字。水平合併（同列跨欄）與垂直合併（跨列）都適用。
    """
    rows = table.rows
    if not rows:
        return []
    xs = sorted({c[0] for c in table.cells})
    x_right = max(c[2] for c in table.cells)
    col_edges = xs + [x_right]
    texts: dict[Bbox, str] = {}

    grid: list[list[tuple[str, Bbox | None]]] = []
    for row in rows:
        top = row.bbox[1]
        out: list[tuple[str, Bbox | None]] = []
        for ci, cell in enumerate(row.cells):
            if cell is None:
                px = (col_edges[ci] + col_edges[ci + 1]) / 2
                py = top + 1.0
                cell = next(
                    (c for c in table.cells if c[0] - 0.5 <= px <= c[2] + 0.5 and c[1] - 0.5 <= py <= c[3] + 0.5),
                    None,
                )
            if cell is None:
                out.append(("", None))
                continue
            bbox = tuple(cell)
            if bbox not in texts:
                texts[bbox] = region_text(page, bbox).strip()
            out.append((texts[bbox], bbox))
        grid.append(out)
    return grid


def table_grid(page: Page, table) -> list[list[str]]:
    return [[text for text, _ in row] for row in table_cells(page, table)]


def largest_table(page: Page):
    tables = page.find_tables()
    if not tables:
        return None
    return max(tables, key=lambda t: len(t.rows) * max(len(r.cells) for r in t.rows))


# ---------------------------------------------------------------- 格線


@dataclass(frozen=True)
class HRule:
    x0: float
    x1: float
    y: float


@dataclass(frozen=True)
class VRule:
    x: float
    top: float
    bottom: float


def thin_rules(page: Page, max_thickness: float = 2.5) -> tuple[list[HRule], list[VRule]]:
    """表格格線：line 物件與「很細的矩形」（很多 PDF 用細矩形畫線）。"""
    hs: list[HRule] = []
    vs: list[VRule] = []
    for o in list(page.lines) + list(page.rects):
        w = o["x1"] - o["x0"]
        h = o["bottom"] - o["top"]
        if h <= max_thickness and w > 5:
            hs.append(HRule(o["x0"], o["x1"], (o["top"] + o["bottom"]) / 2))
        elif w <= max_thickness and h > 5:
            vs.append(VRule((o["x0"] + o["x1"]) / 2, o["top"], o["bottom"]))
    return hs, vs


def rule_ys_spanning(hrules: Iterable[HRule], x0: float, x1: float, tol: float = 4.0, merge: float = 2.0) -> list[float]:
    """橫跨 [x0, x1] 欄位的水平格線 y 座標（排序並合併相近值）。"""
    ys = sorted(r.y for r in hrules if r.x0 <= x0 + tol and r.x1 >= x1 - tol)
    merged: list[float] = []
    for y in ys:
        if not merged or y - merged[-1] > merge:
            merged.append(y)
    return merged


def dominant_vrule_between(vrules: Iterable[VRule], left: float, right: float) -> float | None:
    """兩個欄位標題之間「累積長度最長」的垂直格線，作為欄界。"""
    weight: dict[int, float] = {}
    for r in vrules:
        if left < r.x < right:
            key = round(r.x)
            weight[key] = weight.get(key, 0.0) + (r.bottom - r.top)
    if not weight:
        return None
    return float(max(weight, key=weight.get))


def bands(ys: list[float]) -> list[tuple[float, float]]:
    return [(a, b) for a, b in pairwise(ys) if b - a > 3]


@dataclass
class RuledRow:
    page: int
    cells: dict[str, str]  # 欄位名稱 → 文字


def _spaced_header(words: list[dict], chars: str) -> dict | None:
    """找出「日 期」「項 目」這類字與字之間有空白的表頭，回傳合併後的位置。"""
    first = [w for w in words if w["text"] == chars[0]]
    for w in first:
        same = sorted((x for x in words if abs(x["top"] - w["top"]) < 3 and x["x0"] >= w["x0"]), key=lambda x: x["x0"])
        seq = [x for x in same if x["text"] in chars]
        texts = "".join(x["text"] for x in seq[: len(chars)])
        if texts == chars:
            last = seq[len(chars) - 1]
            return {"x0": w["x0"], "x1": last["x1"], "top": w["top"], "bottom": w["bottom"]}
    return None


def ruled_table_rows(page: Page, page_no: int, columns: dict[str, tuple[str, ...]]) -> list[RuledRow]:
    """解析「日期｜項目｜備註」這類以格線分列的日程表。

    columns：欄位名稱 → 可能的表頭文字（例如 {"date": ("日期",), "item": ("項目", "作業項目")}），
    第一個欄位為最左欄，第二個欄位用來決定「列」的邊界（橫跨該欄的格線）。
    欄界取兩個表頭之間「累積長度最長」的垂直格線，不依賴固定座標。
    """
    words = page.extract_words()
    heads: dict[str, dict] = {}
    for name, options in columns.items():
        for opt in options:
            h = _spaced_header(words, opt)
            if h:
                heads[name] = h
                break
    names = list(columns)
    if names[0] not in heads or names[1] not in heads:
        return []
    names = [n for n in names if n in heads]
    centers = {n: (heads[n]["x0"] + heads[n]["x1"]) / 2 for n in names}
    hrules, vrules = thin_rules(page)
    edges = [dominant_vrule_between(vrules, page.bbox[0], centers[names[0]])]
    for a, b in pairwise(names):
        edges.append(dominant_vrule_between(vrules, centers[a], centers[b]))
    edges.append(dominant_vrule_between(vrules, centers[names[-1]], page.bbox[2]))
    if any(e is None for e in edges):
        raise ValueError(f"第 {page_no} 頁表格找不到完整的垂直格線，無法判定欄位邊界")
    col_x = {n: (edges[i], edges[i + 1]) for i, n in enumerate(names)}
    key_x0, key_x1 = col_x[names[1]]
    header_bottom = max(h["bottom"] for h in heads.values())
    ys = [y for y in rule_ys_spanning(hrules, key_x0, key_x1) if y >= header_bottom - 1]
    rows = []
    for y0, y1 in bands(ys):
        cells = {n: region_text(page, (x0, y0, x1, y1)).strip() for n, (x0, x1) in col_x.items()}
        if any(cells.values()):
            rows.append(RuledRow(page_no, cells))
    return rows


# ---------------------------------------------------------------- OCR fallback


@lru_cache(maxsize=1)
def _ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except ImportError as exc:  # pragma: no cover - 取決於環境
        raise OCRUnavailable("需要 OCR fallback，但未安裝 rapidocr-onnxruntime（pip install -r requirements-ocr.txt）") from exc
    return RapidOCR()


def ocr_available() -> bool:
    try:
        _ocr_engine()
        return True
    except OCRUnavailable:
        return False


_RENDER_CACHE: dict[tuple[int, int, float], object] = {}


def _render(pdf_bytes: bytes, page_index: int, scale: float):
    import pypdfium2 as pdfium

    key = (hash(pdf_bytes), page_index, scale)
    if key not in _RENDER_CACHE:
        doc = pdfium.PdfDocument(pdf_bytes)
        try:
            _RENDER_CACHE[key] = doc[page_index].render(scale=scale).to_pil().convert("RGB")
        finally:
            doc.close()
    return _RENDER_CACHE[key]


def ocr_region(pdf_bytes: bytes, page_index: int, page_bbox: tuple[float, float, float, float],
               bbox: tuple[float, float, float, float], scales: tuple[float, ...] = (5.0, 3.0, 4.0)) -> str:
    """把 PDF 某區域（例如表格儲存格）render 成影像後做 OCR，回傳辨識文字。

    逐格裁切並加白邊的辨識率遠高於整頁辨識；依序嘗試多種解析度直到有結果。
    """
    import numpy as np
    from PIL import ImageOps

    engine = _ocr_engine()
    ox, oy = page_bbox[0], page_bbox[1]
    x0, top, x1, bottom = bbox
    for scale in scales:
        img = _render(pdf_bytes, page_index, scale)
        crop = img.crop((int((x0 - ox) * scale) + 3, int((top - oy) * scale) + 3,
                         int((x1 - ox) * scale) - 3, int((bottom - oy) * scale) - 3))
        crop = ImageOps.expand(crop, border=30, fill="white")
        result, _ = engine(np.array(crop))
        if result:
            result = sorted(result, key=lambda r: (r[0][0][1], r[0][0][0]))
            return "\n".join(r[1] for r in result)
    return ""


# OCR 模型偶爾輸出簡體或相近字，比對關鍵字前先轉回繁體常用字。
_OCR_VARIANTS = str.maketrans({
    "绩": "績", "復": "複", "项": "項", "测": "測", "讯": "訊", "结": "結", "务": "務",
    "题": "題", "参": "參", "发": "發", "试": "試", "报": "報", "询": "詢", "时": "時",
    "间": "間", "审": "審", "关": "關", "开": "開", "应": "應", "证": "證", "单": "單",
    "书": "書", "选": "選", "择": "擇", "听": "聽", "学": "學", "个": "個", "别": "別",
    "窑": "審", "罩": "單", "廳": "應", "遵": "選", "摆": "擇", "餐": "資", "凝": "礙",
})


def normalize_ocr(text: str) -> str:
    return re.sub(r"[\s·•●⚫]", "", (text or "").translate(_OCR_VARIANTS))
