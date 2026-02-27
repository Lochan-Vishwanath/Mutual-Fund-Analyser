# MF Master Plan — Strategy Gap Analysis & Upgrade Report

## 1. What the Python Code (Strategy A) Does Well

| Capability | Implementation Quality |
|---|---|
| Rolling return consistency (vs benchmark) | ✅ Solid — 3-year windows, configurable threshold |
| Absolute return consistency (Advisorkhoj 12% target) | ✅ Excellent addition — pure point-to-point misses this |
| Capital protection gate (max 5% negative windows) | ✅ Smart gate — eliminates disaster-prone funds early |
| Sortino ratio (downside-only risk penalty) | ✅ Correctly prefers Sortino over Sharpe |
| Information ratio | ✅ Proper active-return-per-unit-tracking-error |
| Down-market capture | ✅ Computed and used as a Phase 2 gate |
| Max drawdown | ✅ In both gate and scoring |
| Quartile-based scoring (1–4 system) | ✅ Good relative scoring within peer set |
| Passive fund handling (tracking error ranking) | ✅ Correctly separates passive from active logic |
| AUM gates (min/max per category) | ✅ Category-specific bounds |
| History gate (min 5 years) | ✅ Filters out funds without track records |
| Fund elimination audit trail | ✅ Saves reasons — transparent |

---

## 2. Critical Gaps in Python Code vs Combined Strategy

### Gap 1 — UPSIDE CAPTURE RATIO is ABSENT ❌
**Impact: HIGH**

The code computes `down_capture` but completely ignores `up_capture`. The combined strategy is explicit: you want `up_capture > 1` (fund participates MORE than benchmark in rallies) AND `down_capture < 1` (fund falls LESS than benchmark in crashes). A fund with good down capture but terrible up capture is essentially a glorified debt fund masquerading as equity. You're currently blind to this.

**Fix:** Add `compute_up_capture()` to metrics.py and include it in Phase 3 scoring with a 18-20% weight.

---

### Gap 2 — CATEGORY AVERAGE ROLLING RETURN COMPARISON is ABSENT ❌
**Impact: HIGH**

The code only compares rolling returns against the **benchmark index fund**. The combined strategy explicitly requires comparison against **category average** as a second data point. A fund that beats its benchmark but sits below the category median is a weak choice. Both comparisons together tell you if a fund is truly top-tier or just riding a good benchmark.

**Fix:** After collecting all fund metrics within a category, compute the category median rolling return and add `rolling_vs_category_avg` as a display metric and minor scoring input.

---

### Gap 3 — EXPENSE RATIO (TER) NOT IN SCORING ❌
**Impact: MEDIUM-HIGH**

TER is mentioned in `config.py` comments but is **never fetched and never scored**. The combined strategy is clear: compare TER within the category range — lowest cost among similar-quality funds wins ties. In a 20-year compounding horizon, 0.3% excess TER costs ~6% of total corpus. Two funds with identical rolling consistency and Sortino should not rank equally when one charges 0.45% and the other charges 0.85%.

**Fix:** Fetch TER from AMFI's expense ratio file. Add 5% weight to scoring. Flag high-TER outliers in the UI.

---

### Gap 4 — BETA IS COMPUTED BUT COMPLETELY IGNORED IN SCORING ❌
**Impact: MEDIUM**

Beta is calculated in `metrics.py` and stored in results but contributes 0% to Phase 3 scoring. The combined strategy explicitly uses beta as context for interpreting capture ratios. A fund with beta > 1.2 that has strong up_capture looks good — but if it also has down_capture > 90, it just means it amplifies everything equally, which is just leverage, not skill.

**Fix:** Don't add beta directly to scoring (it's too blunt), but use it to contextualise capture ratio interpretation in the UI and email. Flag beta > 1.3 as "amplified market exposure."

---

### Gap 5 — NO HYBRID CATEGORIES ❌
**Impact: MEDIUM**

The config has only 4 active categories (Mid Cap, Small Cap, Flexi Cap, Large Cap/Index). Missing entirely:
- **Large Cap (Active)** — separate from passive index funds
- **Large & MidCap** — popular SEBI category with distinct risk/return profile
- **MidCap & SmallCap** — another distinct SEBI-defined category

These categories have different benchmarks, different AUM ceilings, and different down-capture thresholds from pure Mid Cap or Small Cap. Conflating them leads to wrong benchmarks being used.

**Fix:** Add all 3 missing categories to `config.py` with correct AMFI keywords and benchmarks.

---

### Gap 6 — FUND MANAGER CHANGE NOT DETECTED ❌
**Impact: MEDIUM (but critical when it occurs)**

The Python code has zero awareness of fund manager tenure or changes. The combined strategy flags this as potentially the most important single check: if the manager who built the track record left 6 months ago, every metric you computed is historical fiction. The new manager may have a completely different risk appetite and investment style.

**Limitation:** Free APIs (mfapi.in, AMFI) don't provide manager change dates. This cannot be fully automated.

**Partial Fix:** Flag funds whose most recent 1-year metrics diverge sharply from their 3-year averages (a proxy indicator that something structural changed). Add a manual checklist reminder in the email/UI.

---

### Gap 7 — SECTOR AND STOCK CONCENTRATION NOT CHECKED ❌
**Impact: MEDIUM**

The combined strategy explicitly checks portfolio internals — sector concentration (a heavy bet on one sector) and stock concentration (top-10 holdings > 70% is high-conviction risk). The code never looks inside the portfolio.

**Limitation:** mfapi.in does not provide portfolio holdings data. This requires scraping AMC websites or using a paid data provider like MFI Explorer / Trendlyne.

**Partial Fix:** Display a reminder in the email to manually check the fund's factsheet for any fund that makes the final top 3. Cannot be automated with current free APIs.

---

### Gap 8 — ROLLING CONSISTENCY USES ONLY BENCHMARK, NOT CATEGORY PEERS ❌
**Impact: MEDIUM**

The `rolling_consistency` metric counts how often a fund beats its **benchmark index fund**. But the category average rolling return gives you a different signal: how does this fund rank vs all funds managing the same mandate? A fund in the 80th percentile vs peers is more informative than one that just barely beats a passive benchmark.

**Fix:** Compute `category_percentile_rolling` = the fund's rolling return as a percentile vs all computed funds in the same category.

---

## 3. What the Combined Strategy Is Missing That the Code Does Right

| Code Strength | Why It's Good |
|---|---|
| Absolute return consistency gate (12% target, 70% windows) | Better than just beating benchmark — asks "does this fund actually make money in absolute terms?" |
| Capital protection gate (< 5% negative windows) | Directly penalises funds that create panic-inducing drawdowns even if they recover |
| Phase 2 as binary gates before Phase 3 scoring | Prevents weak-in-one-dimension funds from sneaking into the top 3 via compensating strengths |
| AUM max gate per category | Prevents recommending funds that are too large to manoeuvre in mid/small cap |
| Fund elimination audit trail | Full transparency on WHY a fund was cut — invaluable for trust |
| Category-specific down_capture_max thresholds | Flexi Cap (95) vs Small Cap (105) vs Mid Cap (100) — correctly category-adjusted |

---

## 4. Combined & Upgraded Strategy

### Phase 1 — Universe Construction
- Fetch all Direct Growth funds from AMFI NAVAll.txt per category
- Apply `_is_direct_growth()` filter to exclude Regular plans, IDCW, ETFs, FoFs

### Phase 2 — Hard Gates (any failure = elimination)
| Gate | Threshold | Notes |
|---|---|---|
| History | ≥ 5 years NAV data | 7 years for Flexi Cap |
| AUM | Category-specific min/max | Prevents illiquidity and bloat |
| Rolling Consistency | ≥ 65% of windows beat benchmark | Relative consistency |
| Absolute Consistency | ≥ 70% of windows ≥ 12% CAGR | Advisorkhoj absolute method |
| Capital Protection | ≤ 5% of windows with negative returns | NEW: also gate on up_capture < 70 |
| Up Capture | ≥ 80 (NEW) | Can't participate in rallies = disqualified |
| Down Capture | Category-specific max | Existing, correct |

### Phase 3 — Weighted Scoring
| Metric | Weight | Direction |
|---|---|---|
| Rolling consistency (vs benchmark) | 18% | Higher = better |
| Sortino ratio | 20% | Higher = better |
| Information ratio | 15% | Higher = better |
| Upside capture ratio (NEW) | 18% | Higher = better |
| Downside capture ratio | 15% | Lower = better |
| Max drawdown | 09% | Less negative = better |
| TER / expense ratio (NEW) | 05% | Lower = better |

### Phase 4 — Qualitative Flags (automated where possible, manual where not)
- **Beta context**: Flag beta > 1.3 as "amplified exposure" in UI
- **Manager change proxy**: Flag if 1Y return rank diverges > 30 percentile points from 3Y rank
- **Category percentile**: Show each fund's rolling return percentile vs all category peers
- **TER vs category range**: Show where the fund sits (bottom 25% = green, top 25% = red)

### Phase 5 — Manual Checks (prompted by the tool, not automated)
- Sector concentration: Open factsheet and check no single sector > 35%
- Top-10 holdings %: Flag if factsheet shows > 70%
- Fund manager tenure on this specific fund
- SEBI stress test results (for Small/MidCap)

---

## 5. Summary of Code Changes Required

| File | Changes |
|---|---|
| `metrics.py` | Add `compute_up_capture()`, include in `compute_all_metrics()` |
| `fetcher.py` | Add `get_ter_map()` from AMFI portal |
| `config.py` | Add Large Cap (active), Large & MidCap, MidCap & SmallCap categories; update SCORE_WEIGHTS |
| `screener.py` | Add up_capture gate; add TER to scoring; compute category percentiles |
| `app.py` | Separate passive/active tabs; show up_capture, TER, category percentile columns |
| `emailer.py` | Show up_capture and TER in fund cards; add qualitative flag section |

---

*Generated by MF Master Plan Strategy Analysis — February 2026*
