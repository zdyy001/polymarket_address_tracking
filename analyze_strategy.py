"""
交易策略分析脚本
分析地址在事件中的交易行为与价格的关系
"""
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

UTC8 = timezone(timedelta(hours=8))


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_polymarket_data(json_path: str) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_merged_csv(csv_path: str) -> list:
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        # Skip comment lines
        lines = [line for line in f if not line.startswith("#")]

    reader = csv.DictReader(lines)
    for row in reader:
        rows.append(row)
    return rows


def analyze_event(pm_data: dict, merged_rows: list, symbol: str):
    """分析单个事件的交易策略"""
    event = pm_data["event"]
    trades = pm_data["trades"]

    print("=" * 70)
    print(f"事件: {event['title']}")
    print("=" * 70)

    # 1. 价格变化分析
    prices = [float(r[f"{symbol.lower()}_close"]) for r in merged_rows if r[f"{symbol.lower()}_close"]]
    start_price = prices[0]
    end_price = prices[-1]
    price_change = end_price - start_price
    price_pct = (price_change / start_price) * 100

    print(f"\n【价格变化】")
    print(f"  开盘价: ${start_price:,.2f}")
    print(f"  收盘价: ${end_price:,.2f}")
    print(f"  变化: ${price_change:+,.2f} ({price_pct:+.4f}%)")
    print(f"  结果: {'Up ↑' if price_change > 0 else 'Down ↓' if price_change < 0 else '持平'}")

    actual_outcome = "Up" if price_change > 0 else "Down"

    # 2. 交易统计
    buy_up_total = sum(float(t.get("size", 0)) for t in trades
                       if t.get("side") == "BUY" and t.get("outcome") == "Up")
    buy_down_total = sum(float(t.get("size", 0)) for t in trades
                         if t.get("side") == "BUY" and t.get("outcome") == "Down")

    buy_up_cost = sum(float(t.get("size", 0)) * float(t.get("price", 0)) for t in trades
                      if t.get("side") == "BUY" and t.get("outcome") == "Up")
    buy_down_cost = sum(float(t.get("size", 0)) * float(t.get("price", 0)) for t in trades
                        if t.get("side") == "BUY" and t.get("outcome") == "Down")

    print(f"\n【交易统计】")
    print(f"  买入 Up:   {buy_up_total:,.2f} shares, 成本 ${buy_up_cost:,.2f}")
    print(f"  买入 Down: {buy_down_total:,.2f} shares, 成本 ${buy_down_cost:,.2f}")
    print(f"  总成本: ${buy_up_cost + buy_down_cost:,.2f}")

    # 3. 盈亏计算
    # 如果结果是 Up，Up shares 价值 $1，Down shares 价值 $0
    # 如果结果是 Down，Down shares 价值 $1，Up shares 价值 $0
    if actual_outcome == "Up":
        payout = buy_up_total * 1.0  # Up wins
        profit = payout - (buy_up_cost + buy_down_cost)
    else:
        payout = buy_down_total * 1.0  # Down wins
        profit = payout - (buy_up_cost + buy_down_cost)

    print(f"\n【盈亏分析】")
    print(f"  实际结果: {actual_outcome}")
    print(f"  派彩金额: ${payout:,.2f}")
    print(f"  净盈亏: ${profit:+,.2f}")

    roi = (profit / (buy_up_cost + buy_down_cost)) * 100 if (buy_up_cost + buy_down_cost) > 0 else 0
    print(f"  投资回报率: {roi:+.2f}%")

    # 4. 交易时机分析
    print(f"\n【交易时机分析】")

    # 按时间排序交易
    sorted_trades = sorted(trades, key=lambda t: t.get("timestamp", 0))

    # 分析入场时机
    if sorted_trades:
        first_trade_ts = sorted_trades[0].get("timestamp")
        last_trade_ts = sorted_trades[-1].get("timestamp")
        event_start = event["start_ts"]
        event_end = event["end_ts"]

        entry_delay = first_trade_ts - event_start
        exit_before = event_end - last_trade_ts

        print(f"  首笔交易: 事件开始后 {entry_delay} 秒")
        print(f"  末笔交易: 事件结束前 {exit_before} 秒")

        # 找出首笔交易时的价格
        first_price = None
        for r in merged_rows:
            if int(r["timestamp"]) == first_trade_ts:
                first_price = float(r[f"{symbol.lower()}_close"])
                break

        if first_price:
            price_at_entry = first_price - start_price
            print(f"  入场时价格变化: ${price_at_entry:+,.2f} (相对开盘)")

    # 5. 交易密集度分析
    trade_seconds = set(t.get("timestamp") for t in trades)
    total_seconds = event["end_ts"] - event["start_ts"]

    print(f"\n【交易密集度】")
    print(f"  有交易的秒数: {len(trade_seconds)} / {total_seconds}")
    print(f"  交易密集度: {len(trade_seconds) / total_seconds * 100:.2f}%")

    # 6. 仓位倾向
    print(f"\n【仓位倾向】")
    total_position = buy_up_total + buy_down_total
    if total_position > 0:
        up_pct = buy_up_total / total_position * 100
        down_pct = buy_down_total / total_position * 100
        print(f"  Up 仓位占比: {up_pct:.1f}%")
        print(f"  Down 仓位占比: {down_pct:.1f}%")

        bias = "偏多 (看涨)" if up_pct > 60 else "偏空 (看跌)" if down_pct > 60 else "中性"
        print(f"  判断: {bias}")

        # 判断是否押对方向
        correct = (up_pct > 50 and actual_outcome == "Up") or (down_pct > 50 and actual_outcome == "Down")
        print(f"  方向正确: {'✓ 是' if correct else '✗ 否'}")

    return {
        "event_title": event["title"],
        "actual_outcome": actual_outcome,
        "price_change": price_change,
        "buy_up_total": buy_up_total,
        "buy_down_total": buy_down_total,
        "profit": profit,
        "roi": roi,
    }


def main():
    print("=" * 70)
    print("Polymarket 交易策略分析")
    print("=" * 70)

    config = load_config()
    slug = config["slug"]
    symbol = config.get("price_symbol", "BTCUSDT")
    output_dir = config.get("output_dir", "./output")

    # 加载数据
    pm_file = Path(output_dir) / f"polymarket_{slug}.json"
    merged_file = Path(output_dir) / f"merged_{slug}.csv"

    if not pm_file.exists() or not merged_file.exists():
        print(f"错误: 数据文件不存在")
        print(f"请先运行 polymarket_fetcher.py 和 binance_fetcher.py")
        return

    pm_data = load_polymarket_data(str(pm_file))
    merged_rows = load_merged_csv(str(merged_file))

    result = analyze_event(pm_data, merged_rows, symbol)

    print("\n" + "=" * 70)
    print("分析完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
