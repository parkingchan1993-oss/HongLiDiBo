#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利低波100(930955) 全自动数据更新 + 策略评分脚本
================================================
用法: python auto_update.py <live_quotes_file>
  <live_quotes_file> 是由AI通过TDX connector拉取的实时行情JSON

自动完成:
  1. 读取最新实时行情
  2. 更新 history_klines.json (新增或修正最后1根K线)
  3. 更新 quotes_data.json
  4. 运行 dividend_strategy.py 重新评分并生成HTML仪表盘

数据来源: TDX connector (通达信) setcode=62 指数市场
"""

import json
import os
import sys
import subprocess
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE, "history_klines.json")
QUOTES_FILE = os.path.join(BASE, "quotes_data.json")
OUTPUT_HTML = os.path.join(BASE, "红利低波100策略仪表盘.html")


def load_json(fp):
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(fp, data):
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def update_from_live(live_file):
    """从实时行情JSON更新数据文件"""
    print(f"  数据源: {live_file}")

    with open(live_file, "r", encoding="utf-8") as f:
        live_raw = json.load(f)

    # 解析TDX行情结构
    hq = live_raw.get("HQInfo", live_raw)
    pinfo = live_raw.get("ProInfo", {})
    calc = live_raw.get("CalcInfo", {})
    base = live_raw.get("BaseInfo", {})

    hq_date = str(hq.get("HQDate", ""))
    hq_time = str(hq.get("HQTime", ""))
    now_price = float(hq.get("Now", 0))
    prev_close = float(hq.get("Close", 0))
    open_price = float(hq.get("Open", now_price))
    high_price = float(hq.get("MaxP", now_price))
    low_price = float(hq.get("MinP", now_price))
    volume = float(hq.get("Volume", 0))
    amount_val = float(hq.get("Amount", 0))
    lb = float(hq.get("LB", 0))

    # 涨跌幅计算
    if prev_close > 0:
        change_pct = round((now_price / prev_close - 1) * 100, 2)
    else:
        change_pct = 0.0

    # 扩展指标
    zaf20 = float(pinfo.get("Zaf20", 0))
    this_year = float(pinfo.get("ThisYear", 0))
    hist_high = float(pinfo.get("HisHigh", now_price))
    hist_low = float(pinfo.get("HisLow", now_price))

    print(f"  行情日期: {hq_date} 时间: {hq_time}")
    print(f"  昨收: {prev_close:.2f}  今开: {open_price:.2f}")
    print(f"  现价: {now_price:.2f}  {change_pct:+.2f}%")
    print(f"  最高: {high_price:.2f}  最低: {low_price:.2f}")

    # 判断是否是收盘数据
    hq_hour = int(hq_time[:2]) if len(hq_time) >= 2 else 0
    hq_min = int(hq_time[2:4]) if len(hq_time) >= 4 else 0
    is_close = (hq_hour >= 15 and hq_min >= 0)  # 15:00后视为收盘
    is_end_of_day = (hq_hour >= 15 or (hq_hour == 11 and hq_min >= 30))  # 午休或收盘
    is_market_closed = hq_hour >= 15  # 收盘后

    # 决定用哪个价格作为"收盘价"
    if is_market_closed:
        # 收盘后，Now就是收盘价
        close_price = now_price
        print(f"  ⏰ 收盘数据 (15:00后)")
    else:
        # 盘中，用当前价作为最新价（非收盘）
        close_price = now_price
        print(f"  ⏰ 盘中数据 ({hq_hour:02d}:{hq_min:02d})")

    # 更新数据
    klines = load_json(HISTORY_FILE)
    last_bar = klines[-1]
    print(f"\n  当前K线最后: {last_bar['date']} 收盘 {last_bar['close']}")

    if last_bar["date"] == hq_date:
        # 同一交易日: 更新最后一条K线
        old_close = last_bar["close"]
        last_bar["open"] = open_price
        last_bar["high"] = max(last_bar["high"], high_price)
        last_bar["low"] = min(last_bar["low"], low_price) if last_bar.get("low", 999999) < 999999 else low_price
        last_bar["close"] = close_price
        last_bar["volume"] = round(volume / 10000, 2)  # 转万手
        print(f"  ✅ 更新K线: {hq_date} {old_close} -> {close_price}")
    elif hq_date > last_bar["date"]:
        # 新交易日: 新增K线
        new_bar = {
            "date": hq_date,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": round(volume / 10000, 2),
        }
        klines.append(new_bar)
        print(f"  ✅ 新增K线: {hq_date} {close_price} (共{len(klines)}根)")
    else:
        print(f"  ⚠️ 行情日期({hq_date})晚于最后K线({last_bar['date']}), 保持不变")

    # 保存更新后的K线
    save_json(HISTORY_FILE, klines)
    print(f"  ✅ history_klines.json 保存 ({len(klines)}根)")

    # 更新quotes_data.json
    quotes = {
        "name": base.get("Name", "红利低波100"),
        "code": base.get("Code", "930955"),
        "current": close_price,
        "change_pct": change_pct,
        "change_20d": round(zaf20, 2),
        "change_ytd": round(this_year, 2),
        "hist_high": round(hist_high, 2),
        "hist_low": round(hist_low, 2),
        "volume": int(volume),
        "amount": int(amount_val),
        "lb": round(lb, 2),
        "hq_date": hq_date,
        "hq_time": hq_time,
        "etf_code": "515100",
        "etf_name": "红利低波100ETF景顺",
        "etf_price": 0.0,
        "etf_code2": "159307",
        "etf_name2": "红利低波100ETF"
    }
    save_json(QUOTES_FILE, quotes)
    print(f"  ✅ quotes_data.json 保存 (现价={close_price})")


def run_strategy():
    """运行主策略"""
    print(f"\n[2] 运行策略评分...")
    script = os.path.join(BASE, "dividend_strategy.py")

    # 使用 env 设置编码避免 Windows console GBK 问题
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, timeout=600, env=env
    )

    # 解码 stdout/stderr
    stdout_text = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

    # 打印输出
    for line in stdout_text.split("\n"):
        print(f"  {line}")
    if stderr_text.strip():
        for line in stderr_text.split("\n"):
            if line.strip():
                print(f"  [ERR] {line}")

    if os.path.exists(OUTPUT_HTML):
        size = os.path.getsize(OUTPUT_HTML)
        print(f"\n  ✅ HTML仪表盘: {OUTPUT_HTML} ({size} bytes)")
    return result.returncode == 0


def main():
    if len(sys.argv) < 2:
        print("=" * 66)
        print("红利低波100(930955) 全自动数据更新")
        print("=" * 66)
        print()
        print("用法: python auto_update.py <live_quotes.json>")
        print()
        print("  <live_quotes.json> 由AI通过TDX connector拉取实时行情后提供")
        print()
        print("完整流程:")
        print("  1. AI: 调用TDX connector tdx_quotes(code=930955, setcode=62)")
        print("  2. AI: 将结果保存为JSON文件")
        print("  3. 脚本: 读取JSON → 更新数据文件 → 运行策略")
        print("  4. AI: 展示结果给用户")
        print()
        sys.exit(1)

    live_file = sys.argv[1]
    if not os.path.exists(live_file):
        print(f"错误: 文件不存在 {live_file}")
        sys.exit(1)

    print("=" * 66)
    print(f"红利低波100(930955) 全自动数据更新")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 66)

    # Step 1: 更新数据
    print(f"\n[1] 解析实时行情并更新数据文件...")
    update_from_live(live_file)

    # Step 2: 运行策略
    run_strategy()

    print("\n" + "=" * 66)
    print("  ✅ 全部完成!")
    print(f"  📄 {OUTPUT_HTML}")
    print("=" * 66)


if __name__ == "__main__":
    main()
