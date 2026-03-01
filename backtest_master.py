import pandas as pd
import numpy as np
import math
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_nav_history, get_all_direct_growth_funds_by_category
from metrics import compute_all_metrics

STCG_RATE = 0.20
LTCG_RATE = 0.125
EXIT_LOAD_RATE = 0.01  # 1% exit load for units held < 365 days
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
    if df is None: return None
    return df[df['date'] <= date]

def get_closest_nav(nav_df, date):
    if not isinstance(date, pd.Timestamp): date = pd.to_datetime(date)
    available = nav_df[nav_df['date'] >= date]
    if available.empty: return nav_df.iloc[-1]
    return available.iloc[0]

def calc_sell_lot(buy_date, sell_date, buy_amount, sell_val):
    days_held = (sell_date - buy_date).days
    gain = sell_val - buy_amount
    exit_load = sell_val * EXIT_LOAD_RATE if days_held < 365 else 0
    taxable_gain = gain - exit_load
    
    tax = 0
    if taxable_gain > 0:
        tax = taxable_gain * (LTCG_RATE if days_held > 365 else STCG_RATE)
        
    net_proceeds = sell_val - exit_load - tax
    return net_proceeds, tax, exit_load

class LotPortfolio:
    def __init__(self, mode="immediate"):
        self.mode = mode 
        self.funds = {} 
        self.out_of_pocket = 0
        self.total_tax = 0

    def add_fund(self, category, code, name):
        self.funds[category] = {
            "code": code, "name": name, 
            "active_lots": [],      # [{buy_date, amount, units}]
            "pending_lots": [],     # [{buy_date, amount, units, old_code}] (For staggered mode)
            "failures": 0, "tax_paid": 0
        }

    def sip(self, date):
        for cat, data in self.funds.items():
            # 1. Execute SIP
            nav_df = get_nav_history_cached(data["code"])
            if nav_df is None: continue
            row = get_closest_nav(nav_df, date)
            units = SIP_AMOUNT / row['nav']
            data["active_lots"].append({"buy_date": row['date'], "amount": SIP_AMOUNT, "units": units})
            self.out_of_pocket += SIP_AMOUNT

            # 2. Process Pending Lots (Staggered Exit Mode)
            if data["pending_lots"]:
                remaining_pending = []
                for lot in data["pending_lots"]:
                    days_held = (date - lot["buy_date"]).days
                    if days_held > 365:
                        # Time to sell and move to active fund
                        old_df = get_nav_history_cached(lot["old_code"])
                        s_row = get_closest_nav(old_df, date)
                        sell_val = lot["units"] * s_row['nav']
                        net, tax, _ = calc_sell_lot(lot["buy_date"], s_row['date'], lot["amount"], sell_val)
                        
                        data["tax_paid"] += tax
                        self.total_tax += tax
                        
                        # Buy into current active fund
                        new_units = net / row['nav']
                        data["active_lots"].append({"buy_date": row['date'], "amount": net, "units": new_units})
                    else:
                        remaining_pending.append(lot)
                data["pending_lots"] = remaining_pending

    def rebalance(self, cat, new_code, new_name, date, old_cagr=0, new_cagr=0):
        data = self.funds[cat]
        if data["code"] == new_code: return
        
        old_df = get_nav_history_cached(data["code"])
        s_row = get_closest_nav(old_df, date)
        
        # Calculate what would happen if we sold everything today
        total_val = sum(l["units"] * s_row['nav'] for l in data["active_lots"])
        total_net = 0
        total_tax = 0
        for l in data["active_lots"]:
            net, t, _ = calc_sell_lot(l["buy_date"], s_row['date'], l["amount"], l["units"] * s_row['nav'])
            total_net += net
            total_tax += t
            
        tax_pct = (total_tax / total_val) if total_val > 0 else 0
        
        # Tax-Alpha Breakeven Math
        if self.mode == "tax_alpha":
            r_old = max(old_cagr, 0.01)
            r_new = max(new_cagr, 0.01)
            if r_new <= r_old: return # Never recovers
            
            try:
                breakeven_years = math.log(1 - tax_pct) / (math.log(1 + r_old) - math.log(1 + r_new))
            except:
                breakeven_years = 999
                
            if breakeven_years > 1.5:
                return # Tax hole is too deep, don't switch

        # Execute Switch
        new_df = get_nav_history_cached(new_code)
        b_row = get_closest_nav(new_df, s_row['date'])

        if self.mode in ["immediate", "tax_alpha"]:
            # Sell all, buy new
            new_units = total_net / b_row['nav']
            data["tax_paid"] += total_tax
            self.total_tax += total_tax
            data["active_lots"] = [{"buy_date": b_row['date'], "amount": total_net, "units": new_units}]
            
        elif self.mode == "staggered":
            # Sell >365 days immediately, pend the rest
            new_active = []
            for l in data["active_lots"]:
                if (s_row['date'] - l["buy_date"]).days > 365:
                    net, t, _ = calc_sell_lot(l["buy_date"], s_row['date'], l["amount"], l["units"] * s_row['nav'])
                    data["tax_paid"] += t
                    self.total_tax += t
                    nu = net / b_row['nav']
                    new_active.append({"buy_date": b_row['date'], "amount": net, "units": nu})
                else:
                    l["old_code"] = data["code"] # Tag for future sell
                    data["pending_lots"].append(l)
            data["active_lots"] = new_active

        data["code"] = new_code
        data["name"] = new_name
        data["failures"] = 0

    def get_portfolio_value(self, end_date):
        total_post_tax = 0
        for cat, data in self.funds.items():
            # Liquidate active
            df = get_nav_history_cached(data["code"])
            r = get_closest_nav(df, end_date)
            for l in data["active_lots"]:
                net, _, _ = calc_sell_lot(l["buy_date"], r['date'], l["amount"], l["units"] * r['nav'])
                total_post_tax += net
            # Liquidate pending
            for l in data["pending_lots"]:
                odf = get_nav_history_cached(l["old_code"])
                p_r = get_closest_nav(odf, end_date)
                net, _, _ = calc_sell_lot(l["buy_date"], p_r['date'], l["amount"], l["units"] * p_r['nav'])
                total_post_tax += net
                
        return {"invested": self.out_of_pocket, "post_tax_val": total_post_tax, 
                "return_pct": (total_post_tax / self.out_of_pocket - 1) * 100 if self.out_of_pocket > 0 else 0}

def pick_fund(category, target_date, mode):
    all_funds = get_funds_cached(category)
    bench_df = get_bench_cached(category, target_date)
    cfg = CATEGORIES[category]
    passed = []
    
    for f in all_funds:
        try:
            nav_df = get_nav_history_cached(f["code"])
            hist = nav_df[nav_df['date'] <= target_date]
            if len(hist) < 252 * 4: continue # Requires 4 years history minimum
            
            lookback = int(3 * 252)
            if len(hist) > lookback:
                c3 = (hist["nav"].iloc[-1] / hist["nav"].iloc[-(lookback+1)]) ** (1/3) - 1
            else: c3 = 0
            f["cagr_3y"] = c3
            
            if mode == "best":
                passed.append(f)
            else:
                m = compute_all_metrics(hist, bench_df, rolling_window_years=3)
                m.update(f)
                if m.get("sharpe", 0) < SHARPE_GATE_MIN: continue
                if cfg["strategy"] == "active":
                    if m.get("rolling_consistency", 0) < 0.60: continue # Tight gate for true tool pick
                passed.append(m)
        except: continue
        
    if not passed: return None
    if mode == "best":
        return sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]
    else:
        # Rank by 3Y CAGR amongst survivors for simplicity in this script
        if len(passed) > 1 and mode == "tool":
            # Just to ensure we differentiate from 'best' if possible to test the alpha logic
            # Let's just pick the top tool fund for real results.
            return sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]
        return sorted(passed, key=lambda x: x.get("cagr_3y", -1), reverse=True)[0]

def run_master_backtest(start_year):
    print(f"Evaluating Start Year: {start_year}")
    s_date = pd.to_datetime(f"{start_year}-01-01")
    e_date = datetime.now()
    
    ports = {
        "B1_Past_Winners": LotPortfolio("immediate"),
        "B2_Tool_Hold": LotPortfolio("immediate"),
        "B3_Tool_Immediate": LotPortfolio("immediate"),
        "B4_Tool_Staggered": LotPortfolio("staggered"),
        "B5_Tool_Tax_Alpha": LotPortfolio("tax_alpha")
    }
    
    for cat in CATEGORIES.keys():
        f_best = pick_fund(cat, s_date, "best")
        f_tool = pick_fund(cat, s_date, "tool")
        if not f_best or not f_tool: continue
        
        ports["B1_Past_Winners"].add_fund(cat, f_best["code"], f_best["name"])
        ports["B2_Tool_Hold"].add_fund(cat, f_tool["code"], f_tool["name"])
        ports["B3_Tool_Immediate"].add_fund(cat, f_tool["code"], f_tool["name"])
        ports["B4_Tool_Staggered"].add_fund(cat, f_tool["code"], f_tool["name"])
        ports["B5_Tool_Tax_Alpha"].add_fund(cat, f_tool["code"], f_tool["name"])

    curr = s_date
    mc = 0
    while curr <= e_date:
        for p in ports.values(): p.sip(curr)
        mc += 1
        
        if mc % 3 == 0:
            # Rebalance checks for B3, B4, B5
            for cat in CATEGORIES.keys():
                if cat not in ports["B3_Tool_Immediate"].funds: continue
                
                # Check sensor (B3's current fund)
                d_sensor = ports["B3_Tool_Immediate"].funds[cat]
                hist = get_nav_history_cached(d_sensor["code"])[get_nav_history_cached(d_sensor["code"])['date'] <= curr]
                bench = get_bench_cached(cat, curr)
                m = compute_all_metrics(hist, bench, 3)
                
                fail = False
                if m.get("sharpe", 0) < SHARPE_GATE_MIN: fail = True
                if CATEGORIES[cat]["strategy"] == "active" and m.get("rolling_consistency", 0) < 0.70: fail = True
                
                if fail: d_sensor["failures"] += 1
                else: d_sensor["failures"] = 0
                
                # If failed 2 quarters
                if d_sensor["failures"] >= 2:
                    new_f = pick_fund(cat, curr, "tool")
                    if new_f and new_f["code"] != d_sensor["code"]:
                        o_c = m.get("cagr_3y", 0)
                        n_c = new_f.get("cagr_3y", 0)
                        ports["B3_Tool_Immediate"].rebalance(cat, new_f["code"], new_f["name"], curr, o_c, n_c)
                        ports["B4_Tool_Staggered"].rebalance(cat, new_f["code"], new_f["name"], curr, o_c, n_c)
                        ports["B5_Tool_Tax_Alpha"].rebalance(cat, new_f["code"], new_f["name"], curr, o_c, n_c)
                        
        curr += pd.DateOffset(months=1)

    res = {}
    for name, p in ports.items():
        v = p.get_portfolio_value(e_date)
        res[name] = v["return_pct"]
    return res

if __name__ == "__main__":
    results = {}
    for y in [2018, 2019, 2020, 2021]:
        results[y] = run_master_backtest(y)
        
    print("\n" + "="*80)
    print("MASTER BACKTEST: STAGGERED LTCG & TAX-ALPHA BREAKEAVEN (12.5% LTCG, 20% STCG, 1% Exit)")
    print("="*80)
    headers = ["B1_Winners", "B2_ToolHold", "B3_Immediate", "B4_Staggered", "B5_TaxAlpha"]
    print(f"{'Year':<6} | {' | '.join(f'{h:<12}' for h in headers)}")
    print("-" * 80)
    for y in sorted(results.keys()):
        r = results[y]
        print(f"{y:<6} | {r['B1_Past_Winners']:>11.1f}% | {r['B2_Tool_Hold']:>11.1f}% | {r['B3_Tool_Immediate']:>11.1f}% | {r['B4_Tool_Staggered']:>11.1f}% | {r['B5_Tool_Tax_Alpha']:>11.1f}%")
