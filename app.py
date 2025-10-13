# app.py
# -------
# Streamlit UI to upload multiple invoice PDFs, parse them, preview the table,
# and download a single Excel file (one sheet) with a header row.

import io
from datetime import datetime

import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

from parse_logic import parse_pdf_bytes, HEADERS


st.set_page_config(page_title="Invoice Processor – Freight A→Z", layout="wide")
st.title("📦 Invoice Processor – Freight A→Z")
st.caption("Invoice Date · CAD aware · kg/cbm chargeable (multi-PDF uploader)")

with st.expander("How it works", expanded=False):
    st.markdown(
        "- Upload one or more **PDF** invoices.\n"
        "- The app parses weights, volume, chargeable (KG/CBM), cartons, currency, subtotal, and freight lines (Air/Ocean).\n"
        "- Review the extracted table.\n"
        "- Click **Download Excel** to export `Invoice_Summary.xlsx`."
    )

uploaded = st.file_uploader("Upload invoice PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded:
    rows = []
    log  = []

    with st.spinner("Parsing invoices..."):
        for f in uploaded:
            try:
                data = f.read()
                row  = parse_pdf_bytes(data, filename=f.name)
                rows.append(row)

                # Build a friendly log line
                log.append(
                    f"✓ {row.get('Filename','')} | "
                    f"{row.get('Invoice_Date') or '—'} | "
                    f"{row.get('Currency') or '—'} | "
                    f"{row.get('Freight_Mode') or '—'} "
                    f"{('(' + str(row.get('Freight_Amount')) + ')') if row.get('Freight_Amount') is not None else ''}"
                )
            except Exception as e:
                rows.append({
                    "Timestamp": datetime.now(), "Filename": f.name,
                    "Invoice_Date": None, "Currency": None, "Shipper": None,
                    "Weight_KG": None, "Volume_M3": None, "Chargeable_KG": None,
                    "Chargeable_CBM": None, "Packages": None, "Subtotal": None,
                    "Freight_Mode": None, "Freight_Amount": None
                })
                log.append(f"✗ {f.name} | error: {e}")

    # DataFrame with fixed column order
    df = pd.DataFrame(rows)
    # Ensure correct column order + any missed columns
    for col in HEADERS:
        if col not in df.columns:
            df[col] = None
    df = df[HEADERS]

    st.subheader("Preview")
    st.dataframe(df, use_container_width=True)

    with st.expander("Parse log"):
        st.write("\n".join(log))

    # Build Excel in-memory
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice_Summary"

    # Write DataFrame (with header)
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)

    # Autosize columns (simple heuristic)
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value is None:
                    continue
                max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    # Save to bytes
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    st.download_button(
        label="⬇️ Download Excel (Invoice_Summary.xlsx)",
        data=buf,
        file_name="Invoice_Summary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Upload one or more **PDF** files to begin.")
