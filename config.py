# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  All configurable parameters.
#
# v3 Changes:
#   - Added Large Cap (Active), Large & MidCap, MidCap & SmallCap categories
#   - Updated SCORE_WEIGHTS: added up_capture (18%), TER (5%), rebalanced
#   - Added UP_CAPTURE_MIN gate (funds that can't participate in rallies = cut)
#   - Added TER_GATE_MAX_PERCENTILE: top 25% most expensive → penalised in score
#
# BENCHMARK CODES: Verify with: python utils.py search "<index name> Direct Growth"
# Then confirm with: python utils.py verify <code>
# ─────────────────────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# ── EMAIL ──────────────────────────────────────────────────────────────────
EMAIL_SENDER    = os.getenv("EMAIL_SENDER", "yourname@gmail.com")
EMAIL_PASSWORD  = os.getenv("MF_EMAIL_PASSWORD", "") # Gmail App Password
EMAIL_SUBJECT   = "Quarterly MF Review — Top 3 Funds Per Category"
SUBSCRIBERS     = os.getenv("SUBSCRIBERS", "you@gmail.com").split(",")

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
ROLLING_WINDOW_YEARS    = 3     # 3-year rolling return windows
ROLLING_CONSISTENCY_MIN = 0.65  # must beat benchmark > 65% of windows
ROLLING_CONSISTENCY_FLOOR = 0.50 # Hard floor: must beat benchmark at least 50%

ABSOLUTE_RETURN_TARGET  = 0.12  # 12% absolute return target
ABSOLUTE_RETURN_MIN_PCT = 0.70  # Must hit target > 70% of windows
ABSOLUTE_RETURN_FLOOR_PCT = 0.50 # Hard floor: must hit target > 50%

CAPITAL_PROTECTION_MAX  = 0.05  # Max 5% of windows with negative returns
CAPITAL_PROTECTION_FLOOR = 0.10 # Hard floor: max 10% negative windows

UP_CAPTURE_MIN          = 80    # Fund must participate >= 80% of benchmark rally
UP_CAPTURE_FLOOR        = 70    # Hard floor: must participate >= 70%

DOWN_CAPTURE_FLOOR      = 100   # Hard floor: must not be worse than index in down market (100)

ROLLING_CONSISTENCY_MIN = 0.65  # must beat benchmark > 65% of windows
MIN_HISTORY_YEARS       = 5     # discard funds with < 5 years of NAV data

# Absolute return targets (Advisorkhoj method)
ABSOLUTE_RETURN_TARGET  = 0.12  # 12% absolute return target
ABSOLUTE_RETURN_MIN_PCT = 0.70  # Must hit target > 70% of windows
CAPITAL_PROTECTION_MAX  = 0.05  # Max 5% of windows with negative returns

# Capture ratio gates (NEW in v3)
UP_CAPTURE_MIN          = 80    # Fund must participate >= 80% of benchmark rally
# (down_capture_max is set per category in CATEGORIES config below)

# TER percentile gate: funds in the top X% most expensive get a scoring penalty
# Set to None to disable. Does NOT eliminate — only penalises in scoring.
TER_TOP_PERCENTILE_PENALTY = 0.75   # above 75th percentile TER = scoring hit

# ── WEIGHTED SCORECARD (must sum to 1.0) ─────────────────────────────────
# v3 changes vs v2:
#   - Added up_capture (18%): can't score well if you can't participate in rallies
#   - Added ter_score (5%): lower cost funds win ties
#   - Reduced sortino from 25% to 20% (still dominant but balanced)
#   - Removed absolute_consistency from scoring (now a Phase 2 gate only)
#   - Rebalanced other weights
SCORE_WEIGHTS = {
    "rolling_consistency": 0.18,   # % of rolling windows beating benchmark
    "sortino_ratio":       0.20,   # risk-adjusted return (downside deviation)
    "information_ratio":   0.15,   # active return per unit of tracking error
    "up_capture":          0.18,   # NEW: participation in benchmark rallies
    "down_capture":        0.15,   # downside protection (lower = better)
    "max_drawdown":        0.09,   # worst peak-to-trough (less negative = better)
    "ter_score":           0.05,   # expense ratio (lower TER = better score)
}
# Sum = 0.18 + 0.20 + 0.15 + 0.18 + 0.15 + 0.09 + 0.05 = 1.00 ✓

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
#
# amfi_category_keywords : substrings matched against AMFI section headers
#                          in NAVAll.txt (case-insensitive).
#
# name_must_contain      : further filter within the AMFI category by name.
#
# benchmark_code         : mfapi.in scheme code for benchmark index fund.
#                          Find/verify: python utils.py search "<name> Direct Growth"
#                                       python utils.py verify <code>
#
# strategy               : "passive" (ranked by tracking error only)
#                          "active"  (full Phase 2 + Phase 3 pipeline)
#
# aum_min / aum_max      : in Crores. Outside range = eliminated.
# down_capture_max       : category-adjusted. Flexi tighter (95), Small Cap looser (105).
# min_history_years      : override global value if needed.
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = {

    # ── PASSIVE ─────────────────────────────────────────────────────────
    # ── LARGE CAP (HYBRID VIEW) ──────────────────────────────────────────
    # Note: app.py will merge the Passive and Active Large Cap results into one view.
    # We keep them separate here to apply different scoring logic (Tracking Error vs Alpha).

    "Large Cap (Passive)": {
        "strategy":               "passive",
        "amfi_category_keywords": ["Index Funds", "Large Cap Fund"],
        "name_must_contain":      ["nifty 50", "sensex", "bse 100", "nifty 100"],
        "benchmark_code":         None,
        "aum_min":                1000,
        "aum_max":                None,
        "down_capture_max":       None,
        "min_history_years":      5,
    },

    # ── LARGE CAP (ACTIVE) ───────────────────────────────────────────────
    # Benchmark: Nifty 100 TRI index fund (Direct Growth)
    # Verify: python utils.py search "Nifty 100 Index Fund Direct Growth"
    "Large Cap (Active)": {
        "strategy":               "active",
        "amfi_category_keywords": ["Large Cap Fund"],
        "name_must_contain":      [],
        # VERIFY THIS CODE: python utils.py search "Nifty 100 Index Fund Direct"
        # Common options: DSP Nifty 100 Index Fund, UTI Nifty 100 Index Fund
        "benchmark_code":         "120716",   # ← VERIFY: UTI Nifty Next 50 or similar
        "aum_min":                1000,
        "aum_max":                None,        # No upper limit for large cap
        "down_capture_max":       95,           # Large cap should protect better
        "min_history_years":      7,
    },

    # Benchmark: Nifty LargeMidcap 250 index fund (Direct Growth)
    # Verify: python utils.py search "Nifty LargeMidcap 250 Direct Growth"
    # ── LARGE & MIDCAP ──────────────────────────────────────────────────
    # Benchmark: Nifty LargeMidcap 250 index fund (Direct Growth)
    # Verify: python utils.py search "Nifty LargeMidcap 250 Direct Growth"
    "Large & MidCap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Large & Mid Cap Fund"],
        "name_must_contain":      [],
        # VERIFY THIS CODE: python utils.py search "LargeMidcap 250 Index Direct"
        "benchmark_code":         "149100",   # ← VERIFY before running
        "aum_min":                500,
        "aum_max":                30000,
        "down_capture_max":       100,
        "min_history_years":      5,
    },

    # ── MID CAP ─────────────────────────────────────────────────────────
    # Benchmark: Nifty Midcap 150 index fund (Direct Growth)
    "Mid Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Mid Cap Fund"],
        "name_must_contain":      [],
        # Run: python utils.py verify 149892 to confirm
        "benchmark_code":         "149892",
        "aum_min":                500,
        "aum_max":                20000,
        "down_capture_max":       100,
        "min_history_years":      5,
    },

    # ── SMALL CAP ───────────────────────────────────────────────────────
    # Benchmark: Nifty Smallcap 250 index fund (Direct Growth)
    "Small Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Small Cap Fund"],
        "name_must_contain":      [],
        # Run: python utils.py verify 148614 to confirm
        "benchmark_code":         "148614",
        "aum_min":                500,
        "aum_max":                12000,
        "down_capture_max":       105,
        "min_history_years":      5,
    },

    # ── FLEXI CAP ────────────────────────────────────────────────────────
    # Benchmark: Nifty 500 index fund (Direct Growth)
    "Flexi Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Flexi Cap Fund"],
        "name_must_contain":      [],
        # Run: python utils.py verify 147622 to confirm
        "benchmark_code":         "147622",
        "aum_min":                500,
        "aum_max":                50000,
        "down_capture_max":       95,
        "min_history_years":      7,
    },

    # ── UNCOMMENT TO ENABLE ADDITIONAL CATEGORIES ────────────────────────
    # "Multi Cap": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["Multi Cap Fund"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",   # Nifty 500 proxy
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "down_capture_max":       100,
    #     "min_history_years":      3,   # category only exists post-2020 SEBI mandate
    # },
    # "ELSS": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["ELSS"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",   # Nifty 500 proxy
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "down_capture_max":       100,
    #     "min_history_years":      7,
    # },
    # "Focused Fund": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["Focused Fund"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",
    #     "aum_min":                500,
    #     "aum_max":                30000,
    #     "down_capture_max":       100,
    #     "min_history_years":      5,
    # },
}
