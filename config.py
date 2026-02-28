# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  All configurable parameters for MF Analyser v4.0
#
# v4 Changes from v3:
#   - AUM bounds are now category-specific (no global max)
#   - Rolling windows are category-specific (3yr Large/Flexi, 5yr Mid/Small)
#   - TER is now a GATE (not a scoring weight) — eliminates funds >0.3% above median
#   - SCORE_WEIGHTS rebalanced to 5 non-collinear metrics:
#       IR (25%), Rolling Consistency (22%), Capture Ratio (20%),
#       Sortino (18%), Alpha Stability (15%)
#   - Capture Ratio replaces separate Up/Down capture in scoring (division-based)
#   - Rolling Consistency floors raised to 55%/60% to compensate for survivorship bias
#   - Manager change proxy replaced by volatility-signature + alpha-sign-flip
#   - Phase 4 flags: PTR (category-relative), portfolio concentration added
# ─────────────────────────────────────────────────────────────────────────────

import os
from dotenv import load_dotenv

load_dotenv()

# ── EMAIL ─────────────────────────────────────────────────────────────────────
EMAIL_SENDER   = os.getenv("EMAIL_SENDER",        "yourname@gmail.com")
EMAIL_PASSWORD = os.getenv("MF_EMAIL_PASSWORD",   "")
EMAIL_SUBJECT  = "Quarterly MF Review — Top 3 Funds Per Category"
SUBSCRIBERS    = os.getenv("SUBSCRIBERS",         "you@gmail.com").split(",")

# ── TOP N FUNDS PER CATEGORY ──────────────────────────────────────────────────
TOP_N = 3

# ── RISK-FREE RATE ────────────────────────────────────────────────────────────
# 91-day T-bill yield. Update quarterly from rbi.org.in
RISK_FREE_RATE_ANNUAL = 0.065   # 6.5% as of Q1 2026

# ── NIFTY P/E DEPLOYMENT SIGNAL ───────────────────────────────────────────────
PE_THRESHOLDS = {
    "overvalued":  24,
    "fair_high":   22,
    "fair_value":  18,
    "attractive":  15,
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 GATE THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

# Gate: Sharpe Ratio — any fund < 0 is eliminated (no equity risk justified)
SHARPE_GATE_MIN = 0.0

# Gate: TER — eliminate any fund whose TER is more than this % above category median
# This replaces the old 5% scoring weight (too weak to matter in quartile scoring)
TER_GATE_SPREAD = 0.003    # 0.3% above category median TER

# Gate: Capital Protection — max % of rolling windows with negative returns
CAPITAL_PROTECTION_FLOOR = 0.10    # 10% maximum

# Gate: Capture Ratio (Upside/Downside) — must be > 1.0 AND above category median
# A ratio >1.0 means the fund gains more than it loses in up vs down markets
CAPTURE_RATIO_MIN = 1.0

# Gate: Rolling Consistency — category-specific (survivorship bias compensation)
# Large/Flexi use 3yr windows; Mid/Small use 5yr windows (longer cycle needed)
ROLLING_CONSISTENCY_FLOORS = {
    "large_cap_active": 0.55,
    "large_mid_cap":    0.55,
    "flexi_cap":        0.55,
    "mid_cap":          0.55,
    "small_cap":        0.60,   # Tighter — small cap cycles punish weak managers harder
}

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 SCORING WEIGHTS (must sum to 1.0)
# ─────────────────────────────────────────────────────────────────────────────
# REMOVED vs v3:
#   - up_capture (18%) + down_capture (15%) — replaced by capture_ratio (20%)
#   - max_drawdown (9%)    — collinear with Sortino, removed
#   - ter_score (5%)       — moved to Phase 2 as a hard gate
#
# ADDED vs v3:
#   - capture_ratio (20%)  — Upside/Downside as a single asymmetry metric
#   - alpha_stability (15%)— rolling alpha stddev; rewards consistent alpha generation
#
# RAISED vs v3:
#   - information_ratio: 15% → 25%  (cleanest measure of repeatable manager skill)
#   - rolling_consistency: 18% → 22%
SCORE_WEIGHTS = {
    "information_ratio":   0.25,   # Alpha per unit of active risk (manager skill)
    "rolling_consistency": 0.22,   # % windows beating benchmark (process > luck)
    "capture_ratio":       0.20,   # Upside÷Downside capture (asymmetry quality)
    "sortino_ratio":       0.18,   # Return per unit of downside volatility only
    "alpha_stability":     0.15,   # Rolling alpha stddev — lower = more consistent
}
# Sum = 0.25 + 0.22 + 0.20 + 0.18 + 0.15 = 1.00 ✓

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 FLAG THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

# Flag 2: High Beta
HIGH_BETA_THRESHOLD = 1.3

# Flag 1: Manager Change — Volatility Signature Shift
# If recent 24mo volatility is >X std devs from prior 36mo volatility → flag
MANAGER_CHANGE_VOL_THRESHOLD = 1.5   # standard deviations

# Flag 3: Portfolio Concentration
# Flag if top-10 holdings > category average by more than X percentage points
# Note: Uses data from AMFI factsheets (updated monthly). If unavailable, skip.
CONCENTRATION_FLAG_DELTA = 10.0      # percentage points above category average

# Flag 4: Portfolio Turnover Ratio
# Flag if PTR > X standard deviations above category median
PTR_FLAG_SD_MULTIPLIER = 1.5

# ─────────────────────────────────────────────────────────────────────────────
# PASSIVE SCORING WEIGHTS
# ─────────────────────────────────────────────────────────────────────────────
# For index funds: only Tracking Error and TER matter
PASSIVE_SCORE_WEIGHTS = {
    "tracking_error": 0.70,    # Lower is better — primary replication quality metric
    "ter":            0.30,    # Lower is better — direct return drag
}

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
#
# strategy           : "passive" or "active"
# amfi_category_keywords : substrings matched against AMFI section headers (NAVAll.txt)
# name_must_contain  : optional further filter by fund name substring
# benchmark_code     : mfapi.in scheme code for benchmark index fund
#                      Verify: python utils.py search "<name> Direct Growth"
#                              python utils.py verify <code>
# aum_min/aum_max    : Crores. Set aum_max to None for no upper cap.
# min_history_years  : Minimum track record required (Phase 1 gate)
# rolling_window_years: Window length for rolling consistency / capital protection
# consistency_floor_key: Key into ROLLING_CONSISTENCY_FLOORS dict above
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = {

    # ── LARGE CAP (PASSIVE) ───────────────────────────────────────────────────
    # Passive path: ranked by Tracking Error (70%) + TER (30%)
    # No benchmark needed — we measure TE against the index directly
    "Large Cap (Passive)": {
        "strategy":               "passive",
        "amfi_category_keywords": ["Index Funds", "Large Cap Fund"],
        "name_must_contain":      ["nifty 50", "sensex", "bse 100", "nifty 100"],
        "benchmark_code":         None,
        "aum_min":                1000,
        "aum_max":                None,     # No cap — large AUM is a stability signal for passive
        "min_history_years":      3,        # Shorter — passive quality visible in 3 years
        "rolling_window_years":   3,
        "consistency_floor_key":  None,     # Not applicable for passive
    },

    # ── LARGE CAP (ACTIVE) ────────────────────────────────────────────────────
    # Active path: scored on IR, Consistency, Capture Ratio, Sortino, Alpha Stability
    # Benchmark: Nifty 100 TRI (captures large-cap universe better than Nifty 50)
    # Verify: python utils.py search "Nifty 100 Index Fund Direct Growth"
    "Large Cap (Active)": {
        "strategy":               "active",
        "amfi_category_keywords": ["Large Cap Fund"],
        "name_must_contain":      [],
        # VERIFY: python utils.py search "UTI Nifty 100 Index Fund Direct"
        "benchmark_code":         "120716",
        "aum_min":                2000,
        "aum_max":                80000,    # Raised from 12k: large-cap stocks absorb large AUM
        "min_history_years":      5,
        "rolling_window_years":   3,
        "consistency_floor_key":  "large_cap_active",
    },

    # ── LARGE & MIDCAP ────────────────────────────────────────────────────────
    # Benchmark: Nifty LargeMidcap 250 index fund (Direct Growth)
    # Verify: python utils.py search "Nifty LargeMidcap 250 Direct Growth"
    "Large & MidCap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Large & Mid Cap Fund"],
        "name_must_contain":      [],
        # VERIFY: python utils.py search "LargeMidcap 250 Index Direct"
        "benchmark_code":         "149100",
        "aum_min":                1000,
        "aum_max":                40000,
        "min_history_years":      5,
        "rolling_window_years":   3,
        "consistency_floor_key":  "large_mid_cap",
    },

    # ── MID CAP ───────────────────────────────────────────────────────────────
    # Benchmark: Nifty Midcap 150 index fund (Direct Growth)
    # Uses 5-year rolling windows — mid-cap cycles in India span ~5-7 years
    # Verify: python utils.py verify 149892
    "Mid Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Mid Cap Fund"],
        "name_must_contain":      [],
        "benchmark_code":         "149892",
        "aum_min":                500,
        "aum_max":                25000,
        "min_history_years":      7,        # Must cover one full mid-cap cycle
        "rolling_window_years":   5,        # 5yr window for Mid Cap
        "consistency_floor_key":  "mid_cap",
    },

    # ── SMALL CAP ─────────────────────────────────────────────────────────────
    # Benchmark: Nifty Smallcap 250 index fund (Direct Growth)
    # Uses 5-year rolling windows — small-cap liquidity cycles are longest
    # Tightest consistency floor (60%) — small-cap is where luck most easily masquerades as skill
    # Verify: python utils.py verify 148614
    "Small Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Small Cap Fund"],
        "name_must_contain":      [],
        "benchmark_code":         "148614",
        "aum_min":                500,
        "aum_max":                15000,    # Strict: mandate drift starts early here
        "min_history_years":      7,
        "rolling_window_years":   5,
        "consistency_floor_key":  "small_cap",
    },

    # ── FLEXI CAP ─────────────────────────────────────────────────────────────
    # Benchmark: Nifty 500 index fund (Direct Growth)
    # No AUM cap — manager controls allocation, size is a trust signal
    # Verify: python utils.py verify 147622
    "Flexi Cap": {
        "strategy":               "active",
        "amfi_category_keywords": ["Flexi Cap Fund"],
        "name_must_contain":      [],
        "benchmark_code":         "147622",
        "aum_min":                2000,
        "aum_max":                None,     # No cap — Flexi Cap is mandate-agnostic
        "min_history_years":      5,
        "rolling_window_years":   3,
        "consistency_floor_key":  "flexi_cap",
    },

    # ── UNCOMMENT TO ENABLE ───────────────────────────────────────────────────
    # "Multi Cap": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["Multi Cap Fund"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "min_history_years":      3,   # Category only exists post-2020 SEBI mandate
    #     "rolling_window_years":   3,
    #     "consistency_floor_key":  "flexi_cap",
    # },
    # "ELSS": {
    #     "strategy":               "active",
    #     "amfi_category_keywords": ["ELSS"],
    #     "name_must_contain":      [],
    #     "benchmark_code":         "147622",
    #     "aum_min":                500,
    #     "aum_max":                50000,
    #     "min_history_years":      7,
    #     "rolling_window_years":   3,
    #     "consistency_floor_key":  "large_cap_active",
    # },
}
