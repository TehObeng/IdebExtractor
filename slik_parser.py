"""
SLIK/iDeb PDF Parser — Core Extraction Module
Parses Indonesian OJK SLIK PDF reports using pdfplumber + regex.
Extracts active credit facilities and returns a DataFrame.
"""

import re
import pdfplumber
import pandas as pd
from io import BytesIO
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Text Extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_source) -> tuple[str, str]:
    """
    Extract all text from a SLIK PDF, filtering out the RAHASIA watermark.

    Args:
        pdf_source: File path (str) or file-like object (BytesIO / UploadedFile).

    Returns:
        (full_text, nama_debitur)
    """
    full_text = ""
    first_page_text = ""

    pdf = pdfplumber.open(pdf_source)
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if i == 0:
            first_page_text = text
        full_text += text + "\n"
    pdf.close()

    # Strip RAHASIA watermark and its disclaimer line
    full_text = _strip_rahasia(full_text)
    first_page_text = _strip_rahasia(first_page_text)

    nama_debitur = _extract_nama_debitur(first_page_text)

    return full_text, nama_debitur


def _strip_rahasia(text: str) -> str:
    """Remove the RAHASIA watermark word and the standard disclaimer line."""
    # Remove standalone "RAHASIA" (watermark overlay)
    text = re.sub(r'\bRAHASIA\b', '', text)
    # Remove the standard disclaimer line
    text = re.sub(
        r'Informasi ini bersifat\s+dan hanya digunakan untuk kepentingan pemohon informasi\.?',
        '', text
    )
    # Remove leftover RAHASIA that may appear inside numbers (e.g. 1.500.RAHASIA000)
    # This is a safety net — pdfplumber may interleave the watermark into data
    text = re.sub(r'\.?RAHASIA\.?', '', text, flags=re.IGNORECASE)
    return text


def _extract_nama_debitur(first_page_text: str) -> str:
    """
    Extract the debtor name from the first page.
    Supports both individual PDFs ('Nama Sesuai Identitas') and
    company/foundation PDFs ('Nama Debitur').
    """
    # --- Company / Foundation PDFs ---
    # Header row: "Nama Debitur  NPWP  Bentuk BU / Go Public ..."
    # Data row:   "YAYASAN BUMI MAITRI  024828006214000  Yayasan / ..."
    #         or: "INDO PERMATA AYU  0029032988215000  Perseroan Terbatas / ..."
    company_match = re.search(
        r'Nama Debitur\s+NPWP\s+Bentuk BU.*?\n\s*([A-Z][A-Z\s]+?)\s+\d{10,}',
        first_page_text, re.DOTALL
    )
    if company_match:
        return company_match.group(1).strip()

    # --- Individual PDFs ---
    # Header row: "Nama Sesuai Identitas  Identitas  Jenis Kelamin ..."
    # Data row:   "SAKUAN  NIK / LAKI-LAKI / ..."
    individual_match = re.search(
        r'Nama Sesuai Identitas.*?\n\s*([A-Z][A-Z\s,\.]+?)(?:\s+NIK|\s+SIM|\s+Paspor)',
        first_page_text, re.DOTALL
    )
    if individual_match:
        return individual_match.group(1).strip()

    # --- Fallback: "Nama" line on page 1 header ---
    # PT PDFs sometimes show: "Nama\nINDO PERMATA AYU  Posisi Data"
    fallback_match = re.search(
        r'(?:^|\n)Nama\s*\n\s*([A-Z][A-Z\s]+?)\s+(?:Posisi|NPWP)',
        first_page_text
    )
    if fallback_match:
        return fallback_match.group(1).strip()

    # --- Last resort: "Nama  Jenis Kelamin" header ---
    match = re.search(r'Nama\s+Jenis Kelamin.*?\n([A-Z][A-Z\s]+)', first_page_text)
    if match:
        return match.group(1).strip()

    return "-"


# ---------------------------------------------------------------------------
# 2. Chunking & Parsing
# ---------------------------------------------------------------------------

def parse_slik_data(full_text: str, nama_debitur: str) -> pd.DataFrame:
    """
    Split text into facility chunks and extract fields via regex.
    Only keeps facilities where Baki Debet > 0.

    Returns a pandas DataFrame.
    """
    # Split by the section header that precedes each facility
    # Each facility block starts with "Kredit/Pembiayaan" followed by
    # "Pelapor  Cabang  Baki Debet  Tanggal Update"
    # and then the actual data line.
    chunks = re.split(r'Kredit/Pembiayaan\s*\n\s*Pelapor\s+Cabang\s+Baki Debet\s+Tanggal Update', full_text)

    # The first chunk is the header/summary section — skip it
    facility_chunks = chunks[1:]

    records = []
    for chunk in facility_chunks:
        record = _parse_chunk(chunk, nama_debitur)
        if record is not None:
            records.append(record)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Reorder columns
    column_order = [
        "Nama Debitur", "Pelapor", "Fasilitas", "Kol",
        "Hari Tunggakan", "Tanggal Mulai", "Tanggal JTO",
        "Plafon", "Suku Bunga", "Baki Debet", "Baki Debet (Raw)", "Agunan"
    ]
    # Only include columns that exist
    column_order = [c for c in column_order if c in df.columns]
    df = df[column_order]

    return df


def _parse_chunk(chunk: str, nama_debitur: str) -> dict | None:
    """
    Parse a single facility chunk.
    Returns a dict or None if the facility should be excluded.

    Inclusion criteria (keep if ANY is true):
      1. The chunk says "Kondisi  Fasilitas Aktif"
      2. Kualitas (Kol) >= 2
    """
    data = {}
    data["Nama Debitur"] = nama_debitur

    # --- Pelapor & Baki Debet (from the first data line) ---
    pelapor_match = re.search(
        r'(\d{2,6}\s*-\s*.*?)\s+Rp\s*([\d\.,]+)',
        chunk
    )
    if pelapor_match:
        raw_pelapor = pelapor_match.group(1).strip()
        baki_debet_str = pelapor_match.group(2).strip()
    else:
        return None  # Can't parse this chunk

    # Parse Baki Debet as integer
    baki_debet_int = _parse_currency_to_int(baki_debet_str)

    # --- Kualitas (Kol) — parse early, needed for filter ---
    kol_match = re.search(r'Kualitas\s+(\d)\s*-', chunk)
    kol_str = kol_match.group(1) if kol_match else "-"
    kol_int = int(kol_str) if kol_str.isdigit() else 0

    # --- Check "Kondisi  Fasilitas Aktif" ---
    is_fasilitas_aktif = bool(re.search(r'Kondisi\s+Fasilitas Aktif', chunk))

    # --- Filter: keep if Fasilitas Aktif OR Kol >= 2 ---
    if not is_fasilitas_aktif and kol_int < 2:
        return None

    # ------------------------------------------------------------------
    # Clean up Pelapor: separate bank name from cabang, handle wrapping
    # ------------------------------------------------------------------
    # raw_pelapor e.g. "602607 - PT Bank Perekonomian Rakyat Pusat"
    # The cabang (Pusat) is wrongly included; real name continues on next line.

    # Extract the numeric code prefix
    code_match = re.match(r'(\d{2,6}\s*-\s*)', raw_pelapor)
    code_prefix = code_match.group(1) if code_match else ""
    name_and_cabang = raw_pelapor[len(code_prefix):].strip() if code_prefix else raw_pelapor

    # Known cabang patterns (order: longer/more specific first)
    cabang_patterns = [
        r'\s+(BANK\s+BUKOPIN\s+\S.*)$',       # BANK BUKOPIN KC TJ.PINANG
        r'\s+(BANK\s+OCBC\s+NISP\s+\S.*)$',    # BANK OCBC NISP KC BTM-RGC.PARK
        r'\s+(BANK\s+CIMB\s+NIAGA\s+\S.*)$',   # BANK CIMB NIAGA KPO
        r'\s+(BPD\s+\w+\s+KC\s+\S.*)$',        # BPD JATIM KC BATAM
        r'\s+(BMI\s+KC\s+\S.*)$',               # BMI KC TANJUNG PINANG
        r'\s+(BRI\s+KAS\s+\S.*)$',              # BRI KAS KPO
        r'\s+(BCA\s+KANTOR\s+\S.*)$',           # BCA KANTOR PUSAT
        r'\s+(KC\s+\S.*)$',                     # KC Sutami
        r'\s+(KPO)$',                           # KPO (standalone)
        r'\s+(Pusat)$',                         # Pusat (standalone)
    ]

    bank_name = name_and_cabang
    for pattern in cabang_patterns:
        cabang_hit = re.search(pattern, name_and_cabang, re.IGNORECASE)
        if cabang_hit:
            candidate = name_and_cabang[:cabang_hit.start()].strip()
            # Ensure we don't consume the entire bank name (e.g. "PT" only)
            if len(candidate) >= 10:
                bank_name = candidate
            break

    # Check for bank name continuation on the next line
    # e.g. "...Rakyat Pusat Rp ...\nCentral Sejahtera\nFeb 24 ..."
    continuation_match = re.search(
        r'Rp\s*[\d\.,]+\s+\d{2}\s+\w+\s+\d{4}\s*\n\s*([A-Z][A-Za-z\s\.\(\)]+?)\s*\n',
        chunk
    )
    if continuation_match:
        cont_text = continuation_match.group(1).strip()
        # Only accept if it's NOT a month row or section header
        if not re.match(
            r'(Feb|Mar|Apr|Mei|Jun|Jul|Agt|Sep|Okt|Nov|Des|Kualitas|No Rekening|Sifat)',
            cont_text
        ):
            bank_name = bank_name + " " + cont_text

    data["Pelapor"] = (code_prefix + bank_name).strip()

    # Format Baki Debet for display + keep raw int for summation
    data["Baki Debet"] = _format_rupiah(baki_debet_int)
    data["Baki Debet (Raw)"] = baki_debet_int

    # --- Kualitas (Kol) ---
    data["Kol"] = kol_str

    # --- Jumlah Hari Tunggakan ---
    tunggakan_match = re.search(r'Jumlah Hari Tunggakan\s+(\d+)', chunk)
    data["Hari Tunggakan"] = tunggakan_match.group(1) if tunggakan_match else "0"

    # --- Tanggal Mulai ---
    tgl_mulai_match = re.search(r'Tanggal Mulai\s+(\d{2}\s+\w+\s+\d{4})', chunk)
    data["Tanggal Mulai"] = _format_date_excel(tgl_mulai_match.group(1)) if tgl_mulai_match else "-"

    # --- Tanggal Jatuh Tempo ---
    tgl_jto_match = re.search(r'Tanggal Jatuh Tempo\s+(\d{2}\s+\w+\s+\d{4})', chunk)
    data["Tanggal JTO"] = _format_date_excel(tgl_jto_match.group(1)) if tgl_jto_match else "-"

    # --- Plafon Awal ---
    plafon_match = re.search(r'Plafon Awal\s+Rp\s*([\d\.,]+)', chunk)
    if plafon_match:
        plafon_int = _parse_currency_to_int(plafon_match.group(1))
        data["Plafon"] = _format_rupiah(plafon_int)
    else:
        data["Plafon"] = "-"

    # --- Suku Bunga ---
    bunga_match = re.search(r'Suku Bunga/Imbalan\s+([\d\.,]+)\s*%', chunk)
    data["Suku Bunga"] = f"{bunga_match.group(1)}%" if bunga_match else "-"

    # --- Jenis Penggunaan (Fasilitas) ---
    fasilitas_match = re.search(r'Jenis Penggunaan\s+(.*?)\s+Frekuensi\s+Restrukturisasi', chunk, re.DOTALL)
    if fasilitas_match:
        fasilitas = fasilitas_match.group(1).strip()
        fasilitas = re.sub(r'\s+', ' ', fasilitas)
        data["Fasilitas"] = fasilitas
    else:
        data["Fasilitas"] = "-"

    # --- Jenis Kredit/Pembiayaan (for Kartu Kredit detection) ---
    jenis_kredit_match = re.search(r'Jenis Kredit/Pembiayaan\s+(.*?)(?:\n|$)', chunk)
    is_kartu_kredit = bool(jenis_kredit_match and 'Kartu Kredit' in jenis_kredit_match.group(1))

    # --- Agunan (Bukti Kepemilikan + Jenis Agunan) ---
    bukti_items = []
    bukti_matches = re.findall(r'Bukti Kepemilikan\s+(.*?)(?:\s+Nilai|\n)', chunk)
    bukti_items.extend(m.strip() for m in bukti_matches if m.strip())

    jenis_items = []
    jenis_matches = re.findall(r'Jenis Agunan\s+Nilai Agunan.*?\n\s*(.*?)\s+Rp', chunk)
    jenis_items.extend(m.strip() for m in jenis_matches if m.strip())

    if is_kartu_kredit:
        data["Agunan"] = "Kartu Kredit"
    elif bukti_items or jenis_items:
        data["Agunan"] = _format_agunan_summary(bukti_items, jenis_items)
    else:
        data["Agunan"] = "-"

    return data


# ---------------------------------------------------------------------------
# 3. Agunan Summary Helper
# ---------------------------------------------------------------------------

def _format_agunan_summary(bukti_items: list, jenis_items: list) -> str:
    """
    Summarise agunan items for display.

    - Group Bukti Kepemilikan by type prefix (SHM, SHGB, etc.)
    - Group Jenis Agunan by name (Tanah, Rumah, etc.)
    - If a group has <= 3 items  → list them
    - If a group has  > 3 items → just show count, e.g. "6 SHM"
    """
    from collections import Counter, defaultdict

    # --- Group Bukti Kepemilikan by type prefix ---
    bukti_groups: dict[str, list[str]] = defaultdict(list)
    for item in bukti_items:
        # Extract type prefix: "SHM NO 7880" → "SHM", "SHGB.9240" → "SHGB"
        type_match = re.match(r'(SHM|SHGB|SKHMT|AJB|BPKB|PPJB|IMB|SIPPT)\b', item, re.IGNORECASE)
        type_key = type_match.group(1).upper() if type_match else "Lainnya"
        bukti_groups[type_key].append(item)

    # --- Count Jenis Agunan ---
    jenis_counts = Counter(jenis_items)

    # --- Format output ---
    parts = []

    # Bukti Kepemilikan groups
    for type_key, items in bukti_groups.items():
        if len(items) <= 3:
            parts.append(", ".join(items))
        else:
            parts.append(f"{len(items)} {type_key}")

    # Jenis Agunan groups
    for jenis, count in jenis_counts.items():
        if count <= 3:
            parts.append(jenis if count == 1 else f"{jenis} ({count})")
        else:
            parts.append(f"{count} {jenis}")

    return " | ".join(parts) if parts else "-"


# ---------------------------------------------------------------------------
# 4. Date & Currency Helpers
# ---------------------------------------------------------------------------

# Indonesian month name -> number mapping
_BULAN = {
    'januari': '01', 'februari': '02', 'maret': '03', 'april': '04',
    'mei': '05', 'juni': '06', 'juli': '07', 'agustus': '08',
    'september': '09', 'oktober': '10', 'november': '11', 'desember': '12',
}


def _format_date_excel(date_str: str) -> str:
    """
    Convert Indonesian date '27 September 2021' -> '27/09/2021'
    which Excel auto-recognises as a date.
    """
    try:
        parts = date_str.strip().split()
        if len(parts) != 3:
            return date_str
        day, month_name, year = parts
        month_num = _BULAN.get(month_name.lower(), '00')
        return f"{int(day)}/{month_num}/{year}"
    except (ValueError, AttributeError):
        return date_str

def _parse_currency_to_int(value: str) -> int:
    """
    Parse Indonesian currency string to integer.
    '383.570.669,00' -> 383570669
    '0,00' -> 0
    """
    try:
        # Strip everything after the comma (decimal part)
        value = value.split(',')[0]
        # Remove thousand separators (dots)
        value = value.replace('.', '')
        return int(value)
    except (ValueError, AttributeError):
        return 0


def _format_rupiah(amount: int) -> str:
    """
    Format integer as Indonesian Rupiah string.
    383570669 -> 'Rp 383.570.669'
    """
    if amount == 0:
        return "Rp 0"
    # Format with dots as thousand separators
    formatted = f"{amount:,}".replace(',', '.')
    return f"Rp {formatted}"


# ---------------------------------------------------------------------------
# 4. Excel Export
# ---------------------------------------------------------------------------

def export_to_excel(df: pd.DataFrame, summary_df: pd.DataFrame = None) -> bytes:
    """
    Export DataFrame to Excel bytes (for Streamlit download button).
    Includes a summary sheet if summary_df is provided.
    """
    # Drop the Raw column from the export
    export_df = df.drop(columns=["Baki Debet (Raw)"], errors="ignore")

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Fasilitas Aktif')
        _auto_adjust_columns(writer, 'Fasilitas Aktif', export_df)

        if summary_df is not None and not summary_df.empty:
            summary_df.to_excel(writer, index=False, sheet_name='Ringkasan per Debitur')
            _auto_adjust_columns(writer, 'Ringkasan per Debitur', summary_df)

    return output.getvalue()


def _auto_adjust_columns(writer, sheet_name: str, df: pd.DataFrame):
    """Auto-adjust column widths in an Excel worksheet."""
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_length = max(
            df[col].astype(str).map(len).max() if len(df) > 0 else 0,
            len(col)
        ) + 3
        col_letter = chr(65 + i) if i < 26 else f"A{chr(65 + i - 26)}"
        worksheet.column_dimensions[col_letter].width = min(max_length, 40)


def build_debtor_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a summary of total outstanding (Baki Debet) per unique debtor.
    """
    if df.empty or "Baki Debet (Raw)" not in df.columns:
        return pd.DataFrame()

    summary = df.groupby("Nama Debitur").agg(
        Jumlah_Fasilitas=("Baki Debet (Raw)", "count"),
        Total_Outstanding=("Baki Debet (Raw)", "sum"),
    ).reset_index()

    summary.columns = ["Nama Debitur", "Jumlah Fasilitas", "Total Outstanding (Raw)"]
    summary["Total Outstanding"] = summary["Total Outstanding (Raw)"].apply(_format_rupiah)
    summary = summary.sort_values("Total Outstanding (Raw)", ascending=False)
    summary = summary[["Nama Debitur", "Jumlah Fasilitas", "Total Outstanding", "Total Outstanding (Raw)"]]

    return summary
