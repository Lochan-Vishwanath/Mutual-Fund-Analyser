Phase 0: Data Ingestion & Pre-Filtering
Before any financial analysis happens, the fetcher.py and screener.py perform basic data cleaning to narrow down the universe of funds.
1.  Direct Growth Only (_is_direct_growth):
    *   Meaning: Filters for schemes where you invest directly with the AMC (lower fees) and returns are reinvested (Growth).
    *   Logic: Excludes "Regular" plans, "Dividend/IDCW" variants, "ETFs," "Fund of Funds (FoF)," and "Pension/Retirement" schemes.
    *   Rationale: Direct Growth is the most efficient way to build wealth in the long term.
2.  Category Keyword Matching:
    *   Meaning: Groups funds into specific AMFI (Association of Mutual Funds in India) categories.
    *   Logic: Uses keywords like "Large Cap," "Mid Cap," etc., from config.py to match against AMFI section headers.
---
Phase 1: Static Hard Filters (Elimination)
In screener.py, these filters act as binary gates. If a fund fails any of these, it is eliminated with a recorded reason.
3.  History Gate (min_history_years):
    *   Meaning: The minimum track record required for a fund.
    *   Logic: Typically 5 to 7 years (set in config.py).
    *   Rationale: Guarantees the fund has survived at least one full market cycle, proving it isn't just a "one-hit wonder."
4.  AUM Bounds (aum_min, aum_max):
    *   Meaning: The total size (Assets Under Management) of the fund in Crores.
    *   Logic: 
        *   Min (₹500Cr - ₹1000Cr): Avoids tiny funds with high liquidity risk.
        *   Max (₹12kCr - ₹50kCr): Prevents "Mandate Drift" in Small/Mid Cap funds where a massive size makes it hard for the manager to find quality stocks.
---
Phase 2: Hybrid Dynamic Gates (The v3 Innovation)
Instead of static numbers, these filters adapt to the current market by comparing a fund against its Benchmark AND its Category Median/Average.
5.  Negative Sharpe Ratio Gate:
    *   Meaning: Measures return per unit of total risk.
    *   Logic: Any fund with a negative Sharpe ratio is cut.
    *   Rationale: If a fund isn't beating the risk-free rate (like a T-bill), there's no reason to take the equity risk.
6.  Rolling Consistency Floor (ROLLING_CONSISTENCY_FLOOR):
    *   Meaning: How often the fund beats its benchmark in 3-year rolling windows.
    *   Logic: Fund must beat the benchmark ≥ 50% of the time AND be above the Category Median.
    *   Rationale: Consistency is valued over lucky "trailing returns."
7.  Capital Protection Gate (CAPITAL_PROTECTION_FLOOR):
    *   Meaning: The percentage of rolling windows with negative returns.
    *   Logic: Must have negative returns in ≤ 10% of 3-year windows.
    *   Rationale: Ensures the fund protects capital during bad times.
8.  Capture Ratio Gates:
    *   Upside Capture (up_capture): Must be above the Category Average. (Ability to gain in rallies).
    *   Downside Capture (down_capture): Must be below the Category Average (or a tight limit like 95/100). (Protection in crashes).
---
Phase 3: Multi-Dimensional Weighted Scoring
Funds that survive the gates are ranked using a 1–4 quartile scale across seven key dimensions.
| Metric | Weight | Why it matters |
| :--- | :--- | :--- |
| Sortino Ratio | 20% | Return vs "Bad" Volatility (downside risk). |
| Rolling Consistency | 18% | Long-term consistency vs. luck. |
| Upside Capture | 18% | Participation in bull markets. |
| Information Ratio | 15% | Manager skill in generating consistent alpha. |
| Downside Capture | 15% | Protection during market crashes. |
| Max Drawdown | 9% | The worst-case drop (behavioral check). |
| Expense Ratio (TER) | 5% | Lower cost acts as a tie-breaker for top funds. |
---
Phase 4: Qualitative Red Flags & Continuity
The system adds heuristic "flags" to the top funds for manual human verification (emailer.py and app.py).
9.  Manager Change Proxy:
    *   Logic: If 3-year performance rank diverges from 5-year rank by > 30 percentile points, it flags a potential manager change.
    *   Rationale: Historical data is invalid if the person who created it is no longer there.
10. High Beta Flag:
    *   Logic: Flags funds with Beta > 1.3.
    *   Rationale: Warns you that this fund will crash much harder than the market during a downturn.
11. Continuity Rule:
    *   Holdover 🛡️: Fund was in the Top 3 last quarter. Keep holding to save on taxes and exit loads.
    *   New Entrant 🌟: New to the Top 3. Requires a manual deep-dive before moving capital.

I was building a mutual fund analyser, i am using the above strategy to analyse and pick 3 funds in each category (large cap index, mid, small, large n mid and flexi cap) 

is this logic / filtering good? or is the logic bad? if its bad how would u improve it?


LLM 1:

The overall architecture is genuinely solid — you're thinking in the right layers (elimination → scoring → qualitative flags), and the v3 hybrid dynamic gates are a real improvement over pure static thresholds. But there are meaningful gaps and a few logical problems worth addressing.

**What's actually good**

The dynamic benchmarking in Phase 2 is the strongest part. Comparing against category median rather than absolute numbers prevents you from accidentally eliminating entire categories during bad market cycles. The Holdover/New Entrant continuity rule is also practically smart — most retail-grade screeners completely ignore tax and exit load friction.

---

**The real problems**

**1. The scoring weights have a hidden double-count**

You're scoring Upside Capture (18%) and Downside Capture (15%) separately, but both are already partially captured in the Sortino Ratio (20%). A fund with great Sortino almost certainly has controlled downside capture. This means downside protection is effectively weighted closer to 35% when you add the correlated components, while the Information Ratio at 15% — arguably the cleanest measure of *manager skill* — is underweighted relative to its importance. Consider replacing Upside/Downside Capture in the scoring with the **Capture Ratio spread** (Upside minus Downside) as a single metric, since what you actually care about is the asymmetry.

**2. The AUM max cap will break on Large Cap**

A ₹12k–50k Cr upper bound makes sense for Small and Mid Cap (mandate drift is real there), but for Large Cap and Flexi Cap funds, large AUM is often a *signal of trust and stability*, not a liability. Funds like PPFAS Flexi Cap or Mirae Large Cap have navigated very large AUM without drift because large-cap stocks have the liquidity to absorb it. You should either remove the max AUM gate for Large Cap and Flexi Cap categories entirely, or raise it significantly (₹80k+ Cr).

**3. The Manager Change Proxy is too noisy**

A 30-percentile-point divergence between 3-year and 5-year rank is an extremely blunt instrument. This will frequently fire due to mean reversion, a style rotation, or simply a bad 2-year stretch — none of which indicate a manager change. A real manager change flag should either pull actual manager tenure data from AMFI/MFI Explorer, or use a change in *volatility signature* (rolling standard deviation of returns changing structurally) as a proxy. The rank divergence check produces too many false positives and will erode trust in your flags quickly.

**4. Rolling Consistency Floor has a survivorship blind spot**

You require ≥50% benchmark-beating in 3-year rolling windows, but 3-year windows measured on a fund's *existing* NAV history already exclude funds that closed down. The funds you're analyzing have already survived. This means your consistency metric is implicitly more lenient than it appears. You won't easily fix survivorship bias entirely, but you should be aware that your consistency bar is softer than the numbers suggest — perhaps tighten the floor to 55–60% to compensate.

**5. Expense Ratio at 5% weight is almost meaningless**

In Direct Growth plans across a given category, TER variance is typically only 0.2–0.5%. At 5% weight in a quartile scoring system, this will almost never change a fund's final rank. Either raise it to 10–12% (where it can actually act as a tiebreaker with teeth), or convert it into a hard gate — eliminate any fund whose TER is more than, say, 0.3% above the category median. A gate is more honest than a weight that does nothing.

**6. No valuation or portfolio concentration check**

Your system is entirely return/risk-based. For Small and Mid Cap especially, a fund can score beautifully on all your metrics while running a highly concentrated portfolio (say, top-10 holdings = 65%+ of AUM). Concentration isn't inherently bad, but it's a behavioral risk your framework currently can't see. Even a simple flag for funds with top-10 concentration above the category average would be valuable.

---

**What I'd add**

A **regime-awareness layer** would make the system significantly more robust. Your rolling windows treat all periods equally, but market behavior in 2020–2021 (liquidity-driven bull run) is structurally different from 2018–2019 (earnings-driven). Weighting recent rolling windows slightly more, or separately flagging how a fund performed specifically during the 2020 crash recovery and the 2022–2023 correction, gives you much richer signal than a single aggregate consistency number.

---

**Summary verdict**

The skeleton is well-reasoned and better than most retail screeners. The main fixes in priority order: fix the AUM cap by category, replace the capture ratio double-count in scoring, rethink the manager change proxy, and give TER a gate instead of a token weight. Do those four things and the system becomes genuinely defensible.

LLM 2:

Yes, the review provided by LLM 1 is exceptionally accurate, financially sound, and highly practical. It correctly identifies the mathematical and logical blind spots in your algorithm while validating the strong architectural choices you made.

Here is a breakdown of exactly why the review is correct, along with one major flaw that both your algorithm and the review missed regarding your specific goals.

Why the Review is Spot-On
The Double-Counting Issue (Collinearity): The review correctly points out that your scoring system heavily overlaps. You have allocated 20% to Sortino Ratio, 15% to Downside Capture, and 9% to Max Drawdown. All three of these metric measure the exact same thing: downside risk. This means 44% of your total score is just penalizing downside volatility. This will heavily skew your results toward hyper-conservative funds and unjustly penalize aggressive funds that might actually generate better long-term wealth.

The AUM Cap Flaw: Limiting AUM to ₹12kCr - ₹50kCr is a great guardrail against "mandate drift" for Small and Mid Cap funds, where liquidity is low. However, as the reviewer noted, applying this to Large Cap or Flexi Cap funds will eliminate some of the best, most stable funds in the Indian market. Large-cap stocks have massive liquidity, so a ₹80,000+ Cr AUM is not a hindrance.

The Manager Change Proxy: Using a >30 percentile drop between 3-year and 5-year ranks is a very poor proxy for a manager change. Markets move in cycles (e.g., Value vs. Growth). A fund manager who strictly buys "Value" stocks will naturally look terrible during a 3-year "Growth" rally, causing their rank to plummet without any change in management. The reviewer's suggestion to track actual AMFI data or volatility signatures is the mathematically correct approach.

The TER Weighting Math: The reviewer is mathematically correct that a 5% weight in a 1-4 quartile system is practically useless. Because Direct Growth funds in the same category have very similar Expense Ratios, a 5% weight will almost never result in enough points to change a fund's final rank. Moving it to a hard elimination gate is a much better solution.

architecture re-write after LLM 1 n 2's reviews:

Good call, let's focus purely on rebuilding. I'll keep the same phase structure since the skeleton is sound, but surgically fix every confirmed problem.

---

## Rebuilt Architecture

### Phase 0: Data Ingestion — No Changes Needed
The Direct Growth filter and Category Keyword Matching are solid. Leave them as-is.

---

### Phase 1: Static Hard Filters — Make AUM Category-Aware

The only real fix here is splitting AUM bounds by category instead of using one universal range.

| Category | AUM Min | AUM Max | Rationale |
|---|---|---|---|
| Small Cap | ₹500 Cr | ₹15,000 Cr | Mandate drift is real, liquidity is low |
| Mid Cap | ₹500 Cr | ₹25,000 Cr | Moderate liquidity constraints |
| Large & Mid Cap | ₹1,000 Cr | ₹40,000 Cr | Blended liquidity |
| Large Cap | ₹2,000 Cr | ₹80,000 Cr | Large-cap stocks absorb large AUM fine |
| Flexi Cap | ₹2,000 Cr | No hard cap | Manager decides allocation, size is a trust signal |

Everything else in Phase 1 (History Gate at 5–7 years) stays unchanged.

---

### Phase 2: Dynamic Gates — Three Changes

**Keep:** Negative Sharpe gate and Capital Protection gate. Both are conceptually clean.

**Change 1 — Rolling Consistency Floor**
Raise the benchmark-beating threshold from ≥50% to ≥55% across all categories, and ≥60% for Small Cap specifically. This partially compensates for survivorship bias without requiring a data infrastructure overhaul you can't practically build.

**Change 2 — TER becomes a Gate, not a Score**
Remove TER from Phase 3 scoring entirely. Instead, add it here as a hard gate: eliminate any fund whose TER is more than 0.3% above its category median. This is honest — a weight that rarely changes rankings is theater, a gate has real teeth.

**Change 3 — Capture Ratio Gate becomes Asymmetry-Based**
Instead of two separate gates (Upside > category average AND Downside < category average), replace with a single **Capture Ratio Spread gate**: Upside Capture minus Downside Capture must be positive AND above the category median spread. This tests the asymmetry you actually care about — gaining more than you lose — rather than two metrics that can compensate each other in misleading ways.

---

### Phase 3: Scoring — Fix the Collinearity Problem

This is the most important structural change. The confirmed problem is that Sortino (20%) + Downside Capture (15%) + Max Drawdown (9%) = 44% of your score measuring the same underlying thing: downside risk. Here's the rebuilt scoring table:

| Metric | Old Weight | New Weight | Change |
|---|---|---|---|
| Information Ratio | 15% | 25% | ↑ Big raise — cleanest measure of repeatable manager skill |
| Rolling Consistency | 18% | 22% | ↑ Slightly raised — consistency over luck is the core philosophy |
| Capture Ratio Spread | — | 20% | ✦ New combined metric replacing separate Up/Down capture |
| Sortino Ratio | 20% | 18% | ↓ Slight trim, still important but no longer triple-counted |
| Alpha Stability | — | 15% | ✦ New — rolling 3yr alpha standard deviation; low variance = consistent manager |
| Max Drawdown | 9% | 0% | ✗ Removed — fully redundant with Sortino and Capture Spread |
| Upside Capture | 18% | 0% | ✗ Removed — now captured in Capture Ratio Spread |
| Downside Capture | 15% | 0% | ✗ Removed — same reason |
| TER | 5% | 0% | ✗ Moved to Phase 2 as a hard gate |
| **Total** | **100%** | **100%** | |

The philosophy shift is deliberate: you're moving from a system that heavily punished downside volatility toward one that rewards *repeatable, skill-based alpha generation* — which is a more accurate proxy for finding a genuinely good active manager.

The **Alpha Stability** metric is new but straightforward to compute: take the fund's rolling 3-year alpha against its benchmark, calculate the standard deviation of that rolling series. A low standard deviation means the manager consistently adds value rather than having great years and terrible ones. This is directionally different from the Information Ratio (which measures average alpha per unit of tracking error) and earns its own slot.

---

### Phase 4: Red Flags — Fix the Manager Change Proxy

**Replace the rank divergence check entirely.** Use a two-signal approach instead:

**Signal 1 — Volatility Signature Shift:** Calculate the rolling 12-month standard deviation of returns over the fund's history. If the most recent 2-year volatility signature differs from the prior 3-year signature by more than 1.5 standard deviations, flag it. A new manager almost always brings a different risk tolerance, which shows up in volatility before it shows up in returns.

**Signal 2 — Alpha Sign Flip:** If the fund's 3-year rolling alpha is positive but its most recent 1-year alpha has turned negative *and* is below the category median, flag it. This catches regime changes in manager behavior without needing external tenure data.

Either signal alone triggers the flag. Both together is a strong warning.

**Keep:** High Beta flag (Beta > 1.3) and the Holdover/New Entrant continuity rule. Both are well-designed.

**Add — Portfolio Concentration Flag:** If the fund's top-10 holdings as a percentage of AUM is more than 10 percentage points above the category average, flag it. This is especially important for Small and Mid Cap. The data is available in monthly factsheets from AMFI. You're not eliminating the fund, just surfacing a behavioral risk for human review.

---

### What the Rebuilt System Looks Like End-to-End

```
Phase 0: Direct Growth filter → Category matching
           ↓
Phase 1: History gate (5-7yr) → Category-specific AUM bounds
           ↓
Phase 2: Negative Sharpe gate → TER gate (new) → 
         Rolling Consistency ≥55% → Capital Protection ≤10% →
         Capture Ratio Spread > category median
           ↓
Phase 3: Score on 5 metrics (IR 25%, Consistency 22%, 
         Capture Spread 20%, Sortino 18%, Alpha Stability 15%)
           ↓
Phase 4: Volatility signature flag → Alpha sign flip flag →
         Concentration flag → Beta flag → Holdover/New Entrant rule
```

The total number of scoring dimensions dropped from 7 to 5, but the system is now measuring 5 genuinely distinct things rather than 7 metrics clustered around 3 concepts. That's a meaningfully better screener.

LLM 3's review:

I completely agree with the architecture re-write. The reviews from LLM 1 and LLM 2 were incredibly sharp, and the resulting rebuilt framework takes your screener from a "good retail script" to a genuinely institutional-grade quantitative model.

You successfully eliminated the downside-risk collinearity, fixed the rigid AUM caps that would have incorrectly penalized massive but stable Large/Flexi cap funds, and correctly demoted TER to a binary gate rather than a useless scoring weight.

That being said, because you asked if we can make it **even better**, the answer is yes. There are a few critical blind spots remaining—especially regarding your specific fund categories—that we need to patch to make this bulletproof.

Here is how we can take this from 95% to 100%:

### 1. The "Large Cap Index" Contradiction (Crucial Fix)

You mentioned you are picking 3 funds in categories including **"large cap index"**.

* **The Problem:** The entire Phase 3 scoring system (Information Ratio, Alpha Stability, Capture Spreads) evaluates *active management skill*. An index fund's explicit goal is to have zero alpha and an Information Ratio of zero. If you run an index fund through this model, it will break or give you garbage outputs.
* **The Fix:** You need a logic fork at Phase 1. If the fund category contains "Index" or "ETF", it must bypass Phase 2 and 3 entirely and go down a **Passive Path**.
* **Passive Gate:** Tracking Error must be below a certain threshold.
* **Passive Score:** 70% Tracking Error (lower is better), 30% TER (lower is better).



### 2. Capture Ratio Spread vs. Capture Ratio Division

The re-write replaced separate Up/Down capture metrics with a "Capture Ratio Spread" (Upside minus Downside).

* **The Problem:** A spread can hide the magnitude of volatility.
* Fund A: 90% Upside, 80% Downside (Spread = 10%)
* Fund B: 130% Upside, 120% Downside (Spread = 10%)
Both pass the gate with the same score, but Fund B is wildly more volatile and behaves very differently during crashes.


* **The Fix:** Instead of subtraction, use division to find the true ratio of asymmetry:
$\text{Capture Ratio} = \frac{\text{Upside Capture}}{\text{Downside Capture}}$
A ratio > 1 means positive asymmetry. This standardizes the metric regardless of how aggressively the fund swings.

### 3. The Missing Metric: Portfolio Turnover Ratio (PTR)

* **The Problem:** The current model doesn't track how often the manager buys and sells. A fund might score beautifully on Alpha Stability and IR, but if it has a Portfolio Turnover Ratio of 150%, the manager is churning the portfolio. This leads to hidden transaction costs (impact cost) and terrible tax efficiency that isn't fully reflected in the gross NAV until it eventually drags down long-term compounding.
* **The Fix:** Add a **High Churn Flag** in Phase 4. If a fund's PTR is > 100% (or significantly above its category median), flag it for manual review.

### 4. Adjusting Rolling Windows by Market Cap

* **The Problem:** You are using 3-year rolling windows for consistency and alpha checks across all categories. While 3 years is perfect for Large and Flexi caps, a full market cycle for Small and Mid caps in India often takes 5 to 7 years.
* **The Fix:** Make your rolling window calculations dynamically adapt to the category. Use 3-year rolling windows for Large/Flexi, and 5-year rolling windows for Small/Mid Cap. This ensures you aren't just capturing a mid-cap fund during a liquidity-fueled bull run.

---

### Final Verdict

Your current re-write is excellent and highly defensible for active equity funds. If you add the **Active vs. Passive logic fork** (which is absolutely necessary for your Large Cap Index requirement), fix the Capture Ratio math, and add a Turnover flag, your script will rival high-end commercial screeners.