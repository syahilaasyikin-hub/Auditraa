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

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

st.set_page_config(
    page_title="Auditraa — Analisis Kertas Kerja Audit",
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


@st.cache_resource
def _cached_gemini_client(api_key: str) -> genai.Client:
    """Menyimpan instance Gemini client agar tidak dibuat ulang tiap interaksi."""
    return genai.Client(api_key=api_key)


def get_gemini_client() -> genai.Client | None:
    api_key = get_api_key()
    if not api_key:
        return None
    return _cached_gemini_client(api_key)


def _offline_deterministic_analysis(
    wp_df: pd.DataFrame,
    client_name: str,
    period: str,
    materiality: float,
    selected_scope: str,
) -> str:
    """Cadangan analisis deterministik dari kode jika seluruh model Gemini sedang 503."""
    lines = [
        "**[DRAFT ANALISIS CADANGAN (NON-LLM) — PERLU REVIEW AUDITOR]**",
        f"_Catatan: Server Gemini sedang mengalami lonjakan beban (503 UNAVAILABLE), sehingga ditampilkan ringkasan otomatis dari hasil perhitungan kode._",
        "",
        f"- **Klien / Periode:** {client_name} ({period})",
        f"- **Ambang Materialitas:** Rp {materiality:,.0f}",
    ]
    if selected_scope == "Semua Akun (Analisis Menyeluruh)":
        target_df = wp_df
    else:
        wp_code = selected_scope.split(" — ")[0].strip()
        target_df = wp_df[wp_df["WP_Ref"] == wp_code]

    for _, row in target_df.iterrows():
        ev = row["Evidence_Ref"] if row["Evidence_Ref"] else "BUKTI BELUM TERSEDIA"
        lines.append(
            f"- **{row['WP_Ref']} — {row['Category']}:** Budget Rp {row['Budget']:,.0f}, "
            f"Actual Rp {row['Actual']:,.0f}, Variance Rp {row['Variance']:,.0f} "
            f"({row['Variance_Pct']:.2f}%), Severity: **{row['Severity']}**, "
            f"Tick Mark: `{row['Tick_Mark']}`, Bukti: `{ev}`."
        )
    return "
".join(lines)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    fallback_df: pd.DataFrame | None = None,
    client_name: str = "",
    period: str = "",
    materiality: float = 0.0,
    selected_scope: str = "Semua Akun (Analisis Menyeluruh)",
) -> str:
    """Memanggil Gemini API dengan pindah model cepat saat 503 dan cadangan otomatis jika semua sibuk."""
    client = get_gemini_client()
    if client is None:
        return (
            "⚠️ **GEMINI_API_KEY belum dikonfigurasi.**\n\n"
            "Tambahkan `GEMINI_API_KEY` ke file `.env` (untuk lokal) atau ke **Settings → Secrets** "
            "di Streamlit Community Cloud."
        )

    last_exc: Exception | None = None
    for model_id in MODEL_CANDIDATES:
        for attempt in range(2):
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
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_overload = (
                    "503" in err_str
                    or "UNAVAILABLE" in err_str
                    or "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "high demand" in err_str.lower()
                )
                if is_overload and attempt == 0:
                    time.sleep(0.6)
                    continue
                break

    if fallback_df is not None:
        return _offline_deterministic_analysis(
            fallback_df, client_name, period, materiality, selected_scope
        ) + f"\n\n_Detail error terakhir: `{last_exc}`_"

    return f"⚠️ Server Gemini sedang sibuk (`503 UNAVAILABLE`). Silakan coba lagi beberapa saat: `{last_exc}`"


def init_session_state() -> None:
    defaults = {
        "ai_analysis": "",
        "use_demo_data": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()

# --- HEADER ---
st.title("📑 Auditraa")
st.caption("**Analisis Hasil Kertas Kerja Audit oleh AI.** | *Kode menghitung, AI menganalisis, manusia memutuskan.*")
st.warning(
    "🔒 **STATUS KELUARAN: SELALU DRAFT** — Hasil analisis AI bersifat draf awal "
    "dan wajib direview serta diputuskan oleh auditor."
)

# --- SIDEBAR ---
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

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        if st.button("▶️ Muat Demo", use_container_width=True):
            st.session_state["use_demo_data"] = True
            st.session_state["ai_analysis"] = ""
            st.rerun()
    with col_d2:
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
        - `✓` : Selisih < 50% materialitas & bukti ada
        - `⊗` : Selisih ≥ 50% materialitas (Medium / High)
        - `?` : `BUKTI BELUM TERSEDIA`
        """
    )

# --- DATA DETERMINISTIK ---
raw_df = None
if uploaded_file is not None:
    st.session_state["use_demo_data"] = False
    try:
        raw_df = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"❌ Gagal membaca file Excel: `{exc}`")
        st.stop()
elif st.session_state["use_demo_data"]:
    try:
        raw_df = pd.read_excel(generate_sample_excel())
    except Exception as exc:
        st.error(f"❌ Gagal memuat data demo: `{exc}`")
        st.stop()

if raw_df is None or raw_df.empty:
    st.info("👈 Unggah file Excel (.xlsx) di sidebar atau klik **▶️ Muat Demo** untuk mulai.")
    st.stop()

is_valid, missing_cols = validate_columns(raw_df)
if not is_valid:
    st.error(f"❌ Kolom wajib yang belum ada: **{', '.join(missing_cols)}**")
    st.stop()

wp_df = process_working_paper(raw_df, float(materiality))
missing_ev_df = get_missing_evidence(wp_df)
payload_json = json.dumps(
    build_llm_payload(wp_df, client_name, period, float(materiality)),
    indent=2,
    ensure_ascii=False,
)

# --- RINGKASAN & TABEL KERTAS KERJA ---
st.subheader(f"Lead Schedule — {client_name} ({period})")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Akun", f"{len(wp_df)} Akun")
m2.metric("Materialitas", f"Rp {materiality:,.0f}")
m3.metric("High / Medium", f"{int((wp_df['Severity'] == 'High').sum())} High / {int((wp_df['Severity'] == 'Medium').sum())} Med")
m4.metric("Bukti Kosong (?)", f"{len(missing_ev_df)} Akun", delta_color="inverse")

if not missing_ev_df.empty:
    st.warning(
        f"⚠️ Terdapat **{len(missing_ev_df)} akun** dengan status `BUKTI BELUM TERSEDIA` (`?`): "
        f"{', '.join(missing_ev_df['WP_Ref'] + ' - ' + missing_ev_df['Category'])}"
    )

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

fig = px.bar(
    wp_df,
    x="Category",
    y="Variance",
    color="Severity",
    text="WP_Ref",
    color_discrete_map={"High": "#DC2626", "Medium": "#F59E0B", "Low": "#16A34A"},
    labels={"Category": "Akun", "Variance": "Selisih (Rp)", "Severity": "Severity"},
    title="Varians Saldo per Akun",
)
fig.add_hline(y=float(materiality), line_dash="dash", line_color="#DC2626", annotation_text="Batas (+)")
fig.add_hline(y=-float(materiality), line_dash="dash", line_color="#DC2626", annotation_text="Batas (-)")
fig.update_traces(textposition="outside")
st.plotly_chart(fig, use_container_width=True)

# --- FITUR UTAMA: AI ANALISIS HASIL ---
st.divider()
st.markdown("### 🤖 Analisis Hasil Kertas Kerja oleh AI")

scope_options = ["Semua Akun (Analisis Menyeluruh)"] + [
    f"{row['WP_Ref']} — {row['Category']}" for _, row in wp_df.iterrows()
]
selected_scope = st.selectbox("Fokus analisis:", options=scope_options)

if st.button("🔍 Analisis Hasil dengan AI", type="primary"):
    if selected_scope == "Semua Akun (Analisis Menyeluruh)":
        target_json = payload_json
        focus_text = (
            "Analisis hasil kertas kerja secara ringkas dan tajam: (1) akun dengan varians paling signifikan "
            "(High/Medium), (2) pola atau indikasi awal yang perlu dicek auditor, dan (3) akun tanpa bukti ('?')."
        )
    else:
        wp_code = selected_scope.split(" — ")[0].strip()
        sub_df = wp_df[wp_df["WP_Ref"] == wp_code]
        target_json = json.dumps(
            build_llm_payload(sub_df, client_name, period, float(materiality)),
            indent=2,
            ensure_ascii=False,
        )
        focus_text = (
            f"Analisis secara rinci hasil untuk akun **{selected_scope}**: makna selisih Budget vs Actual, "
            "alasan Severity & Tick Mark, risiko yang perlu diuji auditor, dan status bukti."
        )

    sys_prompt = """Anda adalah asisten auditor yang menganalisis hasil perhitungan kertas kerja audit dalam Bahasa Indonesia.
ATURAN:
1. Awali dengan label: **[DRAFT ANALISIS AI - PERLU REVIEW AUDITOR]**.
2. HANYA gunakan angka yang persis ada di JSON. DILARANG menghitung ulang atau mengarang angka baru.
3. Selalu sebutkan WP Ref saat merujuk akun.
4. Jika bukti kosong, tulis "BUKTI BELUM TERSEDIA".
5. DILARANG menuduh kecurangan atau menerbitkan opini audit."""

    usr_prompt = f"""Klien: {client_name} | Periode: {period} | Materialitas: Rp {materiality:,.0f}
Instruksi: {focus_text}

Data (JSON):
{target_json}"""

    with st.spinner("Menganalisis hasil..."):
        st.session_state["ai_analysis"] = call_llm(
            sys_prompt,
            usr_prompt,
            fallback_df=wp_df,
            client_name=client_name,
            period=period,
            materiality=float(materiality),
            selected_scope=selected_scope,
        )

if st.session_state["ai_analysis"]:
    is_ok, alien_nums = check_numbers(st.session_state["ai_analysis"], wp_df, float(materiality))
    if is_ok:
        st.success("✅ **Pemeriksa Angka:** Seluruh angka pada analisis AI sesuai dengan data sumber.")
    else:
        st.error(f"🚨 **Peringatan Pemeriksa Angka:** Ada angka di analisis yang tidak ada di data sumber: `{', '.join(alien_nums)}`.")
    st.markdown(st.session_state["ai_analysis"])

excel_simple = export_audit_excel(
    df=wp_df,
    findings_text=st.session_state["ai_analysis"],
    mgmt_letter_text="",
    client_name=client_name,
    period=period,
    materiality=float(materiality),
)
st.download_button(
    label="📥 Unduh Kertas Kerja (.xlsx)",
    data=excel_simple,
    file_name="Auditraa_Analisis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
