"""Verify Pelapor names + Kartu Kredit — output to file."""
from slik_parser import extract_text_from_pdf, parse_slik_data

with open("verify_out.txt", "w", encoding="utf-8") as f:
    for fname in ["SAKUAN IDEB 259.pdf", "SUPRIADI IDEB 261.pdf", "PT INDO 051.pdf", "YAYASAN IDEB 255.pdf"]:
        path = rf"IDEB\YayasanBumiMaitri_240226\{fname}"
        text, nama = extract_text_from_pdf(path)
        df = parse_slik_data(text, nama)
        f.write(f"=== {fname} ({len(df)} facilities) ===\n")
        for i, r in df.iterrows():
            f.write(f"  [{i}] Pelapor: {r['Pelapor']}\n")
            f.write(f"       Fasilitas={r['Fasilitas']} | Kol={r['Kol']} | Agunan={r['Agunan']}\n")
        f.write("\n")

print("Done -> verify_out.txt")
