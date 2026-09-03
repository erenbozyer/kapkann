"""
ask_foundry.py — KAP RAG Sorgu Motoru (Gerçek Matematiksel Bilanço & Analiz Motoru)

SQLite veritabanından doğrudan GERÇEK bilanço kalemlerini (Hasılat, Dönen Varlıklar, 
Kısa/Uzun Borçlar, Özkaynaklar) çekip, cari oran ve kaldıraç rasyolarını hesaplayarak 
100% gerçek sayılarla Bilanço Karnesi ve Analist Raporu üretir.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

SYSTEM_PROMPT = """Sen BİST şirketlerinin KAP verilerini derinlemesine inceleyen bağımsız ve kıdemli bir Finansal Analist yapay zekasısın.

Sana verilen GERÇEK BİLANÇO RAKAMLARINI (Hasılat, Dönen Varlıklar, Borçlar, Özkaynaklar) ve KAP bildirim metinlerini kullanarak kullanıcıya 100% gerçek verili ve profesyonel bir Bilanço Karnesi üret.

KURALLAR:
1. **Gerçek Rakamları Kullan**: Metinde sağlanan somut finansal verileri (TL / Bin TL) birebir tabloya ve analize yansıt. Tablodaki puan sütununa (ör: 4.2 / 5) somut puanları yaz, asla '... / 5' bırakma!
2. **Asla Şablon Kopyalama**: Örnek kelimeleri veya uydurma rakamları kullanma!
3. **Puanlama**: Cari Oran (Dönen Varlıklar / Kısa Borçlar) ve Borç/Özkaynak dengesine dayanarak 5 üzerinden objektif puanlar ver.

CEVAP YAPISI:

📋 **[ŞİRKET_KODU] Bilanço Karnesi & Finansal Rapor Özeti · [DÖNEM]**
⭐ **Genel Finansal Skor:** [SKOR]/5 — [Değerlendirme (Zayıf / Orta / İyi / Çok İyi)]

| Finansal Kalem / Kategori | Gerçek Değer (Bin TL) | Puan (5 Üzerinden) | Analiz Özeti |
| :--- | :--- | :---: | :--- |
| 📈 **Hasılat / Ciro** | [Rakam] | [Puan]/5 | [Ciro seviyesi ve büyüme] |
| 💧 **Dönen Varlıklar / Likidite** | [Rakam] | [Puan]/5 | [Cari Oran ve Nakit gücü] |
| 🛡️ **Borçlar & Yükümlülükler** | [Rakam] | [Puan]/5 | [Kısa ve Uzun Vadeli Borçlar] |
| ⚙️ **Toplam Özkaynaklar** | [Rakam] | [Puan]/5 | [Özkaynak büyüklüğü ve bilanço dengesi] |

📝 **Detaylı Analist Değerlendirmesi:**
[Şirketin bilanço büyüklüğü, cari oranı, borçluluk yapısı ve özkaynak gücü hakkında 3-4 cümlelik somut analist yorumu.]"""


def get_foundry_base_url() -> str:
    """Foundry Local server adresini dinamik tespit et (Windows shell=True destekli)."""
    try:
        res = subprocess.run("foundry status -o json", shell=True, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            urls = data.get("service", {}).get("webUrls", [])
            if urls:
                return urls[0].rstrip("/") + "/v1"
    except Exception:
        pass

    try:
        res = subprocess.run("foundry status", shell=True, capture_output=True, text=True)
        m = re.search(r"http://127\.0\.0\.1:\d+", res.stdout)
        if m:
            return m.group(0) + "/v1"
    except Exception:
        pass

    return "http://127.0.0.1:59812/v1"


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


def extract_real_financial_facts(db: sqlite3.Connection, company: str) -> dict:
    """
    SQLite DB içerisinden şirkete ait en son bilanço rakamlarını doğrudan ayıklar
    ve rasyoları hesaplar.
    """
    comp_str = company.upper()
    rows = db.execute(
        """
        SELECT date, text FROM chunks 
        WHERE (company = ? OR company LIKE ?) AND type = 'FR'
        ORDER BY date DESC
        LIMIT 35
        """,
        (comp_str, f"%{comp_str}%"),
    ).fetchall()

    if not rows:
        return {}

    latest_date = rows[0]["date"]
    facts = {}

    target_headers = {
        "TOPLAM DÖNEN VARLIKLAR": "donen_varliklar",
        "TOPLAM KISA VADELİ YÜKÜMLÜLÜKLER": "kisa_vadeli_borclar",
        "TOPLAM UZUN VADELİ YÜKÜMLÜLÜKLER": "uzun_vadeli_borclar",
        "TOPLAM ÖZKAYNAKLAR": "ozkaynaklar",
        "Hasılat": "hasilat",
    }

    for r in rows:
        if r["date"] != latest_date:
            continue
        lines = r["text"].splitlines()
        for j, line in enumerate(lines):
            clean_l = line.strip()
            for header, key in target_headers.items():
                if key not in facts and (header == clean_l or (header in clean_l and len(clean_l) < 40)):
                    val_idx = j + 1
                    while val_idx < len(lines) and val_idx < j + 4:
                        v_line = lines[val_idx].strip()
                        if re.search(r"\d+[\.\d]*", v_line):
                            facts[key] = v_line
                            break
                        val_idx += 1

    facts["date"] = latest_date
    return facts


def ask_kap(
    question: str,
    db: sqlite3.Connection,
    client: OpenAI,
    chat_model_name: str = CHAT_MODEL,
    company_filter: str = None,
    type_filter: str = None,
    top_k: int = 4,
) -> dict:
    start = time.time()

    q_lower = question.lower()
    karne_keywords = ["karne", "skor", "not", "derece", "karne nasıl", "performans", "trend", "net kar"]
    fin_keywords = ["finansal", "rapor", "bilanço", "bilanco", "gelir", "kar", "kâr", "zarar", "hasılat", "ciro", "özkaynak", "borç", "marj"]

    is_karne_query = any(w in q_lower for w in karne_keywords)
    is_financial_query = is_karne_query or any(w in q_lower for w in fin_keywords)

    real_facts_summary = ""
    matched_chunks = []
    seen_ids = set()

    # Gerçek veri ayıklama
    if company_filter:
        facts = extract_real_financial_facts(db, company_filter)
        if facts:
            fact_lines = [f"• {k.upper()}: {v}" for k, v in facts.items() if k != "date"]
            real_facts_summary = f"BİLANÇO TARİHİ: {facts.get('date')}\nAYIKLANAN DOĞRUDAN VERİLER:\n" + "\n".join(fact_lines)

    # Finansal Sorgularda FR bildirimlerini getir
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

    # Vektör Araması (Eksik durumunda)
    if len(matched_chunks) < top_k:
        subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL], capture_output=True)
        q_res = client.embeddings.create(model=EMBEDDING_MODEL, input=question)
        subprocess.run(["foundry", "model", "unload", EMBEDDING_MODEL], capture_output=True)

        q_embedding = q_res.data[0].embedding
        q_blob = serialize_f32(q_embedding)

        fetch_count = top_k * 15 if (company_filter or type_filter) else top_k * 5
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
        filter_msg = f" (şirket: {company_filter})" if company_filter else ""
        return {
            "answer": f"Bu filtrelerle{filter_msg} KAP verilerinde bilgi bulunamadı.",
            "sources": [],
            "chunks_used": 0,
            "query_time_ms": (time.time() - start) * 1000,
        }

    # Context Oluşturma
    context_parts = []
    if real_facts_summary:
        context_parts.append(f"[DOĞRUDAN GERÇEK BİLANÇO KALEMLERİ]\n{real_facts_summary}")

    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - {chunk['type']} | Tarih: {chunk['date']}] {chunk['company']} — {chunk['title'] or ''}"
        snippet = chunk['text'][:700]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    # LLM (phi-4-mini)
    subprocess.run(["foundry", "model", "load", CHAT_MODEL], capture_output=True)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"KAP GERÇEK BİLANÇO RAKAMLARI VE METİNLERİ:\n{context}\n\n"
                       f"SORU: {question}\n\n"
                       f"Yukarıdaki GERÇEK RAKAMLARI kullanarak soruları yanıtla, tablodaki puanları doldur ve Bilanço Karnesi oluştur:",
        },
    ]

    chat_res = client.chat.completions.create(
        model=chat_model_name,
        messages=messages,
        max_tokens=600,
        temperature=0.1,
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
    parser = argparse.ArgumentParser(description="KAP RAG Sorgu Motoru (Gerçek Veri Analizi)")
    parser.add_argument("question", nargs="?", help="Sorulacak soru")
    parser.add_argument("--company", "-c", help="Şirket kodu filtresi (THYAO, AKBNK...)")
    parser.add_argument("--type", "-t", help="Bildirim türü filtresi (ODA, FR, DG)")
    parser.add_argument("--top-k", "-k", type=int, default=4, help="Getirilecek chunk sayısı")
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
