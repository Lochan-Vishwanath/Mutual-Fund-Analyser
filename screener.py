# ─────────────────────────────────────────────────────────────────────────────
# screener.py  —  Phase 2 elimination + Phase 3 weighted scoring.
#
# v3 Changes:
#   - Phase 3 scoring: includes up_capture and ter_score (new)
#   - Computes category percentiles after all funds are processed
#   - TER fetched and scored (lower = better)
#   - Manager change proxy flag: 1Y return rank divergence vs 3Y rank
#   - Beta context flag (beta > 1.3)
#   - Category average metrics passed into results for UI display
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

from config import (
    CATEGORIES, ROLLING_CONSISTENCY_MIN, ROLLING_CONSISTENCY_FLOOR, SCORE_WEIGHTS,
    MIN_HISTORY_YEARS, ROLLING_WINDOW_YEARS, TOP_N,
    CAPITAL_PROTECTION_MAX, CAPITAL_PROTECTION_FLOOR
)
from fetcher import (
    get_all_direct_growth_funds_by_category,
    get_nav_history, get_amfi_aum_map, get_scheme_name, get_ter_map
)
from metrics import compute_all_metrics, compute_category_percentiles


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _quartile_score(value, all_values: list, higher_is_better: bool = True) -> float:
    """
    Returns 1–4 based on quartile position. Top quartile = 4. Returns 0 if value is None/NaN.
    When higher_is_better=False (down_capture, max_drawdown, ter): top quartile = lowest values.
    """
    clean = [v for v in all_values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not clean or value is None or (isinstance(value, float) and np.isnan(value)):
        return 0.0

    q25, q50, q75 = np.percentile(clean, [25, 50, 75])

    if higher_is_better:
        if value >= q75: return 4.0
        if value >= q50: return 3.0
        if value >= q25: return 2.0
        return 1.0
    else:
        if value <= q25: return 4.0
        if value <= q50: return 3.0
        if value <= q75: return 2.0
        return 1.0


def _weighted_score(fund: dict, all_funds: list) -> float:
    """Compute Phase 3 weighted score. Returns value in [0, 4]."""

    def vals(key):
        return [f.get(key) for f in all_funds]

    rc_score  = _quartile_score(fund.get("rolling_consistency"), vals("rolling_consistency"))
    so_score  = _quartile_score(fund.get("sortino"),             vals("sortino"))
    ir_score  = _quartile_score(fund.get("info_ratio"),          vals("info_ratio"))
    uc_score  = _quartile_score(fund.get("up_capture"),          vals("up_capture"))
    dc_score  = _quartile_score(fund.get("down_capture"),        vals("down_capture"),  higher_is_better=False)
    mdd_score = _quartile_score(fund.get("max_drawdown"),        vals("max_drawdown"),  higher_is_better=False)
    ter_score = _quartile_score(fund.get("ter"),                 vals("ter"),           higher_is_better=False)

    return (
        SCORE_WEIGHTS.get("rolling_consistency", 0) * rc_score +
        SCORE_WEIGHTS.get("sortino_ratio",       0) * so_score +
        SCORE_WEIGHTS.get("information_ratio",   0) * ir_score +
        SCORE_WEIGHTS.get("up_capture",          0) * uc_score +
        SCORE_WEIGHTS.get("down_capture",        0) * dc_score +
        SCORE_WEIGHTS.get("max_drawdown",        0) * mdd_score +
        SCORE_WEIGHTS.get("ter_score",           0) * ter_score
    )


def _compute_passive_score(fund: dict) -> float:
    """For passive funds: score = 1 / tracking_error (lower TE = higher score)."""
    te = fund.get("tracking_error")
    if te and te > 0:
        return 1.0 / te
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Manager change proxy (heuristic — not reliable without manager data API)
# ─────────────────────────────────────────────────────────────────────────────

def _check_manager_change_proxy(fund: dict, all_funds: list) -> dict:
    """
    Heuristic: If a fund's 1Y CAGR percentile rank differs sharply from
    its 5Y CAGR percentile rank (> 30 percentile points), it's a signal
    that something structural may have changed (new manager, mandate shift).

    Returns dict with 'manager_flag' (bool) and 'manager_flag_reason'.
    NOTE: This is a proxy only. Always verify on the AMC website.
    """
    c1 = fund.get("cagr_3y")   # closest to 1Y we track at 3Y
    c5 = fund.get("cagr_5y")

    if c1 is None or c5 is None:
        return {"manager_flag": False, "manager_flag_reason": None}

    all_c1 = [f.get("cagr_3y") for f in all_funds if f.get("cagr_3y") is not None]
    all_c5 = [f.get("cagr_5y") for f in all_funds if f.get("cagr_5y") is not None]

    if len(all_c1) < 5 or len(all_c5) < 5:
        return {"manager_flag": False, "manager_flag_reason": None}

    pct_c1 = (np.array(all_c1) < c1).sum() / len(all_c1) * 100
    pct_c5 = (np.array(all_c5) < c5).sum() / len(all_c5) * 100
    divergence = abs(pct_c1 - pct_c5)

    if divergence > 30:
        return {
            "manager_flag": True,
            "manager_flag_reason": (
                f"3Y rank ({pct_c1:.0f}th pct) diverges {divergence:.0f}pts from "
                f"5Y rank ({pct_c5:.0f}th pct) — verify fund manager hasn't changed"
            )
        }

    return {"manager_flag": False, "manager_flag_reason": None}


# ─────────────────────────────────────────────────────────────────────────────
# Main screener
# ─────────────────────────────────────────────────────────────────────────────

def run_screening(previous_results: dict = None) -> dict[str, dict]:
    """
    Runs the full Phase 2 -> Phase 3 pipeline for every category.
    
    Args:
        previous_results: Dict of results from the previous run (for continuity checks).

    Returns:
    {
      "Mid Cap": {
        "top_funds":            [ {...fund metrics...}, ... ],
        "eliminated":           [ {..., "reason": "..."}, ... ],
        "total_found":          25,
        "total_passed_phase2":  8,
        "is_passive":           False,
        "category_avg":         { "rolling_consistency": 0.62, "cagr_5y": 0.18, ... },
      },
      ...
    }
    """

    aum_map = get_amfi_aum_map()
    ter_map = get_ter_map()   # NEW: fetch TER for all schemes
    results = {}

    for category, cfg in CATEGORIES.items():
        print(f"\n{'='*65}")
        print(f"  CATEGORY: {category}")
        print(f"{'='*65}")

        is_passive   = cfg["strategy"] == "passive"
        bench_code   = cfg.get("benchmark_code")
        aum_min      = cfg.get("aum_min",  0)
        aum_max      = cfg.get("aum_max",  None)
        min_years    = cfg.get("min_history_years", MIN_HISTORY_YEARS)
        aum_max      = cfg.get("aum_max",  None)
        dc_max       = cfg.get("down_capture_max", None)
        min_years    = cfg.get("min_history_years", MIN_HISTORY_YEARS)

        # ── Step 1: Get all funds in AMFI category ────────────────────────
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
                "is_passive": is_passive, "category_avg": {},
            }
            continue

        # ── Step 2: Fetch benchmark ───────────────────────────────────────
        bench_df = None
        if bench_code:
            try:
                bench_df = get_nav_history(bench_code)
                print(f"  Benchmark: {bench_code} ({len(bench_df)} NAV days, "
                      f"{(bench_df['date'].iloc[-1] - bench_df['date'].iloc[0]).days / 365.25:.1f}y)")
            except Exception as e:
                print(f"  [WARN] Benchmark unavailable: {e}")

        # ── Step 3: Phase 2 — Elimination ────────────────────────────────
        # ── Step 3: Phase 2 — Elimination ────────────────────────────────
        passed:         list[dict] = []
        eliminated:     list[dict] = []
        # Collect all computed metrics (even eliminated) for category averages
        all_computed:   list[dict] = []

        print(f"  Phase 1: Filtering by History & AUM...")
        for i, fund in enumerate(all_funds):
            code   = fund["code"]
            name   = fund["name"]
            prefix = f"  [{i+1:>3}/{total_found}]"

            # Gate: History length
            try:
                nav_df = get_nav_history(code)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:52]} — NAV fetch error")
                eliminated.append({**fund, "reason": f"NAV fetch failed: {e}"})
                continue

            years_of_data = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days / 365.25
            if years_of_data < min_years:
                print(f"{prefix} CUT    {name[:52]} — {years_of_data:.1f}y history (need {min_years}y)")
                eliminated.append({**fund, "reason": f"Insufficient history: {years_of_data:.1f}y"})
                continue

            # Gate: AUM
            aum = aum_map.get(code)
            if aum is not None:
                if aum_min and aum < aum_min:
                    print(f"{prefix} CUT    {name[:52]} — AUM ₹{aum:.0f}Cr < min ₹{aum_min}Cr")
                    eliminated.append({**fund, "reason": f"AUM too small: ₹{aum:.0f}Cr"})
                    continue
                if aum_max and aum > aum_max:
                    print(f"{prefix} CUT    {name[:52]} — AUM ₹{aum:.0f}Cr > max ₹{aum_max}Cr")
                    eliminated.append({**fund, "reason": f"AUM too large: ₹{aum:.0f}Cr"})
                    continue

            # Phase 1 Passed -> Compute metrics
            try:
                m = compute_all_metrics(nav_df, bench_df, rolling_window_years=ROLLING_WINDOW_YEARS)
                m.update({"name": name, "code": code, "aum": aum})
                m["ter"] = ter_map.get(code)
                all_computed.append(m)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:52]} — metric error: {e}")
                eliminated.append({**fund, "reason": f"Metric computation failed: {e}"})
                continue

        # ── Phase 2: Hybrid Dynamic Gates ─────────────────────────────────────
        if all_computed:
            cat_stats = _compute_category_stats(all_computed)
            print(f"\n  Category Stats for Dynamic Gates:")
            for k, v in cat_stats.items():
                if v is not None: print(f"    - {k:25}: {v:.2f}")

            for m in all_computed:
                name = m["name"]
                code = m["code"]
                prefix = f"  [GATE]"

                # Gate: Negative Sharpe Ratio
                sharpe = m.get("sharpe")
                if sharpe is not None and sharpe < 0:
                    print(f"{prefix} CUT    {name[:52]} — Negative Sharpe {sharpe:.2f}")
                    eliminated.append({**m, "reason": f"Negative Sharpe Ratio: {sharpe:.2f}"})
                    continue

                if not is_passive:
                    # Hybrid Gate: Rolling consistency
                    rc = m.get("rolling_consistency")
                    rc_med = cat_stats.get("rolling_consistency_median")
                    if rc is not None and not np.isnan(rc):
                        # Rule: Must beat Index floor AND be >= Category Median
                        if rc < ROLLING_CONSISTENCY_FLOOR:
                            reason = f"Rolling consistency {rc:.0%} < floor {ROLLING_CONSISTENCY_FLOOR:.0%}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue
                        if rc_med is not None and rc < rc_med:
                            reason = f"Rolling consistency {rc:.0%} < category median {rc_med:.0%}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue


                    # Hybrid Gate: Capital protection
                    cp = m.get("capital_protection")
                    # Hybrid Gate: Capital protection
                    cp = m.get("capital_protection")
                    if cp is not None and not np.isnan(cp):
                        if cp > CAPITAL_PROTECTION_FLOOR:
                            reason = f"Negative windows {cp:.0%} > floor {CAPITAL_PROTECTION_FLOOR:.0%}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue
                        # (Optional: we could add a category-relative gate for CP, but 5-10% is already strict)

                    # Hybrid Gate: Upside Capture
                    uc = m.get("up_capture")
                    uc_avg = cat_stats.get("up_capture_mean")
                    if uc is not None and not np.isnan(uc):
                        if uc_avg is not None and uc < uc_avg:
                            reason = f"Up capture {uc:.1f} < category average {uc_avg:.1f}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue

                    # Hybrid Gate: Downside Capture
                    dc = m.get("down_capture")
                    dc_avg = cat_stats.get("down_capture_mean")
                    if dc is not None and not np.isnan(dc):
                        if dc_avg is not None and dc > dc_avg:
                            reason = f"Down capture {dc:.1f} > category average {dc_avg:.1f}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue

                    dc_avg = cat_stats.get("down_capture_mean")
                    if dc is not None and not np.isnan(dc):
                        # Use dc_max from config if provided, otherwise use category average
                        effective_dc_max = dc_max if dc_max is not None else dc_avg
                        if effective_dc_max is not None and dc > effective_dc_max:
                            reason = f"Down capture {dc:.1f} > category limit {effective_dc_max:.1f}"
                            print(f"{prefix} CUT    {name[:52]} — {reason}")
                            eliminated.append({**m, "reason": reason})
                            continue

                # If we reached here, fund passed all gates
                print(f"{prefix} PASS   {name[:52]}")
                passed.append(m)

        total_passed = len(passed)
        print(f"\n  Phase 2: {total_passed} funds passed hybrid gates")


        # Collect all computed metrics (even eliminated) for category averages
        all_computed:   list[dict] = []

        for i, fund in enumerate(all_funds):
            code   = fund["code"]
            name   = fund["name"]
            prefix = f"  [{i+1:>3}/{total_found}]"

            # Gate: History length
            try:
                nav_df = get_nav_history(code)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:52]} — NAV fetch error")
                eliminated.append({**fund, "reason": f"NAV fetch failed: {e}"})
                continue

            years_of_data = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days / 365.25
            if years_of_data < min_years:
                print(f"{prefix} CUT    {name[:52]} — {years_of_data:.1f}y history (need {min_years}y)")
                eliminated.append({**fund, "reason": f"Insufficient history: {years_of_data:.1f}y"})
                continue

            # Gate: AUM
            aum = aum_map.get(code)
            if aum is not None:
                if aum_min and aum < aum_min:
                    print(f"{prefix} CUT    {name[:52]} — AUM ₹{aum:.0f}Cr < min ₹{aum_min}Cr")
                    eliminated.append({**fund, "reason": f"AUM too small: ₹{aum:.0f}Cr"})
                    continue
                if aum_max and aum > aum_max:
                    print(f"{prefix} CUT    {name[:52]} — AUM ₹{aum:.0f}Cr > max ₹{aum_max}Cr")
                    eliminated.append({**fund, "reason": f"AUM too large: ₹{aum:.0f}Cr"})
                    continue

            # Compute all metrics
            try:
                m = compute_all_metrics(nav_df, bench_df, rolling_window_years=ROLLING_WINDOW_YEARS)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:52]} — metric error: {e}")
                eliminated.append({**fund, "reason": f"Metric computation failed: {e}"})
                continue

            # Attach TER from AMFI map
            m["ter"] = ter_map.get(code)   # None if unavailable

            m.update({"name": name, "code": code, "aum": aum})
            all_computed.append(m)

            # Gate: Negative Sharpe Ratio (Gap 4 Fix)
            sharpe = m.get("sharpe")
            if sharpe is not None and sharpe < 0:
                print(f"{prefix} CUT    {name[:52]} — Negative Sharpe {sharpe:.2f}")
                eliminated.append({**fund, **m, "reason": f"Negative Sharpe Ratio: {sharpe:.2f}"})
                continue

            # ── Active-only Phase 2 gates ─────────────────────────────────
            if not is_passive:

                # Gate: Rolling return consistency
                rc = m.get("rolling_consistency")
                if rc is not None and not np.isnan(rc) and rc < ROLLING_CONSISTENCY_MIN:
                    print(f"{prefix} CUT    {name[:52]} — rolling {rc:.0%} < {ROLLING_CONSISTENCY_MIN:.0%}")
                    eliminated.append({**fund, **m,
                                       "reason": f"Rolling consistency {rc:.0%} < threshold {ROLLING_CONSISTENCY_MIN:.0%}"})
                    continue

                # Gate: Capital protection
                cp = m.get("capital_protection")
                if cp is not None and not np.isnan(cp) and cp > CAPITAL_PROTECTION_MAX:
                    print(f"{prefix} CUT    {name[:52]} — negative returns in {cp:.0%} of windows")
                    eliminated.append({**fund, **m,
                                       "reason": f"Negative return windows {cp:.0%} > max {CAPITAL_PROTECTION_MAX:.0%}"})
                    continue

                # Gate: Down-market capture
                if dc_max is not None:
                    dc = m.get("down_capture")
                    if dc is not None and not np.isnan(dc) and dc > dc_max:
                        print(f"{prefix} CUT    {name[:52]} — down capture {dc:.1f} > {dc_max}")
                        eliminated.append({**fund, **m,
                                           "reason": f"Down capture {dc:.1f} > threshold {dc_max}"})
                        continue

            print(f"{prefix} PASS   {name[:52]}")
            passed.append(m)

        total_passed = len(passed)
        print(f"\n  Phase 2: {total_passed}/{total_found} passed")

        # Compute category percentiles across ALL computed funds (not just passed)
        if all_computed:
            all_computed = compute_category_percentiles(all_computed)
            # Sync percentile back to passed list
            pct_map = {f["code"]: f.get("rolling_category_percentile") for f in all_computed}
            for f in passed:
                f["rolling_category_percentile"] = pct_map.get(f["code"])

        # Category average metrics (for UI display)
        category_avg = _compute_category_avg(all_computed)

        if not passed:
            print(f"  [WARN] Zero funds passed Phase 2 — using metric-computed fallback")
            passed = [f for f in all_computed if "cagr_5y" in f and f.get("cagr_5y") is not None]

        # ── Step 4: Manager change proxy flags ────────────────────────────
        for f in passed:
            proxy = _check_manager_change_proxy(f, passed)
            f.update(proxy)

        # ── Step 5: Beta context flag ─────────────────────────────────────
        for f in passed:
            beta = f.get("beta")
            if beta is not None and not np.isnan(beta) and beta > 1.3:
                f["beta_flag"] = True
                f["beta_flag_reason"] = (
                    f"Beta {beta:.2f} — fund amplifies market moves by {beta:.0%}. "
                    f"Verify this is intentional and not capturing undue risk."
                )
            else:
                f["beta_flag"] = False
                f["beta_flag_reason"] = None

        # ── Step 6: Phase 3 — Weighted Scoring ───────────────────────────
        if is_passive:
            for f in passed:
                f["total_score"] = _compute_passive_score(f)
            ranked = sorted(passed, key=lambda x: x.get("tracking_error") or 999)
        else:
            for f in passed:
                f["total_score"] = _weighted_score(f, passed)
            ranked = sorted(passed, key=lambda x: x["total_score"], reverse=True)

        top_n_funds = ranked[:TOP_N]

        # ── Step 7: Continuity Check (Holdover vs New Entrant) ────────────────
        if previous_results and category in previous_results:
            prev_top_codes = {f["code"] for f in previous_results[category].get("top_funds", [])}
            for f in top_n_funds:
                if f["code"] in prev_top_codes:
                    f["continuity_status"] = "Holdover 🛡️"
                    f["continuity_desc"]   = "Was in Top 3 last quarter — safe to hold."
                else:
                    f["continuity_status"] = "New Entrant 🌟"
                    f["continuity_desc"]   = "New to Top 3 — verify exit triggers before switching."
        else:
            for f in top_n_funds:
                f["continuity_status"] = "New Entrant 🌟" if previous_results else "—" # First run ever
                f["continuity_desc"]   = ""

        print(f"\n  TOP {TOP_N} [{category}]:")
        for rank, f in enumerate(top_n_funds, 1):
            rc   = f.get("rolling_consistency")
            uc   = f.get("up_capture")
            dc   = f.get("down_capture")
            sc   = f.get("total_score", 0)
            pct  = f.get("rolling_category_percentile")
            cont = f.get("continuity_status", "")
            mngr_console = "[!] MANAGER FLAG" if f.get("manager_flag") else ""
            beta_console = "[!] HIGH BETA" if f.get("beta_flag") else ""
            
            cont_console = cont.replace("🛡️", "").replace("🌟", "").strip()
            print(f"  #{rank}: {f['name'][:50]}  {cont_console}")
            print(f"       Score: {sc:.2f}/4.00 | Rolling: {rc:.0%} ({pct:.0f}th pct)" if rc and pct else
                  f"       Score: {sc:.2f}/4.00")
            print(f"       Up: {uc:.1f} | Down: {dc:.1f}" if uc and dc else "", end="")
            print(f"  {mngr_console} {beta_console}")



        results[category] = {
            "top_funds":            top_n_funds,
            "eliminated":           eliminated,
            "total_found":          total_found,
            "total_passed_phase2":  total_passed,
            "is_passive":           is_passive,
            "category_avg":         category_avg,
        }

    # ── Save JSON ─────────────────────────────────────────────────────────
    out_dir  = Path("./output")
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "latest_results.json"

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):  return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray):  return obj.tolist()
            return super().default(obj)

    with open(json_path, "w") as f:
        json.dump(results, f, cls=NpEncoder, indent=2)
    print(f"\n  Results saved -> {json_path}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Category Average Helper
# ─────────────────────────────────────────────────────────────────────────────

def _compute_category_stats(fund_list: list[dict]) -> dict:
    """
    Computes medians and means for key metrics to be used in dynamic gates.
    """
    keys = ["rolling_consistency", "up_capture", "down_capture"]
    stats = {}
    for key in keys:
        vals = [f.get(key) for f in fund_list 
                if f.get(key) is not None and not (isinstance(f.get(key), float) and np.isnan(f.get(key)))]
        if vals:
            stats[f"{key}_median"] = float(np.median(vals))
            stats[f"{key}_mean"]   = float(np.mean(vals))
        else:
            stats[f"{key}_median"] = None
            stats[f"{key}_mean"]   = None
    return stats


def _compute_category_avg(fund_list: list[dict]) -> dict:
    """
    Computes category-wide average for key metrics.
    Used in the UI to show "Category Average" row for context.
    """
    keys = [
        "cagr_5y", "rolling_consistency", "sortino", "down_capture",
        "up_capture", "max_drawdown", "info_ratio", "ter"
    ]
    avg = {}
    for key in keys:
        vals = [f.get(key) for f in fund_list
                if f.get(key) is not None and not (isinstance(f.get(key), float) and np.isnan(f.get(key)))]
        avg[key] = float(np.mean(vals)) if vals else None
    return avg
