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
# CUSTOM CSS: TEMA BURGUNDY MODERN, CARD LAYOUT, & ANIMASI
# ==============================================================================
custom_css = """
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    /* Base Font & Warna Latar Utama */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at top left, #2b0505 0%, #140101 100%);
        color: #f8f9fa;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #1a0101;
        border-right: 1px solid #4a0e0e;
    }

    /* Animasi Fade-in untuk konten utama */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(15px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .block-container {
        animation: fadeIn 0.8s ease-out;
    }

    /* Animasi Slide-in untuk Alert */
    @keyframes slideIn {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    [data-testid="stAlert"] {
        background-color: #3b0404 !important;
        border: 1px solid #6b1a1a !important;
        color: #f8f9fa !important;
        border-radius: 10px;
        animation: slideIn 0.5s ease-out;
    }

    /* HEADER DASHBOARD KUSTOM */
    .hero-header {
        background: linear-gradient(135deg, #4a0e0e 0%, #1a0101 100%);
        padding: 35px;
        border-radius: 20px;
        border: 1px solid #6b1a1a;
        box-shadow: 0 10px 30px rgba(0,0,0,0.6);
        margin-bottom: 30px;
        text-align: center;
        transition: transform 0.4s ease;
    }
    .hero-header:hover {
        transform: translateY(-3px);
    }
    .hero-header h1 {
        color: #ffffff !important;
        font-size: 2.8rem;
        margin-bottom: 10px;
        font-weight: 800;
        text-shadow: 2px 2px 8px rgba(0,0,0,0.6);
    }
    .hero-header p {
        color: #d1d1d1;
        font-size: 1.15rem;
        margin: 0;
        font-weight: 500;
    }

    /* KARTU (Card Styling) */
    [data-testid="stContainer"], .stCard {
        background: linear-gradient(145deg, #2e0505, #1a0101) !important;
        border: 1px solid #5a1a1a !important;
        border-radius: 15px !important;
        padding: 20px !important;
        box-shadow: 0 6px 15px rgba(0, 0, 0, 0.4) !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
    }
    [data-testid="stContainer"]:hover, .stCard:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 0 12px 25px rgba(0, 0, 0, 0.6) !important;
        border-color: #ff6b6b !important;
    }

    /* METRIK KARTU (KPI) */
    [data-testid="stMetric"] {
        background: transparent;
        border: none;
        padding: 10px;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff;
        font-weight: 800;
        font-size: 2rem;
    }
    [data-testid="stMetricLabel"] {
        color: #ffb3b3;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.9rem;
    }

    /* TOMBOL INTERAKTIF */
    .stButton>button, .stDownloadButton>button {
        background: linear-gradient(90deg, #7d1d1d 0%, #a83232 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 700;
        padding: 12px 24px;
        transition: all 0.3s ease;
        width: 100%;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background: linear-gradient(90deg, #a83232 0%, #d14141 100%);
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 8px 20px rgba(168, 50, 50, 0.6);
    }

    /* TABS STYLING */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: #1a0101;
        padding: 10px 15px;
        border-radius: 12px;
        border: 1px solid #4a0e0e;
    }
    .stTabs [data-baseweb="tab"] {
        color: #b3b3b3;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stTabs [aria-selected="true"] {
        color: #ffffff;
        background-color: #7d1d1d;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    }

    /* INPUT FIELDS */
    .stTextInput>div>div>input, .stNumberInput>div>div>input {
        background-color: #0d0000;
        color: #ffffff;
        border: 1px solid #5a1a1a;
        border-radius: 8px;
        padding: 10px;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #ff6b6b;
        box-shadow: 0 0 0 2px rgba(255, 107, 107, 0.3);
    }

    /* WELCOME SCREEN CARD */
    .welcome-card {
        background: linear-gradient(135deg, #2e0505 0%, #1a0101 100%);
        border: 1px dashed #6b1a1a;
        border-radius: 20px;
        padding: 50px;
        text-align: center;
        margin-top: 30px;
        box-shadow: inset 0 0 30px rgba(0,0,0,0.6);
    }
    .welcome-card h2 { color: #ffb3b3 !important; border: none; font-size: 2.2rem; }
    .welcome-card p { color: #d1d1d1; font-size: 1.1rem; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
pio.templates.default = "plotly_dark"

# --- FUNGSI LOGIKA ---
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

# --- HEADER DASHBOARD ---
st.markdown("""
<div class="hero-header">
    <h1>📑 Auditraa</h1>
    <p><strong>Dari Angka ke Bukti, Otomatis Terdokumentasi.</strong> | <em>Kode menghitung, AI menulis, manusia memutuskan.</em></p>
</div>
""", unsafe_allow_html=True)

st.warning("🔒 **STATUS KELUARAN: SELALU DRAFT** — Seluruh keluaran AI wajib direview, dikoreksi, dan diputuskan oleh auditor.")

# --- SIDEBAR: PARAMETER AUDIT ---
with st.sidebar:
    st.header("⚙️ Parameter Audit")
    client_name = st.text_input("Nama Entitas / Klien", value="PT Nusantara Sejahtera Tbk (Demo)")
    period = st.text_input("Periode Audit", value="Tahun Buku 2025")
    materiality = st.number_input(
        "Ambang Materialitas (Rp)", min_value=1_000_000, max_value=100_000_000_000,
        value=50_000_000, step=5_000_000, format="%d",
    )

    st.divider()
    st.subheader("📂 Unggah Data Saldo")
    uploaded_file = st.file_uploader("Unggah file Excel (.xlsx)", type=["xlsx"])

    if st.button("▶️ Muat Data Demo", use_container_width=True):
        st.session_state["use_demo_data"] = True
        reset_generated_outputs()
        st.rerun()
        
    st.download_button(
        label="📥 Unduh Contoh Excel", data=generate_sample_excel(),
        file_name="contoh_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Legenda Tick Mark:**\n- `✓` : Cocok / di bawah ambang\n- `⊗` : Selisih signifikan\n- `?` : `BUKTI BELUM TERSEDIA`")

# --- PEMUATAN DATA ---
raw_df = None
if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try: raw_df = pd.read_excel(uploaded_file)
    except Exception as exc: st.error(f"❌ Gagal membaca file: `{exc}`"); st.stop()
elif st.session_state["use_demo_data"]:
    try: raw_df = pd.read_excel(generate_sample_excel())
    except Exception as exc: st.error(f"❌ Gagal memuat demo: `{exc}`"); st.stop()

# ==============================================================================
# TAMPILAN JIKA DATA KOSONG (WELCOME SCREEN)
# ==============================================================================
if raw_df is None or raw_df.empty:
    st.markdown("""
    <div class="welcome-card">
        <h2>👋 Selamat Datang di Dashboard Auditraa</h2>
        <p>Belum ada data kertas kerja yang dimuat.</p>
        <p style="font-size: 1rem; color: #a3a3a3; margin-top: 20px;">
            Silakan <b>unggah file Excel (.xlsx)</b> pada menu di sebelah kiri,<br>
            atau klik tombol <b>▶️ Muat Data Demo</b> untuk melihat simulasi kerja Auditraa.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# --- VALIDASI DATA ---
is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(f"❌ Struktur kolom tidak sesuai. Kolom belum ada: **{', '.join(missing_cols)}**.")
    st.stop()

wp_df = process_working_paper(raw_df, float(materiality))
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(build_llm_payload(wp_df, client_name, period, float(materiality)), indent=2, ensure_ascii=False)

# --- TABS UTAMA ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Kertas Kerja", "📝 Ringkasan Temuan", "✉️ Management Letter", "💬 Tanya Agen"
])

# ==============================================================================
# TAB 1: KERTAS KERJA
# ==============================================================================
with tab1:
    st.subheader(f"Lead Schedule — {client_name} ({period})")

    # Baris Metrik Kartu (KPI Cards)
    total_accounts = len(wp_df)
    high_count = int((wp_df["Severity"] == "High").sum())
    med_count = int((wp_df["Severity"] == "Medium").sum())
    missing_count = len(missing_ev_df)

    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1:
        with st.container(border=True):
            st.metric("Total Akun Diuji", f"{total_accounts} Akun")
    with col2:
        with st.container(border=True):
            st.metric("Ambang Materialitas", f"Rp {materiality:,.0f}")
    with col3:
        with st.container(border=True):
            st.metric("Selisih Signifikan", f"{high_count} High / {med_count} Med")
    with col4:
        with st.container(border=True):
            st.metric("Bukti Belum Tersedia", f"{missing_count} Akun", delta_color="inverse")

    st.write("") # Spacer

    # Tabel dan Grafik Berdampingan dalam Card
    col_table, col_chart = st.columns([1.2, 1], gap="medium")
    with col_table:
        with st.container(border=True):
            st.markdown("### 📋 Tabel Kertas Kerja")
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
            st.markdown("### 📈 Grafik Selisih")
            fig = px.bar(
                wp_df, x="Category", y="Variance", color="Severity", text="WP_Ref",
                color_discrete_map={"High": "#ff4d4d", "Medium": "#ffb366", "Low": "#66b366"},
                labels={"Category": "Akun", "Variance": "Selisih [Rp]", "Severity": "Severity"},
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f8f9fa"), margin=dict(l=10, r=10, t=10, b=10)
            )
            fig.add_hline(y=float(materiality), line_dash="dash", line_color="#ff4d4d", annotation_text="Batas (+)")
            fig.add_hline(y=-float(materiality), line_dash="dash", line_color="#ff4d4d", annotation_text="Batas (-)")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    # Peringatan Bukti Hilang
    if not missing_ev_df.empty:
        with st.expander(f"⚠️ Peringatan: {missing_count} Akun Tanpa Referensi Bukti (Klik untuk melihat)", expanded=False):
            with st.container(border=True):
                st.dataframe(
                    missing_ev_df.style.format({"Budget": "Rp {:,.0f}", "Actual": "Rp {:,.0f}", "Variance": "Rp {:,.0f}"}),
                    use_container_width=True, hide_index=True,
                )

    st.write("") # Spacer

    # Penjelasan AI
    with st.container(border=True):
        st.markdown("### 🤖 Penjelasan Hasil Kertas Kerja oleh AI (Draft)")
        account_options = ["Semua Akun (Ringkasan Kertas Kerja)"] + [f"{row['WP_Ref']} — {row['Category']}" for _, row in wp_df.iterrows()]
        selected_scope = st.selectbox("Pilih cakupan penjelasan:", options=account_options, key="explain_scope_select")

        if st.button("🧠 Minta Penjelasan AI", key="btn_explain_wp"):
            if selected_scope == "Semua Akun (Ringkasan Kertas Kerja)":
                target_payload = payload_json
                scope_instruction = "Jelaskan ringkasan kertas kerja seluruh akun, akun dengan selisih terbesar, dan akun bertanda '?'."
            else:
                selected_wp = selected_scope.split(" — ")[0].strip()
                filtered_df = wp_df[wp_df["WP_Ref"] == selected_wp]
                target_payload = json.dumps(build_llm_payload(filtered_df, client_name, period, float(materiality)), indent=2, ensure_ascii=False)
                scope_instruction = f"Jelaskan rinci akun **{selected_scope}**: Budget, Actual, Variance, Severity, dan status Evidence_Ref."

            system_prompt_explain = """Anda adalah asisten auditor. Awali dengan: **[DRAFT - WAJIB REVIEW AUDITOR]**. HANYA gunakan angka dari JSON. Jika bukti kosong, tulis "BUKTI BELUM TERSEDIA"."""
            user_prompt_explain = f"Klien: {client_name} | Periode: {period} | Materialitas: Rp {materiality:,.0f}\nTugas: {scope_instruction}\nData: {target_payload}"

            with st.spinner("Menyusun penjelasan..."):
                st.session_state["ai_explanation"] = call_llm(system_prompt_explain, user_prompt_explain)

        if st.session_state["ai_explanation"]:
            is_ok_exp, alien_nums_exp = check_numbers(st.session_state["ai_explanation"], wp_df, float(materiality))
            if is_ok_exp: st.success("✅ **Pemeriksa Angka:** Seluruh angka cocok dengan data sumber.")
            else: st.error(f"🚨 **Peringatan Angka:** Ditemukan angka tidak valid: `{', '.join(alien_nums_exp)}`.")
            
            st.markdown("---")
            st.markdown(st.session_state["ai_explanation"])

# ==============================================================================
# TAB 2: RINGKASAN TEMUAN
# ==============================================================================
with tab2:
    st.subheader("Penyusunan Draf Ringkasan Temuan Audit")
    with st.container(border=True):
        st.markdown("Menyusun draf narasi temuan dengan struktur **Kondisi, Kriteria, Penyebab, Dampak, Rekomendasi, dan Bukti**.")
        if st.button("✨ Susun Ringkasan Temuan", type="primary", use_container_width=True):
            system_prompt_findings = """Anda adalah asisten auditor. Awali dengan: **[DRAFT - PERLU REVIEW AUDITOR]**. HANYA gunakan angka dari JSON. Setiap temuan WAJIB mencantumkan WP Ref, Kondisi, Kriteria, Penyebab (hipotesis), Dampak, Rekomendasi, dan Bukti."""
            user_prompt_findings = f"Klien: {client_name}, Periode: {period}, Materialitas: Rp {materiality:,.0f}.\nData: {payload_json}"
            
            with st.spinner("Menyusun draf..."):
                st.session_state["findings_draft"] = call_llm(system_prompt_findings, user_prompt_findings)

        if st.session_state["findings_draft"]:
            is_ok, alien_numbers = check_numbers(st.session_state["findings_draft"], wp_df, float(materiality))
            if is_ok: st.success("✅ **Pemeriksa Angka:** Angka pada narasi sesuai data.")
            else: st.error(f"🚨 **Peringatan Angka:** Ditemukan angka tidak valid: `{', '.join(alien_numbers)}`.")
            
            st.divider()
            st.markdown(st.session_state["findings_draft"])

# ==============================================================================
# TAB 3: MANAGEMENT LETTER
# ==============================================================================
with tab3:
    st.subheader("Penyusunan Draf Management Letter & Ekspor")
    with st.container(border=True):
        st.markdown("Menyusun surat rekomendasi lengkap dengan ruang tanggapan manajemen dan ekspor ke Excel 3 sheet.")
        
        col_ml1, col_ml2 = st.columns([1, 1], gap="medium")
        with col_ml1:
            if st.button("✉️ Susun Management Letter", type="primary", use_container_width=True):
                system_prompt_letter = """Anda adalah asisten auditor. Awali dengan: **[DRAFT MANAGEMENT LETTER - WAJIB REVIEW AUDITOR]**. HANYA gunakan angka dari JSON."""
                user_prompt_letter = f"Klien: {client_name}, Periode: {period}, Materialitas: Rp {materiality:,.0f}.\nData: {payload_json}\nTemuan: {st.session_state['findings_draft'] or 'Rujuk JSON.'}"
                
                with st.spinner("Menyusun surat..."):
                    st.session_state["mgmt_letter_draft"] = call_llm(system_prompt_letter, user_prompt_letter)

        with col_ml2:
            excel_data = export_audit_excel(
                df=wp_df, findings_text=st.session_state["findings_draft"],
                mgmt_letter_text=st.session_state["mgmt_letter_draft"],
                client_name=client_name, period=period, materiality=float(materiality),
            )
            safe_client = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in client_name)
            st.download_button(
                label="📥 Unduh Excel (3 Sheet)", data=excel_data,
                file_name=f"Auditraa_Draft_{safe_client}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if st.session_state["mgmt_letter_draft"]:
            is_ok_ml, alien_numbers_ml = check_numbers(st.session_state["mgmt_letter_draft"], wp_df, float(materiality))
            if is_ok_ml: st.success("✅ **Pemeriksa Angka:** Angka pada surat sesuai data.")
            else: st.error(f"🚨 **Peringatan Angka:** Ditemukan angka tidak valid: `{', '.join(alien_numbers_ml)}`.")
            
            st.divider()
            st.markdown(st.session_state["mgmt_letter_draft"])

# ==============================================================================
# TAB 4: TANYA AGEN
# ==============================================================================
with tab4:
    st.subheader("💬 Tanya Agen Kertas Kerja")
    with st.container(border=True):
        st.caption("Ajukan pertanyaan seputar saldo, varians, WP Ref, atau ketersediaan bukti.")
        
        for item in st.session_state["chat_history"]:
            with st.chat_message(item["role"]):
                st.markdown(item["content"])

        question = st.chat_input("Contoh: Akun mana yang bertanda '?' dan berapa selisihnya?")
        if question:
            st.session_state["chat_history"].append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)

            system_prompt_chat = f"""Anda adalah asisten audit. Jawab HANYA berdasarkan JSON. Sertakan WP Ref. Jika bukti tidak ada, tulis "BUKTI BELUM TERSEDIA".
Klien: {client_name} | Periode: {period} | Materialitas: Rp {materiality:,.0f}
Data: {payload_json}"""

            with st.chat_message("assistant"):
                with st.spinner("Menjawab..."):
                    reply = call_llm(system_prompt_chat, question)
                    st.markdown(reply)

            st.session_state["chat_history"].append({"role": "assistant", "content": reply})
