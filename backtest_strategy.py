#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利低波100(930955) MA250偏离值回测策略
========================================
核心逻辑:
  1. 计算每日收盘价与MA250的偏离值: (close - MA250) / MA250 * 100%
  2. 按1%间隔分档: [0%,1%), [1%,2%), [-1%,0%), ...
  3. 对每个档位, 回测第30/60/120/250个工作日后的胜率和平均收益
  4. 统计每个档位的历史天数及占比

数据来源: TDX connector (通达信) setcode=62 target=1 日K线
"""

import json
import os
import sys
import math
import requests
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE, "history_klines.json")
OUTPUT_HTML = os.path.join(BASE, "MA250偏离值回测看板.html")

MA_PERIOD = 250
HOLD_PERIODS = [30, 60, 120, 250]
BUCKET_SIZE = 1.0  # 1%一档


def load_klines():
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # Ensure all numeric fields are float
    for k in raw:
        k["open"] = float(k["open"])
        k["close"] = float(k["close"])
        k["high"] = float(k["high"])
        k["low"] = float(k["low"])
        k["volume"] = float(k["volume"]) if "volume" in k else 0.0
    return raw


def calc_ma250(closes, idx):
    """计算第idx日的MA250"""
    if idx < MA_PERIOD - 1:
        return None
    return sum(closes[idx - MA_PERIOD + 1: idx + 1]) / MA_PERIOD


def get_bucket(deviation_pct):
    """
    将偏离值分档, 左闭右开
    例如: 0.5% -> "0%~1%", -0.5% -> "-1%~0%", 1.0% -> "1%~2%"
    """
    bucket_idx = int(math.floor(deviation_pct / BUCKET_SIZE))
    lower = bucket_idx * BUCKET_SIZE
    upper = lower + BUCKET_SIZE
    if lower >= 0:
        label = f"{lower:.0f}%~{upper:.0f}%"
    else:
        label = f"{lower:.0f}%~{upper:.0f}%"
    return bucket_idx, label


def run_backtest(klines):
    """
    执行完整回测
    返回: {
        buckets: {bucket_idx: {label, count, win_rates, avg_returns, samples}},
        above_count, below_count, total_valid,
        current_deviation, current_bucket
    }
    """
    closes = [k["close"] for k in klines]
    dates = [k["date"] for k in klines]
    n = len(closes)
    
    # 从第250根开始才有MA250
    start_idx = MA_PERIOD - 1  # index 249 (第250根)
    
    # 收集每个档位的数据
    bucket_data = defaultdict(lambda: {
        "label": "",
        "count": 0,
        "win_counts": {p: 0 for p in HOLD_PERIODS},
        "valid_counts": {p: 0 for p in HOLD_PERIODS},
        "returns": {p: [] for p in HOLD_PERIODS},
        "sample_dates": [],
    })
    
    above_count = 0
    below_count = 0
    
    for i in range(start_idx, n):
        ma250 = calc_ma250(closes, i)
        if ma250 is None or ma250 <= 0:
            continue
        
        deviation = (closes[i] - ma250) / ma250 * 100.0
        bucket_idx, label = get_bucket(deviation)
        
        bucket_data[bucket_idx]["label"] = label
        bucket_data[bucket_idx]["count"] += 1
        bucket_data[bucket_idx]["sample_dates"].append(dates[i])
        
        if deviation >= 0:
            above_count += 1
        else:
            below_count += 1
        
        # 对每个持有期计算胜率和收益
        for hold_p in HOLD_PERIODS:
            future_idx = i + hold_p
            if future_idx < n:
                ret = (closes[future_idx] - closes[i]) / closes[i] * 100.0
                bucket_data[bucket_idx]["returns"][hold_p].append(ret)
                bucket_data[bucket_idx]["valid_counts"][hold_p] += 1
                if ret > 0:
                    bucket_data[bucket_idx]["win_counts"][hold_p] += 1
    
    # 计算最终统计
    total_valid = above_count + below_count
    results = []
    
    for bucket_idx in sorted(bucket_data.keys()):
        bd = bucket_data[bucket_idx]
        entry = {
            "bucket_idx": bucket_idx,
            "label": bd["label"],
            "count": bd["count"],
            "count_pct": round(bd["count"] / total_valid * 100, 2) if total_valid > 0 else 0,
            "above_ma250": bucket_idx >= 0,
            "stats": {}
        }
        
        # 占比: 250线以上/以下
        if bucket_idx >= 0:
            entry["group"] = "above"
            entry["group_pct"] = round(bd["count"] / above_count * 100, 2) if above_count > 0 else 0
        else:
            entry["group"] = "below"
            entry["group_pct"] = round(bd["count"] / below_count * 100, 2) if below_count > 0 else 0
        
        for p in HOLD_PERIODS:
            valid = bd["valid_counts"][p]
            wins = bd["win_counts"][p]
            rets = bd["returns"][p]
            
            if valid > 0:
                win_rate = round(wins / valid * 100, 2)
                avg_ret = round(sum(rets) / len(rets), 2)
                if len(rets) > 1:
                    mean = sum(rets) / len(rets)
                    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
                    std = math.sqrt(variance)
                else:
                    std = 0
                max_ret = round(max(rets), 2)
                min_ret = round(min(rets), 2)
            else:
                win_rate = None
                avg_ret = None
                std = 0
                max_ret = None
                min_ret = None
            
            entry["stats"][p] = {
                "valid_count": valid,
                "win_rate": win_rate,
                "avg_return": avg_ret,
                "std": round(std, 2),
                "max_return": max_ret,
                "min_return": min_ret,
            }
        
        results.append(entry)
    
    # 当前偏离值
    current_idx = n - 1
    current_ma250 = calc_ma250(closes, current_idx)
    current_deviation = round((closes[current_idx] - current_ma250) / current_ma250 * 100, 2)
    _, current_label = get_bucket(current_deviation)
    
    # 构建K线图数据: [date, open, close, low, high] 和 MA250值
    kline_chart_dates = []
    kline_chart_ohlc = []
    kline_chart_ma250 = []
    kline_chart_volume = []
    for i in range(n):
        k = klines[i]
        kline_chart_dates.append(k["date"])
        kline_chart_ohlc.append([k["open"], k["close"], k["low"], k["high"]])
        ma_val = calc_ma250(closes, i)
        kline_chart_ma250.append(round(ma_val, 2) if ma_val else None)
        kline_chart_volume.append(k.get("volume", 0))

    return {
        "buckets": results,
        "above_count": above_count,
        "below_count": below_count,
        "total_valid": total_valid,
        "above_pct": round(above_count / total_valid * 100, 2),
        "below_pct": round(below_count / total_valid * 100, 2),
        "current_date": dates[current_idx],
        "current_close": round(closes[current_idx], 2),
        "current_ma250": round(current_ma250, 2),
        "current_deviation": current_deviation,
        "current_bucket": current_label,
        "total_klines": n,
        "valid_klines": total_valid,
        # K线图数据
        "kline_dates": kline_chart_dates,
        "kline_ohlc": kline_chart_ohlc,
        "kline_ma250": kline_chart_ma250,
        "kline_volume": kline_chart_volume,
    }


def run_peak_backtest(klines):
    """
    第二维: 基于高点回落的回测
    峰值=历史最高价(High)的running max
    回落值=(高峰-收盘)/高峰×100%, 始终≥0
    """
    highs = [float(k["high"]) for k in klines]
    closes = [float(k["close"]) for k in klines]
    dates = [k["date"] for k in klines]
    n = len(klines)

    # 计算 running max peak（历史最高价High）
    peaks = []
    running_max = 0.0
    for h in highs:
        running_max = max(running_max, h)
        peaks.append(running_max)

    bucket_data = defaultdict(lambda: {
        "label": "",
        "count": 0,
        "win_counts": {p: 0 for p in HOLD_PERIODS},
        "valid_counts": {p: 0 for p in HOLD_PERIODS},
        "returns": {p: [] for p in HOLD_PERIODS},
    })

    at_peak_count = 0       # 回落=0% 的天数
    deep_pullback_count = 0 # 回落>5% 的天数

    for i in range(n):
        if peaks[i] <= 0:
            continue
        pullback = (peaks[i] - closes[i]) / peaks[i] * 100.0
        bucket_idx = int(math.floor(pullback / BUCKET_SIZE))
        lower = bucket_idx * BUCKET_SIZE
        upper = lower + BUCKET_SIZE
        if lower >= 0:
            label = f"{lower:.0f}%~{upper:.0f}%"
        else:
            label = f"{lower:.0f}%~{upper:.0f}%"
            bucket_idx = bucket_idx  # should not happen

        bucket_data[bucket_idx]["label"] = label
        bucket_data[bucket_idx]["count"] += 1

        if pullback < 1.0:
            at_peak_count += 1
        if pullback > 5.0:
            deep_pullback_count += 1

        for hold_p in HOLD_PERIODS:
            future_idx = i + hold_p
            if future_idx < n:
                ret = (closes[future_idx] - closes[i]) / closes[i] * 100.0
                bucket_data[bucket_idx]["returns"][hold_p].append(ret)
                bucket_data[bucket_idx]["valid_counts"][hold_p] += 1
                if ret > 0:
                    bucket_data[bucket_idx]["win_counts"][hold_p] += 1

    # 统计结果
    total_valid = n
    results = []
    for bucket_idx in sorted(bucket_data.keys()):
        bd = bucket_data[bucket_idx]
        entry = {
            "bucket_idx": bucket_idx,
            "label": bd["label"],
            "count": bd["count"],
            "count_pct": round(bd["count"] / total_valid * 100, 2),
            "stats": {}
        }
        for p in HOLD_PERIODS:
            valid = bd["valid_counts"][p]
            wins = bd["win_counts"][p]
            rets = bd["returns"][p]
            if valid > 0:
                win_rate = round(wins / valid * 100, 2)
                avg_ret = round(sum(rets) / len(rets), 2)
            else:
                win_rate = None
                avg_ret = None
            entry["stats"][p] = {
                "valid_count": valid,
                "win_rate": win_rate,
                "avg_return": avg_ret,
            }
        results.append(entry)

    # 当前状态
    current_idx = n - 1
    current_peak = peaks[current_idx]
    current_pullback = round((current_peak - closes[current_idx]) / current_peak * 100, 2)
    current_bucket_idx = int(math.floor(current_pullback / BUCKET_SIZE))
    lower = current_bucket_idx * BUCKET_SIZE
    upper = lower + BUCKET_SIZE
    current_label = f"{lower:.0f}%~{upper:.0f}%"

    return {
        "buckets": results,
        "at_peak_count": at_peak_count,
        "deep_pullback_count": deep_pullback_count,
        "at_peak_pct": round(at_peak_count / total_valid * 100, 2),
        "deep_pct": round(deep_pullback_count / total_valid * 100, 2),
        "total_valid": total_valid,
        "current_date": dates[current_idx],
        "current_close": round(closes[current_idx], 2),
        "current_peak": round(current_peak, 2),
        "current_pullback": current_pullback,
        "current_bucket": current_label,
        "total_klines": n,
        "valid_klines": total_valid,
        # 峰值线数据（用于可能的后续展示）
        "peak_values": [round(p, 2) for p in peaks],
    }



DIV_BUCKET_SIZE = 0.25  # 股息率0.25%一档


def fetch_div_yield():
    """
    获取930955历史股息率数据
    数据源: CSI index-perf API (PE) + AKShare (最近20天真实股息率校准)
    估算公式: 股息率 = payout_ratio / PE × 100
    """
    # 1. 从CSI API获取完整历史PE数据
    url = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
    params = {"indexCode": "930955", "startDate": "20200101", "endDate": "20260727"}
    r = requests.get(url, params=params, timeout=15)
    csi_rows = r.json()["data"]

    # 2. 从AKShare获取最近20天真实股息率, 校准payout_ratio
    try:
        import akshare as ak
        df_real = ak.stock_zh_index_value_csindex("930955")
        # 取最新一行: PE1 和 股息率2
        latest = df_real.iloc[0]
        pe1 = float(latest["市盈率1"])
        dy2 = float(latest["股息率2"])
        payout_ratio = dy2 * pe1 / 100.0  # payout_ratio = dy × PE / 100
        print(f"  AKShare校准: PE1={pe1:.2f}, 股息率2={dy2:.2f}%, payout_ratio={payout_ratio:.4f}")
    except Exception as e:
        print(f"  AKShare校准失败, 使用默认值: {e}")
        payout_ratio = 0.404  # fallback

    # 3. 估算历史股息率
    div_dict = {}
    for row in csi_rows:
        d = row["tradeDate"]
        pe = row.get("peg")  # peg字段实际是PE1
        if pe and pe > 0:
            div_dict[d] = round(payout_ratio / pe * 100, 4)

    print(f"  CSI API: {len(csi_rows)}行PE数据, 估算股息率范围: {min(div_dict.values()):.2f}% ~ {max(div_dict.values()):.2f}%")
    return div_dict


def run_dividend_backtest(klines, div_dict):
    """
    第三维: 基于股息率的回测
    分档: 0.25%一档, 左闭右开
    """
    closes = [float(k["close"]) for k in klines]
    dates = [k["date"] for k in klines]
    n = len(klines)

    # 匹配股息率: forward fill (用最近的前一个有效值)
    div_values = []
    last_div = None
    for d in dates:
        if d in div_dict:
            last_div = div_dict[d]
        div_values.append(last_div)

    bucket_data = defaultdict(lambda: {
        "label": "",
        "count": 0,
        "win_counts": {p: 0 for p in HOLD_PERIODS},
        "valid_counts": {p: 0 for p in HOLD_PERIODS},
        "returns": {p: [] for p in HOLD_PERIODS},
    })

    high_div_count = 0   # 股息率 >= 5%
    low_div_count = 0    # 股息率 < 4%
    valid_count = 0

    for i in range(n):
        if div_values[i] is None:
            continue
        valid_count += 1
        div = div_values[i]
        bucket_idx = int(math.floor(div / DIV_BUCKET_SIZE))
        lower = bucket_idx * DIV_BUCKET_SIZE
        upper = lower + DIV_BUCKET_SIZE
        label = f"{lower:.2f}%~{upper:.2f}%"

        bucket_data[bucket_idx]["label"] = label
        bucket_data[bucket_idx]["count"] += 1

        if div >= 5.0:
            high_div_count += 1
        if div < 4.0:
            low_div_count += 1

        for hold_p in HOLD_PERIODS:
            future_idx = i + hold_p
            if future_idx < n:
                ret = (closes[future_idx] - closes[i]) / closes[i] * 100.0
                bucket_data[bucket_idx]["returns"][hold_p].append(ret)
                bucket_data[bucket_idx]["valid_counts"][hold_p] += 1
                if ret > 0:
                    bucket_data[bucket_idx]["win_counts"][hold_p] += 1

    # 统计结果
    results = []
    for bucket_idx in sorted(bucket_data.keys()):
        bd = bucket_data[bucket_idx]
        entry = {
            "bucket_idx": bucket_idx,
            "label": bd["label"],
            "count": bd["count"],
            "count_pct": round(bd["count"] / valid_count * 100, 2) if valid_count > 0 else 0,
            "stats": {}
        }
        for p in HOLD_PERIODS:
            valid = bd["valid_counts"][p]
            wins = bd["win_counts"][p]
            rets = bd["returns"][p]
            if valid > 0:
                win_rate = round(wins / valid * 100, 2)
                avg_ret = round(sum(rets) / len(rets), 2)
            else:
                win_rate = None
                avg_ret = None
            entry["stats"][p] = {
                "valid_count": valid,
                "win_rate": win_rate,
                "avg_return": avg_ret,
            }
        results.append(entry)

    # 当前状态
    current_idx = n - 1
    current_div = div_values[current_idx]
    current_bucket_idx = int(math.floor(current_div / DIV_BUCKET_SIZE))
    lower = current_bucket_idx * DIV_BUCKET_SIZE
    upper = lower + DIV_BUCKET_SIZE
    current_label = f"{lower:.2f}%~{upper:.2f}%"

    return {
        "buckets": results,
        "high_div_count": high_div_count,
        "low_div_count": low_div_count,
        "high_div_pct": round(high_div_count / valid_count * 100, 2) if valid_count > 0 else 0,
        "low_div_pct": round(low_div_count / valid_count * 100, 2) if valid_count > 0 else 0,
        "total_valid": valid_count,
        "current_date": dates[current_idx],
        "current_close": round(closes[current_idx], 2),
        "current_div_yield": round(current_div, 2),
        "current_bucket": current_label,
        "total_klines": n,
        "valid_klines": valid_count,
    }


def generate_html(result_ma, result_peak, result_div):

    """生成HTML看板（包含三个维度）"""
    # === 第一维: MA250 ===
    result = result_ma  # 别名，保持后面代码不变
    b = result["buckets"]
    
    # 按bucket_idx排序, 分为above和below
    above_buckets = [x for x in b if x["above_ma250"]]
    below_buckets = [x for x in b if not x["above_ma250"]]
    above_buckets.sort(key=lambda x: x["bucket_idx"])
    below_buckets.sort(key=lambda x: x["bucket_idx"])
    
    # 合并为完整列表(从低到高)
    all_buckets = sorted(b, key=lambda x: x["bucket_idx"])
    
    # 构建表格行
    def make_table_rows(buckets):
        rows = ""
        for entry in buckets:
            label = entry["label"]
            count = entry["count"]
            count_pct = entry["count_pct"]
            group_pct = entry["group_pct"]
            
            # 颜色: 胜率>60%红色(买入), <40%绿色(卖出)
            color_30 = "#dc2626" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] >= 60 else ("#16a34a" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] < 40 else "#94a3b8")
            
            wr30 = f'{entry["stats"][30]["win_rate"]}%' if entry["stats"][30]["win_rate"] is not None else "N/A"
            wr60 = f'{entry["stats"][60]["win_rate"]}%' if entry["stats"][60]["win_rate"] is not None else "N/A"
            wr120 = f'{entry["stats"][120]["win_rate"]}%' if entry["stats"][120]["win_rate"] is not None else "N/A"
            wr250 = f'{entry["stats"][250]["win_rate"]}%' if entry["stats"][250]["win_rate"] is not None else "N/A"
            
            ar30 = f'{entry["stats"][30]["avg_return"]:+.2f}%' if entry["stats"][30]["avg_return"] is not None else "N/A"
            ar60 = f'{entry["stats"][60]["avg_return"]:+.2f}%' if entry["stats"][60]["avg_return"] is not None else "N/A"
            ar120 = f'{entry["stats"][120]["avg_return"]:+.2f}%' if entry["stats"][120]["avg_return"] is not None else "N/A"
            ar250 = f'{entry["stats"][250]["avg_return"]:+.2f}%' if entry["stats"][250]["avg_return"] is not None else "N/A"
            
            # 当前档位高亮
            highlight = 'style="background:#fef3c7"' if label == result["current_bucket"] else ""
            
            rows += f'''<tr {highlight}>
<td><b>{label}</b></td>
<td>{count}</td><td>{count_pct}%</td><td>{group_pct}%</td>
<td style="color:{color_30};font-weight:600">{wr30}</td><td>{ar30}</td>
<td style="color:{color_30};font-weight:600">{wr60}</td><td>{ar60}</td>
<td style="color:{color_30};font-weight:600">{wr120}</td><td>{ar120}</td>
<td style="color:{color_30};font-weight:600">{wr250}</td><td>{ar250}</td>
</tr>'''
        return rows
    
    all_rows = make_table_rows(all_buckets)
    
    # 图表数据: 各档位的胜率和收益
    chart_labels = json.dumps([e["label"] for e in all_buckets])
    chart_wr30 = json.dumps([e["stats"][30]["win_rate"] if e["stats"][30]["win_rate"] else 0 for e in all_buckets])
    chart_wr60 = json.dumps([e["stats"][60]["win_rate"] if e["stats"][60]["win_rate"] else 0 for e in all_buckets])
    chart_wr120 = json.dumps([e["stats"][120]["win_rate"] if e["stats"][120]["win_rate"] else 0 for e in all_buckets])
    chart_wr250 = json.dumps([e["stats"][250]["win_rate"] if e["stats"][250]["win_rate"] else 0 for e in all_buckets])
    chart_ar30 = json.dumps([e["stats"][30]["avg_return"] if e["stats"][30]["avg_return"] else 0 for e in all_buckets])
    chart_ar60 = json.dumps([e["stats"][60]["avg_return"] if e["stats"][60]["avg_return"] else 0 for e in all_buckets])
    chart_ar120 = json.dumps([e["stats"][120]["avg_return"] if e["stats"][120]["avg_return"] else 0 for e in all_buckets])
    chart_ar250 = json.dumps([e["stats"][250]["avg_return"] if e["stats"][250]["avg_return"] else 0 for e in all_buckets])
    chart_counts = json.dumps([e["count"] for e in all_buckets])
    
    # 各档位天数分布
    chart_dist_labels = json.dumps([e["label"] for e in all_buckets])
    chart_dist_data = json.dumps([e["count"] for e in all_buckets])
    labove_json = json.dumps([e["above_ma250"] for e in all_buckets])

    # === 第二维: 高点回落 数据准备 ===
    pb = result_peak["buckets"]
    peak_buckets = sorted(pb, key=lambda x: x["bucket_idx"])
    peak_labels = json.dumps([e["label"] for e in peak_buckets])
    peak_wr30 = json.dumps([e["stats"][30]["win_rate"] if e["stats"][30]["win_rate"] else 0 for e in peak_buckets])
    peak_wr60 = json.dumps([e["stats"][60]["win_rate"] if e["stats"][60]["win_rate"] else 0 for e in peak_buckets])
    peak_wr120 = json.dumps([e["stats"][120]["win_rate"] if e["stats"][120]["win_rate"] else 0 for e in peak_buckets])
    peak_wr250 = json.dumps([e["stats"][250]["win_rate"] if e["stats"][250]["win_rate"] else 0 for e in peak_buckets])
    peak_ar30 = json.dumps([e["stats"][30]["avg_return"] if e["stats"][30]["avg_return"] else 0 for e in peak_buckets])
    peak_ar60 = json.dumps([e["stats"][60]["avg_return"] if e["stats"][60]["avg_return"] else 0 for e in peak_buckets])
    peak_ar120 = json.dumps([e["stats"][120]["avg_return"] if e["stats"][120]["avg_return"] else 0 for e in peak_buckets])
    peak_ar250 = json.dumps([e["stats"][250]["avg_return"] if e["stats"][250]["avg_return"] else 0 for e in peak_buckets])
    peak_counts = json.dumps([e["count"] for e in peak_buckets])

    def make_peak_rows(buckets):
        rows = ""
        for entry in buckets:
            label = entry["label"]
            count = entry["count"]
            count_pct = entry["count_pct"]
            wr30 = f'{entry["stats"][30]["win_rate"]}%' if entry["stats"][30]["win_rate"] is not None else "N/A"
            wr60 = f'{entry["stats"][60]["win_rate"]}%' if entry["stats"][60]["win_rate"] is not None else "N/A"
            wr120 = f'{entry["stats"][120]["win_rate"]}%' if entry["stats"][120]["win_rate"] is not None else "N/A"
            wr250 = f'{entry["stats"][250]["win_rate"]}%' if entry["stats"][250]["win_rate"] is not None else "N/A"
            ar30 = f'{entry["stats"][30]["avg_return"]:+.2f}%' if entry["stats"][30]["avg_return"] is not None else "N/A"
            ar60 = f'{entry["stats"][60]["avg_return"]:+.2f}%' if entry["stats"][60]["avg_return"] is not None else "N/A"
            ar120 = f'{entry["stats"][120]["avg_return"]:+.2f}%' if entry["stats"][120]["avg_return"] is not None else "N/A"
            ar250 = f'{entry["stats"][250]["avg_return"]:+.2f}%' if entry["stats"][250]["avg_return"] is not None else "N/A"
            c = "#dc2626" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] >= 60 else ("#16a34a" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] < 40 else "#94a3b8")
            highlight = 'style="background:#fef3c7"' if label == result_peak["current_bucket"] else ""
            rows += f'''<tr {highlight}>
<td><b>{label}</b></td><td>{count}</td><td>{count_pct}%</td>
<td style="color:{c};font-weight:600">{wr30}</td><td>{ar30}</td>
<td style="color:{c};font-weight:600">{wr60}</td><td>{ar60}</td>
<td style="color:{c};font-weight:600">{wr120}</td><td>{ar120}</td>
<td style="color:{c};font-weight:600">{wr250}</td><td>{ar250}</td>
</tr>'''
        return rows
    peak_rows = make_peak_rows(peak_buckets)
    peak_dev_color = "#16a34a" if result_peak["current_pullback"] > 5 else ("#f59e0b" if result_peak["current_pullback"] > 2 else "#dc2626")

    # === 第三维: 股息率 数据准备 ===
    db = result_div["buckets"]
    div_buckets = sorted(db, key=lambda x: x["bucket_idx"])
    div_labels = json.dumps([e["label"] for e in div_buckets])
    div_wr30 = json.dumps([e["stats"][30]["win_rate"] if e["stats"][30]["win_rate"] else 0 for e in div_buckets])
    div_wr60 = json.dumps([e["stats"][60]["win_rate"] if e["stats"][60]["win_rate"] else 0 for e in div_buckets])
    div_wr120 = json.dumps([e["stats"][120]["win_rate"] if e["stats"][120]["win_rate"] else 0 for e in div_buckets])
    div_wr250 = json.dumps([e["stats"][250]["win_rate"] if e["stats"][250]["win_rate"] else 0 for e in div_buckets])
    div_ar30 = json.dumps([e["stats"][30]["avg_return"] if e["stats"][30]["avg_return"] else 0 for e in div_buckets])
    div_ar60 = json.dumps([e["stats"][60]["avg_return"] if e["stats"][60]["avg_return"] else 0 for e in div_buckets])
    div_ar120 = json.dumps([e["stats"][120]["avg_return"] if e["stats"][120]["avg_return"] else 0 for e in div_buckets])
    div_ar250 = json.dumps([e["stats"][250]["avg_return"] if e["stats"][250]["avg_return"] else 0 for e in div_buckets])
    div_counts = json.dumps([e["count"] for e in div_buckets])
    div_high_json = json.dumps([e["bucket_idx"] * DIV_BUCKET_SIZE >= 5.0 for e in div_buckets])

    def make_div_rows(buckets):
        rows = ""
        for entry in buckets:
            label = entry["label"]
            count = entry["count"]
            count_pct = entry["count_pct"]
            wr30 = f'{entry["stats"][30]["win_rate"]}%' if entry["stats"][30]["win_rate"] is not None else "N/A"
            wr60 = f'{entry["stats"][60]["win_rate"]}%' if entry["stats"][60]["win_rate"] is not None else "N/A"
            wr120 = f'{entry["stats"][120]["win_rate"]}%' if entry["stats"][120]["win_rate"] is not None else "N/A"
            wr250 = f'{entry["stats"][250]["win_rate"]}%' if entry["stats"][250]["win_rate"] is not None else "N/A"
            ar30 = f'{entry["stats"][30]["avg_return"]:+.2f}%' if entry["stats"][30]["avg_return"] is not None else "N/A"
            ar60 = f'{entry["stats"][60]["avg_return"]:+.2f}%' if entry["stats"][60]["avg_return"] is not None else "N/A"
            ar120 = f'{entry["stats"][120]["avg_return"]:+.2f}%' if entry["stats"][120]["avg_return"] is not None else "N/A"
            ar250 = f'{entry["stats"][250]["avg_return"]:+.2f}%' if entry["stats"][250]["avg_return"] is not None else "N/A"
            c = "#dc2626" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] >= 60 else ("#16a34a" if entry["stats"][30]["win_rate"] and entry["stats"][30]["win_rate"] < 40 else "#94a3b8")
            highlight = 'style="background:#fef3c7"' if label == result_div["current_bucket"] else ""
            rows += f'''<tr {highlight}>
<td><b>{label}</b></td><td>{count}</td><td>{count_pct}%</td>
<td style="color:{c};font-weight:600">{wr30}</td><td>{ar30}</td>
<td style="color:{c};font-weight:600">{wr60}</td><td>{ar60}</td>
<td style="color:{c};font-weight:600">{wr120}</td><td>{ar120}</td>
<td style="color:{c};font-weight:600">{wr250}</td><td>{ar250}</td>
</tr>'''
        return rows
    div_rows = make_div_rows(div_buckets)
    div_dev_color = "#16a34a" if result_div["current_div_yield"] >= 5.0 else ("#f59e0b" if result_div["current_div_yield"] >= 4.0 else "#dc2626")
    # K线图数据
    kline_dates_json = json.dumps(result["kline_dates"])
    kline_ohlc_json = json.dumps(result["kline_ohlc"])
    kline_ma250_json = json.dumps(result["kline_ma250"])
    kline_volume_json = json.dumps(result["kline_volume"])
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 当前状态
    dev_color = "#dc2626" if result["current_deviation"] > 0 else "#16a34a"
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>红利低波100(930955) MA250偏离值回测看板</title>
<script>[[ECHARTS_INLINE]]</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f1f5f9;color:#1e293b;padding:16px}}
.ct{{max-width:1600px;margin:0 auto}}
.hd{{background:linear-gradient(135deg,#1e293b,#334155);color:#fff;padding:24px 32px;border-radius:16px 16px 0 0}}
.hd h1{{font-size:22px;font-weight:700}}
.hd .sub{{font-size:13px;color:#94a3b8;margin-top:4px}}
.mb{{background:#fff;padding:24px 32px;border-radius:0 0 16px 16px;box-shadow:0 4px 6px rgba(0,0,0,.05)}}
.sc{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.sc-c{{text-align:center;padding:20px;border-radius:12px;background:#f8fafc;border:2px solid {dev_color}}}
.sc-c .num{{font-size:36px;font-weight:800;color:{dev_color};line-height:1}}
.sc-c .lbl{{font-size:13px;color:#64748b;margin-top:8px}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.sum-c{{background:#f8fafc;border-radius:8px;padding:12px;text-align:center}}
.sum-c .v{{font-size:20px;font-weight:700;color:#1e293b}}
.sum-c .l{{font-size:12px;color:#64748b;margin-top:4px}}
.cb{{background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:16px}}
.cb h3{{font-size:15px;color:#475569;margin-bottom:10px}}
.cht{{width:100%;height:400px}}
.cht-s{{width:100%;height:350px}}
.cht-xl{{width:100%;height:550px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}}
th{{background:#1e293b;color:#fff;padding:8px 6px;text-align:center;position:sticky;top:0}}
td{{padding:6px;text-align:center;border-bottom:1px solid #e2e8f0}}
.dh td{{background:#f8fafc;font-weight:700}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#fff}}
.tag-r{{background:#dc2626}}.tag-g{{background:#16a34a}}
.ft{{text-align:center;padding:16px;color:#94a3b8;font-size:12px}}
.update-time{{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:8px 16px;font-size:12px;color:#64748b;text-align:center;margin-bottom:16px}}
.hist-scroll{{max-height:600px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px}}
</style></head><body><div class="ct">
<div class="hd"><h1>红利低波100(930955) 多维买卖策略看板</h1>
<div class="sub">第一维: MA250偏离值回测 | 第二维: 高点回落回测 | 数据来源: TDX connector setcode=62 target=1 | {result_ma["total_klines"]}根日K线</div></div>
<div class="mb">

<div class="update-time">行情{result["current_date"]} | 策略生成 {now_str}</div>

<div style="margin:0 0 16px"><h2 style="font-size:20px;color:#1e293b">第一维：MA250偏离值回测</h2></div>

<div class="sc">
<div class="sc-c"><div class="lbl">当前偏离值</div><div class="num">{result["current_deviation"]:+.2f}%</div><div class="lbl">档位: {result["current_bucket"]}</div></div>
<div class="sc-c" style="border-color:#3b82f6"><div class="lbl">当前收盘价</div><div class="num" style="color:#3b82f6">{result["current_close"]:.2f}</div><div class="lbl">日期: {result["current_date"]}</div></div>
<div class="sc-c" style="border-color:#8b5cf6"><div class="lbl">当前MA250</div><div class="num" style="color:#8b5cf6">{result["current_ma250"]:.2f}</div><div class="lbl">年线位置</div></div>
<div class="sc-c" style="border-color:#f59e0b"><div class="lbl">有效回测天数</div><div class="num" style="color:#f59e0b">{result["total_valid"]}</div><div class="lbl">MA250以上{result["above_pct"]}% / 以下{result["below_pct"]}%</div></div>
</div>

<div class="summary">
<div class="sum-c"><div class="v" style="color:#dc2626">{result["above_count"]}</div><div class="l">MA250以上天数</div></div>
<div class="sum-c"><div class="v" style="color:#16a34a">{result["below_count"]}</div><div class="l">MA250以下天数</div></div>
<div class="sum-c"><div class="v">{result["above_pct"]}%</div><div class="l">以上占比</div></div>
<div class="sum-c"><div class="v">{result["below_pct"]}%</div><div class="l">以下占比</div></div>
</div>

<!-- K线走势图 -->
<div class="cb"><h3>K线走势图 &amp; MA250年线</h3><div id="kline_chart" class="cht-xl"></div></div>

<!-- 图表区 -->
<div class="cb"><h3>各档位胜率对比 (30/60/120/250日后)</h3><div id="wr_chart" class="cht"></div></div>
<div class="cb"><h3>各档位平均收益对比 (30/60/120/250日后)</h3><div id="ret_chart" class="cht"></div></div>
<div class="cb"><h3>各档位天数分布</h3><div id="dist_chart" class="cht-s"></div></div>

<!-- 回测明细表 -->
<div class="cb" style="margin-bottom:16px">
<h3>MA250偏离值回测明细表 (黄色高亮=当前档位)</h3>
<div class="hist-scroll">
<table>
<thead><tr>
<th rowspan="2">偏离值档位</th>
<th rowspan="2">天数</th>
<th rowspan="2">总占比</th>
<th rowspan="2">组内占比</th>
<th colspan="2">30日后</th>
<th colspan="2">60日后</th>
<th colspan="2">120日后</th>
<th colspan="2">250日后</th>
</tr>
<tr>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
</tr></thead>
<tbody>
{all_rows}
</tbody></table>
</div></div>

<!-- ========== 第二维: 高点回落 ========== -->
<div style="margin:32px 0 16px;border-top:3px solid #e2e8f0;padding-top:20px">
  <h2 style="font-size:20px;color:#1e293b">第二维：高点回落回测</h2>
  <p style="font-size:13px;color:#64748b;margin-top:4px">峰值=历史最高价(High) | 回落值=(峰值-收盘)/峰值×100% | 全部{result_peak["total_klines"]}根K线有效</p>
</div>

<div class="sc">
<div class="sc-c" style="border-color:{peak_dev_color}"><div class="lbl">当前回落值</div><div class="num" style="color:{peak_dev_color}">{result_peak["current_pullback"]:+.2f}%</div><div class="lbl">档位: {result_peak["current_bucket"]}</div></div>
<div class="sc-c" style="border-color:#3b82f6"><div class="lbl">当前收盘价</div><div class="num" style="color:#3b82f6">{result_peak["current_close"]:.2f}</div><div class="lbl">日期: {result_peak["current_date"]}</div></div>
<div class="sc-c" style="border-color:#8b5cf6"><div class="lbl">历史峰值High</div><div class="num" style="color:#8b5cf6">{result_peak["current_peak"]:.2f}</div><div class="lbl">历史最高价</div></div>
<div class="sc-c" style="border-color:#f59e0b"><div class="lbl">有效回测天数</div><div class="num" style="color:#f59e0b">{result_peak["total_valid"]}</div><div class="lbl">峰顶{result_peak["at_peak_pct"]}% / 深回落{result_peak["deep_pct"]}%</div></div>
</div>

<div class="summary">
<div class="sum-c"><div class="v" style="color:#dc2626">{result_peak["at_peak_count"]}</div><div class="l">处于峰值天数(0%~1%回落)</div></div>
<div class="sum-c"><div class="v" style="color:#16a34a">{result_peak["deep_pullback_count"]}</div><div class="l">深回落天数(&gt;5%)</div></div>
<div class="sum-c"><div class="v">{result_peak["at_peak_pct"]}%</div><div class="l">峰顶占比</div></div>
<div class="sum-c"><div class="v">{result_peak["deep_pct"]}%</div><div class="l">深回落占比</div></div>
</div>

<!-- 第二维图表 -->
<div class="cb"><h3>高点回落 · 各档位胜率对比 (30/60/120/250日后)</h3><div id="peak_wr_chart" class="cht"></div></div>
<div class="cb"><h3>高点回落 · 各档位平均收益对比 (30/60/120/250日后)</h3><div id="peak_ret_chart" class="cht"></div></div>
<div class="cb"><h3>高点回落 · 各档位天数分布</h3><div id="peak_dist_chart" class="cht-s"></div></div>

<!-- 第二维明细表 -->
<div class="cb" style="margin-bottom:16px">
<h3>高点回落回测明细表 (黄色高亮=当前档位)</h3>
<div class="hist-scroll">
<table>
<thead><tr>
<th rowspan="2">回落档位</th>
<th rowspan="2">天数</th>
<th rowspan="2">占比</th>
<th colspan="2">30日后</th>
<th colspan="2">60日后</th>
<th colspan="2">120日后</th>
<th colspan="2">250日后</th>
</tr>
<tr>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
<th style="background:#334155">胜率</th><th style="background:#334155">收益</th>
</tr></thead>
<tbody>
{peak_rows}
</tbody></table>
</div></div>

<div class="ft">红利低波100(930955) 多维买卖策略看板 | {result_ma["total_klines"]}根日K线 | {now_str} 生成</div>
</div></div>

<script>
(function(){{
  var MAX_WAIT = 50; // 5s
  var waited = 0;
  function tryInit(){{
    waited++;
    if(typeof echarts === 'undefined'){{
      if(waited < MAX_WAIT){{setTimeout(tryInit,100);return;}}
      showErr('ECharts 加载失败，请刷新页面重试');
      return;
    }}
    initAll();
  }}

  function showErr(m){{
    var cs=document.querySelectorAll('.cht,.cht-s,.cht-xl');
    cs.forEach(function(c){{c.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:14px;border:1px dashed #ef4444;border-radius:8px;background:#fef2f2;min-height:200px">'+m+'</div>';}});
  }}

  function initAll(){{
    try{{
      var wr=echarts.init(document.getElementById('wr_chart'));
      wr.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},legend:{{data:['30日胜率','60日胜率','120日胜率','250日胜率'],top:0,textStyle:{{color:'#475569'}}}},grid:{{left:'8%',right:'5%',top:'14%',bottom:'15%'}},xAxis:{{type:'category',data:{chart_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'胜率%',min:0,max:100,axisLabel:{{color:'#64748b'}}}},series:[{{name:'30日胜率',type:'bar',data:{chart_wr30},itemStyle:{{color:'#dc2626'}},barMaxWidth:14}},{{name:'60日胜率',type:'bar',data:{chart_wr60},itemStyle:{{color:'#f59e0b'}},barMaxWidth:14}},{{name:'120日胜率',type:'bar',data:{chart_wr120},itemStyle:{{color:'#3b82f6'}},barMaxWidth:14}},{{name:'250日胜率',type:'bar',data:{chart_wr250},itemStyle:{{color:'#8b5cf6'}},barMaxWidth:14}}]}});
      window.__wr=wr;
    }}catch(e){{console.error(e)}}
    try{{
      var rc=echarts.init(document.getElementById('ret_chart'));
      rc.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},legend:{{data:['30日平均收益','60日平均收益','120日平均收益','250日平均收益'],top:0,textStyle:{{color:'#475569'}}}},grid:{{left:'8%',right:'5%',top:'14%',bottom:'15%'}},xAxis:{{type:'category',data:{chart_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'收益%',axisLabel:{{color:'#64748b'}}}},series:[{{name:'30日平均收益',type:'line',data:{chart_ar30},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#dc2626'}},itemStyle:{{color:'#dc2626'}}}},{{name:'60日平均收益',type:'line',data:{chart_ar60},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#f59e0b'}},itemStyle:{{color:'#f59e0b'}}}},{{name:'120日平均收益',type:'line',data:{chart_ar120},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#3b82f6'}},itemStyle:{{color:'#3b82f6'}}}},{{name:'250日平均收益',type:'line',data:{chart_ar250},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#8b5cf6'}},itemStyle:{{color:'#8b5cf6'}}}}]}});
      window.__rc=rc;
    }}catch(e){{console.error(e)}}
    try{{
      var dc=echarts.init(document.getElementById('dist_chart'));
      dc.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}}}},grid:{{left:'8%',right:'5%',top:'8%',bottom:'15%'}},xAxis:{{type:'category',data:{chart_dist_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'天数',axisLabel:{{color:'#64748b'}}}},series:[{{type:'bar',data:{chart_dist_data},barMaxWidth:28,itemStyle:{{color:function(p){{return {labove_json}[p.dataIndex]?'#dc2626':'#16a34a'}}}}}}]}});
      window.__dc=dc;
    }}catch(e){{console.error(e)}}
    try{{
      var klDates = {kline_dates_json};
      var klOhlc = {kline_ohlc_json};
      var klMa250 = {kline_ma250_json};
      var klVol = {kline_volume_json};
      var klData = [];
      var ma250Data = [];
      for(var i=0;i<klDates.length;i++){{
        klData.push([klOhlc[i][0], klOhlc[i][1], klOhlc[i][2], klOhlc[i][3]]);
        ma250Data.push(klMa250[i] !== null ? [klDates[i], klMa250[i]] : null);
      }}
      var kl=echarts.init(document.getElementById('kline_chart'));
      kl.setOption({{
        backgroundColor:'transparent',
        tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},
        legend:{{data:['K线','MA250'],top:0,textStyle:{{color:'#475569'}}}},
        grid:[{{left:'8%',right:'2%',top:'14%',height:'68%'}},{{left:'8%',right:'2%',top:'86%',height:'10%'}}],
        xAxis:[
          {{type:'category',data:klDates,axisLabel:{{fontSize:10,color:'#64748b'}},gridIndex:0}},
          {{type:'category',data:klDates,axisLabel:{{show:false}},gridIndex:1}}
        ],
        yAxis:[
          {{type:'value',name:'价格',scale:true,axisLabel:{{color:'#64748b'}},splitArea:{{show:true,areaStyle:{{color:['rgba(200,200,200,0.06)','rgba(200,200,200,0.02)']}}}},gridIndex:0}},
          {{type:'value',name:'成交量',axisLabel:{{color:'#64748b'}},gridIndex:1}}
        ],
        dataZoom:[
          {{type:'inside',xAxisIndex:[0,1],start:70,end:100}},
          {{type:'slider',xAxisIndex:[0,1],start:70,end:100,height:24,bottom:4}}
        ],
        series:[
          {{name:'K线',type:'candlestick',data:klData,
            itemStyle:{{color:'#dc2626',color0:'#16a34a',borderColor:'#dc2626',borderColor0:'#16a34a'}},
            markLine:{{silent:true,symbol:'none',label:{{position:'end',formatter:'MA250: {{c}}',fontSize:10}},
              data:[{{yAxis:klMa250[klMa250.length-1],name:'当前MA250',lineStyle:{{color:'#f59e0b',type:'dashed',width:1}}}}]
            }}
          }},
          {{name:'MA250',type:'line',data:ma250Data.filter(function(d){{return d!==null;}}),smooth:true,symbol:'none',
            lineStyle:{{color:'#f59e0b',width:2}},xAxisIndex:0,yAxisIndex:0
          }},
          {{name:'成交量',type:'bar',data:klVol.map(function(v,i){{return [klDates[i],v];}}),xAxisIndex:1,yAxisIndex:1,
            itemStyle:{{color:function(p){{var idx=p.dataIndex;return idx<klOhlc.length&&klOhlc[idx][1]>=klOhlc[idx][0]?'#dc2626':'#16a34a'}}}}}}
        ]
      }});
      window.__kl=kl;
    }}catch(e){{console.error(e)}}
    try{{
      var pwr=echarts.init(document.getElementById('peak_wr_chart'));
      pwr.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},legend:{{data:['30日胜率','60日胜率','120日胜率','250日胜率'],top:0,textStyle:{{color:'#475569'}}}},grid:{{left:'8%',right:'5%',top:'14%',bottom:'15%'}},xAxis:{{type:'category',data:{peak_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'胜率%',min:0,max:100,axisLabel:{{color:'#64748b'}}}},series:[{{name:'30日胜率',type:'bar',data:{peak_wr30},itemStyle:{{color:'#dc2626'}},barMaxWidth:14}},{{name:'60日胜率',type:'bar',data:{peak_wr60},itemStyle:{{color:'#f59e0b'}},barMaxWidth:14}},{{name:'120日胜率',type:'bar',data:{peak_wr120},itemStyle:{{color:'#3b82f6'}},barMaxWidth:14}},{{name:'250日胜率',type:'bar',data:{peak_wr250},itemStyle:{{color:'#8b5cf6'}},barMaxWidth:14}}]}});
      window.__pwr=pwr;
    }}catch(e){{console.error(e)}}
    try{{
      var prc=echarts.init(document.getElementById('peak_ret_chart'));
      prc.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'cross'}}}},legend:{{data:['30日平均收益','60日平均收益','120日平均收益','250日平均收益'],top:0,textStyle:{{color:'#475569'}}}},grid:{{left:'8%',right:'5%',top:'14%',bottom:'15%'}},xAxis:{{type:'category',data:{peak_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'收益%',axisLabel:{{color:'#64748b'}}}},series:[{{name:'30日平均收益',type:'line',data:{peak_ar30},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#dc2626'}},itemStyle:{{color:'#dc2626'}}}},{{name:'60日平均收益',type:'line',data:{peak_ar60},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#f59e0b'}},itemStyle:{{color:'#f59e0b'}}}},{{name:'120日平均收益',type:'line',data:{peak_ar120},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#3b82f6'}},itemStyle:{{color:'#3b82f6'}}}},{{name:'250日平均收益',type:'line',data:{peak_ar250},smooth:true,symbol:'circle',symbolSize:5,lineStyle:{{width:2,color:'#8b5cf6'}},itemStyle:{{color:'#8b5cf6'}}}}]}});
      window.__prc=prc;
    }}catch(e){{console.error(e)}}
    try{{
      var pdc=echarts.init(document.getElementById('peak_dist_chart'));
      pdc.setOption({{backgroundColor:'transparent',tooltip:{{trigger:'axis',axisPointer:{{type:'shadow'}}}},grid:{{left:'8%',right:'5%',top:'8%',bottom:'15%'}},xAxis:{{type:'category',data:{peak_labels},axisLabel:{{fontSize:9,rotate:45,color:'#64748b'}}}},yAxis:{{type:'value',name:'天数',axisLabel:{{color:'#64748b'}}}},series:[{{type:'bar',data:{peak_counts},barMaxWidth:28,itemStyle:{{color:function(p){{return p.dataIndex>=5?'#dc2626':'#16a34a'}}}}}}]}});
      window.__pdc=pdc;
    }}catch(e){{console.error(e)}}
    window.addEventListener('resize',function(){{try{{window.__wr.resize()}}catch(e){{}}try{{window.__rc.resize()}}catch(e){{}}try{{window.__dc.resize()}}catch(e){{}}try{{window.__kl.resize()}}catch(e){{}}try{{window.__pwr.resize()}}catch(e){{}}try{{window.__prc.resize()}}catch(e){{}}try{{window.__pdc.resize()}}catch(e){{}}}});
  }}
  if(document.readyState==='complete'||document.readyState==='interactive'){{tryInit();}}else{{document.addEventListener('DOMContentLoaded',tryInit);}}
}})();
</script>
</body></html>'''
    # 内联echarts库（避免CDN/相对路径404）
    echarts_path = os.path.join(BASE, "echarts.min.js")
    with open(echarts_path, "r", encoding="utf-8") as f:
        echarts_js = f.read()
    html = html.replace("[[ECHARTS_INLINE]]", echarts_js)
    
    return html


def main():
    print("=" * 66)
    print("红利低波100(930955) MA250偏离值回测策略")
    print("=" * 66)
    
    # 加载数据
    klines = load_klines()
    closes = [k["close"] for k in klines]
    print(f"\n[1] 数据: {len(klines)}根 ({klines[0]['date']} ~ {klines[-1]['date']})")
    
    # 执行回测
    print(f"\n[2] 执行MA250偏离值回测...")
    result = run_backtest(klines)
    
    print(f"  有效回测天数: {result['total_valid']} (MA250以上{result['above_count']}天 / 以下{result['below_count']}天)")
    print(f"  档位数: {len(result['buckets'])}")
    print(f"\n  当前状态:")
    print(f"    日期: {result['current_date']}")
    print(f"    收盘价: {result['current_close']}")
    print(f"    MA250: {result['current_ma250']}")
    print(f"    偏离值: {result['current_deviation']:+.2f}%")
    print(f"    所在档位: {result['current_bucket']}")
    
    # 打印各档位回测结果
    print(f"\n[3] 各档位回测结果:")
    print(f"  {'档位':>10} | {'天数':>4} | {'占比':>5} | {'30日胜率':>7} {'30日收益':>8} | {'60日胜率':>7} {'60日收益':>8} | {'120日胜率':>8} {'120日收益':>9} | {'250日胜率':>8} {'250日收益':>9}")
    print(f"  {'-'*120}")
    
    for entry in sorted(result["buckets"], key=lambda x: x["bucket_idx"]):
        label = entry["label"]
        count = entry["count"]
        pct = entry["count_pct"]
        
        wr30 = f"{entry['stats'][30]['win_rate']}%" if entry['stats'][30]['win_rate'] else "N/A"
        ar30 = f"{entry['stats'][30]['avg_return']:+.2f}%" if entry['stats'][30]['avg_return'] is not None else "N/A"
        wr60 = f"{entry['stats'][60]['win_rate']}%" if entry['stats'][60]['win_rate'] else "N/A"
        ar60 = f"{entry['stats'][60]['avg_return']:+.2f}%" if entry['stats'][60]['avg_return'] is not None else "N/A"
        wr120 = f"{entry['stats'][120]['win_rate']}%" if entry['stats'][120]['win_rate'] else "N/A"
        ar120 = f"{entry['stats'][120]['avg_return']:+.2f}%" if entry['stats'][120]['avg_return'] is not None else "N/A"
        wr250 = f"{entry['stats'][250]['win_rate']}%" if entry['stats'][250]['win_rate'] else "N/A"
        ar250 = f"{entry['stats'][250]['avg_return']:+.2f}%" if entry['stats'][250]['avg_return'] is not None else "N/A"
        
        marker = " <<<" if label == result["current_bucket"] else ""
        print(f"  {label:>10} | {count:>4} | {pct:>4.1f}% | {wr30:>7} {ar30:>8} | {wr60:>7} {ar60:>8} | {wr120:>8} {ar120:>9} | {wr250:>8} {ar250:>9}{marker}")
    
    # 第二维: 高点回落回测
    print(f"\n[4] 执行高点回落回测...")
    result_peak = run_peak_backtest(klines)
    print(f"  峰值: {result_peak['current_peak']:.2f}")
    print(f"  当前回落值: {result_peak['current_pullback']:+.2f}%")
    print(f"  所在档位: {result_peak['current_bucket']}")
    print(f"  档位数: {len(result_peak['buckets'])}")
    print(f"  峰顶天数(0%~1%): {result_peak['at_peak_count']}天 ({result_peak['at_peak_pct']}%)")
    print(f"  深回落(>5%): {result_peak['deep_pullback_count']}天 ({result_peak['deep_pct']}%)")
    
    print(f"\n  各档位回测结果:")
    print(f"  {'档位':>10} | {'天数':>4} | {'占比':>5} | {'30日胜率':>7} {'30日收益':>8} | {'60日胜率':>7} {'60日收益':>8} | {'120日胜率':>8} {'120日收益':>9} | {'250日胜率':>8} {'250日收益':>9}")
    print(f"  {'-'*120}")
    for entry in sorted(result_peak["buckets"], key=lambda x: x["bucket_idx"]):
        label = entry["label"]
        count = entry["count"]
        pct = entry["count_pct"]
        wr30 = f"{entry['stats'][30]['win_rate']}%" if entry['stats'][30]['win_rate'] else "N/A"
        ar30 = f"{entry['stats'][30]['avg_return']:+.2f}%" if entry['stats'][30]['avg_return'] is not None else "N/A"
        wr60 = f"{entry['stats'][60]['win_rate']}%" if entry['stats'][60]['win_rate'] else "N/A"
        ar60 = f"{entry['stats'][60]['avg_return']:+.2f}%" if entry['stats'][60]['avg_return'] is not None else "N/A"
        wr120 = f"{entry['stats'][120]['win_rate']}%" if entry['stats'][120]['win_rate'] else "N/A"
        ar120 = f"{entry['stats'][120]['avg_return']:+.2f}%" if entry['stats'][120]['avg_return'] is not None else "N/A"
        wr250 = f"{entry['stats'][250]['win_rate']}%" if entry['stats'][250]['win_rate'] else "N/A"
        ar250 = f"{entry['stats'][250]['avg_return']:+.2f}%" if entry['stats'][250]['avg_return'] is not None else "N/A"
        marker = " <<<" if label == result_peak["current_bucket"] else ""
        print(f"  {label:>10} | {count:>4} | {pct:>4.1f}% | {wr30:>7} {ar30:>8} | {wr60:>7} {ar60:>8} | {wr120:>8} {ar120:>9} | {wr250:>8} {ar250:>9}{marker}")

    # 第三维: 股息率回测
    print(f"\n[5] 获取股息率数据并回测...")
    div_dict = fetch_div_yield()
    result_div = run_dividend_backtest(klines, div_dict)
    print(f"  当前股息率: {result_div['current_div_yield']:.2f}%")
    print(f"  所在档位: {result_div['current_bucket']}")
    print(f"  有效天数: {result_div['total_valid']}")
    print(f"  高股息(≥5%): {result_div['high_div_count']}天 ({result_div['high_div_pct']}%)")
    print(f"  低股息(<4%): {result_div['low_div_count']}天 ({result_div['low_div_pct']}%)")

    # 生成HTML
    print(f"\n[6] 生成HTML看板...")
    html = generate_html(result, result_peak, result_div)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ 已保存: {OUTPUT_HTML}")
    
    print(f"\n{'='*66}")
    print(f"  第一维 MA250 偏离值: {result['current_deviation']:+.2f}% (档位: {result['current_bucket']})")
    print(f"  第二维 高点回落值:   {result_peak['current_pullback']:+.2f}% (档位: {result_peak['current_bucket']})")
    print(f"  第三维 股息率:       {result_div['current_div_yield']:.2f}% (档位: {result_div['current_bucket']})")
    print(f"{'='*66}")


if __name__ == "__main__":
    main()
