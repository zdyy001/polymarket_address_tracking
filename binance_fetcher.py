"""
Binance K线数据获取 + Polymarket交易数据合并
1. 读取Polymarket数据（事件时间范围 + 交易记录）
2. 获取该时间范围的Binance秒级K线
3. 把交易数据join到K线上
"""
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

import requests
import yaml

UTC8 = timezone(timedelta(hours=8))


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_polymarket_data(json_path: str) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_klines_1s(symbol: str, start_ts: int, end_ts: int) -> list:
    """
    获取秒级K线数据
    Binance 1s K线每次最多返回1000条
    """
    all_klines = []
    url = "https://api.binance.com/api/v3/klines"

    current_start = start_ts * 1000  # 转毫秒

    print(f"获取 {symbol} 秒级K线...")

    while current_start < end_ts * 1000:
        params = {
            "symbol": symbol,
            "interval": "1s",
            "startTime": current_start,
            "endTime": end_ts * 1000,
            "limit": 1000
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            print(f"请求失败: {response.status_code}")
            break

        klines = response.json()
        if not klines:
            break

        all_klines.extend(klines)
        print(f"  已获取 {len(all_klines)} 条K线...")

        # 下一批从最后一条之后开始
        last_open_time = klines[-1][0]
        current_start = last_open_time + 1000  # +1秒

        if len(klines) < 1000:
            break

    print(f"  共获取 {len(all_klines)} 条K线")
    return all_klines


def timestamp_to_utc8(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=UTC8)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    print("=" * 60)
    print("Binance K线获取 + 数据合并")
    print("=" * 60)

    config = load_config()
    slug = config["slug"]
    symbol = config.get("price_symbol", "BTCUSDT")
    output_dir = config.get("output_dir", "./output")

    # 1. 读取Polymarket数据
    pm_file = Path(output_dir) / f"polymarket_{slug}.json"
    if not pm_file.exists():
        print(f"错误: 找不到 {pm_file}")
        print("请先运行 polymarket_fetcher.py")
        return

    print(f"读取: {pm_file}")
    pm_data = load_polymarket_data(str(pm_file))

    event = pm_data["event"]
    trades = pm_data["trades"]
    start_ts = event["start_ts"]
    end_ts = event["end_ts"]

    print(f"事件: {event['title']}")
    print(f"时间范围: {timestamp_to_utc8(start_ts)} ~ {timestamp_to_utc8(end_ts)}")
    print(f"交易记录: {len(trades)} 条")

    # 2. 获取Binance秒级K线
    klines = fetch_klines_1s(symbol, start_ts, end_ts)

    if not klines:
        print("没有获取到K线数据")
        return

    # 3. 构建K线字典 (时间戳秒 -> 价格)
    # K线格式: [开盘时间ms, 开, 高, 低, 收, 成交量, ...]
    kline_dict = {}
    for k in klines:
        ts_sec = k[0] // 1000
        kline_dict[ts_sec] = {
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }

    # 4. 构建交易字典 (时间戳秒 -> 交易列表)
    trades_by_ts = defaultdict(list)
    for t in trades:
        ts = t.get("timestamp")
        if ts:
            trades_by_ts[int(ts)].append(t)

    # 5. 合并数据，生成CSV
    rows = []
    base_price = None  # 0秒的BTC价格，用于计算delta
    cum_up_size = 0.0  # 累计up持仓量
    cum_up_cost = 0.0  # 累计up持仓成本
    cum_down_size = 0.0  # 累计down持仓量
    cum_down_cost = 0.0  # 累计down持仓成本

    for ts in range(start_ts, end_ts + 1):
        kline = kline_dict.get(ts, {})
        ts_trades = trades_by_ts.get(ts, [])

        # 获取当前BTC价格
        btc_close = kline.get("close", "")

        # 记录基准价格（第一秒的价格）
        if base_price is None and btc_close:
            base_price = btc_close

        # 计算相对变化
        btc_delta = ""
        if base_price and btc_close:
            btc_delta = round(btc_close - base_price, 2)

        # 如果这一秒有多笔交易，汇总
        buy_up_size = sum(float(t.get("size", 0)) for t in ts_trades
                         if t.get("side") == "BUY" and t.get("outcome") == "Up")
        buy_down_size = sum(float(t.get("size", 0)) for t in ts_trades
                           if t.get("side") == "BUY" and t.get("outcome") == "Down")

        # 获取交易价格（如果有多笔，取平均）
        buy_up_prices = [float(t.get("price", 0)) for t in ts_trades
                        if t.get("side") == "BUY" and t.get("outcome") == "Up"]
        buy_down_prices = [float(t.get("price", 0)) for t in ts_trades
                          if t.get("side") == "BUY" and t.get("outcome") == "Down"]

        # 更新累计持仓
        if buy_up_size > 0:
            avg_price = sum(buy_up_prices) / len(buy_up_prices)
            cum_up_cost += buy_up_size * avg_price
            cum_up_size += buy_up_size

        if buy_down_size > 0:
            avg_price = sum(buy_down_prices) / len(buy_down_prices)
            cum_down_cost += buy_down_size * avg_price
            cum_down_size += buy_down_size

        # 计算累计平均成本
        cum_up_avg_cost = round(cum_up_cost / cum_up_size, 4) if cum_up_size > 0 else ""
        cum_down_avg_cost = round(cum_down_cost / cum_down_size, 4) if cum_down_size > 0 else ""

        # 计算target和cash_out相关字段
        target_shares = ""
        target_price = ""
        cash_out_shares = ""
        cash_out_price = ""

        if cum_up_size > 0 or cum_down_size > 0:
            target_shares = cum_down_size - cum_up_size
            if target_shares < 0:
                target_price = round(1 - cum_up_avg_cost, 4) if cum_up_avg_cost else ""
            else:
                target_price = round(1 - cum_down_avg_cost, 4) if cum_down_avg_cost else ""
            cash_out_shares = min(cum_up_size, cum_down_size)
            if cum_up_avg_cost and cum_down_avg_cost:
                cash_out_price = round(cum_up_avg_cost + cum_down_avg_cost, 4)

        # 计算hidden_lost和hidden_profit
        hidden_lost = ""
        hidden_profit = ""
        if target_shares != "" and target_price != "":
            hidden_lost = round(-abs(target_shares) * (1 - target_price), 4)
        if cash_out_shares != "" and cash_out_price != "":
            hidden_profit = round(cash_out_shares * (1 - cash_out_price), 4)

        row = {
            "timestamp": ts,
            "time_utc8": timestamp_to_utc8(ts),
            f"{symbol.lower()}_close": btc_close,
            "btc_delta": btc_delta,
            "buy_up_size": buy_up_size if buy_up_size else "",
            "buy_up_price": sum(buy_up_prices) / len(buy_up_prices) if buy_up_prices else "",
            "buy_down_size": buy_down_size if buy_down_size else "",
            "buy_down_price": sum(buy_down_prices) / len(buy_down_prices) if buy_down_prices else "",
            "cum_up_size": cum_up_size if cum_up_size else "",
            "cum_up_avg_cost": cum_up_avg_cost,
            "cum_down_size": cum_down_size if cum_down_size else "",
            "cum_down_avg_cost": cum_down_avg_cost,
            "target_shares": target_shares,
            "target_price": target_price,
            "cash_out_shares": cash_out_shares,
            "cash_out_price": cash_out_price,
            "hidden_lost": hidden_lost,
            "hidden_profit": hidden_profit,
            "trade_count": len(ts_trades) if ts_trades else "",
        }
        rows.append(row)

    # 6. 保存CSV
    output_file = Path(output_dir) / f"merged_{slug}.csv"

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        f.write(f"# Event: {event['title']}\n")
        f.write(f"# Slug: {slug}\n")
        f.write(f"# Address: {pm_data['address']}\n")
        f.write(f"# Time Range: {timestamp_to_utc8(start_ts)} ~ {timestamp_to_utc8(end_ts)}\n")
        f.write(f"# Price Symbol: {symbol}\n")
        f.write(f"# Total Trades: {len(trades)}\n")
        f.write("#\n")

        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n已保存: {output_file}")

    # 统计
    trades_seconds = sum(1 for r in rows if r["trade_count"])
    print(f"\n统计:")
    print(f"  总秒数: {len(rows)}")
    print(f"  有交易的秒数: {trades_seconds}")
    print(f"  总交易笔数: {len(trades)}")

    # 显示示例
    print(f"\n有交易的时刻示例:")
    shown = 0
    for r in rows:
        if r["trade_count"] and shown < 5:
            print(f"  {r['time_utc8']} | {symbol}: {r[f'{symbol.lower()}_close']} | "
                  f"Buy Up: {r['buy_up_size']} | Buy Down: {r['buy_down_size']}")
            shown += 1

    print("\n完成!")


if __name__ == "__main__":
    main()
