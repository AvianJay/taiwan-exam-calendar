# Scraper source mapping

每個 scraper 從哪裡找到最新學年度、讀哪一份官方文件、怎麼解析、產生哪些事件、和誰交叉驗證。
（2026-10-07 實測；`{y}` 代表學年度）

## `ceec` — 大學入學考試中心：英聽、學測、分科測驗

| 項目 | 內容 |
|---|---|
| 入口 | https://www.ceec.edu.tw/ |
| 學年度探索 | 首頁 `div.IndexExamForm` 的標題「`{y}學年度考試簡章`」；後備：全頁搜尋檔名 `{y}學年度簡章.pdf`／`{y}學年度考試重要試務日期.pdf` 取最大年度 |
| Primary 文件 | 該區塊「簡章」連結（`/files/file_pool/1/<每年不同的 id>/{y}學年度簡章.pdf`）。file_pool URL 每年都變，一律從首頁取得 |
| 解析 | 在前 12 頁找「`{y}學年度考試重要試務日期`」頁 → pdfplumber 表格 → 展開合併儲存格 → 依表頭對應四欄（英聽一、英聽二、學測、分科），依列標題對應事件種類。簡章內頁學年度必須與首頁一致 |
| 同文件驗證 | 同一份簡章的「考試重要行事曆」頁（逐行「日期 項目」），任一日期不一致 → 失敗 |
| 第二份官方文件 | 首頁「重要日程」連結的獨立 PDF（`{y}學年度考試重要試務日期.pdf`）逐格比對日期，不一致 → 警告 |
| OCR fallback | 簡章不可用時改用獨立 PDF；該 PDF 中文字型缺 ToUnicode，列標題以 RapidOCR 辨識（逐格裁切＋白邊），日期仍取自文字層 |
| 事件 | `ceec-brochure-{y}`；`ceec-{exam}-{y}[-{n}]` 及 `-registration`、`-registration-check`、`-seat-announcement`、`-answers`、`-result`、`-score-report`、`-review`、`-review-result`（exam = `english-listening`（n=1,2）、`gsat`、`ast`） |
| 必要事件 | 四項考試本身與報名、學測／分科成績公布 |
| 刻意略過 | 身心障礙及重大傷病考生應考服務相關列 |

## `cap` — 國中教育會考、國中適性入學

| 項目 | 內容 |
|---|---|
| 入口 | https://cap.rcpet.edu.tw/（後備：`history.html`） |
| 學年度探索 | 首頁連結文字／檔名符合「`{y}學年度國中教育會考…重要日程表`」的 PDF，取最大年度 |
| Primary 文件 | `documents/{y}學年度國中教育會考及全國高級中等學校與專科學校五年制適性入學重要日程表.pdf`（教育部國教署函頒） |
| 解析 | 版面為左右兩欄的「月份區塊 × (日, 星期, 辦理事項)」，**不印年份**。以「辦理事項」表頭定位區塊與欄位；以橫跨辦理事項欄的細格線切列；以每個區塊印出的星期反推西元年（候選 N+1910～N+1912，必須唯一）；項目自帶日期（「4日-6日：國中教育會考報名」）時以項目日期為準，且起始日必須在該列日期內 |
| 交叉驗證 | `history.html`「`{y}年國中教育會考考試日期訂於…`」公告 → `cap-{y}` |
| 事件 | `cap-{y}`（會考）、`cap-{y}-registration`、`-admission-ticket`、`-result`、`-review`、`-make-up`（官方有列出時）；`k12ea-{y}-*`（免試入學志願選填／放榜／報到、優先免試、特色招生考試、五專各管道、技優甄審、科學班、藝才班、體育班、直升入學、學習區完全免試、建教合作班） |
| 必要事件 | `cap-{y}`、`cap-{y}-registration`、`cap-{y}-result` |

## `tcte` — 技專校院入學測驗中心：統測

| 項目 | 內容 |
|---|---|
| 入口 | https://www.tcte.edu.tw/index.php?mod=TVETest/info4y（四技二專資訊） |
| 學年度探索 | 標題「`{y}學年度四技二專統一入學測驗重要日程表`」 |
| 解析 | 標題後第一個 HTML 表格，處理 rowspan（例如「成績公告與查詢」底下三列） |
| 事件 | `tech-test-{y}`、`-registration`、`-registration-check`、`-admission-ticket`、`-seat-announcement`、`-answers`、`-result`、`-score-report`、`-review`、`-review-result` |
| 必要事件 | 考試、報名、成績公告 |
| 備註 | 新學年度日程通常在簡章開放下載（約 11 月）後才更新到此頁 |

## `jctv-apply`／`jctv-skill`／`jctv-union` — 技專校院招生委員會聯合會

| 項目 | 內容 |
|---|---|
| 入口 | https://www.jctv.ntut.edu.tw/enter42/apply/、`/enter42/skill/`、`/union42/` |
| 學年度探索 | 管道首頁 `<title>` 的「`{y}學年度`」，以及「重要日程」連結的 `subId` |
| Primary 文件 | `contents.php?academicYear={y}&subId=…` 頁中的「招生重要日程表(簡章版)」PDF（技優：「甄審招生重要日程表(簡章版)」）。顯示「目前尚無資訊」時退回 `{y-1}` 並警告 |
| 解析 | 以表頭「日 期」「(作 業) 項 目」「備 註」之間累積長度最長的垂直格線決定欄界，以橫跨項目欄的水平格線切列；日期欄的括號附註（例如「(便利商店繳費僅至…止)」）會先移除 |
| 交叉驗證 | 日程表中的統測報名／考試 → `tech-test-{y}-registration`、`tech-test-{y}` |
| 事件 | `jctv-apply-{y}-*`（第一階段報名、篩選、第二階段、志願序、放榜、報到…）、`jctv-skill-{y}-*`、`jctv-union-{y}-*`（資格審查、繳費、志願選填、放榜…） |
| 必要事件 | apply／skill：報名、放榜；union：選填登記志願、放榜 |

## `cac-star`／`cac-apply` — 大學甄選入學委員會：繁星推薦、個人申請

| 項目 | 內容 |
|---|---|
| 入口 | https://www.cac.edu.tw/cacportal/index.php |
| 學年度探索 | 入口頁連結 `../star{y}/index.php`、`../apply{y}/index.php` |
| Primary 文件 | `https://www.cac.edu.tw/{star,apply}{y}/schedule.php`（重要時程）。顯示「目前尚無資料」時退回 `{y-1}` 並警告 |
| 解析 | 表頭為「項目／日期」的 HTML 表格，處理階段／學群的 rowspan（第一階段、第二階段、統一分發、第一類至第七類學群、第八類學群）；「大學自訂（115.05.14 至 115.05.31）」括號內日期保留為期間 |
| 交叉驗證 | 表中學測考試、學測成績 → `ceec-gsat-{y}`、`ceec-gsat-{y}-result` |
| 事件 | `cac-star-{y}-registration`、`-release`、`-waiver`、`-group8-*`…；`cac-apply-{y}-registration`、`-screening-result`、`-interview`、`-preference-registration`、`-release`… |

## `uac` — 大學考試入學分發委員會：分發入學

| 項目 | 內容 |
|---|---|
| 入口 | https://www.uac.edu.tw/flow.htm |
| 學年度探索 | 標題「`{y}學年度分發入學重要時程`」 |
| 解析 | 「月份／事項／備註」表格，每列「`115/08/05~115/08/08(下午04:30止) 登記-「分發志願」`」 |
| 交叉驗證 | 英聽、學測、分科的報名／考試、分科成績 → `ceec-*`；繁星、申請的放棄錄取資格 → `cac-*-waiver` |
| 事件 | `uac-{y}-payment`、`-preference-registration`、`-release`、`-release-review`、`-review-result`、`-quota-announcement`、`-document-review`… |
