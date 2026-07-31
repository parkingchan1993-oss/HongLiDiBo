#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回答用户三个问题:
1. 40日收益差 + 股债利差 的 30/60/120/250日多窗口回测
2. 股息率估算精度验证 (估算值 vs AKShare真实值)
3. 四维策略 vs Buy & Hold 完整对比回测
"""
import json, os, math
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
HOLD_PERIODS = [30, 60, 120, 250]

# ============================================================
# 加载数据 (复用 four_dim_backtest.py 的逻辑)
# ============================================================
with open(os.path.join(BASE, "history_klines.json"), "r", encoding="utf-8") as f:
    klines = json.load(f)
for k in klines:
    for key in ("open", "high", "low", "close", "volume"):
        k[key] = float(k[key])
closes = [k["close"] for k in klines]
dates = [k["date"] for k in klines]
n = len(klines)

# MA250偏离
ma250_dev = [None] * n
for i in range(249, n):
    ma = sum(closes[i-249:i+1]) / 250
    ma250_dev[i] = (closes[i] - ma) / ma * 100

# 周RSI
weekly = []
cur_w = None
for k in klines:
    d = datetime.strptime(k["date"], "%Y%m%d")
    iso = d.isocalendar()
    if cur_w is None or iso[:2] != cur_w[:2]:
        if cur_w is not None:
            weekly.append(wb)
        cur_w = iso
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
wk_to_day = {}
di = 0
for wi, w in enumerate(weekly):
    while di < n and dates[di] <= w["date"]:
        di += 1
    wk_to_day[wi] = di - 1

daily_rsi = [None] * n
for wi in range(len(weekly)):
    if wr[wi] is not None:
        daily_rsi[wk_to_day[wi]] = wr[wi]
last_rsi = None
for i in range(n):
    if daily_rsi[i] is not None:
        last_rsi = daily_rsi[i]
    daily_rsi[i] = last_rsi

# 40日收益差 (从JSON读取已有结果)
with open(os.path.join(BASE, "four_dim_backtest.json"), "r") as f:
    prev_data = json.load(f)

# 重新计算40日收益差 (需要benchmark数据)
import glob
def parse_tdx_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    for tag in ['{"Setcode"', '{\n  "Setcode"']:
        idx = text.find(tag)
        if idx != -1:
            break
    if idx == -1:
        idx = text.index("{")
    json_text = text[idx:]
    try:
        data = json.loads(json_text)
    except:
        last = json_text.rfind("}")
        data = json.loads(json_text[:last+1])
    rows = data.get("Rows", data.get("ListItem", []))
    result = []
    for r in rows:
        result.append({"date": r["Data"], "close": float(r["Close"])})
    return result

tdx_files = sorted(glob.glob(os.path.join(
    os.path.expanduser("~"), ".workbuddy", "projects", "*", "*",
    "tool-results", "mcp-connector-proxy-tdx-connector_tdx_kline-*.txt"
)))
benchmark_raw = []
for f in tdx_files:
    try:
        with open(f, "r", encoding="utf-8") as fh:
            text = fh.read()
        if "000985" in text and "中证全指" in text:
            benchmark_raw.extend(parse_tdx_file(f))
    except:
        pass

seen = set()
benchmark = []
for b in benchmark_raw:
    if b["date"] not in seen:
        seen.add(b["date"])
        benchmark.append(b)
benchmark.sort(key=lambda x: x["date"])
bench_map = {b["date"]: b["close"] for b in benchmark}

ret_spread = [None] * n
for i in range(40, n):
    d_now = dates[i]
    d_40ago = dates[i - 40]
    if d_now in bench_map and d_40ago in bench_map:
        ret_930 = (closes[i] - closes[i-40]) / closes[i-40] * 100
        ret_bench = (bench_map[d_now] - bench_map[d_40ago]) / bench_map[d_40ago] * 100
        ret_spread[i] = ret_930 - ret_bench

# 股债利差
import requests
url = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
params = {"indexCode": "930955", "startDate": "20200101", "endDate": "20260730"}
r = requests.get(url, params=params, timeout=15)
csi_rows = r.json()["data"]
try:
    import akshare as ak
    df_real = ak.stock_zh_index_value_csindex("930955")
    latest = df_real.iloc[0]
    payout_ratio = float(latest["股息率2"]) * float(latest["市盈率1"]) / 100.0
except:
    payout_ratio = 0.4076

div_map = {}
for row in csi_rows:
    pe = row.get("peg")
    if pe and pe > 0:
        div_map[row["tradeDate"]] = round(payout_ratio / pe * 100, 4)

# CN10Y
cn10y_map = {}
try:
    df_bond = ak.bond_zh_us_rate()
    for _, row in df_bond.iterrows():
        d = str(row["日期"]).replace("-", "")
        y = row.get("中国国债收益率10年")
        if y and not (isinstance(y, float) and math.isnan(y)):
            cn10y_map[d] = float(y)
except:
    pass

def get_val(date_str, vmap, default=0):
    if date_str in vmap:
        return vmap[date_str]
    if not vmap:
        return default
    keys = sorted(vmap.keys())
    lo, hi = 0, len(keys) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if keys[mid] < date_str:
            lo = mid + 1
        else:
            hi = lo
    if lo > 0:
        prev = keys[lo - 1]
        nxt = keys[lo]
        if abs(int(date_str) - int(prev)) < abs(int(nxt) - int(date_str)):
            return vmap[prev]
    return vmap[keys[lo]]

erp = [None] * n
for i in range(n):
    dy = get_val(dates[i], div_map, 4.5)
    cn10 = get_val(dates[i], cn10y_map, 2.5)
    erp[i] = dy - cn10

# ============================================================
# 问题1: 多窗口分档回测 (30/60/120/250日)
# ============================================================
print("=" * 80)
print("问题1: 40日收益差 + 股债利差 多窗口回测")
print("=" * 80)

def multi_horizon_backtest(signal_vals, bucket_fn, name):
    buckets = defaultdict(lambda: {"count": 0,
                                    "wins": {p: 0 for p in HOLD_PERIODS},
                                    "valid": {p: 0 for p in HOLD_PERIODS},
                                    "rets": {p: [] for p in HOLD_PERIODS}})
    for i in range(n):
        sig = signal_vals[i]
        if sig is None:
            continue
        bidx = bucket_fn(sig)
        buckets[bidx]["count"] += 1
        for p in HOLD_PERIODS:
            fi = i + p
            if fi < n:
                ret = (closes[fi] - closes[i]) / closes[i] * 100
                buckets[bidx]["rets"][p].append(ret)
                buckets[bidx]["valid"][p] += 1
                if ret > 0:
                    buckets[bidx]["wins"][p] += 1
    return dict(buckets)

def print_multi_horizon(buckets, bucket_size, name, sort_reverse=False):
    keys = sorted(buckets.keys(), reverse=sort_reverse)
    total = sum(bd["count"] for bd in buckets.values())
    print(f"\n--- {name} (多窗口) ---")
    print(f"{'档位':>12} | {'n':>4} | {'30日胜率':>7} {'30日均收':>8} | {'60日胜率':>7} {'60日均收':>8} | {'120日胜率':>8} {'120日均收':>9} | {'250日胜率':>8} {'250日均收':>9}")
    print("-" * 120)
    for bidx in keys:
        b = buckets[bidx]
        if b["count"] == 0:
            continue
        if bucket_size == 2:
            label = f"{bidx*2}%~{bidx*2+2}%"
        else:
            label = f"{bidx*0.5:.1f}%~{bidx*0.5+0.5:.1f}%"
        parts = [f"{label:>12}", f"{b['count']:>4}"]
        for p in HOLD_PERIODS:
            v = b["valid"][p]
            if v == 0:
                parts += ["N/A", "N/A"]
            else:
                wr = b["wins"][p] / v * 100
                avg = sum(b["rets"][p]) / len(b["rets"][p])
                parts.append(f"{wr:>6.1f}%")
                parts.append(f"{avg:>+7.2f}%")
        print(f"{parts[0]:>12} | {parts[1]:>4} | {parts[2]:>7} {parts[3]:>8} | {parts[4]:>7} {parts[5]:>8} | {parts[6]:>8} {parts[7]:>9} | {parts[8]:>8} {parts[9]:>9}")

# 40日收益差: 按2%分档
bt_sp = multi_horizon_backtest(ret_spread, lambda s: int(math.floor(s / 2)), "40日收益差")
print_multi_horizon(bt_sp, 2, "40日收益差")

# 股债利差: 按0.5%分档
bt_erp = multi_horizon_backtest(erp, lambda s: int(math.floor(s / 0.5)), "股债利差")
print_multi_horizon(bt_erp, 0.5, "股债利差")

# ============================================================
# 问题2: 股息率估算精度验证
# ============================================================
print("\n" + "=" * 80)
print("问题2: 股息率估算精度验证")
print("=" * 80)

# 获取AKShare最近20天真实股息率
try:
    df_real = ak.stock_zh_index_value_csindex("930955")
    real_data = []
    for _, row in df_real.iterrows():
        d = str(row["日期"]).replace("-", "")
        real_data.append({
            "date": d,
            "pe1": float(row["市盈率1"]),
            "dy2_real": float(row["股息率2"]),
        })
    
    # 对比估算值 vs 真实值
    print(f"AKShare真实数据: {len(real_data)}天")
    print(f"{'日期':>10} | {'PE真实':>8} | {'股息率真实':>10} | {'PE估算用':>8} | {'股息率估算':>10} | {'误差':>6}")
    print("-" * 75)
    errors = []
    for rd in real_data:
        d = rd["date"]
        pe_real = rd["pe1"]
        dy_real = rd["dy2_real"]
        # 用同一天的CSI PE估算
        dy_est = div_map.get(d, None)
        if dy_est is None:
            # 找最近的CSI日期
            dy_est = get_val(d, div_map, None)
        if dy_est is not None:
            err = dy_est - dy_real
            errors.append(err)
            print(f"{d:>10} | {pe_real:>8.2f} | {dy_real:>9.2f}% | {'CSI':>8} | {dy_est:>9.2f}% | {err:>+6.2f}%")
    
    if errors:
        import statistics
        print(f"\n估算误差统计:")
        print(f"  平均误差: {statistics.mean(errors):+.4f}%")
        print(f"  误差标准差: {statistics.stdev(errors):.4f}%")
        print(f"  最大正误差: {max(errors):+.4f}%")
        print(f"  最大负误差: {min(errors):+.4f}%")
        print(f"  误差范围: [{min(errors):+.2f}%, {max(errors):+.2f}%]")
        print(f"  结论: {'估算精度良好, 误差在±0.15%以内' if max(abs(e) for e in errors) < 0.15 else '估算存在一定偏差, 需注意'}")
except Exception as e:
    print(f"验证失败: {e}")

# TDX是否有股息率
print("\nTDX股息率数据检查:")
print("  之前已验证: tdx_quotes(hasCwInfo=1)对指数仅返回LongHisHigh/LongHisLow, 无PE/PB/股息率")
print("  tdx_indicator_select对指数返回空 — TDX不支持指数级别的股息率历史数据")
print("  结论: 指数股息率只能通过CSI API(PE) + AKShare(校准)估算, 或AKShare直接获取最近20天")

# ============================================================
# 问题3: 四维策略 vs Buy & Hold 完整对比
# ============================================================
print("\n" + "=" * 80)
print("问题3: 四维策略 vs Buy & Hold 对比回测")
print("=" * 80)

# 信号函数
def ma_sig(dev):
    if dev is None: return None
    if dev <= -3: return 1   # BUY
    if dev > 5: return -1    # SELL
    return 0                  # HOLD

def rsi_sig(r):
    if r is None: return None
    if r < 40: return 1
    if r > 80: return -1
    if r > 65: return -0.5   # REDUCE
    return 0

def sp_sig(s):
    if s is None: return None
    if s < -5: return 1
    if s > 5: return -1
    return 0

def erp_sig(e):
    if e is None: return None
    if e >= 3.0: return 1
    if e < 2.0: return -1
    return 0

# 策略回测: 从第250天开始(MA250有效), 初始资金100
def backtest_strategy():
    cash = 100.0  # 初始100元
    position = 0.0  # 持仓份数
    portfolio_values = []
    positions = []
    trades = 0
    
    # 四维同时有效的起始点
    start = 250
    # 找到四维同时有效的第一天
    while start < n:
        if all(s is not None for s in [ma250_dev[start], daily_rsi[start], ret_spread[start], erp[start]]):
            break
        start += 1
    
    for i in range(start, n):
        if all(s is not None for s in [ma250_dev[i], daily_rsi[i], ret_spread[i], erp[i]]):
            # 计算信号
            signals = [ma_sig(ma250_dev[i]), rsi_sig(daily_rsi[i]), sp_sig(ret_spread[i]), erp_sig(erp[i])]
            buy_count = sum(1 for s in signals if s == 1)
            sell_count = sum(1 for s in signals if s < 0)
            
            # 目标仓位
            if buy_count >= 4:
                target = 1.0
            elif buy_count >= 3:
                target = 0.9
            elif buy_count >= 2:
                target = 0.6
            elif sell_count >= 3:
                target = 0.2
            elif sell_count >= 2:
                target = 0.3
            else:
                target = 0.5
            
            # RSI止盈覆盖
            rsi_val = daily_rsi[i]
            if rsi_val > 80:
                target = min(target, 0.2)
            elif rsi_val > 70:
                target = min(target, 0.4)
            elif rsi_val > 65:
                target = min(target, 0.6)
            
            # 执行调仓
            total_value = cash + position * closes[i]
            target_value = total_value * target
            current_position_value = position * closes[i]
            
            if abs(target_value - current_position_value) > total_value * 0.02:  # 超过2%才调仓
                trades += 1
                position = target_value / closes[i]
                cash = total_value - target_value
        
        portfolio_values.append(cash + position * closes[i])
        positions.append(position * closes[i] / (cash + position * closes[i]) if (cash + position * closes[i]) > 0 else 0)
    
    return portfolio_values, positions, trades, start

# B&H回测 (同期)
def backtest_bh(start):
    values = []
    init_price = closes[start]
    for i in range(start, n):
        values.append(100.0 * closes[i] / init_price)
    return values

pf_vals, pf_pos, pf_trades, start_idx = backtest_strategy()
bh_vals = backtest_bh(start_idx)

# 计算指标
def calc_metrics(values):
    total_ret = (values[-1] / values[0] - 1) * 100
    # 年化
    days = len(values)
    years = days / 252
    ann_ret = ((values[-1] / values[0]) ** (1/years) - 1) * 100 if years > 0 else 0
    # 最大回撤
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
    # Sharpe (日收益率)
    rets = []
    for i in range(1, len(values)):
        rets.append(values[i] / values[i-1] - 1)
    if rets:
        avg_ret = sum(rets) / len(rets)
        std_ret = (sum((r - avg_ret)**2 for r in rets) / len(rets)) ** 0.5
        sharpe = avg_ret / std_ret * (252 ** 0.5) if std_ret > 0 else 0
    else:
        sharpe = 0
    # Calmar
    calmar = ann_ret / abs(max_dd * 100) if max_dd != 0 else 0
    return {
        "total_ret": round(total_ret, 2),
        "ann_ret": round(ann_ret, 2),
        "max_dd": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "calmar": round(calmar, 2),
    }

pf_metrics = calc_metrics(pf_vals)
bh_metrics = calc_metrics(bh_vals)

# 年度收益对比
years_data = defaultdict(lambda: {"pf": [], "bh": []})
for i, v in enumerate(pf_vals):
    d = dates[start_idx + i]
    y = d[:4]
    years_data[y]["pf"].append(v)
for i, v in enumerate(bh_vals):
    d = dates[start_idx + i]
    y = d[:4]
    years_data[y]["bh"].append(v)

print(f"\n回测起始: 第{start_idx}天 ({dates[start_idx]}), 共{len(pf_vals)}天")
print(f"交易次数: 策略{pf_trades}次 vs B&H 0次")
print()
print(f"{'指标':>14} | {'四维策略':>12} | {'Buy&Hold':>12} | {'差值':>12}")
print("-" * 60)
for key in ["total_ret", "ann_ret", "max_dd", "sharpe", "calmar"]:
    labels = {"total_ret": "总收益", "ann_ret": "年化收益", "max_dd": "最大回撤", "sharpe": "Sharpe", "calmar": "Calmar"}
    pv = pf_metrics[key]
    bv = bh_metrics[key]
    diff = pv - bv
    print(f"{labels[key]:>14} | {pv:>11.2f}% | {bv:>11.2f}% | {diff:>+11.2f}%")

print(f"\n年度收益对比:")
print(f"{'年份':>6} | {'策略':>10} | {'B&H':>10} | {'超额':>10}")
print("-" * 45)
for y in sorted(years_data.keys()):
    pf_yr = years_data[y]["pf"]
    bh_yr = years_data[y]["bh"]
    if len(pf_yr) > 1:
        pf_ret = (pf_yr[-1] / pf_yr[0] - 1) * 100
        bh_ret = (bh_yr[-1] / bh_yr[0] - 1) * 100
        print(f"{y:>6} | {pf_ret:>+9.2f}% | {bh_ret:>+9.2f}% | {pf_ret-bh_ret:>+9.2f}%")

# 平均仓位
avg_pos = sum(pf_pos) / len(pf_pos) * 100
print(f"\n策略平均仓位: {avg_pos:.1f}%")
print(f"策略vs B&H超额: {pf_metrics['total_ret'] - bh_metrics['total_ret']:+.2f}%")

# 保存结果
results = {
    "strategy_metrics": pf_metrics,
    "bh_metrics": bh_metrics,
    "trades": pf_trades,
    "avg_position": round(avg_pos, 1),
    "start_date": dates[start_idx],
    "total_days": len(pf_vals),
    "excess_return": round(pf_metrics["total_ret"] - bh_metrics["total_ret"], 2),
}
with open(os.path.join(BASE, "strategy_vs_bh.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: strategy_vs_bh.json")
