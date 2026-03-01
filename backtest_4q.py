
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_all_direct_growth_funds_by_category, get_nav_history
from metrics import compute_all_metrics

# --- GLOBAL CONFIG & CACHE ---
STCG_RATE = 0.20
LTCG_RATE = 0.125
SIP_AMOUNT = 10000
NAV_MEMORY_CACHE = {}
ALL_FUNDS_CACHE = {}
BENCH_CACHE = {}

def get_nav_history_cached(code):
    if code not in NAV_MEMORY_CACHE:
        try: NAV_MEMORY_CACHE[code] = get_nav_history(code)
        except: return None
    return NAV_MEMORY_CACHE[code]

def get_funds_cached(category):
    if category not in ALL_FUNDS_CACHE:
        cfg = CATEGORIES[category]
        ALL_FUNDS_CACHE[category] = get_all_direct_growth_funds_by_category(
            cfg["amfi_category_keywords"], cfg.get("name_must_contain", [])
        )
    return ALL_FUNDS_CACHE[category]

def get_bench_cached(category, date):
    cfg = CATEGORIES[category]
    code = cfg.get("benchmark_code")
    if not code: return None
    if code not in BENCH_CACHE:
        BENCH_CACHE[code] = get_nav_history_cached(code)
    df = BENCH_CACHE[code]
    return df[df['date'] <= date]

def get_closest_nav(nav_df, date):
    if not isinstance(date, pd.Timestamp): date = pd.to_datetime(date)
    available = nav_df[nav_df['date'] >= date]
    if available.empty: return nav_df.iloc[-1]
    return available.iloc[0]

def calculate_tax(sell_date, transactions, sell_nav):
    total_tax, total_proceeds = 0, 0
    for buy_date, buy_amount, buy_units in transactions:
        gain = (sell_nav * buy_units) - buy_amount
        if gain > 0:
            if (sell_date - buy_date).days > 365: tax = gain * LTCG_RATE
            else: tax = gain * STCG_RATE
            total_tax += tax
        total_proceeds += (sell_nav * buy_units)
    return total_proceeds - total_tax, total_tax

# --- CORE LOGIC ---

class Portfolio:
    def __init__(self, bucket_name, failure_threshold=4):
        self.bucket_name = bucket_name
        self.failure_threshold = failure_threshold
        self.funds = {} # category -> {code, name, transactions, consecutive_failures, tax_paid, out_of_pocket}
        self.total_tax_paid = 0
        self.out_of_pocket = 0

    def add_fund(self, category, code, name):
        self.funds[category] = {
            "code": code, "name": name, "transactions": [],
            "consecutive_failures": 0, "tax_paid": 0, "out_of_pocket": 0
        }

    def sip(self, date):
        for category, data in self.funds.items():
            nav_df = get_nav_history_cached(data["code"])
            if nav_df is None: continue
            row = get_closest_nav(nav_df, date)
            units = SIP_AMOUNT / row['nav']
            data["transactions"].append((row['date'], SIP_AMOUNT, units))
            data["out_of_pocket"] += SIP_AMOUNT
            self.out_of_pocket += SIP_AMOUNT

    def rebalance(self, category, new_code, new_name, date):
        old_data = self.funds[category]
        if old_data["code"] == new_code: return
        
        nav_df_old = get_nav_history_cached(old_data["code"])
        sell_row = get_closest_nav(nav_df_old, date)
        net_proceeds, tax = calculate_tax(sell_row['date'], old_data["transactions"], sell_row['nav'])
        self.total_tax_paid += tax
        old_data["tax_paid"] += tax
        
        nav_df_new = get_nav_history_cached(new_code)
        buy_row = get_closest_nav(nav_df_new, sell_row['date'])
        new_units = net_proceeds / buy_row['nav']
        
        self.funds[category] = {
            "code": new_code, "name": new_name,
            "transactions": [(buy_row['date'], net_proceeds, new_units)],
            "consecutive_failures": 0, "tax_paid": old_data["tax_paid"],
            "out_of_pocket": old_data["out_of_pocket"]
        }

    def get_category_metrics(self, category, end_date):
        data = self.funds[category]
        nav_df = get_nav_history_cached(data["code"])
        row = get_closest_nav(nav_df, end_date)
        net_val, final_tax = calculate_tax(row['date'], data["transactions"], row['nav'])
        return {
            "invested": data["out_of_pocket"],
            "post_tax_value": net_val,
            "total_tax": data["tax_paid"] + final_tax
        }

def pick_best_fund(category, target_date, mode="tool"):
    cfg = CATEGORIES[category]
    all_funds = get_funds_cached(category)
    bench_df = get_bench_cached(category, target_date)
    passed = []
    
    for f in all_funds:
        try:
            nav_df = get_nav_history_cached(f["code"])
            nav_hist = nav_df[nav_df['date'] <= target_date]
            if len(nav_hist) < 252 * 5: continue
            
            if mode == "best":
                # Simple CAGR check
                lookback = int(3 * 252)
                if len(nav_hist) > lookback:
                    start_val = nav_hist["nav"].iloc[-(lookback+1)]
                    f["cagr_3y"] = (nav_hist["nav"].iloc[-1] / start_val) ** (1/3) - 1
                else: f["cagr_3y"] = -1
                passed.append(f)
            else:
                m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
                m.update(f)
                if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: continue
                if cfg["strategy"] == "active":
                    consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
                    if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: continue
                    if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: continue
                    if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: continue
                
                # Simplified tool score
                # (Just re-using the logic from previous scripts for speed)
                passed.append(m)
        except: continue
    
    if not passed: return None
    if mode == "best":
        best = sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]
    else:
        # For simplicity in rebalancing pick, use 3Y CAGR of gate-survivors
        best = sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]
    return {"code": best["code"], "name": best["name"]}

def check_fund_fails_gate(category, code, date):
    cfg = CATEGORIES[category]
    try:
        nav_df = get_nav_history_cached(code)
        nav_hist = nav_df[nav_df['date'] <= date]
        bench_df = get_bench_cached(category, date)
        m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
        if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: return True
        if cfg["strategy"] == "active":
            consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
            if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: return True
            if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: return True
            if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: return True
        return False
    except: return False

def run_backtest_for_year(year):
    print(f"Running backtest for {year}...")
    start_date = pd.to_datetime(f"{year}-01-01")
    
    # 1. Identify starting funds
    b1_start = {}
    b23_start = {}
    for cat in CATEGORIES.keys():
        b1_start[cat] = pick_best_fund(cat, start_date, mode="best")
        b23_start[cat] = pick_best_fund(cat, start_date, mode="tool")

    p1 = Portfolio(f"B1_{year}_Best")
    p2 = Portfolio(f"B2_{year}_Tool_4Q", failure_threshold=4)
    p3 = Portfolio(f"B3_{year}_Tool_Hold")
    
    for cat in CATEGORIES.keys():
        if b1_start[cat]: p1.add_fund(cat, b1_start[cat]["code"], b1_start[cat]["name"])
        if b23_start[cat]:
            p2.add_fund(cat, b23_start[cat]["code"], b23_start[cat]["name"])
            p3.add_fund(cat, b23_start[cat]["code"], b23_start[cat]["name"])
            
    end_date, current_date = datetime.now(), start_date
    month_count = 0
    while current_date <= end_date:
        p1.sip(current_date); p2.sip(current_date); p3.sip(current_date)
        month_count += 1
        if month_count % 3 == 0:
            for cat, data in p2.funds.items():
                if check_fund_fails_gate(cat, data["code"], current_date):
                    data["consecutive_failures"] += 1
                else: data["consecutive_failures"] = 0
                if data["consecutive_failures"] >= p2.failure_threshold:
                    new_f = pick_best_fund(cat, current_date, mode="tool")
                    if new_f: p2.rebalance(cat, new_f["code"], new_f["name"], current_date)
        current_date += pd.DateOffset(months=1)

    today = datetime.now()
    res = {}
    for p in [p1, p3, p2]:
        total_inv, total_val = 0, 0
        cat_res = {}
        for cat in p.funds.keys():
            m = p.get_category_metrics(cat, today)
            total_inv += m["invested"]
            total_val += m["post_tax_value"]
            cat_res[cat] = (m["post_tax_value"] / m["invested"] - 1) * 100
        res[p.bucket_name] = {"return": (total_val / total_inv - 1) * 100, "categories": cat_res}
    return res

if __name__ == "__main__":
    years = [2019, 2020, 2021, 2022, 2023, 2024]
    all_year_res = {}
    for y in years:
        all_year_res[y] = run_backtest_for_year(y)
    
    with open("backtest_4q_results.json", "w") as f:
        json.dump(all_year_res, f, indent=2)

    # Simplified summary output
    print("\n" + "="*60)
    print(f"{'Year':<6} | {'B1 (Best)':<12} | {'B3 (Tool Hold)':<15} | {'B2 (Tool 4Q)':<12}")
    print("-" * 60)
    for y in years:
        r = all_year_res[y]
        b1 = r[f"B1_{y}_Best"]["return"]
        b3 = r[f"B3_{y}_Tool_Hold"]["return"]
        b2 = r[f"B2_{y}_Tool_4Q"]["return"]
        print(f"{y:<6} | {b1:>10.1f}% | {b3:>13.1f}% | {b2:>10.1f}%")
