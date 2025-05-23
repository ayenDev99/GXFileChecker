import streamlit as st
import os
import re
import pandas as pd
from datetime import datetime, date
import json

st.set_page_config(page_title="GX BIR File Checker", layout="wide")
st.title("🧾 Z-Read & E-Journal Validation")

# Date Range Picker
with st.expander("📅 Date Range Filter", expanded=True):
    date_range = st.date_input("Date Range", [date.today(), date.today()])
    if len(date_range) != 2:
        st.warning("⚠️ Please select a start and end date.")
        st.stop()

# Global Variables
start_date_range, end_date_range = date_range

###############################################
# Helpers
###############################################
def load_config(config_path="config.json"):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if config_path.endswith(".json"):
                return json.load(f)
            else:
                config = {}
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        config[key.strip()] = value.strip()
                return config
    except FileNotFoundError:
        st.warning(f"⚠️ Config file not found at {config_path}. Using default settings.")
        return {}
    except Exception as e:
        st.error(f"❌ Failed to load config: {e}")
        return {}
    
config = load_config("config.json") 

def extract_zread_info(text):
    date_range = re.search(r"Date Range:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
    amount_match = re.search(r"NET SALES\s+([\d,]+\.\d{2})", text)

    beginning_si = re.search(r"BEGINNING SI\s+(\d+)", text)
    ending_si = re.search(r"ENDING SI\s+(\d+)", text)

    if date_range and amount_match and beginning_si and ending_si:
        start_date      = datetime.strptime(date_range.group(1), "%m/%d/%Y").date()
        end_date        = datetime.strptime(date_range.group(2), "%m/%d/%Y").date()
        amount          = float(amount_match.group(1).replace(",", ""))
        si_start        = beginning_si.group(1)
        si_end          = ending_si.group(1)
        trans_count     = (int(si_end) - int(si_start)) + 1
        return start_date, end_date, amount, trans_count, si_start, si_end
    return None, None, None, None, None, None

def extract_receipt_info(text):
    sales_invoice_receipts = []
    si_numbers = []

    header_keyword  = config.get("receipt_header_keyword")
    date_keyword    = config.get("receipt_date_pattern")
    type_keyword    = config.get("receipt_type_pattern")

    date_patterns = {
                            "date_pattern_1" : r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{2}, \d{4}\b"
                        ,   "date_pattern_2" : r"\b\d{2}/\d{2}/\d{4} \d{2}:\d{2}\b"
                    }
    type_patterns = {
                            "type_pattern_1" : r"Receipt\s*Type\s*:\s*(.+)"
                        ,   "type_pattern_2" : r"\s\*{3}\s(.+)"
                    }

    if header_keyword in text:
        receipts = re.split(rf"(?=\n\s*{re.escape(header_keyword)})", text)
        receipts = [r.strip() for r in receipts if header_keyword in r]

        if date_keyword in date_patterns:
            date_pattern = date_patterns.get(date_keyword)
            date_matches = re.findall(date_pattern, text)
        else:
            st.error(f"❌ Invalid receipt DATE pattern. Please check the config file.")
            st.stop()
            return None, None, None, None
        
        for receipt in receipts:
            type_pattern = type_patterns.get(type_keyword)
            if type_pattern:
                match_receipt_type = re.search(type_pattern, receipt, re.IGNORECASE)

                if match_receipt_type and "SALES INVOICE" in match_receipt_type.group(1).upper():
                    if "re-print" not in receipt.lower():
                        match_si = re.search(r'SI\s*#\s*[:]*\s*(\d+)', receipt)
                        if match_si:
                            si_num = int(match_si.group(1))
                            sales_invoice_receipts.append((receipt, si_num))
                            si_numbers.append(si_num)
            else:
                st.error(f"❌ Invalid receipt TYPE pattern. Please check the config file.")
                st.stop()
                return None, None, None, None

        all_amounts = []
        for receipt, _ in sales_invoice_receipts:
            amount_matches = re.findall(r'₱([\d,]+\.\d{2})\s*\n?Total Amount Due|Total Amount Due\s*₱([\d,]+\.\d{2})', receipt)
            amount_matches = [match[0] or match[1] for match in amount_matches if match[0] or match[1]]
            all_amounts.extend(amount_matches)

        if date_matches and all_amounts:
            date_val    = pd.to_datetime(date_matches[0]).date()
            amount_val  = sum(float(a.replace(",", "")) for a in all_amounts)
            trans_count = len(sales_invoice_receipts)
            return date_val, amount_val, trans_count, si_numbers

        return None, None, None, []
    else:
        st.error(f"❌ Transaction receipt header '{header_keyword}' not found on EJournal receipts. Please check the config file.")
        st.stop()
        return None, None, None, None

def highlight_mismatch_counts(row):
    # Highlight grand total row
    if row["Date"] == "GRAND TOTAL":
        zread = float(str(row["Z-Read Amount"]).replace("₱", "").replace(",", "") or 0)
        ejournal = float(str(row["E-Journal Total"]).replace("₱", "").replace(",", "") or 0)

        if abs(zread - ejournal) > 0.01:
            return ['font-weight: bold; background-color: #ffcccc'] * len(row)
        else:
            return ['font-weight: bold; background-color: #d4edda'] * len(row)
    elif row["Date"] == "":
        return ['background-color: #ffffff'] * len(row)

    return [
        ''      # Date
        , ''    # Z-Read File
        , ''    # Beginning SI
        , ''    # Ending SI
        , 'color: red' if row["Trans Count"] != row["SI Count"] else '' # Trans Count
        , ''    # Z-Read Amount
        , ''    # E-Journal File(s)
        , 'color: red' if row["Trans Count"] != row["SI Count"] else '' # SI Count
        , ''    # E-Journal Total
        , 'color: green' if row["Result"] == "MATCH" else 'color: red'  # Result
    ]

###############################################
# Start Process
###############################################
# Collect Z-Read data
zread_data = []
zread_folder_path = config.get("zread_folder_path")
if os.path.exists(zread_folder_path):
    for fname in os.listdir(zread_folder_path):
        if fname.lower().endswith(".txt"):
            with open(os.path.join(zread_folder_path, fname), "r", encoding="utf-8") as f:
                content = f.read()
                s_date, e_date, amount, z_count, si_start, si_end = extract_zread_info(content)
                if s_date and e_date and amount is not None:
                    if e_date >= start_date_range and s_date <= end_date_range:
                        zread_data.append({
                            "start_date"        : s_date
                            , "end_date"        : e_date
                            , "file"            : fname
                            , "amount"          : amount
                            , "z_trans_count"   : z_count
                            , "si_start"        : si_start
                            , "si_end"          : si_end
                        })
else:
    st.error("❌ Z-Read folder not found. Please check the folder path in config file.")
    st.stop()

# Collect E-Journal data
ejournal_data = []
ejournal_folder_path = config.get("ejournal_folder_path")
if os.path.exists(ejournal_folder_path):
    for fname in os.listdir(ejournal_folder_path):
        if fname.lower().endswith(".txt"):
            with open(os.path.join(ejournal_folder_path, fname), "r", encoding="utf-8") as f:
                content = f.read()
                date_val, amount, trans_count, si_numbers = extract_receipt_info(content)
                if amount is not None and si_numbers:
                    ejournal_data.append({
                        "file"          : fname
                        , "amount"      : amount
                        , "trans_count" : trans_count
                        , "si_numbers"  : si_numbers
                    })
else:
    st.error("❌ E-Journal folder not found. Please check the folder path in config file.")
    st.stop()

# Validation
result_table = []
for z in zread_data:
    si_start = z["si_start"]
    si_end = z["si_end"]

    matching_receipts = []
    for ej in ejournal_data:
        if any(int(si_start) <= si <= int(si_end) for si in ej["si_numbers"]):
            matching_receipts.append(ej)

    ej_total = sum(r["amount"] for r in matching_receipts)
    ej_count = sum(r["trans_count"] for r in matching_receipts)
    ej_files = ", ".join(r["file"] for r in matching_receipts) if matching_receipts else "None"

    result = "MATCH" if abs(z["amount"] - ej_total) < 0.01 else "MISMATCH"
    result_table.append({
        "Date"                  : f"{z['start_date'].strftime('%m/%d/%Y')} - {z['end_date'].strftime('%m/%d/%Y')}"
        , "Z-Read File"         : z["file"]
        , "Beginning SI"        : z["si_start"]
        , "Ending SI"           : z["si_end"]
        , "Trans Count"         : z["z_trans_count"]
        , "Z-Read Amount"       : f"₱{z['amount']:,.2f}"
        , "E-Journal File(s)"   : ej_files
        , "SI Count"            : ej_count
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

    # Create DataFrame and add grand total row
    df = pd.DataFrame(result_table)

    # Grand totals
    grand_zread_total = sum(float(r["Z-Read Amount"].replace("₱", "").replace(",", "")) for r in result_table)
    grand_ejournal_total = sum(float(r["E-Journal Total"].replace("₱", "").replace(",", "")) for r in result_table)

    result = "MATCH" if abs(grand_zread_total - grand_ejournal_total) < 0.01 else "MISMATCH"
    total_row = {
        "Date": "GRAND TOTAL",
        "Z-Read File": "",
        "Beginning SI": "",
        "Ending SI": "",
        "Trans Count": "",
        "Z-Read Amount": f"₱{grand_zread_total:,.2f}",
        "E-Journal File(s)": "",
        "SI Count": "",
        "E-Journal Total": f"₱{grand_ejournal_total:,.2f}",
        "Result": result
    }

    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
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
    st.warning("⚠️ No data found for the selected date range.")
