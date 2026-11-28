import json
import os
import time
import pandas as pd
import plotly.express as px
import plotly.io as pio
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from streamlit.errors import StreamlitSecretNotFoundError

from audit_logic import (
    build_llm_payload,
    check_numbers,
    export_audit_excel,
    generate_sample_excel,
    get_missing_evidence,
    process_working_paper,
    validate_columns,
)

load_dotenv()

MODEL_NAME = "gemini-3.8-flash"
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

st.set_page_config(
    page_title="Auditraa | Smart Audit Engine",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CSS PREMIUM: SOFT BURGUNDY, ANIMATED BACKGROUND, & GLASSMORPHISM
# ==============================================================================
custom_css = """
<style>
    /* Import Font Elegan & Modern */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    /* Base Styling */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #2a0a0a; /* Fallback */
    }
    h1, h2, h3, .brand-title {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Menyembunyikan elemen bawaan Streamlit yang tidak diperlukan */
    header {visibility: hidden;}
    .stApp { background: transparent !important; }

    /* --- ANIMASI LATAR BELAKANG (MESH GRADIENT / BLOBS) --- */
    .bg-container {
        position: fixed;
        top: 0; left: 0; width: 100vw; height: 100vh;
        z-index: -1;
        overflow: hidden;
        background: linear-gradient(135deg, #2a0a0a 0%, #4a1518 100%);
    }
    
    .blob {
        position: absolute;
        border-radius: 50%;
        filter: blur(100px);
        opacity: 0.6;
        animation: floatBlob 20s infinite alternate ease-in-out;
    }
    
    .blob-1 {
        width: 600px; height: 600px;
        background: rgba(180, 60, 70, 0.4); /* Soft Burgundy Glow */
        top: -100px; left: -100px;
    }
    
    .blob-2 {
        width: 500px; height: 500px;
        background: rgba(232, 168, 124, 0.2); /* Rose Gold Glow */
        bottom: -100px; right: -100px;
        animation-delay: -5s;
        animation-duration: 25s;
    }
    
    .blob-3 {
        width: 400px; height: 400px;
        background: rgba(220, 100, 100, 0.25);
        top: 40%; left: 40%;
        animation-delay: -10s;
        animation-duration: 30s;
    }

    @keyframes floatBlob {
        0% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(100px, 50px) scale(1.1); }
        100% { transform: translate(-50px, 150px) scale(0.9); }
    }

    /* --- ANIMASI MASUK KONTEN --- */
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .block-container {
        animation: fadeInUp 0.8s ease-out forwards;
    }

    /* --- SIDEBAR --- */
    [data-testid="stSidebar"] {
        background: rgba(20, 5, 5, 0.6) !important;
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(232, 168, 124, 0.15);
    }

    /* --- HEADER KUSTOM (Bento Style) --- */
    .header-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 30px 40px;
        background: linear-gradient(135deg, rgba(74, 21, 24, 0.4) 0%, rgba(30, 8, 8, 0.7) 100%);
        backdrop-filter: blur(16px);
        border-radius: 20px;
        border: 1px solid rgba(232, 168, 124, 0.2);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;
    }
    .header-container::before {
        content: '';
        position: absolute;
        top: 0; left: 0; width: 4px; height: 100%;
        background: linear-gradient(to bottom, #e8a87c, #fdfbf7);
    }
    
    .header-content h1 {
        margin: 0;
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(to right, #ffffff, #fdfbf7, #e8a87c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
    }
    .header-content p {
        margin: 8px 0 0 0;
        color: #d1d1d1;
        font-size: 1.05rem;
        font-weight: 400;
    }

    /* --- ANIMASI VISUAL DI HEADER (RADAR DATA) --- */
    .visual-core-container {
        position: relative;
        width: 80px;
        height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .core-orb {
        width: 20px;
        height: 20px;
        background: #e8a87c;
        border-radius: 50%;
        box-shadow: 0 0 20px #e8a87c, 0 0 40px rgba(232, 168, 124, 0.5);
        animation: pulseOrb 2s infinite alternate;
        z-index: 2;
    }
    .core-ring-1 {
        position: absolute;
        width: 60px;
        height: 60px;
        border: 2px solid rgba(232, 168, 124, 0.2);
        border-top: 2px solid #e8a87c;
        border-radius: 50%;
        animation: spinRing 3s linear infinite;
    }
    .core-ring-2 {
        position: absolute;
        width: 80px;
        height: 80px;
        border: 1px dashed rgba(232, 168, 124, 0.3);
        border-radius: 50%;
        animation: spinRingReverse 5s linear infinite;
    }
    
    @keyframes spinRing { 100% { transform: rotate(360deg); } }
    @keyframes spinRingReverse { 100% { transform: rotate(-360deg); } }
    @keyframes pulseOrb {
        0% { transform: scale(1); box-shadow: 0 0 10px #e8a87c; }
        100% { transform: scale(1.3); box-shadow: 0 0 30px #e8a87c, 0 0 50px rgba(232, 168, 124, 0.8); }
    }

    /* --- KARTU GLASSMORPHISM --- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(60, 15, 15, 0.4), rgba(30, 5, 5, 0.6)) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(232, 168, 124, 0.15) !important;
        border-radius: 16px !important;
        padding: 20px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.4s ease !important;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(232, 168, 124, 0.15) !important;
        border: 1px solid rgba(232, 168, 124, 0.4) !important;
    }

    /* --- METRIK (KPI) --- */
    [data-testid="stMetric"] { background: transparent; }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
        font-family: 'Outfit', sans-serif;
    }
    [data-testid="stMetricLabel"] {
        color: #e8a87c !important; 
        font-weight: 600 !important;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        font-size: 0.8rem !important;
    }

    /* --- TOMBOL ELEGAN --- */
    .stButton>button, .stDownloadButton>button {
        background: linear-gradient(135deg, #e8a87c 0%, #f5d6c6 100%) !important;
        color: #2a0a0a !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-family: 'Outfit', sans-serif;
        padding: 10px 24px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(232, 168, 124, 0.2) !important;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        transform: translateY(-2px) scale(1.02) !important;
        box-shadow: 0 8px 25px rgba(232, 168, 124, 0.5) !important;
        color: #000000 !important;
    }

    /* --- TABS MODERN --- */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        gap: 10px;
        border-bottom: 1px solid rgba(232, 168, 124, 0.2);
        padding-bottom: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        color: #b3b3b3;
        padding: 10px 20px;
        transition: all 0.3s;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(232, 168, 124, 0.1);
        border: 1px solid #e8a87c;
        color: #e8a87c !important;
        font-weight: 600;
        box-shadow: 0 2px 10px rgba(232, 168, 124, 0.1);
    }

    /* --- INPUT FIELDS --- */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, [data-testid="stFileUploadDropzone"] {
        background-color: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid rgba(232, 168, 124, 0.2) !important;
        border-radius: 8px !important;
        color: #ffffff !important;
        transition: all 0.3s ease;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #e8a87c !important;
        box-shadow: 0 0 0 2px rgba(232, 168, 124, 0.2) !important;
    }
    
    /* Alert Box */
    [data-testid="stAlert"] {
        background-color: rgba(60, 15, 15, 0.8) !important;
        border: 1px solid #e8a87c !important;
        color: #fcfbf9 !important;
        border-radius: 10px;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# Inject Background HTML Elements (Harus diletakkan setelah CSS)
st.markdown("""
<div class="bg-container">
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="blob blob-3"></div>
</div>
""", unsafe_allow_html=True)

pio.templates.default = "plotly_dark"

# ==============================================================================
# FUNGSI LOGIKA BACKEND
# ==============================================================================
def get_api_key() -> str | None:
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip(): return env_key.strip()
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY")
        if secret_key and str(secret_key).strip(): return str(secret_key).strip()
    except Exception: pass
    return None

def get_gemini_client() -> genai.Client | None:
    api_key = get_api_key()
    return genai.Client(api_key=api_key) if api_key else None

def call_llm(system_prompt: str, user_prompt: str) -> str:
    client = get_gemini_client()
    if client is None:
        return "⚠️ **GEMINI_API_KEY belum dikonfigurasi.**"
    models_to_try = list(dict.fromkeys([MODEL_NAME] + FALLBACK_MODELS))
    last_exc = None
    for model_id in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_id, contents=user_prompt,
                    config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0),
                )
                if response.text and response.text.strip(): return response.text.strip()
                return "⚠️ Model tidak mengembalikan teks."
            except Exception as exc:
                last_exc = exc
                if any(err in str(exc) for err in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1)); continue
                break
    return f"⚠️ Server Gemini sibuk: `{last_exc}`"

def init_session_state() -> None:
    defaults = {"ai_explanation": "", "findings_draft": "", "mgmt_letter_draft": "", "chat_history": [], "use_demo_data": False}
    for key, val in defaults.items():
        if key not in st.session_state: st.session_state[key] = val

def reset_generated_outputs() -> None:
    st.session_state.update({"ai_explanation": "", "findings_draft": "", "mgmt_letter_draft": "", "chat_history": []})

init_session_state()

# ==============================================================================
# SIDEBAR: CONTROL PANEL
# ==============================================================================
with st.sidebar:
    st.markdown("""
        <div style="margin-bottom: 25px; text-align: center;">
            <h2 class="brand-title" style="color: #ffffff; margin:0; font-size: 2rem;">Auditraa<span style="color:#e8a87c;">.</span></h2>
            <p style="color: #e8a87c; font-size: 0.8rem; letter-spacing: 2px; text-transform: uppercase;">Smart Audit Engine</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='border-bottom: 1px solid rgba(232,168,124,0.2); margin-bottom: 20px;'></div>", unsafe_allow_html=True)
    st.markdown("### ⚙️ Parameter Audit")
    client_name = st.text_input("Nama Entitas / Klien", value="PT Nusantara Sejahtera Tbk")
    period = st.text_input("Periode Audit", value="Tahun Buku 2025")
    materiality = st.number_input("Ambang Materialitas (Rp)", min_value=1_000_000, max_value=100_000_000_000, value=50_000_000, step=5_000_000, format="%d")

    st.markdown("<div style='border-bottom: 1px solid rgba(232,168,124,0.2); margin: 20px 0;'></div>", unsafe_allow_html=True)
    st.markdown("### 📂 Manajemen Data")
    uploaded_file = st.file_uploader("Unggah file (.xlsx)", type=["xlsx"])
    
    if st.button("▶️ Muat Data Demo", use_container_width=True):
        st.session_state["use_demo_data"] = True
        reset_generated_outputs()
        st.rerun()
        
    st.download_button(
        label="📥 Unduh Contoh Excel", data=generate_sample_excel(),
        file_name="contoh_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown("<div style='border-bottom: 1px solid rgba(232,168,124,0.2); margin: 20px 0;'></div>", unsafe_allow_html=True)
    st.caption("🛡️ **Keamanan:** Jangan unggah data klien riil tanpa izin. Gunakan data fiktif untuk pengujian.")

# ==============================================================================
# HEADER MAIN AREA
# ==============================================================================
st.markdown("""
<div class="header-container">
    <div class="header-content">
        <h1>Auditraa: Smart Audit Engine</h1>
        <p>Sistem Cerdas Deteksi Anomali Saldo & Penyusunan Draf Audit.</p>
    </div>
    <div class="visual-core-container">
        <div class="core-ring-2"></div>
        <div class="core-ring-1"></div>
        <div class="core-orb"></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# PEMUATAN DATA
# ==============================================================================
raw_df = None
if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try: raw_df = pd.read_excel(uploaded_file)
    except Exception as exc: st.error(f"❌ Gagal membaca file: `{exc}`"); st.stop()
elif st.session_state["use_demo_data"]:
    try: raw_df = pd.read_excel(generate_sample_excel())
    except Exception as exc: st.error(f"❌ Gagal memuat demo: `{exc}`"); st.stop()

if raw_df is None or raw_df.empty:
    st.info("👋 **Selamat Datang di Auditraa.** Silakan unggah file Excel (.xlsx) melalui panel di sebelah kiri, atau klik **Muat Data Demo** untuk melihat simulasi kerja sistem.")
    st.stop()

is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(f"❌ Struktur kolom tidak sesuai. Kolom belum ada: **{', '.join(missing_cols)}**.")
    st.stop()

wp_df = process_working_paper(raw_df, float(materiality))
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(build_llm_payload(wp_df, client_name, period, float(materiality)), indent=2, ensure_ascii=False)

# ==============================================================================
# MAIN TABS
# ==============================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Kertas Kerja", "📝 Ringkasan Temuan", "✉️ Management Letter", "💬 Tanya Agen"
])

# ------------------------------------------------------------------------------
# TAB 1: KERTAS KERJA
# ------------------------------------------------------------------------------
with tab1:
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.metric("Total Akun", f"{len(wp_df)}", "Akun diuji")
    with col2:
        with st.container(border=True):
            st.metric("Materialitas", f"Rp {materiality/1_000_000} Jt", "Batas toleransi")
    with col3:
        high_med = int((wp_df['Severity'] == 'High').sum()) + int((wp_df['Severity'] == 'Medium').sum())
        with st.container(border=True):
            st.metric("Signifikan", f"{high_med}", "Butuh perhatian")
    with col4:
        with st.container(border=True):
            st.metric("Bukti Hilang", f"{len(missing_ev_df)}", "Segera dilengkapi")

    st.write("")

    # Tabel & Grafik
    col_left, col_right = st.columns([1.2, 1])
    
    with col_left:
        with st.container(border=True):
            st.markdown("#### 📋 Tabel Kertas Kerja")
            display_df = wp_df.copy()
            display_df["Evidence_Ref"] = display_df["Evidence_Ref"].replace("", "BUKTI BELUM TERSEDIA")
            st.dataframe(
                display_df.style.format({
                    "Budget": "Rp {:,.0f}", "Actual": "Rp {:,.0f}",
                    "Variance": "Rp {:,.0f}", "Variance_Pct": "{:.2f}%",
                }), 
                use_container_width=True, hide_index=True, height=380
            )

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📈 Analisis Varians")
            fig = px.bar(
                wp_df, x="Category", y="Variance", color="Severity", text="WP_Ref",
                color_discrete_map={"High": "#ff4d4d", "Medium": "#e8a87c", "Low": "#2a9d8f"},
                labels={"Category": "", "Variance": "Selisih [Rp]", "Severity": ""},
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e0e0e0"), margin=dict(l=10, r=10, t=10, b=10)
            )
            fig.add_hline(y=float(materiality), line_dash="dot", line_color="#e8a87c", annotation_text="Batas (+)")
            fig.add_hline(y=-float(materiality), line_dash="dot", line_color="#e8a87c", annotation_text="Batas (-)")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    if not missing_ev_df.empty:
        with st.expander(f"⚠️ **Peringatan Kritis:** {len(missing_ev_df)} Akun Tanpa Referensi Bukti", expanded=False):
            with st.container(border=True):
                st.dataframe(
                    missing_ev_df.style.format({"Budget": "Rp {:,.0f}", "Actual": "Rp {:,.0f}", "Variance": "Rp {:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )

    st.write("")

    # AI Assistant Box
    with st.container(border=True):
        st.markdown("#### 🤖 AI Asisten: Penjelasan Hasil")
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            account_options = ["Semua Akun (Ringkasan)"] + [f"{row['WP_Ref']} — {row['Category']}" for _, row in wp_df.iterrows()]
            selected_scope = st.selectbox("Pilih cakupan:", options=account_options, label_visibility="collapsed")
        with col_btn:
            btn_explain = st.button("✨ Analisis", use_container_width=True)

        if btn_explain:
            target_payload = payload_json if selected_scope == "Semua Akun (Ringkasan)" else json.dumps(build_llm_payload(wp_df[wp_df["WP_Ref"] == selected_scope.split(" — ")[0].strip()], client_name, period, float(materiality)), indent=2)
            with st.spinner("Menyusun penjelasan..."):
                st.session_state["ai_explanation"] = call_llm("Anda adalah asisten auditor. Awali dengan: **[DRAFT - WAJIB REVIEW AUDITOR]**.", f"Data: {target_payload}")

        if st.session_state["ai_explanation"]:
            st.success("✅ Verifikasi Angka Selesai.")
            st.markdown(st.session_state["ai_explanation"])

# ------------------------------------------------------------------------------
# TAB 2: RINGKASAN TEMUAN
# ------------------------------------------------------------------------------
with tab2:
    with st.container(border=True):
        st.markdown("#### 📝 Penyusunan Draf Ringkasan Temuan")
        if st.button("✨ Susun Draf Temuan", type="primary", use_container_width=True):
            with st.spinner("Menyusun draf..."):
                st.session_state["findings_draft"] = call_llm("Anda adalah asisten auditor. Awali dengan: **[DRAFT - PERLU REVIEW AUDITOR]**.", f"Data: {payload_json}")
        if st.session_state["findings_draft"]:
            st.markdown("---")
            st.markdown(st.session_state["findings_draft"])

# ------------------------------------------------------------------------------
# TAB 3: MANAGEMENT LETTER
# ------------------------------------------------------------------------------
with tab3:
    with st.container(border=True):
        st.markdown("#### ✉️ Draf Management Letter & Ekspor")
        col_ml1, col_ml2 = st.columns([1, 1])
        with col_ml1:
            if st.button("✉️ Susun Surat", type="primary", use_container_width=True):
                with st.spinner("Menyusun surat..."):
                    st.session_state["mgmt_letter_draft"] = call_llm("Anda adalah asisten auditor. Awali dengan: **[DRAFT MANAGEMENT LETTER]**.", f"Data: {payload_json}")
        with col_ml2:
            excel_data = export_audit_excel(
                df=wp_df, findings_text=st.session_state["findings_draft"],
                mgmt_letter_text=st.session_state["mgmt_letter_draft"],
                client_name=client_name, period=period, materiality=float(materiality),
            )
            safe_client = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in client_name)
            st.download_button("📥 Unduh Excel (3 Sheet)", data=excel_data, file_name=f"Auditraa_{safe_client}.xlsx", use_container_width=True)
        
        if st.session_state["mgmt_letter_draft"]:
            st.markdown("---")
            st.markdown(st.session_state["mgmt_letter_draft"])

# ------------------------------------------------------------------------------
# TAB 4: TANYA AGEN
# ------------------------------------------------------------------------------
with tab4:
    with st.container(border=True):
        st.markdown("#### 💬 Tanya Agen Kertas Kerja")
        for item in st.session_state["chat_history"]:
            with st.chat_message(item["role"]):
                st.markdown(item["content"])

        question = st.chat_input("Contoh: Akun mana yang selisihnya paling besar?")
        if question:
            st.session_state["chat_history"].append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Menjawab..."):
                    reply = call_llm("Jawab HANYA berdasarkan data JSON.", f"Data: {payload_json}\nPertanyaan: {question}")
                    st.markdown(reply)
            st.session_state["chat_history"].append({"role": "assistant", "content": reply})
