import streamlit as st
import pandas as pd
import io

st.title("📂 CSV File Checker with Report")

# Upload files
file1 = st.file_uploader("Upload First CSV File", type="csv")
file2 = st.file_uploader("Upload Second CSV File", type="csv")

# Input column name
column_name = st.text_input("Column name to sum", value="total")

if file1 is not None and file2 is not None:
    try:
        # Read CSVs
        df1 = pd.read_csv(file1)
        df2 = pd.read_csv(file2)

        # Sum specified column
        total1 = df1[column_name].sum()
        total2 = df2[column_name].sum()
        match = total1 == total2

        # Display comparison
        st.write(f"**Total in File 1 ({column_name}):** {total1}")
        st.write(f"**Total in File 2 ({column_name}):** {total2}")
        st.success("✅ Totals Match!") if match else st.error("❌ Totals Do NOT Match!")

        # Create report text
        report = f"""
CSV File Checker Report
------------------------
Column Compared: {column_name}

File 1 Total: {total1}
File 2 Total: {total2}

Result: {"MATCH ✅" if match else "DO NOT MATCH ❌"}
"""

        # Convert report to downloadable bytes
        report_bytes = io.BytesIO(report.encode("utf-8"))

        # Provide download button
        st.download_button(
            label="📄 Download Report as .txt",
            data=report_bytes,
            file_name="comparison_report.txt",
            mime="text/plain"
        )

    except Exception as e:
        st.error(f"⚠️ Error processing files: {e}")
