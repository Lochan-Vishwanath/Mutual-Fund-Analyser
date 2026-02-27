# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  All configurable parameters.
#
# You no longer need to list individual fund candidates.
# The screener fetches ALL Direct Growth funds in each AMFI category,
# runs the full strategy on every one, and surfaces the top N.
#
# What you actually need to update:
#   1. EMAIL_SENDER, EMAIL_PASSWORD, SUBSCRIBERS
#   2. benchmark_code for each active category
#      (find codes with: python utils.py search "Nifty Midcap 150 Index")
#   3. RISK_FREE_RATE_ANNUAL — update quarterly from rbi.org.in
# ─────────────────────────────────────────────────────────────────────────────

# ── EMAIL ──────────────────────────────────────────────────────────────────
EMAIL_SENDER    = "yourname@gmail.com"     # Gmail address
EMAIL_PASSWORD  = ""                       # Or env var: MF_EMAIL_PASSWORD
EMAIL_SUBJECT   = "Quarterly MF Review — Top 3 Funds Per Category"
SUBSCRIBERS     = [
    "you@gmail.com",
    "family@gmail.com",
]

# ── TOP N FUNDS TO SHOW PER CATEGORY ─────────────────────────────────────
TOP_N = 3

# ── RISK-FREE RATE ────────────────────────────────────────────────────────
# 91-day T-bill yield. Update quarterly from rbi.org.in
RISK_FREE_RATE_ANNUAL = 0.065   # 6.5% as of Q1 2026

# ── NIFTY P/E DEPLOYMENT SIGNAL ──────────────────────────────────────────
PE_THRESHOLDS = {
    "overvalued":  24,
    "fair_high":   22,
    "fair_value":  18,
    "attractive":  15,
}

# ── SCREENING PARAMETERS ─────────────────────────────────────────────────
# ── SCREENING PARAMETERS ─────────────────────────────────────────────────
ROLLING_WINDOW_YEARS    = 3     # 3-year rolling return windows
ROLLING_CONSISTENCY_MIN = 0.65  # must beat benchmark > 65% of windows
MIN_HISTORY_YEARS       = 5     # discard funds with < 5 years of NAV data

# Absolute return targets (Advisorkhoj method)
ABSOLUTE_RETURN_TARGET  = 0.12  # 12% absolute return target
ABSOLUTE_RETURN_MIN_PCT = 0.70  # Must hit target > 70% of windows
CAPITAL_PROTECTION_MAX  = 0.05  # Max 5% of windows with negative returns

# ── WEIGHTED SCORECARD (must sum to 1.0) ─────────────────────────────────
SCORE_WEIGHTS = {
    "rolling_consistency": 0.20,
    "absolute_consistency":0.15,
    "sortino_ratio":       0.25,
    "information_ratio":   0.20,
    "down_capture":        0.10,
    "max_drawdown":        0.10,
}
# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
# amfi_category_keywords : substrings matched against AMFI section headers
#                          in NAVAll.txt (case-insensitive).
#                          Example AMFI headers:
#                            "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
#                            "Open Ended Schemes(Equity Scheme - Mid Cap Fund)"
#                            "Open Ended Schemes(Equity Scheme - Small Cap Fund)"
#                            "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)"
#                            "Open Ended Schemes(Other Scheme - Index Funds)"
#
# name_must_contain      : further filter within the AMFI category by name.
#                          Useful for index funds (want Nifty 50 only, not all index funds).
#                          Leave [] to accept all funds in the category.
#
# benchmark_code         : mfapi.in scheme code for benchmark index fund.
#                          Used for Alpha, Beta, Information Ratio, Rolling Consistency.
#                          Find with: python utils.py search "Nifty Midcap 150 Index Direct"
#
# aum_min / aum_max      : in Crores. Outside range = eliminated.
# down_capture_max       : category-adjusted per strategy doc.
# min_history_years      : override global value if needed.
# ─────────────────────────────────────────────────────────────────────────────
CATEGORIES = {

    "Large Cap / Index Fund": {
        "strategy":               "passive",
        "amfi_category_keywords": ["Index Funds", "Large Cap Fund"],
        # Extra name filter — within Index Funds, only want Nifty 50 / Sensex trackers
        "name_must_contain":      ["nifty 50", "sensex", "bse 100", "nifty 100"],
        "benchmark_code":         None,    # passive: ranked by tracking error only
        "aum_min":                1000,
        "aum_max":                None,
        "down_capture_max":       None,
        "min_history_years":      5,
    },

    "Mid Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Mid Cap Fund"],
        "name_must_contain":      [],
        # Benchmark: a Nifty Midcap 150 index fund direct growth
        # Run: python utils.py search "Nifty Midcap 150 Index Direct" to confirm code
        "benchmark_code":         "149892",
        "aum_min":                500,
        "aum_max":                20000,
        "down_capture_max":       100,
        "min_history_years":      5,
    },

    "Small Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Small Cap Fund"],
        "name_must_contain":      [],
        # Benchmark: a Nifty Smallcap 250 index fund direct growth
        # Run: python utils.py search "Nifty Smallcap 250 Index Direct" to confirm code
        "benchmark_code":         "148614",
        "aum_min":                500,
        "aum_max":                12000,
        "down_capture_max":       105,
        "min_history_years":      5,
    },

    "Flexi Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Flexi Cap Fund"],
        "name_must_contain":      [],
        # Benchmark: a Nifty 500 index fund direct growth
        # Run: python utils.py search "Nifty 500 Index Fund Direct" to confirm code
        "benchmark_code":         "147622",
        "aum_min":                500,
        "aum_max":                50000,
        "down_capture_max":       95,
        "min_history_years":      5,
    },

    # ── UNCOMMENT BELOW TO ADD MORE CATEGORIES ───────────────────────────
    # "Multi Cap": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["Multi Cap Fund"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "down_capture_max":       100,
    #     "min_history_years":      3,   # category only exists post-2020 SEBI mandate
    # },
    # "ELSS (Old Tax Regime)": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["ELSS"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "down_capture_max":       100,
    #     "min_history_years":      7,
    # },
}
