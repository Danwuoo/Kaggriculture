理想的 topology path，我認為**不是一條固定的 719-action 最佳 tape**，而是：

> **一張從 step 0 一路連到 terminal、以 incumbent 為 backbone、只在真正有 strategic consequence 的位置分叉，而且每條 branch 都帶有 outcome-conditioned value 的可執行 DAG / tree。**

這和現在的 `full_action_prefix_trie` 有一個關鍵差別。現在 repo 已經可以表達 common prefix → branch，例如 corpus 有 102,803 個 prefix nodes，甚至觀察到 78 個 common actions 後出現 two-child boundary；但目前 branch support 本身不代表 branch quality。

### 理想形狀大概會是這樣

```text
State 0
  │
  │  conserved spine
  ▼
S0 ──────────────── S78
                      │
                ┌─────┴─────┐
                │           │
              B78-A       B78-B
             value +      value -
                │           × prune
                │
                ▼
              S79
                │
        conserved continuation
                │
                ▼
              S238
                │
       ┌────────┼─────────┐
       │        │         │
   incumbent  front-run  delay
      path       path      path
      0.48       0.61      0.31   ← W probability/reference
       │          │
       │          └──────────────► chosen
       │
       ▼
  natural continuation
       │
       ▼
      S551
       │
   livestock / worker
   topology boundary
       │
    ┌──┴──┐
    │     │
 preserve abandon
  0.42     0.57
            │
            ▼
          S690
            │
      terminal boundary
       ┌────┴────┐
       │         │
 fixed route   controller
   0.46         0.63
                 │
                 ▼
              terminal
```

數字不是現在 repo 已有的真實估計，只是在表示理想結構。

最重要的是：**branch 上面要有 value，而不只是 support。**

---

## 一個理想 topology node 應該包含什麼

我會把每個 node 定義成：

[
N_t =
(
t,;
state\ signature,;
incumbent,;
opponent\ context,;
resource\ topology
)
]

不是單純：

```text
step = 240
```

而是例如：

```text
step = 240
incumbent = Boatlee
market:
    fertilizer_price = ...
    fertilizer_inventory = ...
cash topology = ...
worker topology = ...
livestock topology = ...
opponent family posterior = ...
seat = 1
```

所以 **step 240 本身不是 topology node**。

真正的 node 是：

> 「Boatlee 在 step 240、這種資金／市場／livestock／opponent interaction state 下」。

這也是附檔報告其實已經接近的地方：它認為 branch value 至少必須 conditioning 在 incumbent、opponent family、seat、public state，而不能只估一個無條件的 (Q(s,a))。

---

## Edge 才是真正的 topology branch

一條 edge 也不應只是：

```text
step 241 SELL FERTILIZER 16
```

而應該是：

```text
Branch B
trigger:
    state signature X

intervention:
    step 241 SELL FERTILIZER 16

causal continuation:
    market demand changes
    cash changes
    opponent capital path changes
    next production cycle changes

rejoin:
    when state becomes compatible with incumbent again
    NOT necessarily step 242

terminal effect:
    ΔW/D/L distribution
```

也就是：

[
Edge =
Trigger

* ActionMotif
* Continuation
* RejoinCondition
* Value
  ]

這裡 **Continuation 是 branch 的一部分**。

這點非常重要。

現在很多舊實驗等於：

```text
A ─── branch ─── A
        ↑
      1~8 turns
```

但真正 topology 可能是：

```text
A ─── branch ─────────────── B'
       │
       ├── cash topology changed
       ├── labor topology changed
       ├── asset topology changed
       └── market topology changed

                       ↓
              40 turns later才重新
              接回 equivalent state
```

附檔也正確指出 fixed short rejoin 可能切斷 livestock、worker、cash、market 等 persistent causal chain。

---

# 最關鍵的是 branch value 長什麼樣

我不會給 edge 一個單一 scalar：

```text
score = +213 margin
```

而會保存一個 **conditional outcome vector**：

[
V(e)=
{
P(W),P(D),P(L),
\Delta P(W),
uncertainty,
support
}
]

再 stratify：

```text
Branch: premium_front_run@240

         ΔW       ΔD       ΔL
aaa     +0.12    -0.02    -0.10
bbb     +0.08     0.00    -0.08
ccc     -0.04     0.00    +0.04
ddd     -0.21    +0.03    +0.18
eee     +0.17    -0.01    -0.16
```

這樣 search 才知道：

> 這不是「good branch」或「bad branch」。

而是：

> **對 aaa / eee 是 good edge，但對 ddd 是 bad edge。**

這正是 Boatlee E2 現有結果最明顯的教訓：aggregate mean 曾被單一 Roman context 扭曲，而且 selector 最後雖有漂亮 diagnostic，actual win delta 還是 0。

---

# 所以 topology 最好分成 3 層

### 第一層：Structural topology

回答：

> 哪裡有 branch？

來源可以是：

* replay prefix trie
* mutation entropy
* public-agent code
* lineage differences
* incumbent historical paths

例如現在已有：

```text
0 ───────── 78
              ├── A
              └── B
```

這層目前 repo **其實已經做得不少**。Full-tape corpus 已保留 complete 719-action tape、unit/market topology 和 common-prefix branches。

### 第二層：Causal topology

回答：

> 走 A 之後，實際會改變哪些後續 state？

例如：

```text
SELL earlier
  ↓
market inventory ↓
  ↓
opponent price / purchase timing
  ↓
opponent capital
  ↓
animal purchase delayed
  ↓
late-game production
```

這一層決定 branch 的 **natural continuation horizon**。

### 第三層：Outcome topology

回答：

> 這條 causal branch 最後把 Win/Loss boundary 往哪裡推？

這才是你現在指出最缺的 layer。

---

# 最理想的 Full-Path Topology Atlas

最後資料結構我會想像成：

```text
ROOT
│
├── Spine 0–77
│
├── Boundary #1 @ ~78
│     ├── branch A
│     │     ├── conditions
│     │     ├── WDL value
│     │     └── continuation → node 104
│     │
│     └── branch B
│           ├── conditions
│           ├── WDL value
│           └── continuation → node 101
│
├── Spine 104–237
│
├── Market boundary
│     ├── incumbent timing
│     ├── front-run
│     └── delayed sell
│
├── Livestock/labor boundary
│     ├── preserve asset
│     ├── repair
│     └── abandon/reallocate
│
├── ...
│
└── Terminal controller boundary
      ├── continue tape
      ├── liquidation
      └── reactive controller
```

每條 branch 同時附：

```text
support_prior
lineage_sources
state_compatibility
parent
children

matched_WDL
family_WDL
seat_WDL

secondary_margin
secondary_bank

causal_horizon
natural_rejoin_state

confidence
freshness
```

其中優先級應是：

[
\boxed{
WDL\ causal\ value

>

state\ compatibility

>

frontier/replay\ prior

>

margin
}
]

而不是現在比較容易變成：

[
support / margin
\rightarrow candidate
\rightarrow
最後才發現 Win 沒動
]

---

## 更進一步：理想 topology 其實不是「找最佳 path」

這是我認為最重要的一點。

最終目的不應該是得到：

```text
BEST_PATH = [a0, a1, a2, ..., a718]
```

而應該得到：

```text
BEST_POLICY_TOPOLOGY
```

也就是：

[
\pi(N_t)
========

\arg\max_{e\in outgoing(N_t)}
E[W\mid N_t,e]
]

所以同一個 step：

```text
step 240
```

對不同 game 可以選不同 branch。

例如：

```text
                  step 240
                     │
        ┌────────────┼─────────────┐
        │            │             │
    RC5-like       Roman        unknown
        │            │             │
    front-run      incumbent     conservative
```

這樣 topological search 找到的不是一條 tape，而是：

> **一條 conserved spine 加上一組經 W/D/L 校準過的 conditional routing rules。**

這其實也和目前 frontier agent 的形狀吻合：附檔把它總結成 conserved spine + sparse overlays，而不是每 turn 做 global replanning。

---

### 如果壓成一句話

你現在真正應該追的「ideal topology path」我會定義為：

[
\boxed{
\text{Outcome-Conditioned Executable Full-Path DAG}
}
]

而不是：

[
\text{719-turn tape}
]

也不是：

[
\text{incumbent + randomly selected local patches}
]

它的核心單位應該變成：

[
\boxed{
State\ Boundary
\rightarrow
Branch
\rightarrow
Causal\ Continuation
\rightarrow
WDL\ Value
}
]

**這樣 topology search 才第一次真正擁有「往哪裡走」的方向，而不只是「哪裡可以改」。**
