"""端對端：以 fixtures 回放全部官方來源，跑完整 pipeline。"""

import json

import pytest

from src import main as pipeline
from src.scrapers import ceec
from src.validate import validate_document
from tests.conftest import FixtureFetcher, fixture_url

README = """# test
<!-- SOURCES:START -->
(舊表格)
<!-- SOURCES:END -->
尾巴
"""


@pytest.fixture
def paths(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    readme = tmp_path / "README.md"
    readme.write_text(README, encoding="utf-8")
    return {
        "data": tmp_path / "data" / "exams.json",
        "sources": tmp_path / "data" / "sources.json",
        "readme": readme,
        "gh_output": out,
        "summary": tmp_path / "summary.md",
    }


def run(paths, fetcher=None, *extra) -> int:
    args = ["--data", str(paths["data"]), "--sources", str(paths["sources"]), "--readme", str(paths["readme"]), *extra]
    return pipeline.main(args, fetcher=fetcher or FixtureFetcher())


def last_output(paths) -> str:
    return paths["gh_output"].read_text(encoding="utf-8").strip().splitlines()[-1]


def test_full_pipeline_then_idempotent(paths):
    assert run(paths) == 0
    data = json.loads(paths["data"].read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert validate_document(data).ok
    ids = {e["id"] for e in data["events"]}
    for required in ("ceec-gsat-116", "ceec-ast-116", "ceec-english-listening-116-1", "ceec-english-listening-116-2",
                     "cap-116", "tech-test-115", "jctv-apply-115-release", "cac-star-115-release",
                     "cac-apply-115-release", "uac-115-release"):
        assert required in ids
    gsat = next(e for e in data["events"] if e["id"] == "ceec-gsat-116")
    assert (gsat["registration_start"], gsat["registration_end"], gsat["result_date"]) == (
        "2026-10-27", "2026-11-10", "2027-02-25")
    assert last_output(paths) == "changed=true"

    sources = json.loads(paths["sources"].read_text(encoding="utf-8"))
    assert {s["key"] for s in sources["sources"]} >= {"ceec", "cap", "tcte", "uac"}
    readme = paths["readme"].read_text(encoding="utf-8")
    assert "(舊表格)" not in readme and "大學入學考試中心" in readme and readme.endswith("尾巴\n")

    # 第二次執行：內容相同（只有時間戳記會不同）→ 不寫檔
    before = (paths["data"].read_bytes(), paths["sources"].read_bytes(), paths["readme"].read_bytes())
    assert run(paths) == 0
    after = (paths["data"].read_bytes(), paths["sources"].read_bytes(), paths["readme"].read_bytes())
    assert before == after
    assert last_output(paths) == "changed=false"


def test_scraper_failure_fails_without_writing(paths):
    assert run(paths) == 0
    before = paths["data"].read_bytes()
    broken = FixtureFetcher({ceec.HOME_URL: "<html><body>網站維護中</body></html>".encode()})
    assert run(paths, broken) == 1
    assert paths["data"].read_bytes() == before
    assert last_output(paths) == "changed=false"
    assert "❌" in paths["summary"].read_text(encoding="utf-8")


def test_failure_on_first_run_never_creates_empty_json(paths):
    broken = FixtureFetcher({fixture_url("116學年度簡章.pdf"): None, fixture_url("116學年度考試重要試務日期.pdf"): None})
    assert run(paths, broken) == 1
    assert not paths["data"].exists()


def test_dry_run_writes_nothing(paths):
    assert run(paths, None, "--dry-run", "--only", "tcte,uac") == 0
    assert not paths["data"].exists()
    assert last_output(paths) == "changed=false"


def test_partial_run_keeps_other_sources(paths):
    assert run(paths) == 0
    total = len(json.loads(paths["data"].read_text(encoding="utf-8"))["events"])
    assert run(paths, None, "--only", "uac") == 0
    assert len(json.loads(paths["data"].read_text(encoding="utf-8"))["events"]) == total
