# Advanced Testing Strategies for MF Analyser

To move beyond point-in-time backtests and truly stress-test the v4.0 selection architecture, the following strategies should be implemented:

## 1. The "Monte Carlo" Universe Test
**The Problem**: Current tests only pick the #1 ranked fund. If the #2 fund was a disaster, we wouldn't know if the tool is robust or just lucky.
**The Solution**: 
- For each category, identify the Top 5 tool-ranked funds.
- Run the backtest 1,000 times, randomly selecting one fund from the Top 5 for each category in each run.
- **Goal**: Measure the distribution of returns. We want to see a tight variance with a high mean. If variance is high, the tool is "picking needles" (fragile) rather than "picking quality haystacks" (robust).

## 2. "Peak & Trough" Stress Testing
**The Problem**: Testing Jan 1st of every year is arbitrary and might coincide with local market anomalies.
**The Solution**: 
- Manually identify structural market peaks (e.g., Jan 2020 pre-COVID, Oct 2021) and troughs (March 2020, June 2022).
- Start the 3-bucket SIP strategy at these specific dates.
- **Goal**: Measure real-world "Downside Capture." Does the tool-selected portfolio recover faster or protect capital better when entry is poorly timed?

## 3. Rolling Window XIRR Analysis
**The Problem**: Absolute returns are sensitive to start/end dates and don't account for the time value of SIP cash flows accurately over multiple cycles.
**The Solution**: 
- Calculate the **XIRR (Internal Rate of Return)** for every possible 3-year SIP window since 2013 (e.g., Jan-13 to Jan-16, Feb-13 to Feb-16, etc.).
- **Goal**: Determine the "Probability of Outperformance." What percentage of random 3-year windows beat the Nifty 500? This is the ultimate metric for consistency.

## 4. The "Churn Cost" Sensitivity Analysis
**The Problem**: Rebalancing triggers tax and exit loads. A 2-quarter failure rule might be too sensitive for Indian tax laws (LTCG/STCG).
**The Solution**: 
- Run the rebalancing bucket (Bucket 2) with different sensitivity thresholds:
    - 2-Quarter Rule (current)
    - 4-Quarter Rule (more patient)
    - Rank-based exit (e.g., only exit if dropped to Bottom 50%)
- **Goal**: Identify the "Rebalancing Sweet Spot" where the alpha gained from the new fund exceeds the tax friction incurred by selling the old one.
