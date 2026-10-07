"""測試共用：以 fixtures/manifest.json 回放官方網站內容，測試完全不需要網路。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.fetch import FetchError, Response, normalize_url  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


class FixtureFetcher:
    """依 URL 回放 fixture；overrides 可替換內容（bytes）或模擬下載失敗（None）。"""

    def __init__(self, overrides: dict[str, bytes | None] | None = None) -> None:
        self.manifest = {normalize_url(u): v for u, v in MANIFEST.items()}
        self.overrides = {normalize_url(u): v for u, v in (overrides or {}).items()}
        self.requested: list[str] = []

    def get(self, url: str) -> Response:
        key = normalize_url(url)
        self.requested.append(key)
        if key in self.overrides:
            content = self.overrides[key]
            if content is None:
                raise FetchError(f"模擬下載失敗：{url}")
            ctype = "application/pdf" if content.startswith(b"%PDF") else "text/html; charset=utf-8"
            return Response(key, content, ctype)
        entry = self.manifest.get(key)
        if entry is None:
            raise FetchError(f"沒有對應的 fixture：{url}")
        return Response(key, (FIXTURES / entry["file"]).read_bytes(), entry.get("content_type", ""))


def fixture_url(pattern: str) -> str:
    """完整 URL 精確比對，否則以子字串（比對解碼後的 URL）找出 manifest 中唯一的 URL。"""
    if pattern in MANIFEST:
        return pattern
    hits = [u for u in MANIFEST if pattern in unquote(u)]
    assert len(hits) == 1, f"{pattern!r} 對應到 {hits}"
    return hits[0]


def fixture_bytes(pattern: str) -> bytes:
    return (FIXTURES / MANIFEST[fixture_url(pattern)]["file"]).read_bytes()


def fixture_text(pattern: str) -> str:
    return fixture_bytes(pattern).decode("utf-8-sig")


@pytest.fixture
def fetcher() -> FixtureFetcher:
    return FixtureFetcher()


def by_id(events) -> dict:
    return {e.id: e for e in events}
