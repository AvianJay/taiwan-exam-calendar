"""重新錄製測試 fixtures（需要網路）。

執行所有 scraper，並把過程中抓取的每一個官方網頁／PDF 存到 tests/fixtures/，
同時寫出 manifest.json（URL → 檔名）。測試使用 FixtureFetcher 依 manifest 回放，
因此 tests 完全不需要網路。

    python scripts/update_fixtures.py

注意：官方網站內容會隨時間變動，重新錄製後測試中的預期日期可能需要一併更新。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.fetch import HttpFetcher, Response  # noqa: E402
from src.scrapers.registry import ALL_SPECS  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
# 超過此大小的 PDF 只保留前幾頁（CEEC 簡章 PDF 約 4 MB，parser 只需要前 12 頁內的日程頁）
MAX_PDF_BYTES = 1_500_000
KEEP_PAGES = 4


def fixture_name(url: str, content: bytes) -> str:
    """純 ASCII 檔名；路徑含中文或過長時以 URL 的 hash 區分。"""
    parts = urlsplit(url)
    path = unquote(parts.path).strip("/").replace("/", "_") or "index"
    query = re.sub(r"[^\w]+", "_", parts.query).strip("_")
    path = re.sub(r"\.pdf$", "", path, flags=re.I)
    raw = f"{parts.netloc}_{path}{'_' + query if query else ''}"
    stem = re.sub(r"[^A-Za-z0-9.\-]+", "_", raw).strip("_")
    if stem != raw.replace("/", "_") or len(stem) > 80:
        stem = re.sub(r"_+", "_", stem)[:60].rstrip("_.") + "_" + hashlib.sha1(url.encode()).hexdigest()[:8]
    if content.startswith(b"%PDF"):
        return stem + ".pdf"
    return stem if stem.endswith((".html", ".htm", ".php")) else stem + ".html"


def shrink_pdf(content: bytes) -> bytes:
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(content)
    dst = pdfium.PdfDocument.new()
    dst.import_pages(src, list(range(min(KEEP_PAGES, len(src)))))
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()


class RecordingFetcher(HttpFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.recorded: dict[str, Response] = {}

    def get(self, url: str) -> Response:
        resp = super().get(url)
        self.recorded[url] = resp
        return resp


def main() -> int:
    fetcher = RecordingFetcher()
    for spec in ALL_SPECS:
        print(f"→ {spec.key}")
        spec.run(fetcher)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for url, resp in sorted(fetcher.recorded.items()):
        name = fixture_name(url, resp.content)
        content = resp.content
        if content.startswith(b"%PDF") and len(content) > MAX_PDF_BYTES:
            content = shrink_pdf(content)
        (FIXTURES / name).write_bytes(content)
        manifest[url] = {"file": name, "content_type": resp.content_type}
        print(f"  {name} ({len(content):,} bytes)")
    (FIXTURES / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"共 {len(manifest)} 個 fixture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
