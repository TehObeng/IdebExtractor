"""
SLIK Extractor Pro — Streamlit Application
A web-based tool for parsing Indonesian OJK SLIK/iDeb PDF reports.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from slik_parser import extract_text_from_pdf, parse_slik_data, export_to_excel, build_debtor_summary

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SLIK Extractor Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Modern dark theme overrides */
    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 50%, #24243e 100%);
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 {
        color: #ffffff;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        color: rgba(255, 255, 255, 0.85);
        font-size: 1rem;
        margin: 0.5rem 0 0 0;
    }

    /* Card styling */
    .info-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
    }

    /* Stats cards */
    .stat-card {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.15));
        border: 1px solid rgba(102, 126, 234, 0.3);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .stat-card h3 {
        color: #667eea;
        font-size: 1.8rem;
        margin: 0;
        font-weight: 700;
    }
    .stat-card p {
        color: rgba(255, 255, 255, 0.7);
        font-size: 0.85rem;
        margin: 0.3rem 0 0 0;
    }

    /* Upload area */
    .uploadedFile {
        background: rgba(255, 255, 255, 0.05) !important;
        border-color: rgba(102, 126, 234, 0.3) !important;
    }

    /* Table styling */
    .dataframe {
        font-size: 0.85rem !important;
    }

    /* Button styling */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        padding: 0.6rem 2rem !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4) !important;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6) !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #00c9ff 0%, #92fe9d 100%) !important;
        color: #1a1a3e !important;
        border: none !important;
        padding: 0.6rem 2rem !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(0, 201, 255, 0.3) !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(0, 201, 255, 0.5) !important;
    }

    /* Footer */
    .footer {
        text-align: center;
        color: rgba(255, 255, 255, 0.3);
        font-size: 0.75rem;
        padding: 2rem 0 1rem 0;
    }

    /* Success/Warning alerts */
    .success-box {
        background: rgba(146, 254, 157, 0.1);
        border: 1px solid rgba(146, 254, 157, 0.3);
        border-radius: 8px;
        padding: 1rem;
        color: #92fe9d;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def _load_access_code() -> str:
    """Read the access code from access_code.txt (same directory as app.py)."""
    try:
        code_file = Path(__file__).parent / "access_code.txt"
        return code_file.read_text(encoding="utf-8").strip()
    except Exception:
        return "slik2026"  # fallback default

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    # --- Login Screen ---
    st.markdown("""
    <div style="max-width: 420px; margin: 4rem auto;">
        <div class="main-header" style="text-align: center;">
            <h1 style="font-size: 1.8rem;">🔐 SLIK Extractor Pro</h1>
            <p>Enter access code to continue</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_left, col_center, col_right = st.columns([1, 1.2, 1])
    with col_center:
        code_input = st.text_input(
            "Access Code",
            type="password",
            placeholder="Enter your access code",
            label_visibility="collapsed",
        )
        login_clicked = st.button("🔓 Login", use_container_width=True)

        if login_clicked:
            correct_code = _load_access_code()
            if code_input == correct_code:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Invalid access code. Please try again.")

        st.markdown("""
        <div style="text-align: center; margin-top: 1rem;">
            <span style="color: rgba(255,255,255,0.4); font-size: 0.8rem;">
                Change code via <code>access_code.txt</code>
            </span>
        </div>
        """, unsafe_allow_html=True)

    st.stop()

# --- Sidebar logout ---
with st.sidebar:
    if st.button("🚪 Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="main-header">
    <h1>📊 SLIK Extractor Pro</h1>
    <p>Parse Indonesian OJK SLIK/iDeb PDF reports → Extract active credit facilities → Export to Excel</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------
st.markdown("### 📁 Upload SLIK PDF Files")
uploaded_files = st.file_uploader(
    "Drag and drop your SLIK/iDeb PDF files here",
    type=["pdf"],
    accept_multiple_files=True,
    help="Upload one or more SLIK PDF reports. All files will be processed and merged into a single output."
)

if uploaded_files:
    st.markdown(f"""
    <div class="info-card">
        <strong>📄 {len(uploaded_files)} file(s) uploaded:</strong><br/>
        {"&nbsp;•&nbsp;".join(f.name for f in uploaded_files)}
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Process Button
# ---------------------------------------------------------------------------
if uploaded_files:
    col_btn, col_spacer = st.columns([1, 3])
    with col_btn:
        process_clicked = st.button("🚀 Process PDFs", use_container_width=True)
else:
    process_clicked = False

# ---------------------------------------------------------------------------
# Processing Pipeline
# ---------------------------------------------------------------------------
if process_clicked and uploaded_files:
    all_records = pd.DataFrame()

    with st.spinner("⏳ Extracting text and parsing facilities..."):
        progress_bar = st.progress(0, text="Starting...")

        for idx, uploaded_file in enumerate(uploaded_files):
            progress_text = f"Processing: {uploaded_file.name} ({idx + 1}/{len(uploaded_files)})"
            progress_bar.progress((idx) / len(uploaded_files), text=progress_text)

            try:
                # Step 1: Extract text
                full_text, nama_debitur = extract_text_from_pdf(uploaded_file)

                if not full_text.strip():
                    st.warning(f"⚠️ {uploaded_file.name}: No text extracted. Skipping.")
                    continue

                # Step 2: Parse facilities
                df = parse_slik_data(full_text, nama_debitur)

                if not df.empty:
                    all_records = pd.concat([all_records, df], ignore_index=True)

            except Exception as e:
                st.error(f"❌ Error processing {uploaded_file.name}: {str(e)}")

        progress_bar.progress(1.0, text="✅ Processing complete!")

    # Store results in session state
    st.session_state["results"] = all_records
    st.session_state["processed"] = True

# ---------------------------------------------------------------------------
# Results Display
# ---------------------------------------------------------------------------
if st.session_state.get("processed") and "results" in st.session_state:
    df_results = st.session_state["results"]

    st.markdown("---")

    if df_results.empty:
        st.markdown("""
        <div class="info-card">
            <strong>ℹ️ No active facilities found.</strong><br/>
            All credit facilities in the uploaded PDFs have Baki Debet = 0 (Lunas / Closed).
        </div>
        """, unsafe_allow_html=True)
    else:
        # Stats row
        st.markdown("### 📈 Extraction Results")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <h3>{len(df_results)}</h3>
                <p>Active Facilities</p>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            unique_debtors = df_results["Nama Debitur"].nunique() if "Nama Debitur" in df_results.columns else 0
            st.markdown(f"""
            <div class="stat-card">
                <h3>{unique_debtors}</h3>
                <p>Unique Debtors</p>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            unique_banks = df_results["Pelapor"].nunique() if "Pelapor" in df_results.columns else 0
            st.markdown(f"""
            <div class="stat-card">
                <h3>{unique_banks}</h3>
                <p>Reporting Banks</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # Data Preview (hide the Raw column)
        st.markdown("### 📋 Data Preview")
        display_df = df_results.drop(columns=["Baki Debet (Raw)"], errors="ignore")
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=min(400, 50 + len(display_df) * 35),
        )

        # ------------------------------------------------------------------
        # Debtor Summary — Outstanding per Unique Debtor
        # ------------------------------------------------------------------
        summary_df = build_debtor_summary(df_results)
        if not summary_df.empty:
            st.markdown("### 💰 Outstanding per Debtor")

            # Summary table (hide raw column)
            display_summary = summary_df.drop(columns=["Total Outstanding (Raw)"], errors="ignore")
            st.dataframe(
                display_summary,
                use_container_width=True,
                hide_index=True,
            )

            # Grand total
            grand_total_raw = summary_df["Total Outstanding (Raw)"].sum()
            from slik_parser import _format_rupiah
            grand_total_str = _format_rupiah(int(grand_total_raw))
            st.markdown(f"""
            <div class="stat-card" style="margin-top: 0.5rem;">
                <h3>{grand_total_str}</h3>
                <p>Grand Total Outstanding (All Debtors)</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            summary_df = None

        # Download button
        st.markdown("")
        excel_bytes = export_to_excel(df_results, summary_df)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"SLIK_Active_Facilities_{timestamp}.xlsx"

        col_dl, col_sp = st.columns([1, 3])
        with col_dl:
            st.download_button(
                label="📥 Download Excel",
                data=excel_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("""
<div class="footer">
    SLIK Extractor Pro • All processing happens locally in memory • No data leaves your machine
</div>
""", unsafe_allow_html=True)
