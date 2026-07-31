#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成四维综合策略报告HTML"""
import json, os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "four_dim_backtest.json"), "r", encoding="utf-8") as f:
    D = json.load(f)

now = datetime.now().strftime("%Y-%m-%d %H:%M")
cur = D["current"]
corr = D["correlations"]
combo = D["combo_results"]
meta = D["meta"]

# 生成相关性矩阵表格
sig_labels = ["MA250偏离", "周RSI", "40日收益差", "股债利差"]
corr_pairs = [
    ("MA250偏离", "周RSI", 0.7712),
    ("MA250偏离", "股债利差", corr.get("MA250偏离 vs 股债利差", -0.35)),
    ("周RSI", "股债利差", corr.get("周RSI vs 股债利差", -0.26)),
    ("40日收益差", "MA250偏离", corr.get("40日收益差 vs MA250偏离", 0.27)),
    ("40日收益差", "周RSI", corr.get("40日收益差 vs 周RSI", 0.21)),
    ("40日收益差", "股债利差", corr.get("40日收益差 vs 股债利差", 0.09)),
]

def corr_color(r):
    a = abs(r)
    if a < 0.3: return "#16a34a"  # 绿=独立
    if a < 0.5: return "#f59e0b"  # 黄=中等
    return "#dc2626"  # 红=高相关

def corr_label(r):
    a = abs(r)
    if a < 0.3: return "独立 ✅"
    if a < 0.5: return "中等"
    return "高相关 ⚠️"

# 40日收益差表格
spread_rows = ""
for e in D["spread_backtest"]:
    s = e["stats"]["250"]
    lo = e["bucket"] * 2
    hi = lo + 2
    label = f"{lo}%~{hi}%"
    wr = f'{s["win_rate"]}%' if s["win_rate"] else "N/A"
    ar = f'{s["avg_return"]:+.2f}%' if s["avg_return"] is not None else "N/A"
    wo = f'{s["worst"]:+.2f}%' if s["worst"] is not None else "N/A"
    # 颜色: 收益差<0=绿(买入), >4=红(卖出)
    bg = "#dcfce7" if lo < -4 else ("#fee2e2" if lo >= 4 else "#f8fafc")
    spread_rows += f'<tr style="background:{bg}"><td>{label}</td><td>{e["count"]}</td><td>{e.get("count_pct",0)}%</td><td>{wr}</td><td>{ar}</td><td>{wo}</td></tr>\n'

# 股债利差表格
erp_rows = ""
for e in D["erp_backtest"]:
    s = e["stats"]["250"]
    lo = e["bucket"] * 0.5
    hi = lo + 0.5
    label = f"{lo:.1f}%~{hi:.1f}%"
    wr = f'{s["win_rate"]}%' if s["win_rate"] else "N/A"
    ar = f'{s["avg_return"]:+.2f}%' if s["avg_return"] is not None else "N/A"
    wo = f'{s["worst"]:+.2f}%' if s["worst"] is not None else "N/A"
    bg = "#dcfce7" if lo >= 4.0 else ("#fee2e2" if lo < 2.0 else "#f8fafc")
    erp_rows += f'<tr style="background:{bg}"><td>{label}</td><td>{e["count"]}</td><td>{e.get("count_pct",0)}%</td><td>{wr}</td><td>{ar}</td><td>{wo}</td></tr>\n'

# 组合信号表格
combo_rows = ""
combo_order = ["4维4买", "4维3买", "4维2买", "4维中性", "4维2卖", "4维3卖"]
for key in combo_order:
    if key not in combo:
        continue
    c = combo[key]
    bg = "#dcfce7" if "买" in key else ("#fee2e2" if "卖" in key else "#f1f5f9")
    combo_rows += f'<tr style="background:{bg}"><td>{key}</td><td>{c["count"]}</td><td>{c["win_rate"]}%</td><td>{c["avg_return"]:+.2f}%</td><td>{c["worst"]:+.2f}%</td></tr>\n'

# 当前信号状态
def signal_badge(sig):
    colors = {"BUY": "#16a34a", "SELL": "#dc2626", "REDUCE": "#f59e0b", "HOLD": "#64748b"}
    labels = {"BUY": "买入", "SELL": "卖出", "REDUCE": "减仓", "HOLD": "持有"}
    c = colors.get(sig, "#64748b")
    l = labels.get(sig, sig)
    return f'<span style="background:{c};color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:600">{l}</span>'

cur_ma_sig = "BUY" if cur["ma250_dev"] <= -3 else ("SELL" if cur["ma250_dev"] > 5 else "HOLD")
cur_rsi_sig = "BUY" if cur["rsi"] < 40 else ("SELL" if cur["rsi"] > 80 else "HOLD")
cur_sp_sig = "BUY" if cur["spread_40d"] and cur["spread_40d"] < -5 else ("SELL" if cur["spread_40d"] and cur["spread_40d"] > 5 else "HOLD")
cur_erp_sig = "BUY" if cur["erp"] >= 3.0 else ("SELL" if cur["erp"] < 1.5 else "HOLD")

buy_count = sum(1 for s in [cur_ma_sig, cur_rsi_sig, cur_sp_sig, cur_erp_sig] if s == "BUY")
sell_count = sum(1 for s in [cur_ma_sig, cur_rsi_sig, cur_sp_sig, cur_erp_sig] if s == "SELL")

if buy_count >= 3:
    overall = "🟢 强烈买入（3+维共振）"
elif buy_count >= 2:
    overall = "🟢 偏多买入"
elif sell_count >= 3:
    overall = "🔴 强烈减仓"
elif sell_count >= 2:
    overall = "🟡 偏空减仓"
else:
    overall = "⚪ 持有观望"

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>红利低波100 四维买卖策略回测报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f8fafc;color:#1e293b;line-height:1.8;padding:20px}}
.ct{{max-width:1100px;margin:0 auto}}
.hd{{background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fff;padding:36px;border-radius:16px;margin-bottom:24px}}
.hd h1{{font-size:24px;font-weight:700;margin-bottom:8px}}
.hd .sub{{font-size:14px;color:#cbd5e1}}
.hd .meta{{font-size:12px;color:#94a3b8;margin-top:12px}}
.sec{{background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}}
.sec h2{{font-size:18px;color:#1e293b;margin-bottom:16px;padding-bottom:10px;border-bottom:2px solid #e2e8f0}}
.sec h3{{font-size:15px;color:#334155;margin:20px 0 10px}}
p{{font-size:14px;color:#475569;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th{{background:#1e293b;color:#fff;padding:10px 8px;text-align:center}}
td{{padding:8px;text-align:center;border-bottom:1px solid #e2e8f0}}
.green{{color:#16a34a;font-weight:600}}
.red{{color:#dc2626;font-weight:600}}
.blue{{color:#3b82f6;font-weight:600}}
.purple{{color:#8b5cf6;font-weight:600}}
.highlight{{background:#fef3c7;padding:2px 6px;border-radius:4px;font-weight:600}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.kpi-c{{background:#f8fafc;border-radius:8px;padding:16px;text-align:center}}
.kpi-c .v{{font-size:26px;font-weight:800}}
.kpi-c .l{{font-size:12px;color:#64748b;margin-top:4px}}
.ft{{text-align:center;padding:20px;color:#94a3b8;font-size:12px}}
.warn{{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:14px;margin:12px 0;font-size:13px;color:#9a3412}}
.insight{{background:linear-gradient(135deg,#1e293b,#334155);color:#fff;border-radius:12px;padding:24px;margin:16px 0}}
.insight h3{{color:#fbbf24;margin-top:0}}
.insight p{{color:#cbd5e1}}
.insight .key{{color:#fbbf24;font-weight:600}}
.combo-signal{{background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fff;border-radius:16px;padding:28px;margin:16px 0;text-align:center}}
.combo-signal .s{{font-size:32px;font-weight:800;margin-bottom:8px}}
</style></head><body><div class="ct">

<div class="hd">
<h1>红利低波100 (930955) 四维买卖策略回测报告</h1>
<div class="sub">MA250偏离值 + 周RSI(14) + 40日收益差 + 股债利差 | 全网搜索融合改进</div>
<div class="meta">数据范围: {meta["date_range"]} | 930955: {meta["klines_930"]}根 | 基准: {meta["benchmark"]} | CN10Y: {meta["cn10y_days"]}天 | PE: {meta["div_yield_days"]}天 | 四维同时有效: {meta["valid_4d_days"]}天 | 生成: {now}</div>
</div>

<!-- 当前状态 -->
<div class="combo-signal">
<div class="s">{overall}</div>
<div style="display:flex;justify-content:center;gap:24px;margin-top:14px;font-size:15px">
  <div>MA250偏离: <b>{cur["ma250_dev"]:+.2f}%</b> {signal_badge(cur_ma_sig)}</div>
  <div>周RSI: <b>{cur["rsi"]}</b> {signal_badge(cur_rsi_sig)}</div>
  <div>40日收益差: <b>{cur["spread_40d"]:+.2f}%</b> {signal_badge(cur_sp_sig)}</div>
  <div>股债利差: <b>{cur["erp"]:.2f}%</b> {signal_badge(cur_erp_sig)}</div>
</div>
<div style="margin-top:10px;font-size:13px;color:#cbd5e1">买入信号: {buy_count}/4 | 卖出信号: {sell_count}/4 | 股息率={cur["div_yield"]}% | CN10Y={cur["cn10y"]}%</div>
</div>

<!-- 一、信号独立性分析 -->
<div class="sec">
<h2>一、信号独立性分析（核心发现）</h2>
<p>四个维度之间的相关系数（基于{meta["valid_4d_days"]}天同时有效数据）：</p>
<table>
<tr><th>信号对</th><th>相关系数 r</th><th>独立性评估</th><th>说明</th></tr>
<tr><td>MA250偏离 vs 周RSI</td><td class="red">0.77</td><td class="red">高相关 ⚠️</td><td>同一信号说两遍（趋势+动量同源）</td></tr>
<tr><td>MA250偏离 vs 股债利差</td><td style="color:#f59e0b;font-weight:600">-0.35</td><td style="color:#f59e0b">中等</td><td>部分独立——估值维度有增量</td></tr>
<tr><td>周RSI vs 股债利差</td><td style="color:#f59e0b;font-weight:600">-0.26</td><td style="color:#f59e0b">中等</td><td>部分独立</td></tr>
<tr style="background:#dcfce7"><td><b>40日收益差 vs MA250偏离</b></td><td class="green">0.27</td><td class="green">独立 ✅</td><td>风格轮动信号，与绝对位置无关</td></tr>
<tr style="background:#dcfce7"><td><b>40日收益差 vs 周RSI</b></td><td class="green">0.21</td><td class="green">独立 ✅</td><td>与自身动量无关</td></tr>
<tr style="background:#dcfce7"><td><b>40日收益差 vs 股债利差</b></td><td class="green">0.09</td><td class="green">几乎零相关 ✅✅</td><td><b>完全独立——真正的第四维度</b></td></tr>
</table>
<div class="insight">
<h3>关键结论</h3>
<p>MA250偏离与周RSI相关系数高达 <span class="key">0.77</span>，本质上衡量同一件事（价格相对趋势的位置）。但 <span class="key">40日收益差与其余三维的相关系数仅 0.09~0.27</span>，是唯一一个真正独立的信号——它衡量的是"红利低波100相对全市场的冷热程度"，属于<span class="key">风格轮动</span>维度，而非价格位置维度。</p>
<p>股债利差与MA250偏离相关系数 -0.35，也有一定独立性——它加入了一个宏观利率维度（股息率减去国债收益率），是估值的"绝对锚"。</p>
</div>
</div>

<!-- 二、40日收益差回测 -->
<div class="sec">
<h2>二、40日收益差分档回测</h2>
<p><b>定义：</b>930955近40日收益率 − 中证全指(000985)近40日收益率。为负=红利跑输大盘（被冷落）；为正=红利跑赢大盘（受追捧）。</p>
<p><b>逻辑：</b>均值回归——当红利深度跑输大盘时，后续反弹概率极高；当红利大幅跑赢时，回调风险上升。</p>
<table>
<tr><th>收益差档位</th><th>天数</th><th>占比</th><th>250日胜率</th><th>250日均收</th><th>250日最差</th></tr>
{spread_rows}
</table>
<div class="insight">
<h3>核心发现</h3>
<p>当40日收益差 < <span class="key">-10%</span>（红利深度跑输大盘）时，250日胜率 <span class="key">94%~100%</span>，平均收益 <span class="key">+8%~+11%</span>，最差也在 +2.5% 以上。这是极强的买入信号。</p>
<p>当40日收益差 > <span class="key">+4%</span>（红利大幅跑赢大盘）时，250日胜率降至 <span class="key">71%~74%</span>，平均收益降至 +2.4%~+3.5%，最差可达 -12.95%。此时应谨慎，不宜追高。</p>
<p>注意：当前40日收益差为 <span class="key">+5.64%</span>（930955近期跑赢大盘），这是一个短期的<span class="key">偏空信号</span>——意味着红利近期表现强势，均值回归压力上升。</p>
</div>
</div>

<!-- 三、股债利差回测 -->
<div class="sec">
<h2>三、股债利差分档回测</h2>
<p><b>定义：</b>930955股息率 − 中国10年期国债收益率。当前股息率由CSI官网PE数据 + AKShare校准的payout_ratio={meta["payout_ratio"]:.4f}估算。</p>
<p><b>逻辑：</b>股债利差是红利资产的"绝对估值锚"——利差越大，股票相对债券越便宜，配置价值越高。</p>
<table>
<tr><th>利差档位</th><th>天数</th><th>占比</th><th>250日胜率</th><th>250日均收</th><th>250日最差</th></tr>
{erp_rows}
</table>
<div class="insight">
<h3>核心发现</h3>
<p>当股债利差 ≥ <span class="key">4.5%</span> 时，250日胜率 <span class="key">100%</span>，平均收益 <span class="key">+14.09%</span>，最差 +10.25%——这是历史最佳买入区。</p>
<p>当股债利差在 <span class="key">2.5%~3.0%</span> 时，250日胜率 <span class="key">98%</span>，平均收益 +10.77%，最差仅 -0.81%——也是高胜率区。</p>
<p>当前股债利差为 <span class="key">{cur["erp"]:.2f}%</span>（股息率{cur["div_yield"]}% - 国债{cur["cn10y"]}%），处于2.5%~3.0%区间，属于<span class="key">高胜率买入区</span>。</p>
</div>
</div>

<!-- 四、四维组合信号回测 -->
<div class="sec">
<h2>四、四维组合信号回测（250日前瞻）</h2>
<p>将四个维度各转化为BUY/HOLD/SELL信号，统计不同组合下的250日前瞻表现：</p>
<table>
<tr><th>组合信号</th><th>样本数</th><th>250日胜率</th><th>250日均收</th><th>250日最差</th></tr>
{combo_rows}
</table>
<div class="insight">
<h3>组合信号的强大预测力</h3>
<p>当 <span class="key">3个及以上维度同时发出BUY</span> 时（4维3买+4维4买），合计 <span class="key">129个样本</span>，250日胜率 <span class="key">100%</span>，平均收益 <span class="key">+13.5%</span>，<span class="key">最差也有 +1.74%</span>——这意味着历史上从未亏损过。</p>
<p>相比之下，4维中性区（最多1个买入信号）胜率降至 79.8%，最差 -10.49%。而4维2卖以上胜率仅 69.2%。</p>
<p style="margin-top:12px"><b>结论：多维度共振大幅提升了信号可靠性。</b>单一MA250策略的100%胜率存在幸存者偏差（集中在2022年熊市底部），但四维共振的100%胜率覆盖了更广泛的样本（129个 vs 104个），且每个维度从不同角度验证，过拟合风险更低。</p>
</div>
</div>

<!-- 五、最优策略 -->
<div class="sec">
<h2>五、四维最优策略</h2>

<div class="insight">
<h3>策略核心思路</h3>
<p><span class="key">MA250管"什么时候买"</span>（绝对位置低 → 买入）<br>
<span class="key">周RSI管"什么时候卖"</span>（动量超买 → 止盈）<br>
<span class="key">40日收益差管"相对冷热"</span>（跑输大盘 → 加仓确认；跑赢大盘 → 谨慎）<br>
<span class="key">股债利差管"绝对估值"</span>（利差大 → 便宜；利差小 → 贵）<br>
<span class="key">永远保留20%底仓</span>（该指数有正漂移，空仓反而亏钱）</p>
</div>

<h3>▍ 四维信号定义</h3>
<table>
<tr><th>维度</th><th>买入(BUY)</th><th>持有(HOLD)</th><th>卖出(SELL)</th></tr>
<tr><td><b>MA250偏离</b></td><td class="green">≤ -3%</td><td>-3% ~ +5%</td><td class="red">> +5%</td></tr>
<tr><td><b>周RSI(14)</b></td><td class="green">< 40</td><td>40 ~ 65</td><td class="red">> 65 (分批) / > 80 (清仓至底仓)</td></tr>
<tr><td><b>40日收益差</b></td><td class="green">< -5%</td><td>-5% ~ +5%</td><td class="red">> +5%</td></tr>
<tr><td><b>股债利差</b></td><td class="green">≥ 3.0%</td><td>2.0% ~ 3.0%</td><td class="red">< 2.0%</td></tr>
</table>

<h3>▍ 仓位规则（按买入信号数量）</h3>
<table>
<tr><th>买入信号数</th><th>操作</th><th>目标仓位</th><th>250日历史胜率</th><th>250日均收</th></tr>
<tr style="background:#dcfce7"><td>4维全部买入</td><td class="green">满仓加码</td><td>100%</td><td class="green">100%</td><td class="green">+13.1%</td></tr>
<tr style="background:#dcfce7"><td>3维买入</td><td class="green">重仓建仓</td><td>80%~100%</td><td class="green">100%</td><td class="green">+13.6%</td></tr>
<tr style="background:#dcfce7"><td>2维买入</td><td>中度建仓</td><td>50%~70%</td><td class="green">96.3%</td><td>+7.3%</td></tr>
<tr style="background:#f1f5f9"><td>0~1维（中性）</td><td>持有不动</td><td>维持</td><td>79.8%</td><td>+4.0%</td></tr>
<tr style="background:#fef3c7"><td>2维卖出</td><td>开始减仓</td><td>降至50%</td><td>69.2%</td><td>+1.6%</td></tr>
<tr style="background:#fee2e2"><td>3维以上卖出</td><td class="red">大幅减仓至底仓</td><td>20%</td><td>71.4%</td><td>+0.7%</td></tr>
</table>

<h3>▍ 止盈规则（基于周RSI）</h3>
<table>
<tr><th>周RSI水平</th><th>操作</th><th>数据依据</th></tr>
<tr><td>RSI 65~70</td><td>第一档止盈（卖出30%）</td><td>RSI 65+ 所有前瞻均收转负</td></tr>
<tr><td>RSI 70~80</td><td>第二档止盈（再卖30%）</td><td>12周胜率降至38%</td></tr>
<tr><td>RSI > 80</td><td>减至20%底仓</td><td>12周胜率0%，均收-6.2%</td></tr>
</table>

<div class="warn">
<b>⚠️ 重要限制：</b>本回测存在以下局限：①930955收益差使用价格收益（非全收益），40天内约0.75%的股息收益未计入；②中证全指(000985)覆盖自2020-10起，2020年初数据缺失；③股息率由PE估算（误差±0.15%）；④未计入交易成本和分红再投；⑤历史回测不代表未来。本报告不构成投资建议。
</div>
</div>

<!-- 六、当前操作建议 -->
<div class="sec">
<h2>六、当前操作建议 ({cur["date"]})</h2>
<table>
<tr><th>维度</th><th>当前值</th><th>信号</th><th>历史250日胜率</th><th>说明</th></tr>
<tr><td>MA250偏离</td><td>{cur["ma250_dev"]:+.2f}%</td><td>{signal_badge(cur_ma_sig)}</td><td class="green">100%</td><td>低于年线3.9%，买入区</td></tr>
<tr><td>周RSI(14)</td><td>{cur["rsi"]}</td><td>{signal_badge(cur_rsi_sig)}</td><td class="green">高</td><td>RSI<40，超卖区</td></tr>
<tr><td>40日收益差</td><td>{cur["spread_40d"]:+.2f}%</td><td>{signal_badge(cur_sp_sig)}</td><td class="red">74%</td><td>⚠️ 红利近期跑赢大盘，均值回归压力</td></tr>
<tr><td>股债利差</td><td>{cur["erp"]:.2f}%</td><td>{signal_badge(cur_erp_sig)}</td><td class="green">98%</td><td>股息率{cur["div_yield"]}%远超国债{cur["cn10y"]}%</td></tr>
</table>

<div class="insight">
<h3>综合判断</h3>
<p>当前 <span class="key">2/4维看多</span>（MA250 + RSI），<span class="key">1/4维看空</span>（40日收益差），<span class="key">1/4维中性</span>（股债利差）。</p>
<p>按四维策略规则，当前属于 <span class="key">2维买入</span> 区间，对应 <span class="key">50%~70%仓位</span>，250日历史胜率 96.3%。</p>
<p style="margin-top:8px">⚠️ <b>40日收益差的偏空信号值得关注：</b>930955近40天跑赢中证全指5.64%，这意味着短期内红利风格可能面临均值回归压力。如果后续收益差回落至0以下（红利再次跑输大盘），将形成3维买入共振，届时应加仓至80%+。</p>
<p style="margin-top:8px">建议操作：维持当前 <span class="key">50%~70%仓位</span>，等待40日收益差转负后加仓。止盈触发条件：周RSI突破65。</p>
</div>
</div>

<div class="ft">
红利低波100(930955) 四维买卖策略回测报告 | {meta["klines_930"]}根日K线 | 四维有效{meta["valid_4d_days"]}天 | {now} 生成<br>
数据源: TDX(930955+000985) + AKShare(CN10Y) + CSI API(PE) + AKShare(股息率校准)<br>
⚠️ 以上内容由AI基于公开数据整理生成，仅供参考，不构成任何投资建议。投资有风险，决策需谨慎。
</div>

</div></body></html>"""

output = os.path.join(BASE, "四维买卖策略回测报告.html")
with open(output, "w", encoding="utf-8") as f:
    f.write(html)
print(f"✅ 报告已生成: {output}")
