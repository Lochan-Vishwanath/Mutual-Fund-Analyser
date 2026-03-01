
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from config import CATEGORIES, ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR, SHARPE_GATE_MIN, CAPTURE_RATIO_MIN
from fetcher import get_all_direct_growth_funds_by_category, get_nav_history
from metrics import compute_all_metrics

# In-memory cache for expensive calls
NAV_MEMORY_CACHE = {}

def get_nav_history_cached(code):
    if code not in NAV_MEMORY_CACHE:
        try:
            NAV_MEMORY_CACHE[code] = get_nav_history(code)
        except:
            return None
    return NAV_MEMORY_CACHE[code]

def get_historical_funds(target_date):
    bucket1 = {} 
    bucket2 = {} 

    for category, cfg in CATEGORIES.items():
        all_funds = get_all_direct_growth_funds_by_category(
            amfi_category_keywords=cfg["amfi_category_keywords"],
            name_must_contain=cfg.get("name_must_contain", [])
        )
        
        bench_code = cfg.get("benchmark_code")
        bench_df_full = get_nav_history_cached(bench_code) if bench_code else None
        bench_df = bench_df_full[bench_df_full['date'] <= target_date] if bench_df_full is not None else None

        category_funds_metrics = []
        for fund in all_funds:
            nav_df_full = get_nav_history_cached(fund["code"])
            if nav_df_full is None: continue
            nav_df_hist = nav_df_full[nav_df_full['date'] <= target_date]
            
            # Use 5 years history floor
            if len(nav_df_hist) < 252 * 5: continue
            
            # Pre-filter by CAGR if we have too many funds to speed up
            try:
                # Basic CAGR 3Y check first
                nav_series = nav_df_hist["nav"]
                lookback = int(3 * 252)
                if len(nav_series) > lookback:
                    start_val = nav_series.iloc[-(lookback + 1)]
                    end_val = nav_series.iloc[-1]
                    c3 = (end_val / start_val) ** (1/3) - 1
                    fund["cagr_3y_pre"] = c3
                else:
                    fund["cagr_3y_pre"] = -1
                
                # If we have many funds, only compute full metrics for top performers/likely candidates
                # But for now, let's just compute all metrics but more robustly.
                m = compute_all_metrics(nav_df_hist, bench_df, rolling_window_years=cfg.get("rolling_window_years", 3))
                m.update(fund)
                category_funds_metrics.append(m)
            except: continue

        if not category_funds_metrics: continue

        # Bucket 1: Best performers (3Y CAGR)
        b1_fund = sorted(category_funds_metrics, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[0]
        bucket1[category] = {"code": b1_fund["code"], "name": b1_fund["name"]}

        # Bucket 2: Tool selection
        passed_gates = []
        consistency_floor = ROLLING_CONSISTENCY_FLOORS.get(cfg.get("consistency_floor_key"), 0.55)
        for m in category_funds_metrics:
            if m.get("sharpe") is not None and m["sharpe"] < SHARPE_GATE_MIN: continue
            if cfg["strategy"] == "active":
                if m.get("rolling_consistency") is not None and m["rolling_consistency"] < consistency_floor: continue
                if m.get("capital_protection") is not None and m["capital_protection"] > CAPITAL_PROTECTION_FLOOR: continue
                if m.get("capture_ratio") is not None and m["capture_ratio"] < CAPTURE_RATIO_MIN: continue
            passed_gates.append(m)

        if not passed_gates:
            passed_gates = sorted(category_funds_metrics, key=lambda x: x.get("cagr_3y") or -1, reverse=True)[:5]

        # Simplified Scoring
        def q_score(val, all_v, high=True):
            clean = [v for v in all_v if v is not None and not np.isnan(v)]
            if not clean or val is None or np.isnan(val): return 1.0
            q25, q50, q75 = np.percentile(clean, [25, 50, 75])
            if high:
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
                ir_s = q_score(f.get("info_ratio"), [x.get("info_ratio") for x in passed_gates])
                rc_s = q_score(f.get("rolling_consistency"), [x.get("rolling_consistency") for x in passed_gates])
                cr_s = q_score(f.get("capture_ratio"), [x.get("capture_ratio") for x in passed_gates])
                so_s = q_score(f.get("sortino"), [x.get("sortino") for x in passed_gates])
                as_s = q_score(f.get("alpha_stability"), [x.get("alpha_stability") for x in passed_gates], high=False)
                f["score"] = 0.25*ir_s + 0.22*rc_s + 0.20*cr_s + 0.18*so_s + 0.15*as_s
            else:
                f["score"] = q_score(f.get("tracking_error"), [x.get("tracking_error") for x in passed_gates], high=False)

        b2_fund = sorted(passed_gates, key=lambda x: x.get("score", 0), reverse=True)[0]
        bucket2[category] = {"code": b2_fund["code"], "name": b2_fund["name"]}

    return bucket1, bucket2

if __name__ == "__main__":
    for year in range(2023, 2025):
        print(f"Generating buckets for {year}...")
        date = pd.to_datetime(f"{year}-01-01")
        b1, b2 = get_historical_funds(date)
        with open(f"buckets_{year}.json", "w") as f:
            json.dump({"bucket1": b1, "bucket2": b2}, f, indent=2)
