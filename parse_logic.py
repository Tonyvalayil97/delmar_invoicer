# parse_logic.py
# ----------------
# Stateless PDF parser used by the Streamlit app.
# Accepts raw PDF bytes (so it works with Streamlit's in-memory uploads).

import re
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, Optional

import pdfplumber


# ── headers expected by the Excel/DF ─────────────────────────
HEADERS = [
    "Timestamp", "Filename",
    "Invoice_Date", "Currency", "Shipper",
    "Weight_KG", "Volume_M3",
    "Chargeable_KG", "Chargeable_CBM",
    "Packages", "Subtotal",
    "Freight_Mode", "Freight_Amount",
]

# ── regex patterns (ported from your watcher script) ─────────
SHIPPER_PAT   = re.compile(r"SHIPPER\s+(.+?)\s+CONSIGNEE", re.I | re.S)
INVOICE_DATE  = re.compile(r"INVOICE\s+DATE\s+([0-9]{1,2}[A-Za-z\- ]+[0-9]{2,4})", re.I)

ROW_PAT = re.compile(
    r"([\d,.]+)\s*(KG|KGS?|LB)\s+"          # weight
    r"([\d,.]+)\s*(M3|CBM)\s+"              # volume
    r"([\d,.]+)\s*(KG|KGS?|LB|M3|CBM)\s+"   # chargeable any unit
    r"(\d+)\s*CTN", re.I)

KG_PAT  = re.compile(r"([\d,.]+)\s*KG", re.I)
M3_PAT  = re.compile(r"([\d,.]+)\s*(?:M3|CBM)", re.I)
CTN_PAT = re.compile(r"(\d+)\s*CTN", re.I)

CHARGEABLE_LINE = re.compile(
    r"CHARGEABLE\s+([\d,.]+)\s*(KG|KGS?|LB|M3|CBM)", re.I)

SUBTOTAL_PAT  = re.compile(r"SUBTOTAL\s+(?:([A-Z]{3})\s+)?([\d,.]+)", re.I)
AIR_FRT_PAT   = re.compile(r"AIR\s+FREIGHT\s+(?:([A-Z]{3})\s+)?([\d,]+\.\d{2})", re.I)
OCEAN_FRT_PAT = re.compile(r"(?:OCEAN|SEA)\s+FREIGHT\s+(?:([A-Z]{3})\s+)?([\d,]+\.\d{2})", re.I)

CURRENCY_ANY  = re.compile(r"\b(CAD|CDN|C\$)\b", re.I)


def _f(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    return float(str(s).replace(",", "").strip())


def _to_kg(val: float, unit: str) -> float:
    return val if unit.lower().startswith("kg") else val * 0.453592


def _extract_full_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def parse_pdf_bytes(pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Parse a single PDF (bytes) and return a row dict with the expected HEADERS.
    Never raises; on failure returns a minimal row with just Timestamp/Filename.
    """
    try:
        full = _extract_full_text(pdf_bytes)

        # Invoice date
        inv_date = None
        m = INVOICE_DATE.search(full)
        if m:
            inv_date = m.group(1).strip()

        # Currency (default USD, CAD heuristics preserved)
        currency = "USD"
        m = SUBTOTAL_PAT.search(full)
        if m and m.group(1):
            currency = m.group(1)
        else:
            m = AIR_FRT_PAT.search(full)
            if m and m.group(1):
                currency = m.group(1)
            else:
                m = OCEAN_FRT_PAT.search(full)
                if m and m.group(1):
                    currency = m.group(1)
                elif CURRENCY_ANY.search(full):
                    currency = "CAD"

        # Shipper
        shipper = None
        m = SHIPPER_PAT.search(full)
        if m:
            shipper = re.sub(r"\s+", " ", m.group(1).strip())

        # Defaults
        w_kg = v_m3 = c_kg = c_cbm = packs = subtotal = mode = amount = None

        # Detail row (weight, volume, chargeable, cartons)
        m = ROW_PAT.search(full)
        if m:
            w_val, w_unit, v_val, _, c_val, c_unit, packs = m.groups()
            w_kg  = _to_kg(_f(w_val), w_unit)
            v_m3  = _f(v_val)
            packs = int(packs)
            if c_unit.lower() in ("kg", "kgs", "lb"):
                c_kg  = _to_kg(_f(c_val), c_unit)
            else:
                c_cbm = _f(c_val)
        else:
            m = KG_PAT.search(full)
            if m: w_kg = _f(m.group(1))
            m = M3_PAT.search(full)
            if m: v_m3 = _f(m.group(1))
            m = CTN_PAT.search(full)
            if m: packs = int(m.group(1))

        # CHARGEABLE line override
        m = CHARGEABLE_LINE.search(full)
        if m:
            val, unit = m.groups()
            val = _f(val); unit = unit.lower()
            if unit in ("kg", "kgs", "lb"):
                c_kg, c_cbm = _to_kg(val, unit), None
            else:
                c_cbm, c_kg = val, None

        # Money
        m = SUBTOTAL_PAT.search(full)
        if m:
            subtotal = _f(m.group(2))

        for pat in (AIR_FRT_PAT, OCEAN_FRT_PAT):
            m = pat.search(full)
            if m:
                mode   = "Air" if pat is AIR_FRT_PAT else "Ocean"
                amount = _f(m.group(2))
                break

        return {
            "Timestamp"       : datetime.now(),
            "Filename"        : filename,
            "Invoice_Date"    : inv_date,
            "Currency"        : currency,
            "Shipper"         : shipper,
            "Weight_KG"       : w_kg,
            "Volume_M3"       : v_m3,
            "Chargeable_KG"   : c_kg,
            "Chargeable_CBM"  : c_cbm,
            "Packages"        : packs,
            "Subtotal"        : subtotal,
            "Freight_Mode"    : mode,
            "Freight_Amount"  : amount,
        }
    except Exception:
        # Return minimal row so the app can still proceed
        return {
            "Timestamp"       : datetime.now(),
            "Filename"        : filename,
            "Invoice_Date"    : None,
            "Currency"        : None,
            "Shipper"         : None,
            "Weight_KG"       : None,
            "Volume_M3"       : None,
            "Chargeable_KG"   : None,
            "Chargeable_CBM"  : None,
            "Packages"        : None,
            "Subtotal"        : None,
            "Freight_Mode"    : None,
            "Freight_Amount"  : None,
        }
