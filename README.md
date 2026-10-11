# Kaggriculture

本 repository 收錄 Kaggriculture 雙人農業競賽的策略實作、配對實驗與失敗分析。最適合審閱的成果是可讀的策略來源、生成產物契約，以及區分「執行成功」與「策略有效」的研究紀錄。**這份 clone 尚不能直接獨立重現全部實驗；2026-10-11 的來源契約檢查也發現兩個 incumbent 的生成產物已過期。**詳見 [Professor-facing Repository Audit](PROFESSOR_AUDIT.md)。

## 教授閱讀入口

1. [兩條策略與來源](research/main_approach/README.md)：v27 與 Boatlee 各自保存 route、runtime 與對照，不合併結果。
2. [v27 可讀來源](research/main_approach/v27_current_meta/development/README.md)與 [Boatlee 可讀來源](research/main_approach/boatlee_v16_rc2_market_relay/development/README.md)：先讀 `agent.py` 的流程，再讀 route、runtime 與必要 overlay；旁邊的 `main.py` 是生成檔。
3. [圖模型被否證的實驗](research/risk_aware_graph_relay_2026-08-11/decision.md)：GCN、MLP 與簡單規則的配對比較，保留不支持模型複雜度的結果。
4. [最新保留的研究狀態](research/full_path_topology_searcher_2026-08-17/CURRENT_TASK.md)及 [Boatlee broad summary](research/dual_incumbent_topology_search_2026-08-14/e2/artifacts/formal/e2_selector_broad_20260820_v1/summary.json)：先確認時間與證據層級，再閱讀較早報告。

## 實作與證據邊界

- 已有獨立策略來源、719-turn route、runtime overlays、single-file builders，以及 [full-tape search 實作](research/full_path_topology_searcher_2026-08-17/max_search/README.md)。實作存在不代表所有計畫規模已完成。
- [E2 2026-08-15 summary](research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md)是階段紀錄；[2026-08-20 最小 fresh confirmation](research/dual_incumbent_topology_search_2026-08-14/e2/selector_confirmation_decision_20260820.md)後還有 broad evaluation。其 6,656 個 paired contexts 雖有 `actual_win_delta=180`，仍因重複負尾觸發 `promotion_falsified`，不能只展示前面的 PASS。這些均是既有歷史結果，本次未重跑。
- [Kaggle server verification](research/dual_incumbent_topology_search_2026-08-14/e2/submission_server_verification.json)證明歷史包裝與 runtime 可執行，不是策略提升證據。
- [300M run stop record](research/full_path_topology_searcher_2026-08-17/max_search_formal_stop_20260823.json)記載保留 196,272 個 completed T0/T1 games；300M 是原契約預算，不是完成數。後續 two-day 文件描述接續規格，不能據此宣稱已完成接續。
- [公開對手與原 notebook provenance](research/public_agents/README.md)、[Top-50 歷史快照](data/public_replays/top50-2026-08-09/README.md)是第三方參考材料；其排名、分數與分析不等同本人競賽成績。

## 重現與目前阻礙

先做不執行遊戲的來源檢查。在 repo 根目錄，使用可執行 Python 的環境：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m unittest research.main_approach.test_development_sources -v
```

命令已依 [現有測試](research/main_approach/test_development_sources.py)查實，並在本次 clone 用 bundled Python 執行。3 個 test methods 中，route 對應與來源未壓縮檢查通過；生成產物 currentness method 的 v27、Boatlee 子測試均失敗，訊息為 `generated standalone is stale`。本次保留既有程式與生成檔，不重新生成。

完整 official-engine 實驗還需要 [engine loader](scripts/replay_engine_versions.py)預期的 `.vendor/kaggle-environments`；此 clone 未包含該 ignored checkout。其歷史基底 commit 與 audited engine/configuration fingerprints 必須一起對上，安裝任意新版套件不能代替這項核對。repo 亦未附完整環境 lockfile。

[歷史 full-game validator](research/main_approach/validate_development.py)會寫入 validation JSON；本次未執行。較早的 [PASS artifact](research/main_approach/development_validation.json)只代表當時的檔案狀態，不能覆蓋本次 stale 結果。[ARCHIVE.md](ARCHIVE.md)所列 raw replay 與部分舊實驗已移往外部位置；這份 clone 也缺停止紀錄引用的 search database。缺少原資料時應停在來源與摘要審閱，不以新資料替代歷史證據。

公開前的優先項目是釐清生成產物差異、補明既有依賴／外部資產取得條件、確認本人與 AI 的工作範圍，以及檢查第三方來源的再散布權利。完整問題與可宣稱範圍見 [audit](PROFESSOR_AUDIT.md)。
