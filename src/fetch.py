"""HTTP 下載層。

設計重點：
- 所有 scraper 都透過 `Fetcher` 介面取資料，測試時可換成讀 fixture 的實作，
  因此 parser 測試完全不需要網路。
- 台灣多個官方網站（CEEC、TCTE、JCTV、CAC）使用 TWCA 憑證，其中繼憑證缺少
  Subject Key Identifier。Python 3.13 起預設啟用 `VERIFY_X509_STRICT`，會因此
  驗證失敗。這裡只關閉 strict 旗標，**仍然完整驗證憑證鏈與主機名稱**，
  不使用 `verify=False`。
- 重試與退避參考 niansia/taiwan-exam 的 `get_bytes()`（MIT）。
"""

from __future__ import annotations

import os
import re
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _user_agent() -> str:
    # 在 GitHub Actions 中附上 repository 網址，讓官方網站管理者知道是誰在抓取
    repo = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    contact = f"; +{server}/{repo}" if repo else ""
    return f"Mozilla/5.0 (compatible; taiwan-exam-calendar/1.0{contact})"


USER_AGENT = _user_agent()
DEFAULT_TIMEOUT = 45


def utf8_stdio() -> None:
    """CLI 輸出統一用 UTF-8（Windows 管線預設 cp950 會讓中文與符號亂碼或拋錯）。"""
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")


class FetchError(RuntimeError):
    """下載失敗或內容不是預期格式（例如預期 PDF 卻拿到 HTML）。"""


@dataclass(frozen=True)
class Response:
    url: str
    content: bytes
    content_type: str = ""
    status: int = 200

    def text(self) -> str:
        """依 HTTP header → HTML meta → UTF-8 → Big5 的順序解碼。"""
        charset = _charset_from_content_type(self.content_type)
        if not charset:
            head = self.content[:4096].decode("ascii", errors="ignore")
            m = re.search(r"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""", head, re.I)
            if m:
                charset = m.group(1)
        candidates = [c for c in (charset, "utf-8-sig", "cp950") if c]
        for enc in candidates:
            try:
                return self.content.decode(_normalize_charset(enc))
            except (LookupError, UnicodeDecodeError):
                continue
        return self.content.decode("utf-8", errors="replace")

    def expect_pdf(self) -> bytes:
        if not self.content.startswith(b"%PDF"):
            raise FetchError(
                f"預期 PDF 但取得 {self.content_type or '未知格式'}（{len(self.content)} bytes）：{self.url}"
            )
        return self.content


def _charset_from_content_type(content_type: str) -> str | None:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    return m.group(1) if m else None


def _normalize_charset(enc: str) -> str:
    enc = enc.lower()
    if enc in {"big5", "big-5", "x-big5"}:
        return "cp950"
    if enc in {"utf8", "utf-8"}:
        return "utf-8-sig"
    return enc


def normalize_url(url: str) -> str:
    """把含中文的 URL 轉成 percent-encoded（CAP 的 href 是未編碼的中文檔名）。"""
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="=&%/:?+,;-._~")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


class Fetcher(Protocol):
    def get(self, url: str) -> Response: ...


class _TaiwanGovTLSAdapter(HTTPAdapter):
    """保留完整憑證驗證，但不套用 Python 3.13 的 X509 strict 規則。"""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


class HttpFetcher:
    """實際連網的 Fetcher：重試、逾時、同主機節流，並可選擇保存原始檔供除錯。"""

    def __init__(
        self,
        *,
        save_dir: Path | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        min_interval: float = 0.6,
    ) -> None:
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = _TaiwanGovTLSAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5",
            }
        )
        self.timeout = timeout
        self.min_interval = min_interval
        self.save_dir = save_dir
        self._last_hit: dict[str, float] = {}
        self._cache: dict[str, Response] = {}

    def get(self, url: str) -> Response:
        url = normalize_url(url)
        if url in self._cache:
            return self._cache[url]
        host = urlsplit(url).netloc
        wait = self.min_interval - (time.monotonic() - self._last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as exc:
            raise FetchError(f"連線失敗：{url}：{exc}") from exc
        finally:
            self._last_hit[host] = time.monotonic()
        if r.status_code != 200:
            raise FetchError(f"HTTP {r.status_code}：{url}")
        resp = Response(
            url=r.url,
            content=r.content,
            content_type=r.headers.get("Content-Type", ""),
            status=r.status_code,
        )
        self._cache[url] = resp
        if self.save_dir:
            self._save(url, resp)
        return resp

    def _save(self, url: str, resp: Response) -> None:
        assert self.save_dir is not None
        self.save_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", url.split("://", 1)[-1])[-150:]
        (self.save_dir / safe).write_bytes(resp.content)
