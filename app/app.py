import os
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

from audit_logic import (
    validate_columns,
    process_working_paper,
    get_missing_evidence,
    build_llm_payload,
    check_numbers,
    export_audit_excel,
    generate_sample_excel,
)

# Muat environment variables (.env untuk lokal, st.secrets untuk Streamlit Cloud)
load_dotenv()

MODEL_NAME = "openai/gpt-oss-20b"

st.set_page_config(
    page_title="Auditraa — Dari Angka ke Bukti, Otomatis Terdokumentasi",
    page_icon="📑",
    layout="wide",
)


def get_groq_client() -> Groq | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key and "GROQ_API_KEY" in st.secrets:
        api_key = st.secrets["GROQ_API_KEY"]
    if not api_key:
        return None
    return Groq(api_key=api_key)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    client = get_groq_client()
    if client is None:
        return "⚠️ **GROQ_API_KEY belum dikonfigurasi.** Tambahkan `GROQ_API_KEY` di file `.env` atau Streamlit Secrets."
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"⚠️ Terjadi kesalahan saat menghubungi Groq API: `{str(e)}`"


# Inisialisasi Session State
if "findings_draft" not in st.session_state:
    st.session_state["findings_draft"] = ""
if "mgmt_letter_draft" not in st.session_state:
    st.session_state["mgmt_letter_draft"] = ""
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "use_demo_data" not in st.session_state:
    st.session_state["use_demo_data"] = False

# --- HEADER & BRANDING ---
st.title("📑 Auditraa")
st.caption("**Dari Angka ke Bukti, Otomatis Terdokumentasi.** | *Kode menghitung, AI menulis, manusia memutuskan.*")
st.warning("🔒 **STATUS KELUARAN: SELALU DRAFT** — Seluruh hasil yang disusun AI bersifat draf kerja dan wajib direview serta diputuskan oleh auditor.")

# --- SIDEBAR: PARAMETER AUDIT ---
with st.sidebar:
    st.header("⚙️ Parameter Audit")
    client_name = st.text_input("Nama Entitas / Klien", value="PT Nusantara Sejahtera Tbk (Demo)")
    period = st.text_input("Periode Audit", value="Tahun Buku 2025")
    materiality = st.number_input(
        "Ambang Materialitas (Rp)",
        min_value=1_000_000,
        max_value=100_000_000_000,
        value=50_000_000,
        step=5_000_000,
        format="%d",
    )

    st.divider()
    st.subheader("📂 Unggah Data Saldo")
    uploaded_file = st.file_uploader(
        "Unggah file Excel (.xlsx)",
        type=["xlsx"],
        help="Kolom wajib: Category, Budget, Actual. Kolom opsional: Evidence_Ref",
    )

    col_demo1, col_demo2 = st.columns(2)
    with col_demo1:
        if st.button("▶️ Muat Demo", use_container_width=True):
            st.session_state["use_demo_data"] = True
            st.session_state["findings_draft"] = ""
            st.session_state["mgmt_letter_draft"] = ""
            st.session_state["chat_history"] = []
    with col_demo2:
        st.download_button(
            label="📥 Contoh Excel",
            data=generate_sample_excel(),
            file_name="contoh_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()
    st.markdown(
        """
        **Legenda Tick Mark:**
        - `✓` : Selisih di bawah 50% materialitas & bukti tersedia
        - `⊗` : Selisih ≥ 50% materialitas (Medium / High)
        - `?` : `BUKTI BELUM TERSEDIA`
        """
    )
    st.info("🛡️ **Keamanan Data:** Jangan unggah data klien rahasia ke API publik tanpa izin. Gunakan data fiktif untuk simulasi/demo.")

# --- PEMUATAN & PEMROSESAN DATA DETERMINISTIK ---
raw_df = None
if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try:
        raw_df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Gagal membaca file Excel: {e}")
        st.stop()
elif st.session_state["use_demo_data"]:
    raw_df = pd.read_excel(generate_sample_excel())

if raw_df is None:
    st.info("👈 Silakan **unggah file Excel (.xlsx)** di panel kiri atau klik **▶️ Muat Demo** untuk mencoba skenario presentasi Auditraa.")
    st.stop()

is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(f"Struktur kolom tidak valid. Kolom wajib yang hilang: **{', '.join(missing_cols)}**")
    st.stop()

wp_df = process_working_paper(raw_df, materiality)
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(build_llm_payload(wp_df, client_name, period, materiality), indent=2, ensure_ascii=False)

# --- EMPAT TAB UTAMA ---
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Kertas Kerja",
    "2️⃣ Ringkasan Temuan",
    "3️⃣ Management Letter",
    "4️⃣ Tanya Agen",
])

# ==============================================================================
# TAB 1: KERTAS KERJA
# ==============================================================================
with tab1:
    st.subheader(f"Lead Schedule — {client_name} ({period})")

    # Metrik Ringkas
    total_accounts = len(wp_df)
    high_count = int((wp_df["Severity"] == "High").sum())
    med_count = int((wp_df["Severity"] == "Medium").sum())
    missing_count = len(missing_ev_df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Akun Diuji", f"{total_accounts} Akun")
    m2.metric("Materialitas", f"Rp {materiality:,.0f}")
    m3.metric("Selisih Signifikan (High / Med)", f"{high_count} High / {med_count} Med")
    m4.metric("Bukti Belum Tersedia (?)", f"{missing_count} Akun", delta_color="inverse")

    # Peringatan Bukti Hilang
    if not missing_ev_df.empty:
        st.error(f"⚠️ **Peringatan Kelengkapan Bukti:** Ditemukan **{len(missing_ev_df)} akun** dengan status `BUKTI BELUM TERSEDIA` (Tick Mark `?`).")
        with st.expander("Lihat Daftar Akun Tanpa Referensi Bukti", expanded=True):
            st.dataframe(missing_ev_df, use_container_width=True, hide_index=True)

    # Tabel Kertas Kerja
    st.markdown("### Tabel Kertas Kerja Pemeriksaan")
    display_df = wp_df.copy()
    display_df["Evidence_Ref"] = display_df["Evidence_Ref"].replace("", "BUKTI BELUM TERSEDIA")
    st.dataframe(
        display_df.style.format({
            "Budget": "Rp {:,.0f}",
            "Actual": "Rp {:,.0f}",
            "Variance": "Rp {:,.0f}",
            "Variance_Pct": "{:.2f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.caption("**Legenda Tick Mark:** `✓` Cocok / di bawah ambang | `⊗` Selisih melebihi ambang (≥ 50% materialitas) | `?` Bukti belum tersedia")

    # Grafik Selisih (Plotly)
    st.markdown("### Visualisasi Varians per Akun")
    fig = px.bar(
        wp_df,
        x="Category",
        y="Variance",
        color="Severity",
        text="WP_Ref",
        color_discrete_map={"High": "#DC2626", "Medium": "#F59E0B", "Low": "#16A34A"},
        labels={"Category": "Akun", "Variance": "Selisih (Rp)", "Severity": "Tingkat Risiko"},
        title="Perbandingan Selisih (Actual - Budget) Terhadap Tingkat Severity",
    )
    fig.add_hline(y=materiality, line_dash="dash", line_color="#DC2626", annotation_text="Ambang Materialitas (+)")
    fig.add_hline(y=-materiality, line_dash="dash", line_color="#DC2626", annotation_text="Ambang Materialitas (-)")
    st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# TAB 2: RINGKASAN TEMUAN
# ==============================================================================
with tab2:
    st.subheader("Penyusunan Draf Ringkasan Temuan Audit")
    st.markdown("AI akan menyusun narasi terstruktur (**Kondisi, Kriteria, Penyebab [hipotesis], Dampak, Rekomendasi, Bukti**) hanya untuk akun dengan risiko signifikan atau bukti kosong.")

    if st.button("✨ Susun Ringkasan Temuan", type="primary"):
        sys_prompt = """Anda adalah asisten auditor profesional yang menyusun DRAF Ringkasan Temuan Audit dalam Bahasa Indonesia.
ATURAN KERAS (GUARDRAILS):
1. Labeli seluruh dokumen di bagian paling atas sebagai: **[DRAFT - PERLU REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis tercantum di dalam JSON data sumber. DILARANG KERAS menghitung ulang, membulatkan sendiri, atau mengarang angka baru.
3. Setiap temuan WAJIB mencantumkan WP Ref (contoh: C-1) dan disusun dengan format baku:
   - **WP Ref & Akun**
   - **Kondisi** (sebutkan angka Budget, Actual, Variance, dan Variance % sesuai data)
   - **Kriteria** (rujukan PSAK / SA yang relevan secara umum sebagai acuan awal review)
   - **Penyebab (Hipotesis)** (WAJIB diawali kata "Diduga..." karena belum dikonfirmasi ke manajemen)
   - **Dampak**
   - **Rekomendasi**
   - **Bukti** (tulis kode Evidence_Ref persis dari data; jika kosong wajib tulis "BUKTI BELUM TERSEDIA")
4. DILARANG menuduh adanya kecurangan (fraud) atau menerbitkan opini audit final."""

        usr_prompt = f"""Susun Ringkasan Temuan Audit untuk klien **{client_name}**, periode **{period}**, dengan ambang materialitas **Rp {materiality:,.0f}**.
Fokuskan pada akun dengan Severity High, Medium, atau Tick Mark `?` (bukti kosong).

Data Kertas Kerja (JSON):
{payload_json}"""

        with st.spinner("Menyusun draf temuan audit..."):
            st.session_state["findings_draft"] = call_llm(sys_prompt, usr_prompt)

    if st.session_state["findings_draft"]:
        # Pemeriksa Konsistensi Angka
        is_consistent, alien_nums = check_numbers(st.session_state["findings_draft"], wp_df, materiality)
        if is_consistent:
            st.success("✅ **Pemeriksa Angka (Lolos):** Seluruh angka di dalam narasi cocok dengan data sumber kertas kerja.")
        else:
            st.error(f"🚨 **Peringatan Pemeriksa Angka:** Ditemukan angka di narasi yang tidak tercatat pada data sumber: `{', '.join(alien_nums)}`. Harap periksa manual!")

        st.markdown("---")
        st.markdown(st.session_state["findings_draft"])

# ==============================================================================
# TAB 3: MANAGEMENT LETTER
# ==============================================================================
with tab3:
    st.subheader("Penyusunan Draf Management Letter & Ekspor Excel")
    st.markdown("Menyusun draf surat rekomendasi pengendalian internal kepada manajemen lengkap dengan kolom tanggapan dan target penyelesaian.")

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("✉️ Susun Management Letter", type="primary", use_container_width=True):
            sys_prompt = """Anda adalah asisten auditor eksternal/internal yang menyusun DRAF Management Letter dalam Bahasa Indonesia formal.
ATURAN KERAS (GUARDRAILS):
1. Awali dokumen dengan label jelas: **[DRAFT MANAGEMENT LETTER - WAJIB REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis ada pada data sumber JSON atau Ringkasan Temuan. Dilarang mengarang angka.
3. Sertakan bagian pembuka surat kepada Direksi/Manajemen, pokok-pokok observasi & rekomendasi (cantumkan WP Ref dan status bukti; tulis "BUKTI BELUM TERSEDIA" bila kosong), serta tabel/kolom **Tanggapan Manajemen**, **PIC**, dan **Target Waktu Perbaikan**.
4. Gunakan nada konstruktif profesional. Dilarang menuduh kecurangan atau menyatakan opini audit."""

            usr_prompt = f"""Susun Draf Management Letter untuk **{client_name}** periode **{period}** (Materialitas: Rp {materiality:,.0f}).

Data Kertas Kerja (JSON):
{payload_json}

Konteks Draf Temuan (jika sudah tersedia):
{st.session_state['findings_draft'] or 'Belum disusun terpisah; gunakan langsung data JSON di atas.'}"""

            with st.spinner("Menyusun draf Management Letter..."):
                st.session_state["mgmt_letter_draft"] = call_llm(sys_prompt, usr_prompt)

    with col_btn2:
        excel_bytes = export_audit_excel(
            df=wp_df,
            findings_text=st.session_state["findings_draft"],
            mgmt_letter_text=st.session_state["mgmt_letter_draft"],
            client_name=client_name,
            period=period,
            materiality=materiality,
        )
        st.download_button(
            label="📥 Unduh Paket Kertas Kerja Excel (3 Sheet)",
            data=excel_bytes,
            file_name=f"Auditraa_Draft_{client_name.replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state["mgmt_letter_draft"]:
        is_consistent_ml, alien_nums_ml = check_numbers(st.session_state["mgmt_letter_draft"], wp_df, materiality)
        if is_consistent_ml:
            st.success("✅ **Pemeriksa Angka (Lolos):** Seluruh angka di Management Letter terverifikasi terhadap data sumber.")
        else:
            st.error(f"🚨 **Peringatan Pemeriksa Angka:** Ditemukan angka asing di surat: `{', '.join(alien_nums_ml)}`.")

        st.markdown("---")
        st.markdown(st.session_state["mgmt_letter_draft"])

# ==============================================================================
# TAB 4: TANYA AGEN
# ==============================================================================
with tab4:
    st.subheader("💬 Tanya Agen Kertas Kerja")
    st.caption("Ajukan pertanyaan spesifik mengenai saldo, varians, WP Ref, atau status bukti pada kertas kerja yang sedang aktif.")

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_q = st.chat_input("Contoh: Akun mana saja yang variansnya di atas materialitas dan bagaimana status buktinya?")
    if user_q:
        st.session_state["chat_history"].append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        sys_chat = f"""Anda adalah asisten audit Auditraa. Jawab pertanyaan pengguna HANYA berdasarkan data kertas kerja berikut.
ATURAN:
- Sebutkan WP Ref setiap kali merujuk akun.
- Gunakan angka persis dari JSON tanpa mengarang angka baru.
- Jika bukti kosong, nyatakan "BUKTI BELUM TERSEDIA".
- Jangan menerbitkan opini audit atau menuduh kecurangan.

Data Kertas Kerja ({client_name} - {period}, Materialitas: Rp {materiality:,.0f}):
{payload_json}"""

        with st.chat_message("assistant"):
            with st.spinner("Menganalisis kertas kerja..."):
                answer = call_llm(sys_chat, user_q)
                st.markdown(answer)
        st.session_state["chat_history"].append({"role": "assistant", "content": answer})
