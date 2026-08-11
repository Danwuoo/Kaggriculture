# Kaggriculture Agent Strategy

## 0. 2026-08-07 證據與正式語意修訂

本節優先於下方較早的策略敘述；下方數值若未被新證據確認，均只視為
hand-authored prior，不是引擎事實或已驗證最優解。

### 0.1 證據層級

1. **ENGINE_FACT**：目前官方 `kaggriculture.py` 與相同 commit 的官方對局
   逐 transition 對照；可以作 correctness constraint。
2. **MATCHED_EVIDENCE**：相同 seed、seat、opponent block 的官方引擎 paired
   對局，保留所有 losses，並以 paired match wins 與 seed-cluster bootstrap
   95% CI 判斷效力。
3. **OBSERVATIONAL_EVIDENCE**：完整官方 daily episode dataset 的匿名聚合；
   可生成 prior 或候選，但不能單獨證明因果或競爭效力。
4. **HAND_AUTHORED_PRIOR**：例如 3 cow + 1 sheep 開局、melon capital event、
   8 cow／5–6 sheep 成熟拓撲。它是搜尋起點，必須可被 scheduler、可行性與
   paired evidence 推翻。
5. **HYPOTHESIS**：包含 EOD auto-drop 利用、WATER／CARE 邊際行動價值、
   finite-season animal NPV、特定 market ordering。必須先獨立消融；不得因
   `error.md` 提出可能機制就直接凍結成策略。

`error.md` 中已由官方 source／transition 證實的 ERR-025 requested-quantity
污染屬 ENGINE_FACT；selector quality、維護最適頻率及特定排序收益仍須
matched ablation。歷史污染 artifact 保留為 rejected regression evidence，
不得覆寫或重新描述為有效 route bank。

### 0.2 正式雙人市場語意

- 每回合 unit actions 先於 market；SELL 只能消耗 shed，不能直接出售仍在
  worker backpack 的物品。
- 每位玩家只保留前 10 筆 market orders。引擎按 order index 前進；同一
  index 先執行雙方 atomic `HIRE`／`BUY_LAND`，再對該 index 的非 atomic
  order 逐單位 lockstep。
- 每一單位先用當下 market state 為雙方 quote，再依 player order commit；
  每次成功成交都會改變資金、shed、market inventory 與後續 quote。SELL
  遇到 shed 不足、BUY 遇到資金或容量不足即停止；BUY_ANIMAL 與
  BUY_PRODUCT 並非 requested quantity 保證成交。
- split orders 不改善同一玩家連續單位的單邊價格曲線，但會改變與對手
  order-index 的對齊，因此其效力只能由正式雙人 shadow market 與 paired
  games 評估。

任何 replay 特徵都必須累加官方語意下的 **executed** quantity／coins，不能
累加 request。shadow 重建必須逐 transition 與官方 money 相符。

2026-08-07 semantic commit `0528e46cc8a6a50a1e07c3aebaa0b911cd835927`
新增 shed-access 例外：四個中心 access tiles 即使仍為 `LOCKED`，也可執行
`PICKUP`、`DROP` 與放入 shed 的 `PLACE`；其他會修改 tile 的行動仍 no-op。
同日再核對的 upstream `bbcdd460accc16fdb1d1074b8c5b1d30ea92da4a`
只做 package version bump，Kaggriculture 目錄與 engine blob 皆未變。entry
matched matrices 因而與最新官方 Kaggriculture source byte-identical；較早 daily
replays 仍按其記錄時的 module version 重建實際成交，且上述 commits 未改動
market loop。

### 0.3 日終、維護與有限季節價值

官方在每個 day 的最後一個 transition 依序 refresh plants／animals、spawn
weeds，然後把每個 worker inventory 自動放入 shed；超過 100 的部分永久
丟棄，接著重設位置、hands 與 inventories。EOD auto-drop 因而可省下回程
與 DROP 行動，但只有在容量、動物搬運、終局清算及下一日銷售均安全時才是
候選，且必須記錄 auto-drop units 與 cap waste。

P0 第二次缺水／缺飼料永遠是 constraint，普通經濟分數不得覆蓋。非危急
WATER／CARE 則以邊際**行動**價值評估：實際新增 yield、存活／產量窗口、
held cap、後續 FEED、旅行與替代工作成本都要計入。動物購買使用購買日開始
的 finite-season NPV，包含 placement、首次產出前飼料、每日維護、CARE、
harvest／shipment、容量風險與 terminal slack，而不是無限期平均收益。

### 0.4 競爭目標與 route contract

最佳化目標依序為 correctness／safety、matched paired wins、最弱正常強對手
勝率與信賴下界、retained-loss 表現，再看 terminal difference。absolute raw
reward 只可診斷產能，不能代表競爭品質。route quality 必須加入
opponent/style-conditioned relative terminal evidence。

route memory 只輸出 scheduler 原生可消化的 macro targets、deadline、capital
與 inventory reserve、acceptable bands、shipment window；不得輸出固定 action
tape。selector 只可在 shop、market、capital、land、public opponent cohort 或
feasibility 的重大事件重評，使用 deterministic tie-break、cooldown、margin 與
episode switch cap 控制 churn。P0–P5 scheduler 及 legality projector 始終是
不可繞過的執行與最終 action boundary。

研究日期：2026-08-05  
狀態：設計草案，供 multi-file agent 實作、模擬與迭代使用

## 1. 核心結論

本專案採用「高效率基準經濟路線＋閉環任務排程＋對手感知市場控制」的混合策略，而不是純固定腳本或端到端強化學習。

建議的成熟農場基準約為：

- 8 頭牛。
- 5–6 隻羊。
- 6–7 格輪作草莓。
- 少量小麥作為飼料與臨時填充作物。
- 少量開局甜瓜作為第一次資本跳升。
- 解鎖 NE 與 SW；SE 必須通過剩餘時間與邊際收益檢查才購買。
- 生產高峰期每日約 10–12 名臨時工，實際數量由工作負載決定。

這只是穩健起點，不應硬編碼成不可變的唯一策略。真正的競爭優勢應來自：

1. 不發生死亡、爆倉、錯位與 silent no-op。
2. 比對手更有效率地完成餵食、照顧、收成與物流。
3. 根據城鎮商店、即時價格和對手公開農場調整生產與出貨。
4. 對敏感商品進行 SELL front-running、分時變現與終局清倉。
5. 在雜草或狀態偏移時局部修復，而不讓整套排程失同步。

## 2. 官方限制與設計預算

| 項目 | 限制／預設值 | 設計目標 |
|---|---:|---:|
| Episode | 720 回合 | 僅 step 0–718 可依賴為有效行動 |
| 每日回合 | 24 | 以 day/hour 做分層規劃 |
| 單回合時間 | 1 秒 | 軟截止 0.70 秒；一般回合控制於 0.15 秒內 |
| vCPU | 1.6 | 不依賴多程序或大量平行計算 |
| RAM | 6.5 GiB | runtime 目標低於 256 MiB |
| HDD | 8 GiB | 不在比賽中產生大型檔案 |
| Submission | 100 MiB | 實際目標低於 5 MiB |
| 市場訂單 | 每回合最多 10 筆 | 依價值排序，禁止溢出後被靜默丟棄 |
| 倉庫 | 100 件非種子物品 | 保留安全空間並預先清倉 |

設計原則：複雜度放在演算法、離線模擬和參數搜尋；線上 Agent 僅保留經壓縮、可快取且可降級的決策核心。

## 3. 建議的 Multi-file 架構

```text
submission/
├── main.py                  # Kaggle entrypoint：agent(obs)
├── controller.py            # 總控制器、時間預算、快取與降級
├── state.py                 # observation 正規化與衍生特徵
├── rules.py                 # 官方規則、合法性與安全條件
├── constants.py             # 作物、動物、價格曲線與可調參數
├── scheduler.py             # 任務生成、優先級與工人匹配
├── pathfinding.py           # BFS、距離矩陣與回倉路徑
├── economy.py               # 生產報酬、飼料與資本配置
├── market.py                # 精確逐單位價格、SELL 排序與清倉
├── opponent.py              # 對手產量、收成窗口與出貨推測
├── simulator.py             # 宏觀前向模擬與情境評分
├── strategy.py              # 開局、中期、成熟期與終局政策
└── parameters.py            # 離線調好的閾值與權重
```

`main.py` 保持極薄：

```python
from controller import Controller

_controllers = {}


def agent(obs):
    player = int(obs.get("player", 0))
    controller = _controllers.setdefault(player, Controller(player))
    return controller.act(obs)
```

Controller 必須在 `step` 回到 0 或倒退時清除上一局狀態。本機以同一 Python 模組同時測試兩個座位時，狀態必須以 player 分開，不能使用單一未分流的全域狀態。

## 4. 每回合決策管線

```text
observation
  -> 狀態正規化
  -> 新局／新日／重大事件偵測
  -> 宏觀計畫更新（低頻）
  -> 建立強制安全任務
  -> 建立生產、物流與投資任務
  -> 工人－任務匹配
  -> 對手產量預測
  -> 市場訂單最佳化
  -> 合法性與資源一致性驗證
  -> 時間不足時降級
  -> action dict
```

低頻宏觀規劃只在以下時點重算：

- `hour == 0`。
- 新商店解鎖。
- 土地狀態改變。
- 動物逃跑或關鍵作物變成雜草。
- 現金、飼料或倉庫狀態跨過安全閾值。
- 對手公開農場顯示即將大量收成。
- 進入終局清算期。

其他回合沿用快取計畫，只更新任務、價格、庫存與合法性。

## 5. 四階段經濟路線

### 5.1 第 0–3 天：建立生產引擎

主要目標：

- 優先建立約 3 牛＋1 羊的初始畜牧底盤。
- 購買足夠的短期小麥飼料，避免動物因現金耗盡而逃跑。
- 種植約 4–6 格甜瓜，作為第 10 天附近的資本事件。
- 提早雇用廉價工人，但必須確認任務量能有效利用新增行動。
- 暫緩購地，除非模擬顯示現有 25 格已構成真實瓶頸。

執行限制：

- 市場在農場行動之後處理；本回合購買的種子、動物、飼料或肥料不能供本回合農場動作使用。
- 本回合 HIRE 的工人下一回合才可開始行動。
- 動物購買後先進入 shed，必須經過 PICKUP、移動及 PLACE。
- 新種作物當天一定要 WATER，否則當晚成為 WEED。

### 5.2 第 4–10 天：擴張與第一次變現

- 現金和勞動力允許時購買 NE。
- 維持動物 FEED 與 CARE。
- 甜瓜在年齡 6–10 每日澆水；年齡 10 已達 6 單位上限。
- 提前安排 HARVEST、DROP/回倉與 SELL，不能假設收成後商品已在 shed。
- 觀察對手甜瓜種植日與格數；對手若將大量成熟，優先在其可能出貨前變現。

### 5.3 第 11–24 天：成熟混合農場

逐步接近基準結構：

- 8 牛。
- 5–6 羊。
- 6–7 格草莓，採分批輪作。
- NE＋SW。
- 約 10–12 名工人，由工作負載調整。

策略要求：

- 草莓不可同一天大批種植，以免同步結束生產並形成雜草浪潮。
- 靠近 shed 的格子配置給動物與高頻物流作物。
- 預留的未來牧場格可先種短週期小麥，但必須在建造前成熟並清空。
- SE 僅在新增土地的預期終局淨收益高於 4,000、額外勞動與通勤成本時購買。
- 根據已解鎖商店調整牛、羊、草莓、番茄及胡蘿蔔的邊際配置。

### 5.4 第 25–29 天：終局清算

- 停止所有無法在 step 718 前完成成熟、收成、回倉與出售的投資。
- 依剩餘回合建立最低清倉速度，不再只等待理想保留價格。
- 預先將遠端商品送回 shed，避免最後一日仍在搬運。
- step 717–718 啟動強制終局控制；step 719 不作為可靠執行回合。
- 即使售價已為 1，也要出售最後無法恢復價格的庫存，因為未售庫存在終局價值為 0。

## 6. 動物與作物的數值模型

### 6.1 動物穩態價值

假設持續 FEED、CARE、及時 HARVEST，價格維持基準，小麥成本為 25：

| 動物 | CARE 後穩態產量／日 | 基準收入／日 | 扣飼料後／日 |
|---|---:|---:|---:|
| 鵝 | 2 蛋 | 100 | 75 |
| 牛 | 1.5 牛奶 | 240 | 215 |
| 羊 | 約 1.33 羊毛 | 約 267 | 約 242 |

以上尚未計入每日可收集的一份肥料，也未扣除 FEED、CARE、HARVEST、COLLECT_FERTILIZER、PICKUP、DROP 與移動的行動機會成本。

動物評分應使用：

```text
預期產品收入
+ 預期肥料收入
- 動物購買成本
- 飼料成本
- 建築與物流的行動影子價格
- 產品價格崩跌風險
- 終局無法回收風險
```

### 6.2 無肥料作物基準

| 作物 | 基準單輪產量 | 單輪毛利 | 約略毛利／占地日 |
|---|---:|---:|---:|
| 小麥 | 4 | 90 | 18.00 |
| 胡蘿蔔 | 3 | 85 | 21.25 |
| 番茄 | 4 | 190 | 15.83 |
| 草莓 | 4 | 380 | 22.35 |
| 甜瓜 | 6 | 1,420 | 129.09 |

這些數字只適用於基準價格且忽略移動和勞動。甜瓜的紙面優勢會被共享市場的低需求與價格衝擊大幅削弱。

### 6.3 肥料機會成本

一份肥料基準售價為 100。若正確安排 FERTILIZE、WATER 與 HARVEST，增量約為：

| 作物 | 最大增量 | 基準增量價值 | 初步判斷 |
|---|---:|---:|---|
| 小麥 | +2 | 50 | 通常不如直接出售肥料 |
| 胡蘿蔔 | +1 | 35 | 通常不施肥 |
| 番茄 | +3 | 180 | 價格與物流允許時可施肥 |
| 草莓 | +2 | 240 | 通常是較好的施肥目標 |
| 甜瓜 | 產量不增加 | 約提早 2 天達上限 | 以土地周轉價值判斷 |

實際判斷必須使用即時肥料售價與產品預測售價：

```text
施肥增量價值
= 額外產品數 × 預測邊際售價
  + 提前釋放土地的價值
  - 肥料可直接出售的收入
  - FERTILIZE、WATER、運輸與額外 HARVEST 成本
```

番茄或草莓若未及時 HARVEST，`yield_units` 上限可能吃掉施肥增量，排程器必須先確認倉儲與收成容量。

## 7. 任務優先級與工人排程

使用不可被普通經濟分數覆蓋的 lexicographic priority：

| 優先級 | 任務 |
|---:|---|
| P0 | 第二次缺水／缺糧將導致死亡的 WATER、FEED |
| P1 | 即將腐爛、已滿持有上限、倉庫即將溢出的 HARVEST、DROP、SELL 準備 |
| P2 | 甜瓜產量窗口、施肥後生產日、即將到期的強時限任務 |
| P3 | 一般 FEED、CARE、成熟收成與必要物流 |
| P4 | COLLECT_FERTILIZER、補充飼料與短期現金任務 |
| P5 | PLANT、BUILD、DIG、投資準備與低緊急度維護 |

同優先級任務使用數值分數：

```text
score(unit, job)
= expected_coin_value(job)
  + urgency_bonus(job)
  - distance(unit, job) * travel_shadow_price
  - inventory_failure_risk
  - terminal_infeasibility_penalty
```

### 7.1 路徑規劃

- 地圖只有 10×10，可預先建立所有格子的距離矩陣。
- 土地解鎖狀態改變時才重建距離快取。
- LOCKED 格可通行但不可執行農場動作。
- 路徑規劃不可把 locked tile 當障礙，否則早期工人可能被困在出生點。
- 工人與任務初版使用貪婪匹配；確認 CPU 預算後再考慮 Hungarian assignment。

### 7.2 資源一致性

任務指派後立即更新 shadow inventory，避免：

- 多名工人承諾同一件動物或肥料。
- PLANT 數量超過現有種子，導致該作物本回合所有 PLANT 原子性取消。
- 多人重複處理同一格已完成的 WATER、CARE 或收成。
- 需要出售的商品仍在工人背包而不在 shed。

## 8. 市場策略

### 8.1 精確逐單位定價

市場模擬應複製官方逐單位成交邏輯，而不是用目前價格乘數量：

```python
def projected_sale(item, quantity, inventory, market_price):
    revenue = 0
    inv = inventory
    for _ in range(quantity):
        price = market_price(item, inv)
        revenue += price
        if price > 1:
            inv += 1
    return revenue, inv
```

同一回合把大單拆成多個小單，不會憑空改善收入，因為單一大單本來就逐單位重新定價。真正有效的是：

- 跨回合或跨日分時出售，讓城鎮消耗恢復價格。
- 在對手大量出貨前 front-run。
- 把價格最敏感、對手暴露最高的商品排在市場訂單前方。
- 控制清倉速度與倉庫占用。

### 8.2 SELL 排序

候選商品可使用：

```text
sell_priority(item)
= opponent_exposure(item)
   * glut_sensitivity(item)
   * current_price(item)
   * log(1 + own_sellable_quantity(item))
```

再加入：

- 倉庫爆滿加成。
- 商品即將大量成熟的加成。
- 剩餘回合不足的終局加成。
- 城鎮需求即將觸發的等待價值。
- 價格已接近 1 且仍有恢復時間時的延後選項。

### 8.3 商品特性

- 小麥：商店需求最高，亦是動物飼料，應同時計算出售價值與飼料影子價值。
- 草莓：需求高但 glut 線性敏感，適合穩定分批出售。
- 牛奶：需求高、單價高、雙方牛群相似時容易發生出貨競爭。
- 羊毛：單價高且價格曲線敏感，Yarn Store 是否已解鎖很重要。
- 甜瓜：沒有專門商店需求，最需要早期變現和對手預測。
- 肥料：完全沒有城鎮需求，應早期持續出售或轉為高價值施肥用途。
- 蛋：價格較穩但單位經濟弱，通常不是主力配置。

### 8.4 同回合資金與物流

- SELL 只消耗 shed 庫存。
- HARVEST 先進入當前工人背包，不能由同一工人在同一回合再 DROP。
- 已攜帶商品的工人可先 DROP，因農場動作早於市場，該商品可在同回合 SELL。
- 同一市場 action 中，較早的 SELL 可以為較晚的 BUY/HIRE/BUY_LAND 提供資金。
- 市場收入不能倒過來供應已處理完的同回合農場行動。

## 9. 對手模型

對手公開資訊包括：

- 資金。
- 作物類型、位置、種植日、可收成量與施肥狀態。
- 動物種類、位置、產品持有量、餵食與照顧狀態。
- 農夫與工人位置。
- 土地解鎖與當日雇工數。

不可見資訊包括 shed、種子與工人背包，因此模型只輸出範圍或機率，不假裝知道精確數量。

每回合預測未來 1、3、6、12、24 回合內：

- 各商品可能收成量。
- 對手送回 shed 的最早時間。
- 大量出貨概率。
- 對手是否接近自己的固定路線或鏡像策略。

例如對手有 16 格同日種植甜瓜時，應預期約 96 單位的潛在成熟量，並把預測運輸時間納入 SELL front-running。

禁止以隊名、使用者身分或私有資訊做 hardcode routing；只使用可觀察狀態與行為特徵。

## 10. 閉環恢復

固定高效路線容易因隨機 WEED 或一次 silent no-op 整體錯位。使用局部交易式恢復：

```text
預定 PLANT／BUILD
  -> 目標格是 WEED？
  -> DIG
  -> 下一回合重試原意圖
  -> 僅該工人局部追趕最多 N 回合
  -> 回到主排程
```

恢復期間：

- 不改動其他工人的安全任務。
- 不無條件改動市場訂單。
- 每回合重新確認原目標是否合法且仍有經濟價值。
- 設定追趕上限，避免永遠偏離主策略。

角色配置應主要是土地解鎖和固定區域的純函數，不能因現金或短期 herd count 每回合漂移，否則已種作物可能被排程器遺忘。

## 11. 宏觀模擬器

不要在每回合模擬完整 10×10 地圖的 720 回合樹。使用壓縮狀態：

```python
MacroState(
    day,
    money,
    shed,
    seeds,
    herd_counts,
    crop_cohorts,
    market_inventory,
    unlocked_shops,
    unlocked_land,
    estimated_labor_capacity,
    opponent_production_forecast,
)
```

作物以 cohort 表示：

```python
CropCohort(
    crop="STRAWBERRY",
    planted_day=12,
    count=6,
    expected_units_per_tile=4,
)
```

每天或重大事件時比較 16–64 個候選情境：

```text
候選 herd/crop/land 配置
× 尚未解鎖商店的合理情境
× 對手低／中／高出貨情境
× 不同 SELL 保留價格與清倉速度
```

目標函數以勝率為中心，不只最大化自己的平均銀行：

```text
utility
= expected_terminal_money_difference
  - downside_risk
  - probability_of_asset_loss
  - probability_of_unsold_inventory
  - timeout_or_illegal_action_penalty
```

完整動作搜尋只用於很短的局部問題，例如：

- 一組工人在未來 3–8 回合如何完成 harvest/drop/feed。
- SELL 訂單的排列。
- 是否現在買地或等待一次成熟收成。

## 12. 時間與資源降級

採用三層策略：

```text
Level 0：宏觀模擬＋對手模型＋完整市場控制
Level 1：沿用快取宏觀計畫，只更新任務與市場
Level 2：安全模式，只保證存活、收成、回倉與合法 action
```

```python
from time import perf_counter

start = perf_counter()
soft_deadline = start + 0.70
```

- 到 0.45 秒停止新增模擬情境。
- 到 0.60 秒停止可選最佳化，進入 Level 1。
- 到 0.70 秒立即輸出已驗證 action。
- 任何例外都回傳 Level 2，而不是讓 Episode Error。

Runtime 禁止：

- 網路請求。
- 子程序或多程序。
- 讀取大型 replay。
- Pandas／sklearn 重型初始化。
- 每回合寫檔。
- 大量 stdout/stderr 日誌。

離線訓練的 sklearn、CMA-ES 或其他模型應匯出為小型係數、閾值或查表，線上使用純 Python 計算。

## 13. 驗證方法

### 13.1 正確性測試

- 每種 action 的合法／非法案例。
- 種植日 WATER。
- 連續缺水／缺糧計數。
- CARE bonus 與持有上限。
- 肥料生成、收集、施用與出售。
- HARVEST -> inventory -> DROP -> shed -> SELL 流程。
- 倉庫容量與 overflow。
- 多工人 PLANT 的原子性種子驗證。
- step 717、718、719 終局行為。
- 新 Episode 狀態重置與雙座位隔離。

### 13.2 效能測試

對完整 720 回合記錄：

- p50、p95、p99 每回合時間。
- 最大時間。
- 記憶體峰值。
- Level 1/2 降級次數。
- silent no-op 數量。

目標：

- p95 < 150 ms。
- p99 < 400 ms。
- 最大值 < 750 ms。
- 無任何 timeout。

### 13.3 策略升級門檻

每個候選版本必須：

1. Self-play 兩方皆為 DONE。
2. 擊敗 starter，僅作 plumbing smoke test。
3. 與上一最佳版本使用相同 seeds 做配對比較。
4. 每個 seed 測試雙座位。
5. 至少測試一種不同風格的公開 Agent。
6. 保留並分析敗局，不刪除不利樣本。
7. 同時報告勝率、平均終局差、最差分位數與錯誤率。
8. 只有勝負改善穩定時才升級；勝很多不比小勝取得更多 Rating。

兩個 active submissions 應保持策略多樣性：

- A：穩健、低變異的基準經濟路線。
- B：較強的 opponent-aware、市場 front-running 或情境路由版本。

避免兩份近乎相同的 Agent 同時暴露在相同 Meta 風險下。

## 14. 實作順序

### Milestone 1：可靠底盤

- Multi-file submission 可載入。
- observation parser。
- 合法性檢查。
- 距離快取。
- 基本 task scheduler。
- 終局清倉。

### Milestone 2：混合畜牧基準

- 3C1S 開局。
- 甜瓜資本事件。
- 8C5/6S＋草莓成熟路線。
- 動態雇工與 NE/SW 解鎖。
- 無雜草、無逃跑、無爆倉。

### Milestone 3：精確市場

- 官方價格函數。
- 逐單位邊際收益。
- 商品保留價格。
- 分時變現與清倉 glide path。
- 肥料出售／施用選擇。

### Milestone 4：對手感知

- 作物 cohort 與動物產量預測。
- 對手出貨窗口。
- SELL front-running。
- 近鏡像與 Meta 相似性偵測。

### Milestone 5：宏觀模擬與離線調參

- 壓縮 MacroState。
- 每日多情境規劃。
- 參數搜尋。
- 官方每日高分 Episodes 的 imitation/behavior 特徵分析。
- 自動化 paired-seat regression arena。

## 15. 研究依據

官方與公開資料：

- Kaggle 官方環境原始碼：<https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/kaggriculture/kaggriculture.py>
- Kaggriculture 環境規格：<https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/kaggriculture/kaggriculture.json>
- 官方每日高分 Episodes：<https://www.kaggle.com/datasets/kaggle/kaggriculture-episodes-index>
- 公開 Meta 統計：<https://www.kaggle.com/code/georgymamarin/kaggriculture-what-the-top-farms-do-a-live-meta>
- 公開策略演化研究：<https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta>
- Barnyard Economist：<https://www.kaggle.com/code/romanrozen/strong-statr-baseline-agent-lb-950>
- Closed-loop 與 WEED recovery：<https://www.kaggle.com/code/kaitofukami/159-160-vs-frontier-v20-weed-slip-recovery>
- 文件與引擎差異澄清：<https://www.kaggle.com/competitions/kaggriculture/discussion/732450>
- 肥料官方澄清：<https://www.kaggle.com/competitions/kaggriculture/discussion/731953>

當文件、Notebook 或討論與實際行為衝突時，以目前競賽使用的官方引擎版本為準。公開 Notebook 的本地勝率是研究證據，不視為官方排行榜保證。
