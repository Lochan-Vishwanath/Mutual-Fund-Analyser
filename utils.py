# ─────────────────────────────────────────────────────────────────────────────
# utils.py  —  CLI helper tools.
#
#   python utils.py search "Parag Parikh Flexi"   → find scheme codes by name
#   python utils.py verify 122639                  → inspect a scheme code
#   python utils.py categories                     → list all AMFI category headers
#   python utils.py pe                             → current Nifty P/E + signal
#   python utils.py preview                        → full run, save HTML, no email
#   python utils.py count                          → how many funds exist per category
# ─────────────────────────────────────────────────────────────────────────────

import sys
from fetcher import (
    search_scheme, get_nav_history, get_nifty_pe, get_scheme_name,
    _fetch_amfi_raw, _build_category_map, get_all_direct_growth_funds_by_category
)
from metrics import cagr, std_dev_annual, sharpe_ratio, sortino_ratio
from config  import PE_THRESHOLDS, CATEGORIES
import numpy as np


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
    """Quick health check on a scheme code."""
    print(f"\nVerifying: {code}")
    try:
        df   = get_nav_history(code)
        name = get_scheme_name(code)
        c3   = cagr(df["nav"], years=3)
        c5   = cagr(df["nav"], years=5)
        c10  = cagr(df["nav"], years=10)
        sh   = sharpe_ratio(df["nav"])
        so   = sortino_ratio(df["nav"])
        print(f"  Name       : {name}")
        print(f"  Range      : {df['date'].min().date()} -> {df['date'].max().date()}")
        print(f"  Days       : {len(df)}")
        print(f"  Latest NAV : Rs. {df['nav'].iloc[-1]:.4f}")
        print(f"  3Y CAGR    : {c3*100:.2f}%" if c3 and not np.isnan(c3) else "  3Y CAGR    : —")
        print(f"  5Y CAGR    : {c5*100:.2f}%" if c5 and not np.isnan(c5) else "  5Y CAGR    : —")
        print(f"  10Y CAGR   : {c10*100:.2f}%" if c10 and not np.isnan(c10) else "  10Y CAGR   : —")
        print(f"  Sharpe     : {sh:.2f}" if sh and not np.isnan(sh) else "  Sharpe     : —")
        print(f"  Sortino    : {so:.2f}" if so and not np.isnan(so) else "  Sortino    : —")
    except Exception as e:
        print(f"  Error: {e}")


def cmd_categories():
    """Show all AMFI category headers found in NAVAll.txt."""
    print("\nFetching AMFI categories...")
    try:
        text = _fetch_amfi_raw()
        cat_map = _build_category_map(text)
        print(f"\n{'Category':<55} {'Direct Growth Funds':>20}")
        print("-" * 78)
        for cat, funds in sorted(cat_map.items(), key=lambda x: -len(x[1])):
            print(f"  {cat:<53} {len(funds):>20}")
        print(f"\nTotal categories: {len(cat_map)}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_pe():
    """Show current Nifty 50 P/E and deployment signal."""
    pe = get_nifty_pe()
    if not pe:
        print("Could not fetch Nifty P/E. Check NSE website manually: niftyindices.com")
        return
    print(f"\nNifty 50 P/E: {pe:.2f}x")
    if   pe >= PE_THRESHOLDS["overvalued"]:  print("Signal: OVERVALUED — SIPs only, no lump sum")
    elif pe >= PE_THRESHOLDS["fair_high"]:   print("Signal: Fair to High — hold arbitrage buffer")
    elif pe >= PE_THRESHOLDS["fair_value"]:  print("Signal: FAIR VALUE — deploy 25% of buffer")
    elif pe >= PE_THRESHOLDS["attractive"]:  print("Signal: ATTRACTIVE — deploy 75% of buffer")
    else:                                    print("Signal: DEEP VALUE — deploy everything")


def cmd_count():
    """Show how many funds will be screened per configured category."""
    print("\nFund count per category (Direct Growth only):\n")
    for cat_name, cfg in CATEGORIES.items():
        funds = get_all_direct_growth_funds_by_category(
            cfg["amfi_category_keywords"],
            cfg.get("name_must_contain", []),
        )
        print(f"  {cat_name:<35} {len(funds):>4} funds to screen")
    print()


def cmd_preview():
    """Run full screening, save HTML report, no email."""
    from main import run
    run("dry")


COMMANDS = {
    "search":     (cmd_search,     "search <query>     — find scheme codes by name"),
    "verify":     (cmd_verify,     "verify <code>      — inspect a scheme code"),
    "categories": (cmd_categories, "categories         — list all AMFI category headers"),
    "count":      (cmd_count,      "count              — how many funds per category"),
    "pe":         (cmd_pe,         "pe                 — Nifty P/E + deployment signal"),
    "preview":    (cmd_preview,    "preview            — full run, save HTML, no email"),
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
