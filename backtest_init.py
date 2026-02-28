
import pandas as pd
import numpy as np
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_all_direct_growth_funds_by_category, get_nav_history
from metrics import compute_all_metrics

def get_historical_funds(target_date):
    """
    Identifies funds for Bucket 1 (Best performers) and Bucket 2 (Tool-selected) as of target_date.
    """
    bucket1 = {} # Best performers (by 3Y CAGR)
    bucket2 = {} # Tool-selected (passed gates + top score)

    for category, cfg in CATEGORIES.items():
        print(f"Processing category: {category}")
        all_funds = get_all_direct_growth_funds_by_category(
            amfi_category_keywords=cfg["amfi_category_keywords"],
            name_must_contain=cfg.get("name_must_contain", [])
        )
        
        bench_df = None
        if cfg.get("benchmark_code"):
            try:
                bench_df = get_nav_history(cfg["benchmark_code"])
                bench_df = bench_df[bench_df['date'] <= target_date]
            except:
                pass

        category_funds_metrics = []
        for fund in all_funds:
            try:
                nav_df = get_nav_history(fund["code"])
                nav_df_hist = nav_df[nav_df['date'] <= target_date]
                
                # Need at least some history to compute metrics
                if len(nav_df_hist) < 252 * 5: # Use 5 years for backtest start in 2019
                    continue
                
                m = compute_all_metrics(nav_df_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
                m.update(fund)
                category_funds_metrics.append(m)
            except:
                continue

        if not category_funds_metrics:
            print(f"No funds found for {category}")
            continue

        # Bucket 1: Best performing fund by 3Y CAGR (or 5Y if 3Y not available)
        b1_fund = sorted(category_funds_metrics, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[0]
        bucket1[category] = b1_fund

        # Bucket 2: Tool-based selection
        # 1. Apply gates (ignoring AUM/TER as we don't have historical data easily)
        passed_gates = []
        consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
        
        for m in category_funds_metrics:
            # Sharpe Gate
            if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN:
                continue
            
            if cfg["strategy"] == "active":
                # Consistency Gate
                if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor:
                    continue
                # Capital Protection Gate
                if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR:
                    continue
                # Capture Ratio Gate
                if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN:
                    continue
            
            passed_gates.append(m)

        if not passed_gates:
            # Fallback if none pass gates
            passed_gates = sorted(category_funds_metrics, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[:5]

        # 2. Scoring (simplified quartile scoring for the historical snapshot)
        def quartile_score(val, all_vals, higher_is_better=True):
            clean = [v for v in all_vals if v is not None and not np.isnan(v)]
            if not clean or val is None or np.isnan(val): return 1.0
            q25, q50, q75 = np.percentile(clean, [25, 50, 75])
            if higher_is_better:
                if val >= q75: return 4.0
                if val >= q50: return 3.0
                if val >= q25: return 2.0
                return 1.0
            else:
                if val <= q25: return 4.0
                if val <= q50: return 3.0
                if val <= q75: return 2.0
                return 1.0

        for f in passed_gates:
            if cfg["strategy"] == "active":
                ir_s = quartile_score(f.get("info_ratio"), [x.get("info_ratio") for x in passed_gates])
                rc_s = quartile_score(f.get("rolling_consistency"), [x.get("rolling_consistency") for x in passed_gates])
                cr_s = quartile_score(f.get("capture_ratio"), [x.get("capture_ratio") for x in passed_gates])
                so_s = quartile_score(f.get("sortino"), [x.get("sortino") for x in passed_gates])
                as_s = quartile_score(f.get("alpha_stability"), [x.get("alpha_stability") for x in passed_gates], higher_is_better=False)
                
                f["total_score"] = 0.25*ir_s + 0.22*rc_s + 0.20*cr_s + 0.18*so_s + 0.15*as_s
            else:
                # Passive score (only tracking error as we don't have historical TER)
                te_s = quartile_score(f.get("tracking_error"), [x.get("tracking_error") for x in passed_gates], higher_is_better=False)
                f["total_score"] = te_s

        b2_fund = sorted(passed_gates, key=lambda x: x.get("total_score", 0), reverse=True)[0]
        bucket2[category] = b2_fund

    return bucket1, bucket2

if __name__ == "__main__":
    start_date = pd.to_datetime("2019-01-01")
    b1, b2 = get_historical_funds(start_date)
    
    print("\n--- Bucket 1 (Best Performers of 2019) ---")
    for cat, f in b1.items():
        print(f"{cat}: {f['name']} ({f['code']})")
        
    print("\n--- Bucket 2 (Tool Selected in 2019) ---")
    for cat, f in b2.items():
        print(f"{cat}: {f['name']} ({f['code']})")

    # Save to file for backtester
    import json
    with open("backtest_buckets_2019.json", "w") as f:
        json.dump({
            "bucket1": {cat: {"code": f["code"], "name": f["name"]} for cat, f in b1.items()},
            "bucket2": {cat: {"code": f["code"], "name": f["name"]} for cat, f in b2.items()}
        }, f, indent=2)
