"""
chunker.py — KAP Bildirim Metin Bölme Modülü (Tablo & Finansal Rapor Korumalı)

Bildirimleri türüne (FR vs ODA/DG) ve metin yapısına göre dinamik olarak böler.
Finansal Raporlar (FR) için sayısal tabloları ve dipnotları tek parça halinde
korumak amacıyla daha geniş chunk boyutu (3500 char) ve akıllı tablo birleştirme kullanır.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    """Tek bir metin parçası + metadata."""
    text: str
    company: str
    company_name: str
    type: str              # ODA, FR, DG
    date: str
    title: str
    summary: str
    source_index: int      # KAP bildirim numarası
    source_url: str
    source_type: str = "content"          # "content" veya "pdf_attachment"
    attachment_filename: Optional[str] = None
    chunk_index: int = 0   # Bu bildirimdeki kaçıncı chunk


def _is_numeric_or_table_line(line: str) -> bool:
    """Satırın sayısal bir bilanço/tablo verisi olup olmadığını kontrol eder."""
    line = line.strip()
    if not line:
        return False
    # Sadece sayılar, virgül, nokta, eksi işareti ve yüzde simgesinden oluşuyorsa veya çok kısa sayısal etiketse
    if re.match(r"^[\d\.\,\-\%\s\/]+$", line):
        return True
    return False


def preprocess_financial_text(text: str) -> str:
    """
    Finansal raporlardaki kopuk satırları ve sayısal verileri gruplar.
    Ardışık kısa sayısal satırları tek bir tablo satırında birleştirir.
    """
    lines = text.split("\n")
    processed_lines = []
    current_table_block = []

    for line in lines:
        stripped = line.strip()
        if _is_numeric_or_table_line(stripped):
            current_table_block.append(stripped)
        else:
            if current_table_block:
                # Tablo sayı bloğunu tek satırda veya derli toplu birleştir
                processed_lines.append(" | ".join(current_table_block))
                current_table_block = []
            if stripped:
                processed_lines.append(stripped)

    if current_table_block:
        processed_lines.append(" | ".join(current_table_block))

    return "\n".join(processed_lines)


def recursive_split(
    text: str,
    max_size: int = 1500,
    overlap: int = 200,
    separators: Optional[List[str]] = None,
) -> List[str]:
    """
    Metni recursive olarak böler.
    Öncelik sırası: \\n\\n → \\n → . → boşluk
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", " "]

    if len(text) <= max_size:
        stripped = text.strip()
        return [stripped] if stripped else []

    chunks: List[str] = []
    sep = separators[0] if separators else ""
    remaining_separators = separators[1:] if len(separators) > 1 else []

    if sep and sep in text:
        parts = text.split(sep)
    else:
        if remaining_separators:
            return recursive_split(text, max_size, overlap, remaining_separators)
        else:
            return _force_split(text, max_size, overlap)

    current = ""
    for part in parts:
        candidate = (current + sep + part) if current else part

        if len(candidate) <= max_size:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())

            if len(part) > max_size:
                if remaining_separators:
                    sub_chunks = recursive_split(part, max_size, overlap, remaining_separators)
                else:
                    sub_chunks = _force_split(part, max_size, overlap)
                chunks.extend(sub_chunks)
                current = ""
            else:
                if overlap > 0 and current:
                    overlap_text = current[-overlap:] if len(current) > overlap else current
                    current = overlap_text + sep + part
                    if len(current) > max_size:
                        current = part
                else:
                    current = part

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _force_split(text: str, max_size: int, overlap: int) -> List[str]:
    """Hiçbir ayırıcı bulunamadığında karakter bazlı böl."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if overlap > 0 else end
        if start >= len(text) - overlap:
            remaining = text[start:].strip()
            if remaining and (not chunks or remaining != chunks[-1]):
                chunks.append(remaining)
            break
    return chunks


def chunk_disclosure(
    data: dict,
    max_size: Optional[int] = None,
    overlap: Optional[int] = None,
) -> List[Chunk]:
    """
    Tek bir KAP bildirim JSON'ını türüne göre dinamik parametrelerle chunk'lara böler.
    
    - FR (Finansal Rapor): max_size=3500, overlap=500 + Tablo birleştirme
    - ODA / DG (Özel Durum / Diğer): max_size=1500, overlap=250
    """
    content = data.get("content", "")
    if not content or not content.strip():
        return []

    doc_type = (data.get("type") or "").upper()

    # Dinamik Boyut Ayarı
    if max_size is None or overlap is None:
        if doc_type == "FR":
            max_size = 3500
            overlap = 500
        else:
            max_size = 1500
            overlap = 250

    title = data.get("title", "")
    summary = data.get("summary", "")

    # FR için metindeki kopuk tablo rakamlarını birleştir
    if doc_type == "FR":
        content = preprocess_financial_text(content)

    header = ""
    if title:
        header += f"{title}\n"
    if summary and summary != title:
        header += f"{summary}\n"

    full_text = header + content if header else content

    text_chunks = recursive_split(full_text, max_size, overlap)

    chunks = []
    for i, text in enumerate(text_chunks):
        chunk = Chunk(
            text=text,
            company=data.get("company", ""),
            company_name=data.get("company_name", ""),
            type=doc_type,
            date=data.get("date", ""),
            title=title,
            summary=summary,
            source_index=data.get("index", 0),
            source_url=data.get("url", ""),
            source_type="content",
            attachment_filename=None,
            chunk_index=i,
        )
        chunks.append(chunk)

    return chunks


def chunk_pdf_text(
    text: str,
    disclosure_data: dict,
    attachment_filename: str,
    max_size: int = 2500,
    overlap: int = 350,
) -> List[Chunk]:
    """PDF'den çıkarılmış metni chunk'lara böler."""
    if not text or not text.strip():
        return []

    text_chunks = recursive_split(text, max_size, overlap)

    chunks = []
    for i, chunk_text in enumerate(text_chunks):
        chunk = Chunk(
            text=chunk_text,
            company=disclosure_data.get("company", ""),
            company_name=disclosure_data.get("company_name", ""),
            type=disclosure_data.get("type", ""),
            date=disclosure_data.get("date", ""),
            title=disclosure_data.get("title", ""),
            summary=disclosure_data.get("summary", ""),
            source_index=disclosure_data.get("index", 0),
            source_url=disclosure_data.get("url", ""),
            source_type="pdf_attachment",
            attachment_filename=attachment_filename,
            chunk_index=i,
        )
        chunks.append(chunk)

    return chunks


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        chunks = chunk_disclosure(data)
        print(f"Dosya: {sys.argv[1]}")
        print(f"Tür: {data.get('type')}")
        print(f"Content uzunluğu: {len(data.get('content', ''))} karakter")
        print(f"Chunk sayısı: {len(chunks)}")
        for i in range(min(5, len(chunks))):
            c = chunks[i]
            print(f"\n--- Chunk {i} ({len(c.text)} char) ---")
            print(c.text[:300] + "..." if len(c.text) > 300 else c.text)
