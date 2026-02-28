# Backtest Comparison: 2019 Selection Strategies

This backtest compares three strategies for mutual fund selection and portfolio management between **January 2019** and **February 2026**.

## Methodology
- **Bucket 1 (Best of 2019)**: Top performers by 3-year CAGR as of Jan 1, 2019. Buy and hold.
- **Bucket 2 (Tool + Rebalancing)**: Tool-selected funds with a **2-quarter rebalancing rule**. If a fund fails gates for 2 consecutive quarters, it is replaced.
- **Bucket 3 (Tool - No Rebalancing)**: Same initial tool-selected funds as Bucket 2, but follows a **Buy and Hold** strategy.

---

## Category-wise Post-Tax Returns (Jan 2019 – Feb 2026)

| Category | Bucket 1 (Best of 2019) | Bucket 3 (Tool - No Rebal) | Bucket 2 (Tool + Rebal) |
| :--- | :---: | :---: | :---: |
| **Large Cap (Passive)** | 51.2% | **53.7%** | **53.7%** |
| **Large Cap (Active)** | 56.0% | **74.7%** | **74.7%** |
| **Large & MidCap** | **77.6%** | 68.2% | 70.5% |
| **Mid Cap** | 76.6% | **85.2%** | **85.2%** |
| **Small Cap** | **122.9%** | 93.2% | 93.2% |
| **Flexi Cap** | **72.4%** | **72.4%** | 69.0% |

---

## Overall Portfolio Summary

| Metric | Bucket 1 (Best) | Bucket 3 (Tool - Buy/Hold) | Bucket 2 (Tool - Rebal) |
| :--- | :---: | :---: | :---: |
| **Invested** | ₹52.2L | ₹52.2L | ₹52.2L |
| **Final Val (Post-Tax)** | **₹91.9L** | ₹91.1L | ₹91.0L |
| **Return (%)** | **76.1%** | 74.6% | 74.4% |

---

## Key Findings
1. **Selection Alpha**: The tool (Bucket 3) significantly outperformed the "past winners" (Bucket 1) in the **Large Cap (Active)** and **Mid Cap** categories.
2. **The "Nippon Small Cap" Factor**: Bucket 1's overall victory is largely driven by *Nippon India Small Cap*, which returned 122.9% vs the tool's pick (*Franklin Small Cap*) at 93.2%.
3. **Rebalancing Impact**:
    - **Helped**: In *Large & MidCap*, rebalancing from *Canara Robeco* to *Axis* and then *Motilal Oswal* improved returns from 68.2% to 70.5%.
    - **Hurt**: In *Flexi Cap*, rebalancing from *ABSL* to *quant* in 2022 reduced returns from 72.4% to 69.0% due to tax friction and timing.
4. **Tax Friction**: Bucket 2 incurred significant taxes during rebalancing. In the overall portfolio, the "buy and hold" version of the tool (Bucket 3) beat the rebalancing version (Bucket 2) by 0.2% absolute return, proving that rebalancing must provide substantial alpha to cover tax costs.
