"""所有 scraper 的登錄表。新增來源時，在對應模組定義 ScraperSpec 並加到這裡。"""

from __future__ import annotations

from . import admission, cap, ceec, tech
from .base import ScraperSpec

ALL_SPECS: list[ScraperSpec] = [ceec.SPEC, cap.SPEC, *tech.SPECS, *admission.SPECS]


def get_specs(only: list[str] | None = None) -> list[ScraperSpec]:
    if not only:
        return list(ALL_SPECS)
    keys = {s.key for s in ALL_SPECS}
    unknown = [k for k in only if k not in keys]
    if unknown:
        raise SystemExit(f"未知的 scraper：{unknown}；可用：{sorted(keys)}")
    return [s for s in ALL_SPECS if s.key in only]
