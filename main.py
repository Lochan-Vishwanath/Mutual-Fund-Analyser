# ─────────────────────────────────────────────────────────────────────────────
# main.py  —  CLI orchestrator for MF Master Plan v4.0
#   python main.py          → interactive, asks before sending email
#   python main.py --auto   → GitHub Actions mode, sends automatically
#   python main.py --dry    → run screening + save HTML, never send
# ─────────────────────────────────────────────────────────────────────────────

import sys
import json
import numpy as np
from datetime import date
from pathlib import Path
from screener import run_screening
from fetcher  import get_nifty_pe
from emailer  import build_html_email, send_email


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):  return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray):  return obj.tolist()
        return super().default(obj)


def _fmt_cagr(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val*100:.1f}%"

def _fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:.0%}"

def _fmt_f(val, decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:.{decimals}f}"


def run(send_mode: str = "ask"):
    """
    send_mode:
        "ask"  → print results, ask before sending
        "auto" → send automatically (GitHub Actions)
        "dry"  → never send, just save HTML and JSON
    """
    print("\n" + "=" * 65)
    print("  MF MASTER PLAN v4.0 — QUARTERLY SCREENING")
    print(f"  {date.today().strftime('%d %B %Y')}")
    print("=" * 65)

    out_dir  = Path("./output")
    out_dir.mkdir(exist_ok=True)
    prev_json = out_dir / "latest_results.json"

    prev_results = None
    if prev_json.exists():
        try:
            with open(prev_json) as f:
                prev_results = json.load(f)
            print("  Loaded previous run results for continuity comparison.")
        except Exception:
            print("  [WARN] Failed to load previous results — first run assumed.")

    results  = run_screening(previous_results=prev_results)
    nifty_pe = get_nifty_pe()

    if nifty_pe:
        print(f"\n  Nifty 50 P/E: {nifty_pe:.2f}x")
    else:
        print("\n  Nifty 50 P/E: unavailable")

    html      = build_html_email(results, nifty_pe)
    html_path = out_dir / f"report_{date.today().isoformat()}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n  HTML report → {html_path}")

    # ── Console summary ────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  SUMMARY OF QUALIFIED FUNDS")
    print("=" * 65)

    for cat, data in results.items():
        top         = data.get("top_funds", [])
        is_passive  = data.get("is_passive", False)
        rw          = data.get("rolling_window_years", 3)
        found       = data.get("total_found", 0)
        passed      = data.get("total_passed_phase2", 0)

        print(f"\n  [{cat}]  ({found} screened, {passed} qualified, {rw}yr rolling)")

        for i, f in enumerate(top, 1):
            sc   = f.get("total_score", 0)
            c5   = _fmt_cagr(f.get("cagr_5y"))
            cont = f.get("continuity_status", "")
            mflg = " ⚠️ MANAGER" if f.get("manager_flag") else ""
            bflg = " ⚡ BETA"    if f.get("beta_flag")   else ""
            pflg = " 🔄 PTR"     if f.get("ptr_flag")    else ""

            print(f"    #{i}: {f['name'][:58]} {cont}{mflg}{bflg}{pflg}")

            if is_passive:
                te = _fmt_f(f.get("tracking_error"), 4)
                print(f"         TE: {te}%  |  Score: {sc:.2f}/4.00  |  5Y CAGR: {c5}")
            else:
                rc  = _fmt_pct(f.get("rolling_consistency"))
                cr  = _fmt_f(f.get("capture_ratio"), 3)
                ir  = _fmt_f(f.get("info_ratio"))
                als = _fmt_f(f.get("alpha_stability"), 4)
                pct = f.get("rolling_category_percentile")
                pct_s = f"{pct:.0f}th pct" if pct is not None else "—"
                print(f"         Score: {sc:.2f}/4.00  |  RC: {rc} ({pct_s})  |  "
                      f"CaptureRatio: {cr}  |  IR: {ir}  |  αStability: {als}")
                print(f"         5Y CAGR: {c5}")

    # ── Send ───────────────────────────────────────────────────────────────
    if send_mode == "dry":
        print("\n  Dry run — email not sent.")
    elif send_mode == "auto":
        print("\n  Auto mode — sending email...")
        send_email(html)
    else:
        ans = input("\n  Send email to subscribers? (y/n): ").strip().lower()
        if ans == "y":
            send_email(html)
        else:
            print("  Email not sent.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--auto" in args:
        run("auto")
    elif "--dry" in args:
        run("dry")
    else:
        run("ask")
