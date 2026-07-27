#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从TDX K线结果文件解析930955全历史日K线数据
"""
import json
import os
import sys
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
TDX_DIR = os.path.join(BASE, "..", "..", ".workbuddy", "projects",
    "c-Users-BJ-WorkBuddy-2026-06-24-11-03-25",
    "bdb73a4e-635b-45e2-a211-3b615058bd8e", "tool-results")

# 两批数据文件
FILES = [
    os.path.join(TDX_DIR, "mcp-connector-proxy-tdx-connector_tdx_kline-1784883098652-ebd267.txt"),  # startxh=0, 1000根
    os.path.join(TDX_DIR, "mcp-connector-proxy-tdx-connector_tdx_kline-1784883106220-2fbd39.txt"),  # startxh=1000, 1000根
]

def parse_kline_file(filepath):
    """从TDX输出文件中解析K线Rows数据"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 找到JSON部分
    json_start = content.find("{")
    if json_start < 0:
        print(f"  [!] 未找到JSON: {filepath}")
        return []
    
    js_text = content[json_start:]
    data = json.loads(js_text)
    
    rows = data.get("Rows", [])
    klines = []
    for row in rows:
        date = row.get("Data", "")
        klines.append({
            "date": date,
            "open": float(row.get("Open", 0)),
            "high": float(row.get("High", 0)),
            "low": float(row.get("Low", 0)),
            "close": float(row.get("Close", 0)),
            "volume": float(row.get("Volume", 0)),
        })
    return klines

def main():
    all_klines = {}  # date -> kline dict, 用dict去重
    
    for fp in FILES:
        if not os.path.exists(fp):
            print(f"  [!] 文件不存在: {fp}")
            continue
        ks = parse_kline_file(fp)
        print(f"  解析: {os.path.basename(fp)} -> {len(ks)}根")
        for k in ks:
            all_klines[k["date"]] = k
    
    # 按日期排序
    sorted_klines = sorted(all_klines.values(), key=lambda x: x["date"])
    
    print(f"\n  合并去重后: {len(sorted_klines)}根")
    print(f"  日期范围: {sorted_klines[0]['date']} ~ {sorted_klines[-1]['date']}")
    print(f"  首根: {sorted_klines[0]}")
    print(f"  末根: {sorted_klines[-1]}")
    
    # 保存
    out = os.path.join(BASE, "history_klines.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(sorted_klines, f, ensure_ascii=False, indent=1)
    print(f"\n  ✅ 已保存: {out}")

if __name__ == "__main__":
    print("=" * 60)
    print("解析TDX K线数据 -> history_klines.json")
    print("=" * 60)
    main()
