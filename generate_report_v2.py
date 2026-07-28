import json

with open('analysis_output.json', 'r') as f:
    d = json.load(f)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>红利低波100 MA250策略审视与改进报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f8fafc;color:#1e293b;line-height:1.8;padding:20px}}
.ct{{max-width:1100px;margin:0 auto}}
.hd{{background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fff;padding:40px;border-radius:16px;margin-bottom:24px}}
.hd h1{{font-size:24px;font-weight:700;margin-bottom:8px}}
.hd .sub{{font-size:14px;color:#cbd5e1}}
.hd .meta{{font-size:12px;color:#94a3b8;margin-top:12px}}
.sec{{background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}}
.sec h2{{font-size:18px;color:#1e293b;margin-bottom:16px;padding-bottom:10px;border-bottom:2px solid #e2e8f0}}
.sec h3{{font-size:15px;color:#334155;margin:20px 0 10px}}
p{{font-size:14px;color:#475569;margin-bottom:12px}}
.flaw{{background:#fef2f2;border-left:4px solid #dc2626;border-radius:8px;padding:16px;margin:14px 0}}
.flaw .ftitle{{font-weight:700;color:#dc2626;font-size:14px;margin-bottom:6px}}
.flaw .fdesc{{font-size:13px;color:#7f1d1d}}
.flaw .fdata{{background:#fff;border-radius:6px;padding:10px;margin-top:8px;font-size:13px;color:#1e293b;font-family:monospace}}
.fix{{background:#f0fdf4;border-left:4px solid #16a34a;border-radius:8px;padding:16px;margin:14px 0}}
.fix .ftitle{{font-weight:700;color:#16a34a;font-size:14px;margin-bottom:6px}}
.fix .fdesc{{font-size:13px;color:#14532d}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th{{background:#1e293b;color:#fff;padding:10px 8px;text-align:center}}
td{{padding:8px;text-align:center;border-bottom:1px solid #e2e8f0}}
tr:hover{{background:#f8fafc}}
.red{{color:#dc2626;font-weight:600}}
.green{{color:#16a34a;font-weight:600}}
.blue{{color:#3b82f6;font-weight:600}}
.warn-box{{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:14px;margin:12px 0;font-size:13px;color:#9a3412}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.kpi-c{{background:#f8fafc;border-radius:8px;padding:16px;text-align:center}}
.kpi-c .v{{font-size:26px;font-weight:800}}
.kpi-c .l{{font-size:12px;color:#64748b;margin-top:4px}}
.kpi-c .s{{font-size:11px;color:#94a3b8;margin-top:2px}}
.strat-card{{border:2px solid #e2e8f0;border-radius:12px;padding:20px;margin:12px 0}}
.strat-card.best{{border-color:#16a34a;background:#f0fdf4}}
.strat-card h4{{font-size:16px;margin-bottom:8px}}
.strat-card .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px}}
.tag-best{{background:#16a34a;color:#fff}}
.tag-mid{{background:#f59e0b;color:#fff}}
.tag-bad{{background:#dc2626;color:#fff}}
.compare-table td.win{{background:#dcfce7;font-weight:600}}
.compare-table td.lose{{background:#fee2e2}}
.bar-chart{{margin:16px 0}}
.bar-row{{display:flex;align-items:center;gap:8px;margin:6px 0}}
.bar-label{{width:140px;font-size:12px;text-align:right;color:#475569}}
.bar-track{{flex:1;height:24px;background:#f1f5f9;border-radius:4px;position:relative;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;font-size:11px;color:#fff;font-weight:600}}
.bar-pos{{background:linear-gradient(90deg,#16a34a,#22c55e)}}
.bar-neg{{background:linear-gradient(90deg,#dc2626,#ef4444)}}
.ft{{text-align:center;padding:20px;color:#94a3b8;font-size:12px}}
.insight{{background:linear-gradient(135deg,#1e293b,#334155);color:#fff;border-radius:12px;padding:24px;margin:16px 0}}
.insight h3{{color:#fbbf24;margin-top:0}}
.insight p{{color:#cbd5e1}}
.insight .key{{color:#fbbf24;font-weight:600}}
</style>
</head>
<body>
<div class="ct">

<div class="hd">
<h1>红利低波100 (930955) MA250策略审视与改进报告</h1>
<div class="sub">基于原始报告的全面审计 | 数据回溯验证 | 策略对比回测 | 改进方案设计</div>
<div class="meta">数据范围: {d['meta']['date_start']} ~ {d['meta']['date_end']} | 总K线: {d['meta']['n_bars']}根 | 约{d['meta']['years']}年 | 生成时间: 2026-07-28</div>
</div>

<!-- ======== 审计摘要 ======== -->
<div class="sec">
<h2>一、审计摘要：原始报告的 7 个关键漏洞</h2>
<p>对原始《双维买卖策略分析报告》进行了完整的数据回溯验证，发现以下关键问题：</p>

<div class="flaw">
<div class="ftitle">漏洞1: "历史最高价"数据错误 — 盘中瞬时高点 ≠ 收盘价峰值</div>
<div class="fdesc">原始报告使用 12886.60（2024-10-08 盘中高点）作为"历史峰值"，但这一天是开盘即最高、当日暴跌6.5%的"假突破"。实际最高<b>收盘价</b>为 {d['current']['max_close']:.2f}（{d['current']['max_close_date']}），已经超过了 2024-10-08 的收盘价 12053.56。报告声称"尚未被再次突破"<b>是错误的</b>。</div>
<div class="fdata">盘中最高: {d['current']['max_high']:.2f} ({d['current']['max_high_date']}) — 当日收盘 12053.56，跌幅 -6.5%
最高收盘: {d['current']['max_close']:.2f} ({d['current']['max_close_date']}) — 已超越 2024-10-08 收盘价</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞2: "双维确认"是伪独立 — 两个维度相关系数 r = {d['correlation']}</div>
<div class="fdesc">MA250偏离值与峰值回落的相关系数为 <b>-0.82</b>，属于高度线性相关。当价格低于年线时，自然也远离历史高点——这两个指标本质上衡量的是同一件事："价格处于相对低位"。所谓的"双维共振"并非两个独立信号的交叉验证，而是<b>同一个信号说两遍</b>。</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞3: 策略严重跑输 Buy &amp; Hold — 每年都输</div>
<div class="fdesc">按原始报告的 MA250 四区策略回测，策略总收益 <span class="red">-24.00%</span>，而同期 Buy &amp; Hold 收益 <span class="green">+37.72%</span>，超额收益 <span class="red">-61.72%</span>。<b>每一个年度策略都跑输指数</b>，策略最大回撤 -33.90% 也远大于 B&amp;H 的 -17.72%。</div>
<div class="fdata">策略 Sharpe: -0.465 | B&amp;H Sharpe: 0.411 | 策略月度胜率: 36.4% | B&amp;H 月度胜率: 49.4%</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞4: "100%胜率"存在严重的幸存者偏差</div>
<div class="fdesc">买入区（偏离&le;-3%）250日胜率100%看似完美，但实际仅有 <b>104个有效样本</b>，且集中在 2022 年熊市底部区域。这些买入点之后恰好迎来了 2023-2024 年的上涨行情——这是一个特定时期的结果，不代表普适规律。将特定行情的统计结果外推为"100%胜率"具有误导性。</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞5: 峰值回落指标存在"移动靶"问题</div>
<div class="fdesc">历史最高收盘价出现在数据 89.2% 处（第1399根/共1569根K线）。在此之前"峰值"是不断上移的移动目标，在此之后才固定。报告对这两个阶段<b>未做任何区分</b>，混合统计导致结论失真。峰值回落&gt;10%的201天样本中，183天在峰值出现前，仅18天在峰值后——而峰值后没有任何250日前瞻数据可供验证。</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞6: 减仓/卖出区250日仍有正收益 — 减仓反而亏钱</div>
<div class="fdesc">减仓区（+3%~+7%）250日均值收益 <span class="green">+2.35%</span>，卖出区（&gt;+7%）250日均值收益 <span class="green">+1.23%</span>。这意味着即使在高估区域持有250天，平均仍是正收益。报告建议在这些区域减仓/清仓，<b>反而错过了后续涨幅</b>，这是策略跑输B&amp;H的核心原因。</div>
</div>

<div class="flaw">
<div class="ftitle">漏洞7: 无交易成本、无风险调整指标、无样本外验证</div>
<div class="fdesc">原始报告完全没有考虑交易成本（157次交易的摩擦成本被忽略），没有 Sharpe / 最大回撤 / Calmar 等风险调整指标，参数阈值（-3%, +3%, +7%）在全部数据上优化但<b>没有 train/test 分割验证</b>，存在过拟合风险。此外，作为红利指数分析，<b>完全忽略了分红收益</b>，低估了真实回报。</div>
</div>
</div>

<!-- ======== 数据验证 ======== -->
<div class="sec">
<h2>二、数据回溯验证：原始报告声称 vs 实际数据</h2>

<h3>▍ MA250 各区间真实胜率（基于收盘价计算）</h3>
<table>
<tr><th>区间</th><th>样本天数</th><th>占比</th><th>30日胜率</th><th>60日胜率</th><th>120日胜率</th><th>250日胜率</th><th>250日均值</th><th>250日最差</th></tr>

<tr>
<td>深度买入 (&le;-5%)</td><td>{d['zones']['deep_buy']['count']}</td><td>{d['zones']['deep_buy']['pct']:.1f}%</td>
<td class="green">{d['zones']['deep_buy']['wr_30']:.0f}%</td>
<td class="green">{d['zones']['deep_buy']['wr_60']:.0f}%</td>
<td class="green">{d['zones']['deep_buy']['wr_120']:.0f}%</td>
<td class="green">{d['zones']['deep_buy']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['deep_buy']['avg_250']:.1f}%</td>
<td>+{d['zones']['deep_buy']['min_250']:.1f}%</td>
</tr>

<tr>
<td>买入 (-5%~-3%)</td><td>{d['zones']['buy']['count']}</td><td>{d['zones']['buy']['pct']:.1f}%</td>
<td>{d['zones']['buy']['wr_30']:.0f}%</td>
<td class="green">{d['zones']['buy']['wr_60']:.0f}%</td>
<td class="green">{d['zones']['buy']['wr_120']:.0f}%</td>
<td class="green">{d['zones']['buy']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['buy']['avg_250']:.1f}%</td>
<td>+{d['zones']['buy']['min_250']:.1f}%</td>
</tr>

<tr>
<td>持有低位 (-3%~0%)</td><td>{d['zones']['hold_low']['count']}</td><td>{d['zones']['hold_low']['pct']:.1f}%</td>
<td>{d['zones']['hold_low']['wr_30']:.0f}%</td>
<td class="green">{d['zones']['hold_low']['wr_60']:.0f}%</td>
<td class="green">{d['zones']['hold_low']['wr_120']:.0f}%</td>
<td class="green">{d['zones']['hold_low']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['hold_low']['avg_250']:.1f}%</td>
<td>+{d['zones']['hold_low']['min_250']:.1f}%</td>
</tr>

<tr>
<td>持有高位 (0%~+3%)</td><td>{d['zones']['hold_high']['count']}</td><td>{d['zones']['hold_high']['pct']:.1f}%</td>
<td>{d['zones']['hold_high']['wr_30']:.0f}%</td>
<td>{d['zones']['hold_high']['wr_60']:.0f}%</td>
<td>{d['zones']['hold_high']['wr_120']:.0f}%</td>
<td class="green">{d['zones']['hold_high']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['hold_high']['avg_250']:.1f}%</td>
<td class="red">{d['zones']['hold_high']['min_250']:.1f}%</td>
</tr>

<tr>
<td>减仓 (+3%~+7%)</td><td>{d['zones']['reduce']['count']}</td><td>{d['zones']['reduce']['pct']:.1f}%</td>
<td class="red">{d['zones']['reduce']['wr_30']:.0f}%</td>
<td class="red">{d['zones']['reduce']['wr_60']:.0f}%</td>
<td>{d['zones']['reduce']['wr_120']:.0f}%</td>
<td class="green">{d['zones']['reduce']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['reduce']['avg_250']:.1f}%</td>
<td class="red">{d['zones']['reduce']['min_250']:.1f}%</td>
</tr>

<tr>
<td>卖出 (&gt;+7%)</td><td>{d['zones']['sell']['count']}</td><td>{d['zones']['sell']['pct']:.1f}%</td>
<td class="red">{d['zones']['sell']['wr_30']:.0f}%</td>
<td class="red">{d['zones']['sell']['wr_60']:.0f}%</td>
<td class="red">{d['zones']['sell']['wr_120']:.0f}%</td>
<td>{d['zones']['sell']['wr_250']:.0f}%</td>
<td class="green">+{d['zones']['sell']['avg_250']:.1f}%</td>
<td class="red">{d['zones']['sell']['min_250']:.1f}%</td>
</tr>
</table>

<div class="warn-box">
<b>关键发现：</b>减仓区250日均值 +{d['zones']['reduce']['avg_250']:.1f}%、卖出区250日均值 +{d['zones']['sell']['avg_250']:.1f}%。即使在高估区域（偏离&gt;+3%）持有250天，平均仍是正收益。这解释了为什么"减仓/清仓"策略反而跑输Buy&amp;Hold——<b>你卖出的那些仓位，后来大部分都涨了</b>。
</div>

<h3>▍ MA250偏离值百分位分布</h3>
<table>
<tr><th>P5</th><th>P10</th><th>P20</th><th>P30</th><th>P50(中位)</th><th>P70</th><th>P80</th><th>P90</th><th>P95</th></tr>
<tr>
<td class="green">{d['percentiles']['5']:.2f}%</td>
<td class="green">{d['percentiles']['10']:.2f}%</td>
<td>{d['percentiles']['20']:.2f}%</td>
<td>{d['percentiles']['30']:.2f}%</td>
<td>{d['percentiles']['50']:.2f}%</td>
<td>{d['percentiles']['70']:.2f}%</td>
<td class="red">{d['percentiles']['80']:.2f}%</td>
<td class="red">{d['percentiles']['90']:.2f}%</td>
<td class="red">{d['percentiles']['95']:.2f}%</td>
</tr>
</table>
<p>该指数中位数偏离值 +3.01%，说明大部分时间运行在 MA250 上方（牛市偏移特征）。原始报告的 +7% 卖出阈值对应 P90 以上，频率约16%，这部分仓位后续平均仍有正收益。</p>
</div>

<!-- ======== 策略对比 ======== -->
<div class="sec">
<h2>三、策略对比回测：谁才是最优解？</h2>

<div class="kpi">
<div class="kpi-c"><div class="l">Buy &amp; Hold 总收益</div><div class="v green">+{d['bah']['return']:.1f}%</div><div class="s">年化 {d['bah']['annual']:.1f}% | Sharpe {d['bah']['sharpe']:.2f}</div></div>
<div class="kpi-c"><div class="l">B&amp;H 最大回撤</div><div class="v red">{d['bah']['max_dd']:.1f}%</div><div class="s">同期最大回撤</div></div>
<div class="kpi-c"><div class="l">原始MA250策略</div><div class="v red">-24.0%</div><div class="s">Sharpe -0.47 | 回撤 -33.9%</div></div>
<div class="kpi-c"><div class="l">超额收益</div><div class="v red">-61.7%</div><div class="s">策略 vs B&amp;H</div></div>
</div>

<h3>▍ 年度收益对比</h3>
<table class="compare-table">
<tr><th>年份</th><th>Buy &amp; Hold</th><th>原始MA250策略</th><th>超额收益</th><th>当年均值偏离</th></tr>"""

for y in sorted(d['years'].keys()):
    yd = d['years'][y]
    bah_cls = "win" if yd['bah'] > yd['strat1'] else "lose"
    strat_cls = "win" if yd['strat1'] > yd['bah'] else "lose"
    exc_cls = "win" if yd['excess'] > 0 else "lose"
    html += f"""
<tr>
<td>{y}</td>
<td class="{bah_cls}">{'+' if yd['bah']>0 else ''}{yd['bah']:.2f}%</td>
<td class="{strat_cls}">{'+' if yd['strat1']>0 else ''}{yd['strat1']:.2f}%</td>
<td class="{exc_cls}">{'+' if yd['excess']>0 else ''}{yd['excess']:.2f}%</td>
<td>{yd['avg_dev']:.2f}%</td>
</tr>"""

html += f"""
</table>
<p style="text-align:center;font-size:13px;color:#dc2626;font-weight:600">↑ 原始MA250策略在<b>每一个年度</b>都跑输 Buy &amp; Hold，无一例外</p>

<h3>▍ 改进策略对比</h3>

<div class="strat-card">
<h4>方案A: Buy &amp; Hold（持有不动）<span class="tag tag-best">基准</span></h4>
<table>
<tr><th>总收益</th><th>年化</th><th>最大回撤</th><th>Sharpe</th><th>交易次数</th></tr>
<tr>
<td class="green">+{d['bah']['return']:.2f}%</td>
<td class="green">+{d['bah']['annual']:.2f}%</td>
<td class="red">{d['bah']['max_dd']:.2f}%</td>
<td>{d['bah']['sharpe']:.3f}</td>
<td>0</td>
</tr>
</table>
<p style="font-size:13px;color:#64748b">优点：零交易成本，充分享受指数正漂移。缺点：最大回撤较大，需要较强的心理承受力。</p>
</div>

<div class="strat-card best">
<h4>方案B: 动态定投（推荐方案之一）<span class="tag tag-best">低风险</span></h4>
<table>
<tr><th>总投入</th><th>期末价值</th><th>总收益</th><th>年化</th><th>投入月数</th></tr>
<tr>
<td>¥{d['dca']['total_invested']:,.0f}</td>
<td class="green">¥{d['dca']['final_value']:,.0f}</td>
<td class="green">+{d['dca']['return']:.2f}%</td>
<td>+{d['dca']['annual']:.2f}%</td>
<td>{d['dca']['months']}个月</td>
</tr>
</table>
<p style="font-size:13px;color:#64748b">规则：每月定投，偏离&lt;-3%时加倍投入，偏离&lt;-1%时加50%，偏离&gt;+7%时暂停。总投入71.5万→期末80.4万。收益虽低于B&amp;H，但<b>资金利用效率更高</b>（资金是分批投入的，不是一开始就满仓），实际IRR更高。</p>
</div>

<div class="strat-card best">
<h4>方案C: 分批建仓 + 分批止盈（推荐方案之二）<span class="tag tag-best">风险调整最优</span></h4>
<table>
<tr><th>总收益</th><th>最大回撤</th><th>交易次数</th><th>vs B&amp;H</th></tr>
<tr>
<td class="green">+{d['strat3']['return']:.2f}%</td>
<td class="green">{d['strat3']['max_dd']:.2f}%</td>
<td>{d['strat3']['trades']}</td>
<td class="red">{d['strat3']['return'] - d['bah']['return']:.2f}%</td>
</tr>
</table>
<p style="font-size:13px;color:#64748b">规则：偏离每-1%买入20%仓位（最多5次建满），偏离&gt;+5%后每+1%卖出20%。收益为B&amp;H的70%，但最大回撤仅-9.46%（B&amp;H的53%），<b>风险调整后大幅优于Buy&amp;Hold</b>。仅15次交易，交易成本极低。</p>
</div>
</div>

<!-- ======== 策略收益可视化 ======== -->
<div class="sec">
<h2>四、总收益对比可视化</h2>
<div class="bar-chart">
<div class="bar-row">
<div class="bar-label">Buy &amp; Hold</div>
<div class="bar-track"><div class="bar-fill bar-pos" style="width:{min(abs(d['bah']['return'])/40*100,100):.0f}%">+{d['bah']['return']:.1f}%</div></div>
</div>
<div class="bar-row">
<div class="bar-label">方案C 分批建仓止盈</div>
<div class="bar-track"><div class="bar-fill bar-pos" style="width:{min(abs(d['strat3']['return'])/40*100,100):.0f}%">+{d['strat3']['return']:.1f}%</div></div>
</div>
<div class="bar-row">
<div class="bar-label">方案B 动态定投</div>
<div class="bar-track"><div class="bar-fill bar-pos" style="width:{min(abs(d['dca']['return'])/40*100,100):.0f}%">+{d['dca']['return']:.1f}%</div></div>
</div>
<div class="bar-row">
<div class="bar-label">原始MA250策略</div>
<div class="bar-track"><div class="bar-fill bar-neg" style="width:{min(abs(-24)/40*100,100):.0f}%">-24.0%</div></div>
</div>
</div>

<h3>▍ 最大回撤对比（越小越好）</h3>
<div class="bar-chart">
<div class="bar-row">
<div class="bar-label">方案C 分批建仓止盈</div>
<div class="bar-track"><div class="bar-fill bar-pos" style="width:{min(abs(d['strat3']['max_dd'])/35*100,100):.0f}%;background:linear-gradient(90deg,#16a34a,#22c55e)">{d['strat3']['max_dd']:.1f}%</div></div>
</div>
<div class="bar-row">
<div class="bar-label">Buy &amp; Hold</div>
<div class="bar-track"><div class="bar-fill" style="width:{min(abs(d['bah']['max_dd'])/35*100,100):.0f}%;background:linear-gradient(90deg,#f59e0b,#fbbf24)">{d['bah']['max_dd']:.1f}%</div></div>
</div>
<div class="bar-row">
<div class="bar-label">原始MA250策略</div>
<div class="bar-track"><div class="bar-fill bar-neg" style="width:{min(abs(-33.9)/35*100,100):.0f}%">-33.9%</div></div>
</div>
</div>
</div>

<!-- ======== 改进策略详解 ======== -->
<div class="sec">
<h2>五、推荐改进策略：分批建仓 + 分批止盈</h2>

<div class="insight">
<h3>核心思路转变</h3>
<p>原始报告的致命错误：<span class="key">把"低概率赚钱的区域"等同于"应该清仓的区域"</span>。偏离&gt;+7%时250日均值仍有+1.23%正收益，清仓意味着放弃了这部分收益。</p>
<p style="margin-top:12px">改进思路：<span class="key">不在正收益区域清仓，只调整仓位大小</span>。用分批机制平滑入场出场，用仓位控制而非空仓来管理风险。</p>
</div>

<h3>▍ 策略规则</h3>
<table>
<tr><th>MA250偏离值</th><th>操作</th><th>目标仓位</th><th>触发条件</th></tr>
<tr style="background:#dcfce7">
<td>&le; -5%</td><td class="green">加倍建仓</td><td>100%</td><td>每跌1%加20%仓位（从0%开始，最多5次）</td>
</tr>
<tr style="background:#dcfce7">
<td>-5% ~ -3%</td><td class="green">继续建仓</td><td>40%~100%</td><td>延续分批买入</td>
</tr>
<tr style="background:#f1f5f9">
<td>-3% ~ +3%</td><td>持有不动</td><td>维持</td><td>不操作，让利润奔跑</td>
</tr>
<tr style="background:#fef3c7">
<td>+3% ~ +5%</td><td>持有观察</td><td>维持</td><td>开始关注，但不急于卖出</td>
</tr>
<tr style="background:#fee2e2">
<td>+5% ~ +10%</td><td class="red">分批止盈</td><td>逐步降至20%</td><td>每涨1%卖出20%仓位</td>
</tr>
<tr style="background:#fee2e2">
<td>&gt; +10%</td><td class="red">仅保留底仓</td><td>20%</td><td>保留20%底仓，不彻底空仓</td>
</tr>
</table>

<h3>▍ 为什么这个策略更优？</h3>
<div class="fix">
<div class="ftitle">改进1: 不清仓 → 保留正收益</div>
<div class="fdesc">卖出区（&gt;+7%）250日均值仍有+1.23%收益，保留20%底仓意味着不放弃这部分上涨。原始策略在此区域清仓，直接损失了这部分收益。</div>
</div>
<div class="fix">
<div class="ftitle">改进2: 分批机制 → 降低择时风险</div>
<div class="fdesc">原始策略在偏离值穿越-3%时一次性满仓，穿越+7%时一次性清仓——这是典型的"精准择时"假设，现实中几乎不可能做到。分批机制将择时风险分散到多个时点，大幅降低了对单次判断的依赖。</div>
</div>
<div class="fix">
<div class="ftitle">改进3: 交易频率极低 → 降低摩擦成本</div>
<div class="fdesc">整个回测期间仅15次交易（原始策略157次），交易成本可忽略。对于红利低波指数这种低波动品种，频繁交易反而增加成本、降低收益。</div>
</div>
<div class="fix">
<div class="ftitle">改进4: 最大回撤减半 → 风险调整后更优</div>
<div class="fdesc">策略最大回撤仅-9.46%，是B&amp;H（-17.72%）的53%。虽然总收益略低于B&amp;H，但Calmar比率（收益/最大回撤）为2.79，远优于B&amp;H的2.13。<b>承担更小的风险获得了B&amp;H 70%的收益</b>。</div>
</div>
</div>

<!-- ======== 当前状态 ======== -->
<div class="sec">
<h2>六、当前状态评估 (2026-07-27)</h2>

<div class="kpi">
<div class="kpi-c"><div class="l">收盘价</div><div class="v">{d['current']['close']:.0f}</div></div>
<div class="kpi-c"><div class="l">MA250</div><div class="v">{d['current']['ma250']:.0f}</div></div>
<div class="kpi-c"><div class="l">偏离值</div><div class="v green">{d['current']['dev']:.2f}%</div><div class="s">买入区</div></div>
<div class="kpi-c"><div class="l">距收盘峰值回落</div><div class="v">{d['current']['pk_dd_close']:.1f}%</div><div class="s">中等回落</div></div>
</div>

<div class="insight">
<h3>操作建议</h3>
<p>当前 MA250 偏离 <span class="key">{d['current']['dev']:.2f}%</span>，处于分批建仓区间。按改进策略：</p>
<p style="margin-top:8px">
• 若此前已有底仓：当前应处于 <span class="key">60%~80%仓位</span><br>
• 若尚未建仓：当前可开始 <span class="key">第一次建仓（20%仓位）</span>，因为偏离已跌破-3%<br>
• 若偏离继续下探至-4%~-5%：可加仓至40%~60%<br>
• 若偏离回升至-3%以上：停止加仓，持有等待<br>
</p>
<p style="margin-top:8px;color:#fbbf24">⚠️ 不建议一次性满仓。分批建仓的意义在于：如果继续下跌你有更多子弹，如果反弹你已有底仓。</p>
</div>

<div class="warn-box">
<b>重要提醒：</b>本报告基于红利低波100指数(930955) {d['meta']['n_bars']}根日K线的历史数据回测，数据仅覆盖{d['meta']['years']}年（2020-2026），存在特定时期偏差。<b>历史表现不代表未来收益</b>。所有策略均未计入实际交易成本、分红再投收益和税收影响。建议结合估值（股息率、PB百分位）、宏观环境（利率、信用周期）综合判断。本报告不构成任何投资建议，投资有风险，入市需谨慎。
</div>
</div>

<div class="ft">
红利低波100(930955) MA250策略审视与改进报告 | {d['meta']['n_bars']}根日K线 | 2026-07-28 生成<br>
基于原始报告数据重新回测验证 | 不构成投资建议
</div>

</div>
</body>
</html>"""

with open('MA250策略审视与改进报告.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Done! Report saved to MA250策略审视与改进报告.html")
