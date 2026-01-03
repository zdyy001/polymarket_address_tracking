# Polymarket Address Tracking

用于跟踪和分析 Polymarket 预测市场中特定钱包地址的交易行为，并结合 Binance 秒级K线数据进行策略分析。

## 项目结构

```
address_tracking/
├── config.yaml           # 配置文件
├── run.py                # 统一启动脚本
├── polymarket_fetcher.py # 获取 Polymarket 交易数据
├── binance_fetcher.py    # 获取 Binance K线并合并数据
├── analyze_strategy.py   # 策略分析脚本
├── event list            # 事件列表（可选，用于批量处理）
├── output/               # 输出目录
└── venv/                 # Python 虚拟环境
```

## 使用方法

### 1. 环境准备

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖（如果尚未安装）
pip install -r requirements.txt
```

### 2. 配置 config.yaml

编辑 `config.yaml` 文件：

```yaml
# 目标钱包地址
address: "0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d"

# 事件 slug
slug: "btc-updown-15m-1767358800"

# Binance 永续合约交易对
price_symbol: "BTCUSDC"

# 输出目录
output_dir: "./output"
```

### 3. 运行

运行统一启动脚本，会依次执行三个步骤：

```bash
python3 run.py
```

或者分步执行：

```bash
# 步骤1: 获取 Polymarket 交易数据
python3 polymarket_fetcher.py

# 步骤2: 获取 Binance K线并合并数据
python3 binance_fetcher.py

# 步骤3: 策略分析
python3 analyze_strategy.py
```

### 4. 输出文件

- `output/polymarket_{slug}.json` - Polymarket 原始交易数据
- `output/merged_{slug}.csv` - 合并后的秒级数据（含K线和交易）

## 如何获取 Slug

Slug 可以直接从 Polymarket 网站的 URL 中获取。

**URL 格式：**
```
https://polymarket.com/event/{slug}
```

**示例：**
- URL: `https://polymarket.com/event/btc-updown-15m-1767358800`
- Slug: `btc-updown-15m-1767358800`

**Slug 命名规则（以 BTC 15分钟预测为例）：**
- `btc-updown-15m-{timestamp}`
- timestamp 是事件开始时间的 Unix 时间戳

## CSV 输出列说明

输出的 CSV 文件包含秒级时间序列数据，每一列含义如下：

### 基础列

| 列名 | 含义 | 说明 |
|------|------|------|
| `timestamp` | Unix 时间戳 | 秒级精度 |
| `time_utc8` | UTC+8 时间 | 格式: YYYY-MM-DD HH:MM:SS |
| `btcusdc_close` | BTC 收盘价 | 该秒的 Binance BTCUSDC 收盘价 |
| `btc_delta` | 价格变化 | 相对于事件开始时价格的变化（美元） |

### 当前秒交易列

| 列名 | 含义 | 计算逻辑 |
|------|------|----------|
| `buy_up_size` | 买入 Up 份额 | 该秒内所有买入 Up 的交易量之和 |
| `buy_up_price` | 买入 Up 价格 | 该秒内所有买入 Up 交易的平均价格 |
| `buy_down_size` | 买入 Down 份额 | 该秒内所有买入 Down 的交易量之和 |
| `buy_down_price` | 买入 Down 价格 | 该秒内所有买入 Down 交易的平均价格 |

### 累计持仓列

| 列名 | 含义 | 计算逻辑 |
|------|------|----------|
| `cum_up_size` | 累计 Up 持仓 | 从事件开始到当前秒的 Up 总买入量 |
| `cum_up_avg_cost` | Up 平均成本 | `累计 Up 总成本 / 累计 Up 持仓量` |
| `cum_down_size` | 累计 Down 持仓 | 从事件开始到当前秒的 Down 总买入量 |
| `cum_down_avg_cost` | Down 平均成本 | `累计 Down 总成本 / 累计 Down 持仓量` |

### 计算列（策略指标）

| 列名 | 含义 | 计算逻辑 |
|------|------|----------|
| `target_shares` | 目标份额差 | `cum_down_size - cum_up_size`<br>正值表示偏空（Down 多于 Up），负值表示偏多（Up 多于 Down） |
| `target_price` | 目标价格 | 如果 `target_shares < 0`（偏多）: `1 - cum_up_avg_cost`<br>如果 `target_shares >= 0`（偏空）: `1 - cum_down_avg_cost`<br>表示持仓较多一方的盈亏平衡价格 |
| `cash_out_shares` | 对冲份额 | `min(cum_up_size, cum_down_size)`<br>已完成对冲的份额数量 |
| `cash_out_price` | 对冲成本 | `cum_up_avg_cost + cum_down_avg_cost`<br>完全对冲一对 Up+Down 的总成本 |

### 统计列

| 列名 | 含义 | 说明 |
|------|------|------|
| `trade_count` | 交易笔数 | 该秒内的交易次数 |

## 计算逻辑详解

### 价格变化 (btc_delta)
```
btc_delta = 当前秒收盘价 - 事件第一秒收盘价
```

### 累计平均成本
```
cum_up_avg_cost = Σ(buy_up_size × buy_up_price) / Σ(buy_up_size)
cum_down_avg_cost = Σ(buy_down_size × buy_down_price) / Σ(buy_down_size)
```

### 策略指标说明

**target_shares（目标份额差）：**
- 表示 Down 和 Up 持仓的差额
- 负值：Up 持仓更多，交易者看涨
- 正值：Down 持仓更多，交易者看跌
- 零值：完全对冲

**target_price（目标价格）：**
- 表示主要持仓方向的盈亏平衡价格
- 预测市场中，正确结果的份额最终价值为 $1
- 如果买入价格为 0.6，则 target_price = 1 - 0.6 = 0.4
- 这意味着需要价格涨到 0.6 以上才能在该方向上盈利

**cash_out_shares（对冲份额）：**
- 已完成配对的 Up + Down 组合数量
- 这部分持仓无论结果如何都能保证获得 $1（每对）

**cash_out_price（对冲成本）：**
- 买入一对 Up + Down 的总成本
- 如果 cash_out_price < 1，对冲交易有利可图
- 利润 = 1 - cash_out_price（每对）

## 示例分析

假设某时刻的持仓状态：
- `cum_up_size = 100`，`cum_up_avg_cost = 0.55`
- `cum_down_size = 60`，`cum_down_avg_cost = 0.40`

计算结果：
- `target_shares = 60 - 100 = -40`（偏多，Up 多 40 份）
- `target_price = 1 - 0.55 = 0.45`（Up 需要涨到 0.55 以上才盈利）
- `cash_out_shares = min(100, 60) = 60`（已配对 60 组）
- `cash_out_price = 0.55 + 0.40 = 0.95`（每对成本 $0.95，利润 $0.05）
