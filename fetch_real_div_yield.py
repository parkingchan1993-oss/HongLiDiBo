#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利低波100(930955) 真实股息率获取脚本
====================================
从ETF 515100的前20大持仓中, 通过westock-data查询每只成分股的真实dividend_ratio_ttm,
按权重加权平均, 得到指数的真实股息率。

用法: python fetch_real_div_yield.py
输出: 打印加权股息率, 同时存到 real_div_yield.json 供策略调用
"""

import json
import os
import re
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE, "real_div_yield.json")

# westock-data CLI路径
WESTOCK_SCRIPT = os.path.join(BASE, "..", "..", ".workbuddy", "plugins",
    "marketplaces", "experts", "plugins", "stock-partner-team",
    "skills", "westock-data", "scripts", "index.js")


def run_westock(cmd_args):
    """执行westock-data命令并返回原始输出"""
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            ["node", WESTOCK_SCRIPT] + cmd_args,
            capture_output=True, timeout=30,
            cwd=os.path.dirname(WESTOCK_SCRIPT),
            env=env
        )
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [ERR] westock-data调用失败: {e}", file=sys.stderr)
        return ""


def parse_markdown_tables(output):
    """解析westock-data返回的所有Markdown表格, 返回 [(headers, rows), ...]"""
    tables = []
    lines = output.strip().split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and "---" not in lines[i]:
            # 可能的表头行
            headers = [c.strip() for c in lines[i].split("|")[1:-1]]
            if not headers:
                i += 1
                continue
            # 下一行应该是分隔线
            if i + 1 < len(lines) and lines[i+1].startswith("|") and all(c.strip() in ("", "-", "---") for c in lines[i+1].split("|")[1:-1]):
                # 确实是一个表格
                rows = []
                j = i + 2
                while j < len(lines) and lines[j].startswith("|") and "---" not in lines[j]:
                    cols = [c.strip() for c in lines[j].split("|")[1:-1]]
                    row = {}
                    for k, h in enumerate(headers):
                        if k < len(cols):
                            row[h] = cols[k]
                    if row:
                        rows.append(row)
                    j += 1
                tables.append((headers, rows))
                i = j
                continue
        i += 1
    return tables


def fetch_etf_holdings():
    """获取ETF 515100的前20大持仓"""
    print("  查询ETF 515100持仓...")
    output = run_westock(["etf", "sh515100"])
    if not output:
        return []
    
    tables = parse_markdown_tables(output)
    
    # 找到持仓表 (headers包含code, name, ratio)
    holdings = []
    for headers, rows in tables:
        if "code" in headers and "name" in headers and "ratio" in headers:
            ci = headers.index("code")
            ni = headers.index("name")
            ri = headers.index("ratio")
            for row in rows:
                code = row.get("code", "")
                name = row.get("name", "")
                try:
                    ratio = float(row.get("ratio", "0"))
                except ValueError:
                    ratio = 0
                if code and ratio > 0:
                    holdings.append({"code": code, "name": name, "ratio": ratio})
            break
    
    print(f"  → 解析到 {len(holdings)} 只持仓")
    return holdings


def fetch_dividend_yields(holdings):
    """批量查询持仓的dividend_ratio_ttm"""
    # 添加市场前缀: 6xxxxx → sh, 0/3xxxxx → sz, 4xxx → bj
    def add_market(code):
        if code.startswith("6") or code.startswith("9"):
            return f"sh{code}"
        elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
            return f"sz{code}"
        elif code.startswith("4") or code.startswith("8"):
            return f"bj{code}"
        return code
    
    market_codes = [add_market(h["code"]) for h in holdings]
    batch_size = 15
    
    all_rows = []
    for i in range(0, len(market_codes), batch_size):
        batch = market_codes[i:i+batch_size]
        code_str = ",".join(batch)
        print(f"  查询股息率: {code_str[:60]}...")
        output = run_westock(["quote", code_str])
        tables = parse_markdown_tables(output)
        for headers, rows in tables:
            all_rows.extend(rows)
    
    # 建立code -> dividend_ratio_ttm映射
    # quote返回的code带市场前缀(sh/sz), 需要匹配原始code
    yield_map = {}
    for row in all_rows:
        full_code = row.get("code", "")
        dr = row.get("dividend_ratio_ttm", "0")
        try:
            dr_val = float(dr)
        except ValueError:
            dr_val = 0
        if dr_val > 0:
            # 去掉市场前缀
            raw_code = full_code[2:] if full_code.startswith(("sh", "sz", "bj")) else full_code
            yield_map[raw_code] = dr_val
    
    return yield_map


def compute_weighted_yield(holdings, yield_map):
    """计算加权平均股息率"""
    total_weight = 0
    weighted_sum = 0
    details = []
    
    for h in holdings:
        code = h["code"]
        name = h["name"]
        ratio = h["ratio"]
        div_yield = yield_map.get(code, 0)
        
        if div_yield > 0:
            weighted_sum += ratio * div_yield
            total_weight += ratio
        
        details.append({
            "code": code,
            "name": name,
            "weight": ratio,
            "dividend_ratio_ttm": div_yield
        })
    
    if total_weight > 0:
        avg_yield = weighted_sum / total_weight
    else:
        avg_yield = 0
    
    return round(avg_yield, 4), details, total_weight


def main():
    print("=" * 66)
    print("红利低波100(930955) 真实股息率计算")
    print("=" * 66)
    
    # Step 1: 获取ETF持仓
    holdings = fetch_etf_holdings()
    if not holdings:
        print("  ❌ 获取持仓失败")
        sys.exit(1)
    
    for h in holdings:
        print(f"    {h['code']} {h['name']} 权重{h['ratio']}%")
    
    # Step 2: 查询股息率
    print(f"\n  查询 {len(holdings)} 只成分股dividend_ratio_ttm...")
    yield_map = fetch_dividend_yields(holdings)
    
    # Step 3: 计算加权平均
    avg_yield, details, total_weight = compute_weighted_yield(holdings, yield_map)
    
    print(f"\n  有效权重合计: {total_weight:.1f}%")
    print(f"  加权平均股息率TTM: {avg_yield:.2f}%")
    
    # 打印明细
    print("\n  持仓明细:")
    print(f"  {'代码':>8} {'名称':<12} {'权重':>6} {'股息率TTM':>10}")
    print(f"  {'-'*40}")
    for d in details:
        if d["dividend_ratio_ttm"] > 0:
            print(f"  {d['code']:>8} {d['name']:<12} {d['weight']:>5.1f}% {d['dividend_ratio_ttm']:>8.2f}%")
        else:
            print(f"  {d['code']:>8} {d['name']:<12} {d['weight']:>5.1f}% {'N/A':>8}")
    
    # 保存结果
    result = {
        "date": "20260626",
        "holdings_count": len(holdings),
        "effective_weight": round(total_weight, 1),
        "weighted_avg_dividend_yield": avg_yield,
        "baseline_price_calibrated": round(5.0 * 11500 / avg_yield, 2) if avg_yield > 0 else 11500,
        "details": details
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ 已保存: {OUTPUT_FILE}")
    print(f"  加权股息率: {avg_yield:.2f}%")
    print("=" * 66)


if __name__ == "__main__":
    main()
