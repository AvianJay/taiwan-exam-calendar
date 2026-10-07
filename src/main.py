"""Pipeline 進入點：官方網站 → scraper → normalize → validation → JSON。

用法：
    python -m src.main                     # 執行全部 scraper，有變更才寫檔
    python -m src.main --only ceec,cap     # 只執行部分 scraper（其他來源資料保留）
    python -m src.main --dry-run           # 只檢查，不寫檔
    python -m src.main --save-raw raw/     # 保存下載的原始 HTML/PDF（除錯用）

結束代碼：0 = 成功（不論是否有變更）；1 = 任一 scraper 失敗或驗證失敗（不寫入任何檔案）。
GitHub Actions 中會把 changed=true/false 寫入 $GITHUB_OUTPUT，並輸出執行摘要。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import traceback
from pathlib import Path

from .dates import DateParseError
from .fetch import FetchError, Fetcher, HttpFetcher, utf8_stdio
from .models import ScrapeResult, ScraperError
from .normalize import build_document
from .scrapers.base import ScraperSpec
from .scrapers.registry import ALL_SPECS, get_specs
from .store import has_changes, load, merge, sources_canonical, write
from .validate import ValidationReport, validate_document

ROOT = Path(__file__).resolve().parent.parent
README_START = "<!-- SOURCES:START -->"
README_END = "<!-- SOURCES:END -->"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_scrapers(specs: list[ScraperSpec], fetcher: Fetcher) -> tuple[list[ScrapeResult], list[tuple[ScraperSpec, str]]]:
    results: list[ScrapeResult] = []
    failures: list[tuple[ScraperSpec, str]] = []
    for spec in specs:
        print(f"→ {spec.key}：{spec.name}", flush=True)
        try:
            out = spec.run(fetcher)
            if not out:
                raise ScraperError("scraper 沒有回傳任何結果")
            for r in out:
                if len(r.events) < spec.min_events:
                    raise ScraperError(f"{r.academic_year} 學年度只解析出 {len(r.events)} 筆事件（至少需要 {spec.min_events}）")
                print(f"  ✓ {r.academic_year} 學年度：{len(r.events)} 筆事件，{len(r.cross_checks)} 筆交叉驗證宣稱")
                for w in r.warnings:
                    print(f"  ! {w}")
            results += out
        except (ScraperError, FetchError, DateParseError) as exc:
            failures.append((spec, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001 - 任何未預期錯誤都要讓 pipeline 失敗並保留 traceback
            failures.append((spec, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
            print(f"  ✗ 未預期錯誤：{exc}", flush=True)
    return results, failures


def build_sources(specs: list[ScraperSpec], results: list[ScrapeResult], old: dict | None, now: str) -> dict:
    by_key = {r.source_key: r for r in results}
    old_by_key = {s["key"]: s for s in (old or {}).get("sources", [])}
    sources = []
    for spec in ALL_SPECS:
        r = by_key.get(spec.key)
        if r is None:
            if spec.key in old_by_key:
                sources.append(old_by_key[spec.key])
            continue
        sources.append({
            "key": spec.key,
            "name": spec.name,
            "exams": spec.exams,
            "organizer": spec.organizer,
            "official": True,
            "homepage": spec.homepage,
            "status": "active",
            "academic_year": r.academic_year,
            "event_count": len(r.events),
            "source_url": r.source_url,
            "source_title": r.source_title,
            "warnings": r.warnings,
            "skipped_items": r.skipped_items,
            # 只在檔案因內容變更而重寫時才會寫入；單純時間不同不會造成 commit（見 sources_canonical）
            "last_success_at": now,
        })
    return {"schema_version": 1, "sources": sources}


def render_sources_table(sources: dict) -> str:
    lines = [
        "| 來源 | 考試／管道 | 官方 | 狀態 | 目前資料學年度 | 事件數 | 最後成功抓取（UTC） | 備註 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in sources.get("sources", []):
        note = "；".join(s.get("warnings") or []) or "—"
        note = re.sub(r"（https?://[^）]+）", "", note).replace("|", "／")
        lines.append(
            f"| [{s['name']}]({s['homepage']}) | {s['exams']} | {'Yes' if s.get('official') else 'No'} | "
            f"{s['status'].capitalize()} | {s.get('academic_year', '—')} | {s.get('event_count', '—')} | "
            f"{s.get('last_success_at', '—')} | {note} |"
        )
    return "\n".join(lines)


def update_readme(path: Path, sources: dict) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return False
    head, rest = text.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    new = f"{head}{README_START}\n{render_sources_table(sources)}\n{README_END}{tail}"
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
        return True
    return False


def write_summary(lines: list[str]) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def set_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def summarize(results, failures, report: ValidationReport | None, merge_report=None, changed=None) -> list[str]:
    lines = ["## Taiwan Exam Calendar 更新結果", ""]
    lines += ["| 來源 | 學年度 | 事件數 | 狀態 |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.name} | {r.academic_year} | {len(r.events)} | ✅ |")
    for spec, err in failures:
        lines.append(f"| {spec.name} | — | — | ❌ {err.splitlines()[0][:200]} |")
    lines.append("")
    if changed is not None:
        lines.append(f"**資料變更：{'是' if changed else '否'}**")
    if merge_report:
        for label, items in (("新增", merge_report.added), ("移除", merge_report.removed), ("變更", merge_report.changed)):
            if items:
                lines.append(f"- {label}（{len(items)}）：" + ", ".join(f"`{i}`" for i in items[:60]))
    warnings = [w for r in results for w in r.warnings]
    if merge_report:
        warnings += merge_report.warnings
    if report:
        warnings += report.warnings
    if warnings:
        lines += ["", "### ⚠️ 警告"] + [f"- {w}" for w in warnings]
    errors = (report.errors if report else []) + (merge_report.errors if merge_report else [])
    if errors:
        lines += ["", "### ❌ 驗證錯誤"] + [f"- {e}" for e in errors[:100]]
    if report and report.infos:
        lines += ["", "<details><summary>交叉驗證紀錄</summary>", ""] + [f"- {i}" for i in report.infos] + ["", "</details>"]
    return lines


def main(argv: list[str] | None = None, fetcher: Fetcher | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Taiwan Exam Calendar scraper")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "exams.json")
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "sources.json")
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument("--only", help="只執行指定 scraper（逗號分隔），例如 ceec,cap")
    parser.add_argument("--dry-run", action="store_true", help="只解析與驗證，不寫入任何檔案")
    parser.add_argument("--save-raw", type=Path, help="保存下載的原始檔案到此目錄")
    args = parser.parse_args(argv)

    specs = get_specs(args.only.split(",") if args.only else None)
    fetcher = fetcher or HttpFetcher(save_dir=args.save_raw)
    now = utc_now()

    results, failures = run_scrapers(specs, fetcher)
    if failures:
        print("\n✗ 有 scraper 失敗，不更新任何資料：")
        for spec, err in failures:
            print(f"::error title={spec.key}::{err.splitlines()[0]}")
        write_summary(summarize(results, failures, None))
        set_output("changed", "false")
        return 1

    old_doc = load(args.data)
    events, merge_report = merge(old_doc, results, now)
    doc = build_document(events, now)
    report = validate_document(doc, cross_checks=[c for r in results for c in r.cross_checks])
    errors = merge_report.errors + report.errors
    for w in merge_report.warnings + report.warnings:
        print(f"::warning::{w}")
    if errors:
        for e in errors:
            print(f"::error::{e}")
        print(f"\n✗ 驗證失敗（{len(errors)} 個錯誤），不更新任何資料")
        write_summary(summarize(results, [], report, merge_report))
        set_output("changed", "false")
        return 1

    changed = has_changes(old_doc, doc)
    old_sources = load(args.sources)
    sources = build_sources(specs, results, old_sources, now)
    sources_changed = sources_canonical(old_sources) != sources_canonical(sources)

    print(f"\n✓ 驗證通過：共 {len(doc['events'])} 筆事件")
    print(f"  新增 {len(merge_report.added)}、移除 {len(merge_report.removed)}、變更 {len(merge_report.changed)}")
    print(f"  資料變更：{'是' if changed else '否（只有時間戳記不同時不寫檔）'}；來源狀態變更：{'是' if sources_changed else '否'}")

    if not args.dry_run:
        if changed:
            write(args.data, doc)
        if changed or sources_changed:
            write(args.sources, sources)
            update_readme(args.readme, sources)
    set_output("changed", "true" if (changed or sources_changed) and not args.dry_run else "false")
    write_summary(summarize(results, [], report, merge_report, changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
