# ─────────────────────────────────────────────────────────────────────────────
# utils.py  —  CLI helper tools.
#
#   python utils.py search "Parag Parikh Flexi"   → find scheme codes by name
#   python utils.py verify 122639                  → inspect a scheme code
#   python utils.py categories                     → list all AMFI category headers
#   python utils.py pe                             → current Nifty P/E + signal
#   python utils.py preview                        → full run, save HTML, no email
#   python utils.py count                          → how many funds exist per category
#   python utils.py ter 122639                     → show TER for a scheme
#   python utils.py benchmark <cat_name>           → suggest benchmark for a category
# ─────────────────────────────────────────────────────────────────────────────

import sys
import numpy as np
from fetcher import (
    search_scheme, get_nav_history, get_nifty_pe, get_scheme_name,
    _fetch_amfi_raw, _build_category_map, get_all_direct_growth_funds_by_category,
    get_ter_map
)
from metrics import (
    cagr, std_dev_annual, sharpe_ratio, sortino_ratio,
    compute_up_capture, compute_down_capture, compute_all_metrics
)
from config import PE_THRESHOLDS, CATEGORIES


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
    print(f"\n{len(results)} result(s) — copy the code to config.py")


def cmd_verify(code: str):
    """Full health check on a scheme code including upside/downside capture."""
    print(f"\nVerifying: {code}")
    try:
        df   = get_nav_history(code)
        name = get_scheme_name(code)
        c3   = cagr(df["nav"], years=3)
        c5   = cagr(df["nav"], years=5)
        c10  = cagr(df["nav"], years=10)
        sh   = sharpe_ratio(df["nav"])
        so   = sortino_ratio(df["nav"])
        mdd_val = df["nav"].copy()

        from metrics import max_drawdown
        mdd = max_drawdown(df["nav"])

        print(f"  Name       : {name}")
        print(f"  Range      : {df['date'].min().date()} → {df['date'].max().date()}")
        print(f"  Days       : {len(df)}")
        print(f"  Latest NAV : ₹{df['nav'].iloc[-1]:.4f}")
        print(f"  3Y CAGR    : {_fmt(c3, pct=True)}")
        print(f"  5Y CAGR    : {_fmt(c5, pct=True)}")
        print(f"  10Y CAGR   : {_fmt(c10, pct=True)}")
        print(f"  Sharpe     : {_fmt(sh)}")
        print(f"  Sortino    : {_fmt(so)}")
        print(f"  Max DD     : {_fmt(mdd, pct=True)}")
        print(f"\n  ✅ This code is valid and has {len(df)} NAV points.")
        print(f"  Use as benchmark: add to config.py benchmark_code field.")

    except Exception as e:
        print(f"  ❌ Error: {e}")


def cmd_categories():
    """Show all AMFI category headers found in NAVAll.txt."""
    print("\nFetching AMFI categories...")
    try:
        text    = _fetch_amfi_raw()
        cat_map = _build_category_map(text)
        print(f"\n{'Category':<58} {'DG Funds':>10}")
        print("-" * 70)
        for cat, funds in sorted(cat_map.items(), key=lambda x: -len(x[1])):
            print(f"  {cat:<56} {len(funds):>10}")
        print(f"\nTotal AMFI categories: {len(cat_map)}")
        print("\nKeywords to use in config.py amfi_category_keywords:")
        print("  Exact substring match (case-insensitive) against column above.")
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
        strategy = cfg.get("strategy", "active").upper()
        print(f"  {cat_name:<40} [{strategy}]  {len(funds):>4} funds to screen")
        total += len(funds)
    print(f"\n  Total across all categories: {total}")


def cmd_ter(code: str):
    """Show TER (expense ratio) for a specific scheme code."""
    print(f"\nFetching TER for scheme: {code}")
    ter_map = get_ter_map()
    ter = ter_map.get(str(code))
    if ter is not None:
        print(f"  TER: {ter:.2f}%")
    else:
        name = get_scheme_name(code)
        print(f"  TER for '{name}' (code {code}) not found in AMFI data.")
        print(f"  Total TER entries in AMFI dataset: {len(ter_map)}")
        print(f"  Check manually: https://www.amfiindia.com/research-information/other-data/scheme-terpension")


def cmd_preview():
    """Run full screening, save HTML report, no email."""
    from main import run
    run("dry")


def cmd_benchmark(category_name: str = ""):
    """Suggest benchmark search terms for a category and show configured benchmarks."""
    print("\nConfigured benchmarks per category:\n")
    suggestions = {
        "large cap":           "Nifty 100 Index Fund Direct Growth",
        "large & midcap":      "Nifty LargeMidcap 250 Index Fund Direct Growth",
        "large and midcap":    "Nifty LargeMidcap 250 Index Fund Direct Growth",
        "mid cap":             "Nifty Midcap 150 Index Fund Direct Growth",
        "mid small":           "Nifty Midsmallcap 400 Index Fund Direct Growth",
        "small cap":           "Nifty Smallcap 250 Index Fund Direct Growth",
        "flexi cap":           "Nifty 500 Index Fund Direct Growth",
        "index":               "(No benchmark needed — passive strategy)",
    }

    for cat_name, cfg in CATEGORIES.items():
        code = cfg.get("benchmark_code")
        strategy = cfg.get("strategy", "active")
        if strategy == "passive":
            print(f"  {cat_name:<40} [PASSIVE — no benchmark needed]")
        elif code:
            name = get_scheme_name(code)
            print(f"  {cat_name:<40} Code: {code}  ({name[:45]})")
        else:
            print(f"  {cat_name:<40} No benchmark set!")

    print("\nSearch suggestions for missing benchmarks:")
    for cat, suggestion in suggestions.items():
        print(f"  python utils.py search \"{suggestion}\"")


COMMANDS = {
    "search":     (cmd_search,     "search <query>       — find scheme codes by name"),
    "verify":     (cmd_verify,     "verify <code>        — full health check on a scheme code"),
    "categories": (cmd_categories, "categories           — list all AMFI category headers"),
    "count":      (cmd_count,      "count                — how many funds per category"),
    "pe":         (cmd_pe,         "pe                   — Nifty P/E + deployment signal"),
    "preview":    (cmd_preview,    "preview              — full run, save HTML, no email"),
    "ter":        (cmd_ter,        "ter <code>           — show TER for a scheme code"),
    "benchmark":  (cmd_benchmark,  "benchmark            — show all configured benchmarks"),
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
