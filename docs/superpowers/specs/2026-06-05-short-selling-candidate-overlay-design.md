# Short-Selling Candidate Overlay — Design

**Date:** 2026-06-05
**Status:** Approved (ready for plan)
**Related code:** `backend/services/hot_tokens_scanner.py`, `backend/api/hot_tokens.py`, `frontend/src/views/ShortsView.vue`
**Upstream architecture:** `docs/short-selling-data-architecture.md`（5 维度框架）
**Product positioning (decided):** HotToken 是中性涨幅榜（不做空特化）

---

## 0. TL;DR

`/analysis` tab 的产品定位 = 涨幅热度榜（保留） + 在涨幅榜上叠加"做空适配度"信号（新增）。当前代码的 gap 集中在字段层：
- 13 个 API 字段是 `getattr` 兜底默认值
- `_calculate_short_metrics` 算的"拥挤度"方向反了（算成空头拥挤、应该算多头拥挤）
- "做空评级 S/A/B/C/D" 字段从未被后端填过
- 市值 / 板块 / 解锁压力 / 筹码集中度四项"做空基本面"数据全缺

---

## 1. 一句话总结

**`/analysis` tab 的产品定位 = 涨幅热度榜（保留） + 在涨幅榜上叠加"做空适配度"信号（新增）。** 当前代码的 gap 集中在字段层：
- 13 个 API 字段是 `getattr` 兜底默认值
- `_calculate_short_metrics` 算的"拥挤度"方向反了（算成空头拥挤、应该算多头拥挤）
- "做空评级 S/A/B/C/D" 字段从未被后端填过
- 市值 / 板块 / 解锁压力 / 筹码集中度四项"做空基本面"数据全缺

---

## 2. 现状（代码事实）

### 2.1 排序公式 — `_calculate_heat_scores`

```python
# backend/services/hot_tokens_scanner.py:261-265
token.heat_score = (
    volume_score    * 0.5 +   # 归一化后的 24h 成交额
    change_score    * 0.3 +   # |24h 涨跌幅|
    funding_score   * 0.2     # |资金费率|
)
```

排序方向：DESC，取前 50。**这是涨幅热度榜，对应"找热门标的"的产品意图，不动。**

### 2.2 派生指标 — `_calculate_short_metrics`（**方向错位 + 不进排序**）

```python
# backend/services/hot_tokens_scanner.py:270-319
funding_normalized = max(min(-token.funding_rate / 0.01, 1.0), -1.0)
#                ↑ 负号 → funding 为负（空头付费）时归一化为正
ls_normalized = max(min(1.0 - token.long_short_ratio, 1.0), 0.0)
#                            ↑ 减号 → ls_ratio 越低（空头多）归一化越高

token.crowdedness_score   # 空头拥挤度（0-1）
token.squeeze_risk        # 空头轧空风险
token.rebound_potential   # 大跌反弹潜力
token.short_risk_rating   # low/medium/high/extreme
```

**方向错位**：在"涨幅榜里找做空机会"的语境下，我们关心的是**多头拥挤度**（longs 越多越好做空），但代码算的是**空头拥挤度**（shorts 越多）。这俩方向完全相反。

### 2.3 前端看到的字段

`/api/hot_tokens/` 返 13 个 `getattr` 兜底字段（`api/hot_tokens.py:38-51`）：

| # | 字段 | 默认值 | 实际填值？ |
|---|------|--------|------------|
| 1 | `short_grade` | `"C"` | ❌ 后端从没写 |
| 2 | `sector` | `"其他"` | ❌ classifier 没接 |
| 3 | `market_cap` | `0.0` | ❌ 没拉 |
| 4 | `consecutive_up_days` | `0` | ❌ 没拉 K 线 |
| 5 | `trend_strength` | `0.0` | ❌ |
| 6 | `high_24h` | `0.0` | ❌ 没拉 |
| 7 | `low_24h` | `0.0` | ❌ 没拉 |
| 8 | `atr` | `0.0` | ❌ |
| 9 | `recommended_leverage` | `5` | ❌ 永远 5 |
| 10 | `stop_loss_price` | `0.0` | ❌ |
| 11 | `take_profit_price` | `0.0` | ❌ |
| 12 | `oi_usd` | `0.0` | ❌ OI 是币数，要 * price |
| 13 | `funding_annualized` | `0.0` | ❌ funding*3*365 一行能算 |

modal 里"做空评级"永远显示 `C`、"板块"永远 `其他`、`连涨天数`永远 0 — **不是 bug，是功能未实现**。

### 2.4 前端 S/A/B/C/D 文案已就位

`ShortsView.vue:283-301` 有完整的评级颜色和文案：

```typescript
'S · 极佳做空机会' / 'A · 良好做空机会' / 'B · 中性观望'
'C · 风险偏高' / 'D · 不建议做空'
```

后端只缺一个 `short_grade` 字段的产出函数。

---

## 3. 四个 gap

### 3.1 拥挤度方向错位（最高优先级）

**症状**：对 BTC 24h +5% 涨、funding +0.01%、ls_ratio 2.0 的币：
- 当前 `crowdedness_score` = `(-0.01 * 100 + 2.0 - 1) / 2` 归一化后 = 0.0（**误判为不拥挤**）
- 实际信号：funding > 0 → longs pay shorts → **longs 极拥挤**，正是好做空时机

**影响**：
- `crowdedness_score` 字段语义错误，下游所有派生指标（squeeze_risk、short_risk_rating）都跟着错
- `_short_recommendation()` 文案基于错位方向 → 给的提示词正好相反

**修法**：方向翻转（修法 A）
- `crowdedness_score` → 重命名为 `long_crowdedness`，公式 `funding*0.6 + (ls_ratio - 1)*0.4` 归一化
- `squeeze_risk` → 重命名为 `long_squeeze_risk`（高 = longs 即将被轧）
- `rebound_potential` → 删除（涨幅榜上无意义），换 `extension_score`（涨幅到位度）
- `short_risk_rating` 阈值按新方向调
- `_short_recommendation()` 文案重写："extreme long crowd → HIGH CONFIDENCE SHORT"

### 3.2 13 字段空缺

modal 上 13 个字段全是兜底（见 §2.3）。**功能未实现 = 评级永远是 C、连涨永远是 0、市值永远是 0**。

### 3.3 4 项"做空基本面"数据全缺

用户确认的 4 个基本面维度：

| 项 | 数据源 | 用途 | 字段 |
|----|--------|------|------|
| **B. 板块** | CoinGecko `categories` + `sector_classifier.py` | 过滤"我不做空 Meme" | `sector` |
| **C. 解锁/通胀压力** | CoinGecko `fully_diluted_valuation` | FDV/MC > 5 = 砸盘压力大、做空胜率 +1 | `fdv_mcap_ratio` |
| **D. 筹码集中度** | Arkham `get_holder_concentration`（`arkham.py:152`） | top10 > **70%** 或 gini > 0.85 = 大户说了算、易被拉砸 | `top10_holders_pct`, `gini` |

**数据源现状**：
- `datasources/coingecko.py:56` 有 `get_top_market_cap()` 但 scanner 没用
- `datasources/arkham.py:152` 有 `get_holder_concentration(token_cg_id)` 但 scanner 没用
- `services/sector_classifier.py` 已存在但 scanner 没用

### 3.4 做空评级是空壳

modal 文案 (`S/A/B/C/D`) 就位但后端从不写。需新增 `_calculate_short_grade()` 函数。

---

## 4. 设计：在涨幅榜上叠加做空适配度

### 4.1 核心原则 — 不替换 heat_score

```
排序: heat_score DESC（涨幅榜，保留）
显示: 在每行/每行 modal 上叠加 short_opportunity 评级 + 4 项基本面
```

heat_score 维持"找热门"职责。新增的 `long_crowdedness` 和 `short_opportunity_score` 只作为**展示层信号**，不参与排序。

### 4.2 新增字段（汇总）

| 字段 | 类型 | 数据源 | 刷新频率 |
|------|------|--------|----------|
| `long_crowdedness` | float 0-1 | 公式 F1（见下） | 60s（scanner tick） |
| `long_squeeze_risk` | float 0-1 | `crowd*0.6 + drop_norm*0.4` | 60s |
| `extension_score` | float 0-1 | 公式 F2（见下） | 60s |
| `sector` | str | CoinGecko `categories` + `sector_classifier.py` 覆盖 | 6h 缓存 |
| `fdv_mcap_ratio` | float | CoinGecko `fully_diluted_valuation` | 6h 缓存 |
| `top10_holders_pct` | float 0-100 | Arkham `get_holder_concentration` | 6h 缓存 |
| `gini` | float 0-1 | 同上 | 6h 缓存 |
| `market_cap` | float | CoinGecko | 6h 缓存 |
| `consecutive_up_days` | int | OHLCV '1d' × 30 → 数绿 K | 每日 0:05 UTC（scanner tick 内 lazy 算） |
| `low_7d` | float | OHLCV '1d' × 7 | 每日 |
| `rebound_multiple` | float | `price / low_7d` | 每日 |
| `funding_annualized` | float % | `funding * 3 * 365` | 60s |
| `oi_usd` | float | `open_interest * price` | 60s |
| `short_grade` | "S"/"A"/"B"/"C"/"D" | §4.3 映射 | 60s |
| `short_opportunity_score` | float 0-1 | §4.4 公式 | 60s |

**F1 — `long_crowdedness` 公式：**
```python
funding_signal = max(min(token.funding_rate / 0.01, 1.0), 0.0)   # funding ∈ [-1%, +1%] → [0, 1]
ls_signal      = max(min((token.long_short_ratio - 1.0) / 1.0, 1.0), 0.0)  # ls ∈ [1, 2] → [0, 1]
long_crowdedness = funding_signal * 0.6 + ls_signal * 0.4  # ∈ [0, 1]
```

**F2 — `extension_score` 公式：**
```python
extension_score = max(min(token.price_change_24h / 10.0, 1.0), 0.0) if token.price_change_24h > 0 else 0.0
# +10% 涨幅 → 1.0；跌幅 → 0.0；中性 → 0.0
```

### 4.3 评级映射 S/A/B/C/D

| 评级 | 触发条件（**全部需要满足**） |
|------|------------------------------|
| **S** | `long_crowdedness ≥ 0.7` **且** `extension_score ≥ 0.6` **且** `market_cap ≥ 1B` **且** `top10_holders_pct ≤ 70` |
| **A** | `long_crowdedness ≥ 0.5` **且** `extension_score ≥ 0.4` **且** `market_cap ≥ 1B` |
| **B** | `(long_crowdedness ≥ 0.3` **或** `extension_score ≥ 0.3)` **且** `market_cap ≥ 100M` |
| **C** | `market_cap ≥ 100M` **且** `volume_usd ≥ 10M`（流动性 OK 但拥挤度/涨幅都不到 B 线） |
| **D** | `market_cap < 100M` **或** `volume_usd < 10M`（**不可执行**） |

**未填字段处理**：`market_cap == 0` 或 `top10_holders_pct == 0`（缓存未到）→ 视为不满足对应条件，**只可能评到 B/C/D**，不会冒到 S/A。

**top10 阈值统一**：D 风险提示、short_grade S 级、short_opportunity_score 分布公式都用 **70%** 作为高/低集中度的分界。
- `top10 ≤ 70%` → 集中度可接受
- `top10 > 70%` → 高集中度警示

### 4.4 short_opportunity_score 公式（仅展示，不进排序）

```python
def _short_opportunity_score(t: HotToken) -> float:
    # 1. 多头拥挤度（权重 0.35）— 主信号
    crowd = t.long_crowdedness

    # 2. 反弹到位度（权重 0.25）— 涨得越多越接近顶部
    ext = t.extension_score

    # 3. 流动性（权重 0.20）— 市值 + 成交；market_cap 未填时按 0 计
    liq = (min(t.market_cap / 1e9, 1.0) * 0.6
           + min(t.volume_usd / 100e6, 1.0) * 0.4)

    # 4. 筹码分散度（权重 0.20）— top10 越低越好
    #    top10 == 0 (未填) → 视为中性 0.5；top10 ≤ 30% → 1.0；top10 ≥ 70% → 0.0
    if t.top10_holders_pct <= 0:
        dist = 0.5
    else:
        dist = max(min((70 - t.top10_holders_pct) / 40, 1.0), 0.0)

    return crowd * 0.35 + ext * 0.25 + liq * 0.20 + dist * 0.20
```

`short_opportunity_score` 不进 `get_hot_tokens()` 排序，只在 modal 显示。**未填字段（=0）按中性处理，不直接判 0**，避免缓存窗口里分数被低估。

---

## 5. 数据获取与刷新策略

### 5.1 三档刷新频率

| 档位 | 周期 | 字段 |
|------|------|------|
| **热 (60s)** | scanner tick | funding, OI, LS ratio, volume, price, long_crowdedness, extension_score, short_grade, short_opportunity_score |
| **温 (6h)** | 定时任务或 lazy | market_cap, fdv_mcap_ratio, top10_holders_pct, gini, sector |
| **冷 (1d)** | scanner tick 内 lazy 算 | consecutive_up_days, low_7d, rebound_multiple, high_24h, low_24h, atr |

### 5.2 新增数据获取

| 来源 | 调用 | 频率 | 备注 |
|------|------|------|------|
| `coingecko.get_coins_markets(per_page=250)` | 1 次/6h | 6h | 取 `market_cap`, `fully_diluted_valuation`, `categories`，做 symbol → dict |
| `coingecko.search(query=symbol)` | lazy | 1 次/币 | 解析 symbol → `cg_id`（Arkham 需要） |
| `arkham.get_holder_concentration(cg_id)` | 1 次/(币·6h) | 6h | 50 币 × 1/6h ≈ 8 calls/h，限速 OK |
| `exchange.fetch_ohlcv(symbol, '1d', limit=30)` | 1 次/币/tick | 60s | 50 币 × 1/60s = 50 calls/min，Binance 限 1200 weight/min，OK |

### 5.3 配置依赖

- `arkham_api_key` 已在 `config_store` 里（`services/config_store.py`），需要检查是否已填
- `coingecko` 免费 tier 30 calls/min，缓存 6h 远低于限速

### 5.4 错误处理（fail-soft 原则）

所有外部数据获取**永不抛错到 scanner 主循环**。每个 fetch 独立 try/except + 缓存兜底：

| 来源 | 失败行为 |
|------|----------|
| CoinGecko `/coins/markets` | 保留上次缓存，log warn，字段保留 6h 旧值 |
| CoinGecko `search(symbol)` | symbol→cg_id 解析失败 → 跳过该币的 holder_concentration 拉取，top10=0（视为中性） |
| Arkham `get_holder_concentration` | 单币失败不影响其他币；返回 top10=0 |
| Binance `fetch_ohlcv` | 单币失败 → consecutive_up_days/low_7d/rebound_multiple 全部置 0（不阻塞其他币） |

**统一接口**：`FundamentalsCache.get(symbol) -> dict` — 任何字段缺失返回 None，前端按"未填"展示（"–" 灰字）。**绝不让缓存层异常冒泡到 scanner 循环**。

---

## 6. 落地路径（增量交付）

### Phase 1a — 修方向 + 评级 + modal 渲染（**2h，单独 PR**）

**目标**：方向修对、评级真算出来、前端 modal 显示新指标。**不引入新缓存层**，字段暂时还是 0。

| 改动 | 文件 | 工作量 |
|------|------|--------|
| `crowdedness_score` → `long_crowdedness`（公式 F1） | `hot_tokens_scanner.py:270-319` | 20 min |
| 删 `rebound_potential`，加 `extension_score`（公式 F2） | 同上 | 15 min |
| `squeeze_risk` → `long_squeeze_risk`（重命名） | 同上 | 5 min |
| `_calculate_short_grade()` 实现 §4.3 映射 | 同上 | 20 min |
| `_short_opportunity_score()` 实现 §4.4 公式 | 同上 | 15 min |
| scanner tick 内加 `oi_usd = oi * price` | `_fetch_and_update` | 5 min |
| scanner tick 内加 `funding_annualized = funding * 3 * 365` | 同上 | 5 min |
| `_short_recommendation()` 文案按新方向重写 | `api/hot_tokens.py` | 15 min |
| modal 新增渲染：long_crowdedness % / extension_score % / short_grade / oi_usd / funding_annualized | `ShortsView.vue` | 30 min |

**Phase 1a 验收**：modal 显示真实计算值；表里 short_grade 列亮 S/A/B/C/D 真实评级；不依赖缓存层。

### Phase 1b — 缓存层 + 字段填充（**2.5h，单独 PR**）

**目标**：4 项基本面（板块/FDV/筹码/市值）+ K 线指标全部填到 13 个空字段。

| 改动 | 文件 | 工作量 |
|------|------|--------|
| 新建 `services/fundamentals_cache.py`：6h 拉 CoinGecko `/coins/markets?per_page=250`，落 `{symbol: {market_cap, fdv, categories, cg_id}}` | 新文件 | 60 min |
| 同一 cache 配 Arkham 6h 拉取 `get_holder_concentration(cg_id)`，落 `{symbol: {top10_pct, gini}}` | 同上 | 60 min |
| scanner tick 末尾调 `fundamentals_cache.get(symbol)`，把字段写到 token | `hot_tokens_scanner.py` | 20 min |
| `sector_classifier.classify(symbol)` 集成：用 CoinGecko categories + classifier 兜底 | 同上 | 20 min |
| `get_token_analysis` 加 OHLCV：返回 `consecutive_up_days` / `low_7d` / `rebound_multiple` / `high_24h` / `low_24h` / `atr` | `api/hot_tokens.py` | 45 min |
| `_token_to_dict` 去掉对所有 13 字段的 `getattr` 兜底 | `api/hot_tokens.py` | 5 min |
| modal 新增渲染：板块、FDV/MC、top10%、gini、连涨天数、低7日、倍数 | `ShortsView.vue` | 30 min |

**Phase 1b 验收**：13 个字段全有真实值；S/A/B/C/D 评级由 4 维度综合判定；D 不可执行币被标识。

### Phase 2 — 表头 chip 过滤（**2.5h，单独 PR**）

| 改动 | 文件 | 工作量 |
|------|------|--------|
| 资金费率 chip：**空头付费(fr<-0.001) / 极度拥挤(fr<-0.005) / 多头付费(fr>0.001) / 中性(其他)** | `ShortsView.vue` | 30 min |
| 24h 涨跌 chip：**大跌(<-10%) / 跌(-10%~-3%) / 中性(-3%~3%) / 涨(3%~10%) / 大涨(>10%)** | 同上 | 30 min |
| 评级 chip（S/A/B/C/D 单选 = 仅看该评级） | 同上 | 20 min |
| 板块 chip（按 CoinGecko categories 动态生成） | 同上 | 30 min |
| 搜索框（symbol 模糊匹配） | 同上 | 15 min |
| `applyHotTokenFilters(tokens, filters)` 纯函数 + vitest | `utils/` + `__tests__/` | 45 min |

**Phase 2 验收**：表头 chip 可叠加筛选；空筛选 = 原样；显示 N/50 计数。

### Phase 3 — （可选）sector classifier 增强

`sector_classifier.py` 已存在但映射覆盖可能不全。Phase 3 单独审视。

---

## 7. 不做的事（YAGNI）

- ❌ **不替换 heat_score 排序** — 涨幅榜定位正确
- ❌ **不引入新表**（`daily_klines` / `short_pool`）— 内存 + 6h 缓存够
- ❌ **不做 daily cron** — scanner tick 内 lazy 算就行
- ❌ **不重构 ShortSellingEngine** — 那条路径是 `/api/analyze/short` 8 维度 LLM 分析，跟 scanner 榜无关
- ❌ **不做"全 250 币扫描"** — 50 币池够覆盖做空候选
- ❌ **不加新依赖**（pandas-ta / ta-lib）— `consecutive_up_days` 一行 Python 算
- ❌ **不做 daily K 线历史查询 UI** — modal 里给当前/7d 数据就够

---

## 8. 风险与权衡

| 风险 | 缓解 |
|------|------|
| Arkham API 限速 | 6h 缓存 + 50 币池 ≤ 8 calls/h，远低于免费 tier 限速 |
| CoinGecko 30 calls/min | 1 次/6h 拉满 250 币，远低于限速 |
| `consecutive_up_days` 用 1d K 线有时区歧义 | 文档注明 UTC 0:00 切日 |
| 字段重命名（`crowdedness_score` → `long_crowdedness` 等） | **非 breaking change** — 这 3 个字段没在任何外部 API 文档 contract 里，前端没直接读；一次 PR 改完即可 |
| Arkham `get_holder_concentration` 需要 `cg_id`（不是 symbol） | `coingecko.search()` 做 symbol→cg_id 缓存，存进 fundamentals_cache |
| 缓存未到时（=0）字段全空 | §4.3 明确"未填视为不满足"，评分降级；§4.4 公式用 0.5 中性分兜底 |

---

## 9. 行动建议

**Phase 1a（2 小时，单独 PR）** → 修方向 + 评级真算 + modal 渲染热字段  
**Phase 1b（2.5 小时，单独 PR）** → 缓存层 + 13 字段全填 + modal 渲染基本面  
**Phase 2（2.5 小时，单独 PR）** → 表头 chip 过滤 + 搜索  
**Phase 3（待定）** → sector 增强

不发版前可在本地用 `?_grade=S` query param 试看 S 级列表。

---

## 10. 测试计划

### 10.1 单元测试（pytest）

| 函数 | 文件 | 覆盖用例 |
|------|------|----------|
| `_long_crowdedness(token)` | `test_hot_tokens_scanner.py` | funding=0/0.005/0.01/负值；ls=1/1.5/2.0；组合边界 |
| `_extension_score(token)` | 同上 | change=-5%/0/+5%/+20% 边界 |
| `_calculate_short_grade(token)` | 同上 | S/A/B/C/D 5 个分支；market_cap=0 降级；top10=0 降级 |
| `_short_opportunity_score(token)` | 同上 | 公式权重验证；market_cap=0 中性；top10=0 中性 |
| `applyHotTokenFilters(tokens, filters)` | Phase 2 新文件 | 空过滤、单个 chip、多 chip AND、搜索大小写 |
| `FundamentalsCache.get(symbol)` | Phase 1b 新文件 | 缓存命中、未命中、refresh、fail-soft |

### 10.2 集成测试

| 场景 | 验证 |
|------|------|
| `GET /api/hot_tokens/?limit=5` | 返回字段 13 个全有真值（即使 0 也要在响应里） |
| `GET /api/hot_tokens/BTCUSDT/analysis` | 返回 OHLCV 派生字段 |
| scanner tick 一次（含 mock CoinGecko / Arkham） | 不抛异常；缓存 miss 时不阻塞；fail-soft 生效 |

### 10.3 端到端（手动）

| 场景 | 期望 |
|------|------|
| 打开 `/analysis` | 涨幅榜正常，short_grade 列有 S/A/B/C/D |
| 点 D 级 chip | 仅显示 D 评级 |
| 点 S 级 chip | 仅显示 S 评级，且 short_grade 都标 S |
| 切到 D 级再切回"全部" | 恢复原样 |
