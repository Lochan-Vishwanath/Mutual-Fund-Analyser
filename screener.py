# ─────────────────────────────────────────────────────────────────────────────
# screener.py  —  Phase 2 elimination + Phase 3 weighted scoring.
#
# Key change vs. v1:
#   - Fetches ALL Direct Growth funds in each category from AMFI
#   - Runs full strategy on every fund (not a manual shortlist)
#   - Returns top N per category instead of just the winner
#   - Tracks every elimination reason so the email shows why funds were cut
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
from datetime import datetime
from config import (
    CATEGORIES, ROLLING_CONSISTENCY_MIN, SCORE_WEIGHTS,
    MIN_HISTORY_YEARS, ROLLING_WINDOW_YEARS, TOP_N
)
from fetcher import (
    get_all_direct_growth_funds_by_category,
    get_nav_history, get_amfi_aum_map, get_scheme_name
)
from metrics import compute_all_metrics


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _quartile_score(value: float, all_values: list, higher_is_better: bool = True) -> float:
    """
    Returns 1–4 based on which quartile the value falls in.
    Top quartile = 4, bottom quartile = 1. Returns 0 if value is NaN.
    """
    clean = [v for v in all_values if v is not None and not np.isnan(v)]
    if not clean or (value is None) or np.isnan(value):
        return 0.0
    q25, q50, q75 = np.percentile(clean, [25, 50, 75])
    if higher_is_better:
        if value >= q75: return 4.0
        if value >= q50: return 3.0
        if value >= q25: return 2.0
        return 1.0
    else:  # lower is better (down capture, max drawdown)
        if value <= q25: return 4.0
        if value <= q50: return 3.0
        if value <= q75: return 2.0
        return 1.0


def _weighted_score(fund: dict, all_funds: list) -> float:
    """Compute the Phase 3 weighted score for a single fund."""
    def vals(key):
        return [f.get(key) for f in all_funds]

    rc_score  = _quartile_score(fund.get("rolling_consistency"), vals("rolling_consistency"))
    so_score  = _quartile_score(fund.get("sortino"),             vals("sortino"))
    ir_score  = _quartile_score(fund.get("info_ratio"),          vals("info_ratio"))
    dc_score  = _quartile_score(fund.get("down_capture"),        vals("down_capture"),        higher_is_better=False)
    mdd_score = _quartile_score(fund.get("max_drawdown"),        vals("max_drawdown"),        higher_is_better=False)

    return (
        SCORE_WEIGHTS["rolling_consistency"] * rc_score +
        SCORE_WEIGHTS["sortino_ratio"]       * so_score +
        SCORE_WEIGHTS["information_ratio"]   * ir_score +
        SCORE_WEIGHTS["down_capture"]        * dc_score +
        SCORE_WEIGHTS["max_drawdown"]        * mdd_score
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main screener
# ─────────────────────────────────────────────────────────────────────────────

def run_screening() -> dict[str, dict]:
    """
    Runs the full Phase 2 → Phase 3 pipeline for every category.

    Returns:
    {
      "Mid Cap": {
        "top_funds":   [ {...fund metrics...}, ... ],   # top N, ranked
        "eliminated":  [ {..., "reason": "..."}, ... ],
        "total_found": 25,                              # total in category
        "total_passed_phase2": 8,
        "is_passive": False,
      },
      ...
    }
    """
    aum_map = get_amfi_aum_map()
    results = {}

    for category, cfg in CATEGORIES.items():
        print(f"\n{'='*65}")
        print(f"  CATEGORY: {category}")
        print(f"{'='*65}")

        is_passive   = cfg["strategy"] == "passive"
        bench_code   = cfg.get("benchmark_code")
        aum_min      = cfg.get("aum_min",  0)
        aum_max      = cfg.get("aum_max",  None)
        dc_max       = cfg.get("down_capture_max", None)
        min_years    = cfg.get("min_history_years", MIN_HISTORY_YEARS)

        # ── Step 1: Get all funds in this AMFI category ──────────────────
        all_funds = get_all_direct_growth_funds_by_category(
            amfi_category_keywords = cfg["amfi_category_keywords"],
            name_must_contain      = cfg.get("name_must_contain", []),
        )
        total_found = len(all_funds)
        print(f"  Found {total_found} Direct Growth funds in AMFI category")

        if total_found == 0:
            print(f"  [WARN] No funds found — check amfi_category_keywords in config.py")
            results[category] = {
                "top_funds": [], "eliminated": [],
                "total_found": 0, "total_passed_phase2": 0,
                "is_passive": is_passive,
            }
            continue

        # ── Step 2: Fetch benchmark ───────────────────────────────────────
        bench_df = None
        if bench_code:
            try:
                bench_df = get_nav_history(bench_code)
                print(f"  Benchmark: {bench_code} ({len(bench_df)} days)")
            except Exception as e:
                print(f"  [WARN] Benchmark unavailable: {e}")

        # ── Step 3: Phase 2 — Elimination ────────────────────────────────
        passed:     list[dict] = []
        eliminated: list[dict] = []

        for i, fund in enumerate(all_funds):
            code = fund["code"]
            name = fund["name"]
            prefix = f"  [{i+1:>3}/{total_found}]"

            # ── Gate: History length ─────────────────────────────────────
            try:
                nav_df = get_nav_history(code)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:50]} — NAV fetch error")
                eliminated.append({**fund, "reason": f"NAV fetch failed: {e}"})
                continue

            years_of_data = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days / 365.25
            if years_of_data < min_years:
                print(f"{prefix} CUT    {name[:50]} — only {years_of_data:.1f}y history (need {min_years}y)")
                eliminated.append({**fund, "reason": f"Insufficient history: {years_of_data:.1f}y"})
                continue

            # ── Gate: AUM ────────────────────────────────────────────────
            aum = aum_map.get(code)
            if aum is not None:
                if aum_min and aum < aum_min:
                    print(f"{prefix} CUT    {name[:50]} — AUM ₹{aum:.0f}Cr < min")
                    eliminated.append({**fund, "reason": f"AUM too small: ₹{aum:.0f}Cr"})
                    continue
                if aum_max and aum > aum_max:
                    print(f"{prefix} CUT    {name[:50]} — AUM ₹{aum:.0f}Cr > max")
                    eliminated.append({**fund, "reason": f"AUM too large: ₹{aum:.0f}Cr"})
                    continue

            # ── Compute all metrics ──────────────────────────────────────
            try:
                m = compute_all_metrics(nav_df, bench_df, rolling_window_years=ROLLING_WINDOW_YEARS)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:50]} — metric error: {e}")
                eliminated.append({**fund, "reason": f"Metric computation failed: {e}"})
                continue

            m.update({"name": name, "code": code, "aum": aum})

            # ── Gate: Rolling return consistency (active only) ───────────
            if not is_passive:
                rc = m.get("rolling_consistency")
                if rc is not None and not np.isnan(rc) and rc < ROLLING_CONSISTENCY_MIN:
                    print(f"{prefix} CUT    {name[:50]} — rolling {rc:.0%} < {ROLLING_CONSISTENCY_MIN:.0%}")
                    eliminated.append({**fund, **m, "reason": f"Rolling consistency {rc:.0%} below threshold"})
                    continue
                    
                # ── Gate: Absolute Return Consistency (Advisorkhoj method) ───
                from config import ABSOLUTE_RETURN_MIN_PCT, CAPITAL_PROTECTION_MAX
                ac = m.get("absolute_consistency")
                if ac is not None and not np.isnan(ac) and ac < ABSOLUTE_RETURN_MIN_PCT:
                    print(f"{prefix} CUT    {name[:50]} — abs return < target in {1-ac:.0%} of windows")
                    eliminated.append({**fund, **m, "reason": f"Absolute return consistency {ac:.0%} below {ABSOLUTE_RETURN_MIN_PCT:.0%}"})
                    continue
                    
                cp = m.get("capital_protection")
                if cp is not None and not np.isnan(cp) and cp > CAPITAL_PROTECTION_MAX:
                    print(f"{prefix} CUT    {name[:50]} — negative returns in {cp:.0%} of windows")
                    eliminated.append({**fund, **m, "reason": f"Negative returns {cp:.0%} above max {CAPITAL_PROTECTION_MAX:.0%}"})
                    continue
            # ── Gate: Down-market capture (active only) ──────────────────
            if not is_passive and dc_max is not None:
                dc = m.get("down_capture")
                if dc is not None and not np.isnan(dc) and dc > dc_max:
                    print(f"{prefix} CUT    {name[:50]} — down capture {dc:.1f} > {dc_max}")
                    eliminated.append({**fund, **m, "reason": f"Down capture {dc:.1f} > threshold {dc_max}"})
                    continue

            print(f"{prefix} PASS   {name[:50]}")
            passed.append(m)

        total_passed = len(passed)
        print(f"\n  Phase 2 result: {total_passed}/{total_found} funds passed")

        if not passed:
            print(f"  [WARN] Zero funds passed Phase 2 — relaxing rolling consistency gate for this run.")
            # Fallback: keep any fund that had successful metric computation
            passed = [f for f in eliminated if "cagr_5y" in f]

        # ── Step 4: Phase 3 — Weighted Scoring ───────────────────────────
        if is_passive:
            # Sort passive funds by tracking error (lower = better)
            for f in passed:
                te = f.get("tracking_error")
                f["total_score"] = (1.0 / te) if (te and te > 0) else 0.0
            ranked = sorted(passed, key=lambda x: x.get("tracking_error") or 999)
        else:
            for f in passed:
                f["total_score"] = _weighted_score(f, passed)
            ranked = sorted(passed, key=lambda x: x["total_score"], reverse=True)

        top_n_funds = ranked[:TOP_N]

        print(f"\n  TOP {TOP_N} for [{category}]:")
        for rank, f in enumerate(top_n_funds, 1):
            rc  = f.get("rolling_consistency")
            sc  = f.get("total_score", 0)
            print(f"  #{rank}: {f['name'][:58]}")
            if rc: print(f"       Rolling: {rc:.0%}  Score: {sc:.2f}/4.00")

        results[category] = {
            "top_funds":            top_n_funds,
            "eliminated":           eliminated,
            "total_found":          total_found,
            "total_passed_phase2":  total_passed,
            "is_passive":           is_passive,
        }

    # Save structured results to JSON for frontend
    out_dir = Path("./output")
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "latest_results.json"
    
    # Need to clean data for JSON (handle dates/NaNs if any remains, though metrics handles it)
    # But wait, 'top_funds' and 'eliminated' are list of dicts.
    # We should serialize them carefully.
    
    # We will let the caller handle saving or do it here.
    # The user asked: "for each step i want the data to be saved"
    # So saving here is good.
    import json
    
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return super(NpEncoder, self).default(obj)
            
    with open(json_path, "w") as f:
        json.dump(results, f, cls=NpEncoder, indent=2)
    print(f"\n  Data saved to {json_path}")

    return results
