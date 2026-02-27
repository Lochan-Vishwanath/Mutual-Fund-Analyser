# ─────────────────────────────────────────────────────────────────────────────
# fetcher.py  —  Data layer.
#
# Key addition vs. v1: get_all_direct_growth_funds_by_category()
# This parses AMFI's NAVAll.txt to extract every Direct Growth fund
# in a given SEBI category — no manual candidate list needed.
#
# AMFI NAVAll.txt structure:
#   Open Ended Schemes(Equity Scheme - Large Cap Fund)    ← section header
#   <blank line>
#   AMC Name
#   Scheme Code;ISIN1;ISIN2;Scheme Name;NAV;Repurchase;Sale;Date
#   119552;...;Aditya Birla Sun Life Frontline Equity Fund - Direct Plan-Growth;531.11;...
#   ...
#   (repeat for each AMC block, then next section header)
# ─────────────────────────────────────────────────────────────────────────────

import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

MFAPI_BASE   = "https://api.mfapi.in/mf"
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

NAV_CACHE_HOURS    = 12    # re-fetch NAV history if older than this
SCHEME_CACHE_HOURS = 24    # re-fetch AMFI master if older than this
FETCH_DELAY        = 0.25  # seconds between mfapi.in calls — be polite


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"

def _txt_cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.txt"

def _is_fresh(path: Path, max_hours: float) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=max_hours)

def _is_direct_growth(name: str) -> bool:
    """
    Returns True only for Direct Plan Growth schemes.
    Filters out: Regular plans, IDCW/Dividend plans, FoFs, ETFs.
    """
    n = name.lower()
    if "direct" not in n:
        return False
    # Must have growth signal
    if not any(g in n for g in ["growth", "gr", "-g"]):
        return False
    # Exclude dividend/IDCW
    if any(d in n for d in ["idcw", "dividend", "div payout", "reinvest", "bonus"]):
        return False
    # Exclude FoF and ETF
    if any(e in n for e in ["fund of fund", "fof", " etf", "exchange traded"]):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# AMFI category → scheme list
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_amfi_raw() -> str:
    """Fetch or return cached AMFI NAVAll.txt content."""
    cache = _txt_cache_path("amfi_navall")
    if _is_fresh(cache, SCHEME_CACHE_HOURS):
        return cache.read_text(encoding="utf-8", errors="replace")
    resp = requests.get(AMFI_NAV_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text
    cache.write_text(text, encoding="utf-8")
    return text


def _build_category_map(amfi_text: str) -> dict[str, list[dict]]:
    """
    Parses NAVAll.txt and returns:
      {
        "Equity Scheme - Large Cap Fund": [
            {"code": "119552", "name": "Aditya Birla Sun Life Frontline Equity..."},
            ...
        ],
        ...
      }
    Only Direct Growth schemes are included.
    """
    category_map: dict[str, list[dict]] = {}
    current_category = None

    for raw_line in amfi_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Section header: "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
        # or "Close Ended Schemes(...)" — we only care about Open Ended
        if line.startswith("Open Ended Schemes(") or line.startswith("Interval Fund("):
            # Extract the category label between the first ( and last )
            start = line.find("(")
            end   = line.rfind(")")
            if start != -1 and end != -1:
                current_category = line[start + 1: end].strip()
            continue

        if line.startswith("Close Ended Schemes("):
            current_category = None   # skip all close-ended
            continue

        # AMC name lines and header rows — skip
        if current_category is None:
            continue
        if line.startswith("Scheme Code;"):
            continue

        # Data rows: Code;ISIN1;ISIN2;Name;NAV;Repurchase;Sale;Date
        parts = line.split(";")
        if len(parts) < 4:
            continue
        code = parts[0].strip()
        if not code.isdigit():
            continue   # AMC name row or garbage

        name = parts[3].strip()
        if _is_direct_growth(name):
            category_map.setdefault(current_category, []).append({
                "code": code,
                "name": name,
            })

    return category_map


def get_all_direct_growth_funds_by_category(
    amfi_category_keywords: list[str],
    name_must_contain: list[str] = None,
) -> list[dict]:
    """
    Returns list of {code, name} dicts for all Direct Growth funds
    whose AMFI category header matches any of the given keywords (case-insensitive).

    name_must_contain: optional extra name filter (e.g. ["nifty 50"] for index funds).
    """
    amfi_text   = _fetch_amfi_raw()
    category_map = _build_category_map(amfi_text)

    funds = []
    keywords_lower = [k.lower() for k in amfi_category_keywords]

    for cat_label, cat_funds in category_map.items():
        cat_lower = cat_label.lower()
        if any(kw in cat_lower for kw in keywords_lower):
            funds.extend(cat_funds)

    # Deduplicate by code
    seen = set()
    unique = []
    for f in funds:
        if f["code"] not in seen:
            seen.add(f["code"])
            unique.append(f)

    # Optional: filter by fund name keywords
    if name_must_contain:
        name_filters = [n.lower() for n in name_must_contain]
        unique = [
            f for f in unique
            if any(nf in f["name"].lower() for nf in name_filters)
        ]

    return unique


# ─────────────────────────────────────────────────────────────────────────────
# NAV history
# ─────────────────────────────────────────────────────────────────────────────

def get_nav_history(scheme_code: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch full NAV history for a scheme.
    Returns DataFrame: date (datetime), nav (float), sorted oldest→newest.
    """
    cache = _cache_path(str(scheme_code))

    if not force_refresh and _is_fresh(cache, NAV_CACHE_HOURS):
        with open(cache) as f:
            data = json.load(f)
    else:
        resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        with open(cache, "w") as f:
            json.dump(data, f)
        time.sleep(FETCH_DELAY)

    records = data.get("data", [])
    if not records:
        raise ValueError(f"No NAV data for scheme {scheme_code}")

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"]  = df["nav"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "nav"]]


def get_scheme_name(scheme_code: str) -> str:
    cache = _cache_path(str(scheme_code))
    if cache.exists():
        with open(cache) as f:
            return json.load(f).get("meta", {}).get("scheme_name", str(scheme_code))
    return str(scheme_code)


# ─────────────────────────────────────────────────────────────────────────────
# Nifty P/E
# ─────────────────────────────────────────────────────────────────────────────

def get_nifty_pe() -> float | None:
    """Fetch latest Nifty 50 trailing P/E from niftyindices.com."""
    try:
        url = "https://www.niftyindices.com/Backpage.aspx/getPEPBDividenByIndexName"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Referer":       "https://www.niftyindices.com/",
        }
        r = requests.post(
            url,
            json={"indexName": "NIFTY 50", "indexType": "pricereturn"},
            headers=headers,
            timeout=10,
        )
        rows = r.json().get("d", [])
        if rows:
            latest = sorted(rows, key=lambda x: x.get("Date", ""))[-1]
            val = float(latest.get("pe", 0))
            if val:
                # Cache it
                pe_cache = CACHE_DIR / "nifty_pe.json"
                pe_cache.write_text(json.dumps({"pe": val, "ts": datetime.now().isoformat()}))
                return val
    except Exception:
        pass

    # Fallback: return cached value if within 7 days
    pe_cache = CACHE_DIR / "nifty_pe.json"
    if _is_fresh(pe_cache, max_hours=168):
        return json.loads(pe_cache.read_text()).get("pe")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# AUM map
# ─────────────────────────────────────────────────────────────────────────────

def get_amfi_aum_map() -> dict[str, float]:
    """
    Returns {scheme_code: aum_crores} parsed from AMFI NAVAll.txt.
    Note: NAVAll.txt has the latest NAV and some supplementary columns.
    Full AUM requires AMFI's separate AUM report; this is a best-effort proxy.
    """
    aum_cache = _cache_path("amfi_aum")
    if _is_fresh(aum_cache, SCHEME_CACHE_HOURS):
        with open(aum_cache) as f:
            return json.load(f)

    aum_map: dict[str, float] = {}
    try:
        # AMFI publishes a monthly AUM JSON at this endpoint
        url = "https://www.amfiindia.com/modules/AumNav"
        r = requests.get(url, timeout=20)
        for line in r.text.splitlines():
            parts = line.strip().split(";")
            if len(parts) >= 6 and parts[0].strip().isdigit():
                try:
                    code = parts[0].strip()
                    raw  = parts[5].strip().replace(",", "")
                    aum_map[code] = float(raw) if raw else 0.0
                except (ValueError, IndexError):
                    pass
    except Exception as e:
        print(f"[WARN] AUM fetch failed: {e}. AUM gate will be skipped for this run.")

    if aum_map:
        with open(aum_cache, "w") as f:
            json.dump(aum_map, f)

    return aum_map


# ─────────────────────────────────────────────────────────────────────────────
# Search utility (used by utils.py CLI)
# ─────────────────────────────────────────────────────────────────────────────

def search_scheme(query: str, top_n: int = 15) -> list[dict]:
    """Find scheme codes by name. Used to verify benchmark codes."""
    all_cache = _cache_path("all_schemes")
    if not _is_fresh(all_cache, SCHEME_CACHE_HOURS):
        r = requests.get(MFAPI_BASE, timeout=30)
        r.raise_for_status()
        data = r.json()
        with open(all_cache, "w") as f:
            json.dump(data, f)
    else:
        with open(all_cache) as f:
            data = json.load(f)

    q = query.lower()
    matches = [s for s in data if q in s.get("schemeName", "").lower()]
    return matches[:top_n]
