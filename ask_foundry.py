"""
ask_foundry.py — KAP RAG Sorgu Motoru (Rakip Düzeyi Finansal Bilanço & Analiz)

Kullanıcının sorusunu alır, finansal terim algılaması (FR / Bilanço doğrudan erişim) yapar,
en güncel KAP bilanço verilerini tablolandırır ve Phi-4-mini ile profesyonel 
Markdown Tablo + Analist yorumu formatında cevap üretir.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import time

import sqlite3
import sqlite_vec
from openai import OpenAI


# ──────────────────────────── Config ────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__) or ".", "kap_vectors.db")
EMBEDDING_MODEL = "qwen3-embedding-0.6b"
CHAT_MODEL = "phi-4-mini"

SYSTEM_PROMPT = """Sen BİST şirketlerinin KAP (Kamu Aydınlatma Platformu) bildirimlerini ve finansal raporlarını analiz eden kıdemli bir Finansal Analist yapay zekasısın.

Sana verilen KAP bildirim ve bilanço metinlerini dikkatle inceleyerek kullanıcı sorusuna tam, şık ve profesyonel bir finansal rapor formatında yanıt ver.

CEVAP FORMATI VE YAPI KURALLARI:
1. **Başlık**: 📊 [Şirket Kodu/Adı] Finansal Rapor & Bilanço Özeti — [Tarih/Dönem]
2. **Finansal Rapor / Bilanço Özeti (Tablo Formatında)**:
   Metindeki finansal tablolarda geçen rakamları (Hasılat, Brüt Kâr, Esas Faaliyet Kârı/Zararı, Dönem Net Kârı, Toplam Varlıklar, Özkaynaklar, Yükümlülükler vb.) aşağıdaki gibi Markdown Tablosu halinde sun:

   | Kalem | Değer (Bin TL / TL) |
   | :--- | :--- |
   | Hasılat / Ciro | ... |
   | Brüt Kâr | ... |
   | Esas Faaliyet Kârı/Zararı | ... |
   | Dönem Net Kârı / Zararı | ... |
   | Toplam Varlıklar | ... |
   | Toplam Özkaynaklar | ... |
   | Toplam Yükümlülükler | ... |

3. **🔑 Temel Finansal Kalemler & Borç Yapısı**:
   Kısa ve uzun vadeli yükümlülükler ile borç yapısını özetle.
4. **💰 Kârlılık ve Operasyonel Görünüm**:
   Şirketin ciro, kârlılık veya faaliyet kârı gidişatını 2-3 cümle ile değerlendir.
5. **⚠️ Genel Durum ve Analist Yorumu**:
   Özkaynak gücü, finansal yapı ve stratejik kararlar hakkında net bir genel değerlendirme yap.

- Sadece sağlanan KAP kaynaklarındaki somut rakam ve bilgilere dayan.
- Metinde yer alan sayısal verileri tam aktar, Türkçe dilini profesyonel kullan."""


def get_foundry_base_url() -> str:
    """Foundry Local server adresini dinamik tespit et."""
    try:
        res = subprocess.run(["foundry", "status", "-o", "json"], capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            urls = data.get("service", {}).get("webUrls", [])
            if urls:
                return urls[0].rstrip("/") + "/v1"
    except Exception:
        pass
    return "http://127.0.0.1:51667/v1"


def serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def open_db(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"❌ Veritabanı bulunamadı: {db_path}")
        sys.exit(1)

    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.row_factory = sqlite3.Row
    return db


def ask_kap(
    question: str,
    db: sqlite3.Connection,
    client: OpenAI,
    chat_model_name: str = CHAT_MODEL,
    company_filter: str = None,
    type_filter: str = None,
    top_k: int = 5,
) -> dict:
    start = time.time()

    # 0. Finansal Terim Niyet Algılama (Intent Detection)
    fin_keywords = [
        "finansal", "rapor", "bilanço", "bilanco", "gelir", "kar", "kâr", 
        "zarar", "hasılat", "ciro", "özkaynak", "ozkaynak", "varlık", "borç", "borc", "marj", "durum"
    ]
    is_financial_query = any(w in question.lower() for w in fin_keywords)

    matched_chunks = []
    seen_ids = set()

    # Eğer finansal sorgu ve şirket belli ise doğrudan o şirketin en son FR (Finansal Rapor) chunk'larını çek
    if is_financial_query and company_filter and not type_filter:
        comp_str = company_filter.upper()
        fr_rows = db.execute(
            """
            SELECT * FROM chunks 
            WHERE (company = ? OR company LIKE ?) AND type = 'FR'
            ORDER BY date DESC
            LIMIT 4
            """,
            (comp_str, f"%{comp_str}%"),
        ).fetchall()
        for r in fr_rows:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                matched_chunks.append(r)

    # Vektör Araması (Eksik kalan kısımları vektör benzerliğine göre tamamla)
    if len(matched_chunks) < top_k:
        subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL], capture_output=True)
        q_res = client.embeddings.create(model=EMBEDDING_MODEL, input=question)
        subprocess.run(["foundry", "model", "unload", EMBEDDING_MODEL], capture_output=True)

        q_embedding = q_res.data[0].embedding
        q_blob = serialize_f32(q_embedding)

        fetch_count = top_k * 20 if (company_filter or type_filter) else top_k * 5
        vec_rows = db.execute(
            """
            SELECT v.id, v.distance
            FROM vec_chunks v
            WHERE v.embedding MATCH ?
            ORDER BY v.distance
            LIMIT ?
            """,
            (q_blob, fetch_count),
        ).fetchall()

        if vec_rows:
            candidate_ids = [r["id"] for r in vec_rows if r["id"] not in seen_ids]
            if candidate_ids:
                placeholders = ",".join(["?" for _ in candidate_ids])
                sql = f"SELECT * FROM chunks WHERE id IN ({placeholders})"
                params = list(candidate_ids)

                if company_filter:
                    sql += " AND (company = ? OR company LIKE ?)"
                    params.extend([company_filter.upper(), f"%{company_filter.upper()}%"])
                if type_filter:
                    sql += " AND type = ?"
                    params.append(type_filter.upper())

                sql += " ORDER BY date DESC"
                vec_matched = db.execute(sql, params).fetchall()
                for r in vec_matched:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        matched_chunks.append(r)
                        if len(matched_chunks) >= top_k:
                            break

    matched_chunks = matched_chunks[:top_k]

    if not matched_chunks:
        filter_msg = ""
        if company_filter:
            filter_msg += f" (şirket: {company_filter})"
        if type_filter:
            filter_msg += f" (tür: {type_filter})"
        return {
            "answer": f"Bu filtrelerle{filter_msg} KAP verilerinde bilgi bulunamadı.",
            "sources": [],
            "chunks_used": 0,
            "query_time_ms": (time.time() - start) * 1000,
        }

    # Context Oluşturma
    context_parts = []
    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - Tür: {chunk['type']} | Tarih: {chunk['date']}] Şirket: {chunk['company']} | Başlık: {chunk['title'] or ''}"
        snippet = chunk['text'][:1200]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    # LLM'e Sor (phi-4-mini)
    subprocess.run(["foundry", "model", "load", CHAT_MODEL], capture_output=True)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"KAP FİNANSAL RAPOR VE BİLDİRİM KAYNAKLARI:\n{context}\n\n"
                       f"SORU: {question}\n\n"
                       f"Yukarıdaki KAP verilerindeki rakamları kullanarak soruları Markdown Tablosu (📊) ve analiz başlıkları (🔑, 💰, ⚠️) halinde yanıtla:",
        },
    ]

    chat_res = client.chat.completions.create(
        model=chat_model_name,
        messages=messages,
        max_tokens=700,
        temperature=0.2,
    )
    answer = chat_res.choices[0].message.content
    if "<think>" in answer and "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

    # Kaynaklar
    seen_sources = set()
    sources = []
    for i, chunk in enumerate(matched_chunks):
        source_key = (chunk["source_index"], chunk["source_type"], chunk["attachment_filename"])
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            source = {
                "company": chunk["company"],
                "company_name": chunk["company_name"],
                "title": chunk["title"],
                "date": chunk["date"],
                "type": chunk["type"],
                "url": chunk["source_url"],
                "source_type": chunk["source_type"],
                "attachment_filename": chunk["attachment_filename"],
                "relevance_rank": i + 1,
            }
            sources.append(source)

    query_time = (time.time() - start) * 1000

    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(matched_chunks),
        "query_time_ms": round(query_time, 1),
    }


def print_result(result: dict):
    print(f"\n{'='*60}")
    print(f"📝 Cevap:\n")
    print(result["answer"])

    print(f"\n{'─'*60}")
    print(f"📎 Kaynaklar ({len(result['sources'])} bildirim):\n")

    for i, src in enumerate(result["sources"]):
        icon = "📊" if src["type"] == "FR" else "📄"
        line = f"  {i+1}. {icon} [{src['date']}] {src['company']} ({src['type']}) — {src['title']}"
        if src["source_type"] == "pdf_attachment" and src["attachment_filename"]:
            line += f"\n     📁 PDF: {src['attachment_filename']}"
        line += f"\n     🔗 {src['url']}"
        print(line)

    print(f"\n{'─'*60}")
    print(f"⚡ {result['chunks_used']} chunk kullanıldı, {result['query_time_ms']:.0f}ms")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="KAP RAG Sorgu Motoru (Finansal Tablo & Rakip Düzeyi)")
    parser.add_argument("question", nargs="?", help="Sorulacak soru")
    parser.add_argument("--company", "-c", help="Şirket kodu filtresi (THYAO, AKBNK...)")
    parser.add_argument("--type", "-t", help="Bildirim türü filtresi (ODA, FR, DG)")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="Getirilecek chunk sayısı")
    parser.add_argument("--db", default=DB_PATH, help="Vektör DB yolu")
    parser.add_argument("--chat-model", default=CHAT_MODEL, help="Chat LLM modeli")
    args = parser.parse_args()

    if not args.question:
        print("⚠️  Lütfen bir soru girin.")
        sys.exit(1)

    db = open_db(args.db)
    base_url = get_foundry_base_url()
    client = OpenAI(base_url=base_url, api_key="none")

    result = ask_kap(
        args.question, db, client,
        chat_model_name=args.chat_model,
        company_filter=args.company,
        type_filter=args.type,
        top_k=args.top_k,
    )
    print_result(result)

    db.close()


if __name__ == "__main__":
    main()
