#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四维信号回测: MA250偏离 + 周RSI(14) + 40日收益差 + 股债利差
数据源: TDX(930955+000985) + AKShare(CN10Y) + CSI API(PE)
"""
import json, os, math, glob, sys
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
HOLD_PERIODS = [30, 60, 120, 250]

# ============================================================
# 1. 加载930955日K线
# ============================================================
with open(os.path.join(BASE, "history_klines.json"), "r", encoding="utf-8") as f:
    klines_930 = json.load(f)
for k in klines_930:
    for key in ("open", "high", "low", "close", "volume"):
        k[key] = float(k[key])
closes_930 = [k["close"] for k in klines_930]
dates_930 = [k["date"] for k in klines_930]
n_930 = len(klines_930)
print(f"[1] 930955: {n_930}根, {dates_930[0]} ~ {dates_930[-1]}")

# ============================================================
# 2. 解析TDX返回的000985中证全指数据
# ============================================================
def parse_tdx_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    # 找JSON块
    for tag in ['{"Setcode"', '{\n  "Setcode"', '{\n "Setcode"']:
        idx = text.find(tag)
        if idx != -1:
            break
    if idx == -1:
        # 尝试找第一个 {
        idx = text.index("{")
    json_text = text[idx:]
    # 修复可能的尾部内容
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        # 找最后一个 } 
        last_brace = json_text.rfind("}")
        data = json.loads(json_text[:last_brace+1])
    rows = data.get("Rows", data.get("ListItem", []))
    result = []
    for r in rows:
        result.append({
            "date": r["Data"],
            "close": float(r["Close"]),
        })
    return result

tdx_files = sorted(glob.glob(os.path.join(
    os.path.expanduser("~"), ".workbuddy", "projects", "*",
    "*", "tool-results", "mcp-connector-proxy-tdx-connector_tdx_kline-*.txt"
)))
# 只保留000985的文件
benchmark_files = []
for f in tdx_files:
    try:
        with open(f, "r", encoding="utf-8") as fh:
            text = fh.read()
        if "000985" in text and "中证全指" in text:
            benchmark_files.append(f)
    except:
        pass

benchmark_raw = []
for f in benchmark_files:
    benchmark_raw.extend(parse_tdx_file(f))

# 去重并排序
seen = set()
benchmark = []
for b in benchmark_raw:
    if b["date"] not in seen:
        seen.add(b["date"])
        benchmark.append(b)
benchmark.sort(key=lambda x: x["date"])
print(f"[2] 000985中证全指: {len(benchmark)}根, {benchmark[0]['date']} ~ {benchmark[-1]['date']}")

# 构建000985的日期→close映射
bench_close_map = {b["date"]: b["close"] for b in benchmark}

# ============================================================
# 3. 获取CN10Y国债收益率 (AKShare)
# ============================================================
print("[3] 获取CN10Y...")
cn10y_map = {}  # date -> yield
try:
    import akshare as ak
    df_bond = ak.bond_zh_us_rate()
    for _, row in df_bond.iterrows():
        d = str(row["日期"]).replace("-", "")
        if "中国国债收益率10年" in df_bond.columns:
            y = row["中国国债收益率10年"]
            if y and not (isinstance(y, float) and math.isnan(y)):
                cn10y_map[d] = float(y)
    print(f"  CN10Y: {len(cn10y_map)}天, {min(cn10y_map.keys())} ~ {max(cn10y_map.keys())}")
except Exception as e:
    print(f"  AKShare CN10Y失败: {e}, 使用默认值2.5%")
    cn10y_map = {}

def get_cn10y(date_str):
    """获取某日的CN10Y, 如果没有精确匹配则用最近的"""
    if date_str in cn10y_map:
        return cn10y_map[date_str]
    # 找最近的
    if not cn10y_map:
        return 2.5  # fallback
    dates_sorted = sorted(cn10y_map.keys())
    # 二分查找最近的
    lo, hi = 0, len(dates_sorted) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if dates_sorted[mid] < date_str:
            lo = mid + 1
        else:
            hi = mid
    if lo > 0:
        prev_d = dates_sorted[lo - 1]
        next_d = dates_sorted[lo]
        if abs(int(date_str) - int(prev_d)) < abs(int(next_d) - int(date_str)):
            return cn10y_map[prev_d]
    return cn10y_map[dates_sorted[lo]]

# ============================================================
# 4. 获取930955 PE数据 (CSI API) → 估算股息率
# ============================================================
print("[4] 获取930955 PE数据...")
div_yield_map = {}  # date -> div_yield
try:
    import requests
    url = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
    params = {"indexCode": "930955", "startDate": "20200101", "endDate": "20260730"}
    r = requests.get(url, params=params, timeout=15)
    csi_rows = r.json()["data"]
    
    # AKShare校准payout_ratio
    try:
        df_real = ak.stock_zh_index_value_csindex("930955")
        latest = df_real.iloc[0]
        pe1 = float(latest["市盈率1"])
        dy2 = float(latest["股息率2"])
        payout_ratio = dy2 * pe1 / 100.0
        print(f"  AKShare校准: PE1={pe1:.2f}, 股息率2={dy2:.2f}%, payout={payout_ratio:.4f}")
    except:
        payout_ratio = 0.4094
        print(f"  使用默认payout_ratio={payout_ratio}")
    
    for row in csi_rows:
        d = row["tradeDate"]
        pe = row.get("peg")
        if pe and pe > 0:
            div_yield_map[d] = round(payout_ratio / pe * 100, 4)
    print(f"  CSI PE: {len(div_yield_map)}天, 股息率范围 {min(div_yield_map.values()):.2f}% ~ {max(div_yield_map.values()):.2f}%")
except Exception as e:
    print(f"  CSI PE失败: {e}")

def get_div_yield(date_str):
    if date_str in div_yield_map:
        return div_yield_map[date_str]
    if not div_yield_map:
        return 4.5
    dates_sorted = sorted(div_yield_map.keys())
    lo, hi = 0, len(dates_sorted) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if dates_sorted[mid] < date_str:
            lo = mid + 1
        else:
            hi = lo
    if lo > 0:
        prev_d = dates_sorted[lo - 1]
        next_d = dates_sorted[lo]
        if abs(int(date_str) - int(prev_d)) < abs(int(next_d) - int(date_str)):
            return div_yield_map[prev_d]
    return div_yield_map[dates_sorted[lo]]

# ============================================================
# 5. 计算四个维度的每日信号值
# ============================================================
print("[5] 计算四维信号...")

# 维度1: MA250偏离值
ma250_dev = [None] * n_930
for i in range(249, n_930):
    ma = sum(closes_930[i-249:i+1]) / 250
    ma250_dev[i] = (closes_930[i] - ma) / ma * 100

# 维度2: 周RSI(14) — 映射到日线
weekly = []
cur_week = None
for k in klines_930:
    d = datetime.strptime(k["date"], "%Y%m%d")
    iso = d.isocalendar()
    if cur_week is None or iso[:2] != cur_week[:2]:
        if cur_week is not None:
            weekly.append(wb)
        cur_week = iso
        wb = {"date": k["date"], "close": k["close"]}
    else:
        wb["close"] = k["close"]
        wb["date"] = k["date"]
weekly.append(wb)
wc = [w["close"] for w in weekly]

def calc_rsi(closes, p=14):
    out = [None] * len(closes)
    for i in range(p, len(closes)):
        g, l = [], []
        for j in range(i - p, i):
            c = closes[j+1] - closes[j]
            g.append(max(c, 0))
            l.append(max(-c, 0))
        ag = sum(g) / p
        al = sum(l) / p
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

wr = calc_rsi(wc, 14)
# 周线→日线映射
wk_to_day = {}
di = 0
for wi, w in enumerate(weekly):
    while di < n_930 and dates_930[di] <= w["date"]:
        di += 1
    wk_to_day[wi] = di - 1

daily_rsi = [None] * n_930
for wi in range(len(weekly)):
    if wr[wi] is not None:
        di = wk_to_day[wi]
        daily_rsi[di] = wr[wi]
# forward fill RSI到日线
last_rsi = None
for i in range(n_930):
    if daily_rsi[i] is not None:
        last_rsi = daily_rsi[i]
    daily_rsi[i] = last_rsi

# 维度3: 40日收益差 = 930955的40日收益率 - 000985的40日收益率
ret_spread_40d = [None] * n_930
for i in range(40, n_930):
    d_now = dates_930[i]
    d_40ago = dates_930[i - 40]
    ret_930 = (closes_930[i] - closes_930[i - 40]) / closes_930[i - 40] * 100
    # 找000985在d_40ago和d_now的close
    if d_now in bench_close_map and d_40ago in bench_close_map:
        ret_bench = (bench_close_map[d_now] - bench_close_map[d_40ago]) / bench_close_map[d_40ago] * 100
        ret_spread_40d[i] = ret_930 - ret_bench

# 维度4: 股债利差 = 股息率 - CN10Y
erp = [None] * n_930
for i in range(n_930):
    dy = get_div_yield(dates_930[i])
    cn10 = get_cn10y(dates_930[i])
    erp[i] = dy - cn10

# ============================================================
# 6. 信号相关性分析
# ============================================================
print("[6] 信号相关性分析...")
signals = {"MA250偏离": ma250_dev, "周RSI": daily_rsi, "40日收益差": ret_spread_40d, "股债利差": erp}
sig_names = list(signals.keys())
corr_results = {}

# 收集所有维度都有值的点
valid_indices = []
for i in range(n_930):
    if all(signals[s][i] is not None for s in sig_names):
        valid_indices.append(i)

print(f"  四维同时有效: {len(valid_indices)}天")

for s1 in sig_names:
    for s2 in sig_names:
        if s1 < s2:
            xs = [signals[s1][i] for i in valid_indices]
            ys = [signals[s2][i] for i in valid_indices]
            mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
            cov = sum((x-mx)*(y-my) for x,y in zip(xs,ys))/len(xs)
            sx = (sum((x-mx)**2 for x in xs)/len(xs))**0.5
            sy = (sum((y-my)**2 for y in ys)/len(ys))**0.5
            r = cov/(sx*sy) if sx*sy > 0 else 0
            key = f"{s1} vs {s2}"
            corr_results[key] = round(r, 4)
            print(f"  {key}: r = {r:.4f}")

# ============================================================
# 7. 分档回测函数
# ============================================================
def backtest_signal(signal_values, bucket_size, bucket_fn, min_val=None, max_val=None):
    """通用分档回测"""
    buckets = defaultdict(lambda: {"count": 0, "wins": {p: 0 for p in HOLD_PERIODS},
                                    "valid": {p: 0 for p in HOLD_PERIODS},
                                    "rets": {p: [] for p in HOLD_PERIODS}})
    for i in range(n_930):
        sig = signal_values[i]
        if sig is None:
            continue
        bidx = bucket_fn(sig)
        buckets[bidx]["count"] += 1
        for p in HOLD_PERIODS:
            fi = i + p
            if fi < n_930:
                ret = (closes_930[fi] - closes_930[i]) / closes_930[i] * 100
                buckets[bidx]["rets"][p].append(ret)
                buckets[bidx]["valid"][p] += 1
                if ret > 0:
                    buckets[bidx]["wins"][p] += 1
    return dict(buckets)

def summarize_buckets(buckets, sorted_keys=None):
    """汇总各档统计"""
    results = []
    keys = sorted_keys if sorted_keys else sorted(buckets.keys())
    for bidx in keys:
        b = buckets[bidx]
        entry = {"bucket": bidx, "count": b["count"], "stats": {}}
        if b["count"] > 0:
            entry["count_pct"] = round(b["count"] / sum(bd["count"] for bd in buckets.values()) * 100, 1)
        for p in HOLD_PERIODS:
            v = b["valid"][p]
            w = b["wins"][p]
            rs = b["rets"][p]
            entry["stats"][p] = {
                "valid": v,
                "win_rate": round(w/v*100, 1) if v > 0 else None,
                "avg_return": round(sum(rs)/len(rs), 2) if rs else None,
                "worst": round(min(rs), 2) if rs else None,
            }
        results.append(entry)
    return results

# 回测维度3: 40日收益差 (按2%分档)
def bucket_spread(s):
    return int(math.floor(s / 2))  # 每2%一档

bt_spread = backtest_signal(ret_spread_40d, 2, bucket_spread)
spread_summary = summarize_buckets(bt_spread)
print(f"\n[7] 40日收益差回测: {len(bt_spread)}个档位")

# 回测维度4: 股债利差 (按0.5%分档)
def bucket_erp(s):
    return int(math.floor(s / 0.5))  # 每0.5%一档

bt_erp = backtest_signal(erp, 0.5, bucket_erp)
erp_summary = summarize_buckets(bt_erp)
print(f"[7] 股债利差回测: {len(bt_erp)}个档位")

# ============================================================
# 8. 组合信号回测: 四维共振
# ============================================================
print("\n[8] 组合信号回测...")

# 定义信号区间
def ma_signal(dev):
    if dev is None: return None
    if dev <= -3: return "BUY"
    if dev > 5: return "SELL"
    if dev > 3: return "REDUCE"
    return "HOLD"

def rsi_signal(r):
    if r is None: return None
    if r < 40: return "BUY"
    if r > 80: return "SELL"
    if r > 65: return "REDUCE"
    return "HOLD"

def spread_signal(s):
    if s is None: return None
    if s < -5: return "BUY"
    if s > 5: return "SELL"
    return "HOLD"

def erp_signal(e):
    if e is None: return None
    if e >= 3.0: return "BUY"  # 股债利差≥3% = 买入
    if e < 1.5: return "SELL"  # 股债利差<1.5% = 卖出
    return "HOLD"

# 统计各组合的250日前瞻收益
combo_stats = defaultdict(lambda: {"count": 0, "wins": 0, "rets": []})
for i in valid_indices:
    ma_s = ma_signal(ma250_dev[i])
    rsi_s = rsi_signal(daily_rsi[i])
    sp_s = spread_signal(ret_spread_40d[i])
    erp_s = erp_signal(erp[i])
    
    if any(s is None for s in [ma_s, rsi_s, sp_s, erp_s]):
        continue
    
    # 组合: 统计BUY信号数量
    buy_count = sum(1 for s in [ma_s, rsi_s, sp_s, erp_s] if s == "BUY")
    sell_count = sum(1 for s in [ma_s, rsi_s, sp_s, erp_s] if s == "SELL")
    
    if buy_count >= 3:
        combo_key = f"4维{buy_count}买"
    elif sell_count >= 3:
        combo_key = f"4维{sell_count}卖"
    elif buy_count >= 2:
        combo_key = "4维2买"
    elif sell_count >= 2:
        combo_key = "4维2卖"
    else:
        combo_key = "4维中性"
    
    fi = i + 250
    if fi < n_930:
        ret = (closes_930[fi] - closes_930[i]) / closes_930[i] * 100
        combo_stats[combo_key]["count"] += 1
        combo_stats[combo_key]["rets"].append(ret)
        if ret > 0:
            combo_stats[combo_key]["wins"] += 1

print(f"  组合信号类别: {len(combo_stats)}")
combo_results = {}
for key in sorted(combo_stats.keys()):
    s = combo_stats[key]
    if s["count"] > 0:
        wr = s["wins"] / s["count"] * 100
        avg = sum(s["rets"]) / len(s["rets"])
        worst = min(s["rets"])
        combo_results[key] = {
            "count": s["count"],
            "win_rate": round(wr, 1),
            "avg_return": round(avg, 2),
            "worst": round(worst, 2),
        }
        print(f"  {key}: n={s['count']}, 胜率={wr:.1f}%, 均收={avg:+.2f}%, 最差={worst:+.2f}%")

# ============================================================
# 9. 当前状态
# ============================================================
print("\n[9] 当前状态:")
cur_idx = n_930 - 1
print(f"  日期: {dates_930[cur_idx]}")
print(f"  收盘: {closes_930[cur_idx]:.2f}")
print(f"  MA250偏离: {ma250_dev[cur_idx]:+.2f}% → {ma_signal(ma250_dev[cur_idx])}")
print(f"  周RSI(14): {daily_rsi[cur_idx]:.1f} → {rsi_signal(daily_rsi[cur_idx])}")
print(f"  40日收益差: {ret_spread_40d[cur_idx]:+.2f}% → {spread_signal(ret_spread_40d[cur_idx])}")
print(f"  股债利差: {erp[cur_idx]:.2f}% → {erp_signal(erp[cur_idx])}")

cur_div = get_div_yield(dates_930[cur_idx])
cur_cn10 = get_cn10y(dates_930[cur_idx])
print(f"  (股息率={cur_div:.2f}%, CN10Y={cur_cn10:.2f}%)")

# ============================================================
# 10. 保存完整结果
# ============================================================
output = {
    "meta": {
        "klines_930": n_930,
        "date_range": f"{dates_930[0]}~{dates_930[-1]}",
        "benchmark": f"000985 {len(benchmark)}根 {benchmark[0]['date']}~{benchmark[-1]['date']}",
        "cn10y_days": len(cn10y_map),
        "div_yield_days": len(div_yield_map),
        "valid_4d_days": len(valid_indices),
        "payout_ratio": payout_ratio,
    },
    "correlations": corr_results,
    "spread_backtest": spread_summary,
    "erp_backtest": erp_summary,
    "combo_results": combo_results,
    "current": {
        "date": dates_930[cur_idx],
        "close": closes_930[cur_idx],
        "ma250_dev": round(ma250_dev[cur_idx], 2),
        "rsi": round(daily_rsi[cur_idx], 1),
        "spread_40d": round(ret_spread_40d[cur_idx], 2) if ret_spread_40d[cur_idx] else None,
        "erp": round(erp[cur_idx], 2),
        "div_yield": round(cur_div, 2),
        "cn10y": round(cur_cn10, 2),
    }
}

output_path = os.path.join(BASE, "four_dim_backtest.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n[10] 完整结果已保存: {output_path}")
