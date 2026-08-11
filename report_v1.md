# Kaggriculture Top-50 回放策略複製研究報告 v1

研究日期：2026-08-09～2026-08-10  
研究範圍：Top-50 公開回放、三組閉環研究代理、官方引擎驗證與 288 場完整矩陣  
狀態：研究完成；保留為 frozen reference，不升級 production

## 1. 執行摘要

本研究分析固定的 Top-50 公開排行榜回放快照，重建不同 Kaggriculture 引擎版本的正式語意，並從高分路線中建立三組狀態驅動的閉環研究代理：

1. `dominant_8c6s`：主流 8 牛、6 羊、甜瓜資本事件、草莓成熟路線。
2. `rank1_fullmap_10c11s`：Rank 1 快速全地圖、10 牛、11 羊路線。
3. `cow_heavy_12c2s`：Rank 33 牛重型、12 牛、2 羊、少量番茄路線。

分析器成功逐 transition 重建全部 50 場回放；三組代理也通過官方引擎的安全、確定性、封裝與延遲門檻。然而，來源 episode 的主要作物 cohort 與關鍵日空間拓撲沒有達到原定高保真標準。完整 288 場 fresh-seed 競爭矩陣中，三組代理皆為 0 勝。

因此，本研究證明了以下兩件事：

- 高分公開回放確實存在高度普及的共同宏觀路線。
- 只複製 herd、土地與作物配置輪廓，不足以複製高分代理的執行效率與競爭力。

三組成果應描述為「安全、可執行、可重現的閉環 route reference」，不可描述為已完成的高保真或高勝率複製。

## 2. 資料集與選擇偏差

資料來源為：

- `data/public_replays/top50-2026-08-09/manifest.json`
- 50 個唯一官方回放檔案。
- 未壓縮總量 1,391,681,379 bytes（1.296 GiB）。
- 全部為 720-state、終局 `DONE/DONE` 的完整 episode。
- 引擎版本分布：47 場 1.32.6、2 場 1.32.5、1 場 1.32.4。

每隊只保留其排行榜匹配 submission 的最高 reward 公開單場。因此：

- 樣本適合觀察路線普及度與可重現行為。
- 樣本不適合估計平均勝率或預期 reward。
- Rank 1 與 Rank 33 路線各只有一個目標 episode，僅能當個案 reference。
- 回放同時含兩位玩家各自的 private observation；private 資料只用於稽核同一玩家，跨玩家比較只使用公開狀態。

## 3. 回放重建方法

新增的 `scripts/analyze_top50_replays.py` 完成下列工作：

- 驗證 manifest、檔案數、SHA-256、720-state 與終局狀態。
- 依回放版本重建官方語意：
  - 1.32.4：本機 pinned `a4dce5a`。
  - 1.32.5：`0528e46`／`bbcdd460` shed-access 語意。
  - 1.32.6：`bded87b`。
- 從本機 pinned source 在記憶體套用版本差異，不修改 `.vendor/`。
- 逐 transition 比對 money、market、farm 與同一玩家 private state。
- 分別記錄 requested 與 executed market quantity，避免大量 over-request 污染成交統計。

重建結果：

| 項目 | 結果 |
|---|---:|
| 回放通過 | 50/50 |
| action transitions | 35,950 |
| money mismatch | 0 |
| market mismatch | 0 |
| farm mismatch | 0 |
| same-player private mismatch | 0 |
| audit error | 0 |

## 4. Top-50 共同策略證據

回放群聚顯示：

- 最大宏觀指紋群為 45/50。
- 最大完整 unit-action 序列群為 33/50。
- 最大宏觀群的選定單場 reward 中位數為 149,980，範圍 134,868～183,163。

共同特徵包括：

- 約 8 牛、6 羊的成熟混合畜牧場。
- 甜瓜作為早中期資本事件。
- 中後期大量草莓與小麥。
- 通常解鎖三個象限。
- 約 10～12 名日工支撐密集維護、收成與物流。
- 高分差異更多出現在逐回合勞動效率、物流和 premium 商品出售時機，而不只是最終資產數量。

45 個相同宏觀指紋與 33 個相同行動序列可以證明路線高度普及，但不能證明它在 fresh seeds 上具有相同勝率。

## 5. 三組閉環研究代理

代理位於 `research/replay_clones/`，共享核心提供：

- `RouteSpec`：來源 episode、每日 herd/crop/land/hand 目標、格子角色、reserve、購買與出貨順序、終局 cutoff。
- P0/P1 安全優先級，可中斷普通工作。
- 固定 worker zones 與距離、deadline 排程。
- WEED 的 DIG → 重驗 → 限次重試。
- PLANT 同日 WATER 約束。
- shadow seed、shed、money 與逐單位市場投影。
- 1.32.5+ 四個中心格的 shed 操作語意。
- 終局回倉、DROP、SELL 與庫存清空。

代理不是 runtime 固定 action tape；每組皆暴露標準 `agent(obs)`，並可透過 `make_agent(route_name)` 載入。

### 5.1 凍結路線

| 代理 | 來源定位 | 主要目標 |
|---|---|---|
| `dominant_8c6s` | Top-50 主流群 | 8 牛、6 羊、42 草莓種子、12 甜瓜種子；第 7／11 天買地 |
| `rank1_fullmap_10c11s` | Rank 1 個案 | 快速全解鎖、10 牛、11 羊、42 草莓種子 |
| `cow_heavy_12c2s` | Rank 33 個案 | 12 牛、2 羊、3 番茄、42 草莓種子 |

## 6. 快速官方引擎驗證

`reports/replay_clone_study/quick_validation.json` 包含 21 場完整遊戲：三組 self-play、starter/random 雙座位，以及 seed 777 重複 determinism。

- 21/21 `DONE/DONE`。
- 三組 action digest 與 rewards determinism 全部通過。
- malformed、timeout、animal escape、fresh-crop death、shed overflow、seed overcommit、超過 10 筆 market order及終局可售殘留全部為 0。

| 代理 | 最差單場 p95 | 最大單次 latency |
|---|---:|---:|
| `dominant_8c6s` | 3.2123 ms | 51.4310 ms |
| `rank1_fullmap_10c11s` | 3.6919 ms | 54.6622 ms |
| `cow_heavy_12c2s` | 4.1065 ms | 68.6193 ms |

三組皆遠低於 p95 150 ms、max 750 ms 的門檻。

## 7. 來源 episode 忠實度

忠實度測試使用各來源 replay 的 configuration 與 seed，對手只重放其公開 action stream；候選代理仍為閉環，沒有載入自己的 action tape。

通過部分：

- 三組 herd peak 完全吻合。
- `rank1_fullmap_10c11s` 三次買地日完全吻合。
- 另外兩組買地最大誤差一天。
- 三組安全診斷全部為 0。

未通過部分：

| 代理 | 主要作物 peak 誤差 | 關鍵日 topology Jaccard |
|---|---|---:|
| `dominant_8c6s` | MELON 0、STRAWBERRY -8 | 0.273～0.624 |
| `rank1_fullmap_10c11s` | MELON -4、STRAWBERRY -12 | 0.333～0.600 |
| `cow_heavy_12c2s` | MELON -3、TOMATO 0、STRAWBERRY -15 | 0.288～0.623 |

原定門檻為主要作物誤差不超過 2 格、關鍵日 topology Jaccard 至少 0.75。因此三組均未達高保真標準。

這代表目前成功複製的是宏觀策略輪廓，尚未複製高分來源的完整工人路線、日內物流、作物 cohort 密度與再投資節奏。

## 8. 288 場完整研究矩陣

矩陣組成：

```text
3 組研究代理
× canonical control 與 5 個既有公開代理
× 8 fresh seeds
× 2 seats
= 288 場
```

Fresh seeds：`410101, 410211, 410307, 410409, 410503, 410607, 410709, 410811`。

矩陣完成 288/288，笛卡兒積無缺漏、無重複；所有敗局保留於 `matrix_games.jsonl` 與 `full_matrix_results.json`。

### 8.1 總體結果

| 代理 | 單場 W-T-L | paired-seat W-T-L | 平均 margin | 中位數 | P10 | 最差 |
|---|---:|---:|---:|---:|---:|---:|
| `rank1_fullmap_10c11s` | 0-0-96 | 0-0-48 | -97,629.0 | -106,191.0 | -147,418.0 | -164,102.0 |
| `cow_heavy_12c2s` | 0-0-96 | 0-0-48 | -102,141.6 | -98,512.5 | -150,791.5 | -173,691.0 |
| `dominant_8c6s` | 0-0-96 | 0-0-48 | -107,700.2 | -115,609.5 | -155,712.0 | -172,025.0 |

`rank1_fullmap_10c11s` 的平均 margin 最佳，但仍是 0/96 單場、0/48 paired-seat，不能視為競爭成功。

### 8.2 相同情境描述性比較

在相同 opponent、seed、seat 下比較 terminal margin：

| 左側 − 右側 | 情境 W-T-L | 平均差 | 95% seed-cluster CI |
|---|---:|---:|---:|
| Rank-1 − cow-heavy | 51-0-45 | +4,512.6 | [-5,608.7, 17,617.8] |
| Rank-1 − dominant | 63-0-33 | +10,071.2 | [4,318.4, 16,279.9] |
| cow-heavy − dominant | 61-0-35 | +5,558.6 | [-2,398.6, 12,347.5] |

只有 Rank-1 相對 dominant 的差分 CI 排除 0；其餘跨過 0。這只是三個失敗 reference 的相對排序，不是三者直接交手，也不能取代勝率判定。

### 8.3 全矩陣安全與效能

- 288/288 `DONE/DONE`。
- malformed：0。
- timeout：0。
- animal escape：0。
- fresh-crop death：0。
- shed overflow：0。
- seed overcommit：0。
- market order cap violation：0。
- 終局可售殘留：0。
- 全矩陣最差單場 p95：5.3599 ms。
- 最大單次 latency：255.3698 ms。

安全與效能全部合格，但完全沒有正向 paired-win 訊號。

## 9. 為何宏觀策略相同，結果仍然全敗

高分策略不是只有「最後養幾頭牛、種幾格草莓」。真正的收益差距還包括：

1. 每日工人的區域分工與移動距離。
2. WATER、FEED、CARE、HARVEST 的精確先後與漏做率。
3. 收成後回倉、DROP、SELL 的物流延遲。
4. 逐單位市場價格與對手 order-index 對齊。
5. 何時把現金轉為土地、工人、動物或種子。
6. 作物 cohort 的種植密度、成熟同步與重種速度。
7. WEED 或 silent no-op 後能否快速回到原本節奏。

本研究代理複製了 herd peak、土地日程與主要作物方向，但草莓 cohort 少 8～15 格，空間拓撲差距也大。這些偏差會累積成更少的產量、更慢的回款與更弱的再投資，最後形成明顯 terminal margin 落差。

## 10. 可重現成果

主要程式：

- `scripts/analyze_top50_replays.py`
- `scripts/replay_engine_versions.py`
- `scripts/run_replay_clone_fidelity.py`
- `scripts/run_replay_clone_study.py`
- `scripts/build_replay_clones.py`
- `research/replay_clones/core.py`
- `research/replay_clones/routes.py`

主要證據：

- `reports/replay_clone_study/top50_summary.json`
- `reports/replay_clone_study/analysis.md`
- `reports/replay_clone_study/route_specs.json`
- `reports/replay_clone_study/quick_validation.json`
- `reports/replay_clone_study/source_episode_fidelity.json`
- `reports/replay_clone_study/full_matrix_results.json`
- `reports/replay_clone_study/full_matrix_report.md`
- `reports/replay_clone_study/matrix_games.jsonl`

Frozen source digest：

```text
39D7FC856222C9FD10C95C868940F649754CEC82C9F6EB5873CF9E861F876439
```

研究 tarball：

| 代理 | Bytes | SHA-256 |
|---|---:|---|
| `dominant_8c6s` | 16,887 | `D71F88CD63DC5838A9DCC80439799EABDBEFEA49B1C643825FA145DA0FC1D1F0` |
| `rank1_fullmap_10c11s` | 16,899 | `305A407AEB4288E6567662E2654761523EFB25015225262650971F086106B50A` |
| `cow_heavy_12c2s` | 16,894 | `A67C97438D5EF565B75D8FF55A92DE3CCA6DF72155D69AB581D1B1F58FD56B5B` |

三份 archive root 均含 `main.py`，不包含回放、測試、cache 或 production submission。

## 11. 最終判定

| 判定項目 | 結果 |
|---|---|
| Top-50 回放重建 | 通過 |
| Requested／executed market 分離 | 通過 |
| 三組閉環代理實作 | 完成 |
| 官方引擎安全 | 通過 |
| Determinism | 通過 |
| Latency | 通過 |
| 封裝與 import smoke | 通過 |
| Herd peak 忠實度 | 通過 |
| 土地解鎖忠實度 | 通過 |
| 主要作物 cohort 忠實度 | 未通過 |
| Topology Jaccard | 未通過 |
| Fresh-seed paired-win 訊號 | 未通過 |
| Production promotion | 否 |

最終結論：三組代理可作為後續研究、消融與策略理解的 frozen reference，但沒有證據支持將其視為高分代理的完整複製，亦沒有理由取代目前 production submission。

本研究未修改 `data/`、`.vendor/`、`submission/` 或 `dist/`，未提交 Kaggle，也未改變任何外部狀態。
