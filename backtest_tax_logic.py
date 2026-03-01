
import pandas as pd
import numpy as np
import json
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_nav_history, get_all_direct_growth_funds_by_category
from metrics import compute_all_metrics

# --- CONFIG ---
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

def calculate_tax_and_proceeds(sell_date, transactions, sell_nav):
    """Calculates proceeds and tax for specific lots."""
    total_tax, total_proceeds = 0, 0
    for buy_date, buy_amount, buy_units in transactions:
        gain = (sell_nav * buy_units) - buy_amount
        if gain > 0:
            if (sell_date - buy_date).days > 365: tax = gain * LTCG_RATE
            else: tax = gain * STCG_RATE
            total_tax += tax
        total_proceeds += (sell_nav * buy_units)
    return total_proceeds - total_tax, total_tax

class AdvancedPortfolio:
    def __init__(self, bucket_name, mode="immediate"):
        self.bucket_name = bucket_name
        self.mode = mode # "immediate", "ltcg_only", "tax_alpha"
        self.funds = {} # cat -> {code, name, transactions, consecutive_failures, tax_paid, out_of_pocket, pending_transfer}
        self.total_tax_paid = 0
        self.out_of_pocket = 0

    def add_fund(self, category, code, name):
        self.funds[category] = {
            "code": code, "name": name, "transactions": [],
            "consecutive_failures": 0, "tax_paid": 0, "out_of_pocket": 0,
            "pending_transfer": None # {old_transactions, old_code, trigger_date}
        }

    def sip(self, date):
        for category, data in self.funds.items():
            # Handle SIP into current active fund
            nav_df = get_nav_history_cached(data["code"])
            if nav_df is not None:
                row = get_closest_nav(nav_df, date)
                units = SIP_AMOUNT / row['nav']
                data["transactions"].append((row['date'], SIP_AMOUNT, units))
                data["out_of_pocket"] += SIP_AMOUNT
                self.out_of_pocket += SIP_AMOUNT
            
            # Check if pending transfer in LTCG mode can be executed
            if self.mode == "ltcg_only" and data["pending_transfer"]:
                pending = data["pending_transfer"]
                # If 1 year has passed since the trigger (which was the last SIP)
                if (date - pending["trigger_date"]).days >= 366:
                    self._execute_transfer(category, date)

    def _execute_transfer(self, category, date):
        data = self.funds[category]
        pending = data["pending_transfer"]
        
        nav_df_old = get_nav_history_cached(pending["old_code"])
        sell_row = get_closest_nav(nav_df_old, date)
        net_proceeds, tax = calculate_tax_and_proceeds(sell_row['date'], pending["old_transactions"], sell_row['nav'])
        
        self.total_tax_paid += tax
        data["tax_paid"] += tax
        
        nav_df_new = get_nav_history_cached(data["code"])
        buy_row = get_closest_nav(nav_df_new, sell_row['date'])
        new_units = net_proceeds / buy_row['nav']
        
        # Add proceeds as a single lot to the new fund
        data["transactions"].append((buy_row['date'], net_proceeds, new_units))
        data["pending_transfer"] = None
        print(f"[{self.bucket_name}] Executed delayed transfer for {category} on {date.date()}")

    def rebalance_trigger(self, category, new_f, date, old_cagr, new_cagr):
        data = self.funds[category]
        if data["code"] == new_f["code"]: return
        
        # Tax Alpha Logic
        if self.mode == "tax_alpha":
            nav_df_old = get_nav_history_cached(data["code"])
            sell_row = get_closest_nav(nav_df_old, date)
            val = sum(t[2] for t in data["transactions"]) * sell_row['nav']
            _, tax = calculate_tax_and_proceeds(sell_row['date'], data["transactions"], sell_row['nav'])
            tax_hurdle = (tax / val) if val > 0 else 0
            
            # Trailing 3Y CAGR diff vs Tax Hurdle
            if (new_cagr - old_cagr) <= tax_hurdle:
                # print(f"[{self.bucket_name}] Skipping rebalance for {category}: Alpha {new_cagr-old_cagr:.2%} <= Tax Hurdle {tax_hurdle:.2%}")
                return

        if self.mode == "immediate" or self.mode == "tax_alpha":
            # Standard immediate swap
            nav_df_old = get_nav_history_cached(data["code"])
            sell_row = get_closest_nav(nav_df_old, date)
            net_proceeds, tax = calculate_tax_and_proceeds(sell_row['date'], data["transactions"], sell_row['nav'])
            self.total_tax_paid += tax
            data["tax_paid"] += tax
            
            nav_df_new = get_nav_history_cached(new_f["code"])
            buy_row = get_closest_nav(nav_df_new, sell_row['date'])
            new_units = net_proceeds / buy_row['nav']
            
            data["code"] = new_f["code"]
            data["name"] = new_f["name"]
            data["transactions"] = [(buy_row['date'], net_proceeds, new_units)]
            data["consecutive_failures"] = 0
            # print(f"[{self.bucket_name}] Immediate Rebalance {category} on {date.date()}")

        elif self.mode == "ltcg_only":
            # Switch SIPs immediately, but hold old units for 1 year
            print(f"[{self.bucket_name}] Triggered rebalance for {category}. Switching SIP to {new_f['name']}. Holding old units for LTCG.")
            data["pending_transfer"] = {
                "old_transactions": data["transactions"],
                "old_code": data["code"],
                "trigger_date": date
            }
            data["code"] = new_f["code"]
            data["name"] = new_f["name"]
            data["transactions"] = [] # New transactions start here
            data["consecutive_failures"] = 0

    def get_final_metrics(self, end_date):
        total_val = 0
        for cat, data in self.funds.items():
            # Current active fund value
            nav_df = get_nav_history_cached(data["code"])
            row = get_closest_nav(nav_df, end_date)
            net_val, _ = calculate_tax_and_proceeds(row['date'], data["transactions"], row['nav'])
            total_val += net_val
            
            # Pending transfer value
            if data["pending_transfer"]:
                p = data["pending_transfer"]
                nav_df_p = get_nav_history_cached(p["old_code"])
                row_p = get_closest_nav(nav_df_p, end_date)
                net_val_p, _ = calculate_tax_and_proceeds(row_p['date'], p["old_transactions"], row_p['nav'])
                total_val += net_val_p
                
        return (total_val / self.out_of_pocket - 1) * 100 if self.out_of_pocket > 0 else 0

def get_metrics_for_decision(category, code, date):
    cfg = CATEGORIES[category]
    nav_df = get_nav_history_cached(code)
    nav_hist = nav_df[nav_df['date'] <= date]
    bench_df = get_bench_cached(category, date)
    m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
    return m

def pick_best_tool_fund(category, target_date):
    all_funds = get_funds_cached(category)
    bench_df = get_bench_cached(category, target_date)
    passed = []
    for f in all_funds:
        try:
            nav_df = get_nav_history_cached(f["code"])
            nav_hist = nav_df[nav_df['date'] <= target_date]
            if len(nav_hist) < 252 * 5: continue
            m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=3)
            m.update(f)
            # Standard gates
            if m.get("sharpe", 0) < SHARPE_GATE_MIN: continue
            if m.get("rolling_consistency", 0) < 0.55: continue
            passed.append(m)
        except: continue
    if not passed: return None
    # Force a different pick for rebalancing to simulate switching
    if len(passed) > 1:
        # Pick the second best if rebalancing to ensure we actually switch
        best = sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[1]
    else:
        best = sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]
    return best

def run_tax_backtest():
    start_year = 2019
    print(f"\n>>> RUNNING TAX OPTIMIZATION BACKTEST (Start: {start_year}) <<<")
    
    p1 = AdvancedPortfolio("Mode 1: Immediate", mode="immediate")
    p2 = AdvancedPortfolio("Mode 2: LTCG Optimized", mode="ltcg_only")
    p3 = AdvancedPortfolio("Mode 3: Tax-Alpha Hurdle", mode="tax_alpha")
    
    start_date = pd.to_datetime(f"{start_year}-01-01")
    for cat in CATEGORIES.keys():
        f = pick_best_tool_fund(cat, start_date)
        if f:
            p1.add_fund(cat, f["code"], f["name"])
            p2.add_fund(cat, f["code"], f["name"])
            p3.add_fund(cat, f["code"], f["name"])
            
    current_date, end_date = start_date, datetime.now()
    month_count = 0
    while current_date <= end_date:
        p1.sip(current_date); p2.sip(current_date); p3.sip(current_date)
        month_count += 1
        if month_count % 3 == 0:
            for cat in CATEGORIES.keys():
                if cat not in p1.funds: continue
                # We check failure once per category (sensor fund = p1)
                data_sensor = p1.funds[cat]
                m_sensor = get_metrics_for_decision(cat, data_sensor["code"], current_date)
                
                fail = False
                if m_sensor.get("sharpe", 0) < SHARPE_GATE_MIN: fail = True
                # Use a tighter gate for the backtest to force rebalancing activity
                if m_sensor.get("rolling_consistency", 0) < 0.70: fail = True
                
                if fail: data_sensor["consecutive_failures"] += 1
                else: data_sensor["consecutive_failures"] = 0
                
                if data_sensor["consecutive_failures"] >= 2:
                    new_f = pick_best_tool_fund(cat, current_date)
                    if new_f:
                        old_c = m_sensor.get("cagr_3y", 0)
                        new_c = new_f.get("cagr_3y", 0)
                        for p in [p1, p2, p3]:
                            # In LTCG mode, if we already have a pending transfer, don't trigger another rebalance
                            if p.mode == "ltcg_only" and p.funds[cat]["pending_transfer"]:
                                continue
                            p.rebalance_trigger(cat, new_f, current_date, old_c, new_c)

        current_date += pd.DateOffset(months=1)

    print("\n" + "="*50)
    print("TAX-ALPHA BACKTEST RESULTS")
    print("="*50)
    for p in [p1, p2, p3]:
        ret = p.get_final_metrics(end_date)
        print(f"{p.bucket_name:<25} | Post-Tax Return: {ret:>6.1f}%")

if __name__ == "__main__":
    run_tax_backtest()
