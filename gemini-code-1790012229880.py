import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import re
import io
import sqlite3
from PIL import Image

# Optional OCR import
try:
    import easyocr
    import numpy as np
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False

# -----------------------------------------------------------------------------
# Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Poultry Farm Manager",
    page_icon="🐔",
    layout="wide",
    initial_sidebar_state="expanded"
)

EGG_PRICE_PKR = 50.0
PARTNERS = ["Mustafeez", "Umar", "Hamza", "Kamran"]

# -----------------------------------------------------------------------------
# Database Setup (SQLite for Local Persistence)
# -----------------------------------------------------------------------------
DB_FILE = "poultry_farm.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id TEXT PRIMARY KEY,
            date TEXT,
            operator TEXT,
            type TEXT,
            eggs INTEGER,
            amount REAL,
            reason TEXT,
            device TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

def load_logs_from_db():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id AS 'Transaction ID', date AS 'Date', operator AS 'Operator', type AS 'Type', eggs AS 'Eggs', amount AS 'Amount (RS)', reason AS 'Category/Reason', device AS 'Device Info', timestamp AS 'Timestamp' FROM logs", conn)
    conn.close()
    return df

def save_log_to_db(entry):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        entry["Transaction ID"], entry["Date"], entry["Operator"], 
        entry["Type"], entry["Eggs"], entry["Amount (RS)"], 
        entry["Category/Reason"], entry["Device Info"], entry["Timestamp"]
    ))
    conn.commit()
    conn.close()

init_db()

# Load state from Database
st.session_state.logs = load_logs_from_db()

# Balance Calculation Engine
def calculate_partner_balances(df):
    balances = {p: 0.0 for p in PARTNERS}
    if not df.empty:
        for _, row in df.iterrows():
            op = row["Operator"]
            if op in balances:
                amt = float(row["Amount (RS)"])
                if row["Type"] == "Collection (Debit)":
                    balances[op] += amt  # Operator holds egg money
                elif row["Type"] in ["Repayment (Credit)", "Expense (Credit)"]:
                    balances[op] -= amt  # Operator paid cash back or spent own money
    return balances

partner_balances = calculate_partner_balances(st.session_state.logs)

# -----------------------------------------------------------------------------
# Device Specs Detection
# -----------------------------------------------------------------------------
def get_device_info():
    try:
        ua_string = st.context.headers.get("User-Agent", "Mobile Device")
        if "iPhone" in ua_string or "iPad" in ua_string:
            return "Apple iOS Device"
        elif "Android" in ua_string:
            return "Android Mobile Device"
        elif "Windows" in ua_string:
            return "Windows PC Workstation"
        elif "Macintosh" in ua_string:
            return "Apple Mac Workstation"
        else:
            return "Mobile/Desktop Browser"
    except Exception:
        return "Mobile Web Browser"

# -----------------------------------------------------------------------------
# AI OCR Reader (EasyOCR Engine)
# -----------------------------------------------------------------------------
@st.cache_resource
def get_ocr_reader():
    if HAS_EASYOCR:
        # Load CPU version to save RAM on free servers
        return easyocr.Reader(['en'], gpu=False)
    return None

def extract_amount_from_image(image_bytes):
    try:
        reader = get_ocr_reader()
        if reader:
            img = Image.open(io.BytesIO(image_bytes))
            results = reader.readtext(np.array(img), detail=0)
            full_text = " ".join(results)
            
            # Find numbers associated with money figures
            numbers = re.findall(r'(?:RS|PKR|AMOUNT|\$)?\s*([\d,]+(?:\.\d{2})?)', full_text, re.IGNORECASE)
            valid_nums = []
            for num in numbers:
                clean_num = float(num.replace(',', ''))
                if clean_num > 50:  # Exclude tiny numbers like times or small fees
                    valid_nums.append(clean_num)
            if valid_nums:
                return max(valid_nums)
        return 0.0
    except Exception:
        return 0.0

# -----------------------------------------------------------------------------
# Sidebar Navigation
# -----------------------------------------------------------------------------
st.sidebar.image("https://img.icons8.com/color/96/poultry.png", width=80)
st.sidebar.title("Poultry Farm App")
page = st.sidebar.radio("Select View", ["Operator Portal", "Executive Dashboard", "Ledger History & Export"])

st.sidebar.divider()
st.sidebar.markdown("### Operator Balances")
for p, bal in partner_balances.items():
    color = "red" if bal > 0 else ("green" if bal < 0 else "gray")
    label = "Owes Farm" if bal > 0 else ("Farm Owes" if bal < 0 else "Balanced")
    st.sidebar.markdown(f"**{p}:** <span style='color:{color}; font-weight:bold;'>RS {abs(bal):,.2f} ({label})</span>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 1: OPERATOR PORTAL
# -----------------------------------------------------------------------------
if page == "Operator Portal":
    st.title("🐔 Operator Portal & Daily Logging")
    
    col_op1, col_op2 = st.columns(2)
    with col_op1:
        selected_operator = st.selectbox("Select Active Operator Name", PARTNERS)
    with col_op2:
        detected_device = get_device_info()
        st.info(f"**Detected Device:** {detected_device}\n\n**Operator:** {selected_operator}")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["🥚 Egg Collection (Debit)", "💳 Repay Amount (Upload Proof)", "💸 Log Expense (Credit)"])

    # --- TAB 1: EGG COLLECTION ---
    with tab1:
        st.subheader("Record Daily Egg Collection")
        c1, c2 = st.columns(2)
        with c1:
            coll_date = st.date_input("Collection Date", value=date.today(), key="egg_date")
            egg_count = st.number_input("Number of Eggs Collected", min_value=0, step=1, value=100)
        
        calculated_debit = egg_count * EGG_PRICE_PKR
        
        with c2:
            st.metric("Rate per Egg", f"RS {EGG_PRICE_PKR}")
            st.metric("Total Collection Value", f"RS {calculated_debit:,.2f}")

        if st.button("Submit Egg Collection Record", type="primary"):
            tx_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            entry = {
                "Transaction ID": tx_id,
                "Date": coll_date.strftime("%Y-%m-%d"),
                "Operator": selected_operator,
                "Type": "Collection (Debit)",
                "Eggs": egg_count,
                "Amount (RS)": calculated_debit,
                "Category/Reason": "Daily Egg Collection",
                "Device Info": detected_device,
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_log_to_db(entry)
            st.success(f"Recorded {egg_count} eggs! RS {calculated_debit:,.2f} debited to {selected_operator}.")
            st.rerun()

    # --- TAB 2: REPAYMENT VIA RECEIPT SCREENSHOT ---
    with tab2:
        st.subheader("Balance Debit Account via Transfer Screenshot")
        curr_bal = partner_balances.get(selected_operator, 0.0)
        st.write(f"Current Outstanding Balance for **{selected_operator}**: **RS {curr_bal:,.2f}**")
        
        repay_date = st.date_input("Transfer Date", value=date.today(), key="repay_date")
        uploaded_file = st.file_uploader("Upload Transfer Proof (EasyPaisa/JazzCash/Bank)", type=["png", "jpg", "jpeg", "webp"])
        
        detected_amt = 0.0
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Uploaded Payment Screenshot", width=280)
            with st.spinner("AI Scanner analyzing image..."):
                file_bytes = uploaded_file.read()
                detected_amt = extract_amount_from_image(file_bytes)
                if detected_amt > 0:
                    st.success(f"AI Detected Amount: **RS {detected_amt:,.2f}**")

        final_repay_amt = st.number_input("Confirmed Repayment Amount (RS)", min_value=0.0, value=float(detected_amt), step=100.0)

        if st.button("Confirm Payment & Balance Account"):
            if final_repay_amt <= 0:
                st.error("Please enter a valid payment amount.")
            else:
                tx_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                entry = {
                    "Transaction ID": tx_id,
                    "Date": repay_date.strftime("%Y-%m-%d"),
                    "Operator": selected_operator,
                    "Type": "Repayment (Credit)",
                    "Eggs": 0,
                    "Amount (RS)": final_repay_amt,
                    "Category/Reason": "Payment Proof Uploaded",
                    "Device Info": detected_device,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_log_to_db(entry)
                st.success(f"Payment of RS {final_repay_amt:,.2f} credited to {selected_operator}.")
                st.rerun()

    # --- TAB 3: EXPENSE LOGGING ---
    with tab3:
        st.subheader("Log Spent Money (Feed, Medicines, Repairs)")
        exp_date = st.date_input("Expense Date", value=date.today(), key="exp_date")
        exp_category = st.selectbox("Category", ["Hen Feed", "Medicines/Vaccines", "Electricity/Utilities", "Shed Maintenance", "Worker Wages", "Other"])
        exp_amount = st.number_input("Amount Spent (RS)", min_value=0.0, step=500.0, value=1000.0)
        exp_reason = st.text_area("Reason for Expense", placeholder="e.g. Bought 2 bags layer feed")

        if st.button("Log Expense"):
            if not exp_reason.strip():
                st.error("Please enter a reason for the expense.")
            else:
                tx_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                entry = {
                    "Transaction ID": tx_id,
                    "Date": exp_date.strftime("%Y-%m-%d"),
                    "Operator": selected_operator,
                    "Type": "Expense (Credit)",
                    "Eggs": 0,
                    "Amount (RS)": exp_amount,
                    "Category/Reason": f"[{exp_category}] {exp_reason}",
                    "Device Info": detected_device,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_log_to_db(entry)
                st.success(f"Expense of RS {exp_amount:,.2f} logged for {selected_operator}.")
                st.rerun()

# -----------------------------------------------------------------------------
# PAGE 2: EXECUTIVE DASHBOARD
# -----------------------------------------------------------------------------
elif page == "Executive Dashboard":
    st.title("📊 Executive Dashboard")
    
    df = st.session_state.logs.copy()
    
    total_eggs = int(df[df["Type"] == "Collection (Debit)"]["Eggs"].sum()) if not df.empty else 0
    total_revenue = float(df[df["Type"] == "Collection (Debit)"]["Amount (RS)"].sum()) if not df.empty else 0.0
    total_expenses = float(df[df["Type"] == "Expense (Credit)"]["Amount (RS)"].sum()) if not df.empty else 0.0
    net_profit = total_revenue - total_expenses

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Eggs Collected", f"{total_eggs:,} pcs")
    m2.metric("Total Revenue", f"RS {total_revenue:,.2f}")
    m3.metric("Total Expenses", f"RS {total_expenses:,.2f}")
    m4.metric("Net Farm Profit", f"RS {net_profit:,.2f}")

    st.divider()

    st.subheader("Dynamic Revenue & Collection Chart")
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        y_axis_mode = st.radio("Y-Axis Metric", ["Revenue (RS)", "Eggs Layed"])
    with c2:
        auto_scale = st.checkbox("Auto-Adjust Y-Axis", value=True)
    with c3:
        manual_min = st.number_input("Y-Min Scale", value=0, disabled=auto_scale)
    with c4:
        manual_max = st.number_input("Y-Max Scale", value=50000, disabled=auto_scale)

    if not df.empty:
        df_collections = df[df["Type"] == "Collection (Debit)"].groupby("Date")[["Eggs", "Amount (RS)"]].sum().reset_index()
        
        y_col = "Amount (RS)" if y_axis_mode == "Revenue (RS)" else "Eggs"
        
        fig = px.line(
            df_collections, x="Date", y=y_col, markers=True,
            title=f"Daily {y_axis_mode} Trend",
            labels={"Date": "Date", y_col: y_axis_mode}
        )
        fig.update_traces(line_color="#1E3A8A", line_width=3)

        if not auto_scale:
            fig.update_layout(yaxis_range=[manual_min, manual_max])

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No egg collection data available yet.")

# -----------------------------------------------------------------------------
# PAGE 3: LEDGER HISTORY & EXCEL EXPORT
# -----------------------------------------------------------------------------
elif page == "Ledger History & Export":
    st.title("📜 Transaction History & Excel Export")
    
    df_logs = st.session_state.logs.copy()
    
    col1, col2 = st.columns(2)
    with col1:
        op_filter = st.multiselect("Filter by Operator", PARTNERS, default=PARTNERS)
    with col2:
        type_filter = st.multiselect(
            "Filter by Type", 
            ["Collection (Debit)", "Repayment (Credit)", "Expense (Credit)"],
            default=["Collection (Debit)", "Repayment (Credit)", "Expense (Credit)"]
        )

    if not df_logs.empty:
        filtered_df = df_logs[
            (df_logs["Operator"].isin(op_filter)) & 
            (df_logs["Type"].isin(type_filter))
        ]

        st.dataframe(filtered_df, use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            filtered_df.to_excel(writer, sheet_name="Transaction Logs", index=False)
            
            summary_df = pd.DataFrame(
                list(partner_balances.items()),
                columns=["Partner Name", "Outstanding Balance (RS)"]
            )
            summary_df.to_excel(writer, sheet_name="Partner Ledger", index=False)

        st.download_button(
            label="📥 Download Excel Report (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"Poultry_Farm_Ledger_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No log data available.")