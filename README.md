# Kaggriculture

本 repository 收錄 Kaggriculture 雙人農業遊戲的策略實作、路線搜尋、配對實驗與失敗分析。研究重點是以有界策略介入、相同情境的反事實比較及負尾檢查，判斷策略修改是否真正改善結果，而不只觀察程式有沒有成功執行。

## 兩條獨立策略

| 策略 | 機制與來源 | 可讀入口 |
| --- | --- | --- |
| `v27_current_meta` | HIRE4-derived fixed route、actor-local weed repair、market SELL-slot ranking | [development README](research/main_approach/v27_current_meta/development/README.md) |
| `boatlee_v16_rc2_market_relay` | Boatlee V16-RC2 livestock route、wool control、guarded fertilizer relay | [development README](research/main_approach/boatlee_v16_rc2_market_relay/development/README.md) |

先讀 [main-approach catalog](research/main_approach/README.md)，再從各自的 `development/agent.py` 追到 route、runtime 與 overlay。旁邊的 `main.py` 是 single-file builder 產物，不是主要閱讀入口。兩條策略的來源、baseline、controls 和結果保持分開，不以單一 aggregate 隱藏另一條策略的退步。

## 實驗與結果入口

| 主題 | 來源 | 閱讀重點 |
| --- | --- | --- |
| 圖模型與簡單規則比較 | [Graph-relay decision](research/risk_aware_graph_relay_2026-08-11/decision.md) | GCN、MLP 與簡單規則的配對比較；保留不支持增加模型複雜度的結果。 |
| E2 階段決策 | [2026-08-15 summary](research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md)、[2026-08-20 最小 fresh confirmation](research/dual_incumbent_topology_search_2026-08-14/e2/selector_confirmation_decision_20260820.md) | 階段紀錄需與後續 broad evaluation 一起閱讀。 |
| Boatlee broad evaluation | [原始 summary](research/dual_incumbent_topology_search_2026-08-14/e2/artifacts/formal/e2_selector_broad_20260820_v1/summary.json) | 6,656 個 paired contexts；`actual_win_delta=180`，但重複負尾觸發 `promotion_falsified`，不能只引用前面的 PASS。 |
| Full-tape search | [實作 README](research/full_path_topology_searcher_2026-08-17/max_search/README.md)、[保留狀態](research/full_path_topology_searcher_2026-08-17/CURRENT_TASK.md)、[停止紀錄](research/full_path_topology_searcher_2026-08-17/max_search_formal_stop_20260823.json) | 停止紀錄保存 196,272 個 completed T0/T1 games；300M 是原契約預算，不是完成量。 |
| Server 包裝驗證 | [Kaggle server verification](research/dual_incumbent_topology_search_2026-08-14/e2/submission_server_verification.json) | 證明當次包裝／runtime 可執行，不證明策略提升。 |

以上是保留的歷史結果，不是這次文件更新產生的新實驗。較晚的 broad failure 限制較早的最小確認結論；two-day 等接續文件是規格，不能據此推定接續已完成。

## 最小來源檢查

從 repository 根目錄執行；這個入口不執行 official-engine games：

```sh
python -B -m unittest research.main_approach.test_development_sources -v
```

[現有測試](research/main_approach/test_development_sources.py) 檢查 route 對應、可讀來源與生成檔 currentness。生成檔逐位元一致性曾出現 `generated standalone is stale`；這個訊息本身不能判定策略邏輯不同。排查時應分開比較壓縮 payload、解壓內容與其餘程式語法，並保留原檔，不直接以重新生成覆蓋歷史版本。

[歷史 full-game validator](research/main_approach/validate_development.py) 會執行較完整的驗證並寫入 JSON；它和上述來源測試不是同一個範圍。[development_validation.json](research/main_approach/development_validation.json) 只代表當次被驗證的檔案及環境。

## 完整重現需要什麼

[Engine loader](scripts/replay_engine_versions.py) 預期額外的 `.vendor/kaggle-environments` checkout，它不隨一般 clone 提供。需要同時對上歷史 engine commit 與 configuration fingerprints；安裝任意新版套件不能取代版本核對。Repository 尚未提供完整環境 lockfile。

[ARCHIVE.md](ARCHIVE.md) 說明已外移的 raw replay 與部分舊實驗；停止紀錄引用的 search database 也不完整包含於本庫。缺少原始資產時只能閱讀現存來源和摘要，不能拿新資料冒充歷史重現。

## 第三方材料與可見性

[Public-agent catalog](research/public_agents/README.md) 與 [Top-50 歷史快照](data/public_replays/top50-2026-08-09/README.md) 保存第三方來源。HIRE4／Boatlee 基礎策略、公開對手排名和 notebook 成果不等同本專案自行原創或取得的競賽成績。

Replay 可能含雙方的 private observations；離線分析可見的欄位不應被當成策略 runtime 當時可見的資訊。Repository 目前未附 LICENSE，第三方程式、routes、replays 與 notebook 的再散布條件需逐一依來源確認。

開發邊界與策略隔離要求見 [AGENTS.md](AGENTS.md)。歷史紀錄的版本與結果保留原樣；README 僅提供現有策略、實驗及重現條件的閱讀入口。
