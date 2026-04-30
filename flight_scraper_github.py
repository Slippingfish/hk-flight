#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机票价格监控程序（GitHub Actions版）
=====================================
航线：北京首都(PEK) → 纽约肯尼迪(JFK)
日期：2026年07月01日（单程，经济舱）
平台：Google Flights（通过 SerpAPI 接口）

每次运行只执行一次抓取并追加到 flight_prices.csv。
由 GitHub Actions 每小时触发，共12次。

SerpAPI 免费账号：https://serpapi.com（每月100次免费）
将你的 API Key 存入 GitHub Secrets，名称为 SERPAPI_KEY
"""

import os
import csv
import json
import requests
from datetime import datetime

# ── 配置 ──────────────────────────────────────────
ORIGIN      = "PEK"           # 出发：北京首都
DEST        = "JFK"           # 到达：纽约肯尼迪
FLIGHT_DATE = "2026-07-01"    # 出发日期
OUTPUT_CSV  = "flight_prices.csv"
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")   # 从环境变量读取
# ──────────────────────────────────────────────────

FIELDNAMES = [
    "抓取时间", "第几次", "航线", "出发日期",
    "航空公司", "出发时间", "到达时间", "飞行时长_分钟",
    "中转次数", "价格_USD", "本次最低价_USD"
]


def fetch_flights():
    """调用 SerpAPI Google Flights 接口获取航班数据"""
    if not SERPAPI_KEY:
        raise ValueError("未设置 SERPAPI_KEY 环境变量")

    params = {
        "engine":         "google_flights",
        "departure_id":   ORIGIN,
        "arrival_id":     DEST,
        "outbound_date":  FLIGHT_DATE,
        "currency":       "USD",
        "hl":             "en",
        "type":           "2",       # 2 = 单程
        "api_key":        SERPAPI_KEY,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_flights(data):
    """解析 SerpAPI 返回的航班列表"""
    results = []
    for section in ("best_flights", "other_flights"):
        for item in data.get(section, []):
            flights = item.get("flights", [])
            if not flights:
                continue
            first = flights[0]
            last  = flights[-1]
            price = item.get("price")
            if not price:
                continue
            stops = len(flights) - 1
            results.append({
                "航空公司":   first.get("airline", "—"),
                "出发时间":   first.get("departure_airport", {}).get("time", "—"),
                "到达时间":   last.get("arrival_airport", {}).get("time", "—"),
                "飞行时长_分钟": item.get("total_duration", 0),
                "中转次数":   stops,
                "价格_USD":   price,
            })
    return results


def get_run_count():
    """从已有 CSV 推断本次是第几次运行"""
    if not os.path.exists(OUTPUT_CSV):
        return 1
    with open(OUTPUT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 1
    seen = set()
    for r in rows:
        seen.add(r.get("第几次", ""))
    return len(seen) + 1


def save_csv(records):
    write_header = not os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for r in records:
            writer.writerow(r)
    print(f"写入 {len(records)} 条 → {OUTPUT_CSV}")


def main():
    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_count = get_run_count()

    print(f"[{now_str}] 第 {run_count}/12 次抓取  {ORIGIN}→{DEST}  {FLIGHT_DATE}")

    try:
        data    = fetch_flights()
        flights = parse_flights(data)
    except Exception as e:
        print(f"抓取失败：{e}")
        # 写入一条占位记录，保证第几次字段连续
        save_csv([{
            "抓取时间": now_str, "第几次": run_count,
            "航线": f"{ORIGIN}→{DEST}", "出发日期": FLIGHT_DATE,
            "航空公司": "ERROR", "出发时间": "—", "到达时间": "—",
            "飞行时长_分钟": 0, "中转次数": 0,
            "价格_USD": None, "本次最低价_USD": None,
        }])
        return

    if not flights:
        print("本次未解析到航班数据")
        save_csv([{
            "抓取时间": now_str, "第几次": run_count,
            "航线": f"{ORIGIN}→{DEST}", "出发日期": FLIGHT_DATE,
            "航空公司": "无数据", "出发时间": "—", "到达时间": "—",
            "飞行时长_分钟": 0, "中转次数": 0,
            "价格_USD": None, "本次最低价_USD": None,
        }])
        return

    min_price = min(f["价格_USD"] for f in flights)
    print(f"获取 {len(flights)} 条航班，最低价：${min_price}")

    records = []
    for f in flights:
        records.append({
            "抓取时间":       now_str,
            "第几次":         run_count,
            "航线":           f"{ORIGIN}→{DEST}",
            "出发日期":       FLIGHT_DATE,
            "航空公司":       f["航空公司"],
            "出发时间":       f["出发时间"],
            "到达时间":       f["到达时间"],
            "飞行时长_分钟":   f["飞行时长_分钟"],
            "中转次数":       f["中转次数"],
            "价格_USD":       f["价格_USD"],
            "本次最低价_USD":  min_price,
        })
    save_csv(records)

    # 打印价格变化摘要
    if os.path.exists(OUTPUT_CSV) and run_count > 1:
        with open(OUTPUT_CSV, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        by_run = {}
        for r in rows:
            n = r.get("第几次")
            p = r.get("本次最低价_USD")
            if n and p:
                by_run[n] = p
        print("── 历次最低价 ──")
        for k in sorted(by_run.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            print(f"  第{k:>2}次：${by_run[k]}")


if __name__ == "__main__":
    main()
