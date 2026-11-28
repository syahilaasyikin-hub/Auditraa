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
    page_title="Auditraa — Dari Angka ke Bukti",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CUSTOM CSS — REDESIGN TOTAL: TEMA BURGUNDY MODERN, CARD SYSTEM, ANIMASI
# ==============================================================================
custom_css = """
<style>
/* ===== FONT IMPORT ===== */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ===== BASE ===== */
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.stApp {
    background: radial-gradient(circle at 15% 10%, #2b0505 0%, #140101 55%, #0a0000 100%);
    color: #f8f9fa;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #1a0101; }
::-webkit-scrollbar-thumb { background: #5a1a1a; border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: #7d1d1d; }

/* ===== SIDEBAR ===== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a0101 0%, #140000 100%);
    border-right: 1px solid #4a0e0e;
    box-shadow: 4px 0 20px rgba(0,0,0,0.4);
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffb3b3 !important;
    letter-spacing: 0.3px;
}
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stNumberInput label,
[data-testid="stSidebar"] .stFileUploader label {
    color: #e0c0c0 !important;
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ===== ANIMASI KEYFRAMES ===== */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-25px); }
    to { opacity: 1; transform: translateX(0); }
}
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(168, 50, 50, 0.4); }
    50% { box-shadow: 0 0 20px 4px rgba(168, 50, 50, 0.3); }
}
@keyframes floatY {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-4px); }
}
@keyframes borderFlow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* ===== MAIN CONTAINER ===== */
.block-container {
    animation: fadeIn 0.7s ease-out;
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
    max-width: 1500px;
}

/* ===== HERO HEADER ===== */
.hero-header {
    position: relative;
    background: linear-gradient(135deg, #4a0e0e 0%, #2a0303 40%, #1a0101 100%);
    padding: 42px 35px;
    border-radius: 24px;
    border: 1px solid #6b1a1a;
    box-shadow: 0 12px 40px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.05);
    margin-bottom: 28px;
    text-align: center;
    overflow: hidden;
    animation: fadeInUp 0.8s ease-out;
}
.hero-header::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(255,107,107,0.08) 0%, transparent 60%);
    animation: floatY 6s ease-in-out infinite;
    pointer-events: none;
}
.hero-header::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #a83232, #ff6b6b, #a83232, transparent);
    background-size: 200% 100%;
    animation: borderFlow 4s linear infinite;
}
.hero-header h1 {
    position: relative;
    color: #ffffff !important;
    font-size: 2.9rem;
    margin-bottom: 8px;
    font-weight: 800;
    letter-spacing: -0.5px;
    text-shadow: 0 2px 20px rgba(168, 50, 50, 0.5);
}
.hero-header p {
    position: relative;
    color: #d8c8c8;
    font-size: 1.08rem;
    margin: 0;
    font-weight: 500;
}
.hero-header .badge-row {
    display: flex;
    justify-content: center;
    gap: 10px;
    margin-top: 18px;
    flex-wrap: wrap;
    position: relative;
}
.hero-badge {
    display: inline-block;
    padding: 6px 14px;
    background: rgba(168, 50, 50, 0.18);
    border: 1px solid rgba(255, 107, 107, 0.35);
    border-radius: 100px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #ffb3b3;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    animation: fadeInUp 0.9s ease-out backwards;
}
.hero-badge:nth-child(1) { animation-delay: 0.15s; }
.hero-badge:nth-child(2) { animation-delay: 0.25s; }
.hero-badge:nth-child(3) { animation-delay: 0.35s; }

/* ===== ALERT ===== */
[data-testid="stAlert"] {
    background: linear-gradient(135deg, #3b0404 0%, #2a0202 100%) !important;
    border: 1px solid #6b1a1a !important;
    border-left: 4px solid #ff6b6b !important;
    color: #f8f9fa !important;
    border-radius: 12px !important;
    animation: slideInLeft 0.5s ease-out;
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}

/* ===== STREAMLIT CONTAINER (CARD) ===== */
[data-testid="stContainer"] {
    background: linear-gradient(145deg, #260404 0%, #180101 100%) !important;
    border: 1px solid #5a1a1a !important;
    border-radius: 18px !important;
    padding: 22px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45) !important;
    transition: all 0.35s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
    animation: fadeInUp 0.6s ease-out backwards;
}
[data-testid="stContainer"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 14px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 107, 107, 0.25) !important;
    border-color: #8a2a2a !important;
}

/* ===== METRICS (KPI CARDS) ===== */
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #2e0505, #1a0101) !important;
    border: 1px solid #4a0e0e !important;
    border-radius: 14px !important;
    padding: 18px 20px !important;
    transition: all 0.3s ease;
    animation: fadeInUp 0.5s ease-out backwards;
}
[data-testid="stMetric"]:hover {
    border-color: #a83232 !important;
    box-shadow: 0 0 20px rgba(168, 50, 50, 0.25);
    transform: translateY(-2px);
}
[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 1.85rem !important;
    letter-spacing: -0.5px;
}
[data-testid="stMetricLabel"] {
    color: #ffb3b3 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 0.78rem !important;
}

/* ===== BUTTONS ===== */
.stButton > button,
.stDownloadButton > button {
    background: linear-gradient(135deg, #7d1d1d 0%, #a83232 100%) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255,107,107,0.25) !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    padding: 12px 24px !important;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
    width: 100%;
    box-shadow: 0 4px 14px rgba(0,0,0,0.35) !important;
    letter-spacing: 0.3px;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    background: linear-gradient(135deg, #a83232 0%, #d14141 100%) !important;
    transform: translateY(-2px) scale(1.01) !important;
    box-shadow: 0 10px 24px rgba(168, 50, 50, 0.55) !important;
    border-color: #ff6b6b !important;
}
.stButton > button:active,
.stDownloadButton > button:active {
    transform: translateY(0) scale(0.99) !important;
}
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    background: linear-gradient(135deg, #a83232 0%, #d14141 100%) !important;
    animation: pulseGlow 3s ease-in-out infinite;
}

/* ===== TABS ===== */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: linear-gradient(145deg, #1a0101, #140000) !important;
    padding: 10px !important;
    border-radius: 16px !important;
    border: 1px solid #4a0e0e !important;
    margin-bottom: 20px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
.stTabs [data-baseweb="tab"] {
    color: #b3b3b3 !important;
    border-radius: 10px !important;
    padding: 12px 24px !important;
    font-weight: 600 !important;
    font-size: 0.95rem;
    transition: all 0.3s ease !important;
    border: 1px solid transparent !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(168, 50, 50, 0.15) !important;
    color: #ffb3b3 !important;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    background: linear-gradient(135deg, #7d1d1d, #a83232) !important;
    box-shadow: 0 4px 16px rgba(168, 50, 50, 0.4) !important;
    border: 1px solid rgba(255,107,107,0.3) !important;
    animation: fadeIn 0.3s ease-out;
}
.stTabs [data-baseweb="tab-highlight"] { display: none; }
.stTabs [data-baseweb="tab-border"] { display: none; }

/* ===== INPUT FIELDS ===== */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div > div {
    background: #0d0000 !important;
    color: #ffffff !important;
    border: 1px solid #5a1a1a !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    transition: all 0.25s ease !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #ff6b6b !important;
    box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.15) !important;
}

/* ===== DATAFRAME ===== */
[data-testid="stDataFrame"] {
    border: 1px solid #4a0e0e !important;
    border-radius: 12px !important;
    overflow: hidden;
}
[data-testid="stDataFrame"] > div { background: #140000 !important; }
[data-testid="stDataFrame"] [role="columnheader"] {
    background: linear-gradient(135deg, #3a0808, #260404) !important;
    color: #ffb3b3 !important;
    font-weight: 700 !important;
    letter-spacing: 0.3px;
}

/* ===== EXPANDER ===== */
[data-testid="stExpander"] {
    background: linear-gradient(145deg, #260404, #180101) !important;
    border: 1px solid #4a0e0e !important;
    border-radius: 14px !important;
    overflow: hidden;
    transition: all 0.3s ease;
}
[data-testid="stExpander"]:hover { border-color: #8a2a2a !important; }
[data-testid="stExpander"] summary {
    color: #ffb3b3 !important;
    font-weight: 600 !important;
    padding: 14px 18px !important;
}

/* ===== CHAT ===== */
[data-testid="stChatMessage"] {
    background: linear-gradient(145deg, #260404, #180101) !important;
    border: 1px solid #4a0e0e !important;
    border-radius: 14px !important;
    padding: 16px 20px !important;
    margin-bottom: 12px;
    animation: fadeInUp 0.4s ease-out;
}
[data-testid="stChatInput"] textarea {
    background: #0d0000 !important;
    color: #fff !important;
    border: 1px solid #5a1a1a !important;
    border-radius: 12px !important;
}

/* ===== SECTION TITLES ===== */
h1, h2, h3, h4 { color: #f8f9fa !important; letter-spacing: -0.3px; }
h3 { font-weight: 700 !important; }
.section-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 1.25rem;
    font-weight: 700;
    color: #ffffff;
    margin: 4px 0 14px 0;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255,107,107,0.15);
}
.section-title .icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px; height: 34px;
    background: linear-gradient(135deg, #7d1d1d, #a83232);
    border-radius: 10px;
    font-size: 1rem;
    box-shadow: 0 4px 12px rgba(168,50,50,0.35);
}

/* ===== WELCOME SCREEN ===== */
.welcome-card {
    background: linear-gradient(135deg, #2e0505 0%, #1a0101 100%);
    border: 1px dashed #6b1a1a;
    border-radius: 24px;
    padding: 60px 40px;
    text-align: center;
    margin-top: 30px;
    box-shadow: inset 0 0 40px rgba(0,0,0,0.6), 0 10px 40px rgba(0,0,0,0.5);
    animation: fadeInUp 0.8s ease-out;
    position: relative;
    overflow: hidden;
}
.welcome-card::before {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(circle at 50% 0%, rgba(255,107,107,0.06), transparent 60%);
    pointer-events: none;
}
.welcome-card .welcome-icon {
    font-size: 4rem;
    margin-bottom: 12px;
    animation: floatY 3.5s ease-in-out infinite;
    display: inline-block;
}
.welcome-card h2 {
    color: #ffb3b3 !important;
    border: none;
    font-size: 2rem;
    margin-bottom: 10px;
    position: relative;
}
.welcome-card p {
    color: #d1d1d1;
    font-size: 1.05rem;
    position: relative;
}
.welcome-card .hint {
    display: inline-block;
    margin-top: 22px;
    padding: 12px 22px;
    background: rgba(168,50,50,0.12);
    border: 1px solid rgba(255,107,107,0.25);
    border-radius: 12px;
    color: #ffb3b3;
    font-size: 0.95rem;
    font-weight: 500;
}

/* ===== LEGEND CHIP ===== */
.legend-chip {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 600;
    margin: 3px 4px 3px 0;
    letter-spacing: 0.3px;
}
.chip-ok { background: rgba(102,179,102,0.15); color: #9be09b; border: 1px solid rgba(102,179,102,0.35); }
.chip-warn { background: rgba(255,179,102,0.15); color: #ffd0a3; border: 1px solid rgba(255,179,102,0.35); }
.chip-err { background: rgba(255,77,77,0.15); color: #ff9b9b; border: 1px solid rgba(255,77,77,0.35); }
.chip-info { background: rgba(102,153,255,0.15); color: #a8c2ff; border: 1px solid rgba(102,153,255,0.35); }

/* ===== MONO ===== */
code, .mono {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85em;
    background: rgba(255,107,107,0.08) !important;
    color: #ffb3b3 !important;
    padding: 2px 6px;
    border-radius: 5px;
}

/* ===== DIVIDER ===== */
hr { border-color: #4a0e0e !important; opacity: 0.6; }

/* ===== PANEL HEADER ===== */
.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 1px solid rgba(255,107,107,0.12);
}
.panel-header h2 {
    margin: 0;
    font-size: 1.4rem;
    font-weight: 700;
    color: #ffffff;
}
.panel-header .sub {
    color: #a0a0a0;
    font-size: 0.85rem;
    margin-top: 2px;
}

/* ===== FOOTER NOTE ===== */
.footer-note {
    text-align: center;
    color: #6b1a1a;
    font-size: 0.8rem;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #2a0505;
    letter-spacing: 0.5px;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
pio.templates.default = "plotly_dark"

# --- FUNGSI LOGIKA (TIDAK DIUBAH) ---
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
                content = response.text
                if content and content.strip(): return content.strip()
                return "⚠️ Model tidak mengembalikan teks."
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if any(err in err_str for err in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "high demand"]) and attempt < 2:
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

# --- HERO HEADER ---
st.markdown("""
<div class="hero-header">
    <h1>📑 Auditraa</h1>
    <p><strong>Dari Angka ke Bukti, Otomatis Terdokumentasi.</strong> &nbsp;|&nbsp; <em>Kode menghitung, AI menulis, manusia memutuskan.</em></p>
    <div class="badge-row">
        <span class="hero-badge">🧠 AI-Assisted</span>
        <span class="hero-badge">🔍 Evidence-Based</span>
        <span class="hero-badge">📑 Audit-Ready</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.warning("🔒 **STATUS KELUARAN: SELALU DRAFT** — Seluruh keluaran AI wajib direview, dikoreksi, dan diputuskan oleh auditor.")

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 10px 0 18px 0;">
        <div style="font-size:2.2rem; animation: floatY 3s ease-in-out infinite; display:inline-block;">⚙️</div>
        <h2 style="margin:6px 0 0 0; font-size:1.3rem;">Parameter Audit</h2>
        <p style="color:#8a5a5a; font-size:0.8rem; margin:4px 0 0 0;">Konfigurasi dasar pengujian</p>
    </div>
    """, unsafe_allow_html=True)

    client_name = st.text_input("🏢 Nama Entitas / Klien", value="PT Nusantara Sejahtera Tbk (Demo)")
    period = st.text_input("📅 Periode Audit", value="Tahun Buku 2025")
    materiality = st.number_input(
        "💰 Ambang Materialitas (Rp)", min_value=1_000_000, max_value=100_000_000_000,
        value=50_000_000, step=5_000_000, format="%d",
    )

    st.divider()
    st.markdown("#### 📂 Unggah Data Saldo")
    uploaded_file = st.file_uploader("Unggah file Excel (.xlsx)", type=["xlsx"], label_visibility="collapsed")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("▶️ Demo", use_container_width=True):
            st.session_state["use_demo_data"] = True
            reset_generated_outputs()
            st.rerun()
    with col_b:
        st.download_button(
            label="📥 Contoh", data=generate_sample_excel(),
            file_name="contoh_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()
    st.markdown("""
    <div style="padding:14px; background:rgba(168,50,50,0.08); border:1px solid rgba(255,107,107,0.2); border-radius:12px;">
        <div style="font-weight:700; color:#ffb3b3; font-size:0.85rem; margin-bottom:8px; letter-spacing:0.5px;">📖 LEGENDA TICK MARK</div>
        <div class="legend-chip chip-ok">✓ Cocok / di bawah ambang</div>
        <div class="legend-chip chip-err">⊗ Selisih signifikan</div>
        <div class="legend-chip chip-warn">? Bukti belum tersedia</div>
    </div>
    """, unsafe_allow_html=True)

# --- PEMUATAN DATA (TIDAK DIUBAH) ---
raw_df = None
if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try: raw_df = pd.read_excel(uploaded_file)
    except Exception as exc: st.error(f"❌ Gagal membaca file: `{exc}`"); st.stop()
elif st.session_state["use_demo_data"]:
    try: raw_df = pd.read_excel(generate_sample_excel())
    except Exception as exc: st.error(f"❌ Gagal memuat demo: `{exc}`"); st.stop()

# --- WELCOME SCREEN ---
if raw_df is None or raw_df.empty:
    st.markdown("""
    <div class="welcome-card">
        <div class="welcome-icon">👋</div>
        <h2>Selamat Datang di Dashboard Auditraa</h2>
        <p>Belum ada data kertas kerja yang dimuat.</p>
        <div class="hint">
            📂 Unggah file Excel (.xlsx) di panel kiri, atau klik <b>▶️ Demo</b> untuk melihat simulasi kerja Auditraa.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# --- VALIDASI (TIDAK DIUBAH) ---
is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(f"❌ Struktur kolom tidak sesuai. Kolom belum ada: **{', '.join(missing_cols)}**.")
    st.stop()

wp_df = process_working_paper(raw_df, float(materiality))
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(build_llm_payload(wp_df, client_name, period, float(materiality)), indent=2, ensure_ascii=False)

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Kertas Kerja", "📝 Ringkasan Temuan", "✉️ Management Letter", "💬 Tanya Agen"
])

# ==============================================================================
# TAB 1: KERTAS KERJA
# ==============================================================================
with tab1:
    st.markdown(f"""
    <div class="panel-header">
        <div>
            <h2>📊 Lead Schedule</h2>
            <div class="sub">{client_name} &nbsp;•&nbsp; {period}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    total_accounts = len(wp_df)
    high_count = int((wp_df["Severity"] == "High").sum())
    med_count = int((wp_df["Severity"] == "Medium").sum())
    missing_count = len(missing_ev_df)

    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        st.metric("Total Akun Diuji", f"{total_accounts} Akun")
    with col2:
        st.metric("Ambang Materialitas", f"Rp {materiality:,.0f}")
    with col3:
        st.metric("Selisih Signifikan", f"{high_count} High / {med_count} Med")
    with col4:
        st.metric("Bukti Belum Tersedia", f"{missing_count} Akun", delta_color="inverse")

    st.write("")

    col_table, col_chart = st.columns([1.25, 1], gap="medium")
    with col_table:
        with st.container(border=True):
            st.markdown('<div class="section-title"><span class="icon">📋</span>Tabel Kertas Kerja</div>', unsafe_allow_html=True)
            display_df = wp_df.copy()
            display_df["Evidence_Ref"] = display_df["Evidence_Ref"].replace("", "BUKTI BELUM TERSEDIA")
            st.dataframe(
                display_df.style.format({
                    "Budget": "Rp {:,.0f}", "Actual": "Rp {:,.0f}",
                    "Variance": "Rp {:,.0f}", "Variance_Pct": "{:.2f}%",
                }), use_container_width=True, hide_index=True,
            )

    with col_chart:
        with st.container(border=True):
            st.markdown('<div class="section-title"><span class="icon">📈</span>Grafik Selisih</div>', unsafe_allow_html=True)
            fig = px.bar(
                wp_df, x="Category", y="Variance", color="Severity", text="WP_Ref",
                color_discrete_map={"High": "#ff4d4d", "Medium": "#ffb366", "Low": "#66b366"},
                labels={"Category": "Akun", "Variance": "Selisih [Rp]", "Severity": "Severity"},
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f8f9fa", family="Plus Jakarta Sans"),
                margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(
                    bgcolor="rgba(26,1,1,0.7)", bordercolor="#5a1a1a", borderwidth=1,
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                ),
            )
            fig.add_hline(y=float(materiality), line_dash="dash", line_color="#ff4d4d", annotation_text="Batas (+)")
            fig.add_hline(y=-float(materiality), line_dash="dash", line_color="#ff4d4d", annotation_text="Batas (-)")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    if not missing_ev_df.empty:
        with st.expander(f"⚠️ Peringatan: {missing_count} Akun Tanpa Referensi Bukti (Klik untuk melihat)", expanded=False):
            with st.container(border=True):
                st.dataframe(
                    missing_ev_df.style.format({"Budget": "Rp {:,.0f}", "Actual": "Rp {:,.0f}", "Variance": "Rp {:,.0f}"}),
                    use_container_width=True,
