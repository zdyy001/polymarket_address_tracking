"""
Polymarket 交易数据获取脚本
获取事件信息和指定地址的交易记录
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict

import requests
import yaml

UTC8 = timezone(timedelta(hours=8))


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_event_info(slug: str) -> dict:
    """获取事件信息"""
    url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        return response.json()
    raise Exception(f"获取事件失败: {response.status_code}")


def fetch_trades(address: str, condition_id: str) -> List[Dict]:
    """获取指定地址的所有交易"""
    all_trades = []
    offset = 0

    while True:
        response = requests.get(
            "https://data-api.polymarket.com/trades",
            params={
                "user": address,
                "market": condition_id,
                "limit": 100,
                "offset": offset
            },
            timeout=30
        )

        if response.status_code != 200:
            break

        trades = response.json()
        if not trades:
            break

        all_trades.extend(trades)
        print(f"  已获取 {len(all_trades)} 条交易...")

        if len(trades) < 100:
            break
        offset += 100

    return all_trades


def parse_event_time(time_str: str) -> int:
    """解析事件时间字符串为Unix时间戳"""
    # 格式: 2025-12-28T11:15:00Z
    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    return int(dt.timestamp())


def timestamp_to_utc8(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=UTC8)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    print("=" * 60)
    print("Polymarket 数据获取")
    print("=" * 60)

    config = load_config()
    address = config["address"]
    slug = config["slug"]
    output_dir = config.get("output_dir", "./output")

    print(f"地址: {address}")
    print(f"事件: {slug}")

    # 1. 获取事件信息
    print("\n获取事件信息...")
    event = fetch_event_info(slug)
    print(f"标题: {event.get('title')}")

    start_time_str = event.get("startTime") or event.get("startDate")
    end_time_str = event.get("endDate")

    start_ts = parse_event_time(start_time_str)
    end_ts = parse_event_time(end_time_str)

    print(f"事件时间 (UTC): {start_time_str} ~ {end_time_str}")
    print(f"事件时间 (UTC+8): {timestamp_to_utc8(start_ts)} ~ {timestamp_to_utc8(end_ts)}")
    print(f"时间戳: {start_ts} ~ {end_ts} (共 {end_ts - start_ts} 秒)")

    # 获取 conditionId
    markets = event.get("markets", [])
    if not markets:
        print("没有市场数据")
        return

    condition_id = markets[0].get("conditionId")
    print(f"ConditionId: {condition_id}")

    # 2. 获取交易数据
    print("\n获取交易数据...")
    trades = fetch_trades(address, condition_id)
    print(f"总交易数: {len(trades)}")

    # 统计
    if trades:
        buy_up = sum(1 for t in trades if t.get("side") == "BUY" and t.get("outcome") == "Up")
        buy_down = sum(1 for t in trades if t.get("side") == "BUY" and t.get("outcome") == "Down")
        sell_up = sum(1 for t in trades if t.get("side") == "SELL" and t.get("outcome") == "Up")
        sell_down = sum(1 for t in trades if t.get("side") == "SELL" and t.get("outcome") == "Down")
        print(f"  买 Up: {buy_up}, 买 Down: {buy_down}")
        print(f"  卖 Up: {sell_up}, 卖 Down: {sell_down}")

    # 3. 保存数据
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_file = Path(output_dir) / f"polymarket_{slug}.json"

    data = {
        "event": {
            "title": event.get("title"),
            "slug": slug,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "condition_id": condition_id,
        },
        "address": address,
        "trades": trades,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n已保存: {output_file}")
    print(f"\n下一步请运行 binance_fetcher.py 获取K线数据并合并")


if __name__ == "__main__":
    main()
