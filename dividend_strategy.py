#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利低波100指数(930955) 多维评分买卖策略 v3
=================================================
完全对齐"是强哥啊"量化体系 (参考7张看板截图):
  - 估值维度(60分): 真实股息率(20) + 股债利差(16) + 10Y国债方向(10) + PB百分位(10) + 成分股ROE(4)
  - 技术面维度(40分): 价格与均线(10) + 斐波那契(6) + 脉冲MACD(7) + 动能强弱(5) + 挤压动量(6) + RSI(3) + 成交量状态(3)
  - 信号映射: 85~100极强买入 / 70~84强买 / 60~69中性偏多 / 45~59中性观望 / 30~44偏贵 / <30高估警示
  - 综合研判: 利多/利空双因素列表面向

数据: 红利低波100指数930955全历史(2020-02-10至今, 1546根)
运行: python dividend_strategy.py
"""

import json
import os
import sys
import math
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE, "history_klines.json")
HS300_FILE = os.path.join(BASE, "hs300_data.json")
QUOTES_FILE = os.path.join(BASE, "quotes_data.json")
OUTPUT_HTML = os.path.join(BASE, "红利低波100策略仪表盘.html")

# 策略参数（与截图对齐）
BASELINE_PRICE = 11500.0       # 基准价 → DID=5%
BASELINE_YIELD = 5.0           # 基准股息率
RISK_FREE_RATE = 1.752          # 10Y国债收益率基准（截图实际值）
CALIBRATED_BASELINE = None      # 由真实股息率校准后的基准价
REAL_DIV_YIELD_CURRENT = None   # 真实的当前股息率(从成分股加权)
REAL_DIV_YIELD_FILE = os.path.join(BASE, "real_div_yield.json")
ETF_CODE, ETF_NAME = "55100", "红利低波100ETF景顺"
ETF2_CODE, ETF2_NAME = "159307", "红利低波100ETF"


# ======================== 数据加载 ========================
def load_json(fp):
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


# ======================== 基础技术指标 ========================
def calc_ma(closes, p):
    return sum(closes[-p:]) / p if len(closes) >= p else None

def calc_ema_series(values, period):
    if len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    out = [None] * (period - 1)
    out.append(sum(values[:period]) / period)
    for i in range(period, len(values)):
        out.append(values[i] * k + out[-1] * (1 - k))
    return out

def calc_macd_full(closes, fast=12, slow=26, signal=9):
    ef = calc_ema_series(closes, fast)
    es = calc_ema_series(closes, slow)
    dif = [ef[i] - es[i] if ef[i] is not None and es[i] is not None else None for i in range(len(closes))]
    valid = [d for d in dif if d is not None]
    dea_v = calc_ema_series(valid, signal)
    dea = [None] * len(closes)
    vs = next(i for i, d in enumerate(dif) if d is not None)
    for i, d in enumerate(dea_v):
        if d is not None:
            dea[vs + i] = d
    hist = [(dif[i] - dea[i]) * 2 if dif[i] is not None and dea[i] is not None else None for i in range(len(closes))]
    return dif, dea, hist

def calc_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-min(period, len(trs)):]) / min(period, len(trs)) if trs else 0

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    ch = [closes[i] - closes[i-1] for i in range(len(closes) - period, len(closes))]
    g = sum(max(c, 0) for c in ch) / period
    l = sum(max(-c, 0) for c in ch) / period
    return 100.0 if l == 0 else 100.0 - 100.0 / (1 + g / l)

def calc_boll(closes, p=20, ns=2):
    if len(closes) < p:
        return None
    win = closes[-p:]
    mid = sum(win) / p
    var = sum((x - mid) ** 2 for x in win) / p
    std = math.sqrt(var)
    return {"upper": mid + ns * std, "mid": mid, "lower": mid - ns * std}

def calc_volatility(closes, p=20):
    if len(closes) < p + 1:
        return 0.0
    rets = [math.log(closes[i] / closes[i-1]) for i in range(len(closes) - p, len(closes)) if closes[i-1] > 0]
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    v = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(v) * math.sqrt(252) * 100

def percentile(value, data):
    return sum(1 for d in data if d < value) / len(data) if data else 0.5


# ======================== 高级技术指标 ========================
def calc_pulse_macd(closes):
    """脉冲MACD: MACD柱的动量(柱值-EMA5(柱值)). >0=动能增强"""
    _, _, hist = calc_macd_full(closes)
    vh = [h for h in hist if h is not None]
    if len(vh) < 5:
        return {"pulse": 0, "reversed": False, "hist": vh[-1] if vh else 0, "state": "neutral"}
    ema5 = calc_ema_series(vh, 5)
    last_h = vh[-1]
    last_p = last_h - (ema5[-1] or 0)
    prev_p = vh[-2] - (ema5[-2] or 0) if len(vh) >= 2 else last_p
    rev = last_p > 0 and last_p > prev_p
    # 状态判断(截图中用Red/Green/Gray)
    if last_h < 0 and last_p < prev_p:
        state = "red_weak"      # Red极弱/恐慌抛售
    elif last_h < 0 and last_p > 0 and last_p < 0:
        state = "red_slowing"   # Red下跌减速
    elif last_h >= 0 and last_p > 0:
        state = "green"         # Green动能增强
    else:
        state = "gray"
    return {"pulse": last_p, "reversed": rev, "hist": last_h, "prev_pulse": prev_p,
            "state": state}


def calc_andean_momentum(closes, period=12):
    """动能强弱指标 Andean: ROC12 + 多头能量线.
    截图中: 绿线=0表示多头消失→0/5分"""
    roc = (closes[-1] / closes[-period] - 1) * 100 if len(closes) > period else 0
    # 多头能量: 近期ROC趋势
    roc_prev = (closes[-2] / closes[-period-1] - 1) * 100 if len(closes) > period+1 else roc
    # 截图逻辑: 绿线=0 → 多头完全消失 → ROC为负且恶化
    bull_alive = roc > 0
    improving = roc > roc_prev
    rev = bull_alive and improving
    return {"roc": roc, "prev_roc": roc_prev, "bull_alive": bull_alive,
            "improving": improving, "reversed": rev,
            "green_line": int(bull_alive)}  # 绿线=多头存活数(0或1+)


def calc_squeeze_momentum(highs, lows, closes):
    """挤压动量: 布林带(20,2) vs Keltner(20,1.5*ATR14).
    截图: Red下跌加速=0/6; 中轴gray"""
    if len(closes) < 25:
        return {"squeeze_on": False, "momentum": 0, "reversed": False, "state": "gray"}
    bb = calc_boll(closes, 20, 2)
    atr = calc_atr(highs, lows, closes, 14)
    ma20 = bb["mid"]
    kc_u = ma20 + 1.5 * atr
    kc_l = ma20 - 1.5 * atr
    sq_on = bb["lower"] > kc_l and bb["upper"] < kc_u
    # 动量: 线性回归斜率*系数
    win = closes[-20:]
    n = len(win); x_mean = (n-1)/2; y_m = sum(win)/n
    num = sum((i-x_mean)*(win[i]-y_m) for i in range(n))
    den = sum((i-x_mean)**2 for i in range(n))
    slope = num/den if den else 0
    mom = slope * n
    prev_sq_on = False
    if len(closes) >= 26:
        bp = calc_boll(closes[:-1], 20, 2)
        ap = calc_atr(highs[:-1], lows[:-1], closes[:-1], 14)
        if bp and ap:
            kp_u = bp["mid"] + 1.5*ap; kp_l = bp["mid"] - 1.5*ap
            prev_sq_on = bp["lower"] > kp_l and bp["upper"] < kp_u
    just_released = prev_sq_on and not sq_on
    # 状态: Red下跌加速 / Green上涨加速 / Gray中轴
    if mom < 0 and not sq_on and slope < 0:
        st = "red_accel"     # Red下跌加速
    elif mom > 0 and not sq_on:
        st = "green_accel"   # Green上涨加速
    else:
        st = "gray"          # Gray中轴
    rev = (not sq_on) and mom > 0 and closes[-1] > ma20
    return {"squeeze_on": sq_on, "just_released": just_released,
            "momentum": mom, "reversed": rev, "state": st,
            "bb_upper": bb["upper"], "bb_lower": bb["lower"],
            "kc_upper": kc_u, "kc_lower": kc_l}


def calc_fibonacci_extended(closes, lookback=250):
    """斐波那契回撤+扩展位 (截图含1.214/1.382极限扩展位)。
    取lookback日内显著高低点, 计算9个关键位"""
    window = closes[-lookback:] if len(closes) >= lookback else closes
    high = max(window)
    low = min(window)
    diff = high - low
    if diff <= 0:
        return None
    levels = {
        "0.000": high,           # 高点
        "0.236": high - 0.236*diff,   # 压力
        "0.382": high - 0.382*diff,   # 压力
        "0.500": high - 0.500*diff,   # 中轴
        "0.618": high - 0.618*diff,   # 黄金位/强支撑
        "0.786": high - 0.786*diff,   # 强支撑
        "1.000": low,             # 前低
        "1.214": low - 0.214*diff,   # 扩展位
        "1.382": low - 0.382*diff,   # 极限扩展位
    }
    price = closes[-1]
    # 当前位置判断
    if price <= levels.get("1.382", low):
        pos = "extreme_deep"     # 1.000+极限扩展区 ★★
    elif price <= levels["1.000"]:
        pos = "deep_value"       # 扩展区
    elif price <= levels["0.786"]:
        pos = "strong_support"   # 强支撑区
    elif price <= levels["0.618"]:
        pos = "value"            # 黄金价值区
    elif price <= levels["0.382"]:
        pos = "neutral"
    else:
        pos = "expensive"
    return {"high": high, "low": low, "levels": levels, "price": price, "pos": pos}


# ======================== 估值维度评分(60分) ========================
def score_valuation(closes):
    """
    估值维度满分60分 (截图体系):
      股息率D/P2:   20分 — 中证官网股息率2(计算用股本), 百分位4.5%~5.5%=合理中枢
      股债利差:     16分 — 股息率-CN10Y(AKShare实时), 合理中枢以上加分
      10Y国债方向:  10分 — CN10Y(AKShare实时), 低利率利好股票资产
      PB百分位:     10分 — 价格全历史百分位作PB代理
      成分股ROE:     4分 — ROE 8%~10%为一般水平
    """
    global CALIBRATED_BASELINE, REAL_DIV_YIELD_CURRENT
    d = []
    price = closes[-1]

    # 从缓存文件加载AKShare直采的中证官方估值数据(股息率2/计算用股本D/P2)
    real_div_yield = None
    if os.path.exists(REAL_DIV_YIELD_FILE):
        try:
            with open(REAL_DIV_YIELD_FILE, "r", encoding="utf-8") as f:
                real_data = json.load(f)
            # 支持新旧格式: akshare格式有dividend_yield_official字段
            real_div_yield = real_data.get("dividend_yield_official") or real_data.get("weighted_avg_dividend_yield")
        except:
            pass

    # 使用真实股息率校准DID公式
    if real_div_yield and real_div_yield > 0:
        div_yield = real_div_yield
        # 校准BASELINE_PRICE: backward_price = BASELINE_YIELD * BASELINE_PRICE / real_yield
        calibrated = BASELINE_YIELD * BASELINE_PRICE / real_div_yield
        CALIBRATED_BASELINE = calibrated
        REAL_DIV_YIELD_CURRENT = real_div_yield
        # 用校准后的基准价计算历史股息率序列(用于百分位)
        div_series = [BASELINE_YIELD * calibrated / c for c in closes]
    else:
        # 回退到旧DID公式
        div_yield = BASELINE_YIELD * BASELINE_PRICE / price
        CALIBRATED_BASELINE = BASELINE_PRICE
        div_series = [BASELINE_YIELD * BASELINE_PRICE / c for c in closes]

    spread = div_yield - RISK_FREE_RATE

    # 1. 股息率DID (满分20)
    # 反推每日股息率序列, 取当前在全历史的百分位
    div_series = [BASELINE_YIELD * BASELINE_PRICE / c for c in closes]
    div_pct = percentile(div_yield, div_series)
    # 4.5%~5.5%为合理中枢 → 在此区间附近给高分
    # 百分位越高(相对历史越便宜)→分越高; 但也要考虑绝对值在合理区间
    if 4.5 <= div_yield <= 5.5:
        s1_base = 18  # 合理中枢区间高分
    elif div_yield > 5.5:
        s1_base = 16 + min(4, (div_yield - 5.5) * 2)  # 更高也加分但有上限
    elif div_yield >= 4.0:
        s1_base = 10 + (div_yield - 4.0) * 16  # 线性
    else:
        s1_base = max(0, div_yield * 2.5)
    # 百分位修正: 历史低位加分
    pct_bonus = max(0, (0.70 - div_pct) / 0.70) * 4  # 分位<30%额外加到20
    s1 = min(20, s1_base + pct_bonus * 0.3)
    did_zone = "合理中枢" if 4.5<=div_yield<=5.5 else ("偏高" if div_yield>5.5 else "偏低")
    d.append({"name": "股息率(中证官方)", "value": f"股息率2(D/P2)={div_yield:.2f}% 百分位{div_pct*100:.1f}% {did_zone}",
              "score": round(s1, 1), "max": 20,
              "desc": f"AKShare直采中证官网 | 校准价{CALIBRATED_BASELINE:.0f} | 全历史{len(closes)}日分位"})

    # 2. 股债利差 (满分16)
    # 利差>3%为安全边际厚实, 2%~3%合理中枢, <2%不利
    if spread >= 4.0:
        s2 = 16
    elif spread >= 3.0:
        s2 = 13 + (spread - 3.0) * 3  # 3~4线性
    elif spread >= 2.0:
        s2 = 8 + (spread - 2.0) * 5   # 2~3线性
    else:
        s2 = max(0, spread * 4)
    sp_zone = "极有利" if spread>=4 else ("厚实" if spread>=3 else ("合理中枢" if spread>=2 else "偏薄"))
    d.append({"name": "股债利差", "value": f"利差={spread:.3f}% {sp_zone}",
              "score": round(s2, 1), "max": 16,
              "desc": f"股息率{div_yield:.2f}%-CN10Y{RISK_FREE_RATE:.4f}%={spread:.3f}%"})

    # 3. 10Y国债方向 (满分10) — 低利率利好股票资产
    # CN10Y < 2.0% = 极低利率(满分), 2~2.5% = 低利率(8分), 2.5~3% = 中等(5分), >3% = 不利(递减)
    cn10y = RISK_FREE_RATE  # 使用配置值(可后续接入实时API)
    if cn10y <= 2.0:
        s3 = 10
    elif cn10y <= 2.5:
        s3 = 8
    elif cn10y <= 3.0:
        s3 = 5
    else:
        s3 = max(0, 5 - (cn10y - 3.0) * 3)
    cn_zone = "极低利好" if cn10y<=2 else ("低位利好" if cn10y<=2.5 else ("中等" if cn10y<=3 else "偏高不利"))
    d.append({"name": "10Y国债方向", "value": f"CN10Y={cn10y:.4f}% {cn_zone}",
              "score": round(s3, 1), "max": 10,
              "desc": "AKShare实时: 低利率环境利好股票资产估值"})

    # 4. PB百分位 (满分10) — 用价格分位代理PB
    price_pct = percentile(price, closes)
    # 价格分位越低(PB越低)→分越高; 中位附近给中间分
    if price_pct < 0.15:
        s4 = 10   # 深度低估
    elif price_pct < 0.30:
        s4 = 8    # 低估
    elif price_pct < 0.50:
        s4 = 6    # 中位偏低
    elif price_pct < 0.70:
        s4 = 4    # 中位偏高
    else:
        s4 = 2    # 高估
    pb_zone = "深度低估" if price_pct<0.15 else ("低估" if price_pct<0.3 else ("中位" if price_pct<0.5 else ("偏高" if price_pct<0.7 else "高估")))
    d.append({"name": "PB百分位", "value": f"PB分位{price_pct*100:.1f}% {pb_zone}",
              "score": round(s4, 1), "max": 10,
              "desc": "价格分位代理PB; 红利不用PE因利润波动大"})

    # 5. 成分股ROE (满分4) — 用长期趋势代理
    # MA60相对MA250的位置反映盈利能力稳定性
    ma60 = calc_ma(closes, 60)
    ma250 = calc_ma(closes, 250) if len(closes)>=250 else calc_ma(closes, len(closes))
    if ma60 and ma250:
        roe_ratio = ma60 / ma250 if ma250 > 0 else 1
        if roe_ratio >= 1.05:
            s5 = 4   # 强势(ROE改善)
        elif roe_ratio >= 0.97:
            s5 = 3   # 一般稳定(8%~10%区间)
        elif roe_ratio >= 0.92:
            s5 = 2   # 偏弱
        else:
            s5 = 1   # 弱化
        roe_status = f"{roe_ratio*100:.1f}%"
    else:
        s5 = 2
        roe_status = "N/A"
    d.append({"name": "成分股ROE", "value": f"MA60/MA250={roe_status} ({'稳健' if s5>=3 else '走弱' if s5==2 else '弱化'})",
              "score": s5, "max": 4,
              "desc": "长期趋势代理ROE稳定性, 一般8%~10%"})

    total = s1 + s2 + s3 + s4 + s5
    return {"score": round(total, 1), "details": d,
            "div_yield": div_yield, "div_pct": div_pct, "spread": spread,
            "price_pct": price_pct}


# ======================== 技术面维度评分(40分) ========================
def score_technical(closes, highs, lows, volumes):
    """
    技术面维度满分40分 (截图体系):
      价格与均线:   10分 — SMA250偏离度, 回踩支撑=便宜信号
      斐波那契位置:  6分 — 含扩展位(1.214/1.382), 深度回调强支撑
      脉冲MACD:     7分 — Red极弱=0, Green增强=满分
      动能强弱:     5分 — Andean绿线=0多头消失→0/5
      挤压动量:     6分 — Red下跌加速=0/6
      RSI(14):      3分 — 超卖区(<30)=满分
      成交量状态:   3分 — 温和放量下跌=部分分
    """
    d = []
    price = closes[-1]

    # 1. 价格与均线 (满分10)
    ma60 = calc_ma(closes, 60)
    ma120 = calc_ma(closes, 120)
    ma250 = calc_ma(closes, 250) if len(closes)>=250 else calc_ma(closes, len(closes))
    mas = [("SMA60", ma60), ("SMA120", ma120), ("SMA250", ma250)]
    # 计算偏离度和下方状态
    below_all = all(m and price < m for _, m in mas)
    dd_from_250 = ((ma250 - price) / ma250 * 100) if ma250 and price < ma250 else 0
    # 跌破SMA250后回踩支撑 → 便宜信号(高分区间)
    if below_all and dd_from_250 >= 5:
        s1 = 10  # 深度回踩支撑, 便宜信号(截图: -7.3%得8/10, 接近满分)
    elif below_all and dd_from_250 >= 3:
        s1 = 8   # 明显跌破
    elif below_all:
        s1 = 6
    else:
        # 部分或多头排列
        above = sum(1 for _, m in mas if m and price > m)
        s1 = above * 2 + 1  # 最多7分(不完全多头)
    ma_desc = f"SMA60={ma60:.0f}({(price/ma60-1)*100:+.1f}%) SMA120={ma120:.0f}({(price/ma120-1)*100:+.1f}%) SMA250={ma250:.0f}({(price/ma250-1)*100:+.1f}%)" if ma250 else ""
    d.append({"name": "价格与均线", "value": f"{'跌破后回踩' if below_all else '部分多头'} {dd_from_250:.1f}%",
              "score": round(s1, 1), "max": 10,
              "desc": f"跌破SMA250后{'深' if dd_from_250>5 else '浅'}度回踩支撑 {'便宜信号' if s1>=8 else ''}".strip()})

    # 2. 斐波那契位置 (满分6)
    fib = calc_fibonacci_extended(closes, 250)
    fib_score_map = {
        "extreme_deep": 6,   # 1.000+极限扩展区★★ → 满分(截图当前就在这里!)
        "deep_value": 5,     # 扩展区
        "strong_support": 4, # 强支撑区
        "value": 3,          # 黄金价值区
        "neutral": 2,
        "expensive": 0,
    }
    s2 = fib_score_map.get(fib["pos"], 2)
    fib_labels = {"extreme_deep": "极限扩展区★★", "deep_value": "扩展区",
                  "strong_support": "强支撑区", "value": "黄金位", "neutral": "中性", "expensive": "高位"}
    d.append({"name": "斐波那契位置", "value": f"{fib_labels[fib['pos']]}",
              "score": s2, "max": 6,
              "desc": f"高{fib['high']:.0f}低{fib['low']:.0f} 现{price:.0f}"})

    # 3. 脉冲MACD (满分7)
    pulse = calc_pulse_macd(closes)
    if pulse["state"] == "green":
        s3 = 7
    elif pulse["state"] == "red_slowing":
        s3 = 4   # 下跌减速给中间分
    elif pulse["state"] == "red_weak":
        s3 = 0   # Red极弱/恐慌抛售 → 0分(截图!)
    else:
        s3 = 3   # neutral
    pulse_labels = {"red_weak": "Red极弱/恐慌抛售", "red_slowing": "Red下跌减速",
                    "green": "Green动能增强", "gray": "Neutral"}
    d.append({"name": "脉冲MACD", "value": f"{pulse_labels[pulse['state']]} -> {s3}/7",
              "score": s3, "max": 7,
              "desc": f"柱动量Pulse={pulse['pulse']:.1f} 柱值={pulse['hist']:.1f}"})

    # 4. 动能强弱Andean (满分5)
    andean = calc_andean_momentum(closes, 12)
    if andean["bull_alive"] and andean["improving"]:
        s4 = 5   # 多头且增强
    elif andean["bull_alive"]:
        s4 = 3   # 多头但减弱
    else:
        s4 = 0   # 绿线=0多头消失→0/5(截图!)
    d.append({"name": "动能强弱指标", "value": f"绿线={andean['green_line']} {'多头存活' if andean['bull_alive'] else '多头消失'} ROC={andean['roc']:.2f}%",
              "score": s4, "max": 5,
              "desc": "Andean绿线=0→多头完全消失→0分"})

    # 5. 挤压动量 (满分6)
    sq = calc_squeeze_momentum(highs, lows, closes)
    if sq["state"] == "green_accel":
        s5 = 6
    elif sq["state"] == "gray":
        s5 = 3   # 中轴给中间分(截图: gray中轴)
    elif sq["state"] == "red_accel":
        s5 = 0   # Red下跌加速→0/6(截图!)
    else:
        s5 = 2
    sq_labels = {"red_accel": "Red下跌加速", "green_accel": "Green上涨加速", "gray": "Gray中轴"}
    d.append({"name": "挤压动量指标", "value": f"{sq_labels[sq['state']]} Mom={sq['momentum']:.1f} -> {s5}/6",
              "score": s5, "max": 6,
              "desc": "布林vsKeltner, 释放+向上=右侧确认"})

    # 6. RSI(14) (满分3)
    rsi = calc_rsi(closes, 14)
    if rsi < 30:
        s6 = 3   # 超卖区 → 满分(截图: RSI=26.1超卖区→3/3)
    elif rsi < 40:
        s6 = 2   # 偏弱
    elif rsi < 70:
        s6 = 1.5 # 中性
    else:
        s6 = 0   # 超买
    rsi_zone = "超卖区" if rsi<30 else ("偏弱" if rsi<40 else ("中性" if rsi<70 else "超买"))
    d.append({"name": "RSI(14)", "value": f"RSI={rsi:.1f} {rsi_zone}",
              "score": s6, "max": 3,
              "desc": "<30超卖(短线超跌信号)"})

    # 7. 成交量状态 (满分3)
    # 近5日 vs 前5日量能变化 + 价格方向
    if len(volumes) >= 11 and len(closes) >= 11:
        vol_recent = sum(volumes[-5:]) / 5
        vol_prev = sum(volumes[-10:-5]) / 5
        vol_ratio = vol_recent / vol_prev if vol_prev > 0 else 1
        price_5d = (closes[-1] / closes[-6] - 1) * 100
        if price_5d < -3 and vol_ratio < 0.9:
            s7, vs = 3, "温和放量下跌"   # 缩量下跌=有支撑(截图: 温和放量下跌→2/3, 给2~3)
        elif price_5d < -3 and 0.9 <= vol_ratio <= 1.2:
            s7, vs = 2, "温和放量下跌"
        elif price_5d < -3 and vol_ratio > 1.2:
            s7, vs = 1, "放量下跌"
        elif price_5d > 1 and vol_ratio > 1.1:
            s7, vs = 3, "放量上涨确认"
        elif price_5d > 1:
            s7, vs = 2, "缩量上涨"
        else:
            s7, vs = 1.5, "量价平稳"
    else:
        s7, vs = 1.5, "数据不足"
    d.append({"name": "成交量状态", "value": vs,
              "score": s7, "max": 3,
              "desc": "温和放量下跌=有承接(非恐慌)"})

    total = s1+s2+s3+s4+s5+s6+s7
    # 右侧确认计数(三大指标反转数)
    right_count = sum([pulse["reversed"], andean["reversed"], sq["reversed"]])

    return {"score": round(total, 1), "details": d,
            "pulse": pulse, "andean": andean, "sq": sq, "fib": fib,
            "ma60": ma60, "ma120": ma120, "ma250": ma250,
            "rsi": rsi, "right_count": right_count}


# ======================== 综合研判 & 信号生成 ========================
def generate_judgment(val_score, tech_score, val_details, tech_details, closes):
    """综合研判: 利多/利空双因素列表 (截图图5格式)"""
    bullish = []
    bearish = []

    # 利多因素
    did = val_details[0]["value"]
    if "5.0" in did or "5.09" in did or val_score >= 35:
        bullish.append("DID股息率充裕, 估值具吸引力")
    sp = val_details[1]["value"]
    if "厚实" in sp or "有利" in sp or val_score >= 35:
        bullish.append("股债利差处合理中枢以上, 安全边际厚实")
    cn = val_details[2]["value"]
    if "利好" in cn or "低" in cn:
        bullish.append("CN10Y处低位区, 利好股票资产估值")
    # 价格跌破均线
    ma_d = tech_details[0]["value"]
    if "回踩" in ma_d or "跌破" in ma_d:
        bullish.append("价格跌破SMA250后深度回踩, 属\"便宜信号\"区间")
    # 斐波那契
    fb = tech_details[1]["value"]
    if "极限" in fb or "扩展" in fb or "支撑" in fb:
        bullish.append("Fibonacci处深度回调强支撑区, 布局性价比高")
    # RSI
    rs = tech_details[5]["value"]
    if "超卖" in rs:
        bullish.append("RSI处于低位/超卖区, 短线超跌信号")

    # 利空因素
    pu = tech_details[2]["value"]
    if "极弱" in pu or "Red" in pu or "恐慌" in pu:
        bearish.append("脉冲MACD为Red极弱, 价格跌破下方缓冲区")
    an = tech_details[3]["value"]
    if "消失" in an or "0/" in an:
        bearish.append("Andean绿线=0, 多头能量完全消失")
    sq_t = tech_details[4]["value"]
    if "加速" in sq_t or "下跌" in sq_t:
        bearish.append("挤压动量鲜红下跌加速, 短线风险仍存")

    return {"bullish": bullish, "bearish": bearish}


def generate_signal(composite, val_score, tech_score, right_count, judgment):
    """信号映射 (截图图6精确对应):
      85~100: 极强买入 → 重仓布局
      70~84:  强买入 → 分批建仓
      60~69:  中性偏多 → 轻仓试探,等待信号共振
      45~59:  中性观望 → 持仓不动
      30~44:  偏贵信号 → 减仓或空仓
      <30:    高估警示 → 清仓规避风险
    """
    if composite >= 85:
        sig, pos, color = "极强买入", "重仓布局(70-90%)", "#dc2626"
    elif composite >= 70:
        sig, pos, color = "强买入", "分批建仓(50-70%)", "#ef4444"
    elif composite >= 60:
        sig, pos, color = "中性偏多", "轻仓试探(20-40%)", "#f59e0b"
    elif composite >= 45:
        sig, pos, color = "中性观望", "持仓不动(10-20%)", "#94a3b8"
    elif composite >= 30:
        sig, pos, color = "偏贵信号", "减仓或空仓等待(0-10%)", "#22c55e"
    else:
        sig, pos, color = "高估警示", "清仓规避风险(0%)", "#16a34a"

    # 买入触发条件
    buy_confirm = []
    if right_count >= 2:
        buy_confirm.append("≥2个技术指标右侧确认")
    if tech_score >= 28:  # 技术面70%+
        buy_confirm.append("技术面改善明显")
    if val_score >= 42:  # 估值面70%+
        buy_confirm.append("估值面充裕")
    buy_triggered = composite >= 60 and val_score >= 36 and right_count >= 1

    # 卖出触发
    sell_reasons = []
    if composite < 35:
        sell_reasons.append("综合评分进入高估警示区")
    if val_score < 24:
        sell_reasons.append("估值面恶化")
    sell_triggered = len(sell_reasons) > 0

    return {"signal": sig, "position": pos, "color": color,
            "buy_triggered": buy_triggered, "buy_confirm": buy_confirm,
            "sell_triggered": sell_triggered, "sell_reasons": sell_reasons,
            "right_count": right_count, "judgment": judgment}


# ======================== 历史分数回溯 ========================
def compute_historical_scores(klines):
    """回溯自2026年1月1日起每天的综合评分.
    对每个交易日, 用截止该日的全量数据计算估值分+技术分.
    返回: [{date, price, val_score, tech_score, total, signal_name}, ...]
    """
    # 找2026年1月1日后的第一个交易日
    start_idx = 0
    target = "20260101"
    for i, k in enumerate(klines):
        if k["date"] >= target:
            start_idx = i
            break

    records = []
    total_bars = len(klines)
    for i in range(start_idx, total_bars):
        k = klines[i]
        date = k["date"]
        closes_slice = [kk["close"] for kk in klines[:i+1]]
        highs_slice = [kk["high"] for kk in klines[:i+1]]
        lows_slice = [kk["low"] for kk in klines[:i+1]]
        vols_slice = [kk["volume"] for kk in klines[:i+1]]

        val = score_valuation(closes_slice)
        tech = score_technical(closes_slice, highs_slice, lows_slice, vols_slice)
        total = round(val["score"] + tech["score"], 1)
        right_count = tech["right_count"]

        # 信号映射
        if total >= 85:
            sig = "极强买入"
        elif total >= 70:
            sig = "强买入"
        elif total >= 60:
            sig = "中性偏多"
        elif total >= 45:
            sig = "中性观望"
        elif total >= 30:
            sig = "偏贵信号"
        else:
            sig = "高估警示"

        records.append({
            "date": date,
            "price": k["close"],
            "val_score": round(val["score"], 1),
            "tech_score": round(tech["score"], 1),
            "total": total,
            "right_count": right_count,
            "signal": sig,
        })

        # 进度提示每100条
        if (i - start_idx) % 100 == 0:
            done = i - start_idx + 1
            total_days = total_bars - start_idx
            print(f"  [历史回溯] {date} 分数{total:.1f}(估值{val['score']:.0f}/技术{tech['score']:.0f}) [{done}/{total_days}]")

    print(f"  [历史回溯] 完成! 共{len(records)}个交易日")
    return records


# ======================== HTML仪表盘生成 ========================
def generate_html(result, klines, quotes, hist_records=None):
    """生成HTML v4 — 含历史分数回溯 + DOMContentLoaded修复 + 数据时间戳"""
    comp = result["composite_score"]
    sig = result["signal"]
    dims = result["dimensions"]
    val = dims["valuation"]
    tech = dims["technical"]
    jdg = result["judgment"]

    # K线数据 (最近150根)
    ck = klines[-150:]
    dates = [k['date'][:4]+"-"+k['date'][4:6]+"-"+k['date'][6:] for k in ck]
    ohlc = [[k["open"], k["close"], k["low"], k["high"]] for k in ck]
    ac = [k["close"] for k in klines]
    ma20d, ma60d, ma120d, ma250d, bb_u, bb_l = [], [], [], [], [], []
    for i in range(len(ck)):
        idx = len(klines)-len(ck)+i
        ma20d.append(round(sum(ac[idx-19:idx+1])/20,2) if idx>=19 else None)
        ma60d.append(round(sum(ac[idx-59:idx+1])/60,2) if idx>=59 else None)
        ma120d.append(round(sum(ac[idx-119:idx+1])/120,2) if idx>=119 else None)
        ma250d.append(round(sum(ac[idx-249:idx+1])/250,2) if idx>=249 else None)
        if idx>=19:
            w=ac[idx-19:idx+1];mid=sum(w)/20;var=sum((x-mid)**2 for x in w)/20;std=math.sqrt(var)
            bb_u.append(round(mid+2*std,2));bb_l.append(round(mid-2*std,2))
        else: bb_u.append(None);bb_l.append(None)

    dif,dea,hist = calc_macd_full(ac)
    md,me,mh=[],[],[]
    for i in range(len(ck)):
        idx=len(klines)-len(ck)+i
        md.append(round(dif[idx],2) if dif[idx] is not None else None)
        me.append(round(dea[idx],2) if dea[idx] is not None else None)
        mh.append(round(hist[idx],2) if hist[idx] is not None else None)
    rsi_d=[]
    for i in range(len(ck)):
        idx=len(klines)-len(ck)+i
        rsi_d.append(round(calc_rsi(ac[:idx+1],14),1) if idx>=14 else None)

    radar = [round(val["score"]/60*100,1), round(tech["score"]/40*100,1),
             round(tech["right_count"]/3*100,1), 0, 0]

    # 表格行
    def make_row(dd):
        pct=dd["score"]/dd["max"]*100
        bc="#dc2626" if pct>=65 else ("#f59e0b" if pct>=40 else "#22c55e")
        return ('<tr><td>'+dd["name"]+'</td><td>'+dd["value"]+'</td>'
                '<td><div class="sb"><div class="sf" style="width:'+str(round(pct))+'%;background:'+bc+'"></div></div></td>'
                '<td><b>'+str(round(dd["score"],1))+'</b>/'+str(dd["max"])+'</td>'
                '<td class="ds">'+dd["desc"]+'</td></tr>')

    vrows="".join(make_row(dd) for dd in val["details"])
    vrows=('<tr class="dh"><td colspan="5" style="background:#fef2f2;font-weight:700;color:#dc2626">'
           '估值维度 — '+str(round(val["score"],1))+'/60</td></tr>')+vrows

    trows="".join(make_row(dd) for dd in tech["details"])
    trows=('<tr class="dh"><td colspan="5" style="background:#eff6ff;font-weight:700;color:#2563eb">'
           '技术面维度 — '+str(round(tech["score"],1))+'/40</td></tr>')+trows

    blist="".join("<li>"+b+"</li>" for b in jdg["bullish"])
    alist="".join("<li>"+a+"</li>" for a in jdg["bearish"])

    sig_rows=[("85~100","极强买入","#dc2626","重仓布局,加大单次买入比例"),("70~84","强买入","#22c55e","分批建仓,正常节奏布局"),
               ("60~69","中性偏多","#f59e0b","轻仓试探,等待信号共振"),("45~59","中性观望","#94a3b8","持仓不动,暂停新增"),
               ("30~44","偏贵信号","#f97316","减仓或空仓等待"),("<30","高估警示","#dc2626","清仓规避风险")]
    stable=""
    for sc,sig_n,c,adv in sig_rows:
        hl="background:#fee" if str(int(comp))[:2]==sc[:2] else ""
        stable+=('<tr style="'+hl+'"><td>'+sc+'</td><td style="color:'+c+';font-weight:700">'+sig_n+'</td><td>'+adv+'</td></tr>')

    bh="、".join(sig["buy_confirm"]) if sig["buy_confirm"] else '<span style="color:#999">无</span>'
    sh="；".join(sig["sell_reasons"]) if sig["sell_reasons"] else '<span style="color:#999">无</span>'
    tc="trigger-buy" if sig["buy_triggered"] else ("trigger-sell" if sig["sell_triggered"] else "trigger-neutral")
    tt="OK 买入信号已触发" if sig["buy_triggered"] else ("! 卖出条件出现" if sig["sell_triggered"] else "... 等待信号共振")

    div_yield=val["div_yield"]
    hq=quotes['hq_date'][:4]+"-"+quotes['hq_date'][4:6]+"-"+quotes['hq_date'][6:]
    price=quotes["current"]

    # 标签状态
    pulse_tag = "tag-g" if tech['pulse']['reversed'] else "tag-r"
    pulse_txt = "反转" if tech['pulse']['reversed'] else "压制"
    andean_tag = "tag-g" if tech['andean']['reversed'] else "tag-r"
    andean_txt = "反转" if tech['andean']['reversed'] else "消失"
    sq_tag = "tag-g" if tech['sq']['reversed'] else "tag-r"
    sq_txt = "向上" if tech['sq']['reversed'] else "向下"

    pct_cls = "down" if quotes['change_pct']<0 else "up"
    c20_cls = "down" if quotes['change_20d']<0 else "up"
    cytd_cls = "down" if quotes['change_ytd']<0 else "up"
    val_ok = "OK" if val['score']>=36 else "X"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ========== 历史分数数据 ==========
    hist_dates_json = "[]"
    hist_prices_json = "[]"
    hist_total_json = "[]"
    hist_val_json = "[]"
    hist_tech_json = "[]"
    hist_table_rows = ""
    hist_summary = ""

    if hist_records:
        hist_dates = [r["date"][:4]+"-"+r["date"][4:6]+"-"+r["date"][6:] for r in hist_records]
        hist_prices = [r["price"] for r in hist_records]
        hist_total = [r["total"] for r in hist_records]
        hist_val = [r["val_score"] for r in hist_records]
        hist_tech = [r["tech_score"] for r in hist_records]
        hist_dates_json = json.dumps(hist_dates)
        hist_prices_json = json.dumps(hist_prices)
        hist_total_json = json.dumps(hist_total)
        hist_val_json = json.dumps(hist_val)
        hist_tech_json = json.dumps(hist_tech)

        # 表格: 只显示最近30个交易日
        last30 = hist_records[-30:] if len(hist_records) > 30 else hist_records
        for r in reversed(last30):
            dt = r["date"][:4]+"-"+r["date"][4:6]+"-"+r["date"][6:]
            sig_col = "#dc2626" if r["total"]>=70 else ("#f59e0b" if r["total"]>=60 else ("#94a3b8" if r["total"]>=45 else ("#22c55e" if r["total"]>=30 else "#16a34a")))
            pr_cls = "up" if len(hist_records) > 1 and r["price"] >= hist_records[-2]["price"] else "down"
            hist_table_rows += ('<tr><td>'+dt+'</td><td class="vl '+pr_cls+'">'+str(r["price"])+'</td>'
                '<td>'+str(r["val_score"])+'</td><td>'+str(r["tech_score"])+'</td>'
                '<td><b>'+str(r["total"])+'</b></td>'
                '<td style="color:'+sig_col+';font-weight:600">'+r["signal"]+'</td></tr>')

        # 统计摘要
        first = hist_records[0]
        last_r = hist_records[-1]
        n = len(hist_records)
        # 分数变化
        score_chg = last_r["total"] - first["total"]
        price_chg_pct = (last_r["price"] - first["price"]) / first["price"] * 100
        # 统计各信号占比
        sig_counts = {}
        for r in hist_records:
            sig_counts[r["signal"]] = sig_counts.get(r["signal"], 0) + 1
        sig_pct_str = " | ".join(f"{k}: {v/n*100:.0f}%" for k,v in sorted(sig_counts.items(), key=lambda x:-x[1]))
        # 最高/低分
        max_r = max(hist_records, key=lambda r: r["total"])
        min_r = min(hist_records, key=lambda r: r["total"])
        hist_summary = (
            f'<div class="hist-summary">'
            f'<span><b>回溯期:</b> {first["date"][:4]}-{first["date"][4:6]}-{first["date"][6:]} ~ {last_r["date"][:4]}-{last_r["date"][4:6]}-{last_r["date"][6:]} ({n}个交易日)</span>'
            f'<span><b>价格区间:</b> {min(r["price"] for r in hist_records):.0f} ~ {max(r["price"] for r in hist_records):.0f} (当前{last_r["price"]:.0f}, 期间{price_chg_pct:+.1f}%)</span>'
            f'<span><b>分数区间:</b> {min_r["total"]} ~ {max_r["total"]} (当前{last_r["total"]}, 从{first["total"]}{"+" if score_chg>=0 else ""}{score_chg:+.1f})</span>'
            f'<span><b>信号分布:</b> {sig_pct_str}</span>'
            f'<span><b>最高分日:</b> {max_r["date"][:4]}-{max_r["date"][4:6]}-{max_r["date"][6:]} ({max_r["total"]}分, {max_r["signal"]})</span>'
            f'<span><b>最低分日:</b> {min_r["date"][:4]}-{min_r["date"][4:6]}-{min_r["date"][6:]} ({min_r["total"]}分, {min_r["signal"]})</span>'
            f'</div>')

    # ========== JS ECharts代码 ==========
    _js_charts = (
        "document.addEventListener('DOMContentLoaded',function(){"
        "try{"
        # 1. K线
        "var kl=echarts.init(document.getElementById('kl'));"
        "kl.setOption({backgroundColor:'transparent',"
        "legend:{data:['K线','SMA60','SMA120','SMA250','布林上轨','布林下轨'],top:0,textStyle:{fontSize:11}},"
        "grid:{left:'8%',right:'5%',top:'12%',bottom:'15%'},"
        "xAxis:{type:'category',data:"+json.dumps(dates)+",axisLabel:{fontSize:10,interval:24}},"
        "yAxis:{scale:true,axisLabel:{fontSize:10}},"
        "dataZoom:[{type:'inside',start:55,end:100},{type:'slider',start:55,end:100,height:20,bottom:5}],"
        "series:["
        "{name:'K线',type:'candlestick',data:"+json.dumps(ohlc)+",itemStyle:{color:'#dc2626',color0:'#16a34a',borderColor:'#dc2626',borderColor0:'#16a34a'}},"
        "{name:'SMA60',type:'line',data:"+json.dumps(ma60d)+",smooth:true,symbol:'none',lineStyle:{width:1.5,color:'#f59e0b'}},"
        "{name:'SMA120',type:'line',data:"+json.dumps(ma120d)+",smooth:true,symbol:'none',lineStyle:{width:1.5,color:'#3b82f6'}},"
        "{name:'SMA250',type:'line',data:"+json.dumps(ma250d)+",smooth:true,symbol:'none',lineStyle:{width:2,color:'#8b5cf6'}},"
        "{name:'布林上轨',type:'line',data:"+json.dumps(bb_u)+",smooth:true,symbol:'none',lineStyle:{width:1,type:'dashed',color:'#94a3b8'}},"
        "{name:'布林下轨',type:'line',data:"+json.dumps(bb_l)+",smooth:true,symbol:'none',lineStyle:{width:1,type:'dashed',color:'#94a3b8'}}"
        "]});console.log('[OK] K线图加载完成, %d条',"+str(len(dates))+");"
        "}catch(e){console.error('[ERR] K线图:',e);}"

        "try{"
        # 2. 雷达
        "var rd=echarts.init(document.getElementById('rd'));"
        "rd.setOption({backgroundColor:'transparent',"
        "radar:{indicator:[{name:'估值(60->100)',max:100},{name:'技术(40->100)',max:100},"
        "{name:'右侧确认(/3)',max:100},{name:'利多因素',max:100},{name:'利空因素(逆)',max:100}],"
        "radius:'65%',axisName:{fontSize:12,color:'#475569'}},"
        "series:[{type:'radar',data:[{value:"+json.dumps(radar)+",name:'当前'}],"
        "areaStyle:{color:'rgba(220,38,38,0.2)'},lineStyle:{color:'#dc2626',width:2},"
        "itemStyle:{color:'#dc2626'},label:{show:true,fontSize:12,fontWeight:'bold'}}]});"
        "console.log('[OK] 雷达图加载完成');"
        "}catch(e){console.error('[ERR] 雷达图:',e);}"

        "try{"
        # 3. MACD
        "var mc=echarts.init(document.getElementById('mc'));"
        "mc.setOption({backgroundColor:'transparent',"
        "legend:{data:['DIF','DEA','MACD'],top:0,textStyle:{fontSize:11}},"
        "grid:{left:'10%',right:'5%',top:'15%',bottom:'12%'},"
        "xAxis:{type:'category',data:"+json.dumps(dates)+",axisLabel:{fontSize:10,interval:24}},"
        "yAxis:{axisLabel:{fontSize:10}},"
        "dataZoom:[{type:'inside',start:55,end:100}],"
        "series:["
        "{name:'DIF',type:'line',data:"+json.dumps(md)+",symbol:'none',lineStyle:{width:1.5,color:'#f59e0b'}},"
        "{name:'DEA',type:'line',data:"+json.dumps(me)+",symbol:'none',lineStyle:{width:1.5,color:'#3b82f6'}},"
        "{name:'MACD',type:'bar',data:"+json.dumps(mh)+",itemStyle:{color:function(p){return p.value>=0?'#dc2626':'#16a34a'}}}"
        "]});console.log('[OK] MACD加载完成');"
        "}catch(e){console.error('[ERR] MACD:',e);}"

        "try{"
        # 4. RSI
        "var rs=echarts.init(document.getElementById('rs'));"
        "rs.setOption({backgroundColor:'transparent',"
        "grid:{left:'10%',right:'5%',top:'8%',bottom:'12%'},"
        "xAxis:{type:'category',data:"+json.dumps(dates)+",axisLabel:{fontSize:10,interval:24}},"
        "yAxis:{min:0,max:100,axisLabel:{fontSize:10}},"
        "dataZoom:[{type:'inside',start:55,end:100}],"
        "series:[{name:'RSI',type:'line',data:"+json.dumps(rsi_d)+",symbol:'none',lineStyle:{width:2,color:'#8b5cf6'},"
        "markLine:{symbol:'none',data:["
        "{yAxis:30,lineStyle:{color:'#dc2626',type:'dashed'},label:{formatter:'Oversold 30',fontSize:10}},"
        "{yAxis:70,lineStyle:{color:'#16a34a',type:'dashed'},label:{formatter:'Overbought 70',fontSize:10}}"
        "]}}]});console.log('[OK] RSI加载完成');"
        "}catch(e){console.error('[ERR] RSI:',e);}"

        "window.addEventListener('resize',function(){try{kl.resize()}catch(e){}try{rd.resize()}catch(e){}try{mc.resize()}catch(e){}try{rs.resize()}catch(e){}});"
        "});")

    # 历史分数图表JS
    _js_hist = ""
    if hist_records and len(hist_records) > 1:
        _js_hist = (
            "document.addEventListener('DOMContentLoaded',function(){try{"
            "var hs=echarts.init(document.getElementById('hs'));"
            "hs.setOption({backgroundColor:'transparent',"
            "tooltip:{trigger:'axis',axisPointer:{type:'cross'}},"
            "legend:{data:['综合评分','指数价格(归一化)','估值分','技术分'],top:0,textStyle:{fontSize:11}},"
            "grid:{left:'8%',right:'5%',top:'14%',bottom:'12%'},"
            "xAxis:{type:'category',data:"+hist_dates_json+",axisLabel:{fontSize:9,interval:"+str(max(1, len(hist_records)//12))+"}},"
            "dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,height:20,bottom:5}],"
            "yAxis:[{type:'value',name:'综合分',min:0,max:100,axisLabel:{fontSize:10}},"
            "{type:'value',name:'价格(归一)',min:0,max:100,axisLabel:{fontSize:10}}],"
            "series:["
            "{name:'综合评分',type:'line',data:"+hist_total_json+",smooth:true,symbol:'none',lineStyle:{width:2,color:'#dc2626'},"
            "areaStyle:{color:'rgba(220,38,38,0.1)'},z:2,"
            "markLine:{silent:true,data:[{yAxis:85,lineStyle:{color:'#dc2626',type:'dashed'},label:{formatter:'极强买入85',fontSize:9}},"
            "{yAxis:70,lineStyle:{color:'#ef4444',type:'dashed'},label:{formatter:'强买入70',fontSize:9}},"
            "{yAxis:60,lineStyle:{color:'#f59e0b',type:'dashed'},label:{formatter:'中性偏多60',fontSize:9}},"
            "{yAxis:45,lineStyle:{color:'#94a3b8',type:'dashed'},label:{formatter:'中性45',fontSize:9}},"
            "{yAxis:30,lineStyle:{color:'#22c55e',type:'dashed'},label:{formatter:'偏贵30',fontSize:9}}]}},"
            "{name:'指数价格(归一化)',type:'line',data:"+json.dumps([max(0,min(100,round((p-min(hist_prices))/(max(hist_prices)-min(hist_prices))*100,1))) for p in hist_prices])+","
            "smooth:true,symbol:'none',lineStyle:{width:1.5,color:'#3b82f6',type:'dotted'},yAxisIndex:1,z:1},"
            "{name:'估值分',type:'line',data:"+hist_val_json+",smooth:true,symbol:'none',lineStyle:{width:1,color:'#f59e0b',opacity:0.5}},"
            "{name:'技术分',type:'line',data:"+hist_tech_json+",smooth:true,symbol:'none',lineStyle:{width:1,color:'#8b5cf6',opacity:0.5}}"
            "]});console.log('[OK] 历史分数图加载完成');"
            "}catch(e){console.error('[ERR] 历史分数图:',e);}});")

    # 更新时间字符串
    update_time = "行情" + hq + " | 策略生成 " + now_str

    # HTML模板
    html = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>红利低波100(930955) 多维评分策略 v4</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script>
if(typeof echarts==='undefined'){
  var sc=document.createElement('script');
  sc.src='https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js';
  sc.onload=function(){console.log('[OK] ECharts加载(备选CDN)');};
  sc.onerror=function(){console.error('[ERR] ECharts所有CDN均失败');
    document.querySelectorAll('.cht,.cht-s,.cht-xl').forEach(function(el){
      el.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#dc2626;font-size:14px">\u2728 ECharts\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u8fde\u63a5</div>';
    });
  };
  document.head.appendChild(sc);
}else{console.log('[OK] ECharts已加载');}
</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f1f5f9;color:#1e293b;padding:16px}
.ct{max-width:1440px;margin:0 auto}
.hd{background:linear-gradient(135deg,#1e293b,#334155);color:#fff;padding:24px 32px;border-radius:16px 16px 0 0;display:flex;justify-content:space-between;align-items:center}
.hd h1{font-size:22px;font-weight:700}
.hd .sub{font-size:13px;color:#94a3b8;margin-top:4px}
.mb{background:#fff;padding:24px 32px;border-radius:0 0 16px 16px;box-shadow:0 4px 6px rgba(0,0,0,.05)}
.sc{display:grid;grid-template-columns:300px 1fr 280px;gap:24px;margin-bottom:24px}
.sc-c{text-align:center;padding:24px;border-radius:12px;background:#f8fafc;border:3px solid [[SIG_COLOR]]}
.sc-c .num{font-size:64px;font-weight:800;color:[[SIG_COLOR]];line-height:1}
.sc-c .lbl{font-size:13px;color:#64748b;margin-top:8px}
.badge{display:inline-block;padding:10px 28px;border-radius:10px;background:[[SIG_COLOR]];color:#fff;font-size:20px;font-weight:700;margin-top:12px}
.pos{font-size:13px;color:#475569;margin-top:8px}
.trig{padding:20px;border-radius:12px}
.trig.trigger-buy{background:#f0fdf4;border:1px solid #bbf7d0}
.trig.trigger-sell{background:#fef2f2;border:1px solid #fecaca}
.trig.trigger-neutral{background:#fffbeb;border:1px solid #fde68a}
.tt{font-size:17px;font-weight:700;margin-bottom:12px}
.ti{font-size:13px;color:#475569;padding:3px 0}
.pc{padding:20px;border-radius:12px;background:#f8fafc}
.pc h3{font-size:14px;color:#64748b;margin-bottom:12px}
.pr{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #e2e8f0;font-size:14px}
.pr:last-child{border-bottom:none}
.pr .lb{color:#64748b}
.pr .vl{font-weight:600}
.up{color:#dc2626}
.down{color:#16a34a}
.cg{display:grid;grid-template-columns:1fr 340px;gap:16px;margin-bottom:24px}
.cb{background:#f8fafc;border-radius:12px;padding:16px}
.cb h3{font-size:14px;color:#475569;margin-bottom:8px;padding-left:4px}
.cht{width:100%;height:420px}
.cht-s{width:100%;height:200px}
.cht-xl{width:100%;height:400px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1e293b;color:#fff;padding:10px 12px;text-align:left}
td{padding:8px 12px;border-bottom:1px solid #e2e8f0}
.dh td{background:#f8fafc;font-weight:700}
.ds{color:#94a3b8;font-size:12px}
.sb{width:80px;height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden}
.sf{height:100%;border-radius:4px}
.jg{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.jg-bull{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:18px}
.jg-bear{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:18px}
.jg h4{font-size:15px;margin-bottom:10px}
.jg ul{list-style:none;padding:0}
.jg li{padding:4px 0;font-size:13px}
.jg-bull li::before{content:"\u25cf ";color:#16a34a}
.jg-bear li::before{content:"\u25cf ";color:#f59e0b}
.sig-tbl{margin-top:12px;background:white;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0}
.sig-tbl table{font-size:13px}
.sig-tbl th{background:#f8fafc;color:#475569}
.es{background:#f8fafc;border-radius:12px;padding:20px;margin-top:16px}
.es h3{font-size:16px;margin-bottom:12px}
.eg{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.ec{background:#fff;padding:16px;border-radius:8px;border-left:4px solid [[SIG_COLOR]]}
.ec .code{font-size:13px;color:#64748b}
.ec .nm{font-size:15px;font-weight:600;margin:4px 0}
.ec .act{font-size:14px;color:[[SIG_COLOR]];font-weight:600}
.warn{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:14px 16px;font-size:12px;color:#92400e;margin-top:16px}
.ft{text-align:center;padding:16px;color:#94a3b8;font-size:12px}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#fff}
.tag-r{background:#dc2626}.tag-g{background:#16a34a}.tag-y{background:#f59e0b}.tag-gray{background:#94a3b8}
.update-time{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:8px 16px;font-size:12px;color:#64748b;text-align:center;margin-top:12px}
.hist-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px;background:#f8fafc;border-radius:8px;font-size:12px;color:#475569;margin-bottom:12px}
.hist-scroll{max-height:420px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px}
.hist-scroll table th{position:sticky;top:0;z-index:1}
</style></head><body><div class="ct">
<div class="hd"><div><h1>红利低波100指数(930955) 多维评分策略 v4</h1>
<div class="sub">估值(60分)+技术(40分)=100分 | 全历史[[NKLINE]]日 | 对齐"是强哥啊"体系 | 右侧买入理念</div></div>
<div style="font-size:13px;color:#cbd5e1">[[HQ_DATE]] [[SIG_NAME]]</div></div>
<div class="mb">

<div class="update-time">\u23f0 [[UPDATE_TIME]]</div>

<div class="sc">
<div class="sc-c"><div class="lbl">综合值博率评分</div><div class="num">[[COMP_SCORE]]</div><div class="lbl">/ 100</div>
<div class="badge">[[SIG_NAME]]</div><div class="pos">建议仓位: [[SIG_POS]]</div>
<div style="margin-top:12px;font-size:12px;color:#94a3b8">得分越高代表值博率越高 | 60分以上可考虑分批布局</div></div>
<div class="trig [[TRIG_CLASS]]"><div class="tt">[[TRIG_TITLE]]</div>
<div class="ti"><b>核心规则:</b>估值支撑充裕(>=36分) + 技术右侧确认(>=1个) = 可轻仓试探</div>
<div class="ti">当前: 估值[[VAL_SCORE]]/60 [[VAL_OK]] | 技术[[TECH_SCORE]]/40 | 右侧确认[[RIGHT_COUNT]]/3</div>
<div class="ti" style="padding-left:16px">买入确认: [[BUY_CONFIRM]]</div>
<div class="ti">卖出条件: [[SELL_REASONS]]</div>
<div style="margin-top:10pt"><b>三大技术指标状态:</b></div>
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
<span class="tag [[PULSE_TAG]]">\u9ea6\u51b2MACD:[[PULSE_TXT]]</span>
<span class="tag [[ANDEAN_TAG]]">\u52a8\u80fd:[[ANDEAN_TXT]]</span>
<span class="tag [[SQ_TAG]]">\u6324\u538b:[[SQ_TXT]]</span></div></div>
<div class="pc"><h3>\u5b9e\u65f6\u884c\u60c5</h3>
<div class="pr"><span class="lb">\u73b0\u4ef7</span><span class="vl">[[PRICE]]</span></div>
<div class="pr"><span class="lb">\u6da8\u8dcc\u5e45</span><span class="vl [[PCT_CLS]]">[[CHANGE_PCT]]%</span></div>
<div class="pr"><span class="lb">20\u65e5\u6da8\u8dcc</span><span class="vl [[C20_CLS]]">[[CHANGE_20D]]%</span></div>
<div class="pr"><span class="lb">\u5e74\u521d\u81f3\u4eca</span><span class="vl [[CYTD_CLS]]">[[CHANGE_YTD]]%</span></div>
<div class="pr"><span class="lb">股息率(D/P2)</span><span class="vl up">[[DIV_YIELD]]%</span></div>
<div class="pr"><span class="lb">\u80a1\u503a\u5229\u5dee</span><span class="vl up">[[SPREAD]]%</span></div>
<div class="pr"><span class="lb">CN10Y(实时)</span><span class="vl up">[[CN10Y]]%</span></div></div></div>

<!-- 图表区 -->
<div class="cg"><div class="cb"><h3>K线 + SMA60/120/250 + 布林带</h3><div id="kl" class="cht"></div></div>
<div class="cb"><h3>评分雷达(估值/技术/右侧)</h3><div id="rd" class="cht"></div></div></div>
<div class="cg" style="grid-template-columns:1fr 1fr"><div class="cb"><h3>MACD</h3><div id="mc" class="cht-s"></div></div>
<div class="cb"><h3>RSI(14)</h3><div id="rs" class="cht-s"></div></div></div>

<!-- 估值明细 -->
<div class="cb" style="margin-bottom:16px"><h3>(1) 量化得分分解 — 估值维度 (总分60)</h3>
<table><thead><tr><th>指标</th><th>当前值</th><th>得分条</th><th>得分</th><th>说明</th></tr></thead><tbody>[[VROWS]]</tbody></table></div>

<!-- 技术明细 -->
<div class="cb" style="margin-bottom:16px"><h3>(1) 量化得分分解 — 技术面维度 (总分40)</h3>
<table><thead><tr><th>指标</th><th>当前值</th><th>得分条</th><th>得分</th><th>说明</th></tr></thead><tbody>[[TROWS]]</tbody></table></div>

<!-- 综合研判 -->
<div class="jg"><div class="jg-bull"><h4 style="color:#16a34a">利多因素</h4><ul>[[BLIST]]</ul></div>
<div class="jg-bear"><h4 style="color:#d97706">利空因素</h4><ul>[[ALIST]]</ul></div></div>

<!-- 信号参考表 -->
<div class="sig-tbl"><h3 style="padding:12px 16px;font-size:15px;background:#f8fafc">评分信号参考 (对齐"是强哥啊"体系)</h3>
<table><thead><tr><th>总分</th><th>信号</th><th>建议</th></tr></thead><tbody>[[STABLE]]</tbody></table></div>

<!-- 数据来源说明 -->
<div style="margin-top:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px">
<h3 style="font-size:15px;margin-bottom:10px">各指标数据来源</h3>
<table style="font-size:12px">
<thead><tr><th>指标</th><th>数据来源</th><th>API/接口</th><th>统计周期</th></tr></thead>
<tbody>
<tr><td>股息率(D/P2)</td><td>中证指数官网</td><td>akshare stock_zh_index_value_csindex</td><td>日频, 最新1个交易日</td></tr>
<tr><td>股债利差</td><td>股息率+CN10Y</td><td>akshare 中证估值 + bond_zh_us_rate</td><td>实时计算</td></tr>
<tr><td>10Y国债收益率</td><td>akshare 债券利率</td><td>akshare bond_zh_us_rate</td><td>日频, 最新交易日</td></tr>
<tr><td>PB百分位</td><td>指数K线收盘价</td><td>通达信TDX setcode=62</td><td>全历史1548日(2020-至今)</td></tr>
<tr><td>ROE代理</td><td>指数K线MA60/MA250</td><td>通达信TDX setcode=62</td><td>60日/250日均线比</td></tr>
<tr><td>价格与均线</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>SMA60/120/250</td></tr>
<tr><td>斐波那契</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>最近250交易日</td></tr>
<tr><td>脉冲MACD</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>MACD(12,26,9)+EMA5</td></tr>
<tr><td>动能Andean</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>ROC12, 最近13日</td></tr>
<tr><td>挤压动量</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>布林(20,2)+Keltner+ATR14</td></tr>
<tr><td>RSI(14)</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>最近14日涨跌幅</td></tr>
<tr><td>成交量</td><td>指数K线</td><td>通达信TDX setcode=62</td><td>近5日/前5日对比</td></tr>
<tr><td>实时行情</td><td>通达信指数行情</td><td>tdx_quotes setcode=62</td><td>实时</td></tr>
<tr><td>历史分数回溯</td><td>全指标回算</td><td>上述API逐日计算</td><td>2026-01-01至今 114日</td></tr>
</tbody></table>
</div>

<!-- 历史分数回溯 -->
[[HIST_SECTION]]

<!-- ETF操作 -->
<div class="es"><h3>ETF操作建议</h3><div class="eg">
<div class="ec"><div class="code">[[ETF_CODE]]</div><div class="nm">[[ETF_NAME]]</div><div class="act">操作: [[SIG_NAME]] | 仓位: [[SIG_POS]]</div></div>
<div class="ec"><div class="code">[[ETF2_CODE]]</div><div class="nm">[[ETF2_NAME]]</div><div class="act">操作: [[SIG_NAME]] | 仓位: [[SIG_POS]]</div></div></div>
<div class="warn">免责声明: 本策略基于"是强哥啊"量化体系构建(AI复刻版)，仅供参考不构成投资建议。核心理念为右侧买入: 估值便宜但脉冲MACD/动能/挤压三指标未反转时维持观望，避免左侧抄底被挂半山腰。<b>股息率数据来源: AKShare直采中证官网(股息率2/D/P2)</b>，PE/PB也同源。CN10Y取配置基准值，实际请以基金公告和实时市场数据为准。投资有风险，入市需谨慎。</div>
</div><div class="ft">红利低波100(930955)多维评分策略 v4.0 | 全历史[[NKLINE]]日 | 对齐"是强哥啊"体系(7张看板) | [[NOW_STR]] 生成</div>
</div>
<script>
[[JS_CHARTS]]
[[JS_HIST]]
</script></body></html>'''

    # 历史分数板块
    hist_section = ""
    if hist_records and len(hist_records) > 1:
        hist_section = (
            '<div class="cb" style="margin-bottom:16px">'
            '<h3>\u5386\u53f2\u56de\u6eaf: 综合评分走势 (2026\u5e741\u6708\u4ee5\u6765)</h3>'
            + hist_summary
            + '<div id="hs" class="cht-xl"></div>'
            + '<div style="margin-top:12px"><p style="font-size:12px;color:#94a3b8;margin-bottom:8px">\u7ea2\u8272\u5b9e\u7ebf=综合评分 | \u84dd\u8272\u865a\u7ebf=指数价格(归一化) | \u9ec4\u8272\u7ebf=估值分 | \u7d2b\u8272\u7ebf=技术分 | \u6c34\u5e73\u865a\u7ebf=信号阈值(85/70/60/45/30)</p>'
            + '<div class="hist-scroll"><table><thead><tr><th>日期</th><th>价格</th><th>估值分</th><th>技术分</th><th>总分</th><th>信号</th></tr></thead><tbody>'
            + hist_table_rows
            + '</tbody></table></div></div></div>')

    # 替换所有占位符
    replacements = {
        "[[SIG_COLOR]]": sig['color'],
        "[[SIG_NAME]]": sig['signal'],
        "[[SIG_POS]]": sig['position'],
        "[[NKLINE]]": str(len(klines)),
        "[[HQ_DATE]]": hq,
        "[[COMP_SCORE]]": str(round(comp)),
        "[[TRIG_CLASS]]": tc,
        "[[TRIG_TITLE]]": tt,
        "[[VAL_SCORE]]": str(round(val['score'])),
        "[[VAL_OK]]": val_ok,
        "[[TECH_SCORE]]": str(round(tech['score'])),
        "[[RIGHT_COUNT]]": str(sig['right_count']),
        "[[BUY_CONFIRM]]": bh,
        "[[SELL_REASONS]]": sh,
        "[[PULSE_TAG]]": pulse_tag,
        "[[PULSE_TXT]]": pulse_txt,
        "[[ANDEAN_TAG]]": andean_tag,
        "[[ANDEAN_TXT]]": andean_txt,
        "[[SQ_TAG]]": sq_tag,
        "[[SQ_TXT]]": sq_txt,
        "[[PRICE]]": str(round(price, 2)),
        "[[PCT_CLS]]": pct_cls,
        "[[CHANGE_PCT]]": str(round(quotes['change_pct'], 2)),
        "[[C20_CLS]]": c20_cls,
        "[[CHANGE_20D]]": str(round(quotes['change_20d'], 2)),
        "[[CYTD_CLS]]": cytd_cls,
        "[[CHANGE_YTD]]": str(round(quotes['change_ytd'], 2)),
        "[[DIV_YIELD]]": str(round(div_yield, 2)),
        "[[SPREAD]]": str(round(val['spread'], 3)),
        "[[CN10Y]]": str(round(RISK_FREE_RATE, 4)),
        "[[VROWS]]": vrows,
        "[[TROWS]]": trows,
        "[[BLIST]]": blist,
        "[[ALIST]]": alist,
        "[[STABLE]]": stable,
        "[[ETF_CODE]]": ETF_CODE,
        "[[ETF_NAME]]": ETF_NAME,
        "[[ETF2_CODE]]": ETF2_CODE,
        "[[ETF2_NAME]]": ETF2_NAME,
        "[[NOW_STR]]": now_str,
        "[[UPDATE_TIME]]": update_time,
        "[[HIST_SECTION]]": hist_section,
        "[[JS_CHARTS]]": _js_charts,
        "[[JS_HIST]]": _js_hist,
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


# ======================== 主流程 ========================
def main():
    global RISK_FREE_RATE
    print("=" * 66)
    print("红利低波100指数(930955) 多维评分策略 v4 (对齐'是强哥那'体系)")
    print("=" * 66)

    # 加载数据
    klines = load_json(HISTORY_FILE)
    quotes = load_json(QUOTES_FILE)
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]
    price = quotes["current"]
    print(f"\n[1] 数据: {len(klines)}根 ({klines[0]['date']} ~ {klines[-1]['date']}) 现价{price:.2f}")

    # 通过AKShare获取中证官方估值数据(含股息率2/D/P2 + 中国10Y国债收益率)
    print("\n[1b] 获取中证官网估值数据 & CN10Y...")
    try:
        import akshare as ak

        # 指数估值
        df = ak.stock_zh_index_value_csindex(symbol='930955')
        if df is not None and len(df) > 0:
            latest = df.iloc[0]
            div_yield_official = float(latest['股息率2'])
            pe1 = float(latest['市盈率1'])
            pe2 = float(latest['市盈率2'])
            val_date = str(latest['日期'])
            akshare_data = {
                "date": val_date,
                "dividend_yield_official": div_yield_official,
                "pe1": pe1,
                "pe2": pe2,
                "source": "akshare->中证官网"
            }
            with open(REAL_DIV_YIELD_FILE, "w", encoding="utf-8") as f:
                json.dump(akshare_data, f, ensure_ascii=False, indent=2)
            print(f"  ✅ AKShare: 股息率2(D/P2)={div_yield_official}% PE1={pe1} PE2={pe2} 日期={val_date}")

        # 中国10年期国债收益率
        bond_df = ak.bond_zh_us_rate()
        if bond_df is not None and len(bond_df) > 0:
            valid = bond_df[bond_df['中国国债收益率10年'].notna()]
            if len(valid) > 0:
                latest_bond = valid.iloc[-1]
                new_cn10y = float(latest_bond['中国国债收益率10年'])
                if new_cn10y > 0.5:  # AKShare返回的是百分比值如1.7351
                    RISK_FREE_RATE = new_cn10y  # 直接作为百分比
                print(f"  ✅ AKShare: CN10Y={latest_bond['中国国债收益率10年']}% → 策略使用{RISK_FREE_RATE:.4f}%")
    except Exception as e:
        print(f"  ⚠️ AKShare获取失败: {e}，使用缓存数据")

    # 估值维度
    print("\n[2] 估值维度评分(60分):")
    val = score_valuation(closes)
    for d in val["details"]:
        print(f"  [{d['score']:>5}/{d['max']:<2}] {d['name']}: {d['value']}")
    print(f"  => 估值小计: {val['score']}/60")

    # 技术面维度
    print("\n[3] 技术面维度评分(40分):")
    tech = score_technical(closes, highs, lows, volumes)
    for d in tech["details"]:
        print(f"  [{d['score']:>5}/{d['max']:<2}] {d['name']}: {d['value']}")
    print(f"  => 技术小计: {tech['score']}/40 | 右侧确认: {tech['right_count']}/3")

    # 综合评分
    comp = val["score"] + tech["score"]
    print(f"\n[4] 综合得分: {comp:.1f}/100 (估值{val['score']:.0f}+技术{tech['score']:.0f})")

    # 综合研判
    jdg = generate_judgment(val["score"], tech["score"], val["details"], tech["details"], closes)
    print("\n[5] 综合研判:")
    print("  利多因素:")
    for b in jdg["bullish"]:
        print(f"    ✓ {b}")
    print("  利空因素:")
    for a in jdg["bearish"]:
        print(f"    ✗ {a}")

    # 信号
    sig = generate_signal(comp, val["score"], tech["score"], tech["right_count"], jdg)
    print(f"\n[6] 信号: {sig['signal']} | 仓位: {sig['position']} | 右侧确认: {sig['right_count']}/3")
    if sig["buy_triggered"]:
        print(f"  [OK] 买入触发! => {', '.join(sig['buy_confirm'])}")
    if sig["sell_triggered"]:
        print(f"  [!] 卖出条件 => {', '.join(sig['sell_reasons'])}")

    # 历史分数回溯
    print("\n[7] 历史分数回溯 (2026-01-01 ~ 今):")
    hist_records = compute_historical_scores(klines)

    # 生成HTML
    result = {"composite_score": comp, "signal": sig,
              "dimensions": {"valuation": val, "technical": tech},
              "judgment": jdg}
    html = generate_html(result, klines, quotes, hist_records)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[8] HTML已保存: {OUTPUT_HTML}")

    print("\n" + "=" * 66)
    print(f"  综合: {comp:.0f}/100 | {sig['signal']} | 仓位:{sig['position']}")
    print(f"  估值: {val['score']:.0f}/60 | 技术: {tech['score']:.0f}/40 | 右侧: {tech['right_count']}/3")
    print("=" * 66)


if __name__ == "__main__":
    main()
