# Taiwan Exam Calendar

從台灣**官方**教育考試／升學網站抓取最新的考試與升學重要日期（報名、考試、成績公布、複查、放榜、志願選填…），
整理成機器可讀的 JSON：[`data/exams.json`](data/exams.json)。Flutter App、網頁或 API 可以直接使用。

```
官方網站 → scraper → normalize → validation → JSON → Git commit（GitHub Actions 每週一次）
```

本專案只處理「日期與升學重要事件」，不是題庫。

- **不寫死年度**：每個 scraper 都從官方網站找出最新可用的學年度；明年大考中心換成 117 學年度，程式不用改。
- **年份不硬算**：不用「學年度 + 1911」推算考試年份。日期一律取自官方文件；會考日程表沒印年份，就用文件上印的「星期」反推西元年。
- **Fail loudly**：官方網站結構改變、抓不到資料、解析結果不合理時，GitHub Actions 直接失敗，**不會**產生空的或錯誤的 JSON。
- **可追查**：每個事件都記錄 `source_url`、`source_title`、`source_text`（官方原文）與 `last_verified_at`。

## 支援的考試與管道

| Exam | Source | Official | Status |
|---|---|---|---|
| 學科能力測驗（學測） | [大學入學考試中心 CEEC](https://www.ceec.edu.tw/) 考試簡章 PDF | Yes | Active |
| 分科測驗 | CEEC 考試簡章 PDF | Yes | Active |
| 高中英語聽力測驗（第一次、第二次） | CEEC 考試簡章 PDF | Yes | Active |
| 國中教育會考 | [國中教育會考網站](https://cap.rcpet.edu.tw/) 重要日程表 PDF | Yes | Active |
| 國中教育會考補考 | 同上（官方日程表有列出時才會產生 `cap-{學年度}-make-up`） | Yes | Active（目前官方未公布） |
| 免試入學、特色招生、五專入學等國中升學管道 | 同上（國教署函頒之適性入學重要日程表） | Yes | Active |
| 四技二專統一入學測驗（統測） | [技專校院入學測驗中心 TCTE](https://www.tcte.edu.tw/) 重要日程表 | Yes | Active |
| 四技二專甄選入學 | [技專校院招生委員會聯合會 JCTV](https://www.jctv.ntut.edu.tw/enter42/apply/) 重要日程表 PDF | Yes | Active |
| 四技二專技優甄審 | [JCTV](https://www.jctv.ntut.edu.tw/enter42/skill/) 甄審招生重要日程表 PDF | Yes | Active |
| 四技二專日間部聯合登記分發 | [JCTV](https://www.jctv.ntut.edu.tw/union42/) 重要日程表 PDF | Yes | Active |
| 大學繁星推薦 | [大學甄選入學委員會 CAC](https://www.cac.edu.tw/) 重要時程 | Yes | Active |
| 大學個人申請 | CAC 重要時程 | Yes | Active |
| 大學分發入學 | [大學考試入學分發委員會 UAC](https://www.uac.edu.tw/flow.htm) 重要時程 | Yes | Active |
| 大學術科考試 | 大學術科考試委員會聯合會 | Yes | 未實作（日期僅出現在 CAC/UAC 頁面，作為參考） |
| 科技校院繁星計畫、四技申請入學、特殊選才、二技 | JCTV / 各招生委員會 | Yes | 未實作（見「已知限制」） |

每個來源的詳細對照（探索路徑、解析方式、產生的事件 ID、交叉驗證）請見 [`docs/SOURCES.md`](docs/SOURCES.md)。

### 來源狀態（自動更新）

下表由 pipeline 依 [`data/sources.json`](data/sources.json) 產生，只在資料有變更時更新。
每週執行的即時結果（含警告與交叉驗證紀錄）請看 GitHub Actions 的執行摘要。

<!-- SOURCES:START -->
| 來源 | 考試／管道 | 官方 | 狀態 | 目前資料學年度 | 事件數 | 最後成功抓取（UTC） | 備註 |
|---|---|---|---|---|---|---|---|
| [大學入學考試中心（CEEC）](https://www.ceec.edu.tw/) | 高中英語聽力測驗、學科能力測驗、分科測驗 | Yes | Active | 116 | 35 | 2026-10-07T11:47:17Z | — |
| [國中教育會考（CAP）／國中適性入學](https://cap.rcpet.edu.tw/) | 國中教育會考、免試入學、特色招生、五專入學等 | Yes | Active | 116 | 35 | 2026-10-07T11:47:17Z | — |
| [技專校院入學測驗中心（TCTE）](https://www.tcte.edu.tw/) | 四技二專統一入學測驗（統測） | Yes | Active | 115 | 10 | 2026-10-07T11:47:17Z | — |
| [技專校院招生委員會聯合會（JCTV）四技二專甄選入學](https://www.jctv.ntut.edu.tw/enter42/apply/) | 四技二專甄選入學 | Yes | Active | 115 | 14 | 2026-10-07T11:47:17Z | 四技二專甄選入學 116 學年度重要日程尚未公布 |
| [技專校院招生委員會聯合會（JCTV）四技二專技優甄審入學](https://www.jctv.ntut.edu.tw/enter42/skill/) | 四技二專技優甄審入學 | Yes | Active | 115 | 12 | 2026-10-07T11:47:17Z | 四技二專技優甄審入學 116 學年度重要日程尚未公布 |
| [技專校院招生委員會聯合會（JCTV）四技二專日間部聯合登記分發](https://www.jctv.ntut.edu.tw/union42/) | 四技二專日間部聯合登記分發 | Yes | Active | 115 | 13 | 2026-10-07T11:47:17Z | 四技二專日間部聯合登記分發 116 學年度重要日程尚未公布 |
| [大學甄選入學委員會（CAC）大學繁星推薦](https://www.cac.edu.tw/cacportal/index.php) | 大學繁星推薦 | Yes | Active | 115 | 11 | 2026-10-07T11:47:17Z | 大學繁星推薦 116 學年度重要時程尚未公布 |
| [大學甄選入學委員會（CAC）大學個人申請](https://www.cac.edu.tw/cacportal/index.php) | 大學個人申請 | Yes | Active | 115 | 12 | 2026-10-07T11:47:17Z | 大學個人申請 116 學年度重要時程尚未公布 |
| [大學考試入學分發委員會（UAC）](https://www.uac.edu.tw/) | 大學分發入學 | Yes | Active | 115 | 9 | 2026-10-07T11:47:17Z | — |
<!-- SOURCES:END -->

> 「目前資料學年度」比最新學年度舊，代表官方尚未公布新年度日程（例如 CAC、JCTV 通常在 11～12 月公布下一學年度簡章）。
> 官方一公布，下一次排程就會自動抓到，舊年度資料會保留作為歷史紀錄。

## 資料格式

`data/exams.json`（完整定義：[`schema/exams.schema.json`](schema/exams.schema.json)，JSON Schema 2020-12）

```json
{
  "schema_version": 1,
  "updated_at": "2026-10-07T12:00:00Z",
  "events": [
    {
      "id": "ceec-gsat-116",
      "academic_year": 116,
      "category": "university",
      "type": "exam",
      "exam": "gsat",
      "name": "學科能力測驗",
      "organizer": "CEEC",
      "start_date": "2027-01-22",
      "end_date": "2027-01-24",
      "registration_start": "2026-10-27",
      "registration_end": "2026-11-10",
      "result_date": "2027-02-25",
      "note": null,
      "source_url": "https://www.ceec.edu.tw/files/file_pool/1/0q215601929252011195/116%e5%ad%b8%e5%b9%b4%e5%ba%a6%e7%b0%a1%e7%ab%a0.pdf",
      "source_title": "116學年度考試簡章（考試重要試務日期）",
      "source_text": "考試｜116.01.22(五)~116.01.24(日)",
      "last_verified_at": "2026-10-07T12:00:00Z"
    }
  ]
}
```

| 欄位 | 說明 |
|---|---|
| `id` | Deterministic ID（不使用 UUID），格式見下方 |
| `academic_year` | 官方文件標示的學年度（民國年）。**注意**：116 學年度的大學入學考試，英聽在 2026 年、學測在 2027 年 |
| `category` | `university`、`high_school`、`junior_high`、`technical`、`admission`、`other` |
| `type` | `exam`、`registration`、`result`、`review`、`admission`、`announcement`、`other` |
| `exam` | 考試／管道代碼（`gsat`、`ast`、`english-listening`、`cap`、`tcte`、`star`、`apply`、`uac`…） |
| `start_date` / `end_date` | `YYYY-MM-DD`（台灣時間）。只有一天時兩者相同 |
| `registration_start` / `registration_end` / `result_date` | 只在 `type=exam` 的事件中、且官方文件有對應項目時填入，否則為 `null`（不推測） |
| `note` | 官方註記的時間（例如「上午9時起；下午5時止」「日期由各校自訂」），沒有則 `null` |
| `organizer` | `CEEC`、`CAP`、`K12EA`（教育部國教署）、`TCTE`、`JCTV`、`CAC`、`UAC` |
| `source_url` / `source_title` / `source_text` | 日期出處（網址、文件標題、官方原文） |
| `last_verified_at` | 該事件最後一次被官方來源驗證並寫入的時間（UTC） |

**Category 對應**

| category | 內容 |
|---|---|
| `university` | 大學入學考試：英聽、學測、分科測驗 |
| `admission` | 大學入學管道：繁星推薦、個人申請、分發入學 |
| `technical` | 技職體系：統測、四技二專甄選入學、技優甄審、聯合登記分發 |
| `junior_high` | 國中教育會考 |
| `high_school` | 國中升高中職／五專：免試入學、特色招生、五專入學、科學班、體育班… |

**Event ID 規則**

| 範例 | 意義 |
|---|---|
| `ceec-gsat-116` / `ceec-ast-116` | 學測／分科測驗考試本身 |
| `ceec-english-listening-116-1` | 英聽第一次考試（`-2` 為第二次） |
| `ceec-gsat-116-registration`、`-result`、`-review`、`-score-report`、`-review-result`、`-answers`、`-seat-announcement` | 同一考試的其他事件 |
| `cap-116`、`cap-116-registration`、`cap-116-result`、`cap-116-make-up` | 會考、會考報名、成績、補考 |
| `k12ea-116-free-admission-release` | 國中升學管道（免試入學放榜） |
| `tech-test-116`、`tech-test-116-registration` | 統測 |
| `jctv-apply-116-registration`、`jctv-skill-116-release`、`jctv-union-116-preference-registration` | 四技二專各管道 |
| `cac-star-116-release`、`cac-apply-116-screening-result`、`uac-116-release` | 大學各入學管道 |

`data/sources.json` 記錄每個來源最近一次的狀態：學年度、事件數、來源網址、警告，以及官方文件中有日期但
不在對照規則內而略過的項目（`skipped_items`，透明記錄、不會默默丟掉）。

## 更新頻率與 GitHub Actions

[`.github/workflows/update.yml`](.github/workflows/update.yml)：

1. **每週一 09:23（台灣時間）** 自動執行，也可在 Actions 頁面手動觸發（`workflow_dispatch`）。
2. 安裝依賴 → 執行離線測試（`pytest`，使用 fixtures，不連網）。
3. `python -m src.main` 執行全部 scraper：
   - 任一 scraper 失敗（抓不到、格式改變、必要事件缺漏、事件數驟減）→ **exit 1，不寫任何檔案**，workflow 失敗。
   - 合併後的資料通過 JSON Schema 與語意驗證才會寫檔。
   - 新舊資料先 canonicalize（排除 `updated_at`、`last_verified_at`）再比較；**只有時間戳記不同時不寫檔、不 commit**。
4. `python -m src.validate data/exams.json` 再驗證一次寫出的檔案。
5. 有實質變更才 commit：`chore(data): update Taiwan exam calendar`。
6. 失敗時會把下載的原始 HTML／PDF 上傳成 artifact（保留 14 天）方便除錯。

[`.github/workflows/test.yml`](.github/workflows/test.yml) 在 push／PR 時執行測試並驗證已提交的資料。

### 驗證規則

| 類型 | 規則 |
|---|---|
| 格式 | 日期必須是有效的 `YYYY-MM-DD`；JSON Schema 不允許多餘欄位或未知的 category/type |
| 區間 | `start_date <= end_date`；報名開始 <= 報名截止；區間不超過 400 天 |
| 學年度 | 介於 100 與「今年民國年 + 2」之間；N 學年度的日期必須落在西元 N+1909～N+1912 年 |
| 唯一性 | event ID 不得重複；兩個來源不得產生相同 ID |
| 必填 | `source_url`（http/https）、`name`、`organizer`、`source_title` 不得為空 |
| 日期衝突 | 考試的報名截止不得晚於考試開始、成績公布不得早於考試結束；考試事件的報名欄位必須與 `-registration` 事件一致 |
| 星期 | 官方文件有印星期的日期，星期必須正確（不一致即解析錯誤） |
| 防覆蓋 | 官方網站若退回顯示較舊學年度，資料檔中較新年度的事件保持不動（警告） |
| 防退化 | 同一來源同一學年度事件數比上次少 40% 以上 → 失敗 |
| 必要事件 | 每個來源都有必須存在的事件（例如 `ceec-gsat-{y}`、`cap-{y}-registration`），缺一不可 |
| 不產生空檔 | `events` 為空直接失敗 |

### 不相信單一來源（交叉驗證）

Primary 來源永遠是主辦單位自己的官方文件。其他官方頁面上「轉述」的日期只做交叉驗證，**不一致時發出警告，絕不覆蓋**：

- CEEC 簡章的「重要試務日期」表 ↔ 同一份簡章的「重要行事曆」（不一致 → 失敗，代表解析錯誤）
- CEEC 簡章 ↔ CEEC 首頁另一份獨立的「重要日程」PDF（逐格比對）
- CEEC 學測／分科／英聽 ↔ UAC 分發入學時程、CAC 繁星／申請時程
- 會考日程表 ↔ 會考網站歷史訊息「XXX年國中教育會考考試日期訂於…」公告
- 統測 ↔ JCTV 甄選入學、聯合登記分發日程表
- CAC 繁星／申請「聲明放棄」日期 ↔ UAC 時程

## 本地執行

需要 Python 3.11 以上（CI 使用 3.13）。

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ocr.txt  # 選用：OCR fallback

python -m pytest                     # 離線測試
python -m src.main --dry-run         # 抓取並驗證，但不寫檔
python -m src.main                   # 抓取，有變更才寫入 data/
python -m src.main --only ceec,cap   # 只跑部分來源（其他來源資料保留）
python -m src.main --save-raw raw/   # 保存下載的原始檔案（除錯用）
python -m src.validate data/exams.json
python scripts/update_fixtures.py    # 重新錄製測試 fixtures（需要網路）
```

### 專案結構

```
src/
  fetch.py          HTTP 下載（重試、節流、TWCA 憑證相容、PDF 檢查）
  dates.py          民國／西元、學年度、星期驗證、以星期反推年份
  pdf_utils.py      PDF 文字／表格（合併儲存格展開）／格線分列／OCR fallback
  models.py         Event、CrossCheck、ScrapeResult
  normalize.py      輸出格式、考試摘要欄位、canonical JSON
  validate.py       JSON Schema + 語意驗證 + 交叉驗證（也可單獨執行）
  store.py          與舊資料合併、防覆蓋、防退化、變更偵測
  main.py           pipeline 進入點
  scrapers/
    ceec.py         英聽、學測、分科
    cap.py          會考、國中適性入學
    tech.py         統測（TCTE）、四技二專各管道（JCTV）
    admission.py    繁星推薦、個人申請（CAC）、分發入學（UAC）
    registry.py     scraper 登錄表
schema/exams.schema.json
data/exams.json, data/sources.json
tests/              parser／日期／驗證／合併／端對端測試；fixtures/ 為官方網站的離線快照
docs/SOURCES.md     scraper source mapping
```

## 新增 scraper

1. 在 `src/scrapers/` 新增模組（或加到既有模組），實作 `scrape(fetcher) -> list[ScrapeResult]`：
   1. **找出最新學年度**：從官方頁面的標題／連結動態取得，不寫死年份或檔案 URL。
   2. **取得官方資料**：一律透過 `fetcher.get()`（測試時會換成 fixture）；PDF 用 `.expect_pdf()` 確認真的拿到 PDF。
   3. **解析日期**：用 `src.dates` 的工具（`parse_roc_range`、`find_roc_dates` 會驗證星期）。
   4. **正規化**：用 `Rule` 把官方項目文字對應到 `suffix`／`type`／名稱，用 `EventBuilder` 產生事件（同一 ID 日期不同會直接報錯）。
   5. **保留出處**：`source_url`、`source_title`、`source_text`。
   6. 回傳 `ScrapeResult`，`id_prefixes` 宣告此來源擁有的 ID 前綴（合併時只替換這些事件）。
   7. 其他網站轉述的日期請產生 `CrossCheck`，不要產生事件。
2. 定義 `ScraperSpec`（`required` 列出必須存在的事件、`min_events`），加入 `src/scrapers/registry.py`。
3. 執行 `python scripts/update_fixtures.py` 錄製 fixtures，在 `tests/` 加上 parser 測試。
4. 更新本 README 的支援表與 `docs/SOURCES.md`。

**解析不到就丟 `ScraperError`**，不要回傳部分結果或空清單。

## 已知限制

- **官方新學年度公布時間不同**：CAC（繁星、申請）、JCTV（四技二專各管道）、TCTE（統測）通常在 11～12 月才公布下一學年度日程；
  在那之前資料會是上一學年度（已過期的日期），`sources.json` 與上表會註記「尚未公布」。
- **CEEC「重要日程」獨立 PDF 沒有中文文字層**（字型缺 ToUnicode），因此以簡章 PDF 為主要來源；
  簡章無法使用時才以 OCR（RapidOCR）辨識獨立 PDF 的列標題，日期仍取自文字層。OCR 結果需人工留意 Actions 警告。
- **官方延期或臨時異動**（例如颱風延期）若只以新聞稿公告、未更新日程表，本專案不會自動得知；
  交叉驗證若發現不同官方頁面日期不一致，會在 Actions 摘要中警告。
- **「日期由各校自訂」的項目**（甄試、指定項目甄審等）只記錄官方公告的期間範圍，實際日期依各校而定（`note` 欄位會註明）。
- **未對應的官方項目**（例如身心障礙考生應考服務、運動績優生、特定縣市安置作業）不會轉成事件，但會列在 `sources.json` 的 `skipped_items`。
- **台北、新北等五市的身心障礙學生適性輔導安置、各區特色招生細節**以各區簡章為準，本專案不處理。
- 未實作的管道（大學術科考試、科技校院繁星計畫、四技申請入學、特殊選才、二技）尚未找到穩定的單一官方日程表格式，
  依原則不硬寫 scraper。
- 官方網站可能封鎖境外 IP；目前（2026-10）從境外連線測試皆正常。若未來被封鎖，workflow 會失敗並保留原始回應供檢查。

## 既有專案研究（不重複造輪子）

開始實作前研究了以下專案：

| 專案 | 內容 | 結論 |
|---|---|---|
| [niansia/taiwan-exam](https://github.com/niansia/taiwan-exam)（MIT） | 學測模擬試題產生器；`scripts/download_ceec_gsat.py` 從 CEEC「歷屆試題」列表（`xmfile?xsmsid=...`）分頁抓 file_pool PDF | 只抓考古題與統計資料，**沒有任何日程解析**；年度靠參數與分頁，非自動偵測。參考了其下載重試／退避與 `%PDF` 檢查的做法 |
| [5219rayhsu/open-book-is-good-skill](https://github.com/5219rayhsu/open-book-is-good-skill)（MIT） | 以官方考古題建立自學題庫的 Claude skill；CEEC 數學考古題 scraper、會考試題的 Google Drive 下載說明 | 同樣只處理題目，年份寫死；**沒有可用的 CAP 日程 scraper**。參考了「抓不到資料就中止、不覆寫舊結果」的防呆原則 |

兩者都沒有考試日期資料可直接使用，也不需要引入其題庫 pipeline；本專案的 parser 皆針對各官方「重要日程」文件重新撰寫。

## 資料來源與版權注意事項

- 所有日期資料皆來自各主辦單位的官方網站（見上表與 `docs/SOURCES.md`），每筆事件都附原始出處。
  **一切請以官方最新公告為準**；本專案資料僅供參考，若有出入以官方為準。
- 考試日期屬於事實資訊；本專案不重新散布官方簡章或文件全文。`tests/fixtures/` 內的官方網頁／PDF 快照僅供離線測試解析器使用，
  其著作權屬原單位；若權利人不同意收錄，請開 issue，我們會改為測試時才下載。
- 抓取頻率為每週一次、同一主機請求間隔至少 0.6 秒，User-Agent 會標示本專案（在 Actions 中附上 repository 網址）。
- 程式碼以 MIT 授權釋出（見 [LICENSE](LICENSE)）。
