from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# screener.py  —  Full screening pipeline for MF Analyser v4.0
#
# Architecture (matches v4 design doc):
#   Phase 1 : Static Hard Filters (History, AUM — category-specific bounds)
#   Phase 2 : Hybrid Dynamic Gates (Sharpe, TER, Rolling Consistency,
#              Capital Protection, Capture Ratio — all category-relative)
#   Phase 3 : Weighted Scoring on 5 non-collinear metrics
#              (IR 25%, Consistency 22%, Capture Ratio 20%, Sortino 18%, Alpha Stability 15%)
#   Phase 4 : Qualitative Flags
#              (Manager Change [2-signal], High Beta, Concentration, PTR, Continuity)
#
# Active/Passive Fork:
#   - "passive" strategy → Phase P scoring (TE 70% + TER 30%), no Phase 2/3 active gates
#   - "active" strategy  → Full Phase 1-4 pipeline
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

from config import (
    CATEGORIES, SCORE_WEIGHTS, PASSIVE_SCORE_WEIGHTS, TOP_N,
    ROLLING_CONSISTENCY_FLOORS, CAPITAL_PROTECTION_FLOOR,
    SHARPE_GATE_MIN, TER_GATE_SPREAD, CAPTURE_RATIO_MIN,
    HIGH_BETA_THRESHOLD, MANAGER_CHANGE_VOL_THRESHOLD,
    CONCENTRATION_FLAG_DELTA, PTR_FLAG_SD_MULTIPLIER,
)
from fetcher import (
    get_all_direct_growth_funds_by_category,
    get_nav_history, get_amfi_aum_map, get_scheme_name, get_ter_map,
)
from metrics import (
    compute_all_metrics, compute_category_percentiles,
    compute_manager_change_signals,
)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────────────────────────────────────

def _quartile_score(value, all_values: list, higher_is_better: bool = True) -> float:
    """
    Returns 1.0–4.0 based on quartile position within a peer group.
    Top quartile = 4.0 regardless of direction.
    Returns 0.0 if value is None/NaN (not penalised, just unscored).
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
    else:  # lower_is_better: lower value = better quartile
        if value <= q25: return 4.0
        if value <= q50: return 3.0
        if value <= q75: return 2.0
        return 1.0


def _active_score(fund: dict, all_funds: list) -> float:
    """
    Phase 3 weighted scoring for active funds.
    5 non-collinear dimensions:
      IR (25%) + Rolling Consistency (22%) + Capture Ratio (20%)
      + Sortino (18%) + Alpha Stability (15%)
    
    Alpha Stability: LOWER stddev is better (use higher_is_better=False)
    All others: higher is better.
    """
    def vals(key):
        return [f.get(key) for f in all_funds]
    
    ir_score   = _quartile_score(fund.get("info_ratio"),       vals("info_ratio"))
    rc_score   = _quartile_score(fund.get("rolling_consistency"), vals("rolling_consistency"))
    cr_score   = _quartile_score(fund.get("capture_ratio"),    vals("capture_ratio"))
    so_score   = _quartile_score(fund.get("sortino"),          vals("sortino"))
    as_score   = _quartile_score(fund.get("alpha_stability"),  vals("alpha_stability"),
                                  higher_is_better=False)  # lower stddev = better
    
    return (
        SCORE_WEIGHTS["information_ratio"]   * ir_score +
        SCORE_WEIGHTS["rolling_consistency"] * rc_score +
        SCORE_WEIGHTS["capture_ratio"]       * cr_score +
        SCORE_WEIGHTS["sortino_ratio"]       * so_score +
        SCORE_WEIGHTS["alpha_stability"]     * as_score
    )


def _passive_score(fund: dict, all_funds: list) -> float:
    """
    Phase P scoring for index funds: TE (70%) + TER (30%).
    Both metrics are lower-is-better.
    """
    te_score  = _quartile_score(fund.get("tracking_error"), [f.get("tracking_error") for f in all_funds],
                                 higher_is_better=False)
    ter_score = _quartile_score(fund.get("ter"),            [f.get("ter") for f in all_funds],
                                 higher_is_better=False)
    
    # If TER is unavailable, use only TE (normalise weight to 1.0)
    if fund.get("ter") is None:
        return PASSIVE_SCORE_WEIGHTS["tracking_error"] * te_score
    
    return (
        PASSIVE_SCORE_WEIGHTS["tracking_error"] * te_score +
        PASSIVE_SCORE_WEIGHTS["ter"]             * ter_score
    )


# ─────────────────────────────────────────────────────────────────────────────
# Category statistics helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_category_stats(fund_list: list[dict]) -> dict:
    """
    Computes medians and means for key metrics — used in Phase 2 dynamic gates.
    """
    keys = ["rolling_consistency", "capture_ratio", "down_capture", "up_capture", "ter"]
    stats = {}
    for key in keys:
        vals = [f.get(key) for f in fund_list
                if f.get(key) is not None and not (isinstance(f.get(key), float) and np.isnan(f.get(key)))]
        if vals:
            stats[f"{key}_median"] = float(np.median(vals))
            stats[f"{key}_mean"]   = float(np.mean(vals))
            stats[f"{key}_std"]    = float(np.std(vals))
        else:
            stats[f"{key}_median"] = None
            stats[f"{key}_mean"]   = None
            stats[f"{key}_std"]    = None
    return stats


def _compute_category_avg(fund_list: list[dict]) -> dict:
    """
    Category-wide averages for UI display.
    """
    keys = [
        "cagr_5y", "rolling_consistency", "sortino", "down_capture",
        "up_capture", "capture_ratio", "max_drawdown", "info_ratio",
        "alpha_stability", "ter"
    ]
    avg = {}
    for key in keys:
        vals = [f.get(key) for f in fund_list
                if f.get(key) is not None and not (isinstance(f.get(key), float) and np.isnan(f.get(key)))]
        avg[key] = float(np.mean(vals)) if vals else None
    return avg


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Qualitative Flags
# ─────────────────────────────────────────────────────────────────────────────

def _apply_phase4_flags(funds: list[dict], nav_map: dict, bench_df, category_stats: dict) -> list[dict]:
    """
    Applies all Phase 4 qualitative flags to the top funds.
    Flags do not eliminate — they surface issues for manual human review.
    
    Flag 1: Manager Change (2-signal: volatility signature + alpha sign flip)
    Flag 2: High Beta (Beta > 1.3)
    Flag 3: Portfolio Concentration (top-10 holdings > category avg + threshold)
    Flag 4: Portfolio Turnover (PTR > 1.5 SD above category median)
    """
    for fund in funds:
        code    = fund["code"]
        nav_df_ = nav_map.get(code)
        
        # ── Flag 1: Manager Change ─────────────────────────────────────────
        mc = compute_manager_change_signals(
            nav_df=nav_df_,
            bench_df=bench_df,
            vol_threshold=MANAGER_CHANGE_VOL_THRESHOLD,
        ) if nav_df_ is not None else {"manager_flag": False, "manager_flag_reason": None}
        fund.update(mc)
        
        # ── Flag 2: High Beta ──────────────────────────────────────────────
        beta = fund.get("beta")
        if beta is not None and not (isinstance(beta, float) and np.isnan(beta)) and beta > HIGH_BETA_THRESHOLD:
            fund["beta_flag"] = True
            fund["beta_flag_reason"] = (
                f"Beta {beta:.2f} — this fund amplifies market moves by {beta:.1%}. "
                f"It will fall ~{beta:.1f}x harder than the market in a crash. "
                f"Only appropriate for investors with high risk tolerance and 10+ year horizon."
            )
        else:
            fund["beta_flag"] = False
            fund["beta_flag_reason"] = None
        
        # ── Flag 3: Portfolio Concentration ───────────────────────────────
        # Note: We don't currently have top-10 holdings data from the API.
        # This flag is a placeholder — manually check AMFI factsheets.
        # If you add a factsheet parser, store top10_pct in fund dict.
        top10 = fund.get("top10_pct")
        # We'd need factsheet data here. For now, skip silently.
        fund["concentration_flag"] = False
        fund["concentration_flag_reason"] = None
        
        # ── Flag 4: Portfolio Turnover ─────────────────────────────────────
        # Note: PTR data is from AMFI monthly factsheets (not via mfapi.in).
        # This flag is a placeholder — manually check factsheets.
        ptr = fund.get("portfolio_turnover_ratio")
        ptr_median = category_stats.get("ptr_median")
        ptr_std    = category_stats.get("ptr_std")
        if ptr is not None and ptr_median is not None and ptr_std is not None and ptr_std > 0:
            z = (ptr - ptr_median) / ptr_std
            if z > PTR_FLAG_SD_MULTIPLIER:
                fund["ptr_flag"] = True
                fund["ptr_flag_reason"] = (
                    f"PTR {ptr:.0f}% is {z:.1f} standard deviations above category median "
                    f"({ptr_median:.0f}%) — high churn may erode alpha via impact costs."
                )
            else:
                fund["ptr_flag"] = False
                fund["ptr_flag_reason"] = None
        else:
            fund["ptr_flag"] = False
            fund["ptr_flag_reason"] = None
    
    return funds


# ─────────────────────────────────────────────────────────────────────────────
# Continuity Check
# ─────────────────────────────────────────────────────────────────────────────

def _apply_continuity(top_n_funds: list[dict], category: str, previous_results: dict) -> list[dict]:
    """
    Holdover 🛡️ : Fund was in Top 3 last quarter — hold to avoid taxes/exit loads.
    New Entrant 🌟: First appearance — manual deep-dive before allocating capital.
    
    The 2-quarter rule for exiting is enforced at the portfolio level (main.py),
    not here. This function only tags status; the caller decides action.
    """
    if not previous_results or category not in previous_results:
        for f in top_n_funds:
            f["continuity_status"] = "🌟 New Entrant"
            f["continuity_desc"]   = "First run — verify before allocating."
        return top_n_funds
    
    prev_top_codes = {f["code"] for f in previous_results[category].get("top_funds", [])}
    
    for f in top_n_funds:
        if f["code"] in prev_top_codes:
            f["continuity_status"] = "🛡️ Holdover"
            f["continuity_desc"]   = (
                "In Top 3 last quarter. Continue holding — switching incurs "
                "STCG/LTCG tax and exit loads. Only exit if a gate was failed, not just rank drop."
            )
        else:
            f["continuity_status"] = "🌟 New Entrant"
            f["continuity_desc"]   = (
                "Newly entered Top 3. Manual deep-dive required: "
                "verify manager tenure, sector concentration, and factsheet commentary "
                "before moving capital from any existing position."
            )
    
    return top_n_funds


# ─────────────────────────────────────────────────────────────────────────────
# Main Screener
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 Helper Logic
# ─────────────────────────────────────────────────────────────────────────────

def _apply_phase2_gates(
    funds: list[dict],
    is_passive: bool,
    cat_stats: dict,
    consistency_floor: float,
    capture_ratio_min: float,
    rolling_window_years: int,
    verbose: bool = True
) -> tuple[list[dict], list[dict]]:
    passed = []
    failed = []
    
    for m in funds:
        name = m["name"]
        code = m["code"]
        px   = "  [GATE]"
        
        # ── Gate 3: Sharpe Ratio ───────────────────────────────────────
        sharpe = m.get("sharpe")
        if sharpe is not None and not np.isnan(sharpe) and sharpe < SHARPE_GATE_MIN:
            reason = f"Negative Sharpe: {sharpe:.2f} (not compensating for equity risk)"
            if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
            failed.append({**m, "reason": reason})
            continue
            
        if is_passive:
            if verbose: print(f"{px} PASS   {name[:50]} [PASSIVE]")
            passed.append(m)
            continue
            
        # ── Gate 4: TER Gate ───────────────────────────────────────────
        ter = m.get("ter")
        ter_median = cat_stats.get("ter_median")
        if ter is not None and ter_median is not None:
            if ter > ter_median + (TER_GATE_SPREAD * 100):
                reason = f"TER {ter:.2f}% is {ter - ter_median:.2f}% above category median {ter_median:.2f}%"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
                
        # ── Gate 5: Rolling Consistency ───────────────────────────────
        rc = m.get("rolling_consistency")
        rc_med = cat_stats.get("rolling_consistency_median")
        if rc is not None and not np.isnan(rc):
            if rc < consistency_floor:
                reason = f"Rolling consistency {rc:.0%} < floor {consistency_floor:.0%} ({rolling_window_years}yr windows)"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
            if rc_med is not None and rc < rc_med:
                reason = f"Rolling consistency {rc:.0%} < category median {rc_med:.0%}"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
                
        # ── Gate 6: Capital Protection ────────────────────────────────
        cp = m.get("capital_protection")
        if cp is not None and not np.isnan(cp):
            if cp > CAPITAL_PROTECTION_FLOOR:
                reason = f"Negative windows {cp:.0%} > {CAPITAL_PROTECTION_FLOOR:.0%} max ({rolling_window_years}yr)"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
                
        # ── Gate 7: Capture Ratio ─────────────────────────────────────
        cr = m.get("capture_ratio")
        cr_med = cat_stats.get("capture_ratio_median")
        if cr is not None and not np.isnan(cr):
            if cr < capture_ratio_min:
                reason = f"Capture ratio {cr:.3f} < {capture_ratio_min:.3f} (negative asymmetry)"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
            if cr_med is not None and cr < cr_med:
                reason = f"Capture ratio {cr:.3f} < category median {cr_med:.3f}"
                if verbose: print(f"{px} CUT    {name[:50]} — {reason}")
                failed.append({**m, "reason": reason})
                continue
                
        if verbose: print(f"{px} PASS   {name[:50]}")
        passed.append(m)
        
    return passed, failed

def run_screening(previous_results: dict = None) -> dict[str, dict]:
    """
    Runs the full v4 pipeline for every configured category.
    
    Returns:
    {
      "Mid Cap": {
        "top_funds":            [ {...fund metrics + flags...}, ... ],
        "eliminated":           [ {..., "reason": "..."}, ... ],
        "total_found":          25,
        "total_passed_phase2":  8,
        "is_passive":           False,
        "category_avg":         { "rolling_consistency": 0.62, ... },
        "category_stats":       { "rolling_consistency_median": 0.60, ... },
        "rolling_window_years": 5,
      },
      ...
    }
    """
    aum_map = get_amfi_aum_map()
    ter_map = get_ter_map()
    results = {}

    for category, cfg in CATEGORIES.items():
        print(f"\n{'='*65}")
        print(f"  CATEGORY: {category}  [{cfg['strategy'].upper()}]")
        print(f"{'='*65}")

        is_passive          = cfg["strategy"] == "passive"
        bench_code          = cfg.get("benchmark_code")
        aum_min             = cfg.get("aum_min", 0)
        aum_max             = cfg.get("aum_max", None)
        min_years           = cfg.get("min_history_years", 5)
        rolling_window_years = cfg.get("rolling_window_years", 3)
        consistency_floor_key = cfg.get("consistency_floor_key")
        consistency_floor   = ROLLING_CONSISTENCY_FLOORS.get(consistency_floor_key, 0.55) if consistency_floor_key else 0.55

        # ── Step 1: Get all funds in AMFI category ─────────────────────────
        all_funds = get_all_direct_growth_funds_by_category(
            amfi_category_keywords = cfg["amfi_category_keywords"],
            name_must_contain      = cfg.get("name_must_contain", []),
        )
        total_found = len(all_funds)
        print(f"  Found {total_found} Direct Growth funds in AMFI category")

        if total_found == 0:
            print(f"  [WARN] No funds found — check amfi_category_keywords in config.py")
            results[category] = _empty_result(is_passive, rolling_window_years)
            continue

        # ── Step 2: Fetch benchmark ────────────────────────────────────────
        bench_df = None
        if bench_code:
            try:
                bench_df = get_nav_history(bench_code)
                bench_years = (bench_df["date"].iloc[-1] - bench_df["date"].iloc[0]).days / 365.25
                print(f"  Benchmark: code={bench_code}  ({len(bench_df)} NAV days, {bench_years:.1f}y)")
            except Exception as e:
                print(f"  [WARN] Benchmark unavailable: {e}")

        # ── Step 3: Phase 1 — History & AUM gates ─────────────────────────
        print(f"\n  Phase 1: History (≥{min_years}y) & AUM [₹{aum_min}–{aum_max or '∞'}Cr]")
        
        phase1_passed: list[dict] = []
        eliminated:    list[dict] = []
        nav_map:       dict       = {}   # code → nav_df (for Phase 4 flags)

        for i, fund in enumerate(all_funds):
            code   = fund["code"]
            name   = fund["name"]
            prefix = f"  [{i+1:>3}/{total_found}]"

            # Gate: History
            try:
                nav_df = get_nav_history(code)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:50]} — NAV fetch error")
                eliminated.append({**fund, "reason": f"NAV fetch failed: {e}"})
                continue

            years_of_data = (nav_df["date"].iloc[-1] - nav_df["date"].iloc[0]).days / 365.25
            if years_of_data < min_years:
                print(f"{prefix} CUT    {name[:50]} — {years_of_data:.1f}y history (need {min_years}y)")
                eliminated.append({**fund, "reason": f"Insufficient history: {years_of_data:.1f}y"})
                continue

            # Gate: AUM
            aum = aum_map.get(code)
            if aum is not None:
                if aum_min and aum < aum_min:
                    print(f"{prefix} CUT    {name[:50]} — AUM ₹{aum:.0f}Cr < ₹{aum_min}Cr min")
                    eliminated.append({**fund, "reason": f"AUM too small: ₹{aum:.0f}Cr"})
                    continue
                if aum_max and aum > aum_max:
                    print(f"{prefix} CUT    {name[:50]} — AUM ₹{aum:.0f}Cr > ₹{aum_max}Cr max")
                    eliminated.append({**fund, "reason": f"AUM too large: ₹{aum:.0f}Cr (mandate drift risk)"})
                    continue

            # Phase 1 passed — compute metrics
            try:
                m = compute_all_metrics(nav_df, bench_df, rolling_window_years=rolling_window_years)
                m.update({"name": name, "code": code, "aum": aum})
                m["ter"] = ter_map.get(code)
                nav_map[code] = nav_df
                phase1_passed.append(m)
            except Exception as e:
                print(f"{prefix} SKIP   {name[:50]} — metric error: {e}")
                eliminated.append({**fund, "reason": f"Metric computation failed: {e}"})
                continue

        print(f"\n  Phase 1 result: {len(phase1_passed)} funds passed (out of {total_found})")

        if not phase1_passed:
            print(f"  [WARN] No funds passed Phase 1")
            results[category] = _empty_result(is_passive, rolling_window_years)
            continue

        # ── Compute category stats across ALL Phase 1 passers (for dynamic gates) ──
        cat_stats = _compute_category_stats(phase1_passed)
        print(f"\n  Category Dynamic Stats ({rolling_window_years}yr rolling windows):")
        for k in ["rolling_consistency_median", "capture_ratio_median", "ter_median"]:
            v = cat_stats.get(k)
            if v is not None:
                print(f"    {k:<40}: {v:.3f}")

        # ── Step 4: Phase 2 — Hybrid Dynamic Gates ─────────────────────────
        print(f"\n  Phase 2: Dynamic Gates...")
        
        # Pass 1: Strict Absolute Gates (per config floors)
        phase2_passed, p2_failed = _apply_phase2_gates(
            funds                = phase1_passed,
            is_passive           = is_passive,
            cat_stats            = cat_stats,
            consistency_floor    = consistency_floor,
            capture_ratio_min    = CAPTURE_RATIO_MIN,
            rolling_window_years = rolling_window_years
        )
        
        # Fallback Logic: If no funds passed strict gates, try relative median gates
        if not phase2_passed and not is_passive:
            print(f"  [WARN] Zero funds passed strict absolute gates. Falling back to relative median gates...")
            fallback_consistency = cat_stats.get("rolling_consistency_median", 0.50) or 0.50
            fallback_capture     = cat_stats.get("capture_ratio_median", 1.0) or 1.0
            
            phase2_passed, p2_failed = _apply_phase2_gates(
                funds                = phase1_passed,
                is_passive           = is_passive,
                cat_stats            = cat_stats,
                consistency_floor    = min(consistency_floor, fallback_consistency),
                capture_ratio_min    = min(CAPTURE_RATIO_MIN, fallback_capture),
                rolling_window_years = rolling_window_years
            )
        
        eliminated.extend(p2_failed)
        total_passed = len(phase2_passed)
        print(f"\n  Phase 2 result: {total_passed} funds passed gates")

        # Compute category percentiles across all Phase 1 passers (not just Phase 2)
        # This gives proper peer-relative context even for eliminated funds
        all_computed_with_pct = compute_category_percentiles(phase1_passed)
        pct_map = {f["code"]: f.get("rolling_category_percentile") for f in all_computed_with_pct}
        for f in phase2_passed:
            f["rolling_category_percentile"] = pct_map.get(f["code"])

        # Fallback: if everything was eliminated, use Phase 1 passers sorted by 5Y CAGR
        # Fallback: if STILL nothing passed (extremely rare), use Phase 1 CAGR fallback as last resort
        if not phase2_passed:
            print(f"  [WARN] Zero funds passed even relative gates — using Phase 1 fallback (sorted by 5Y CAGR)")
            phase2_passed = sorted(
                [f for f in phase1_passed if f.get("cagr_5y") is not None],
                key=lambda x: x.get("cagr_5y", 0),
                reverse=True,
            )[:max(TOP_N, 5)]
        # Category averages for UI display
        category_avg = _compute_category_avg(phase1_passed)

        # ── Step 5: Phase 3 — Weighted Scoring ────────────────────────────
        print(f"\n  Phase 3: Scoring ({len(phase2_passed)} funds)...")
        
        if is_passive:
            for f in phase2_passed:
                f["total_score"] = _passive_score(f, phase2_passed)
            ranked = sorted(phase2_passed, key=lambda x: x.get("total_score", 0), reverse=True)
            score_desc = "Passive score: TE×70% + TER×30%"
        else:
            for f in phase2_passed:
                f["total_score"] = _active_score(f, phase2_passed)
            ranked = sorted(phase2_passed, key=lambda x: x.get("total_score", 0), reverse=True)
            score_desc = "Active score: IR×25% + RC×22% + CaptureRatio×20% + Sortino×18% + AlphaStability×15%"
        
        print(f"  Scoring method: {score_desc}")

        top_n_funds = ranked[:TOP_N]

        # ── Step 6: Phase 4 — Qualitative Flags ───────────────────────────
        print(f"\n  Phase 4: Qualitative flags on top {TOP_N} funds...")
        if not is_passive:
            top_n_funds = _apply_phase4_flags(top_n_funds, nav_map, bench_df, cat_stats)
        else:
            for f in top_n_funds:
                f["manager_flag"]        = False
                f["manager_flag_reason"] = None
                f["beta_flag"]           = False
                f["beta_flag_reason"]    = None
                f["concentration_flag"]  = False
                f["ptr_flag"]            = False

        # ── Step 7: Continuity Rule ────────────────────────────────────────
        top_n_funds = _apply_continuity(top_n_funds, category, previous_results)

        # ── Console summary ────────────────────────────────────────────────
        print(f"\n  TOP {TOP_N} [{category}]:")
        for rank, f in enumerate(top_n_funds, 1):
            score = f.get("total_score", 0)
            cont  = f.get("continuity_status", "")
            flags = []
            if f.get("manager_flag"):   flags.append("[!MANAGER]")
            if f.get("beta_flag"):      flags.append("[!HIGH BETA]")
            if f.get("ptr_flag"):       flags.append("[!HIGH PTR]")
            flag_str = "  " + " ".join(flags) if flags else ""
            
            if is_passive:
                te = f.get("tracking_error")
                print(f"  #{rank}: {f['name'][:55]} {cont}")
                print(f"       Score: {score:.2f} | TE: {te:.4f}%" if te else f"       Score: {score:.2f}")
            else:
                rc  = f.get("rolling_consistency")
                cr  = f.get("capture_ratio")
                ir  = f.get("info_ratio")
                pct = f.get("rolling_category_percentile")
                print(f"  #{rank}: {f['name'][:55]} {cont}{flag_str}")
                print(f"       Score: {score:.2f}/4.00 | RC: {rc:.0%} ({pct:.0f}th pct) | "
                      f"CaptureRatio: {cr:.3f} | IR: {ir:.2f}" 
                      if rc is not None and pct is not None and cr is not None and ir is not None
                      else f"       Score: {score:.2f}/4.00")

        results[category] = {
            "top_funds":            top_n_funds,
            "eliminated":           eliminated,
            "total_found":          total_found,
            "total_passed_phase2":  total_passed,
            "is_passive":           is_passive,
            "category_avg":         category_avg,
            "category_stats":       cat_stats,
            "rolling_window_years": rolling_window_years,
            "consistency_floor":    consistency_floor,
        }

    # ── Save JSON ──────────────────────────────────────────────────────────
    out_dir   = Path("./output")
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
    print(f"\n{'='*65}")
    print(f"  Results saved → {json_path}")
    print(f"{'='*65}")

    return results


def _empty_result(is_passive: bool, rolling_window_years: int) -> dict:
    return {
        "top_funds": [], "eliminated": [],
        "total_found": 0, "total_passed_phase2": 0,
        "is_passive": is_passive, "category_avg": {},
        "category_stats": {}, "rolling_window_years": rolling_window_years,
    }
