#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从统一回测JSON生成MA250可信基线HTML报告。"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median

BASE = Path(__file__).resolve().parent
INPUT = BASE / "outputs" / "ma250_baseline_results.json"
OUTPUT = BASE / "outputs" / "MA250可信基线回测报告.html"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    echarts_code = (BASE / "echarts.min.js").read_text(encoding="utf-8")
    scenarios = data["scenarios"]
    current = data["current_signal"]
    neighborhood = data["parameter_neighborhood_cost_20bps"]
    positive = sum(row["excess_total_return_pct"] > 0 for row in neighborhood)
    median_excess = median(row["excess_total_return_pct"] for row in neighborhood)
    median_sharpe = median(row["sharpe"] for row in neighborhood)

    scenario_rows = ""
    for key, label in [("cost_0bps", "无成本"), ("cost_10bps", "单边10bp"), ("cost_20bps", "单边20bp")]:
        row = scenarios[key]
        m = row["metrics"]
        b = row["benchmark_metrics"]
        scenario_rows += f"""
        <tr>
          <td><b>{label}</b></td><td class="up">{pct(m['total_return_pct'])}</td>
          <td>{m['annual_return_pct']:.2f}%</td><td>{m['sharpe']:.3f}</td>
          <td>{m['max_drawdown_pct']:.2f}%</td><td>{m['trade_count']}</td>
          <td>{m['cumulative_turnover']:.2f}倍</td><td>{pct(b['total_return_pct'])}</td>
          <td class="{'up' if row['excess_total_return_pct'] >= 0 else 'down'}">{pct(row['excess_total_return_pct'])}</td>
        </tr>"""

    top_rows = ""
    for row in neighborhood[:8]:
        top_rows += f"""<tr><td>{row['deep_buy_threshold']:.0f}%</td><td>{row['reduce_threshold']:.0f}%</td><td>{row['exit_threshold']:.0f}%</td><td class="up">{pct(row['total_return_pct'])}</td><td>{row['sharpe']:.3f}</td><td>{row['max_drawdown_pct']:.2f}%</td><td>{row['trade_count']}</td><td>{pct(row['excess_total_return_pct'])}</td></tr>"""

    ledger = scenarios["cost_20bps"]["strategy_ledger"]
    benchmark_ledger = scenarios["cost_20bps"]["benchmark_ledger"]
    dates = [row["date"] for row in ledger]
    equities = [round(row["equity"], 4) for row in ledger]
    benchmark_values = [round(row["equity"], 4) for row in benchmark_ledger]
    weights = [round(row["actual_weight"] * 100, 2) for row in ledger]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MA250可信基线回测报告</title>
<style>
:root{{--bg:#f4f7fb;--card:#fff;--text:#172033;--muted:#667085;--line:#dce4ee;--red:#c62828;--green:#16845b;--blue:#245ea8;--amber:#a66300}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,"Microsoft YaHei",sans-serif;line-height:1.65}}.wrap{{max-width:1180px;margin:auto;padding:26px 18px 52px}}.hero{{background:linear-gradient(135deg,#f7fbff,#eaf2fb);border:1px solid #d6e2f0;border-radius:18px;padding:28px}}h1{{margin:5px 0 8px;font-size:28px}}.eyebrow{{font-size:12px;color:var(--blue);font-weight:800;letter-spacing:.1em}}.sub,.note{{color:var(--muted);font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}.kpi,.sec{{background:var(--card);border:1px solid var(--line);border-radius:14px}}.kpi{{padding:16px}}.kpi .v{{font-size:25px;font-weight:800}}.kpi .l{{font-size:12px;color:var(--muted)}}.sec{{padding:23px;margin:18px 0}}h2{{font-size:19px;margin:0 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}}h3{{font-size:15px;margin:18px 0 8px}}table{{width:100%;border-collapse:collapse;font-size:12.5px}}th{{background:#eef3f8}}th,td{{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right}}th:first-child,td:first-child{{text-align:left}}.up{{color:var(--red);font-weight:700}}.down{{color:var(--green);font-weight:700}}.call{{padding:14px 16px;border-radius:9px;margin:12px 0}}.warn{{background:#fff7e8;border:1px solid #f0ddb5}}.good{{background:#eef9f4;border:1px solid #cdebdc}}.info{{background:#eef6ff;border:1px solid #cfe0f5}}.chart{{height:390px;width:100%}}.mono{{font-family:Consolas,monospace;font-size:12px}}.footer{{font-size:12px;color:var(--muted);text-align:center;margin-top:22px}}@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}.chart{{height:330px}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}.sec{{padding:15px}}}}
</style><script>{echarts_code}</script></head><body><main class="wrap">
<section class="hero"><div class="eyebrow">POINT-IN-TIME BACKTEST BASELINE</div><h1>红利低波100（930955）MA250可信基线回测</h1><div class="sub">T日收盘生成信号 → T+1交易日开盘执行｜单资产离散调仓｜逐日账本与逐笔交易可复算</div></section>
<div class="grid">
<div class="kpi"><div class="v up">+37.30%</div><div class="l">20bp成本后策略总收益</div></div>
<div class="kpi"><div class="v">-9.40%</div><div class="l">20bp成本后最大回撤</div></div>
<div class="kpi"><div class="v">0.915</div><div class="l">20bp成本后Sharpe</div></div>
<div class="kpi"><div class="v">25 / 27</div><div class="l">参数邻域正超额组合数</div></div>
</div>
<section class="sec"><h2>一、结论先行</h2>
<div class="good call"><b>研究结论：</b>在统一执行时序和同起点对照下，MA250仓位策略表现出较稳定的回撤压缩能力。20bp单边成本下，策略总收益为+37.30%，同期成本调整Buy & Hold为+27.80%，最大回撤从-17.72%降至-9.40%。</div>
<div class="warn call"><b>限制：</b>该结果仍是同一历史样本内的参数邻域检验，尚未进行walk-forward样本外验证；累计换手46.76倍，成本估计和ETF实际成交质量会显著影响结果；当前使用价格指数收益，不含分红再投资。</div>
<table><tr><th>执行与数据口径</th><th>设定</th></tr><tr><td>数据</td><td>{data['meta']['bars']}根日K，{data['meta']['date_start']}—{data['meta']['date_end']}</td></tr><tr><td>回测有效期</td><td>{scenarios['cost_20bps']['metrics']['start_date']}—{scenarios['cost_20bps']['metrics']['end_date']}</td></tr><tr><td>执行规则</td><td>{data['meta']['execution_rule']}</td></tr><tr><td>调仓规则</td><td>仅目标仓位档位发生变化时调仓；不因自然漂移每日再平衡</td></tr><tr><td>成本规则</td><td>{data['meta']['cost_rule']}</td></tr><tr><td>数据哈希</td><td class="mono">{data['meta']['data_sha256']}</td></tr></table>
</section>
<section class="sec"><h2>二、成本情景与同起点基准</h2><div class="info call"><b>成本是什么意思？</b><br>无成本：假设每次买卖完全免费，主要用于观察策略本身，不符合真实交易。<br>单边10bp：每成交1万元，扣除约10元成本；买入扣一次，之后卖出还要再扣一次。<br>单边20bp：每成交1万元，扣除约20元成本；这是更保守的估计，用来覆盖手续费、买卖价差和滑点。<br><span class="note">1bp＝0.01%＝万分之一；10bp＝0.10%，20bp＝0.20%。这里按每次实际成交金额计算，不是按全部账户资金计算。</span></div><table><tr><th>情景</th><th>策略总收益</th><th>年化收益</th><th>Sharpe</th><th>最大回撤</th><th>交易次数</th><th>累计换手</th><th>Buy & Hold</th><th>超额</th></tr>{scenario_rows}</table><p class="note">Buy & Hold同样在首个有效信号后的下一交易日开盘买入，并按相同成本情景计提一次买入成本。</p></section>
<section class="sec"><h2>三、20bp情景净值与仓位</h2><div id="equity" class="chart"></div><div id="weight" class="chart" style="height:280px"></div></section>
<section class="sec"><h2>四、参数邻域稳定性</h2><div class="info call">共检验27组参数（买入阈值-2/-3/-4%，减仓阈值2/3/4%，退出阈值6/7/8%）。20bp成本下，{positive}/27组取得正超额；超额中位数{median_excess:+.2f}%，Sharpe中位数{median_sharpe:.3f}。这支持“不是单一点参数偶然命中”的初步判断，但不能替代样本外验证。</div><h3>按Sharpe排序前8组</h3><table><tr><th>买入阈值</th><th>减仓阈值</th><th>退出阈值</th><th>总收益</th><th>Sharpe</th><th>最大回撤</th><th>交易次数</th><th>超额</th></tr>{top_rows}</table></section>
<section class="sec"><h2>五、当前信号与信号独立性</h2><table><tr><th>日期</th><th>收盘</th><th>MA250</th><th>偏离</th><th>MA斜率</th><th>目标仓位</th><th>状态</th></tr><tr><td>{current['date']}</td><td>{current['close']:.2f}</td><td>{current['ma250']:.2f}</td><td>{current['deviation_pct']:+.2f}%</td><td>{current['ma250_slope_pct']:+.4f}%</td><td>{current['target_weight']*100:.0f}%</td><td>{current['regime']}</td></tr></table><p class="note">该“当前”仅对应数据文件最后日期{current['date']}，并非实时行情。MA≤-3%共有{data['signal_summary']['daily_observations']}个每日观察，但只有{data['signal_summary']['entry_events']}次首次入区事件。</p></section>
<section class="sec"><h2>六、下一步验收项</h2><ol><li>按时间滚动实施walk-forward，参数只能在训练窗选择。</li><li>加入1%~2%现金收益率、真实ETF价差与跟踪误差情景。</li><li>用总收益指数或显式分红再投资重算策略和基准。</li><li>降低换手：加入滞回阈值、最短持有期和5%调仓带并比较。</li><li>在MA250基线稳定后，再逐一验证估值和风格因子的样本外增量。</li></ol></section>
<div class="footer">自动生成自 outputs/ma250_baseline_results.json｜仅供策略研究，不构成投资建议</div>
<script>
const dates={json.dumps(dates, ensure_ascii=False)};
const strategy={json.dumps(equities)};
const benchmark={json.dumps(benchmark_values)};
const weights={json.dumps(weights)};
echarts.init(document.getElementById('equity')).setOption({{
  tooltip:{{trigger:'axis'}},legend:{{data:['MA250策略','Buy & Hold']}},grid:{{left:55,right:20,top:48,bottom:46}},
  xAxis:{{type:'category',data:dates,boundaryGap:false}},yAxis:{{type:'value',scale:true,name:'净值'}},
  dataZoom:[{{type:'inside'}},{{type:'slider',height:18,bottom:8}}],
  series:[{{name:'MA250策略',type:'line',showSymbol:false,data:strategy,lineStyle:{{color:'#c62828',width:2}}}},{{name:'Buy & Hold',type:'line',showSymbol:false,data:benchmark,lineStyle:{{color:'#16845b',width:1.8}}}}]
}});
echarts.init(document.getElementById('weight')).setOption({{
  tooltip:{{trigger:'axis',formatter:params=>params[0].axisValue+'<br>仓位: '+params[0].value+'%'}},grid:{{left:55,right:20,top:35,bottom:40}},
  xAxis:{{type:'category',data:dates,boundaryGap:false}},yAxis:{{type:'value',min:0,max:100,name:'仓位%'}},
  series:[{{name:'实际仓位',type:'line',step:'end',showSymbol:false,areaStyle:{{color:'rgba(198,40,40,.15)'}},lineStyle:{{color:'#c62828'}},data:weights}}]
}});
window.addEventListener('resize',()=>{{echarts.getInstanceByDom(document.getElementById('equity')).resize();echarts.getInstanceByDom(document.getElementById('weight')).resize();}});
</script></main></body></html>"""
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"报告已生成: {OUTPUT}")


if __name__ == "__main__":
    main()
