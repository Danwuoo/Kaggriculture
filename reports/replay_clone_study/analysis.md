# Top-50 公開回放策略分析（2026-08-09）

## 結論

- 固定資料集含 50 場、1,391,681,379 bytes；全部為 720-step DONE/DONE 回放。
- 最大宏觀群有 45/50 個完全相同指紋；最大逐回合 unit-action 群有 33/50 個完全相同序列。
- 這證明路線在榜上高度普及，但每隊樣本都是該 submission 的最高 reward 單場，不能視為勝率或期望 reward。
- 市場統計使用官方 interpreter 實際成交量，不把未成交的大額 request 納入產能或收益。

## 凍結研究路線

- `dominant_8c6s`：Rank 24 / episode 90974965；COW 8、SHEEP 6、STRAWBERRY 42、MELON 12；買地日 [7, 11]。
- `rank1_fullmap_10c11s`：Rank 1 / episode 90442423；COW 10、SHEEP 11、STRAWBERRY 42、MELON 13；買地日 [4, 6, 10]。
- `cow_heavy_12c2s`：Rank 33 / episode 91023354；COW 12、SHEEP 2、STRAWBERRY 42、MELON 12；買地日 [7, 11]。

## 正確性與資訊界線

- Transition audit：50/50 episodes 通過；money／market／farm／same-player private mismatch 均為 0。
- 兩位玩家 private observation 只各自用於 transition correctness；跨玩家分群未使用 shed、seeds 或 inventories。
- 1.32.4、1.32.5、1.32.6 依回放 module version 使用對應官方語意。

## 研究限制

- Rank 1 與 Rank 33 各只有一個目標樣本，屬可重現候選，不是已證實最優策略。
- 複製代理採閉環 route goals、P0/P1 安全與合法性投影，不把原始 action tape 當 runtime 策略。
- 競爭效果必須由 fresh seeds、雙座位、保留所有 losses 的官方引擎矩陣另行判斷。
# Archive note (2026-08-10)

Large raw JSON/JSONL evidence now lives under
`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10\reports\replay_clone_study`.
The narrative analysis and compact fidelity/specification artifacts remain in
this directory. See `ARCHIVE.md` at the workspace root.
