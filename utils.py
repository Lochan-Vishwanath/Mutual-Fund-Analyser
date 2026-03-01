# ─────────────────────────────────────────────────────────────────────────────
# utils.py  —  CLI helper tools for MF Master Plan v4.0
#
#   python utils.py search "Parag Parikh Flexi"   → find scheme codes by name
#   python utils.py verify 122639                  → inspect a scheme code
#   python utils.py categories                     → list all AMFI category headers
#   python utils.py pe                             → current Nifty P/E + signal
#   python utils.py preview                        → full run, save HTML, no email
#   python utils.py count                          → how many funds per category
#   python utils.py ter 122639                     → show TER for a scheme
#   python utils.py benchmark                      → show configured benchmarks
#   python utils.py config                         → print key config thresholds
# ─────────────────────────────────────────────────────────────────────────────

import sys
import numpy as np
from fetcher import (
    search_scheme, get_nav_history, get_nifty_pe, get_scheme_name,
    _fetch_amfi_raw, _build_category_map, get_all_direct_growth_funds_by_category,
    get_ter_map,
)
from metrics import (
    cagr, std_dev_annual, sharpe_ratio, sortino_ratio, max_drawdown,
    compute_info_ratio, compute_up_capture, compute_down_capture,
    compute_capture_ratio, compute_alpha_stability,
)
from config import PE_THRESHOLDS, CATEGORIES, SCORE_WEIGHTS, ROLLING_CONSISTENCY_FLOORS


def _fmt(val, pct=False, decimals=2, na="—"):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return na
    if pct:
        return f"{val:.1%}"
    return f"{val:.{decimals}f}"


def cmd_search(query: str):
    """Find scheme codes by fund name."""
    print(f"\nSearching: '{query}'\n")
    results = search_scheme(query, top_n=20)
    if not results:
        print("No results.")
        return
    print(f"{'Code':<10} Scheme Name")
    print("-" * 80)
    for r in results:
        print(f"{r.get('schemeCode', ''):<10} {r.get('schemeName', '')}")
    print(f"\n{len(results)} result(s) — copy the code to config.py benchmark_code")


def cmd_verify(code: str):
    """Full health check on a scheme code, including v4 metrics."""
    print(f"\nVerifying: {code}")
    try:
        df   = get_nav_history(code)
        name = get_scheme_name(code)
        years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.25

        c3  = cagr(df["nav"], 3)
        c5  = cagr(df["nav"], 5)
        c10 = cagr(df["nav"], 10)
        sh  = sharpe_ratio(df["nav"])
        so  = sortino_ratio(df["nav"])
        mdd = max_drawdown(df["nav"])

        print(f"  Name        : {name}")
        print(f"  Range       : {df['date'].min().date()} → {df['date'].max().date()}")
        print(f"  History     : {years:.1f} years  ({len(df)} NAV points)")
        print(f"  Latest NAV  : ₹{df['nav'].iloc[-1]:.4f}")
        print(f"  3Y CAGR     : {_fmt(c3, pct=True)}")
        print(f"  5Y CAGR     : {_fmt(c5, pct=True)}")
        print(f"  10Y CAGR    : {_fmt(c10, pct=True)}")
        print(f"  Sharpe      : {_fmt(sh)}")
        print(f"  Sortino     : {_fmt(so)}")
        print(f"  Max DD      : {_fmt(mdd, pct=True)}")
        print(f"\n  ✅ Code {code} is valid.")
        print(f"  Use as benchmark_code in config.py CATEGORIES dict.")
    except Exception as e:
        print(f"  ❌ Error: {e}")


def cmd_categories():
    """Show all AMFI category headers with fund counts."""
    print("\nFetching AMFI categories...")
    try:
        text    = _fetch_amfi_raw()
        cat_map = _build_category_map(text)
        print(f"\n{'Category':<60} {'DG Funds':>8}")
        print("-" * 70)
        for cat, funds in sorted(cat_map.items(), key=lambda x: -len(x[1])):
            print(f"  {cat:<58} {len(funds):>8}")
        print(f"\nTotal AMFI categories: {len(cat_map)}")
        print("\nUse the category name (or substring) as amfi_category_keywords in config.py")
    except Exception as e:
        print(f"Error: {e}")


def cmd_pe():
    """Show current Nifty 50 P/E and deployment signal."""
    pe = get_nifty_pe()
    if not pe:
        print("Could not fetch Nifty P/E. Check niftyindices.com manually.")
        return
    print(f"\nNifty 50 P/E: {pe:.2f}x")
    if   pe >= PE_THRESHOLDS["overvalued"]:  print("Signal: 🔴 OVERVALUED — SIPs only, no lump sum")
    elif pe >= PE_THRESHOLDS["fair_high"]:   print("Signal: 🟡 FAIR TO HIGH — hold arbitrage buffer")
    elif pe >= PE_THRESHOLDS["fair_value"]:  print("Signal: 🟢 FAIR VALUE — deploy 25% of buffer")
    elif pe >= PE_THRESHOLDS["attractive"]:  print("Signal: 🟢 ATTRACTIVE — deploy 75% of buffer")
    else:                                    print("Signal: 🟢 DEEP VALUE — deploy everything")


def cmd_count():
    """Show how many funds will be screened per configured category."""
    print("\nFund count per category (Direct Growth only):\n")
    total = 0
    for cat_name, cfg in CATEGORIES.items():
        funds = get_all_direct_growth_funds_by_category(
            cfg["amfi_category_keywords"],
            cfg.get("name_must_contain", []),
        )
        strategy  = cfg.get("strategy", "active").upper()
        rw        = cfg.get("rolling_window_years", 3)
        min_hist  = cfg.get("min_history_years", 5)
        floor_key = cfg.get("consistency_floor_key", "")
        floor     = ROLLING_CONSISTENCY_FLOORS.get(floor_key, "—")
        floor_str = f"{floor:.0%}" if isinstance(floor, (int, float)) else str(floor)
        print(f"  {cat_name:<40} [{strategy}]  {len(funds):>4} funds  "
              f"({min_hist}yr hist, {rw}yr rolling, {floor_str} floor)")
        total += len(funds)
    print(f"\n  Total across all categories: {total}")


def cmd_ter(code: str):
    """Show TER for a specific scheme code."""
    print(f"\nFetching TER for scheme: {code}")
    ter_map = get_ter_map()
    ter = ter_map.get(str(code))
    if ter is not None:
        print(f"  TER: {ter:.2f}%")
    else:
        name = get_scheme_name(code)
        print(f"  TER for '{name}' not found in AMFI data.")
        print(f"  Total TER entries in AMFI dataset: {len(ter_map)}")
        print(f"  Check: https://www.amfiindia.com/research-information/other-data/scheme-terpension")


def cmd_preview():
    """Run full screening, save HTML report, no email."""
    from main import run
    run("dry")


def cmd_benchmark():
    """Show all configured benchmarks and suggest searches for missing ones."""
    print("\nConfigured benchmarks per category:\n")
    for cat_name, cfg in CATEGORIES.items():
        code     = cfg.get("benchmark_code")
        strategy = cfg.get("strategy", "active")
        if strategy == "passive":
            print(f"  {cat_name:<40} [PASSIVE — no benchmark needed]")
        elif code:
            try:
                name = get_scheme_name(code)
                print(f"  {cat_name:<40} Code: {code}  ({name[:50]})")
            except Exception:
                print(f"  {cat_name:<40} Code: {code}  (name fetch failed)")
        else:
            print(f"  {cat_name:<40} ⚠️  No benchmark set!")

    print("\nSuggested searches for benchmark codes:")
    suggestions = {
        "Large Cap":      "Nifty 100 Index Fund Direct Growth",
        "Large & MidCap": "Nifty LargeMidcap 250 Index Fund Direct Growth",
        "Mid Cap":        "Nifty Midcap 150 Index Fund Direct Growth",
        "Small Cap":      "Nifty Smallcap 250 Index Fund Direct Growth",
        "Flexi Cap":      "Nifty 500 Index Fund Direct Growth",
    }
    for cat, q in suggestions.items():
        print(f"  python utils.py search \"{q}\"")


def cmd_config():
    """Print key v4 config thresholds for quick review."""
    from config import (
        SHARPE_GATE_MIN, TER_GATE_SPREAD, CAPITAL_PROTECTION_FLOOR,
        CAPTURE_RATIO_MIN, HIGH_BETA_THRESHOLD,
        MANAGER_CHANGE_VOL_THRESHOLD, PTR_FLAG_SD_MULTIPLIER,
    )
    print("\n  MF Master Plan v4.0 — Key Config Thresholds")
    print("  " + "─"*50)
    print(f"  Sharpe gate min           : {SHARPE_GATE_MIN}")
    print(f"  TER gate spread           : {TER_GATE_SPREAD*100:.1f}% above category median")
    print(f"  Capital protection max    : {CAPITAL_PROTECTION_FLOOR:.0%} negative windows")
    print(f"  Capture ratio min         : {CAPTURE_RATIO_MIN} (upside÷downside)")
    print(f"  High Beta threshold       : {HIGH_BETA_THRESHOLD}")
    print(f"  Manager change vol zscore : {MANAGER_CHANGE_VOL_THRESHOLD}")
    print(f"  PTR flag SD multiplier    : {PTR_FLAG_SD_MULTIPLIER}")
    print(f"\n  Rolling Consistency Floors:")
    for k, v in ROLLING_CONSISTENCY_FLOORS.items():
        print(f"    {k:<28} : {v:.0%}")
    print(f"\n  Phase 3 Score Weights:")
    for k, v in SCORE_WEIGHTS.items():
        print(f"    {k:<28} : {v:.0%}")
    print(f"\n  AUM Bounds per Category:")
    for cat, cfg in CATEGORIES.items():
        mn = cfg.get("aum_min", 0)
        mx = cfg.get("aum_max", "No cap")
        rw = cfg.get("rolling_window_years", 3)
        print(f"    {cat:<35} : ₹{mn:,}Cr – {('₹'+str(mx//1000)+'kCr') if isinstance(mx,int) else mx}  ({rw}yr rolling)")


COMMANDS = {
    "search":    (cmd_search,    "search <query>     — find scheme codes by name"),
    "verify":    (cmd_verify,    "verify <code>      — full health check on a scheme code"),
    "categories":(cmd_categories,"categories         — list all AMFI category headers"),
    "count":     (cmd_count,     "count              — fund count per configured category"),
    "pe":        (cmd_pe,        "pe                 — Nifty P/E + deployment signal"),
    "preview":   (cmd_preview,   "preview            — full run, save HTML, no email"),
    "ter":       (cmd_ter,       "ter <code>         — show TER for a scheme code"),
    "benchmark": (cmd_benchmark, "benchmark          — show all configured benchmarks"),
    "config":    (cmd_config,    "config             — show key v4 config thresholds"),
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print("\nUsage:")
        for _, (_, desc) in COMMANDS.items():
            print(f"  python utils.py {desc}")
        sys.exit(0)

    fn = COMMANDS[args[0]][0]
    fn(*args[1:]) if args[1:] else fn()
