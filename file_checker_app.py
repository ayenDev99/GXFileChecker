import streamlit as st
import os
import re
import pandas as pd
from datetime import datetime, date
import json

APP_VERSION = "v1.0.2"

st.set_page_config(page_title="GX BIR File Checker", page_icon="gx_icon.png", layout="wide")
st.title(f"🧾 Z-Read & E-Journal Validation ({APP_VERSION})")

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
    from decimal import Decimal
    date_range = re.search(r"Date Range:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
    amount_match = re.search(r"NET SALES\s+([\d,]+\.\d{2})", text)

    beginning_si = re.search(r"BEGINNING SI\s+(\d+)", text)
    ending_si = re.search(r"ENDING SI\s+(\d+)", text)

    if date_range and amount_match and beginning_si and ending_si:
        start_date      = datetime.strptime(date_range.group(1), "%m/%d/%Y").date()
        end_date        = datetime.strptime(date_range.group(2), "%m/%d/%Y").date()
        amount          = Decimal(amount_match.group(1).replace(",", ""))
        si_start        = int(beginning_si.group(1))
        si_end          = int(ending_si.group(1))
        # Calculate transaction count including single transaction
        if si_start == 0 and si_end == 0:
            trans_count = 0
        else:
            trans_count = si_end - si_start + 1  # inclusive count

        tot_trans_count = trans_count
        return start_date, end_date, amount, tot_trans_count, si_start, si_end
    return None, None, None, None, None, None

def split_documents(text: str) -> list[tuple[str, str]]:
    # ── Format 1: *** SALES INVOICE *** / *** Return *** ─────────────────────
    fmt1_parts = re.split(
        r"\*{3}\s*(SALES INVOICE|Return)\s*\*{3}",
        text,
        flags=re.IGNORECASE
    )
    if len(fmt1_parts) > 1:
        return [
            (fmt1_parts[i].strip().upper(), fmt1_parts[i + 1])
            for i in range(1, len(fmt1_parts) - 1, 2)
            if not re.search(r"\*{3}\s*Re-Print\s*\*{3}", fmt1_parts[i + 1], re.IGNORECASE)
        ]

    # ── Format 2: Receipt Type: SALES INVOICE / Receipt Type: Return ──────────────────────────────
    type_matches = list(re.finditer(
        r"Receipt\s+Type:\s*(SALES INVOICE|Return)",
        text,
        flags=re.IGNORECASE
    ))

    if not type_matches:
        return []

    para_starts = [0] + [m.end() for m in re.finditer(r"\n[ \t]*\n", text)]

    block_starts = [
        max((p for p in para_starts if p <= tm.start()), default=0)
        for tm in type_matches
    ]

    sections = []
    for i, tm in enumerate(type_matches):
        block = text[block_starts[i] : block_starts[i + 1] if i + 1 < len(block_starts) else len(text)]

        if re.search(r"\*{3}\s*Re-Print\s*\*{3}", block, re.IGNORECASE):
            continue  # ← skip reprints

        sections.append((tm.group(1).strip().upper(), block))

    return sections 

def extract_receipt_info(text):

    from decimal import Decimal

    sales_amounts  = []
    return_amounts = []
    si_numbers     = []
    return_numbers = []
    date_val       = None
    sales_count    = 0

    def extract_tax_value(label, content):
        pattern = rf"{label}\s*:\s*(?:₱)?\s*(-?[\d,]+(?:\.\d{{2}})?)"
        match = re.search(pattern, content, re.IGNORECASE)
        return Decimal(match.group(1).replace(",", "").strip()) if match else Decimal("0.00")

    for doc_type, content in split_documents(text):

        # ── Date extraction ───────────────────────────────────────────────────
        month_match = re.search(
            r"(January|February|March|April|May|June|July|August"
            r"|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            content, re.IGNORECASE
        )
        md_match = re.search(r"(?<!ISSUED:\s)(\d{1,2}/\d{1,2}/\d{4})", content)

        if month_match:
            date_val = datetime.strptime(month_match.group(0), "%B %d, %Y").date()
        elif md_match:
            date_val = datetime.strptime(md_match.group(1), "%m/%d/%Y").date()

        # ── Sales Invoice ─────────────────────────────────────────────────────
        if "SALES INVOICE" in doc_type:
            sales_count += 1

            si_match = (
                re.search(r"SI\s*#\s*:\s*(\d+)", content, re.IGNORECASE)
                or re.search(r"Sales Invoice\s*#\s*:\s*(\d+)", content, re.IGNORECASE)
            )
            if si_match:
                si_numbers.append(int(si_match.group(1)))

            sales_amounts.append(
                extract_tax_value("VATable Sales",     content)
                + extract_tax_value("VAT Amount",      content)
                + extract_tax_value("VAT-Exempt Sales", content)
                + extract_tax_value("Zero-Rated Sales", content)
            )

        # ── Return ────────────────────────────────────────────────────────────
        elif "RETURN" in doc_type:
            return_match = re.search(r"Return\s*#\s*:\s*(\d+)", content)
            if return_match:
                return_numbers.append(int(return_match.group(1)))

            return_amounts.append(
                extract_tax_value("VATable Sales",     content)
                + extract_tax_value("VAT Amount",      content)
                + extract_tax_value("VAT-Exempt Sales", content)
                + extract_tax_value("Zero-Rated Sales", content)
            )

    net_amount    = sum(sales_amounts) - abs(sum(return_amounts))
    skipped_si    = (
        sorted(set(range(min(si_numbers), max(si_numbers) + 1)) - set(si_numbers))
        if si_numbers else []
    )

    return date_val, net_amount, sales_count, si_numbers, skipped_si

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

                    # st.write(start_date_range)
                    # st.write(date_val)
                    # st.write(end_date_range)

                    # st.write('-----')     
                       
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
    # st.write(ejournal_data)

    matching_receipts = []
    for ej in ejournal_data:
        if ej["si_numbers"]:
            if any(int(si_start) <= si <= int(si_end) for si in ej["si_numbers"]):
                matching_receipts.append(ej)
        else:
            pass
  
    # st.write(si_end)
    # st.write(matching_receipts)

    ej_total = sum(r["amount"] if r["amount"] else 0 for r in matching_receipts)
    ej_count = sum(r["trans_count"] if r["trans_count"] else 0 for r in matching_receipts)
    ej_files = ", ".join(r["file"] for r in matching_receipts) if matching_receipts else "None"
    ej_skip = ", ".join(r["skipped_si"] for r in matching_receipts) if matching_receipts else ""

    # st.write(ej_total)
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
