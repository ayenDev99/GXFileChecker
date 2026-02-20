import streamlit as st
import os
import re
import pandas as pd
from datetime import datetime, date
import json

st.set_page_config(page_title="GX BIR File Checker", page_icon="gx_icon.png", layout="wide")
st.title("🧾 Z-Read & E-Journal Validation")

# Date Range Picker
with st.expander("📅 Date Range Filter", expanded=True):
    date_range = st.date_input("Date Range", [date.today(), date.today()])
    if len(date_range) != 2:
        st.warning("⚠️ Please select a start and end date.")
        st.stop()

# Global Variables
start_date_range, end_date_range = date_range

hide_top_space_style = """
                            <style>
                                header      {display: none !important;}
                                #MainMenu   {visibility: hidden;}
                                footer      {visibility: hidden;}
                                
                                .css-18e3th9    {padding-top    : 0rem !important;}
                                .css-k1vhr4     {margin-top     : 0rem !important;}
                                div.block-container {
                                                        padding-top : 15px !important;
                                                        margin-top  : 0rem !important;
                                                    }
                            </style>
                        """
st.markdown(hide_top_space_style, unsafe_allow_html=True)


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
        si_start        = int(beginning_si.group(1))
        si_end          = int(ending_si.group(1))
        # trans_count     = (int(si_end) - int(si_start))
        # Calculate transaction count including single transaction
        if si_start == 0 and si_end == 0:
            trans_count = 0
        else:
            trans_count = si_end - si_start + 1  # inclusive count

        tot_trans_count = trans_count
        return start_date, end_date, amount, tot_trans_count, si_start, si_end
    return None, None, None, None, None, None

def extract_receipt_info(text):

    sales_amounts = []
    return_amounts = []
    si_numbers = []
    return_numbers = []
    date_val = None

    # Split keeping type
    parts = re.split(
        r"\*{3}\s*(SALES INVOICE|Return)\s*\*{3}",
        text,
        flags=re.IGNORECASE
    )

    # parts structure:
    # [header, type1, content1, type2, content2, ...]

    for i in range(1, len(parts), 2):
        doc_type = parts[i].strip().upper()
        content = parts[i+1]

        # Extract date once
        if not date_val:
            date_match = re.search(
                r"\d{1,2}:\d{2}\s*(?:am|pm),\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{2},\s+\d{4}",
                content,
                re.IGNORECASE
            )
            if date_match:
                date_str = date_match.group(0).split(", ", 1)[1]
                date_val = datetime.strptime(date_str, "%B %d, %Y").date()

        # SALES
        if "SALES INVOICE" in doc_type:

            si_match = re.search(r"SI\s*#\s*:\s*(\d+)", content)
            if si_match:
                si_numbers.append(int(si_match.group(1)))

            amount_match = re.search(
                r"Subtotal\s*:\s*([\d,]+\.\d{2})",
                content,
                re.IGNORECASE
            )

            if amount_match:
                sales_amounts.append(
                    float(amount_match.group(1).replace(",", ""))
                )

        # RETURN
        elif "RETURN" in doc_type:

            return_match = re.search(r"Return\s*#\s*:\s*(\d+)", content)
            if return_match:
                return_numbers.append(int(return_match.group(1)))

            amount_match = re.search(
                r"Subtotal\s*:\s*-\s*([\d,]+\.\d{2})",
                content,
                re.IGNORECASE
            )

            if amount_match:
                return_amounts.append(
                    float(amount_match.group(1).replace(",", ""))
                )

    total_sales = sum(sales_amounts)
    total_returns = sum(return_amounts)
    net_amount = total_sales - total_returns

    total_trans_count = len(si_numbers)

    skipped_si = []
    if si_numbers:
        skipped_si = [
            i for i in range(min(si_numbers), max(si_numbers)+1)
            if i not in si_numbers
        ]

    return (
        date_val,
        net_amount,
        total_trans_count,
        si_numbers,
        skipped_si
    )

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
        ''                                                                          # Date
        , ''                                                                        # Z-Read File
        , ''                                                                        # Beginning SI
        , ''                                                                        # Ending SI
        , 'color: red' if row["Trans Count"] != row["SI Count"] else ''             # Trans Count
        , 'color: red' if row["Z-Read Amount"] != row["E-Journal Total"] else ''    # Z-Read Amount
        , ''                                                                        # E-Journal File(s)
        , 'color: red' if row["Trans Count"] != row["SI Count"] else ''             # SI Count
        , 'color: red' if row["Z-Read Amount"] != row["E-Journal Total"] else ''    # E-Journal Total
        , 'color: red'                                                              # Skipped SI
        , 'color: green' if row["Result"] == "MATCH" else 'color: red'              # Result
    ]

###############################################
# Start Process
###############################################
# Collect Z-Read data
with st.spinner("Processing..."):
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
                    date_val, amount, trans_count, si_numbers, skipped_si = extract_receipt_info(content)

                    if date_val and start_date_range <= date_val <= end_date_range:
                        ejournal_data.append({
                            "file"          : fname,
                            "date"          : date_val,
                            "amount"        : amount,
                            "trans_count"   : trans_count,
                            "si_numbers"    : si_numbers,
                            "skipped_si"    : ", ".join(map(str, skipped_si))
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
        if ej["si_numbers"]:
            if any(int(si_start) <= si <= int(si_end) for si in ej["si_numbers"]):
                matching_receipts.append(ej)
        else:
            pass

    ej_total = sum(r["amount"] if r["amount"] else 0 for r in matching_receipts)
    ej_count = sum(r["trans_count"] if r["trans_count"] else 0 for r in matching_receipts)
    ej_files = ", ".join(r["file"] for r in matching_receipts) if matching_receipts else "None"
    ej_skip = ", ".join(r["skipped_si"] for r in matching_receipts) if matching_receipts else ""

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
        , "Skipped SI"          : ej_skip
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
