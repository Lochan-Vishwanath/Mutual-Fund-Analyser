
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

def get_nav_history_cached(code):
    if code not in NAV_MEMORY_CACHE:
        NAV_MEMORY_CACHE[code] = get_nav_history(code)
    return NAV_MEMORY_CACHE[code]

def get_closest_nav(nav_df, date):
    """Find the NAV on or just after the given date."""
    # Convert to datetime if it's not
    if not isinstance(date, pd.Timestamp):
        date = pd.to_datetime(date)
    available = nav_df[nav_df['date'] >= date]
    if available.empty:
        return nav_df.iloc[-1]
    return available.iloc[0]

def calculate_tax(sell_date, transactions, sell_nav):
    """
    Calculates tax based on FIFO.
    Each transaction is (date, amount, units).
    Returns (net_amount, total_tax).
    """
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
        self.funds = {} # category -> {code, name, transactions, consecutive_failures}
        self.total_tax_paid = 0
        self.out_of_pocket = 0

    def add_fund(self, category, code, name):
        self.funds[category] = {
            "code": code,
            "name": name,
            "transactions": [], # List of (date, amount, units)
            "consecutive_failures": 0
        }

    def sip(self, date):
        for category, data in self.funds.items():
            nav_df = get_nav_history_cached(data["code"])
            row = get_closest_nav(nav_df, date)
            nav = row['nav']
            units = SIP_AMOUNT / nav
            data["transactions"].append((row['date'], SIP_AMOUNT, units))
            self.out_of_pocket += SIP_AMOUNT

    def rebalance(self, category, new_code, new_name, date):
        old_data = self.funds[category]
        if old_data["code"] == new_code:
            return
        
        print(f"Rebalancing {category}: {old_data['name']} -> {new_name} on {date.date()}")
        nav_df_old = get_nav_history_cached(old_data["code"])
        sell_row = get_closest_nav(nav_df_old, date)
        sell_nav = sell_row['nav']
        
        net_proceeds, tax = calculate_tax(sell_row['date'], old_data["transactions"], sell_nav)
        self.total_tax_paid += tax
        
        # Invest proceeds into new fund
        nav_df_new = get_nav_history_cached(new_code)
        buy_row = get_closest_nav(nav_df_new, sell_row['date'])
        buy_nav = buy_row['nav']
        new_units = net_proceeds / buy_nav
        
        self.funds[category] = {
            "code": new_code,
            "name": new_name,
            "transactions": [(buy_row['date'], net_proceeds, new_units)],
            "consecutive_failures": 0
        }

    def get_value(self, date):
        total_value = 0
        for category, data in self.funds.items():
            nav_df = get_nav_history_cached(data["code"])
            row = get_closest_nav(nav_df, date)
            units = sum(t[2] for t in data["transactions"])
            total_value += units * row['nav']
        return total_value

    def get_total_invested(self):
        return self.out_of_pocket


def pick_best_fund(category, target_date):
    """Pick the best fund using the tool's logic at a specific date."""
    cfg = CATEGORIES[category]
    all_funds = get_all_direct_growth_funds_by_category(cfg["amfi_category_keywords"], cfg.get("name_must_contain", []))
    
    bench_df = None
    if cfg.get("benchmark_code"):
        try:
            bench_df = get_nav_history(cfg["benchmark_code"])
            bench_df = bench_df[bench_df['date'] <= target_date]
        except: pass

    passed = []
    consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
    
    for f in all_funds:
        try:
            nav_df = get_nav_history_cached(f["code"])
            nav_hist = nav_df[nav_df['date'] <= target_date]
            if len(nav_hist) < 252 * 5: continue
            m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
            m.update(f)
            
            # Simplified gate check
            if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: continue
            if cfg["strategy"] == "active":
                if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: continue
                if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: continue
                if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: continue
            passed.append(m)
        except: continue
    
    if not passed: return None
    
    # Simple sorting by 3Y CAGR for rebalancing selection
    best = sorted(passed, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[0]
    return {"code": best["code"], "name": best["name"]}

def check_fund_fails_gate(category, code, date):
    """Check if fund fails any gate on specific date."""
    cfg = CATEGORIES[category]
    try:
        nav_df = get_nav_history_cached(code)
        nav_hist = nav_df[nav_df['date'] <= date]
        
        bench_df = None
        if cfg.get("benchmark_code"):
            bench_df = get_nav_history_cached(cfg["benchmark_code"])
            bench_df = bench_df[bench_df['date'] <= date]
            
        m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
        
        consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
        
        if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: return True
        if cfg["strategy"] == "active":
            if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: return True
            if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: return True
            if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: return True
        return False
    except:
        return False

def run_backtest():
    with open("backtest_buckets_2019.json") as f:
        config_data = json.load(f)
    
    p1 = Portfolio("Bucket 1 (Best Performers)")
    p2 = Portfolio("Bucket 2 (Tool-based)")
    
    for cat, fund in config_data["bucket1"].items():
        p1.add_fund(cat, fund["code"], fund["name"])
    for cat, fund in config_data["bucket2"].items():
        p2.add_fund(cat, fund["code"], fund["name"])
        
    start_date = pd.to_datetime("2019-01-01")
    end_date = datetime.now()
    
    current_date = start_date
    month_count = 0
    
    while current_date <= end_date:
        # SIP
        p1.sip(current_date)
        p2.sip(current_date)
        
        month_count += 1
        # Quarterly Review for Bucket 2
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

        # Increment month
        current_date = current_date + pd.DateOffset(months=1)

    # Final Value Calculation
    today = datetime.now()
    v1 = p1.get_value(today)
    v2 = p2.get_value(today)
    
    i1 = p1.get_total_invested()
    i2 = p2.get_total_invested()
    
    # Post-tax value for Bucket 1 (liquidate all today)
    v1_net = 0
    t1_total = 0
    for cat, data in p1.funds.items():
        nav_df = get_nav_history_cached(data["code"])
        sell_row = get_closest_nav(nav_df, today)
        net, tax = calculate_tax(sell_row['date'], data["transactions"], sell_row['nav'])
        v1_net += net
        t1_total += tax

    # Post-tax value for Bucket 2
    v2_net = 0
    t2_total = p2.total_tax_paid
    for cat, data in p2.funds.items():
        nav_df = get_nav_history_cached(data["code"])
        sell_row = get_closest_nav(nav_df, today)
        net, tax = calculate_tax(sell_row['date'], data["transactions"], sell_row['nav'])
        v2_net += net
        t2_total += tax

    print("\n" + "="*50)
    print("BACKTEST RESULTS (2019 - PRESENT)")
    print("="*50)
    
    print(f"\nBucket 1: {p1.bucket_name}")
    print(f"Total Invested: ₹{i1:,.2f}")
    print(f"Final Value (Pre-tax): ₹{v1:,.2f}")
    print(f"Final Value (Post-tax): ₹{v1_net:,.2f}")
    print(f"Absolute Return: {(v1/i1 - 1)*100:.2f}%")
    print(f"Post-tax Return: {(v1_net/i1 - 1)*100:.2f}%")
    
    print(f"\nBucket 2: {p2.bucket_name}")
    print(f"Total Invested: ₹{i2:,.2f}")
    print(f"Final Value (Pre-tax): ₹{v2:,.2f}")
    print(f"Final Value (Post-tax): ₹{v2_net:,.2f}")
    print(f"Absolute Return: {(v2/i2 - 1)*100:.2f}%")
    print(f"Post-tax Return: {(v2_net/i2 - 1)*100:.2f}%")
    print(f"Total Tax Paid during rebalancing: ₹{p2.total_tax_paid:,.2f}")

if __name__ == "__main__":
    run_backtest()
