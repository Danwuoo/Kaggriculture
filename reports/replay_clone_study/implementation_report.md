# Top-50 回放複製研究：實作與快速驗證

## 已完成範圍

- 驗證固定 Top-50 snapshot 的 50 個檔案、1,391,681,379 bytes 與 SHA-256。
- 依 1.32.4、1.32.5、1.32.6 語意重建 50/50、共 35,950 個 action transition；money、market、farm、同一玩家 private state mismatch 均為 0。
- 實際成交量由官方 interpreter 的逐單位 commit 記錄，與 requested quantity 分開。
- 凍結三組無 action tape、狀態驅動的研究代理：`dominant_8c6s`、`rank1_fullmap_10c11s`、`cow_heavy_12c2s`。
- 建立三份研究 tarball；每份 archive root 含 `main.py`，已通過解壓匯入與完整 720-step smoke。

## Top-50 主要證據

- 最大宏觀指紋群：45/50；選定單場中 38 勝，reward 中位數 149,980、範圍 134,868–183,163。
- 最大完整 unit-action 序列群：33/50。
- 這只能證明公開路線高度普及；資料是每隊 matched submission 的最高 reward 單場，不能當勝率或期望 reward。

## 快速官方引擎驗證

最終 `quick_validation.json` 含 21 場完整遊戲：三組 self-play、starter/random 雙座位，以及 seed 777 重複 determinism。

- 21/21 均為 `DONE/DONE`。
- malformed、timeout、animal escape、fresh-crop death、shed overflow、seed overcommit、超過 10 筆 market order、終局可售殘留均為 0。
- 三組 action digest 與 rewards determinism 均通過。
- 最差單場 p95：dominant 3.2124 ms、Rank-1 3.6919 ms、cow-heavy 4.1066 ms。
- 最大單次 latency：dominant 51.4310 ms、Rank-1 54.6622 ms、cow-heavy 68.6193 ms。

## 忠實度門檻（未通過）

另以各來源 replay 的 configuration／seed 重跑，離線對手只重放其公開 action stream；候選代理仍為閉環，沒有載入自己的來源 action。三組均 `DONE/DONE` 且安全診斷全為零。三組 herd peak 均完全吻合；Rank-1 三次買地日也完全吻合，另外兩組買地最大誤差一天。但主要作物 peak 與關鍵日 topology 尚未達計畫門檻：

- `dominant_8c6s`：MELON 誤差 0、STRAWBERRY -8；關鍵日 Jaccard 0.273–0.624。
- `rank1_fullmap_10c11s`：MELON -4、STRAWBERRY -12；關鍵日 Jaccard 0.333–0.600。
- `cow_heavy_12c2s`：MELON -3、TOMATO 0、STRAWBERRY -15；關鍵日 Jaccard 0.288–0.623。

因此三組定位是「安全、可執行、凍結的閉環 route reference」，不能描述為已完成高保真複製，也不能據此升級 production。完整 288 場矩陣只評估 frozen reference，不在本輪調參。

## 完整矩陣（已完成）

三組代理 × canonical control 與五個既有公開代理 × 8 fresh seeds × 2 seats，共 288/288 場；笛卡兒積無缺漏、無重複，背景程序正常結束且 stderr 為空。所有遊戲均 `DONE/DONE`，所有 losses 保留於 `matrix_games.jsonl` 與 `full_matrix_results.json`。

- `rank1_fullmap_10c11s`：0-0-96，paired-seat 0-0-48，平均 margin -97,629.0。
- `cow_heavy_12c2s`：0-0-96，paired-seat 0-0-48，平均 margin -102,141.6。
- `dominant_8c6s`：0-0-96，paired-seat 0-0-48，平均 margin -107,700.2。

全矩陣 malformed、timeout、escape、fresh-crop death、overflow、seed overcommit、market cap violation 與終局可售殘留均為 0；最差單場 p95 5.3599 ms，最大單次 latency 255.3698 ms。三組安全與效能合格，但完全沒有正向 paired-win 訊號，故不升級 production。完整總體、同情境差分、各對手 bootstrap CI 與最差分位見 `full_matrix_report.md`。
