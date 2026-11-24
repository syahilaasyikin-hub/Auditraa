import json
import os
import time
import pandas as pd
import plotly.express as px
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
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash"]

st.set_page_config(
    page_title="Auditraa — Dari Angka ke Bukti, Otomatis Terdokumentasi",
    page_icon="📑",
    layout="wide",
)


def get_api_key() -> str | None:
    """Mengambil GEMINI_API_KEY dari environment (.env) atau Streamlit Secrets dengan aman."""
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    try:
        secret_key = st.secrets.get("GEMINI_API_KEY")
        if secret_key and str(secret_key).strip():
            return str(secret_key).strip()
    except (StreamlitSecretNotFoundError, AttributeError, KeyError, Exception):
        pass

    return None


def get_gemini_client() -> genai.Client | None:
    """Membuat instance Gemini client jika API key tersedia."""
    api_key = get_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Memanggil Gemini API dengan retry otomatis saat 503/UNAVAILABLE dan fallback model."""
    client = get_gemini_client()
    if client is None:
        return (
            "⚠️ **GEMINI_API_KEY belum dikonfigurasi.**\n\n"
            "Tambahkan `GEMINI_API_KEY` ke file `.env` (untuk lokal) atau ke **Settings → Secrets** "
            "di Streamlit Community Cloud."
        )

    models_to_try = []
    for m in [MODEL_NAME] + FALLBACK_MODELS:
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_exc: Exception | None = None
    for model_id in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0,
                    ),
                )
                content = response.text
                if content and content.strip():
                    return content.strip()
                return "⚠️ Model tidak mengembalikan teks."
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_transient = (
                    "503" in err_str
                    or "UNAVAILABLE" in err_str
                    or "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "high demand" in err_str.lower()
                )
                if is_transient and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break

    return (
        f"⚠️ Server Gemini sedang sibuk atau terjadi gangguan setelah beberapa percobaan: `{last_exc}`\n\n"
        "Silakan tunggu beberapa detik lalu klik tombolnya kembali."
    )


def init_session_state() -> None:
    """Inisialisasi state aplikasi di session_state."""
    defaults = {
        "ai_explanation": "",
        "findings_draft": "",
        "mgmt_letter_draft": "",
        "chat_history": [],
        "use_demo_data": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def reset_generated_outputs() -> None:
    """Membersihkan draf narasi, penjelasan AI, dan chat saat dataset baru dimuat."""
    st.session_state["ai_explanation"] = ""
    st.session_state["findings_draft"] = ""
    st.session_state["mgmt_letter_draft"] = ""
    st.session_state["chat_history"] = []


init_session_state()

# --- HEADER & BRANDING ---
st.title("📑 Auditraa")
st.caption("**Dari Angka ke Bukti, Otomatis Terdokumentasi.** | *Kode menghitung, AI menulis, manusia memutuskan.*")
st.warning(
    "🔒 **STATUS KELUARAN: SELALU DRAFT** — Seluruh keluaran yang disusun AI bersifat draf kerja "
    "dan wajib direview, dikoreksi, serta diputuskan oleh auditor."
)

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
            reset_generated_outputs()
            st.rerun()
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
    st.info(
        "🛡️ **Keamanan & Etika:** Jangan unggah data klien rahasia ke API publik tanpa izin. "
        "Gunakan data fiktif untuk demo, tugas, atau pengujian."
    )

# --- PEMUATAN & PEMROSESAN DATA DETERMINISTIK ---
raw_df = None

if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try:
        raw_df = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"❌ Gagal membaca file Excel yang diunggah: `{exc}`")
        st.stop()
elif st.session_state["use_demo_data"]:
    try:
        raw_df = pd.read_excel(generate_sample_excel())
    except Exception as exc:
        st.error(f"❌ Gagal memuat data demo: `{exc}`")
        st.stop()

if raw_df is None or raw_df.empty:
    st.info(
        "👈 Silakan **unggah file Excel (.xlsx)** di sidebar atau klik **▶️ Muat Demo** "
        "untuk menjalankan skenario Auditraa."
    )
    st.stop()

is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(
        f"❌ Struktur kolom Excel tidak sesuai. Kolom wajib yang belum ada: **{', '.join(missing_cols)}**.\n\n"
        "Pastikan file memiliki kolom `Category`, `Budget`, dan `Actual` (opsional: `Evidence_Ref`)."
    )
    st.stop()

wp_df = process_working_paper(raw_df, float(materiality))
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(
    build_llm_payload(wp_df, client_name, period, float(materiality)),
    indent=2,
    ensure_ascii=False,
)

# --- EMPAT TAB UTAMA ---
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Kertas Kerja",
    "2️⃣ Ringkasan Temuan",
    "3️⃣ Management Letter",
    "4️⃣ Tanya Agen",
])

# ==============================================================================
# TAB 1: KERTAS KERJA + PENJELASAN HASIL OLEH AI
# ==============================================================================
with tab1:
    st.subheader(f"Lead Schedule — {client_name} ({period})")

    total_accounts = len(wp_df)
    high_count = int((wp_df["Severity"] == "High").sum())
    med_count = int((wp_df["Severity"] == "Medium").sum())
    missing_count = len(missing_ev_df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Akun Diuji", f"{total_accounts} Akun")
    m2.metric("Ambang Materialitas", f"Rp {materiality:,.0f}")
    m3.metric("Selisih Signifikan", f"{high_count} High / {med_count} Med")
    m4.metric("Bukti Belum Tersedia (?)", f"{missing_count} Akun", delta_color="inverse")

    if not missing_ev_df.empty:
        st.error(
            f"⚠️ **Peringatan Bukti Hilang:** Terdapat **{missing_count} akun** dengan status "
            "`BUKTI BELUM TERSEDIA` (Tick Mark `?`)."
        )
        with st.expander("📋 Daftar Akun Tanpa Referensi Bukti", expanded=True):
            st.dataframe(
                missing_ev_df.style.format({
                    "Budget": "Rp {:,.0f}",
                    "Actual": "Rp {:,.0f}",
                    "Variance": "Rp {:,.0f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

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

    st.caption(
        "**Legenda Tick Mark:** `✓` Cocok / di bawah ambang & bukti tersedia | "
        "`⊗` Selisih melebihi ambang (≥ 50% materialitas) | `?` Bukti belum tersedia"
    )

    st.markdown("### Grafik Selisih per Akun")
    fig = px.bar(
        wp_df,
        x="Category",
        y="Variance",
        color="Severity",
        text="WP_Ref",
        color_discrete_map={
            "High": "#DC2626",
            "Medium": "#F59E0B",
            "Low": "#16A34A",
        },
        labels={
            "Category": "Akun",
            "Variance": "Selisih (Actual - Budget) [Rp]",
            "Severity": "Severity",
        },
        title="Varians Saldo per Akun Terhadap Ambang Materialitas",
    )
    fig.add_hline(
        y=float(materiality),
        line_dash="dash",
        line_color="#DC2626",
        annotation_text="Batas Materialitas (+)",
    )
    fig.add_hline(
        y=-float(materiality),
        line_dash="dash",
        line_color="#DC2626",
        annotation_text="Batas Materialitas (-)",
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # --- PENJELASAN HASIL KERTAS KERJA OLEH AI ---
    st.divider()
    st.markdown("### 🤖 Penjelasan Hasil Kertas Kerja oleh AI (Draft)")
    st.caption(
        "AI membantu menjelaskan arti selisih (Budget vs Actual), tingkat Severity, Tick Mark, "
        "dan kelengkapan bukti berdasarkan hasil hitung kode—bukan opini audit final."
    )

    account_options = ["Semua Akun (Ringkasan Kertas Kerja)"] + [
        f"{row['WP_Ref']} — {row['Category']}" for _, row in wp_df.iterrows()
    ]
    selected_scope = st.selectbox(
        "Pilih cakupan penjelasan:",
        options=account_options,
        key="explain_scope_select",
    )

    if st.button("🧠 Jelaskan Hasil Kertas Kerja", key="btn_explain_wp"):
        if selected_scope == "Semua Akun (Ringkasan Kertas Kerja)":
            target_payload = payload_json
            scope_instruction = (
                "Jelaskan secara ringkas dan jelas gambaran umum hasil kertas kerja seluruh akun: "
                "akun dengan selisih terbesar, akun ber-Severity High/Medium, serta akun bertanda '?' "
                "(BUKTI BELUM TERSEDIA)."
            )
        else:
            selected_wp = selected_scope.split(" — ")[0].strip()
            filtered_df = wp_df[wp_df["WP_Ref"] == selected_wp]
            target_payload = json.dumps(
                build_llm_payload(filtered_df, client_name, period, float(materiality)),
                indent=2,
                ensure_ascii=False,
            )
            scope_instruction = (
                f"Jelaskan secara rinci hasil perhitungan untuk akun **{selected_scope}**: "
                "arti angka Budget, Actual, Variance, dan Variance %, alasan penetapan Severity & Tick Mark, "
                "serta status Evidence_Ref (jika kosong wajib tulis 'BUKTI BELUM TERSEDIA')."
            )

        system_prompt_explain = """Anda adalah asisten auditor yang menjelaskan hasil perhitungan kertas kerja audit dalam Bahasa Indonesia yang jelas dan terstruktur.
ATURAN KETAT:
1. Awali penjelasan dengan label: **[DRAFT PENJELASAN HASIL - WAJIB REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis ada pada data JSON sumber. DILARANG menghitung ulang, mengubah angka, atau mengarang angka baru.
3. Selalu sertakan WP Ref saat merujuk akun.
4. Jika bukti kosong, tulis persis "BUKTI BELUM TERSEDIA".
5. DILARANG menuduh kecurangan atau menyatakan opini audit."""

        user_prompt_explain = f"""Klien: **{client_name}** | Periode: **{period}** | Materialitas: **Rp {materiality:,.0f}**
Tugas: {scope_instruction}

Data Hasil Hitung Kode (JSON):
{target_payload}"""

        with st.spinner("Menyusun penjelasan hasil kertas kerja..."):
            st.session_state["ai_explanation"] = call_llm(
                system_prompt_explain,
                user_prompt_explain,
            )

    if st.session_state["ai_explanation"]:
        is_ok_exp, alien_nums_exp = check_numbers(
            st.session_state["ai_explanation"],
            wp_df,
            float(materiality),
        )
        if is_ok_exp:
            st.success("✅ **Pemeriksa Angka:** Seluruh angka pada penjelasan AI cocok dengan data sumber.")
        else:
            st.error(
                f"🚨 **Peringatan Pemeriksa Angka:** Ditemukan angka pada penjelasan yang tidak ada di data sumber: "
                f"`{', '.join(alien_nums_exp)}`."
            )

        st.markdown(st.session_state["ai_explanation"])

# ==============================================================================
# TAB 2: RINGKASAN TEMUAN
# ==============================================================================
with tab2:
    st.subheader("Penyusunan Draf Ringkasan Temuan Audit")
    st.markdown(
        "Menyusun draf narasi temuan dengan struktur **Kondisi, Kriteria, Penyebab (hipotesis), "
        "Dampak, Rekomendasi, dan Bukti** berdasarkan hasil perhitungan kertas kerja."
    )

    if st.button("✨ Susun Ringkasan Temuan", type="primary"):
        system_prompt_findings = """Anda adalah asisten auditor yang menyusun DRAF Ringkasan Temuan Audit dalam Bahasa Indonesia.
ATURAN KETAT (GUARDRAILS):
1. Awali seluruh keluaran dengan label: **[DRAFT - PERLU REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis ada pada data JSON sumber. DILARANG menghitung ulang, mengubah angka, atau mengarang angka baru.
3. Setiap temuan WAJIB mencantumkan WP Ref dan menggunakan bagian:
   - **WP Ref & Akun**
   - **Kondisi**
   - **Kriteria** (rujukan PSAK/SA umum sebagai acuan awal; wajib diverifikasi auditor)
   - **Penyebab (Hipotesis)** (WAJIB diawali kata "Diduga...")
   - **Dampak**
   - **Rekomendasi**
   - **Bukti** (gunakan Evidence_Ref dari data; jika kosong WAJIB tulis "BUKTI BELUM TERSEDIA")
4. DILARANG menuduh kecurangan (fraud) atau menyatakan opini audit final."""

        user_prompt_findings = f"""Susun Ringkasan Temuan Audit untuk klien **{client_name}**, periode **{period}**, dengan materialitas **Rp {materiality:,.0f}**.
Prioritaskan akun dengan Severity High, Medium, atau Tick Mark `?` (bukti belum tersedia).

Data Kertas Kerja (JSON):
{payload_json}"""

        with st.spinner("Menyusun draf Ringkasan Temuan..."):
            st.session_state["findings_draft"] = call_llm(
                system_prompt_findings,
                user_prompt_findings,
            )

    if st.session_state["findings_draft"]:
        is_ok, alien_numbers = check_numbers(
            st.session_state["findings_draft"],
            wp_df,
            float(materiality),
        )
        if is_ok:
            st.success(
                "✅ **Pemeriksa Angka:** Seluruh angka pada narasi temuan cocok dengan data sumber kertas kerja."
            )
        else:
            st.error(
                f"🚨 **Peringatan Pemeriksa Angka:** Ditemukan angka di narasi yang tidak ada di data sumber: "
                f"`{', '.join(alien_numbers)}`. Mohon periksa kembali secara manual."
            )

        st.divider()
        st.markdown(st.session_state["findings_draft"])

# ==============================================================================
# TAB 3: MANAGEMENT LETTER
# ==============================================================================
with tab3:
    st.subheader("Penyusunan Draf Management Letter & Ekspor Excel")
    st.markdown(
        "Menyusun draf surat rekomendasi kepada manajemen lengkap dengan ruang tanggapan manajemen "
        "dan target perbaikan, serta mengunduh paket Excel 3 sheet."
    )

    col_ml1, col_ml2 = st.columns([1, 1])
    with col_ml1:
        if st.button("✉️ Susun Management Letter", type="primary", use_container_width=True):
            system_prompt_letter = """Anda adalah asisten auditor yang menyusun DRAF Management Letter dalam Bahasa Indonesia formal.
ATURAN KETAT (GUARDRAILS):
1. Awali surat dengan label: **[DRAFT MANAGEMENT LETTER - WAJIB REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis ada pada data JSON sumber atau Ringkasan Temuan. DILARANG mengarang angka.
3. Sertakan bagian pembuka surat kepada Manajemen, poin-poin observasi & rekomendasi (cantumkan WP Ref dan status bukti; tulis "BUKTI BELUM TERSEDIA" jika kosong), serta bagian/tabel **Tanggapan Manajemen** dan **Target Perbaikan**.
4. DILARANG menuduh kecurangan atau menerbitkan opini audit."""

            user_prompt_letter = f"""Susun Draf Management Letter untuk **{client_name}** periode **{period}** (Materialitas: Rp {materiality:,.0f}).

Data Kertas Kerja (JSON):
{payload_json}

Draf Ringkasan Temuan (jika sudah dibuat):
{st.session_state["findings_draft"] or "Belum dibuat terpisah; rujuk langsung data JSON kertas kerja."}"""

            with st.spinner("Menyusun draf Management Letter..."):
                st.session_state["mgmt_letter_draft"] = call_llm(
                    system_prompt_letter,
                    user_prompt_letter,
                )

    with col_ml2:
        excel_data = export_audit_excel(
            df=wp_df,
            findings_text=st.session_state["findings_draft"],
            mgmt_letter_text=st.session_state["mgmt_letter_draft"],
            client_name=client_name,
            period=period,
            materiality=float(materiality),
        )
        safe_client = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in client_name)
        st.download_button(
            label="📥 Unduh Excel (3 Sheet: Kertas Kerja, Temuan, Letter)",
            data=excel_data,
            file_name=f"Auditraa_Draft_{safe_client}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if st.session_state["mgmt_letter_draft"]:
        is_ok_ml, alien_numbers_ml = check_numbers(
            st.session_state["mgmt_letter_draft"],
            wp_df,
            float(materiality),
        )
        if is_ok_ml:
            st.success(
                "✅ **Pemeriksa Angka:** Seluruh angka pada draf Management Letter sesuai dengan data sumber."
            )
        else:
            st.error(
                f"🚨 **Peringatan Pemeriksa Angka:** Ditemukan angka di surat yang tidak ada di data sumber: "
                f"`{', '.join(alien_numbers_ml)}`."
            )

        st.divider()
        st.markdown(st.session_state["mgmt_letter_draft"])

# ==============================================================================
# TAB 4: TANYA AGEN
# ==============================================================================
with tab4:
    st.subheader("💬 Tanya Agen Kertas Kerja")
    st.caption(
        "Ajukan pertanyaan seputar saldo, varians, WP Ref, atau ketersediaan bukti berdasarkan kertas kerja aktif."
    )

    for item in st.session_state["chat_history"]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input(
        "Contoh: Akun mana yang bertanda '?' dan berapa selisihnya dibanding budget?"
    )
    if question:
        st.session_state["chat_history"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        system_prompt_chat = f"""Anda adalah asisten audit Auditraa. Jawab pertanyaan pengguna HANYA berdasarkan data kertas kerja berikut.
ATURAN KETAT:
- Sertakan WP Ref setiap kali menyebut akun.
- Gunakan angka persis sesuai JSON; jangan mengarang angka.
- Jika bukti tidak ada, tulis "BUKTI BELUM TERSEDIA".
- Jangan menuduh kecurangan atau memberikan opini audit final.

Klien: {client_name} | Periode: {period} | Materialitas: Rp {materiality:,.0f}
Data Kertas Kerja (JSON):
{payload_json}"""

        with st.chat_message("assistant"):
            with st.spinner("Menjawab berdasarkan kertas kerja..."):
                reply = call_llm(system_prompt_chat, question)
                st.markdown(reply)

        st.session_state["chat_history"].append({"role": "assistant", "content": reply})
