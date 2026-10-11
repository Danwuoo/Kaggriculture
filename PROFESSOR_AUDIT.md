# Professor-facing Repository Audit — Kaggriculture

這個 repo 有值得審閱的策略實作與研究失敗紀錄，但目前公開展示應限定為「既有來源與歷史實驗的可追查研究作品」。生成產物與可讀來源不同步、外部 engine／資料缺失及個人歸屬未確認，仍阻礙獨立重現與個人成果認定。

審查日期：2026-10-11（Asia/Taipei）。檢視 HEAD：`79b7fcd20833da7f2af87ee02f37dc66a513173f`。初始 Git 工作樹乾淨；本次只新增 README 與 audit，未改程式、資料、配置或歷史結果。這是本地文件與代表性來源審查，未查新榜、未執行研究實驗。

本次 README 與 audit 由 AI 協助整理；這項文件協作不代表原專案的研究或程式貢獻已完成歸屬確認。

## 評分

採 1–5 分：1＝入口或證據缺失；2＝部分具備且有重要限制；3＝可沿文件核查但有公開前缺口；4＝易審閱且範圍內可重現；5＝獨立重現與個人歸屬完整。分數是本次審查判斷，不是研究成績。

| 面向 | 分數 | 本地依據與理由 |
| --- | ---: | --- |
| Readiness | 2 | [來源契約](research/main_approach/test_development_sources.py)在本次 clone 判定兩個 generated `main.py` stale；[engine loader](scripts/replay_engine_versions.py)所需 ignored vendor 不在 clone。[新入口](README.md)可導航，但不能消除這兩個實際阻礙。 |
| Readability | 3 | [v27](research/main_approach/v27_current_meta/development/README.md)與 [Boatlee](research/main_approach/boatlee_v16_rc2_market_relay/development/README.md)已分 route、runtime、overlay；[舊 E2 summary](research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md)與 [後續狀態](research/full_path_topology_searcher_2026-08-17/CURRENT_TASK.md)仍需按日期對讀，缺單一持續同步的結果入口。 |
| Verifiability | 3 | [broad machine summary](research/dual_incumbent_topology_search_2026-08-14/e2/artifacts/formal/e2_selector_broad_20260820_v1/summary.json)、[歷史 source-equivalence JSON](research/main_approach/development_validation.json)與 [server verification](research/dual_incumbent_topology_search_2026-08-14/e2/submission_server_verification.json)保留數值／hash／範圍；[外部 archive](ARCHIVE.md)與 [stop record](research/full_path_topology_searcher_2026-08-17/max_search_formal_stop_20260823.json)引用的原始資產不完整於 clone。 |
| Technical Depth | 4 | [graph-relay experiment](research/risk_aware_graph_relay_2026-08-11/decision.md)具反事實配對、模型控制與負面結果；[population search](research/full_path_topology_searcher_2026-08-17/max_search/README.md)具 lane isolation、checkpoint 與 receipt 管理。實作與研究設計可讀；不能將設計規模當完成證據。 |
| Individual Contribution | 2 | [main-approach catalog](research/main_approach/README.md)明載 HIRE4-derived 與 uploaded Boatlee artifact；[public-agent catalog](research/public_agents/README.md)及 [frontier source registry](research/full_path_topology_searcher_2026-08-17/frontier_code_evidence.json)保留他人來源。本人做了哪些方法／整合／實驗，以及 AI 承擔多少實作，目前未確認。 |

## 先看哪裡

以 [README 閱讀路線](README.md#教授閱讀入口)進入。核心閱讀從兩個 `development/agent.py` 開始，依呼叫追到 route、runtime 與 market／weed／livestock／relay；generated `main.py`用於包裝審查。研究方法可先看圖模型的否證，再對讀 E2 最小確認與 broad 失敗，最後看 search execution 的來源與停止紀錄。這種導覽不需要重構核心。

## 公開前必須修復或明確交代

| 優先 | 問題 | 完成條件與現有依據 |
| --- | --- | --- |
| P0 | 兩個 incumbent 的 generated artifact stale | 先由作者說明 intended source／artifact 身分；另行處理差異並驗證，不可直接用歷史 PASS 宣稱目前一致。[測試](research/main_approach/test_development_sources.py)、[歷史 JSON](research/main_approach/development_validation.json)。本次沒有重建。 |
| P0 | 研究結論入口有時間落差 | 展示前明列 [8/15 summary](research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md)、[8/20 minimum PASS](research/dual_incumbent_topology_search_2026-08-14/e2/selector_confirmation_decision_20260820.md)已被後續 [broad summary](research/dual_incumbent_topology_search_2026-08-14/e2/artifacts/formal/e2_selector_broad_20260820_v1/summary.json)的 promotion falsifier 更新；本 README 已做入口註記，舊紀錄保持原樣。 |
| P0 | 本人、AI、第三方的實質工作範圍未確認 | 由作者確認：策略來源與哪些修改屬本人；搜尋系統／實驗設計／分析由誰完成；AI 生成、修改及人工驗證範圍。[catalog](research/main_approach/README.md)只能證明來源紀錄，不能證明全部為本人原創。 |
| P0 | 再散布授權未釐清 | 根目錄未見 LICENSE；[公開對手 notebooks](research/public_agents/README.md)、[replay manifest](data/public_replays/top50-2026-08-09/manifest.json)、[第三方分析 notebook](data/some_notebook/everyone-is-playing-the-same-opening.ipynb)需逐來源確認 attribution、version 與再散布條件。公開可下載不等於已取得整個 repo 的發布權；本次未刪資料或替作者選 license。 |
| P1 | 完整重現依賴不在 clone | 提供既有 engine checkout/config hashes 的恢復路徑與可用環境條件；明列 [archive](ARCHIVE.md)及 [stopped search database](research/full_path_topology_searcher_2026-08-17/max_search_formal_stop_20260823.json)哪些能取得、哪些不能，不能宣稱 fresh clone 一鍵重現。 |
| P1 | 原始 replay 的展示範圍 | [Top-50 README](data/public_replays/top50-2026-08-09/README.md)指出 replay 同時含各玩家 private observations，manifest 又帶 team／submission／episode 身分。公開前確認可展示欄位與資料權利；不得把雙方 private view 包裝成 runtime 可見資訊。 |
| P1 | 搜尋規模與進度容易誤讀 | [stop record](research/full_path_topology_searcher_2026-08-17/max_search_formal_stop_20260823.json)記載完成 196,272 T0/T1 keys；[two-day runbook](research/full_path_topology_searcher_2026-08-17/two_day_runbook_20260823.md)是接續規格。需作者確認接續最終狀態，不據契約中的 300M 預算寫成完成量。 |

## 可宣稱與不能宣稱

- 可宣稱：repository 實作了兩條可讀策略來源與獨立生成契約；留有配對實驗、負面結果、來源 hash 與包裝驗證紀錄。具體依據見上表。
- 可展示歷史結果：Boatlee broad summary 記載 paired-margin `5054/518/1084`、actual-win delta `+180`、worst margin `-9517`，並觸發 promotion falsifier；必須連同失敗結論展示，未於本次重跑。
- 不能宣稱：已證明 frozen selector 可穩健提升、目前兩個 incumbent artifact 與來源一致、完成 300M games、或 public opponent 的排名屬本人。[public-agent scores](research/public_agents/README.md)與 [Top-50 snapshot](data/public_replays/top50-2026-08-09/leaderboard_snapshot.json)僅是歷史第三方快照。
- 不能宣稱：third-party notebooks／routes 均為本人原創，或全部成果已由獨立讀者重現。

## 本次驗證範圍

執行既有 source-contract suite：`python -B -m unittest research.main_approach.test_development_sources -v`，設 `PYTHONDONTWRITEBYTECODE=1`。3 個 test methods，2 個通過；currentness method 在 v27 與 Boatlee 兩 subtests 失敗。只核對 route、來源形態與 builder 輸出相符性，沒有 official-engine game、Kaggle 上傳或效能測試。另檢查 Git 狀態、代表性 JSON／來源、上述資產是否在 clone、Markdown 本地連結及 diff 空白；未安裝新依賴或補研究證據。
