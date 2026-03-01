
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from backtest_tax_logic import get_nav_history_cached, get_funds_cached, get_bench_cached, compute_all_metrics, SHARPE_GATE_MIN, get_closest_nav

def xirr(dates, cash_flows):
    years = [(d - dates[0]).days / 365.25 for d in dates]
    def npv(rate): return sum(cf / (1 + rate)**y for cf, y in zip(cash_flows, years))
    def d_npv(rate): return sum(-y * cf / (1 + rate)**(y + 1) for cf, y in zip(cash_flows, years))
    rate = 0.1
    for _ in range(100):
        try:
            prev_rate = rate
            rate = rate - npv(rate) / d_npv(rate)
            if abs(rate - prev_rate) < 1e-6: return rate
        except: return None
    return None

def run_rolling_xirr():
    print("\n" + "="*60)
    print("ROLLING WINDOW XIRR ANALYSIS (3-YEAR WINDOWS)")
    print("="*60)
    start_point = pd.to_datetime("2013-01-01")
    end_point = datetime.now() - pd.DateOffset(years=3)
    windows = pd.date_range(start=start_point, end=end_point, freq='3ME')
    results = []
    
    proxy_bench_code = "120716"
    bench_nav_full = get_nav_history_cached(proxy_bench_code)

    for start_date in windows:
        end_date = start_date + pd.DateOffset(years=3)
        cat = "Flexi Cap"
        all_funds = get_funds_cached(cat)
        
        bench_df = get_bench_cached(cat, start_date)
        if bench_df is None or bench_df.empty:
            bench_df = bench_nav_full[bench_nav_full['date'] <= start_date]

        passed = []
        for f in all_funds:
            try:
                nav_df = get_nav_history_cached(f["code"])
                nav_hist = nav_df[nav_df['date'] <= start_date]
                if len(nav_hist) < 252 * 3: continue
                m = compute_all_metrics(nav_hist, bench_df, rolling_window_years=3)
                m.update(f)
                if m.get("sharpe", 0) < SHARPE_GATE_MIN: continue
                if m.get("rolling_consistency", 0) < 0.50: continue
                passed.append(m)
            except: continue
        
        if not passed: continue
        
        def q_score(val, all_v, high=True):
            clean = [v for v in all_v if v is not None and not np.isnan(v)]
            if not clean: return 1.0
            q50 = np.median(clean)
            if high: return 4.0 if val >= q50 else 2.0
            else: return 4.0 if val <= q50 else 2.0

        for f in passed:
            ir_s = q_score(f.get("info_ratio"), [x.get("info_ratio") for x in passed])
            rc_s = q_score(f.get("rolling_consistency"), [x.get("rolling_consistency") for x in passed])
            f["total_score"] = 0.5*ir_s + 0.5*rc_s
            
        best_f = sorted(passed, key=lambda x: x.get("total_score", 0), reverse=True)[0]
        nav_df_f = get_nav_history_cached(best_f["code"])
        cf, d, u = [], [], 0
        sd = start_date
        while sd < end_date:
            r = get_closest_nav(nav_df_f, sd)
            cf.append(-10000); d.append(r['date']); u += 10000 / r['nav']; sd += pd.DateOffset(months=1)
        re = get_closest_nav(nav_df_f, end_date)
        cf.append(u * re['nav']); d.append(re['date'])
        t_x = xirr(d, cf)
        
        cf_b, d_b, u_b = [], [], 0
        sd = start_date
        while sd < end_date:
            r = get_closest_nav(bench_nav_full, sd)
            cf_b.append(-10000); d_b.append(r['date']); u_b += 10000 / r['nav']; sd += pd.DateOffset(months=1)
        re_b = get_closest_nav(bench_nav_full, end_date)
        cf_b.append(u_b * re_b['nav']); d_b.append(re_b['date'])
        b_x = xirr(d_b, cf_b)
        
        if t_x is not None and b_x is not None:
            results.append({"start": str(start_date.date()), "tool": float(t_x*100), "bench": float(b_x*100), "win": bool(t_x > b_x)})
            print(f"Window {start_date.date()}: Tool {t_x*100:.1f}% vs Bench {b_x*100:.1f}% {'(WIN)' if t_x > b_x else ''}")

    if not results: return
    win_pct = sum(1 for r in results if r["win"]) / len(results) * 100
    avg_alpha = sum(r["tool"] - r["bench"] for r in results) / len(results)
    print(f"\nSUMMARY:\n  Total Windows: {len(results)}\n  Outperformance Prob: {win_pct:.1f}%\n  Avg Alpha: {avg_alpha:.2f}%")
    with open("rolling_xirr_results.json", "w") as f: json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_rolling_xirr()
