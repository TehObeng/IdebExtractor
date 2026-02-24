"""Debug: show raw pelapor lines - write to file."""
import re
import pdfplumber

with open("debug_out.txt", "w", encoding="utf-8") as out:
    for fname in ["SAKUAN IDEB 259.pdf", "YAYASAN IDEB 255.pdf", "PT INDO 051.pdf", "SUPRIADI IDEB 261.pdf"]:
        path = rf"IDEB\YayasanBumiMaitri_240226\{fname}"
        pdf = pdfplumber.open(path)
        full = ""
        for p in pdf.pages:
            full += (p.extract_text() or "") + "\n"
        pdf.close()

        chunks = re.split(r'Kredit/Pembiayaan\s*\n\s*Pelapor\s+Cabang\s+Baki Debet\s+Tanggal Update', full)
        out.write(f"=== {fname} ({len(chunks)-1} chunks) ===\n")
        for i, chunk in enumerate(chunks[1:], 1):
            lines = chunk.strip().split('\n')[:3]
            out.write(f"  Chunk {i}:\n")
            for l in lines:
                out.write(f"    |{l}|\n")
        out.write("\n")

print("Done -> debug_out.txt")
