# ─────────────────────────────────────────────────────────────────────────────
# emailer.py  —  Builds the HTML quarterly email and sends it.
#
# Shows top 3 funds per category with full metrics and rank badges.
# Also shows a summary of how many funds were screened and eliminated.
# ─────────────────────────────────────────────────────────────────────────────

import os
import smtplib
import numpy as np
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_SUBJECT, SUBSCRIBERS,
    PE_THRESHOLDS, TOP_N
)


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(val, fmt=".2f", pct=False, na="—"):
    """Format a metric value cleanly, returns na string if NaN/None."""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return na
    if pct:
        return f"{val:.1%}"
    return f"{val:{fmt}}"


def _indicator(val, good_threshold, bad_threshold=None, higher_is_better=True):
    """
    Returns a colour dot:
      🟢 clearly good,  🟡 borderline,  🔴 clearly bad,  ⚪ no data
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "⚪"
    if higher_is_better:
        if val >= good_threshold: return "🟢"
        if bad_threshold and val <= bad_threshold: return "🔴"
        return "🟡"
    else:
        if val <= good_threshold: return "🟢"
        if bad_threshold and val >= bad_threshold: return "🔴"
        return "🟡"


def _pe_signal(pe):
    if pe is None:
        return ("Data unavailable — check NSE manually", "#888888")
    if pe >= PE_THRESHOLDS["overvalued"]:
        return (f"🔴  OVERVALUED (P/E {pe:.1f}x) — Continue SIPs. No lump sum.", "#C00000")
    if pe >= PE_THRESHOLDS["fair_high"]:
        return (f"🟡  FAIR TO HIGH (P/E {pe:.1f}x) — Hold arbitrage buffer.", "#C05A00")
    if pe >= PE_THRESHOLDS["fair_value"]:
        return (f"🟢  FAIR VALUE (P/E {pe:.1f}x) — Deploy 25% of arbitrage buffer.", "#1A7A4A")
    if pe >= PE_THRESHOLDS["attractive"]:
        return (f"🟢  ATTRACTIVE (P/E {pe:.1f}x) — Deploy 75% of arbitrage buffer.", "#0A5A2A")
    return (f"🟢  DEEP VALUE (P/E {pe:.1f}x) — Deploy everything. Maximum aggression.", "#003300")


RANK_COLORS  = ["#C9A84C", "#9E9E9E", "#CD7F32"]   # Gold, Silver, Bronze
RANK_LABELS  = ["#1", "#2", "#3"]


# ─────────────────────────────────────────────────────────────────────────────
# Fund card builder
# ─────────────────────────────────────────────────────────────────────────────

def _metric_row(label, value_str, indicator="⚪"):
    return f"""
    <tr>
      <td style="padding:5px 14px;color:#555;font-size:13px;border-bottom:1px solid #f5f5f5;width:60%">{label}</td>
      <td style="padding:5px 14px;font-weight:600;font-size:13px;border-bottom:1px solid #f5f5f5;text-align:right">{value_str} {indicator}</td>
    </tr>"""


def _fund_card(fund: dict, rank: int, is_passive: bool) -> str:
    name  = fund.get("name", "—")
    code  = fund.get("code", "—")
    score = fund.get("total_score", 0)
    aum   = fund.get("aum")
    aum_s = f"₹{aum:,.0f} Cr" if aum and not np.isnan(aum) else "AUM unavailable"

    rank_color = RANK_COLORS[rank - 1] if rank <= 3 else "#555555"
    rank_label = RANK_LABELS[rank - 1] if rank <= 3 else f"#{rank}"

    if is_passive:
        te    = fund.get("tracking_error")
        c3    = fund.get("cagr_3y")
        c5    = fund.get("cagr_5y")
        sharpe = fund.get("sharpe")
        mdd   = fund.get("max_drawdown")
        rows  = (
            _metric_row("Tracking Error (lower = better)",
                        _f(te, ".4f") + "%",
                        _indicator(te, 0.001, 0.003, higher_is_better=False)) +
            _metric_row("3Y CAGR",   _f(c3, pct=True)) +
            _metric_row("5Y CAGR",   _f(c5, pct=True)) +
            _metric_row("Sharpe Ratio", _f(sharpe),
                        _indicator(sharpe, 1.0, 0.5)) +
            _metric_row("Max Drawdown",
                        _f(mdd, pct=True),
                        _indicator(mdd, -0.30, -0.50, higher_is_better=False))
        )
        verdict = f"Ranked by tracking error — lowest wins for passive"
    else:
        rc  = fund.get("rolling_consistency")
        so  = fund.get("sortino")
        ir  = fund.get("info_ratio")
        dc  = fund.get("down_capture")
        alp = fund.get("alpha")
        c5  = fund.get("cagr_5y")
        c10 = fund.get("cagr_10y")
        mdd = fund.get("max_drawdown")
        rows = (
            _metric_row("5Y Rolling Return Consistency",
                        _f(rc, pct=True),
                        _indicator(rc, 0.85, 0.65)) +
            _metric_row("Sortino Ratio",
                        _f(so),
                        _indicator(so, 2.0, 1.0)) +
            _metric_row("Information Ratio",
                        _f(ir),
                        _indicator(ir, 0.7, 0.3)) +
            _metric_row("Down Capture Ratio",
                        _f(dc, ".1f"),
                        _indicator(dc, 85, 100, higher_is_better=False)) +
            _metric_row("Alpha (annualised)",
                        _f(alp, pct=True),
                        _indicator(alp, 0.02, -0.01)) +
            _metric_row("5Y / 10Y CAGR",
                        f"{_f(c5, pct=True)} / {_f(c10, pct=True)}") +
            _metric_row("Max Drawdown",
                        _f(mdd, pct=True),
                        _indicator(mdd, -0.40, -0.60, higher_is_better=False))
        )
        verdict = f"Weighted Score: {score:.2f} / 4.00"

    return f"""
    <div style="margin-bottom:16px;border:1px solid #e0e8f0;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.07)">
      <div style="background:#1B3A6B;padding:12px 18px;display:flex;align-items:center;gap:12px">
        <div style="background:{rank_color};color:#fff;font-size:15px;font-weight:800;
                    width:34px;height:34px;border-radius:50%;display:inline-flex;
                    align-items:center;justify-content:center;flex-shrink:0;
                    line-height:34px;text-align:center">{rank_label}</div>
        <div style="flex:1">
          <div style="color:#fff;font-size:15px;font-weight:700;line-height:1.3">{name}</div>
          <div style="color:#aac4e8;font-size:12px;margin-top:2px">Code: {code} &nbsp;·&nbsp; {aum_s}</div>
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse">
        {rows}
      </table>
      <div style="background:#f0f8f4;padding:8px 18px;border-top:1px solid #e0e8f0">
        <span style="color:#1A7A4A;font-size:12px;font-weight:600">{verdict}</span>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Full email builder
# ─────────────────────────────────────────────────────────────────────────────

def build_html_email(results: dict, nifty_pe: float | None) -> str:
    quarter  = f"Q{(date.today().month - 1) // 3 + 1} {date.today().year}"
    run_date = date.today().strftime("%d %B %Y")
    pe_msg, pe_color = _pe_signal(nifty_pe)

    # Summary row
    total_screened  = sum(d["total_found"] for d in results.values())
    total_passed    = sum(d["total_passed_phase2"] for d in results.values())
    total_eliminated = total_screened - total_passed

    # Category sections
    category_sections = ""
    for category, data in results.items():
        top_funds    = data.get("top_funds", [])
        eliminated   = data.get("eliminated", [])
        is_passive   = data.get("is_passive", False)
        total_f      = data.get("total_found", 0)
        passed_f     = data.get("total_passed_phase2", 0)

        cards_html = ""
        if not top_funds:
            cards_html = f"""
            <div style="background:#fff3cd;border-left:4px solid #C05A00;padding:14px;border-radius:4px">
              No funds passed all criteria this quarter for <b>{category}</b>.
              Consider reviewing the candidate list or threshold settings.
            </div>"""
        else:
            for rank, fund in enumerate(top_funds, 1):
                cards_html += _fund_card(fund, rank, is_passive)

        # Eliminated summary (collapsed — just top 5 reasons)
        elim_rows = ""
        for f in eliminated[:8]:
            elim_rows += f"""
            <tr>
              <td style="padding:4px 8px;font-size:11px;color:#666;border-bottom:1px solid #f5f5f5;max-width:320px;overflow:hidden">{f.get('name','')[:55]}</td>
              <td style="padding:4px 8px;font-size:11px;color:#C05A00;border-bottom:1px solid #f5f5f5">{f.get('reason','')}</td>
            </tr>"""
        if len(eliminated) > 8:
            elim_rows += f"""
            <tr><td colspan="2" style="padding:4px 8px;font-size:11px;color:#888;font-style:italic">
              + {len(eliminated) - 8} more eliminated
            </td></tr>"""

        elim_section = ""
        if elim_rows:
            elim_section = f"""
            <details style="margin-top:8px">
              <summary style="cursor:pointer;font-size:12px;color:#888;padding:6px 0">
                ▸ {len(eliminated)} funds eliminated this quarter — click to expand
              </summary>
              <table style="width:100%;border-collapse:collapse;margin-top:8px">
                <tr style="background:#f5f5f5">
                  <th style="padding:4px 8px;font-size:11px;text-align:left;color:#555">Fund</th>
                  <th style="padding:4px 8px;font-size:11px;text-align:left;color:#555">Reason</th>
                </tr>
                {elim_rows}
              </table>
            </details>"""

        category_sections += f"""
        <div style="margin-bottom:32px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;
                      border-bottom:2px solid #1B3A6B;padding-bottom:8px">
            <h2 style="margin:0;font-size:18px;color:#1B3A6B;font-family:Arial,sans-serif">{category}</h2>
            <span style="font-size:12px;color:#888;margin-left:auto">
              {total_f} screened → {passed_f} qualified → Top {min(TOP_N, len(top_funds))} shown
            </span>
          </div>
          {cards_html}
          {elim_section}
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body {{ margin:0;padding:0;background:#edf2f7;font-family:Arial,Helvetica,sans-serif; }}
  details summary::-webkit-details-marker {{ display:none; }}
</style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#edf2f7;padding:20px 0">
<tr><td align="center">
<table width="660" cellpadding="0" cellspacing="0" style="max-width:660px;width:100%">

  <!-- ── HEADER ── -->
  <tr><td style="background:#1B3A6B;padding:28px 32px;border-radius:8px 8px 0 0">
    <div style="color:#aac4e8;font-size:11px;text-transform:uppercase;letter-spacing:2px;margin-bottom:6px">Mutual Fund Quarterly Review</div>
    <div style="color:#fff;font-size:24px;font-weight:700">{quarter} — Top {TOP_N} Funds Per Category</div>
    <div style="color:#aac4e8;font-size:12px;margin-top:6px">
      Generated: {run_date} &nbsp;·&nbsp; Strategy: MF Master Plan 2026
      &nbsp;·&nbsp; {total_screened} funds screened, {total_eliminated} eliminated
    </div>
  </td></tr>

  <!-- ── P/E SIGNAL ── -->
  <tr><td style="background:{pe_color};padding:13px 32px">
    <div style="color:#fff;font-size:13px;font-weight:600">Deployment Signal: {pe_msg}</div>
  </td></tr>

  <!-- ── INTRO ── -->
  <tr><td style="background:#fff;padding:18px 32px 4px;border-left:1px solid #dde5ef;border-right:1px solid #dde5ef">
    <p style="margin:0;color:#555;font-size:13px;line-height:1.7">
      Every Direct Growth fund in each SEBI category was screened. Phase 2 eliminated funds that were too young (&lt;{7}y history),
      outside AUM bounds, had rolling return consistency below 75%, or exceeded the category's down-capture threshold.
      Phase 3 ranked survivors using a weighted score: <b>35%</b> rolling consistency · <b>25%</b> Sortino ·
      <b>20%</b> information ratio · <b>10%</b> down capture · <b>10%</b> max drawdown.
    </p>
  </td></tr>

  <!-- ── CATEGORIES ── -->
  <tr><td style="background:#fff;padding:24px 32px;border-left:1px solid #dde5ef;border-right:1px solid #dde5ef">
    {category_sections}
  </td></tr>

  <!-- ── QUARTERLY REMINDERS ── -->
  <tr><td style="background:#f5f8fc;padding:18px 32px;border:1px solid #dde5ef">
    <div style="color:#1B3A6B;font-weight:700;font-size:13px;margin-bottom:8px">📌 Quarterly Checklist</div>
    <ul style="margin:0;padding-left:18px;color:#555;font-size:13px;line-height:2.0">
      <li>SIPs are on autopilot — never pause them regardless of market levels.</li>
      <li>Review your arbitrage fund balance vs. the deployment signal above.</li>
      <li>Check SEBI stress test results for any held small/mid-cap fund on the AMC website.</li>
      <li>If a held fund is no longer in the top 3, check against exit triggers before switching.</li>
      <li>In February: run LTCG tax harvesting — book gains below ₹1.25L to reset cost basis.</li>
    </ul>
  </td></tr>

  <!-- ── FOOTER ── -->
  <tr><td style="background:#1B3A6B;padding:16px 32px;border-radius:0 0 8px 8px;text-align:center">
    <div style="color:#aac4e8;font-size:11px;line-height:1.6">
      For personal use only. Not financial advice. Consult a SEBI-registered advisor for personalised guidance.<br>
      Data: mfapi.in · AMFI India · NSE India. All computations performed locally.
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
# Sender
# ─────────────────────────────────────────────────────────────────────────────

def send_email(html_body: str) -> None:
    password = EMAIL_PASSWORD or os.environ.get("MF_EMAIL_PASSWORD", "")
    if not password:
        raise ValueError(
            "Email password not set. Export MF_EMAIL_PASSWORD or set EMAIL_PASSWORD in config.py."
        )

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(SUBSCRIBERS)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, password)
        server.sendmail(EMAIL_SENDER, SUBSCRIBERS, msg.as_string())

    print(f"Email sent to {len(SUBSCRIBERS)} subscriber(s): {', '.join(SUBSCRIBERS)}")
