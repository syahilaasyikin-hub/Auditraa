"""
FinAudit - Agen Pelaporan & Kertas Kerja (versi pengembangan dari app Variance Analysis)
Jalankan: streamlit run app.py
"""
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

import audit_logic as al

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", None)

st.set_page_config(page_title="FinAudit - Pelaporan & Kertas Kerja", page_icon="🧾", layout="wide")
st.title("🧾 FinAudit – Agen Pelaporan & Kertas Kerja")
st.caption("Draf kertas kerja, ringkasan temuan, management letter, dan referensi silang bukti. "
           "Semua keluaran adalah DRAFT yang wajib direview auditor.")

if not API_KEY:
    st.error("🚨 GROQ_API_KEY belum diatur (file .env atau Streamlit Secrets).")
    st.stop()
client = Groq(api_key=API_KEY)

# ---------------- Sidebar: parameter penugasan ----------------
with st.sidebar:
    st.header("⚙️ Parameter Penugasan")
    client_name = st.text_input("Nama klien", "PT Contoh Sejahtera")
    period = st.text_input("Periode", "FY2026 (1 Jan - 31 Des 2026)")
    preparer = st.text_input("Disusun oleh", "Auditor Junior")
    materiality = st.number_input("Materialitas pelaksanaan (Rp)", min_value=1.0,
                                  value=50_000_000.0, step=5_000_000.0)
    model = st.selectbox("Model Groq", ["openai/gpt-oss-20b"])
    st.caption("Daftar model terbaru: console.groq.com/docs/models")


def ask(prompt: str) -> str:
    """Panggil LLM. temperature=0 agar keluaran stabil dan minim 'kreativitas' angka."""
    r = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": al.SYSTEM_RULES},
                  {"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content


# ---------------- Upload ----------------
st.markdown("**Format Excel:** kolom wajib `Category`, `Budget` (saldo pembanding/ekspektasi), "
            "`Actual` (saldo per buku). Kolom opsional `Evidence_Ref` (nomor bukti).")
up = st.file_uploader("📂 Unggah data (.xlsx)", type=["xlsx"])
if not up:
    st.stop()

raw = pd.read_excel(up)
missing = al.validate_columns(raw)
if missing:
    st.error(f"⚠️ Kolom wajib hilang: {missing}")
    st.stop()

wp = al.build_working_paper(raw, materiality)
payload = al.findings_payload(wp)

tab1, tab2, tab3, tab4 = st.tabs(
    ["📑 Kertas Kerja", "🔎 Ringkasan Temuan", "✉️ Management Letter", "💬 Tanya Agen"])

# ---------------- Tab 1: Kertas kerja ----------------
with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("Jumlah akun diuji", len(wp))
    c2.metric("Temuan High", int((wp["Severity"] == "High").sum()))
    c3.metric("Bukti belum tersedia", int((wp["Evidence_Ref"] == "").sum()))

    st.dataframe(wp[["WP Ref", "Category", "Budget", "Actual", "Variance", "Variance %",
                     "Severity", "Tick", "Evidence_Ref", "Status"]], use_container_width=True)
    st.caption("Legenda tick mark: " + " | ".join(f"{k} {v}" for k, v in al.TICK_LEGEND.items()))

    fig = px.bar(wp, x="Category", y="Variance", color="Severity", text_auto=".2s",
                 color_discrete_map={"High": "red", "Medium": "orange", "Low": "green"},
                 title="Selisih per akun (warna = severity)")
    st.plotly_chart(fig, use_container_width=True)

    miss = al.missing_evidence(wp)
    if not miss.empty:
        st.warning("Akun berikut belum memiliki referensi bukti (belum boleh disimpulkan):")
        st.dataframe(miss)

# ---------------- Tab 2: Temuan ----------------
with tab2:
    if not payload:
        st.success("Tidak ada selisih High/Medium berdasarkan materialitas yang ditetapkan.")
    elif st.button("Susun Ringkasan Temuan"):   # tombol -> tidak memanggil API di setiap rerun
        with st.spinner("Menyusun temuan..."):
            st.session_state["findings"] = ask(
                al.prompt_findings(client_name, period, materiality, payload))
    text = st.session_state.get("findings")
    if text:
        st.markdown(text)
        bad = al.check_numbers(text, payload)
        if bad:
            st.error(f"⚠️ Angka berikut tidak ditemukan di data sumber, periksa manual: {bad}")
        else:
            st.success("✅ Pemeriksa konsistensi: semua angka besar pada narasi ada di data sumber.")

# ---------------- Tab 3: Management letter ----------------
with tab3:
    if payload and st.button("Susun Draf Management Letter"):
        with st.spinner("Menyusun surat..."):
            st.session_state["letter"] = ask(al.prompt_letter(client_name, period, payload))
    letter = st.session_state.get("letter")
    if letter:
        st.markdown(letter)
        bad = al.check_numbers(letter, payload)
        if bad:
            st.error(f"⚠️ Periksa manual angka berikut: {bad}")

    st.divider()
    xls = al.export_excel(wp, client_name, period, preparer, materiality,
                          st.session_state.get("findings", ""), st.session_state.get("letter", ""))
    st.download_button("⬇️ Unduh Kertas Kerja (Excel)", xls,
                       file_name="kertas_kerja_draft.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------- Tab 4: Chat ----------------
with tab4:
    q = st.text_input("Tanyakan sesuatu tentang kertas kerja ini:")
    if q:
        ctx = wp.drop(columns=["Status"]).to_string()
        st.write(ask(f"Data kertas kerja:\n{ctx}\n\nPertanyaan auditor: {q}"))
