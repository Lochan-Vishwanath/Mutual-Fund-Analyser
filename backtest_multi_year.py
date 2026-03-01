
import pandas as pd
import json
from datetime import datetime
from backtest_engine import Portfolio, pick_best_fund, check_fund_fails_gate

def run_single_backtest(year):
    print(f"\n>>> STARTING BACKTEST FOR YEAR {year} <<<")
    bucket_file = f"buckets_{year}.json"
    if year == 2019:
        bucket_file = "backtest_buckets_2019.json"
        
    with open(bucket_file) as f:
        config_data = json.load(f)
    
    p1 = Portfolio(f"B1_{year}_Best")
    p2 = Portfolio(f"B2_{year}_Tool_Rebal")
    p3 = Portfolio(f"B3_{year}_Tool_Hold")
    
    for cat, fund in config_data["bucket1"].items():
        p1.add_fund(cat, fund["code"], fund["name"])
    for cat, fund in config_data["bucket2"].items():
        p2.add_fund(cat, fund["code"], fund["name"])
        p3.add_fund(cat, fund["code"], fund["name"])
        
    start_date = pd.to_datetime(f"{year}-01-01")
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
    results = {}
    for p in [p1, p3, p2]:
        total_inv = p.out_of_pocket
        total_post_tax = sum(p.get_category_metrics(cat, today)["post_tax_value"] for cat in p.funds.keys())
        results[p.bucket_name] = {
            "invested": total_inv,
            "post_tax_value": total_post_tax,
            "return_pct": (total_post_tax / total_inv - 1) * 100
        }
    return results

if __name__ == "__main__":
    years = [2019, 2020, 2021, 2022] # Start with these as they are ready
    # Check if 2023/2024 exist
    import os
    if os.path.exists("buckets_2023.json"): years.append(2023)
    if os.path.exists("buckets_2024.json"): years.append(2024)
    
    all_results = {}
    for y in years:
        all_results[y] = run_single_backtest(y)
        
    with open("multi_year_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    
    print("\n" + "="*50)
    print("MULTI-YEAR BACKTEST SUMMARY")
    print("="*50)
    print(f"{'Year':<6} | {'Best of Year':<15} | {'Tool (Hold)':<15} | {'Tool (Rebal)':<15}")
    print("-" * 60)
    for y in sorted(years):
        r = all_results[y]
        b1 = r[f"B1_{y}_Best"]["return_pct"]
        b3 = r[f"B3_{y}_Tool_Hold"]["return_pct"]
        b2 = r[f"B2_{y}_Tool_Rebal"]["return_pct"]
        print(f"{y:<6} | {b1:>13.1f}% | {b3:>13.1f}% | {b2:>13.1f}%")
