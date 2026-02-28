
import pandas as pd
import numpy as np
import json
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_nav_history, get_all_direct_growth_funds_by_category
from metrics import compute_all_metrics

# Tax rates as per user
STCG_RATE = 0.20
LTCG_RATE = 0.125
SIP_AMOUNT = 10000

# In-memory cache for NAV history
NAV_MEMORY_CACHE = {}
ALL_FUNDS_CACHE = {}
BENCH_CACHE = {}

def get_nav_history_cached(code):
    if code not in NAV_MEMORY_CACHE:
        NAV_MEMORY_CACHE[code] = get_nav_history(code)
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
    """Find the NAV on or just after the given date."""
    if not isinstance(date, pd.Timestamp):
        date = pd.to_datetime(date)
    available = nav_df[nav_df['date'] >= date]
    if available.empty:
        return nav_df.iloc[-1]
    return available.iloc[0]

def calculate_tax(sell_date, transactions, sell_nav):
    """Calculates tax based on FIFO."""
    total_tax = 0
    total_proceeds = 0
    for buy_date, buy_amount, buy_units in transactions:
        gain = (sell_nav * buy_units) - buy_amount
        if gain > 0:
            if (sell_date - buy_date).days > 365:
                tax = gain * LTCG_RATE
            else:
                tax = gain * STCG_RATE
            total_tax += tax
        total_proceeds += (sell_nav * buy_units)
    return total_proceeds - total_tax, total_tax

class Portfolio:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.funds = {} # category -> {code, name, transactions, consecutive_failures, tax_paid, out_of_pocket}
        self.total_tax_paid = 0
        self.out_of_pocket = 0

    def add_fund(self, category, code, name):
        self.funds[category] = {
            "code": code,
            "name": name,
            "transactions": [],
            "consecutive_failures": 0,
            "tax_paid": 0,
            "out_of_pocket": 0
        }

    def sip(self, date):
        for category, data in self.funds.items():
            nav_df = get_nav_history_cached(data["code"])
            row = get_closest_nav(nav_df, date)
            nav = row['nav']
            units = SIP_AMOUNT / nav
            data["transactions"].append((row['date'], SIP_AMOUNT, units))
            data["out_of_pocket"] += SIP_AMOUNT
            self.out_of_pocket += SIP_AMOUNT

    def rebalance(self, category, new_code, new_name, date):
        old_data = self.funds[category]
        if old_data["code"] == new_code:
            return
        
        print(f"[{self.bucket_name}] Rebalancing {category}: {old_data['name']} -> {new_name} on {date.date()}")
        nav_df_old = get_nav_history_cached(old_data["code"])
        sell_row = get_closest_nav(nav_df_old, date)
        sell_nav = sell_row['nav']
        
        net_proceeds, tax = calculate_tax(sell_row['date'], old_data["transactions"], sell_nav)
        self.total_tax_paid += tax
        old_data["tax_paid"] += tax
        
        nav_df_new = get_nav_history_cached(new_code)
        buy_row = get_closest_nav(nav_df_new, sell_row['date'])
        buy_nav = buy_row['nav']
        new_units = net_proceeds / buy_nav
        
        self.funds[category] = {
            "code": new_code,
            "name": new_name,
            "transactions": [(buy_row['date'], net_proceeds, new_units)],
            "consecutive_failures": 0,
            "tax_paid": old_data["tax_paid"],
            "out_of_pocket": old_data["out_of_pocket"]
        }

    def get_category_metrics(self, category, end_date):
        data = self.funds[category]
        nav_df = get_nav_history_cached(data["code"])
        row = get_closest_nav(nav_df, end_date)
        
        units = sum(t[2] for t in data["transactions"])
        pre_tax_val = units * row['nav']
        invested = data["out_of_pocket"]
        
        # Calculate final tax if liquidated today
        net_val, final_tax = calculate_tax(row['date'], data["transactions"], row['nav'])
        
        return {
            "name": data["name"],
            "invested": invested,
            "pre_tax_value": pre_tax_val,
            "post_tax_value": net_val,
            "total_tax": data["tax_paid"] + final_tax
        }

def pick_best_fund(category, target_date):
    cfg = CATEGORIES[category]
    all_funds = get_funds_cached(category)
    bench_df = get_bench_cached(category, target_date)
    
    passed = []
    consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
    for f in all_funds:
        try:
            nav_df = get_nav_history_cached(f["code"])
            nav_hist = nav_df[nav_df['date'] <= target_date]
            if len(nav_hist) < 252 * 5: continue
            
            m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
            m.update(f)
            
            if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: continue
            if cfg["strategy"] == "active":
                if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: continue
                if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: continue
                if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: continue
            passed.append(m)
        except: continue
    if not passed: return None
    best = sorted(passed, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[0]
    return {"code": best["code"], "name": best["name"]}

def check_fund_fails_gate(category, code, date):
    cfg = CATEGORIES[category]
    try:
        nav_df = get_nav_history_cached(code)
        nav_hist = nav_df[nav_df['date'] <= date]
        bench_df = get_bench_cached(category, date)
        
        m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
        consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
        
        if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: return True
        if cfg["strategy"] == "active":
            if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: return True
            if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: return True
            if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: return True
        return False
    except: return False

def run_backtest():
    with open("backtest_buckets_2019.json") as f:
        config_data = json.load(f)
    
    p1 = Portfolio("Bucket 1 (Best Performers)")
    p2 = Portfolio("Bucket 2 (Tool + Rebalancing)")
    p3 = Portfolio("Bucket 3 (Tool - No Rebalancing)")
    
    for cat, fund in config_data["bucket1"].items():
        p1.add_fund(cat, fund["code"], fund["name"])
    for cat, fund in config_data["bucket2"].items():
        p2.add_fund(cat, fund["code"], fund["name"])
        p3.add_fund(cat, fund["code"], fund["name"])
        
    start_date = pd.to_datetime("2019-01-01")
    end_date = datetime.now()
    current_date = start_date
    month_count = 0
    
    while current_date <= end_date:
        p1.sip(current_date)
        p2.sip(current_date)
        p3.sip(current_date)
        
        month_count += 1
        if month_count % 3 == 0:
            for category, data in p2.funds.items():
                if check_fund_fails_gate(category, data["code"], current_date):
                    data["consecutive_failures"] += 1
                else:
                    data["consecutive_failures"] = 0
                if data["consecutive_failures"] >= 2:
                    new_fund = pick_best_fund(category, current_date)
                    if new_fund:
                        p2.rebalance(category, new_fund["code"], new_fund["name"], current_date)

        current_date = current_date + pd.DateOffset(months=1)

    today = datetime.now()
    
    # Category-wise Comparison
    print("\n" + "="*80)
    print(f"{'Category':<20} | {'Bucket':<10} | {'Invested':<10} | {'Post-Tax Val':<12} | {'Return %':<8}")
    print("-" * 80)
    
    for cat in p1.funds.keys():
        for p in [p1, p3, p2]:
            m = p.get_category_metrics(cat, today)
            ret = (m["post_tax_value"] / m["invested"] - 1) * 100
            print(f"{cat:<20} | {p.bucket_name[:10]:<10} | ₹{m['invested']/1e5:>7.2f}L | ₹{m['post_tax_value']/1e5:>9.2f}L | {ret:>7.1f}%")
        print("-" * 80)

    # Total Comparison
    print("\n" + "="*80)
    print("OVERALL PORTFOLIO SUMMARY")
    print("="*80)
    for p in [p1, p3, p2]:
        total_inv = p.out_of_pocket
        total_post_tax = sum(p.get_category_metrics(cat, today)["post_tax_value"] for cat in p.funds.keys())
        total_ret = (total_post_tax / total_inv - 1) * 100
        print(f"{p.bucket_name:<30} | Invested: ₹{total_inv/1e5:>6.1f}L | Post-Tax: ₹{total_post_tax/1e5:>6.1f}L | Return: {total_ret:>5.1f}%")

if __name__ == "__main__":
    run_backtest()
