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
# CSS PREMIUM: PARALLAX, STARS, INTERACTIVE 3D HOLOGRAPHIC CUBE
# ==============================================================================
custom_css = """
<style>
    /* Import Font Elegan & Modern */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    /* Base Styling */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #1c0404; /* Fallback */
        overflow-x: hidden;
    }
    h1, h2, h3, .brand-title {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Sembunyikan header bawaan Streamlit & buat app transparan */
    header {visibility: hidden;}
    .stApp { background: transparent !important; }

    /* ======================================================================== */
    /* BACKGROUND: TWINKLING STARS, PARALLAX BLOBS, & DATA GRID                 */
    /* ======================================================================== */
    .bg-container {
        position: fixed;
        top: 0; left: 0; width: 100vw; height: 100vh;
        z-index: -1;
        overflow: hidden;
        background: radial-gradient(circle at top right, #3d0a0a 0%, #120101 100%);
        perspective: 1000px;
    }
    
    .data-grid {
        position: absolute;
        top: -50%; left: -50%; width: 200%; height: 200%;
        background-image: 
            linear-gradient(rgba(232, 168, 124, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(232, 168, 124, 0.03) 1px, transparent 1px);
        background-size: 50px 50px;
        transform: rotateX(60deg) translateZ(-200px);
        animation: gridMove 30s linear infinite;
    }
    @keyframes gridMove {
        0% { transform: rotateX(60deg) translateZ(-200px) translateY(0); }
        100% { transform: rotateX(60deg) translateZ(-200px) translateY(50px); }
    }

    .parallax-layer {
        position: absolute;
        border-radius: 50%;
        filter: blur(100px);
        transition: transform 0.1s ease-out;
    }
    .blob-1 { width: 50vw; height: 50vw; background: rgba(160, 40, 50, 0.3); top: -10%; left: -10%; }
    .blob-2 { width: 40vw; height: 40vw; background: rgba(232, 168, 124, 0.15); bottom: -10%; right: -10%; }

    .stars-container { position: absolute; width: 100%; height: 100%; }
    .star {
        position: absolute;
        background: #fff;
        border-radius: 50%;
        box-shadow: 0 0 4px #fff, 0 0 8px #e8a87c;
        animation: twinkle linear infinite;
    }
    @keyframes twinkle {
        0%, 100% { opacity: 0.1; transform: scale(0.8); }
        50% { opacity: 1; transform: scale(1.2); }
    }

    /* ======================================================================== */
    /* UI ELEMENTS                                                              */
    /* ======================================================================== */

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .block-container { animation: fadeInUp 0.8s ease-out forwards; }

    [data-testid="stSidebar"] {
        background: rgba(20, 5, 5, 0.6) !important;
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(232, 168, 124, 0.15);
    }

    .header-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 40px 50px;
        background: linear-gradient(135deg, rgba(60, 15, 15, 0.4) 0%, rgba(20, 5, 5, 0.6) 100%);
        backdrop-filter: blur(16px);
        border-radius: 24px;
        border: 1px solid rgba(232, 168, 124, 0.2);
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        margin-bottom: 30px;
        position: relative;
        overflow: hidden;
    }
    .header-content { z-index: 2; max-width: 60%; }
    .header-content h1 {
        margin: 0;
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(to right, #ffffff, #fdfbf7, #e8a87c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -1px;
    }
    .header-content p {
        margin: 10px 0 0 0;
        color: #d1d1d1;
        font-size: 1.1rem;
    }

    /* Ilustrasi 3D Cube */
    .illustration-wrapper {
        width: 200px; height: 200px;
        perspective: 800px;
        z-index: 2;
        position: relative;
        display: flex; align-items: center; justify-content: center;
    }
    .cube-container {
        width: 90px; height: 90px;
        position: absolute;
        transform-style: preserve-3d;
        animation: rotateCube 12s linear infinite;
        transition: all 0.5s ease;
    }
    @keyframes rotateCube {
        0% { transform: rotateX(-20deg) rotateY(0deg); }
        100% { transform: rotateX(-20deg) rotateY(360deg); }
    }
    .illustration-wrapper:hover .cube-container {
        animation-play-state: paused;
        transform: rotateX(-10deg) rotateY(45deg) scale(1.2);
        filter: drop-shadow(0 0 20px rgba(232, 168, 124, 0.8));
    }
    .cube-face {
        position: absolute; width: 90px; height: 90px;
        background: rgba(60, 15, 15, 0.85);
        border: 1.5px solid #e8a87c;
        box-shadow: inset 0 0 15px rgba(232, 168, 124, 0.3), 0 0 10px rgba(232, 168, 124, 0.2);
        backdrop-filter: blur(4px);
    }
    .face-front  { transform: translateZ(45px); display: flex; align-items: flex-end; justify-content: center; gap: 6px; padding-bottom: 10px; }
    .face-back   { transform: rotateY(180deg) translateZ(45px); }
    .face-right  { transform: rotateY(90deg) translateZ(45px); display: flex; flex-direction: column; justify-content: center; padding: 15px; gap: 6px; }
    .face-left   { transform: rotateY(-90deg) translateZ(45px); }
    .face-top    { transform: rotateX(90deg) translateZ(45px); display: flex; align-items: center; justify-content: center; }
    .face-bottom { transform: rotateX(-90deg) translateZ(45px); }
    .cube-bar { width: 12px; background: linear-gradient(to top, #d4af37, #fdfbf7); border-radius: 2px 2px 0 0; box-shadow: 0 0 8px #e8a87c; }
    .cube-bar.b1 { height: 25px; }
    .cube-bar.b2 { height: 50px; animation: pulseBar 1.5s infinite alternate; }
    .cube-bar.b3 { height: 35px; animation: pulseBar 1.5s infinite alternate 0.5s; }
    @keyframes pulseBar { 0% { height: 20px; } 100% { height: 50px; } }
    .cube-line { width: 100%; height: 4px; background: rgba(232, 168, 124, 0.5); border-radius: 2px; }
    .cube-line.short { width: 60%; }
    .cube-core {
        width: 30px; height: 30px;
        background: #e8a87c;
        border-radius: 50%;
        box-shadow: 0 0 20px #e8a87c, 0 0 40px rgba(232, 168, 124, 0.6);
        animation: pulseCore 1s infinite alternate;
    }
    @keyframes pulseCore { 0% { transform: scale(0.8); } 100% { transform: scale(1.2); } }
    .orbit-ring {
        position: absolute;
        width: 160px; height: 160px;
        border: 2px dashed rgba(232, 168, 124, 0.4);
        border-radius: 50%;
        transform: rotateX(70deg) rotateY(15deg);
        animation: spinRing 10s linear infinite;
        box-shadow: 0 0 15px rgba(232, 168, 124, 0.1);
    }
    @keyframes spinRing { 100% { transform: rotateX(70deg) rotateY(15deg) rotateZ(360deg); } }

    /* Card & UI */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(60, 15, 15, 0.5), rgba(30, 5, 5, 0.7)) !important;
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
    [data-testid="stMetric"] { background: transparent; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 2rem !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #e8a87c !important; font-weight: 600 !important; text-transform: uppercase; font-size: 0.8rem !important; }
    .stButton>button, .stDownloadButton>button {
        background: linear-gradient(135deg, #e8a87c 0%, #f5d6c6 100%) !important;
        color: #2a0a0a !important;
        border: none !important; border-radius: 10px !important;
        font-weight: 700 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(232, 168, 124, 0.2) !important;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        transform: translateY(-2px) scale(1.02) !important;
        box-shadow: 0 8px 25px rgba(232, 168, 124, 0.5) !important;
    }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; gap: 10px; border-bottom: 1px solid rgba(232, 168, 124, 0.2); padding-bottom: 10px; }
    .stTabs [data-baseweb="tab"] { background: rgba(255, 255, 255, 0.03); border-radius: 8px; color: #b3b3b3; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background: rgba(232, 168, 124, 0.1); border: 1px solid #e8a87c; color: #e8a87c !important; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input { background-color: rgba(0, 0, 0, 0.3) !important; border: 1px solid rgba(232, 168, 124, 0.2) !important; color: #fff !important; }
    [data-testid="stAlert"] { background-color: rgba(60, 15, 15, 0.8) !important; border: 1px solid #e8a87c !important; border-radius: 10px; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==============================================================================
# INJEKSI HTML UNTUK BACKGROUND
# ==============================================================================
import random

stars_html = ""
for _ in range(40):
    top = random.randint(0, 100)
    left = random.randint(0, 100)
    size = random.randint(1, 3)
    delay = random.uniform(0, 5)
    duration = random.uniform(2, 6)
    stars_html += f'<div class="star" style="top: {top}%; left: {left}%; width: {size}px; height: {size}px; animation-delay: {delay}s; animation-duration: {duration}s;"></div>'

background_html = f"""
<div class="bg-container">
    <div class="data-grid"></div>
    <div class="parallax-layer blob-1"></div>
    <div class="parallax-layer blob-2"></div>
    <div class="stars-container">
        {stars_html}
    </div>
</div>
"""
st.markdown(background_html, unsafe_allow_html=True)

parallax_script = """
<script>
document.addEventListener('mousemove', (e) => {
    const x = (window.innerWidth / 2 - e.clientX) / 50;
    const y = (window.innerHeight / 2 - e.clientY) / 50;
    const layers = document.querySelectorAll('.parallax-layer');
    layers.forEach((layer, index) => {
        const speed = (index + 1) * 0.5;
        layer.style.transform = `translate(${x * speed}px, ${y * speed}px)`;
    });
});
</script>
"""
st.markdown(parallax_script, unsafe_allow_html=True)

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
    if client is None: return "⚠️ **GEMINI_API_KEY belum dikonfigurasi.**"
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
            except Exception as exc:
                last_exc = exc
                if any(err in str(exc) for err in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1)); continue
                break
    return f"⚠️ Server Gemini sibuk: `{last_exc}`"

def call_llm_stream(system_prompt: str, user_prompt: str):
    client = get_gemini_client()
    if client is None:
        yield "⚠️ **GEMINI_API_KEY belum dikonfigurasi.**"
        return
    
    models_to_try = list(dict.fromkeys([MODEL_NAME] + FALLBACK_MODELS))
    last_exc = None
    
    for model_id in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content_stream(
                    model=model_id, contents=user_prompt,
                    config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0),
                )
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return 
            except Exception as exc:
                last_exc = exc
                if any(err in str(exc) for err in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
    yield f"⚠️ Server Gemini sibuk atau API Key bermasalah: `{last_exc}`"

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
    st.caption("🛡️ **Keamanan:** Jangan unggah data klien riil tanpa izin.")

# ==============================================================================
# HEADER MAIN AREA
# ==============================================================================
st.markdown("""
<div class="header-container">
    <div class="header-content">
        <h1>Auditraa: Smart Audit Engine</h1>
        <p>Sistem Cerdas Deteksi Anomali Saldo & Penyusunan Draf Audit.</p>
    </div>
    <div class="illustration-wrapper">
        <div class="orbit-ring"></div>
        <div class="cube-container">
            <div class="cube-face face-front">
                <div class="cube-bar b1"></div>
                <div class="cube-bar b2"></div>
                <div class="cube-bar b3"></div>
            </div>
            <div class="cube-face face-right">
                <div class="cube-line"></div>
                <div class="cube-line short"></div>
                <div class="cube-line"></div>
                <div class="cube-line short"></div>
            </div>
            <div class="cube-face face-top">
                <div class="cube-core"></div>
            </div>
            <div class="cube-face face-back"></div>
            <div class="cube-face face-left"></div>
            <div class="cube-face face-bottom"></div>
        </div>
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

    # --- AI ASSISTANT DENGAN STREAMING (TANPA SPINNER) ---
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
            system_prompt_explain = "Anda adalah asisten auditor. Awali dengan: **[DRAFT - WAJIB REVIEW AUDITOR]**. HANYA gunakan angka dari JSON. Jika bukti kosong, tulis 'BUKTI BELUM TERSEDIA'."
            user_prompt_explain = f"Data: {target_payload}"
            
            # Status dan placeholder output
            status_text = st.empty()
            status_text.info("⏳ Menghubungkan ke server AI... (Membaca data)")
            
            response_placeholder = st.empty()
            full_text = ""
            
            for chunk in call_llm_stream(system_prompt_explain, user_prompt_explain):
                if full_text == "":
                    status_text.empty() # Hapus status info saat teks pertama muncul
                full_text += chunk
                response_placeholder.markdown(full_text + "▌")
                
            response_placeholder.markdown(full_text)
            st.session_state["ai_explanation"] = full_text

        if st.session_state["ai_explanation"]:
            is_ok_exp, alien_nums_exp = check_numbers(st.session_state["ai_explanation"], wp_df, float(materiality))
            if is_ok_exp: st.success("✅ **Pemeriksa Angka:** Seluruh angka cocok dengan data sumber.")
            else: st.error(f"🚨 **Peringatan Angka:** Ditemukan angka tidak valid: `{', '.join(alien_nums_exp)}`.")
            
            if not btn_explain:
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
