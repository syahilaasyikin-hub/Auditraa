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
    page_title="Auditraa | Premium Audit Dashboard",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CSS PREMIUM: DARK GLASSMORPHISM, ROSE GOLD ACCENTS, & ANIMASI
# ==============================================================================
custom_css = """
<style>
    /* Import Font Modern & Elegan */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    /* Base */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3, .brand-title {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Background Utama: Deep Burgundy Gradient */
    .stApp {
        background: radial-gradient(circle at top left, #2c0606 0%, #0d0101 100%);
        color: #e0e0e0;
    }

    /* Sidebar: Efek Kaca Gelap */
    [data-testid="stSidebar"] {
        background: rgba(20, 2, 2, 0.6) !important;
        backdrop-filter: blur(15px);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Sembunyikan Header Streamlit Bawaan */
    header {visibility: hidden;}

    /* --- ANIMASI MASUK (FADE IN UP) --- */
    @keyframes fadeUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .block-container {
        animation: fadeUp 0.6s ease-out forwards;
    }

    /* --- KARTU GLASSMORPHISM (BENTO BOX STYLE) --- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(45, 10, 10, 0.4) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 215, 0, 0.15) !important; /* Aksen Rose Gold tipis */
        border-radius: 16px !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4) !important;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
    }
    
    /* Efek Hover pada Kartu */
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px 0 rgba(0, 0, 0, 0.6), 0 0 15px 0 rgba(255, 215, 0, 0.1) !important;
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
    }

    /* --- STYLING METRIK (KPI) --- */
    [data-testid="stMetric"] {
        background: transparent;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        font-family: 'Outfit', sans-serif;
    }
    [data-testid="stMetricLabel"] {
        color: #d4af37 !important; /* Rose Gold Text */
        font-weight: 600 !important;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        font-size: 0.85rem !important;
    }

    /* --- TOMBOL ELEGAN (ROSE GOLD GRADIENT) --- */
    .stButton>button, .stDownloadButton>button {
        background: linear-gradient(135deg, #b76e79 0%, #e8a87c 100%) !important;
        color: #1a0505 !important; /* Teks gelap agar kontras */
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        padding: 10px 24px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(232, 168, 124, 0.2) !important;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        transform: translateY(-2px) scale(1.02) !important;
        box-shadow: 0 8px 25px rgba(232, 168, 124, 0.4) !important;
        color: #000000 !important;
    }

    /* --- TABS MODERN (PILL SHAPE) --- */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        gap: 10px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        padding-bottom: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        color: #a3a3a3;
        padding: 8px 20px;
        transition: all 0.3s;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(232, 168, 124, 0.15);
        border: 1px solid #e8a87c;
        color: #ffffff !important;
        font-weight: 600;
    }

    /* --- INPUT FIELDS --- */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, [data-testid="stFileUploadDropzone"] {
        background-color: rgba(0, 0, 0, 0.2) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        color: #ffffff !important;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #e8a87c !important;
        box-shadow: 0 0 0 2px rgba(232, 168, 124, 0.2) !important;
    }

    /* --- HEADER KUSTOM --- */
    .header-glass {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 30px;
        background: linear-gradient(90deg, rgba(45, 10, 10, 0.6) 0%, rgba(20, 2, 2, 0.2) 100%);
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 215, 0, 0.1);
        margin-bottom: 25px;
        animation: fadeUp 0.5s ease-out;
    }
    .header-glass h1 {
        margin: 0;
        font-size: 2rem;
        background: linear-gradient(to right, #ffffff, #e8a87c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    .header-glass p {
        margin: 5px 0 0 0;
        color: #a3a3a3;
        font-size: 0.95rem;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
pio.templates.default = "plotly_dark"

# ==============================================================================
# FUNGSI LOGIKA (TIDAK BERUBAH)
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
        <div style="margin-bottom: 20px;">
            <h2 class="brand-title" style="color: #ffffff; margin:0;">💎 Auditraa</h2>
            <p style="color: #d4af37; font-size: 0.8rem; letter-spacing: 1px;">PREMIUM AUDIT SUITE</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### ⚙️ Parameter Audit")
    client_name = st.text_input("Nama Entitas / Klien", value="PT Nusantara Sejahtera Tbk")
    period = st.text_input("Periode Audit", value="Tahun Buku 2025")
    materiality = st.number_input("Ambang Materialitas (Rp)", min_value=1_000_000, max_value=100_000_000_000, value=50_000_000, step=5_000_000, format="%d")

    st.markdown("---")
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

    st.markdown("---")
    st.caption("🛡️ **Keamanan:** Gunakan data fiktif untuk pengujian.")

# ==============================================================================
# HEADER MAIN AREA
# ==============================================================================
st.markdown("""
<div class="header-glass">
    <div>
        <h1>Dashboard Kertas Kerja</h1>
        <p>Sistem deteksi anomali saldo dan penyusunan draf audit berbasis AI.</p>
    </div>
    <div style="font-size: 2.5rem;">⚖️</div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# PEMUATAN DATA & WELCOME SCREEN
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
    st.info("👋 **Selamat Datang!** Silakan unggah file Excel (.xlsx) melalui panel di sebelah kiri, atau klik **Muat Data Demo** untuk melihat kekuatan sistem.")
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
# TAB 1: KERTAS KERJA (BENTO GRID LAYOUT)
# ------------------------------------------------------------------------------
with tab1:
    # KPI Cards (Glassmorphism)
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

    # Area Tabel & Grafik
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
                color_discrete_map={"High": "#ff4d4d", "Medium": "#f4a261", "Low": "#2a9d8f"},
                labels={"Category": "", "Variance": "Selisih [Rp]", "Severity": ""},
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e0e0e0"), margin=dict(l=10, r=10, t=10, b=10)
            )
            fig.add_hline(y=float(materiality), line_dash="dot", line_color="#d4af37", annotation_text="Batas (+)")
            fig.add_hline(y=-float(materiality), line_dash="dot", line_color="#d4af37", annotation_text="Batas (-)")
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
