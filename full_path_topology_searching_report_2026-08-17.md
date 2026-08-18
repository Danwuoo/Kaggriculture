# Kaggriculture Full-Path Topology Searching 正式研究報告

**報告日期：2026-08-17**  
**研究對象：Danwuoo/Kaggriculture**  
**文件性質：正式研究報告（Research Report）**  
**主題：從 replay lineage、frontier strategy code、W/D/L causal evidence 與 topology failure analysis，重建 Full-Path Topology Searching 方法論**

---

## 摘要

本報告重新檢視 Kaggriculture 既有 topology search 的研究方向，並整合四類證據：

1. 目前兩個獨立 incumbents（v27 與 Boatlee V16-RC2）的正式實驗紀錄；
2. `data/some_notebook/` 內 9 本已完整保存的 replay / meta / optimisation notebooks；
3. 2026-08-16 Public Score top-ten notebooks 對應的 8 個 unique frontier `main.py`；
4. 過去已出現的正向、假正向與弱池退化案例。

最重要的結論是：**既有 topology search 的主要問題，不是「搜尋範圍不夠大」，而是搜尋所使用的目標函數、搜尋單位、continuation 假設與 opponent distribution 同時存在偏差。**

現有證據不支持把 Kaggriculture frontier 視為「從 720-turn action space 中尋找一條完全不同的最佳完整路徑」。相反地，top-public agents、replay genealogy 與 source code 一致顯示：高分策略通常具有一條高度保守的 route spine，真正的差異集中在少量、具競爭外部性的 mutation loci，例如 premium-market front-running、same-turn sell ordering、livestock placement recovery、opponent-family counter、weed repair 與 terminal takeover。

因此，本文提出的 Full-Path Topology Searching 不是重新引入大型 planner 或全域 learned model，而是把「完整路徑」重新定義為：

> **conserved spine + empirically mutable loci + causal continuation**。

Replay 與 public code 可以有效回答「**在哪裡值得 branch**」，但不能單獨回答「**哪個 branch 是 good**」。後者必須由 parent-relative、matched、family/seat-stratified 的 **W/D/L causal evidence** 決定。

在正式 calibration 上，本報告認為至少需要同時正確處理三類已知案例：

- **W/D/L causal positive**：terminal takeover boundary 的 c27，相對 direct parent c17 為 13–7，而 mean margin 僅約 +42；
- **margin-only false positive**：Boatlee E2 public fertilizer selector 在 consumed diagnostic contexts 上具有漂亮 paired-margin / own-bank 結果，但 actual win delta = 0；
- **weak-pool parent regression**：fixed horizon 25 曾在弱歷史 aggregate 中成為 finalist，換到 fresh / parent-relative 驗證後對 direct parent 與更強比較組退化。

任何下一代 topology evaluator 若不能把這三種情況正確區分，就不應被用來導引 full-path search。

---

# 1. 研究目的與範圍

本研究回答的不是「如何快速修改現有 agent」，而是更上游的問題：

> **Kaggriculture 的高分策略究竟呈現什麼 topology？既有 topology search 為何沒有可靠轉化成 Wins？Full-path search 應該如何重新定義，才能讓 replay、public frontier 與 causal W/D/L evidence 在同一個研究框架中工作？**

本報告遵守以下研究邊界：

- v27 與 Boatlee V16-RC2 是兩個**獨立 incumbents**，其分數、結論與 promotion evidence 不得混合；
- primary objective 是 **Wins / W-D-L**，不是 money、paired margin 或 own-bank；
- top-ten Public Score notebooks 中存在 exact duplicates，rank 1/3 與 rank 7/8 不得重複加權；
- smoke test 只代表 runtime / packaging compatibility，不代表 efficacy；
- 舊 internal opponent pool 已不足以代表 frontier；
- 本報告不提出大型新 planner、共享架構或模型優先的開發方案；
- replay correlation、source-code mechanism 與 causal efficacy 必須分層處理，不得互相替代。

---

# 2. 證據語料與資料結構

## 2.1 Incumbent 與正式實驗紀錄

本研究以 `research/main_approach/` 的兩條 incumbent lane 為正式基礎：

### v27 current meta

主要特徵：

- HIRE4-derived fixed route；
- actor-local weed repair；
- market SELL-slot ranking；
- E2 delayed selector 曾改變 receipts / public state，但在 fresh S1 contexts 中沒有產生任何 terminal paired-margin、own-bank 或 W/D/L effect。

這個結果的重要性不是「selector 很弱」而已，而是：

> **action digest、receipt 或 public-state difference 並不等價於 strategically material topology change。**

### Boatlee V16-RC2 market relay

主要特徵：

- livestock-centric replay route；
- wool control；
- guarded fertilizer relay；
- E2 always-on step240/241 block 在 S1 強，但在 fresh S2 被 Roman/seat-sensitive public-market tail 推翻；
- frozen step241 public selector 在 consumed remediation contexts 上具有 36 positive / 12 fallback / 0 negative paired-margin diagnostics，但 actual win delta = 0，且 threshold 完美分離 Roman family，存在明顯 proxy-overfit 風險。

因此 Boatlee E2 已經提供一個非常重要的 counterexample：

> **economic diagnostics 可以很漂亮，但仍然沒有證明任何 Win-boundary movement。**

---

## 2.2 `data/some_notebook/` 的 9 本 notebook

本研究完整使用以下 9 本 notebook：

1. `everyone-is-playing-the-same-opening.ipynb`
2. `kaggriculture-daily-replays-the-live-meta-report.ipynb`
3. `kaggriculture-the-free-experiment-you-already-ran.ipynb`
4. `kaggriculture-what-kind-of-game-is-this.ipynb`
5. `kaggriculture-what-kind-of-optimisation-is-this.ipynb`
6. `mutants-at-the-top-genetic-potential-of-a-replay.ipynb`
7. `the-leaderboard-has-a-fossil-record.ipynb`
8. `the-leaderboard-is-a-habitat-gradient.ipynb`
9. `wins-not-money.ipynb`

這 9 本 notebook 並不是 9 個互相獨立的 strategy recipe。它們更像是一套連續的 meta-research chain：

> common opening → lineage / fossil record → habitat-conditioned competition → sparse mutations → natural reactivity experiment → optimisation epistasis → W/D/L objective。

這個 distinction 很重要。若把這些 notebooks 當成「高分玩家告訴我們該做什麼」，會產生錯誤的 imitation bias；若把它們視為**topology priors 與 research instrumentation**，則價值很高。

---

## 2.3 目前 Public Score frontier：8 個 unique `main.py`

2026-08-16 top-ten Public Score capture 一共有 10 個 ranked entries，但只有 8 個 unique artifacts：

- rank 1 = rank 3：exact duplicate；
- rank 7 = rank 8：exact duplicate。

因此 lineage / family aggregate 必須以 unique artifact 為基礎。

目前 8 個 unique source 可概括為：

1. **Boatlee RC5 premium timing family**：fixed route + premium one-turn front-run / repay；
2. **Kaito V25**：regime-aware route + price-impact / demand-aware SELL-slot ranking；
3. **Rayk zero-to-top**：distilled trajectory + late observation-driven terminal / market controller；
4. **Boatlee RC5 R5A**：RC5 family + bounded cow placement / labor recovery；
5. **Boatlee V14 clone-preemption**：near-clone detection + premium planned-sale preemption；
6. **Kunal TTV1 / Salem duplicate family**：public-replay consensus + opponent-family recognition / counter；
7. **Bruce high-score pipeline**：strong fixed replay + generic weed / pending repair + terminal liquidation；
8. **Prvsiyan Soil**：outcome-blind modal route + live RC5-style weed repair。

這些 source code 對 replay notebooks 最重要的交叉驗證是：

> **frontier agents 真的普遍是「高度保守路徑 + 少量局部 overlay」，不是每局重新規劃完整 route。**

---

# 3. 證據分級標準

為避免把 correlation、code presence 與 efficacy 混在一起，本報告採用以下正式 evidence hierarchy。

## 3.1 `CAUSAL_WDL_CONFIRMED`

必須滿足：

- matched control；
- direct parent 或 unchanged incumbent；
- fresh / untouched contexts；
- both seats；
- W/D/L outcome 有可重複的 parent-relative movement；
- family / seat tail 沒有被 aggregate mean 掩蓋。

這是最高等級，可直接支持 promotion 或 search utility 判定。

## 3.2 `CODE_CONFIRMED_MECHANISM`

source code 明確實作某個 mechanism，例如：

- front-run future premium sell；
- clone-conditioned preemption；
- cow placement alignment；
- terminal takeover；
- SELL-slot price-impact ranking。

這能證明「mechanism 存在於高分 agent」，但不能證明它對另一 incumbent 或另一 opponent distribution 仍有效。

## 3.3 `REPLAY_CORRELATION`

例如：

- total hires 與 final bank 的 rank correlation 約 +0.35；
- strawberry count 與 final bank 約 +0.30；
- first-land day 約 +0.02；
- high-rating habitats 的 opening diversity 較低。

此等級只能用來建立 search prior 或提出可檢驗 hypothesis，不能直接作為 branch reward。

## 3.4 `DIAGNOSTIC_ONLY`

例如 consumed remediation contexts、same-seed replays、smoke games、step-level receipts / action differences。

它們可以說明 execution、mechanism 或 tail source，但不能當 fresh efficacy。

## 3.5 `UNVALIDATED_HYPOTHESIS`

任何僅由 source similarity、author claim 或單一 replay pattern 推得的策略主張，在未經 matched W/D/L ablation 前均屬此類。

---

# 4. Notebook 分析：哪些主張被 frontier code 驗證？

## 4.1 `everyone-is-playing-the-same-opening`

Notebook 分析 4,546 ladder games / 9,092 seats，顯示大量 agents 在相當長的前綴共享 opening，但後續會分裂成不同 endings。

它最重要的貢獻不是「opening X 很強」，而是：

> **Kaggriculture 的 trajectory space 具有明顯 lineage / shared-prefix 結構。**

目前 Public Score top-ten 中的 exact duplicates 與大量 replay-derived code 直接支持這一點。

但此 notebook 不提供 branch efficacy：同 opening 可能來自 copying、共同 ancestor、competition convergence 或 simply robust baseline。

### 正確用途

- lineage fingerprint；
- conserved prefix prior；
- branch-search-space reduction。

### 不正確用途

- 以 opening popularity 當 Win utility；
- 把同 lineage 的 100 次 replay 當 100 個獨立 votes。

---

## 4.2 `kaggriculture-daily-replays-the-live-meta-report`

在約 69,146 seats 中，較明顯的 rank correlations 包含：

- total hires：約 +0.35；
- crew size 同樣偏高；
- strawberry：約 +0.30；
- first-land day：約 +0.02。

Notebook 本身已警告：heavy hiring 可能是 winning farm 能負擔更多 labor 的結果，而不是勝因。

因此這類結果應被視為 **resource-allocation hypothesis generator**。

### 可導出的 topology questions

- 同資金、同 public state 下，提前一個 hire 是否會讓後續 worker-turn allocation 改變 W probability？
- strawberry 相關性究竟代表 crop mix、cashflow timing，還是 simply late-game wealth proxy？
- land timing correlation 很低，是否意味「買地」本身不是 frontier differentiator，而 worker / market timing 才是？

這些都需要 matched counterfactual，不可由 replay correlation 直接回答。

---

## 4.3 `kaggriculture-the-free-experiment-you-already-ran`

此 notebook 把相同 code 放在兩個 seats 的 episodes 視為天然 reactivity probe。

其核心觀察是：

- 雙 action-stream episodes 中，一部分完全或近乎固定；
- 另一部分會因 observation / opponent interaction 發生 divergence；
- divergence 與更大的 terminal margin spread 明顯相關。

這證明「是否 reactive」是一個可觀察的 topology property。

但它仍然不能告訴我們：

> reactive branch 是好、壞，還是只增加 variance。

### 正確用途

- 判斷 agent 是 outcome-blind spine 還是 state-conditioned；
- 找出 first-divergence turn；
- 建立 action-mutability map。

### 不正確用途

- 以 divergence 本身作 efficacy reward。

v27 E1c action-only no-op 已經正式證明：**action digest difference 本身不足以支持 efficacy。**

---

## 4.4 `what-kind-of-game-is-this`

這本 notebook 的價值在於 game geometry：

- symmetric；
- stochastic；
- simultaneous；
- 存在相當長的 deterministic / highly conserved prefix；
- absolute money 受 episode common shock 影響；
- relative margin 比 absolute bank 更適合作 diagnostic，但最終 objective 仍是 Win。

這支持一個重要 inference：

> **搜尋完整 720-turn 路徑的每一個 action slot，不只是昂貴，而且在資訊上是浪費的。**

大部分 early conserved region 應視為 spine；真正需要探索的是與 opponent / public market / scarce resource interaction 有關的 windows。

---

## 4.5 `what-kind-of-optimisation-is-this`

此 notebook 強調 resource constraints 與 epistasis：

- worker turns；
- capital timing；
- livestock / field capacity；
- crop / feed chains；
- public-market externality。

因此單一 action 或單一 scalar parameter 的 local best，不一定是完整 continuation 的 best。

這對既有 topology search 有直接含義：

> **「修改 2–3 turns，然後強制 rejoin incumbent」不是中立的實驗設計，而是一個很強的 topology assumption。**

如果 branch 的價值是透過 persistent asset allocation、cash timing、worker routing 或 livestock state 才逐漸發生，那麼 forced short rejoin 會把真正的 causal path 人為消除。

這並不意味應建立大型 planner；它只意味 continuation horizon 必須由 mechanism 決定，而不是固定為極短值。

---

## 4.6 `mutants-at-the-top-genetic-potential-of-a-replay`

這是本研究對 Full-Path Topology Searching 最關鍵的 notebook 之一。

它不是比較完整 agent score，而是找：

> **相對 conserved lineage，哪些 turn / action channel 在 top agents 中會穩定 mutation。**

其結果顯示大量 top family 在完整 720 turns 中，真正可辨認的 mutable turns 僅是少數，且常集中於中後段。

這與目前 frontier source code 高度吻合：

- RC5：fixed action tape + premium front-run / repay；
- R5A：加一段 cow placement alignment；
- V14：near-clone market preemption；
- Kaito：SELL-slot ranking；
- TTV1：opponent-family counter；
- Bruce：fixed replay + repair + terminal cashout；
- Soil：modal route + live weed repair。

因此可以正式得到：

> **Replay mutation map 是 branch proposal oracle 的高品質輸入。**

但仍必須保留一條界線：

> **mutable locus ≠ beneficial direction。**

它只能決定「哪裡值得 test」，不能決定「test 哪一側應該被 promote」。

---

## 4.7 `the-leaderboard-has-a-fossil-record`

Notebook 的核心結論可概括為：

> **the field does not drift; it turns over by sweeps.**

也就是 meta 並非平穩 stationary distribution，而是 lineage 會快速擴散、被改寫、被下一輪 lineage sweep 取代。

其直接含義是：

- 舊 replay 不能永續等權；
- lineage 頻率不能當獨立 evidence count；
- search reference 必須具有 temporal decay；
- fresh frontier code 的 mechanism evidence 權重應高於早期低-rating replay popularity。

---

## 4.8 `the-leaderboard-is-a-habitat-gradient`

此 notebook 顯示 behavioral genealogy 中大多數 agents 都可歸入 clones 或 descendants，真正 unrelated 的比例很低；同時不同 rating band 的 effective behavioral diversity 明顯不同。

它對 evaluation design 的含義非常直接：

> **一個 branch 的 utility 必須 conditioning 在 opponent habitat 上。**

所以 evaluator 不應只估：

\[
Q(s,a)
\]

而至少在研究設計層面要近似：

\[
Q(s,a\mid incumbent, opponent\ family, seat, public\ state)
\]

這不是要求建立 machine-learning Q model，而是要求結果分層，避免在 aggregate 中把 race condition、seat effect、clone-preemption 等 discontinuous interaction 洗掉。

---

## 4.9 `wins-not-money`

這本 notebook 為 topology search 提供最重要的 objective-function correction：

\[
\arg\max E[M] \neq \arg\max P(M>0)
\]

其中 \(M\) 為 terminal margin。

它展示存在 mean margin 較差、但 win rate 顯著更高的 policy；反之，也存在 mean margin 很漂亮但勝率較差的 policy。

這與 repo 中的 Boatlee E2 形成直接對照：

- frozen public selector 在 consumed diagnostics 上 paired margin / own-bank 很漂亮；
- 但 actual win delta = 0。

因此 full-path topology evaluator 的 primary label 必須是：

- `L → D/W`：Improvement；
- `D → W`：Improvement；
- same outcome class：No primary efficacy；
- `W → D/L` 或 `D → L`：Regression。

money、bank、receipts、market movement 只應用來解釋 mechanism。

---

# 5. Frontier source code 所揭示的真正 topology

## 5.1 高度保守 spine

目前 top-public code 的共同現象是：

- 大段 route 由 replay / distilled trajectory / modal trace 給定；
- live observation 只修改有限 channel；
- 很少出現「每 turn 全局重新規劃」。

這表示 frontier 的主要搜索自由度不是「整條 path 的任意重寫」。

---

## 5.2 Sparse interaction overlays

主要可觀察 overlay 包含：

### A. Premium-market temporal preemption

RC5 會把未來一回合的 premium sale 提前到現在，再在原未來 turn 減掉同 quantity。

這是一個真正的 temporal topology mutation：

\[
SELL(t+1) \rightarrow SELL(t)
\]

其價值不一定來自自己多賺，而可能來自：

- 先消耗 public demand；
- 改變下一回合價格；
- 讓 opponent capital / inventory path 改變。

### B. Same-turn market ordering

Kaito 等 agent 會依 price impact、town demand、urgency 對 sell slots 排序。

這顯示 topology 不只是「做不做某件事」，還包括同一局部 window 中 action ordering。

### C. Livestock / worker placement recovery

R5A 的 cow placement alignment 表明：

- route target 可以不變；
- 但 labor / actor geometry 若錯一格，會破壞 continuation；
- 一小段 repair 可以保住後續 topology。

### D. Opponent-family conditional counter

V14 與 TTV1 明確依 public signature / livestock pattern 推測對手 family，再做 timing counter。

這是 frontier 對 `habitat gradient` 的直接 code-level 實現。

### E. Terminal takeover

Rayk family 直到非常晚的 step 才把固定 trajectory 交給 observation-driven terminal controller。

這證明：

> **continuation boundary 本身就是 topology parameter。**

---

# 6. 既有 Topology Search 的失效機制

綜合所有證據，既有 topology search 至少存在五個系統性問題。

## 6.1 問題一：Surrogate objective 錯誤

過度依賴：

- paired terminal margin；
- own-bank delta；
- receipt movement；
- public-state difference。

而 primary objective 是 W/D/L。

E2 Boatlee selector 已正式證明 margin-only selection 會產生 false positive。

---

## 6.2 問題二：Search unit 錯誤

舊方法傾向先挑「可編輯 route segment」，再向前做 intervention。

但 frontier code 顯示真正的 mechanism 多數是：

- opponent interaction window；
- market priority race；
- worker / asset bottleneck；
- terminal controller handoff。

因此更合理的 unit 是：

> **causal interaction window**，而不是 arbitrary editable segment。

---

## 6.3 問題三：Forced short rejoin assumption 過強

若 intervention 改變：

- livestock inventory；
- worker turns；
- cash timing；
- public price path；
- future market slot ownership；
- terminal control state；

則在 2–3 turns 內強制 rejoin 原 incumbent，可能把 causal chain 人為截斷。

Full-path search 應該允許 mechanism-specific continuation horizon。

---

## 6.4 問題四：Opponent distribution 錯誤

舊 internal pool 太弱，無法暴露 frontier 的：

- near-clone preemption；
- family-conditioned counters；
- late market control；
- race-like livestock / cash timing。

因此舊池中的「穩健」不能外推到 2026-08-16 Public Score frontier。

---

## 6.5 問題五：Family / seat aggregation 會洗掉 discontinuity

Boatlee S2 的 Roman outlier 已證明：

- aggregate mean 可以由單一大正值掩蓋其他 31 contexts 的負值；
- public-market externality 具有 opponent-family / seat sensitivity。

所以 full-path search 不可只看總平均。

---

# 7. 對「Full-Path」的重新定義

Full-path 不應解讀成：

> 每個 turn 都是自由 decision variable，從 720-turn combinatorial action tree 中找 globally optimal path。

在目前 evidence 下，更正確的定義是：

\[
FullPath = ConservedSpine + MutableLoci + CausalContinuation
\]

其中：

## 7.1 Conserved Spine

來源：

- incumbent route；
- replay prefix consensus；
- top-public code conserved regions；
- lineage frequency，但必須 deduplicate。

spine 的作用不是宣告這些 actions 最優，而是：

> 在沒有反證前，避免把 search budget 浪費在高保守、低資訊增益區域。

## 7.2 Mutable Loci

來源：

- replay mutation entropy；
- public code overlay points；
- first divergence turns；
- historical W/L regression windows。

## 7.3 Causal Continuation

一個 branch 是否有價值，必須連同它造成的後續資源配置與 opponent state 一起評估，而不是只看 local receipts。

---

# 8. Full-Path Topology Searching 正式方法論

本報告建議把研究流程改為：

> **locate Win-boundary interaction → propose branch from replay/code topology → causal ablation → continuation search → frontier W/D/L validation**

而不是：

> generate arbitrary topology segment → screen by margin → remediation selector → fresh confirmation。

---

## 8.1 Phase A — Reference Atlas

此階段不產生 promotion candidate，只建立研究地圖。

對每個 incumbent **獨立**建立：

- 720-turn conserved / mutable map；
- action-channel mutation entropy；
- public market interaction windows；
- labor / livestock / field asset bottlenecks；
- terminal controller boundary；
- opponent-family interaction tags。

Reference source 包含：

- incumbent own historical traces；
- 8 unique current public agents；
- 9 notebook 中的 replay lineage / mutation evidence。

### 重要限制

Exact duplicates 只計一次；同 lineage descendants 不得被當獨立 efficacy votes。

---

## 8.2 Phase B — Win-Boundary Forensics

此階段仍不修改 incumbent。

在 fresh matched games 中，先找：

> **candidate eventual W 與 L 的 trajectory，在何時第一次出現不可逆的 strategic divergence？**

分析窗口可先以 preceding 8–48 turns 為主要尺度，對以下項目做 forensic attribution：

- market slot / premium timing；
- cash / debt timing；
- worker turns；
- livestock acquisition / placement / feeding；
- shed / capacity pressure；
- crop maintenance / weed repair；
- fertilizer inventory / sell timing；
- terminal liquidation / controller takeover。

目的不是找 correlation 最大的變數，而是找：

> **哪一個 action motif 使 outcome class 從 W-side 移向 L-side，或反之。**

---

## 8.3 Phase C — Branch Proposal Oracle

Branch proposal 應由三類 reference 共同產生：

### 1. Replay mutability

高 mutation entropy turn / action channel 優先。

### 2. Frontier code motifs

若多個強 lineage 獨立使用相似 mechanism，可提高 test priority，但不得視為獨立 efficacy proof。

### 3. Own loss forensics

若某 loss window 顯示明確 resource race，branch 應直接對準該 bottleneck，而不是在附近 arbitrary segment 搜尋。

因此 proposal score 可以概念化為：

\[
P(test\ branch) \propto
Mutability \times FrontierRelevance \times LossWindowMatch
\]

這只是一個 prioritisation 概念，不代表需要建立模型。

---

## 8.4 Phase D — Minimal Causal Ablation

對每個 branch 使用：

- unchanged incumbent 作 direct control；
- identical seed；
- both seats；
- same opponent；
- same initial condition；
- primary outcome transition classification。

### Primary classification

| Control | Candidate | 結果 |
|---|---|---|
| L | D / W | Improve |
| D | W | Improve |
| W | W | Same |
| D | D | Same |
| L | L | Same |
| W | D / L | Worsen |
| D | L | Worsen |

所有 money / margin 指標只作 secondary diagnostics。

---

## 8.5 Phase E — Continuation Horizon Search

若 minimal action branch 有 signal，才研究「後續何時 rejoin」。

這一步是 full-path topology 與舊 micro-tuning 最大的差別。

可比較：

- immediate rejoin；
- 8-turn continuation；
- 16-turn continuation；
- 32-turn continuation；
- natural state rejoin；
- terminal-only handoff。

但 horizon 不應盲目掃描；它應由 mechanism 推導。

例如：

- premium sell preemption：可能只需 1–2 turns debt repayment；
- livestock placement change：可能需要一路保留至下一個 feeding / production cycle；
- terminal takeover：應研究 controller handoff boundary，而不是 arbitrary fixed 2-turn patch。

---

## 8.6 Phase F — Frontier Validation

只有在 causal ablation 顯示 W/D/L movement 後，才值得使用 current 8 unique top-public sources進行 frontier validation。

結果必須：

- family-stratified；
- seat-stratified；
- exact duplicates deduplicated；
- 報 raw W/D/L first；
- secondary 才報 paired margin、own-bank、receipts、market path。

### 停止條件

- 任何明確 `W → L`：立即視為高風險 regression；
- 任一 family/seat 發生 repeatable net worsening：停止 aggregate promotion interpretation；
- 若全部 matched contexts W/D/L class 不變，即使 margin 更好，也不得宣稱 Wins efficacy。

---

# 9. Reference Weighting 原則

Replay / public code 不能等權處理。

建議正式採用四個 weighting dimensions。

## 9.1 Lineage Deduplication

- byte-identical：只計一次；
- highly conserved descendants：降低獨立權重；
- shared opening 不能當多數投票。

## 9.2 Temporal Decay

fossil-record 顯示 leaderboard 是 sweep-driven；因此越舊的 replay，對 current frontier 的 prior 權重應越低。

## 9.3 Habitat Weighting

high-rating / current-public frontier 的 behavior 應高於全 ladder 平均，因為不同 rating band 是不同 opponent habitat。

## 9.4 Evidence-Type Weighting

原則上：

\[
CAUSAL\_WDL > CODE\_MECHANISM > REPLAY\_CORRELATION > POPULARITY
\]

任何 popularity / frequency 都不能覆蓋 direct parent-relative regression evidence。

---

# 10. 三個必要 Calibration Anchors

下一代 topology evaluator 至少必須能在以下案例中得到正確排序。

## 10.1 Positive Control：c27 terminal boundary

歷史 replay-driven terminal controller lineage 中，c27 相對 direct parent c17：

- W/L：13–7；
- mean margin 約 +42。

它代表：

> **經濟 signal 很小，但 W/L topology movement 可觀察。**

若 evaluator 因 margin 小而忽略 c27，則 objective 錯誤。

---

## 10.2 False-Positive Control：Boatlee E2 selector

frozen public fertilizer selector 在 consumed diagnostic contexts：

- 36 positive interventions；
- 12 incumbent fallbacks；
- 0 negative paired margins；
- paired margin / own-bank diagnostics 亮眼；
- actual win delta = 0；
- threshold 完美分離 Roman family。

它代表：

> **economic diagnostic fit ≠ Wins efficacy。**

若 evaluator 把它排在 c27 之前，則 evaluator 不合格。

---

## 10.3 Distribution-Failure Control：fixed horizon 25

fixed horizon 25 曾在 restricted historical aggregate 中看似可行，但在 fresh / parent-relative comparisons 中對 direct parent 與更強 alternatives 出現 regression。

它代表：

> **弱 opponent pool 可以把錯誤 branch 推到 frontier。**

若 evaluator 沒有 direct parent 與 current habitat weighting，就會重複此錯誤。

---

# 11. 對 v27 與 Boatlee 的正式解讀

## 11.1 v27

v27 E2 的核心 negative result 應保留：

- selector 可以改變 action / receipt / public state；
- 但沒有 terminal paired-margin、own-bank 或 W/D/L movement。

因此 v27 不應繼續沿著「只要 public state 被改變，就可能有 value」的 selector-style search。

對 v27 更高資訊價值的方向，是先找：

- loss-side market ordering windows；
- worker allocation bottlenecks；
- route-conservation 之外的 mutation loci；
- terminal handoff / liquidation boundary。

但這些仍應從 v27 自己的 trace 建立，不能由 Boatlee conclusion transplant。

---

## 11.2 Boatlee

Boatlee E2 的 always-on 240/241 block 已被 fresh S2 falsify；frozen selector 則只證明：

- implementation semantics 正確；
- consumed contexts fit 良好；
- Roman proxy risk 明顯；
- 沒有 Win delta。

因此從研究資訊價值角度，本報告建議：

> **deprioritize 把下一個主要 fresh budget 用於確認「step241 fertilizer threshold 是否 generalize」；先確認 step241 fertilizer timing 是否真的是 Wins-relevant axis。**

這不是撤銷既有 remediation 記錄，也不是說 selector 必然無效；而是指出其上游 scientific uncertainty 更大。

---

# 12. Full-Path Search 的正式 Branch Taxonomy

未來 branch atlas 至少應標記以下 topology classes。

## 12.1 Market Temporal Shift

- future sell front-run；
- debt repayment；
- price/demand race；
- public inventory threshold。

## 12.2 Same-Turn Ordering

- sell-slot ranking；
- price-impact ordering；
- demand urgency ordering。

## 12.3 Labor / Worker Allocation

- hire timing；
- actor routing；
- short repair 是否避免後續 lost worker turns。

## 12.4 Asset / Livestock Topology

- placement；
- feeding / production continuity；
- abandon vs preserve 的 opportunity cost。

資產存活不具 intrinsic priority；若剩餘資產價值低於 worker turn、capacity、capital timing 或 market opportunity cost，放棄可以是合理 branch。

## 12.5 Maintenance / Repair

- weeds；
- pending placement；
- invalid route-state recovery。

此類 branch 通常目標是保住 continuation spine，而不是產生新的主策略。

## 12.6 Opponent-Conditioned Counter

- near-clone detection；
- livestock signature；
- family-conditioned market preemption。

## 12.7 Terminal Controller Boundary

- fixed route 何時停止；
- observation-driven liquidation 何時接管；
- one-step-too-early / one-step-too-late 的 W/D/L effect。

---

# 13. Reporting Standard

正式 topology report 必須遵循以下順序。

## 13.1 先報 W/D/L

每個 incumbent、每個 opponent family、每個 seat 分開報：

- candidate W/D/L；
- control W/D/L；
- outcome transition counts。

## 13.2 再報 secondary economics

包括：

- paired terminal margin；
- own-bank；
- worst-case downside；
- public prices；
- receipts；
- labor / livestock state。

## 13.3 最後才做 mechanism interpretation

只有在 primary outcome 有 movement 時，secondary diagnostics 才用來回答「為什麼」。

如果 primary outcome 完全不動，則最多只能宣稱：

> economic / state effect exists, Wins efficacy unproven。

---

# 14. 不應再使用的研究捷徑

以下做法在目前 evidence 下應正式排除。

1. **把 paired margin improvement 當 promotion proxy。**
2. **把 public-state/action difference 當 strategically material evidence。**
3. **用 old weak pool 推論 current frontier efficacy。**
4. **把 exact duplicate notebook 重複加權。**
5. **把 replay popularity 當 independent causal votes。**
6. **跨 v27 / Boatlee pooling。**
7. **固定所有 intervention 都必須 2–3 turns rejoin。**
8. **先建立大型 model / shared architecture，再找 mechanism。**
9. **把 smoke reward 當 strength evidence。**
10. **只看 aggregate mean、不做 family / seat tail analysis。**

---

# 15. Formal Research Decision

綜合目前證據，本報告對研究方向作以下正式判定。

## 15.1 Topology search 本身不應被放棄

問題不是 topology 概念錯誤，而是過去把 topology 簡化成：

> 「選一段 route，做一個短 patch，再看 economic delta。」

這個 formulation 太窄。

---

## 15.2 應放棄的是舊 search formulation

新的 full-path topology research 應該：

- 從 Win/Loss boundary 反推；
- 用 replay / code 找 sparse mutable loci；
- 用 W/D/L 做 value label；
- 允許 mechanism-specific continuation；
- 使用 current frontier habitat；
- 對 lineage / duplicate / seat / family 做正確 stratification。

---

## 15.3 Full-path 的研究核心不是「更大搜索」

而是：

> **更正確的搜尋空間與更正確的 supervision。**

如果這兩個問題不先處理，720-turn 全局 search 只會放大 false positives。

---

# 16. 最終結論

本研究的核心結論可濃縮為六點。

### 1. Frontier 並不像 full free-form planner

目前 Public Score 前十與 replay genealogy 都支持「conserved replay spine + sparse overlays」。

### 2. Replay 最適合做 proposal oracle

它可以高品質地回答：

> 哪些 turns / channels / motifs 是 lineage 真正在改的？

但不能單獨回答：

> 改了之後會不會增加 Wins？

### 3. Value oracle 必須是 W/D/L causal evidence

margin、bank、receipt 只能做 mechanism diagnostics。

### 4. Branch value 是 context-conditioned

至少應條件化於：

- incumbent；
- opponent family；
- seat；
- public market / asset state。

### 5. Full-path 的真正難點是 continuation topology

不是找到一個 local action，而是理解這個 action 如何經由 cash、worker、asset、market、terminal state 影響後續 W/L boundary。

### 6. 下一代 topology evaluator 必須通過三個 calibration anchors

- 能辨認 c27 這種 **W/L positive、margin 小** 的 branch；
- 能拒絕 E2 selector 這種 **margin positive、Win delta 0** 的 branch；
- 能拒絕 fixed horizon 25 這種 **弱池 finalist、parent-relative regression** 的 branch。

如果無法做到，search quality 不足以支撐任何 full-path expansion。

最終，本報告對 Kaggriculture Full-Path Topology Searching 的正式定義為：

> **以 incumbent-specific conserved route 為 spine，以 replay/public-frontier mutation loci 為 branch proposal，以 matched W/D/L 為 primary value label，以 mechanism-specific continuation 追蹤跨期因果，並在 lineage-deduplicated、family/seat-stratified 的 current frontier habitat 中完成驗證。**

這個方向保留 topology research 的核心價值，同時避免重複 E1/E2 已經暴露的 margin proxy、weak-pool、short-rejoin 與 aggregate-selection 錯誤。

---

# 附錄 A：主要 Repository Evidence Paths

## A.1 Incumbent / E2

- `AGENTS.md`
- `research/main_approach/README.md`
- `research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md`
- `research/dual_incumbent_topology_search_2026-08-14/e2/remediation_decision.md`

## A.2 Public Agents Registry

- `research/public_agents/README.md`
- `research/public_agents/primary_opponents.json`
- `research/public_agents/primary_opponent_smoke.json`
- `research/public_agents/extraction_manifest.json`

## A.3 Unique Frontier Strategy Sources

- `research/public_agents/lb20260816_01_boatlee_v16_rc5/extracted/main.py`
- `research/public_agents/lb20260816_02_kaito_v25/extracted/main.py`
- `research/public_agents/lb20260816_04_rayk_zero_to_top/extracted/main.py`
- `research/public_agents/lb20260816_05_boatlee_v16_rc5_r5a/extracted/main.py`
- `research/public_agents/lb20260816_06_boatlee_v14_clone_preemption/extracted/main.py`
- `research/public_agents/lb20260816_07_kunal_ttv1/extracted/main.py`
- `research/public_agents/lb20260816_09_bruce_high_score_pipeline/extracted/main.py`
- `research/public_agents/lb20260816_10_prvsiyan_soil/extracted/main.py`

> 注意：rank 3 與 rank 1 byte-identical；rank 8 與 rank 7 byte-identical，因此不另列為 unique source。

---

# 附錄 B：Notebook Evidence Inventory

- `data/some_notebook/everyone-is-playing-the-same-opening.ipynb`
- `data/some_notebook/kaggriculture-daily-replays-the-live-meta-report.ipynb`
- `data/some_notebook/kaggriculture-the-free-experiment-you-already-ran.ipynb`
- `data/some_notebook/kaggriculture-what-kind-of-game-is-this.ipynb`
- `data/some_notebook/kaggriculture-what-kind-of-optimisation-is-this.ipynb`
- `data/some_notebook/mutants-at-the-top-genetic-potential-of-a-replay.ipynb`
- `data/some_notebook/the-leaderboard-has-a-fossil-record.ipynb`
- `data/some_notebook/the-leaderboard-is-a-habitat-gradient.ipynb`
- `data/some_notebook/wins-not-money.ipynb`

---

# 附錄 C：Evidence Interpretation Labels

| Label | 意義 | 可否直接支持 promotion |
|---|---|---|
| `CAUSAL_WDL_CONFIRMED` | Fresh matched parent-relative W/D/L evidence | 可以 |
| `CODE_CONFIRMED_MECHANISM` | 高分 source 中 mechanism 明確存在 | 不可以 |
| `REPLAY_CORRELATION` | Meta/replay 相關性或 population pattern | 不可以 |
| `DIAGNOSTIC_ONLY` | Consumed context、smoke、receipt/state execution evidence | 不可以 |
| `UNVALIDATED_HYPOTHESIS` | 尚未 matched causal test | 不可以 |

---

**End of Report**
