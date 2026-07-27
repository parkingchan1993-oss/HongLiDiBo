#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利低波100(930955) 数据更新助手
================================
对我说 "帮我更新红利低波100数据" 即可自动完成全流程:

1. AI: 调用 TDX connector tdx_quotes(code=930955, setcode=62) 获取最新实时行情 → 保存为JSON
2. 脚本: auto_update.py <行情JSON> → 更新K线数据+行情文件
3. 策略: dividend_strategy.py → AKShare直采中证官网估值数据(股息率2/D/P2) → 评分 → 生成HTML
"""

print("=" * 66)
print("红利低波100(930955) 数据更新助手")
print("=" * 66)
print()
print("对我说:")
print()
print('    "帮我更新红利低波100数据"')
print()
print("自动完成:")
print("  1. 🔌 TDX connector → 最新实时行情")
print("  2. 📊 更新K线数据 + 行情文件")
print("  3. 📈 AKShare → 中证官网估值数据(股息率2/D/P2)")
print("  4. 🤖 策略评分 + 历史分数回溯 (114个交易日)")
print("  5. 📄 生成 HTML 仪表盘")
print()
print("数据源:")
print("  行情: TDX connector setcode=62 (指数市场)")
print("  股息率: AKShare → 中证官网 stock_zh_index_value_csindex('930955')")
print("  K线: history_klines.json 全历史数据维护")
print()
