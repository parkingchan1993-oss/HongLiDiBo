import json, statistics, math

with open('history_klines.json', 'r') as f:
    data = json.load(f)

closes = [float(d['close']) for d in data]
highs = [float(d['high']) for d in data]
lows = [float(d['low']) for d in data]
volumes = [float(d['volume']) for d in data]
dates = [d['date'] for d in data]
n = len(closes)

# ========== MA250 ==========
ma250 = [None] * n
for i in range(249, n):
    ma250[i] = sum(closes[i-249:i+1]) / 250

dev = [None] * n
for i in range(n):
    if ma250[i]:
        dev[i] = (closes[i] - ma250[i]) / ma250[i] * 100

# MA250斜率方向
ma250_slope = [None] * n
for i in range(n):
    if ma250[i] and i > 0 and ma250[i-1]:
        ma250_slope[i] = (ma250[i] / ma250[i-1] - 1) * 100

# ========== 峰值回落 (用收盘价) ==========
running_max_close = []
mx = 0
for c in closes:
    mx = max(mx, c)
    running_max_close.append(mx)

pk_dd_close = [(running_max_close[i] - closes[i]) / running_max_close[i] * 100 for i in range(n)]

# ========== 相关性 ==========
valid_idx = [i for i in range(n) if dev[i] is not None]
devs_valid = [dev[i] for i in valid_idx]
pks_valid = [pk_dd_close[i] for i in valid_idx]
corr = statistics.correlation(devs_valid, pks_valid)

# ========== Buy & Hold ==========
bah_return = (closes[-1] / closes[0] - 1) * 100
bah_annual = ((closes[-1] / closes[0]) ** (250 / n) - 1) * 100
peak_so_far = closes[0]
max_dd_bah = 0
for c in closes:
    if c > peak_so_far:
        peak_so_far = c
    dd = (c - peak_so_far) / peak_so_far * 100
    if dd < max_dd_bah:
        max_dd_bah = dd

daily_rets_bah = [closes[i] / closes[i-1] - 1 for i in range(1, n)]
sharpe_bah = (statistics.mean(daily_rets_bah) / statistics.pstdev(daily_rets_bah)) * (250 ** 0.5) if statistics.pstdev(daily_rets_bah) > 0 else 0

# ========== 改进策略1: MA250偏离 + 趋势方向 ==========
# 规则: 偏离<=-3%且MA250上行 -> 满仓; 偏离<=-3%且MA250下行 -> 75%
#       偏离>+7% -> 空仓; 偏离+3%~+7% -> 25%; 其他 -> 50%
strat1_pos = [0.5] * n
strat1_values = [closes[0] * 0.5]
trades1 = 0
for i in range(1, n):
    if dev[i] is not None:
        slope_up = ma250_slope[i] is not None and ma250_slope[i] > 0
        if dev[i] <= -3:
            new_pos = 1.0 if slope_up else 0.75
        elif dev[i] >= 7:
            new_pos = 0.0
        elif dev[i] >= 3:
            new_pos = 0.25
        else:
            new_pos = 0.5
        if abs(new_pos - strat1_pos[i-1]) > 0.01:
            trades1 += 1
        strat1_pos[i] = new_pos
    else:
        strat1_pos[i] = strat1_pos[i-1]
    daily_ret = closes[i] / closes[i-1] - 1
    strat1_values.append(strat1_values[-1] * (1 + daily_ret * strat1_pos[i]))

strat1_return = (strat1_values[-1] / strat1_values[0] - 1) * 100
peak_s1 = strat1_values[0]
max_dd_s1 = 0
for v in strat1_values:
    if v > peak_s1:
        peak_s1 = v
    dd = (v - peak_s1) / peak_s1 * 100
    if dd < max_dd_s1:
        max_dd_s1 = dd
daily_rets_s1 = [strat1_values[i] / strat1_values[i-1] - 1 for i in range(1, n)]
sharpe_s1 = (statistics.mean(daily_rets_s1) / statistics.pstdev(daily_rets_s1)) * (250 ** 0.5) if statistics.pstdev(daily_rets_s1) > 0 else 0

# ========== 改进策略2: 动态定投 (DCA enhanced) ==========
# 规则: 每月固定投入, 偏离<-3%时加倍, 偏离>+7%时暂停
# 简化: 按月计算
months = {}
for i in range(n):
    ym = dates[i][:6]
    if ym not in months:
        months[ym] = i

dca_total_invested = 0.0
dca_total_shares = 0.0
base_amount = 10000  # 每月基础投入

for ym in sorted(months.keys()):
    i = months[ym]
    amount = base_amount
    if dev[i] is not None:
        if dev[i] <= -3:
            amount = base_amount * 2.0  # 加倍
        elif dev[i] <= -1:
            amount = base_amount * 1.5
        elif dev[i] >= 7:
            amount = 0  # 暂停
        elif dev[i] >= 5:
            amount = base_amount * 0.5

    if amount > 0:
        dca_total_invested += amount
        dca_total_shares += amount / closes[i]

dca_final_value = dca_total_shares * closes[-1]
dca_return = (dca_final_value / dca_total_invested - 1) * 100
dca_months = len(months)
dca_annual = ((dca_final_value / dca_total_invested) ** (12 / dca_months) - 1) * 100

# ========== 改进策略3: 分批建仓 + 止盈 ==========
# 规则: 偏离每-1%买入20%仓位(最多5次), 偏离>+5%开始卖出(每次卖20%)
strat3_pos = [0.0] * n
strat3_values = [closes[0]]
trades3 = 0
current_pos = 0.0
last_buy_dev = 0
last_sell_dev = 0

for i in range(1, n):
    if dev[i] is not None:
        # 买入逻辑: 分批
        if dev[i] <= -1 and current_pos < 1.0:
            buy_threshold = -1 - int((-last_buy_dev - 1) / 1) * 1 if last_buy_dev < 0 else -1
            if dev[i] <= last_buy_dev - 1 and current_pos < 1.0:
                buy_amount = min(0.2, 1.0 - current_pos)
                current_pos += buy_amount
                last_buy_dev = dev[i]
                trades3 += 1
        # 卖出逻辑: 分批止盈
        if dev[i] >= 5 and current_pos > 0:
            if dev[i] >= last_sell_dev + 1:
                sell_amount = min(0.2, current_pos)
                current_pos -= sell_amount
                last_sell_dev = dev[i]
                trades3 += 1
        # 重置
        if dev[i] > 0 and current_pos == 0:
            last_buy_dev = 0
        if dev[i] < 0 and current_pos == 1.0:
            last_sell_dev = 0

    strat3_pos[i] = current_pos
    daily_ret = closes[i] / closes[i-1] - 1
    strat3_values.append(strat3_values[-1] * (1 + daily_ret * strat3_pos[i]))

strat3_return = (strat3_values[-1] / strat3_values[0] - 1) * 100
peak_s3 = strat3_values[0]
max_dd_s3 = 0
for v in strat3_values:
    if v > peak_s3:
        peak_s3 = v
    dd = (v - peak_s3) / peak_s3 * 100
    if dd < max_dd_s3:
        max_dd_s3 = dd
daily_rets_s3 = [strat3_values[i] / strat1_values[i-1] - 1 for i in range(1, n)]
sharpe_s3 = (statistics.mean(daily_rets_s3) / statistics.pstdev(daily_rets_s3)) * (250 ** 0.5) if statistics.pstdev(daily_rets_s3) > 0 else 0

# ========== 年度对比 ==========
years_data = {}
for i in range(n):
    y = dates[i][:4]
    if y not in years_data:
        years_data[y] = {'start': i, 'end': i}
    years_data[y]['end'] = i

# ========== MA250偏离值百分位 ==========
dev_valid_sorted = sorted([d for d in dev if d is not None])
percentiles = {}
for p in [5, 10, 20, 30, 50, 70, 80, 90, 95]:
    idx = int(len(dev_valid_sorted) * p / 100)
    percentiles[p] = dev_valid_sorted[idx]

# ========== 各区间详细统计 ==========
zones_detail = {}
zone_defs = [
    ("deep_buy", -999, -5),
    ("buy", -5, -3),
    ("hold_low", -3, 0),
    ("hold_high", 0, 3),
    ("reduce", 3, 7),
    ("sell", 7, 999)
]

for name, lo, hi in zone_defs:
    indices = [i for i in range(n) if dev[i] is not None and lo <= dev[i] < hi]
    if not indices:
        continue
    detail = {'count': len(indices), 'pct': len(indices) / len(valid_idx) * 100}
    for period in [30, 60, 120, 250]:
        rets = []
        for i in indices:
            if i + period < n:
                r = (closes[i + period] / closes[i] - 1) * 100
                rets.append(r)
        if rets:
            detail[f'wr_{period}'] = sum(1 for r in rets if r > 0) / len(rets) * 100
            detail[f'avg_{period}'] = statistics.mean(rets)
            detail[f'med_{period}'] = statistics.median(rets)
            detail[f'min_{period}'] = min(rets)
            detail[f'max_{period}'] = max(rets)
            detail[f'n_{period}'] = len(rets)
        else:
            detail[f'wr_{period}'] = None
    zones_detail[name] = detail

# ========== 输出JSON供HTML使用 ==========
output = {
    'meta': {
        'n_bars': n,
        'date_start': dates[0],
        'date_end': dates[-1],
        'years': round(n / 250, 1),
    },
    'correlation': round(corr, 4),
    'bah': {
        'return': round(bah_return, 2),
        'annual': round(bah_annual, 2),
        'max_dd': round(max_dd_bah, 2),
        'sharpe': round(sharpe_bah, 3),
    },
    'strat1': {
        'name': 'MA250偏离+趋势方向',
        'return': round(strat1_return, 2),
        'max_dd': round(max_dd_s1, 2),
        'sharpe': round(sharpe_s1, 3),
        'trades': trades1,
    },
    'dca': {
        'name': '动态定投',
        'total_invested': round(dca_total_invested, 0),
        'final_value': round(dca_final_value, 0),
        'return': round(dca_return, 2),
        'annual': round(dca_annual, 2),
        'months': dca_months,
    },
    'strat3': {
        'name': '分批建仓+分批止盈',
        'return': round(strat3_return, 2),
        'max_dd': round(max_dd_s3, 2),
        'sharpe': round(sharpe_s3, 3),
        'trades': trades3,
    },
    'percentiles': {str(k): round(v, 2) for k, v in percentiles.items()},
    'zones': {},
    'years': {},
    'current': {
        'close': closes[-1],
        'ma250': ma250[-1],
        'dev': dev[-1],
        'pk_dd_close': pk_dd_close[-1],
        'max_close': max(closes),
        'max_close_date': dates[closes.index(max(closes))],
        'max_high': max(highs),
        'max_high_date': dates[highs.index(max(highs))],
    }
}

for name, d in zones_detail.items():
    output['zones'][name] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()}

for y, d in years_data.items():
    si, ei = d['start'], d['end']
    yr_bah = (closes[ei] / closes[si] - 1) * 100
    yr_s1 = (strat1_values[ei] / strat1_values[si] - 1) * 100
    dev_list = [dev[i] for i in range(si, ei+1) if dev[i] is not None]
    avg_dev = statistics.mean(dev_list) if dev_list else 0
    output['years'][y] = {
        'bah': round(yr_bah, 2),
        'strat1': round(yr_s1, 2),
        'excess': round(yr_s1 - yr_bah, 2),
        'avg_dev': round(avg_dev, 2),
    }

with open('analysis_output.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("Done! Output saved to analysis_output.json")
print(json.dumps(output, ensure_ascii=False, indent=2))
