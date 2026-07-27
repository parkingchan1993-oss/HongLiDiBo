# 红利低波100(930955) 策略项目记忆

## 项目概况
- 构建红利低波100指数(930955)的多维买卖策略与看板
- 第一维: MA250偏离值回测 (已完成 2026-07-24)
- 数据源: TDX connector setcode=62 target=1 日K线

## 关键技术发现
- **TDX K线数据获取**: 930955需要 `setcode="62"` + `target="1"` 才能返回数据，缺一不可
- **AKShare估值数据**: `stock_zh_index_value_csindex('930955')` 可获取中证官网股息率2(D/P2)、PE1、PE2
- **AKShare国债数据**: `bond_zh_us_rate()` 可获取中国10年期国债收益率(日频)
- **TDX实时行情**: `tdx_quotes(code=930955, setcode=62, hasCalcInfo=1)` 可获取指数实时行情

## 数据文件
- `history_klines.json` — 1268根日K线 (2020-02-10 ~ 2026-07-24), 来源TDX
- `backtest_strategy.py` — MA250偏离值回测脚本
- `MA250偏离值回测看板.html` — 回测看板
- `dividend_strategy.py` — 多维评分策略(旧版v4)
