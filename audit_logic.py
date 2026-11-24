import io
import re
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def validate_columns(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """Memeriksa apakah kolom wajib tersedia di file Excel."""
    required_cols = {"Category", "Budget", "Actual"}
    missing = list(required_cols - set(df.columns))
    return len(missing) == 0, missing


def process_working_paper(df: pd.DataFrame, materiality: float) -> pd.DataFrame:
    """
    Menghitung Variance, Variance %, Severity, Tick Mark, dan WP Ref secara deterministik.
    """
    work_df = df.copy()

    if "Evidence_Ref" not in work_df.columns:
        work_df["Evidence_Ref"] = ""

    work_df["Evidence_Ref"] = work_df["Evidence_Ref"].fillna("").astype(str).str.strip()
    work_df["Budget"] = pd.to_numeric(work_df["Budget"], errors="coerce").fillna(0.0)
    work_df["Actual"] = pd.to_numeric(work_df["Actual"], errors="coerce").fillna(0.0)

    work_df["Variance"] = work_df["Actual"] - work_df["Budget"]

    def calc_var_pct(row):
        if row["Budget"] == 0:
            return 0.0 if row["Actual"] == 0 else 100.0
        return (row["Variance"] / abs(row["Budget"])) * 100.0

    work_df["Variance_Pct"] = work_df.apply(calc_var_pct, axis=1)

    severities = []
    tick_marks = []
    wp_refs = []

    for idx, row in work_df.iterrows():
        abs_var = abs(row["Variance"])
        has_evidence = bool(row["Evidence_Ref"]) and row["Evidence_Ref"].lower() not in ["nan", "none", "-", ""]

        if abs_var >= materiality:
            sev = "High"
        elif abs_var >= 0.5 * materiality:
            sev = "Medium"
        else:
            sev = "Low"

        if not has_evidence:
            tick = "?"
        elif abs_var >= 0.5 * materiality:
            tick = "⊗"
        else:
            tick = "✓"

        severities.append(sev)
        tick_marks.append(tick)
        wp_refs.append(f"C-{idx + 1}")

    work_df["Severity"] = severities
    work_df["Tick_Mark"] = tick_marks
    work_df["WP_Ref"] = wp_refs

    cols_order = [
        "WP_Ref",
        "Category",
        "Budget",
        "Actual",
        "Variance",
        "Variance_Pct",
        "Severity",
        "Tick_Mark",
        "Evidence_Ref",
    ]
    other_cols = [c for c in work_df.columns if c not in cols_order]
    return work_df[cols_order + other_cols]


def get_missing_evidence(df: pd.DataFrame) -> pd.DataFrame:
    """Mengambil daftar akun yang belum memiliki referensi bukti."""
    mask = df["Tick_Mark"] == "?"
    return df[mask][["WP_Ref", "Category", "Budget", "Actual", "Variance", "Severity"]].copy()


def build_llm_payload(df: pd.DataFrame, client_name: str, period: str, materiality: float) -> list[dict]:
    """Menyiapkan payload JSON terstruktur dengan angka terformat untuk LLM."""
    records = []
    for _, row in df.iterrows():
        ev = row["Evidence_Ref"] if row["Evidence_Ref"] else "BUKTI BELUM TERSEDIA"
        records.append({
            "WP_Ref": row["WP_Ref"],
            "Category": row["Category"],
            "Budget": f"{row['Budget']:,.0f}",
            "Actual": f"{row['Actual']:,.0f}",
            "Variance": f"{row['Variance']:,.0f}",
            "Variance_Pct": f"{row['Variance_Pct']:.2f}%",
            "Severity": row["Severity"],
            "Tick_Mark": row["Tick_Mark"],
            "Evidence_Ref": ev,
        })
    return records


def check_numbers(narrative: str, df: pd.DataFrame, materiality: float) -> tuple[bool, list[str]]:
    """
    Pemeriksa konsistensi angka: mengekstrak angka dari narasi LLM dan mencocokkannya
    dengan angka yang valid di data sumber.
    """
    if not narrative or not narrative.strip():
        return True, []

    allowed_numbers = set()
    allowed_numbers.add(round(float(materiality), 2))
    allowed_numbers.add(round(float(materiality) / 1_000_000, 2))

    for _, row in df.iterrows():
        for col in ["Budget", "Actual", "Variance"]:
            val = abs(float(row[col]))
            allowed_numbers.add(round(val, 2))
            allowed_numbers.add(round(val / 1_000_000, 2))
            allowed_numbers.add(round(val / 1_000, 2))
        pct = abs(float(row["Variance_Pct"]))
        allowed_numbers.add(round(pct, 2))
        allowed_numbers.add(round(pct, 1))
        allowed_numbers.add(round(pct, 0))

    cleaned_text = re.sub(r"\bC-\d+\b", "", narrative)
    cleaned_text = re.sub(r"\b(?:PSAK|SA|No\.|Nomor|Bab|Pasal|Ayat)\s*\d+(?:\.\d+)?\b", "", cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r"\b20[2-3]\d\b", "", cleaned_text)

    raw_matches = re.findall(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\b", cleaned_text)

    unmatched = []
    for token in raw_matches:
        normalized = token
        if "." in token and "," in token:
            if token.rfind(",") > token.rfind("."):
                normalized = token.replace(".", "").replace(",", ".")
            else:
                normalized = token.replace(",", "")
        elif "," in token:
            parts = token.split(",")
            if len(parts[-1]) == 3 and len(parts) > 1:
                normalized = token.replace(",", "")
            else:
                normalized = token.replace(",", ".")
        elif "." in token:
            parts = token.split(".")
            if len(parts[-1]) == 3 and len(parts) > 1:
                normalized = token.replace(".", "")

        try:
            num_val = abs(float(normalized))
        except ValueError:
            continue

        if num_val in {1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 50.0, 100.0}:
            continue

        is_found = any(abs(num_val - allowed) <= 0.05 for allowed in allowed_numbers)
        if not is_found and token not in unmatched:
            unmatched.append(token)

    return len(unmatched) == 0, unmatched


def export_audit_excel(
    df: pd.DataFrame,
    findings_text: str,
    mgmt_letter_text: str,
    client_name: str,
    period: str,
    materiality: float,
) -> bytes:
    """Mengekspor 3 sheet ke Excel (.xlsx)."""
    output = io.BytesIO()
    wb = openpyxl.Workbook()

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(bold=True, size=14, color="1E3A8A")
    draft_font = Font(bold=True, size=10, color="B91C1C")
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    ws1 = wb.active
    ws1.title = "Kertas Kerja"
    ws1["A1"] = f"KERTAS KERJA PEMERIKSAAN (LEAD SCHEDULE) - {client_name.upper()}"
    ws1["A1"].font = title_font
    ws1["A2"] = f"Periode: {period} | Materialitas: Rp {materiality:,.0f} | Status: DRAFT - PERLU REVIEW AUDITOR"
    ws1["A2"].font = draft_font

    headers = [
        "WP Ref",
        "Category",
        "Budget (Rp)",
        "Actual (Rp)",
        "Variance (Rp)",
        "Variance (%)",
        "Severity",
        "Tick Mark",
        "Evidence Ref",
    ]
    start_row = 4
    for col_idx, h in enumerate(headers, start=1):
        cell = ws1.cell(row=start_row, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    for r_idx, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        ev_display = row["Evidence_Ref"] if row["Evidence_Ref"] else "BUKTI BELUM TERSEDIA"
        values = [
            row["WP_Ref"],
            row["Category"],
            float(row["Budget"]),
            float(row["Actual"]),
            float(row["Variance"]),
            round(float(row["Variance_Pct"]), 2),
            row["Severity"],
            row["Tick_Mark"],
            ev_display,
        ]
        for c_idx, val in enumerate(values, start=1):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.border = thin_border
            if c_idx in [3, 4, 5]:
                cell.number_format = "#,##0"
            elif c_idx == 6:
                cell.number_format = "0.00\"%\""
            elif c_idx in [1, 7, 8]:
                cell.alignment = Alignment(horizontal="center")

    for col in ws1.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.row >= start_row and cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws1.column_dimensions[col_letter].width = max(max_len + 4, 14)

    ws2 = wb.create_sheet(title="Ringkasan Temuan")
    ws2["A1"] = f"RINGKASAN TEMUAN AUDIT (DRAFT) - {client_name.upper()}"
    ws2["A1"].font = title_font
    ws2["A2"] = f"Periode: {period} | Dokumen ini adalah draf awal dan wajib direview oleh auditor."
    ws2["A2"].font = draft_font

    content_findings = findings_text.strip() if findings_text else "Belum ada ringkasan temuan yang disusun."
    for idx, line in enumerate(content_findings.splitlines(), start=4):
        cell = ws2.cell(row=idx, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws2.column_dimensions["A"].width = 110

    ws3 = wb.create_sheet(title="Management Letter")
    ws3["A1"] = f"DRAF MANAGEMENT LETTER - {client_name.upper()}"
    ws3["A1"].font = title_font
    ws3["A2"] = f"Periode: {period} | Status: DRAFT - UNTUK DISKUSI DENGAN MANAJEMEN"
    ws3["A2"].font = draft_font

    content_letter = mgmt_letter_text.strip() if mgmt_letter_text else "Belum ada draf management letter yang disusun."
    for idx, line in enumerate(content_letter.splitlines(), start=4):
        cell = ws3.cell(row=idx, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws3.column_dimensions["A"].width = 110

    wb.save(output)
    return output.getvalue()


def generate_sample_excel() -> bytes:
    """Membuat file contoh_data.xlsx (7 akun, 1 tanpa bukti) untuk kebutuhan demo."""
    sample_data = pd.DataFrame([
        {"Category": "Pendapatan Penjualan", "Budget": 1200000000, "Actual": 1345000000, "Evidence_Ref": "GL-401 / Inv-Recap"},
        {"Category": "Beban Pokok Penjualan", "Budget": 720000000, "Actual": 748000000, "Evidence_Ref": "GL-501 / COGS-Sheet"},
        {"Category": "Persediaan Akhir", "Budget": 310000000, "Actual": 372000000, "Evidence_Ref": ""},
        {"Category": "Piutang Usaha", "Budget": 250000000, "Actual": 262000000, "Evidence_Ref": "AR-Aging-Dec"},
        {"Category": "Beban Operasional & Umum", "Budget": 180000000, "Actual": 184500000, "Evidence_Ref": "Voucher-Batch-12"},
        {"Category": "Kas dan Setara Kas", "Budget": 400000000, "Actual": 405000000, "Evidence_Ref": "Bank-Recon-BCA"},
        {"Category": "Beban Pemasaran", "Budget": 95000000, "Actual": 128000000, "Evidence_Ref": "MKT-Promo-Q4"},
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sample_data.to_excel(writer, index=False, sheet_name="Saldo_Akun")
    return buf.getvalue()
