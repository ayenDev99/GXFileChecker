import streamlit as st
import os
import re
import io
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="Z-Read & E-Journal Checker", layout="wide")
st.title("🧾 Z-Read vs E-Journal Validation")

# Folder Selection
with st.expander("📁 Folder Selection", expanded=True):
    folder1 = st.text_input("Z-Read Folder Path", value=r"C:\Users\ZOut")
    folder2 = st.text_input("E-Journal Folder Path", value=r"C:\Users\BIREjournals")

# Date Range Picker
with st.expander("📅 Date Range Filter", expanded=True):
    date_range = st.date_input("Date Range", [date.today(), date.today()])
    if len(date_range) != 2:
        st.warning("⚠️ Please select a start and end date.")
        st.stop()

start_date_range, end_date_range = date_range

###############################################
# Helpers
###############################################
def extract_zread_info(text):
    date_range = re.search(r"Date Range:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
    amount_match = re.search(r"NET SALES\s+([\d,]+\.\d{2})", text)

    beginning_si = re.search(r"BEGINNING SI\s+(\d+)", text)
    beginning_si_count = int(beginning_si.group(1))

    ending_si = re.search(r"ENDING SI\s+(\d+)", text)
    ending_si_count = int(ending_si.group(1))

    if date_range and amount_match:
        start_date_str  = date_range.group(1)
        end_date_str    = date_range.group(2)
        start_date      = datetime.strptime(start_date_str, "%m/%d/%Y").date()
        end_date        = datetime.strptime(end_date_str, "%m/%d/%Y").date()
        amount          = float(amount_match.group(1).replace(",", ""))
        trans_count = (ending_si_count - beginning_si_count) + 1
        return start_date, end_date, amount, trans_count
    return None, None, None, None

def extract_receipt_info(text):
    date_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{2}, \d{4}\b'
    date_matches = re.findall(date_pattern, text)

    receipts = re.split(r"\n\s*TRIUMPH", text)
    receipts = [("TRIUMPH" + r.strip()) for r in receipts if r.strip()]

    # Receipt Type
    sales_invoice_receipts = []
    for receipt in receipts:
        match = re.search(r"Receipt\s*Type\s*:\s*(.+)", receipt, re.IGNORECASE)
        if match and match.group(1).strip() == "SALES INVOICE":
            match_reprint = re.search(r"Re-Print", receipt, re.IGNORECASE)
            if not match_reprint:
                sales_invoice_receipts.append(receipt)

    # Total Amount Due
    amount_pattern = r'₱([\d,]+\.\d{2})\s*\n?Total Amount Due:'
    all_amounts = []
    for receipt in sales_invoice_receipts:
        amount_matches = re.findall(amount_pattern, receipt)
        all_amounts.extend(amount_matches)

    # SI #
    trans_pattern = r'SI #:'
    all_trans = []
    for receipt in sales_invoice_receipts:
        trans_matches = re.findall(trans_pattern, receipt)
        all_trans.extend(trans_matches)

    if date_matches and all_amounts:
        date_val    = datetime.strptime(date_matches[0], "%B %d, %Y").date()
        amount_val  = sum(float(amount.replace(",", "")) for amount in all_amounts)
        trans_count = len(all_trans)
        return date_val, amount_val, trans_count
    return None, None, None

def color_result(val):
    if val == "MATCH":
        return 'color: green'
    else:
        return 'color: red'

def highlight_mismatch_counts(row):
    return [
        '',  # Date
        '',  # Z-Read File
        'color: red' if row["Z-Read Count"] != row["E-Journal Count"] else '',  # Z-Read Count
        '',  # Z-Read Amount
        '',  # E-Journal File(s)
        'color: red' if row["Z-Read Count"] != row["E-Journal Count"] else '',  # E-Journal Count
        '',  # E-Journal Total
        'color: green' if row["Result"] == "MATCH" else 'color: red'  # Result
    ]

###############################################
# Start Process
###############################################
# Collect Z-Read data
zread_data = []
if os.path.exists(folder1):
    for fname in os.listdir(folder1):
        if fname.lower().endswith(".txt"):
            with open(os.path.join(folder1, fname), "r", encoding="utf-8") as f:
                content = f.read()
                start_date, end_date, amount, z_trans_count = extract_zread_info(content)
                if start_date and end_date and amount is not None:
                    if end_date >= start_date_range and start_date <= end_date_range:
                        zread_data.append({
                            "start_date"        : start_date
                            , "end_date"        : end_date
                            , "file"            : fname
                            , "amount"          : amount
                            , "z_trans_count"   : z_trans_count
                        })
else:
    st.error("❌ Folder 1 not found")

# Collect E-Journal data
ejournal_data = {}
if os.path.exists(folder2):
    for fname in os.listdir(folder2):
        if fname.lower().endswith(".txt"):
            with open(os.path.join(folder2, fname), "r", encoding="utf-8") as f:
                content = f.read()
                date_val, amount, trans_count = extract_receipt_info(content)
                if date_val and amount is not None and start_date_range <= date_val <= end_date_range:
                    ejournal_data.setdefault(date_val, []).append({
                        "file": fname
                        , "amount": amount
                        , "trans_count" : trans_count
                    })
else:
    st.error("❌ Folder 2 not found")

# Build validation results
result_table = []
for z in zread_data:
    start_date  = z["start_date"]
    end_date    = z["end_date"]
    z_file      = z["file"]
    z_total     = z["amount"]
    z_count     = z["z_trans_count"]

    matching_receipts = [r for d in ejournal_data if start_date <= d <= end_date for r in ejournal_data[d]]
    ej_total = sum(r["amount"] for r in matching_receipts)
    ej_count = sum(r["trans_count"] for r in matching_receipts)
    ej_files = ", ".join(r["file"] for r in matching_receipts) if matching_receipts else "None"

    result = "MATCH" if abs(z_total - ej_total) < 0.01 else "MISMATCH"
    result_table.append({
        "Date"                  : f"{start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')}"
        , "Z-Read File"         : z_file
        , "Z-Read Count"        : z_count
        , "Z-Read Amount"       : f"₱{z_total:,.2f}"
        , "E-Journal File(s)"   : ej_files
        , "E-Journal Count"     : ej_count
        , "E-Journal Total"     : f"₱{ej_total:,.2f}"
        , "Result"              : result
    })

# Show Summary & Table
if result_table:
    st.subheader("📈 Summary")
    total_files = len(result_table)
    total_match = sum(1 for r in result_table if r["Result"] == "MATCH")
    total_mismatch = total_files - total_match

    col1, col2, col3 = st.columns(3)
    col1.metric("📄 Z-Read Files", total_files)
    col2.metric("Matches", total_match)
    col3.metric("Mismatches", total_mismatch)

    # Show result table with custom styling
    df = pd.DataFrame(result_table)
    styled_df = df.style.apply(highlight_mismatch_counts, axis=1)

    st.markdown("📊 Validation Table (Per Z-Read File)")
    st.dataframe(styled_df, use_container_width=True)

    #Download summary into CSV
    csv_data = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label       = "📥CSV"
        , data      = csv_data
        , file_name = "validation_report.csv"
        , mime      = "text/csv"
    )
else:
    st.warning("⚠️ No data found for the selected date range. Try adjusting the folders or dates.")
    