# Backtest Comparison: Best Performers (2019) vs. Tool-Based Selection

This backtest compares two strategies for mutual fund selection and portfolio management between **January 2019** and **February 2026**.

## Methodology
- **Bucket 1 (Best Performers of 2019)**: Selected the top fund by 3-year CAGR in each category as of Jan 1, 2019. This bucket follows a "buy and hold" strategy with monthly SIPs.
- **Bucket 2 (Tool-based Selection)**: Initially selected the top-scoring fund using the "v4.0 Architecture" as of Jan 1, 2019. It uses monthly SIPs but includes a **2-quarter rebalancing rule**: If a fund fails any gate for two consecutive quarters, it is replaced by a fresh tool-based selection (no warnings).

### Categories (6 Funds)
1. Large Cap Index Fund (Passive)
2. Large Cap Active Fund
3. Large & Mid Cap Fund
4. Mid Cap Fund
5. Small Cap Fund
6. Flexi Cap Fund

### Tax Assumptions (User Specified)
- **STCG**: 20.0% (Holding period < 1 year)
- **LTCG**: 12.5% (Holding period > 1 year)
- SIP Amount: ₹10,000 per fund per month (Total ₹60,000/month per bucket)

---

## Performance Summary (Jan 2019 – Feb 2026)

| Metric | Bucket 1 (Best of 2019) | Bucket 2 (Tool-based) |
| :--- | :--- | :--- |
| **Total Invested (Out-of-Pocket)** | **₹5,220,000.00** | **₹5,220,000.00** |
| **Final Value (Pre-tax)** | **₹9,764,969.95** | **₹9,558,747.54** |
| **Final Value (Post-tax)** | **₹9,192,890.06** | **₹9,102,551.24** |
| **Absolute Return (%)** | **87.07%** | **83.12%** |
| **Post-tax Return (%)** | **76.11%** | **74.38%** |
| **Total Tax Paid (on Rebalance)** | ₹0.00 | ₹125,485.48 |

---

## Detailed Observations

### Bucket 1 Selections (Jan 2019)
- **Large Cap Index**: Taurus Nifty 50 Index Fund
- **Large Cap Active**: Mirae Asset Large Cap Fund
- **Large & MidCap**: Mirae Asset Large & Midcap Fund
- **Mid Cap**: DSP Midcap Fund
- **Small Cap**: Nippon India Small Cap Fund
- **Flexi Cap**: Aditya Birla Sun Life Flexi Cap Fund

### Bucket 2 Selections & Rebalancing
- **Initial Selection (Jan 2019)**:
    - Large Cap Index: Aditya Birla Sun Life Nifty 50 Index Fund
    - Large Cap Active: ICICI Prudential Large Cap Fund
    - Large & MidCap: Canara Robeco Large and Mid Cap Fund
    - Mid Cap: Franklin India Mid Cap Fund
    - Small Cap: Franklin India Small Cap Fund
    - Flexi Cap: Aditya Birla Sun Life Flexi Cap Fund
- **Rebalances**:
    - **Jun 2022 (Flexi Cap)**: Aditya Birla Sun Life Flexi Cap → quant Flexi Cap Fund.
    - **Jun 2025 (Large & MidCap)**: Canara Robeco Large and Mid Cap → Axis Large & Mid Cap Fund.
    - **Dec 2025 (Large & MidCap)**: Axis Large & Mid Cap Fund → Motilal Oswal Large and Midcap Fund.

## Conclusion
In this specific window (2019–2026), the **Best Performers of 2019** (Bucket 1) slightly outperformed the **Tool-based Strategy** (Bucket 2) by **1.73%** in post-tax terms. 

Bucket 2's performance was significantly impacted by the **₹125,485 tax bill** incurred during rebalancing. This highlights the "tax friction" of active portfolio management — a strategy must generate enough alpha to overcome the immediate tax outgo from switching funds.
