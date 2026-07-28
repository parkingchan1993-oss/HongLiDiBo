import json, statistics

with open('history_klines.json', 'r') as f:
    data = json.load(f)

closes = [float(d['close']) for d in data]
dates = [d['date'] for d in data]
volumes = [float(d['volume']) for d in data]
n = len(closes)

# 1. MA250偏离值
ma250 = [None] * n
for i in range(249, n):
    ma250[i] = sum(closes[i-249:i+1]) / 250

dev = [None] * n
for i in range(n):
    if ma250[i]:
        dev[i] = (closes[i] - ma250[i]) / ma250[i] * 100

# 2. 峰值回落 (running max)
running_max = []
mx = 0
for c in closes:
    mx = max(mx, c)
    running_max.append(mx)

pk_drawdown = [(running_max[i] - closes[i]) / running_max[i] * 100 for i in range(n)]

# 3. 两个维度的相关性
valid = [i for i in range(n) if dev[i] is not None]
devs = [dev[i] for i in valid]
pks = [pk_drawdown[i] for i in valid]
corr = statistics.correlation(devs, pks)
print(f"两个维度相关系数: {corr:.4f}")

# 4. 历史最高价
peak_idx = closes.index(max(closes))
print(f"历史最高价: {max(closes):.2f}, 日期: {dates[peak_idx]}")
print(f"最高价出现位置: 第{peak_idx}根K线 (共{n}根), 即数据开始{peak_idx/n*100:.1f}%处")

# 5. 峰值回落分阶段
pre_peak = pk_drawdown[:peak_idx]
post_peak = pk_drawdown[peak_idx:]
print(f"\n峰值出现前 ({len(pre_peak)}天): 平均回落 {statistics.mean(pre_peak):.2f}%")
print(f"峰值出现后 ({len(post_peak)}天): 平均回落 {statistics.mean(post_peak):.2f}%")
print(f"峰值出现前 max回落: {max(pre_peak):.2f}%")
print(f"峰值出现后 max回落: {max(post_peak):.2f}%")

# 6. Buy and Hold 基准
bah_return = (closes[-1] / closes[0] - 1) * 100
print(f"\nBuy & Hold 收益: {bah_return:.2f}%")
print(f"持有期: {n}天 (~{n/250:.1f}年)")
print(f"年化收益: {((closes[-1]/closes[0])**(250/n)-1)*100:.2f}%")

# 7. 最大回撤
peak_so_far = closes[0]
max_dd = 0
for c in closes:
    if c > peak_so_far:
        peak_so_far = c
    dd = (c - peak_so_far) / peak_so_far * 100
    if dd < max_dd:
        max_dd = dd
print(f"Buy&Hold 最大回撤: {max_dd:.2f}%")

# 8. MA250各区间胜率验证
zones = {
    "买入区 <=-3%": (-999, -3),
    "持有区 -3%~+3%": (-3, 3),
    "减仓区 +3%~+7%": (3, 7),
    "卖出区 >+7%": (7, 999)
}
print("\n=== MA250偏离值各区间验证 ===")
for name, (lo, hi) in zones.items():
    indices = [i for i in range(n) if dev[i] is not None and lo <= dev[i] < hi]
    if not indices:
        print(f"{name}: 0天")
        continue

    rets_250 = []
    for i in indices:
        if i + 250 < n:
            r = (closes[i+250] / closes[i] - 1) * 100
            rets_250.append(r)

    if rets_250:
        wins = sum(1 for r in rets_250 if r > 0)
        avg_ret = statistics.mean(rets_250)
        med_ret = statistics.median(rets_250)
        min_ret = min(rets_250)
        max_ret = max(rets_250)
        print(f"{name}: {len(indices)}天, 250日胜率={wins/len(rets_250)*100:.1f}%, "
              f"均值={avg_ret:.2f}%, 中位={med_ret:.2f}%, 最差={min_ret:.2f}%, 最好={max_ret:.2f}%")
    else:
        print(f"{name}: {len(indices)}天, 无250日前瞻数据")

# 9. 样本量检查
print("\n=== 样本量检查 ===")
for name, (lo, hi) in zones.items():
    indices = [i for i in range(n) if dev[i] is not None and lo <= dev[i] < hi]
    has_250 = sum(1 for i in indices if i + 250 < n)
    print(f"{name}: 总{len(indices)}天, 有250日前瞻数据的={has_250}天")

# 10. 不同持有期胜率（30/60/120/250日）
print("\n=== 各区间不同持有期胜率 ===")
for name, (lo, hi) in zones.items():
    indices = [i for i in range(n) if dev[i] is not None and lo <= dev[i] < hi]
    if not indices:
        continue
    for period in [30, 60, 120, 250]:
        rets = []
        for i in indices:
            if i + period < n:
                r = (closes[i+period] / closes[i] - 1) * 100
                rets.append(r)
        if rets:
            wins = sum(1 for r in rets if r > 0)
            print(f"  {name} {period}日: 胜率={wins/len(rets)*100:.1f}%, 均值={statistics.mean(rets):.2f}%, 样本={len(rets)}")

# 11. 峰值回落区间的分段分析（峰值前 vs 峰值后）
print("\n=== 峰值回落>10%的分段验证 ===")
pk_buy_indices = [i for i in range(n) if pk_drawdown[i] > 10]
pk_buy_pre = [i for i in pk_buy_indices if i < peak_idx]
pk_buy_post = [i for i in pk_buy_indices if i >= peak_idx]
print(f"峰值回落>10%总天数: {len(pk_buy_indices)}")
print(f"  其中峰值出现前: {len(pk_buy_pre)}天")
print(f"  其中峰值出现后: {len(pk_buy_post)}天")

for label, idx_list in [("峰值前", pk_buy_pre), ("峰值后", pk_buy_post)]:
    if not idx_list:
        print(f"  {label}: 无数据")
        continue
    rets_250 = []
    for i in idx_list:
        if i + 250 < n:
            r = (closes[i+250] / closes[i] - 1) * 100
            rets_250.append(r)
    if rets_250:
        wins = sum(1 for r in rets_250 if r > 0)
        print(f"  {label} 250日胜率: {wins/len(rets_250)*100:.1f}%, 均值={statistics.mean(rets_250):.2f}%, 样本={len(rets_250)}")
    else:
        print(f"  {label}: 无250日前瞻数据")

# 12. 简单策略 vs Buy&Hold
print("\n=== 策略回测对比 ===")
# 策略: MA250偏离 <= -3% 满仓, >= +7% 空仓, 中间半仓
position = 0.5  # 初始半仓
strategy_values = [closes[0] * position]
bah_values = [closes[0]]

trades = 0
for i in range(1, n):
    if dev[i] is not None:
        if dev[i] <= -3:
            new_pos = 1.0
        elif dev[i] >= 7:
            new_pos = 0.0
        elif dev[i] <= 0:
            new_pos = 0.75
        else:
            new_pos = 0.5
        if new_pos != position:
            trades += 1
            position = new_pos

    daily_ret = (closes[i] / closes[i-1] - 1)
    strategy_values.append(strategy_values[-1] * (1 + daily_ret * position))
    bah_values.append(bah_values[-1] * (1 + daily_ret))

strat_return = (strategy_values[-1] / strategy_values[0] - 1) * 100
bah_return = (bah_values[-1] / bah_values[0] - 1) * 100
print(f"策略总收益: {strat_return:.2f}%")
print(f"Buy&Hold总收益: {bah_return:.2f}%")
print(f"策略超额收益: {strat_return - bah_return:.2f}%")
print(f"交易次数: {trades}")

# 策略最大回撤
peak_s = strategy_values[0]
max_dd_s = 0
for v in strategy_values:
    if v > peak_s:
        peak_s = v
    dd = (v - peak_s) / peak_s * 100
    if dd < max_dd_s:
        max_dd_s = dd
print(f"策略最大回撤: {max_dd_s:.2f}%")

# Sharpe (daily -> annualized)
daily_rets_strat = [strategy_values[i]/strategy_values[i-1]-1 for i in range(1, len(strategy_values))]
daily_rets_bah = [bah_values[i]/bah_values[i-1]-1 for i in range(1, len(bah_values))]

if statistics.pstdev(daily_rets_strat) > 0:
    sharpe_strat = (statistics.mean(daily_rets_strat) / statistics.pstdev(daily_rets_strat)) * (250**0.5)
else:
    sharpe_strat = 0
if statistics.pstdev(daily_rets_bah) > 0:
    sharpe_bah = (statistics.mean(daily_rets_bah) / statistics.pstdev(daily_rets_bah)) * (250**0.5)
else:
    sharpe_bah = 0
print(f"策略Sharpe: {sharpe_strat:.3f}")
print(f"Buy&Hold Sharpe: {sharpe_bah:.3f}")

# 13. 年度收益率对比
print("\n=== 年度收益率对比 ===")
years = {}
for i in range(n):
    y = dates[i][:4]
    if y not in years:
        years[y] = {'start_idx': i, 'end_idx': i}
    years[y]['end_idx'] = i

for y in sorted(years.keys()):
    si = years[y]['start_idx']
    ei = years[y]['end_idx']
    yr_bah = (closes[ei] / closes[si] - 1) * 100
    yr_strat = (strategy_values[ei] / strategy_values[si] - 1) * 100
    print(f"  {y}: 策略={yr_strat:+.2f}%, Buy&Hold={yr_bah:+.2f}%, 超额={yr_strat-yr_bah:+.2f}%")

# 14. 月度胜率
print("\n=== 月度收益分析 ===")
months = {}
for i in range(n):
    ym = dates[i][:6]
    if ym not in months:
        months[ym] = {'start_idx': i, 'end_idx': i}
    months[ym]['end_idx'] = i

strat_monthly = []
bah_monthly = []
for ym in sorted(months.keys()):
    si = months[ym]['start_idx']
    ei = months[ym]['end_idx']
    if si > 0:
        sr = (strategy_values[ei] / strategy_values[si-1] - 1) * 100
        br = (closes[ei] / closes[si-1] - 1) * 100
        strat_monthly.append(sr)
        bah_monthly.append(br)

strat_win = sum(1 for r in strat_monthly if r > 0)
bah_win = sum(1 for r in bah_monthly if r > 0)
print(f"策略月度胜率: {strat_win/len(strat_monthly)*100:.1f}% ({strat_win}/{len(strat_monthly)})")
print(f"B&H月度胜率: {bah_win/len(bah_monthly)*100:.1f}% ({bah_win}/{len(bah_monthly)})")

# 15. 偏离值分布
print("\n=== MA250偏离值分布 ===")
dev_valid = [d for d in dev if d is not None]
print(f"均值: {statistics.mean(dev_valid):.2f}%")
print(f"中位数: {statistics.median(dev_valid):.2f}%")
print(f"标准差: {statistics.pstdev(dev_valid):.2f}%")
print(f"最小: {min(dev_valid):.2f}%")
print(f"最大: {max(dev_valid):.2f}%")
# 百分位
sorted_dev = sorted(dev_valid)
for p in [5, 10, 25, 50, 75, 90, 95]:
    idx = int(len(sorted_dev) * p / 100)
    print(f"  P{p}: {sorted_dev[idx]:.2f}%")
