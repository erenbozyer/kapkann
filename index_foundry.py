"""
index_foundry.py — KAP Vektör İndeksleme (Faz 1: Content)

KAP_DATA altındaki tüm JSON bildirimlerini okur, chunk'lar,
Foundry Local (OpenAI API - http://127.0.0.1:56400/v1) üzerinden 
qwen3-embedding-0.6b ile vektörleştirir ve SQLite + sqlite-vec'e yazar.

Kullanım:
    python index_foundry.py
    python index_foundry.py --data-dir ./KAP_DATA --db kap_vectors.db --batch-size 32
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

import sqlite3
import sqlite_vec
from openai import OpenAI

# Yerel modüller
from chunker import chunk_disclosure, Chunk


FOUNDRY_BASE_URL = "http://127.0.0.1:56400/v1"
EMBEDDING_MODEL = "qwen3-embedding-0.6b"


# ──────────────────────────── Helpers ────────────────────────────

def serialize_f32(vec: list[float]) -> bytes:
    """Float listesini sqlite-vec'in beklediği binary formata çevir."""
    return struct.pack(f"{len(vec)}f", *vec)


def create_db(db_path: str) -> sqlite3.Connection:
    """SQLite veritabanını oluştur ve sqlite-vec uzantısını yükle."""
    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    # Metadata tablosu
    db.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            company_name TEXT,
            type TEXT,
            date TEXT,
            title TEXT,
            summary TEXT,
            text TEXT NOT NULL,
            source_index INTEGER,
            source_url TEXT,
            source_type TEXT DEFAULT 'content',
            attachment_filename TEXT
        )
    """)

    # İndeksler
    db.execute("CREATE INDEX IF NOT EXISTS idx_company ON chunks(company)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_type ON chunks(type)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_date ON chunks(date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_source_type ON chunks(source_type)")

    db.commit()
    return db


def create_vec_table(db: sqlite3.Connection, dim: int):
    """Embedding boyutu belli olduktan sonra vektör tablosunu oluştur."""
    db.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            id INTEGER PRIMARY KEY,
            embedding float[{dim}]
        )
    """)
    db.commit()


def collect_json_files(data_dir: str) -> list[str]:
    """KAP_DATA altındaki tüm JSON dosyalarının yollarını topla."""
    files = []
    for company_dir in sorted(os.listdir(data_dir)):
        company_path = os.path.join(data_dir, company_dir)
        if not os.path.isdir(company_path):
            continue
        for fname in sorted(os.listdir(company_path)):
            if fname.endswith(".json"):
                files.append(os.path.join(company_path, fname))
    return files


def get_indexed_sources(db: sqlite3.Connection) -> set[int]:
    """Zaten indekslenmiş bildirim numaralarını getir (resume için)."""
    try:
        rows = db.execute(
            "SELECT DISTINCT source_index FROM chunks WHERE source_type = 'content'"
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


# ──────────────────────────── Main ────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="KAP bildirimlerini vektör indeksle")
    parser.add_argument("--data-dir", default="KAP_DATA", help="KAP_DATA klasör yolu")
    parser.add_argument("--db", default="kap_vectors.db", help="SQLite DB dosya yolu")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch boyutu")
    parser.add_argument("--max-chunk-size", type=int, default=1500, help="Max chunk karakter")
    parser.add_argument("--overlap", type=int, default=200, help="Chunk overlap karakter")
    parser.add_argument("--resume", action="store_true", help="Kaldığı yerden devam et")
    args = parser.parse_args()

    data_dir = os.path.join(os.path.dirname(__file__) or ".", args.data_dir)
    db_path = os.path.join(os.path.dirname(__file__) or ".", args.db)

    # ─── 1. JSON dosyalarını topla ───
    print(f"📂 KAP verileri taranıyor: {data_dir}")
    json_files = collect_json_files(data_dir)
    print(f"   Toplam JSON dosya: {len(json_files)}")

    if not json_files:
        print("❌ Hiç JSON dosyası bulunamadı!")
        sys.exit(1)

    # ─── 2. SQLite veritabanını oluştur ───
    print(f"\n💾 Veritabanı: {db_path}")
    db = create_db(db_path)

    indexed = set()
    if args.resume:
        indexed = get_indexed_sources(db)
        print(f"   Zaten indekslenmiş: {len(indexed)} bildirim (atlayacak)")

    # ─── 3. OpenAI Client (Foundry Local Server) ───
    print(f"\n🤖 Foundry Local Server bağlanılıyor ({FOUNDRY_BASE_URL})...")
    client = OpenAI(base_url=FOUNDRY_BASE_URL, api_key="none")

    # Test embedding
    try:
        test_res = client.embeddings.create(model=EMBEDDING_MODEL, input="test")
        embed_dim = len(test_res.data[0].embedding)
        print(f"   ✅ Model '{EMBEDDING_MODEL}' hazır, embedding boyutu: {embed_dim}")
    except Exception as e:
        print(f"❌ Model yükleme hatası: {e}")
        print(f"   Lütfen 'foundry model load {EMBEDDING_MODEL}' komutunu çalıştırın.")
        sys.exit(1)

    create_vec_table(db, embed_dim)

    # ─── 4. İndeksleme döngüsü ───
    print(f"\n🚀 İndeksleme başlıyor (batch_size={args.batch_size})...\n")

    total_chunks = 0
    total_skipped = 0
    total_errors = 0
    start_time = time.time()

    pending_chunks: list[Chunk] = []
    pending_texts: list[str] = []

    for file_idx, fpath in enumerate(json_files):
        if (file_idx + 1) % 100 == 0 or file_idx == 0:
            elapsed = time.time() - start_time
            rate = (file_idx + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(json_files) - file_idx - 1) / rate if rate > 0 else 0
            print(
                f"  [{file_idx + 1}/{len(json_files)}] "
                f"chunk={total_chunks} skip={total_skipped} err={total_errors} "
                f"({rate:.0f} dosya/sn, ~{remaining/60:.1f}dk kaldı)",
                flush=True
            )

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            total_errors += 1
            continue

        source_idx = data.get("index", 0)
        if args.resume and source_idx in indexed:
            total_skipped += 1
            continue

        max_s = args.max_chunk_size if args.max_chunk_size != 1500 else None
        ovr = args.overlap if args.overlap != 200 else None
        chunks = chunk_disclosure(data, max_s, ovr)

        if not chunks:
            continue

        for chunk in chunks:
            pending_chunks.append(chunk)
            pending_texts.append(chunk.text)

        while len(pending_texts) >= args.batch_size:
            batch_texts = pending_texts[:args.batch_size]
            batch_chunks = pending_chunks[:args.batch_size]
            pending_texts = pending_texts[args.batch_size:]
            pending_chunks = pending_chunks[args.batch_size:]

            _embed_and_store(db, client, batch_chunks, batch_texts)
            total_chunks += len(batch_chunks)

    if pending_texts:
        _embed_and_store(db, client, pending_chunks, pending_texts)
        total_chunks += len(pending_chunks)

    # ─── 5. Sonuç ───
    elapsed = time.time() - start_time
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"✅ İndeksleme tamamlandı!")
    print(f"   Toplam chunk: {total_chunks}")
    print(f"   Atlanan (resume): {total_skipped}")
    print(f"   Hatalar: {total_errors}")
    print(f"   Süre: {elapsed/60:.1f} dakika")
    print(f"   DB boyutu: {db_size_mb:.1f} MB")
    print(f"   Dosya: {db_path}")
    print(f"{'='*60}")

    row = db.execute("SELECT COUNT(*) FROM chunks").fetchone()
    vec_row = db.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()
    print(f"\n🔍 Doğrulama:")
    print(f"   chunks tablosu: {row[0]} kayıt")
    print(f"   vec_chunks tablosu: {vec_row[0]} kayıt")

    company_count = db.execute("SELECT COUNT(DISTINCT company) FROM chunks").fetchone()
    print(f"   Benzersiz şirket: {company_count[0]}")

    db.close()
    print("\n🎉 İndeksleme tamamlandı, DB kapatıldı.")


def _embed_and_store(
    db: sqlite3.Connection,
    client: OpenAI,
    chunks: list[Chunk],
    texts: list[str],
):
    """Bir batch chunk'ı OpenAI API üzerinden embed et ve veritabanına yaz."""
    res = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)

    for chunk, emb_data in zip(chunks, res.data):
        embedding = emb_data.embedding

        cursor = db.execute(
            """INSERT INTO chunks 
               (company, company_name, type, date, title, summary, 
                text, source_index, source_url, source_type, attachment_filename)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.company,
                chunk.company_name,
                chunk.type,
                chunk.date,
                chunk.title,
                chunk.summary,
                chunk.text,
                chunk.source_index,
                chunk.source_url,
                chunk.source_type,
                chunk.attachment_filename,
            ),
        )
        chunk_id = cursor.lastrowid

        db.execute(
            "INSERT INTO vec_chunks (id, embedding) VALUES (?, ?)",
            (chunk_id, serialize_f32(embedding)),
        )

    db.commit()


if __name__ == "__main__":
    main()
