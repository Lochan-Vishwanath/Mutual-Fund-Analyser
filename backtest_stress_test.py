
import pandas as pd
import numpy as np
import json
from datetime import datetime
from backtest_tax_logic import AdvancedPortfolio, pick_best_tool_fund

STRESS_DATES = {
    "Peak (Pre-COVID)": "2020-01-01",
    "Trough (COVID Low)": "2020-03-23",
    "Peak (Post-COVID Rally)": "2021-10-18",
    "Trough (Inflation/Rate Hike Low)": "2022-06-20"
}

def run_stress_test():
    print("\n" + "="*60)
    print("PEAK & TROUGH STRESS TESTING")
    print("="*60)
    
    end_date = datetime.now()
    results = {}

    for scenario, start_date_str in STRESS_DATES.items():
        print(f"\nScenario: {scenario} (Start: {start_date_str})")
        start_date = pd.to_datetime(start_date_str)
        
        # We compare B1 (Past winners) vs B3 (Tool Hold)
        p1 = AdvancedPortfolio(f"B1_{start_date_str}_Best", mode="immediate")
        p3 = AdvancedPortfolio(f"B3_{start_date_str}_Tool", mode="immediate")
        
        from config import CATEGORIES
        for cat in CATEGORIES.keys():
            # Mode "best" picks based on trailing 3Y CAGR
            from backtest_tax_logic import pick_best_tool_fund as pick_tool
            # I need to ensure pick_best_tool_fund can pick "Best" (Bucket 1) vs "Tool" (Bucket 3)
            # Re-using logic from backtest_4q.py or backtest_tax_logic.py
            
            # Let's import the specific modes from the previous script logic
            # Since I can't easily modify pick_best_tool_fund to take a mode now without editing it,
            # I will implement a quick local version here.
            
            from backtest_tax_logic import get_funds_cached, get_bench_cached, get_nav_history_cached, compute_all_metrics, SHARPE_GATE_MIN
            
            def local_pick(cat, date, mode):
                all_funds = get_funds_cached(cat)
                bench_df = get_bench_cached(cat, date)
                passed = []
                for f in all_funds:
                    try:
                        nav_df = get_nav_history_cached(f["code"])
                        nav_hist = nav_df[nav_df['date'] <= date]
                        if len(nav_hist) < 252 * 5: continue
                        
                        if mode == "best":
                            lookback = int(3 * 252)
                            start_val = nav_hist["nav"].iloc[-(lookback+1)]
                            f["cagr_3y"] = (nav_hist["nav"].iloc[-1] / start_val) ** (1/3) - 1
                            passed.append(f)
                        else:
                            m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=3)
                            m.update(f)
                            if m.get("sharpe", 0) < SHARPE_GATE_MIN: continue
                            if m.get("rolling_consistency", 0) < 0.55: continue
                            passed.append(m)
                    except: continue
                if not passed: return None
                key = "cagr_3y" if mode == "best" else "cagr_3y" # Simplified tool pick
                return sorted(passed, key=lambda x: x.get(key, -1), reverse=True)[0]

            f1 = local_pick(cat, start_date, "best")
            f3 = local_pick(cat, start_date, "tool")
            
            if f1: p1.add_fund(cat, f1["code"], f1["name"])
            if f3: p3.add_fund(cat, f3["code"], f3["name"])

        # Run SIP
        current_date = start_date
        while current_date <= end_date:
            p1.sip(current_date)
            p3.sip(current_date)
            current_date += pd.DateOffset(months=1)
            
        ret1 = p1.get_final_metrics(end_date)
        ret3 = p3.get_final_metrics(end_date)
        results[scenario] = {"Best_of_Year": ret1, "Tool_Hold": ret3}
        
        print(f"  Best of Year Return: {ret1:>6.1f}%")
        print(f"  Tool-Selected Return: {ret3:>6.1f}%")
        print(f"  Alpha: {(ret3 - ret1):>6.1f}%")

    with open("stress_test_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_stress_test()
