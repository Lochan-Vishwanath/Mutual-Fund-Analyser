from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# emailer.py  —  HTML quarterly report builder + SMTP sender for v4.0
#
# v4 Changes:
#   - Fund cards now show Capture Ratio (division-based) instead of separate
#     up/down capture in the scoring section
#   - Alpha Stability shown as a new metric row
#   - Manager change shows 2-signal breakdown (volatility shift + alpha flip)
#   - Phase 4 flags: PTR flag + Concentration flag added
#   - Score breakdown section updated to reflect 5-metric weighting
#   - TER shown as gate info, not a scoring weight
#   - Rolling window (3yr vs 5yr) shown per category
# ─────────────────────────────────────────────────────────────────────────────

import os
import smtplib
import numpy as np
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_SUBJECT, SUBSCRIBERS,
    PE_THRESHOLDS, TOP_N, SCORE_WEIGHTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(val, fmt=".2f", pct=False, na="—"):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return na
    if pct:
        return f"{val:.1%}"
    return f"{val:{fmt}}"


def _indicator(val, good_threshold, bad_threshold=None, higher_is_better=True):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "⚪"
    if higher_is_better:
        if val >= good_threshold:                      return "🟢"
        if bad_threshold and val <= bad_threshold:     return "🔴"
        return "🟡"
    else:
        if val <= good_threshold:                      return "🟢"
        if bad_threshold and val >= bad_threshold:     return "🔴"
        return "🟡"


def _pe_signal(pe):
    if pe is None:
        return ("Data unavailable — check NSE manually", "#888888")
    if pe >= PE_THRESHOLDS["overvalued"]:
        return (f"🔴 OVERVALUED (P/E {pe:.1f}x) — SIPs only. No lump sum.", "#C00000")
    if pe >= PE_THRESHOLDS["fair_high"]:
        return (f"🟡 FAIR TO HIGH (P/E {pe:.1f}x) — Hold arbitrage buffer.", "#C05A00")
    if pe >= PE_THRESHOLDS["fair_value"]:
        return (f"🟢 FAIR VALUE (P/E {pe:.1f}x) — Deploy 25% of buffer.", "#1A7A4A")
    if pe >= PE_THRESHOLDS["attractive"]:
        return (f"🟢 ATTRACTIVE (P/E {pe:.1f}x) — Deploy 75% of buffer.", "#0A5A2A")
    return (f"🟢 DEEP VALUE (P/E {pe:.1f}x) — Deploy everything.", "#003300")


RANK_COLORS = ["#C9A84C", "#9E9E9E", "#CD7F32"]
RANK_LABELS = ["#1", "#2", "#3"]


# ─────────────────────────────────────────────────────────────────────────────
# Card sub-components
# ─────────────────────────────────────────────────────────────────────────────

def _metric_row(label, value_str, indicator="⚪", highlight=False):
    bg = "#fffbeb" if highlight else "transparent"
    return f"""
    <tr style="background:{bg}">
      <td style="padding:5px 14px;color:#555;font-size:13px;border-bottom:1px solid #f5f5f5;width:58%">{label}</td>
      <td style="padding:5px 14px;font-weight:600;font-size:13px;border-bottom:1px solid #f5f5f5;text-align:right">{value_str} {indicator}</td>
    </tr>"""


def _flag_row(msg: str, color: str = "#C05A00") -> str:
    return f"""
    <tr>
      <td colspan="2" style="padding:6px 14px;font-size:12px;color:{color};
                             border-bottom:1px solid #f5f5f5;background:#fffbeb">
        ⚠️ {msg}
      </td>
    </tr>"""


def _continuity_badge(status):
    if not status or status == "—":
        return ""
    color = "#1A7A4A" if "Holdover" in status else "#997A00"
    label = status.replace("🛡️", "").replace("🌟", "").strip()
    return (f'<span style="background:{color};color:#fff;font-size:10px;font-weight:700;'
            f'padding:2px 7px;border-radius:4px;vertical-align:middle;margin-left:6px">{status}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Fund card builder
# ─────────────────────────────────────────────────────────────────────────────

def _fund_card(fund: dict, rank: int, is_passive: bool, rolling_window_years: int = 3) -> str:
    name       = fund.get("name", "—")
    code       = fund.get("code", "—")
    score      = fund.get("total_score", 0)
    aum        = fund.get("aum")
    aum_s      = f"₹{aum:,.0f} Cr" if aum and not (isinstance(aum, float) and np.isnan(aum)) else "AUM unavailable"
    cont_badge = _continuity_badge(fund.get("continuity_status"))

    rank_color = RANK_COLORS[rank - 1] if rank <= 3 else "#555555"
    rank_label = RANK_LABELS[rank - 1] if rank <= 3 else f"#{rank}"

    # Flags
    flags_html = ""
    if fund.get("manager_flag"):
        reason = fund.get("manager_flag_reason", "Potential manager change detected")
        flags_html += _flag_row(f"MANAGER CHANGE SIGNAL: {reason}")
    if fund.get("beta_flag"):
        flags_html += _flag_row(fund.get("beta_flag_reason", "High Beta detected"), "#1B3A6B")
    if fund.get("ptr_flag"):
        flags_html += _flag_row(fund.get("ptr_flag_reason", "High portfolio turnover"), "#6B1B1B")
    if fund.get("concentration_flag"):
        flags_html += _flag_row(fund.get("concentration_flag_reason", "High portfolio concentration"), "#4B1B6B")

    # Continuity description
    cont_desc = fund.get("continuity_desc", "")
    cont_html = ""
    if cont_desc:
        cont_html = f"""
        <tr>
          <td colspan="2" style="padding:6px 14px;font-size:12px;color:#1A5A3A;
                                 background:#eafaf1;border-bottom:1px solid #f5f5f5">
            {fund.get("continuity_status", "")} {cont_desc}
          </td>
        </tr>"""

    if is_passive:
        te     = fund.get("tracking_error")
        c3     = fund.get("cagr_3y")
        c5     = fund.get("cagr_5y")
        sharpe = fund.get("sharpe")
        mdd    = fund.get("max_drawdown")
        ter    = fund.get("ter")

        rows = (
            _metric_row("Tracking Error % (lower = better)",
                        _f(te, ".4f") + "%",
                        _indicator(te, 0.001, 0.005, higher_is_better=False),
                        highlight=True) +
            _metric_row("3Y CAGR",      _f(c3, pct=True)) +
            _metric_row("5Y CAGR",      _f(c5, pct=True)) +
            _metric_row("Sharpe Ratio", _f(sharpe), _indicator(sharpe, 1.0, 0.5)) +
            _metric_row("Max Drawdown", _f(mdd, pct=True),
                        _indicator(mdd, -0.30, -0.50, higher_is_better=False)) +
            _metric_row("Expense Ratio (TER)",
                        _f(ter) + "%" if ter else "—",
                        _indicator(ter, 0.10, 0.30, higher_is_better=False) if ter else "⚪",
                        highlight=True)
        )
        verdict = f"Passive Score: TE×70% + TER×30% = {score:.2f}/4.00"

    else:
        rc   = fund.get("rolling_consistency")
        pct  = fund.get("rolling_category_percentile")
        cr   = fund.get("capture_ratio")
        uc   = fund.get("up_capture")
        dc   = fund.get("down_capture")
        so   = fund.get("sortino")
        ir   = fund.get("info_ratio")
        als  = fund.get("alpha_stability")
        alp  = fund.get("alpha")
        c5   = fund.get("cagr_5y")
        c10  = fund.get("cagr_10y")
        mdd  = fund.get("max_drawdown")
        ter  = fund.get("ter")
        beta = fund.get("beta")

        pct_str = f"{pct:.0f}th percentile vs peers" if pct is not None else "—"
        rw_label = f"{rolling_window_years}yr rolling windows"

        rows = (
            _metric_row(f"Rolling Consistency [{rw_label}] — {pct_str}",
                        _f(rc, pct=True),
                        _indicator(rc, 0.70, 0.55),
                        highlight=True) +
            _metric_row("Capture Ratio (Upside÷Downside)",
                        _f(cr, ".3f"),
                        _indicator(cr, 1.10, 1.0),
                        highlight=True) +
            _metric_row("  ↳ Upside Capture (context)",
                        _f(uc, ".1f"),
                        _indicator(uc, 105, 85)) +
            _metric_row("  ↳ Downside Capture (context)",
                        _f(dc, ".1f"),
                        _indicator(dc, 85, 105, higher_is_better=False)) +
            _metric_row("Sortino Ratio",
                        _f(so),
                        _indicator(so, 2.0, 1.0)) +
            _metric_row("Information Ratio (manager skill)",
                        _f(ir),
                        _indicator(ir, 0.7, 0.3),
                        highlight=True) +
            _metric_row("Alpha Stability (rolling α stddev — lower = better)",
                        _f(als, ".4f"),
                        _indicator(als, 0.03, 0.08, higher_is_better=False)) +
            _metric_row("Alpha (annualised Jensen)",
                        _f(alp, pct=True),
                        _indicator(alp, 0.02, -0.01)) +
            _metric_row(f"5Y / 10Y CAGR",
                        f"{_f(c5, pct=True)} / {_f(c10, pct=True)}") +
            _metric_row("Max Drawdown",
                        _f(mdd, pct=True),
                        _indicator(mdd, -0.40, -0.60, higher_is_better=False)) +
            _metric_row("Beta",
                        _f(beta),
                        _indicator(beta, 1.0, 1.3, higher_is_better=False) if beta else "⚪") +
            _metric_row("Expense Ratio (TER — gate, not score)",
                        _f(ter) + "%" if ter else "—",
                        _indicator(ter, 0.50, 0.85, higher_is_better=False) if ter else "⚪")
        )
        verdict = f"Active Score: {score:.2f} / 4.00 (IR×25% + RC×22% + Capture×20% + Sortino×18% + αStability×15%)"

    return f"""
    <div style="margin-bottom:16px;border:1px solid #e0e8f0;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.07)">
      <div style="background:#1B3A6B;padding:12px 18px;display:flex;align-items:center;gap:12px">
        <div style="background:{rank_color};color:#fff;font-size:15px;font-weight:800;
                    width:34px;height:34px;border-radius:50%;display:inline-flex;
                    align-items:center;justify-content:center;flex-shrink:0">{rank_label}</div>
        <div style="flex:1">
          <div style="color:#fff;font-size:15px;font-weight:700;line-height:1.3">{name} {cont_badge}</div>
          <div style="color:#aac4e8;font-size:12px;margin-top:2px">Code: {code} &nbsp;·&nbsp; {aum_s}</div>
        </div>
        <div style="color:#aac4e8;font-size:12px;text-align:right;flex-shrink:0">{verdict}</div>
      </div>
      <table style="width:100%;border-collapse:collapse">
        {flags_html}
        {cont_html}
        {rows}
      </table>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Category section builder
# ─────────────────────────────────────────────────────────────────────────────

def _category_avg_row(avg: dict, is_passive: bool, rolling_window_years: int = 3) -> str:
    if not avg:
        return ""
    if is_passive:
        return f"""
        <tr style="background:#f0f4fa;font-style:italic">
          <td colspan="8" style="padding:6px 14px;font-size:12px;color:#555">
            📊 Category Average — TE: {_f(avg.get("tracking_error"), ".4f")}% &nbsp;·&nbsp;
            TER: {_f(avg.get("ter"))}%
          </td>
        </tr>"""
    rw = f"{rolling_window_years}yr"
    return f"""
    <div style="background:#f0f4fa;border:1px solid #d0ddf0;border-radius:6px;
                padding:8px 14px;font-size:12px;color:#445;margin-bottom:16px">
      📊 <strong>Category Peer Averages</strong> &nbsp;·&nbsp;
      Rolling Consistency [{rw}]: <strong>{_f(avg.get("rolling_consistency"), pct=True)}</strong> &nbsp;·&nbsp;
      Capture Ratio: <strong>{_f(avg.get("capture_ratio"), ".3f")}</strong> &nbsp;·&nbsp;
      Sortino: <strong>{_f(avg.get("sortino"))}</strong> &nbsp;·&nbsp;
      Info Ratio: <strong>{_f(avg.get("info_ratio"))}</strong> &nbsp;·&nbsp;
      5Y CAGR: <strong>{_f(avg.get("cagr_5y"), pct=True)}</strong>
    </div>"""


def _category_section(category: str, data: dict) -> str:
    top_funds    = data.get("top_funds", [])
    eliminated   = data.get("eliminated", [])
    is_passive   = data.get("is_passive", False)
    cat_avg      = data.get("category_avg", {})
    total_found  = data.get("total_found", 0)
    total_passed = data.get("total_passed_phase2", 0)
    rw_years     = data.get("rolling_window_years", 3)
    cons_floor   = data.get("consistency_floor", 0.55)

    strategy_label = "PASSIVE — ranked by Tracking Error" if is_passive else f"ACTIVE — {rw_years}yr rolling windows, consistency floor ≥{cons_floor:.0%}"
    header_style   = "background:#2C5F8A" if is_passive else "background:#1B3A6B"

    cards = "".join(_fund_card(f, i + 1, is_passive, rw_years) for i, f in enumerate(top_funds))
    avg_row = _category_avg_row(cat_avg, is_passive, rw_years)

    elim_rows = ""
    if eliminated:
        rows_html = "".join(
            f"""<tr>
              <td style="padding:4px 10px;font-size:12px;border-bottom:1px solid #eee">{e.get("name","")[:60]}</td>
              <td style="padding:4px 10px;font-size:12px;color:#888;border-bottom:1px solid #eee">{e.get("reason","")}</td>
            </tr>"""
            for e in eliminated[:20]   # Cap at 20 to keep email size reasonable
        )
        elim_html = f"""
        <details style="margin-top:8px">
          <summary style="cursor:pointer;font-size:12px;color:#888">
            ❌ {len(eliminated)} funds eliminated (click to expand)
          </summary>
          <table style="width:100%;border-collapse:collapse;margin-top:6px">
            <tr style="background:#f9f9f9">
              <th style="padding:4px 10px;font-size:11px;text-align:left;color:#666">Fund</th>
              <th style="padding:4px 10px;font-size:11px;text-align:left;color:#666">Reason</th>
            </tr>
            {rows_html}
          </table>
        </details>"""
    else:
        elim_html = ""

    no_funds_msg = ""
    if not top_funds:
        no_funds_msg = """
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px;
                    font-size:13px;color:#856404">
          ⚠️ No funds passed all gates for this category this quarter.
          Review eliminated funds below and consider relaxing thresholds in config.py if needed.
        </div>"""

    return f"""
    <div style="margin-bottom:32px">
      <div style="{header_style};color:#fff;padding:10px 18px;border-radius:6px 6px 0 0">
        <strong style="font-size:16px">{category}</strong>
        <span style="font-size:11px;opacity:0.8;margin-left:12px">{strategy_label}</span>
        <span style="font-size:11px;opacity:0.7;float:right">{total_found} screened · {total_passed} qualified</span>
      </div>
      <div style="border:1px solid #d0ddf0;border-top:none;border-radius:0 0 6px 6px;padding:16px">
        {no_funds_msg}
        {avg_row}
        {cards}
        {elim_html}
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Full email HTML builder
# ─────────────────────────────────────────────────────────────────────────────

def build_html_email(results: dict, nifty_pe: float = None) -> str:
    today      = date.today().strftime("%d %B %Y")
    pe_msg, pe_color = _pe_signal(nifty_pe)

    total_screened = sum(cat.get("total_found", 0)          for cat in results.values())
    total_passed   = sum(cat.get("total_passed_phase2", 0)  for cat in results.values())

    # Separate Large Cap for side-by-side view
    lc_active  = results.get("Large Cap (Active)")
    lc_passive = results.get("Large Cap (Passive)")
    other_cats = {k: v for k, v in results.items()
                  if k not in ("Large Cap (Active)", "Large Cap (Passive)")}

    # Build Large Cap section
    lc_html = ""
    if lc_active or lc_passive:
        act_section  = _category_section("Large Cap (Active)", lc_active)  if lc_active  else ""
        pass_section = _category_section("Large Cap (Passive)", lc_passive) if lc_passive else ""
        lc_html = f"""
        <h2 style="color:#1B3A6B;border-bottom:2px solid #1B3A6B;padding-bottom:6px;margin-top:28px">
          ⚔️ Large Cap: Active vs Passive
        </h2>
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="width:50%;vertical-align:top;padding-right:10px">{act_section}</td>
            <td style="width:50%;vertical-align:top;padding-left:10px">{pass_section}</td>
          </tr>
        </table>"""

    # Build other categories
    other_html = ""
    for cat, data in other_cats.items():
        other_html += _category_section(cat, data)

    methodology_html = f"""
    <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:18px;margin-top:28px">
      <h3 style="color:#1B3A6B;margin-top:0">📐 Methodology — v4.0 Architecture</h3>
      
      <p style="font-size:13px;color:#555;margin:4px 0">
        <strong>Active/Passive Fork:</strong> Index funds score purely on Tracking Error (70%) + TER (30%).
        Active funds go through the full 4-phase pipeline below.
      </p>
      
      <p style="font-size:13px;color:#555;margin:8px 0 4px 0"><strong>Phase 1 — Hard Filters:</strong></p>
      <ul style="font-size:12px;color:#666;margin:0 0 8px 16px">
        <li>History: ≥5yr (Large/Flexi) or ≥7yr (Mid/Small Cap)</li>
        <li>AUM: Category-specific min/max (e.g. Small Cap max ₹15,000Cr; Flexi Cap no max)</li>
      </ul>
      
      <p style="font-size:13px;color:#555;margin:8px 0 4px 0"><strong>Phase 2 — Dynamic Gates (category-relative):</strong></p>
      <ul style="font-size:12px;color:#666;margin:0 0 8px 16px">
        <li>Sharpe Ratio > 0 (fund must justify equity risk over T-bills)</li>
        <li>TER ≤ category median + 0.3% (gate replaces old 5% scoring weight)</li>
        <li>Rolling Consistency ≥ 55–60% AND above category median</li>
        <li>Capital Protection: negative windows ≤ 10%</li>
        <li>Capture Ratio (Upside÷Downside) > 1.0 AND above category median</li>
      </ul>
      
      <p style="font-size:13px;color:#555;margin:8px 0 4px 0"><strong>Phase 3 — Scoring (5 non-collinear dimensions):</strong></p>
      <ul style="font-size:12px;color:#666;margin:0 0 8px 16px">
        <li>Information Ratio — 25% (manager skill: consistent alpha per unit active risk)</li>
        <li>Rolling Consistency — 22% (process vs luck: % windows beating benchmark)</li>
        <li>Capture Ratio (÷) — 20% (asymmetry quality: gains more than it loses)</li>
        <li>Sortino Ratio — 18% (return per unit of downside volatility only)</li>
        <li>Alpha Stability — 15% (rolling alpha std dev: lower = more consistent)</li>
      </ul>
      
      <p style="font-size:13px;color:#555;margin:8px 0 4px 0"><strong>Phase 4 — Qualitative Flags (manual verification):</strong></p>
      <ul style="font-size:12px;color:#666;margin:0 0 4px 16px">
        <li>⚠️ Manager Change: volatility signature shift + alpha sign flip signals</li>
        <li>⚡ High Beta (&gt;1.3): fund amplifies market moves significantly</li>
        <li>🔄 High PTR: portfolio turnover &gt;1.5 SD above category median</li>
        <li>🛡️ Holdover / 🌟 New Entrant continuity rule (tax + exit load aware)</li>
      </ul>
      
      <p style="font-size:11px;color:#888;margin:8px 0 0 0">
        Rolling windows: 3yr for Large/Flexi Cap · 5yr for Mid/Small Cap (matches cycle length).
        Capture Ratio uses Upside÷Downside (division, not subtraction) to correctly penalise 
        high-volatility funds with the same spread as conservative ones.
      </p>
    </div>"""

    checklist_html = """
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:18px;margin-top:16px">
      <h3 style="color:#856404;margin-top:0">✅ Manual Verification Checklist (New Entrants 🌟)</h3>
      <ol style="font-size:12px;color:#666;margin:0;padding-left:18px">
        <li><strong>Fund Manager Tenure:</strong> Still the same manager who built the track record? (Check AMC website / MFI Explorer)</li>
        <li><strong>AUM Trajectory:</strong> Has AUM doubled recently? Could force mandate drift in Mid/Small cap.</li>
        <li><strong>Sector Concentration:</strong> No single sector &gt;35% of portfolio.</li>
        <li><strong>Portfolio P/E:</strong> Compare fund P/E vs benchmark P/E — gap &gt;30% = style drift risk.</li>
        <li><strong>SEBI Stress Test (Mid/Small):</strong> Check days to liquidate 50% of portfolio on SEBI portal.</li>
        <li><strong>Switching Cost:</strong> Calculate Exit Load + LTCG (10% above ₹1L gains) / STCG (15%) before any switch.</li>
        <li><strong>2-Quarter Rule:</strong> Only exit a Holdover if it fails a gate for 2 consecutive quarters — not just a rank drop.</li>
      </ol>
    </div>"""

    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #222; margin: 0; padding: 0; background: #f4f6f9; }}
  .wrapper {{ max-width: 860px; margin: 0 auto; background: #fff; }}
  .header  {{ background: linear-gradient(135deg, #1B3A6B 0%, #2C5F8A 100%); padding: 28px 32px; }}
  .content {{ padding: 24px 32px 32px 32px; }}
  h2 {{ font-size: 18px; }}
</style>
</head><body>
<div class="wrapper">
  <div class="header">
    <h1 style="margin:0;color:#fff;font-size:22px">📈 MF Master Plan — Quarterly Review</h1>
    <p style="margin:6px 0 0 0;color:#aac4e8;font-size:14px">
      {today} &nbsp;·&nbsp; {total_screened} funds screened &nbsp;·&nbsp; {total_passed} qualified
    </p>
  </div>
  
  <div class="content">
    <div style="background:{pe_color}18;border-left:4px solid {pe_color};
                padding:12px 16px;border-radius:4px;margin-bottom:20px;font-size:14px">
      <strong>Deployment Signal:</strong> {pe_msg}
    </div>
    
    {lc_html}
    
    {"<h2 style='color:#1B3A6B;border-bottom:2px solid #1B3A6B;padding-bottom:6px;margin-top:28px'>🧠 Active Funds</h2>" if other_cats else ""}
    {other_html}
    
    {methodology_html}
    {checklist_html}
    
    <p style="font-size:11px;color:#aaa;margin-top:20px;text-align:center">
      Generated by MF Master Plan v4.0 · Data: mfapi.in + AMFI India ·
      This is not financial advice. Always verify with a SEBI-registered advisor.
    </p>
  </div>
</div>
</body></html>"""

    return body


# ─────────────────────────────────────────────────────────────────────────────
# SMTP Sender
# ─────────────────────────────────────────────────────────────────────────────

def send_email(html: str) -> None:
    """Send the HTML report to all subscribers via Gmail SMTP."""
    if not EMAIL_PASSWORD:
        raise ValueError("EMAIL_PASSWORD not set in .env — run python check_env.py to diagnose")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{EMAIL_SUBJECT} — {date.today().strftime('%d %b %Y')}"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(SUBSCRIBERS)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, SUBSCRIBERS, msg.as_string())
        print(f"  ✉️  Email sent to {len(SUBSCRIBERS)} subscriber(s)")
