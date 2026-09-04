"""
ask_foundry.py — KAP RAG Sorgu Motoru (Niyet Tabanlı 5 Analiz Modu & Gerçek Bilanço Motoru)

SQLite veritabanından doğrudan GERÇEK bilanço kalemlerini ve KAP bildirimlerini çekip,
kullanıcının sorusuna uygun 5 spesifik analiz modundan (Bilanço, Gelir Tablosu, Temettü/Sermaye, 
Yeni İş/Yatırım, Genel KAP) birini otomatik seçerek %100 gerçek verilerle rapor üretir.
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

# Ensure UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ──────────────────────────── Config ────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__) or ".", "kap_vectors.db")
EMBEDDING_MODEL = "qwen3-embedding-0.6b"
CHAT_MODEL = "phi-4-mini"

# ──────────────────────────── System Prompts ────────────────────────────

PROMPT_BILANCO = """Sen BİST şirketlerinin bilanço ve likidite durumunu inceleyen kıdemli bir Finansal Analistsin.
Sana verilen GERÇEK BİLANÇO RAKAMLARINI (Dönen/Duran Varlıklar, Borçlar, Özkaynaklar) ve hesaplanan Cari Oran değerlerini kullanarak 100% gerçek verili bir Bilanço Karnesi üret.

KURALLAR:
1. Metinde sağlanan somut finansal verileri (TL / Milyon TL) birebir tabloya yansıt. Tablodaki puan sütununa somut puanları yaz!
2. Cari Oran (Dönen Varlıklar / Kısa Borçlar) ve Borç/Özkaynak dengesine dayanarak 5 üzerinden puanla.

CEVAP YAPISI:
📋 **[ŞİRKET_KODU] Bilanço & Likidite Karnesi · [DÖNEM]**
⭐ **Genel Finansal Skor:** [SKOR]/5 — [Zayıf / Orta / İyi / Çok İyi]

| Finansal Kalem / Kategori | Gerçek Değer | Puan (5 Üzerinden) | Analiz Özeti |
| :--- | :--- | :---: | :--- |
| 📈 **Hasılat / Ciro** | [Rakam] | [Puan]/5 | [Ciro seviyesi] |
| 💧 **Dönen Varlıklar / Likidite** | [Rakam] | [Puan]/5 | [Nakit ve likidite gücü] |
| 🛡️ **Kısa & Uzun Vadeli Borçlar** | [Rakam] | [Puan]/5 | [Borç yükü ve kaldıraç] |
| ⚙️ **Toplam Özkaynaklar** | [Rakam] | [Puan]/5 | [Özkaynak gücü ve bilanço dengesi] |

📊 **Kritik Finansal Rasyolar:**
- **Cari Oran:** [Oran] (Referans: > 1.5 Güçlü)
- **Borç / Özkaynak Oranı:** [Oran] (Referans: < 1.0 Makul)

📝 **Analist Değerlendirmesi:**
[3-4 cümlelik somut analist yorumu]"""

PROMPT_GELIR = """Sen BİST şirketlerinin gelir tablosu, ciro ve karlılık performansını inceleyen kıdemli bir Finansal Analistsin.
Sana verilen GERÇEK GELİR TABLOSU RAKAMLARINI (Hasılat, Esas Faaliyet Karı, Net Dönem Karı) kullanarak 100% gerçek verili Gelir Tablosu & Karlılık Raporu üret.

CEVAP YAPISI:
📈 **[ŞİRKET_KODU] Gelir Tablosu & Karlılık Raporu · [DÖNEM]**
⭐ **Karlılık Skoru:** [SKOR]/5 — [Değerlendirme]

| Gelir Kalemi | Gerçek Değer | Değişim / Marj | Analitik Yorum |
| :--- | :--- | :---: | :--- |
| 💰 **Hasılat (Ciro)** | [Rakam] | [Oran/Değişim] | [Satış hacmi performansı] |
| ⚙️ **Esas Faaliyet Karı** | [Rakam] | [Faaliyet Marjı] | [Ana faaliyet karlılığı] |
| 🏆 **Net Dönem Karı** | [Rakam] | [Net Kar Marjı] | [Dönem net sonucu] |

📝 **Karlılık ve Operasyonel Performans Analizi:**
[3-4 cümlelik detaylı analist değerlendirmesi]"""

PROMPT_TEMETTU = """Sen BİST şirketlerinin temettü (kar payı) ve sermaye artırımı (bedelsiz/bedelli) kararlarını inceleyen kıdemli bir Finansal Analistsin.
Sana verilen KAP Kar Payı Dağıtım Bildirimi metinlerini kullanarak GERÇEK RAKAMLARLA Kar Payı & Sermaye Raporu üret.

KURALLAR:
1. Tahvil, Bono, Kupon İtfası, Borçlanma Aracı ("Pay Dışında Sermaye Piyasası Aracı") bildirimlerini KESİNLİKLE Temettü / Kar Payı ile karıştırma!
2. Eğer 1. Taksit, 2. Taksit gibi taksitli temettü ödemesi varsa, her taksidi ve tarihlerini ayrı satırlar halinde tabloda göster.
3. Eğer sunulan metinlerde temettü kararı yoksa "Temettü kararı bulunmamaktadır" yaz, kesinlikle borçlanma aracı ödemelerini temettü gibi gösterme.

CEVAP YAPISI:
💰 **[ŞİRKET_KODU] Temettü & Sermaye Artırımı Karar Karnesi**

| Karar / Taksit Türü | Hisse Başı Brüt TL | Hisse Başı Net TL | Ödeme / Hak Kullanım Tarihi | Toplam Tutar / Oran | Durum |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 💵 **1. Taksit Temettü** | [Tutar] | [Tutar] | [Tarih] | [Toplam TL] | [Genel Kurul Onaylandı / Ödendi] |
| 💵 **2. Taksit Temettü** | [Tutar] | [Tutar] | [Tarih] | [Toplam TL] | [Genel Kurul Onaylandı] |
| 📈 **Bedelsiz Sermaye Artırımı** | - | - | [Tarih/Yok] | [% Oran/Yok] | [Varsa Detay] |

📝 **Yatırımcı Notu & Analist Değerlendirmesi:**
[2-3 cümlelik net açıklama, toplam temettü tutarı, ödeme tarihleri ve kar dağıtım oranı özeti]"""

PROMPT_YATIRIM = """Sen BİST şirketlerinin yeni iş ilişkilerini, ihale sonuçlarını ve yatırım kararlarını inceleyen bir Finansal Analistsin.
Sana verilen KAP Özel Durum Açıklamalarını (ÖDA) inceleyerek Yeni İş İlişkisi & Yatırım Raporu üret.

CEVAP YAPISI:
🤝 **[ŞİRKET_KODU] Yeni İş İlişkileri & Yatırım Raporu**

| Sözleşme / Yatırım Konusu | Müşteri / Taraf | Sözleşme / Yatırım Bedeli | Ciroya Etkisi (%) |
| :--- | :--- | :--- | :---: |
| 🎯 **Yeni İş / Anlaşma** | [Müşteri/Taraf] | [Tutar TL/USD] | [% Etki veya Belirtilmedi] |
| 🏭 **Yatırım / Kapasite** | [Detay] | [Yatırım Tutarı] | [Kapasite Etkisi] |

📝 **Şirket Büyümesine ve Geleceğe Etkisi:**
[2-3 cümlelik somut analist değerlendirmesi]"""

PROMPT_GENEL = """Sen BİST şirketlerinin KAP bildirimlerini ve kamuoyu açıklamalarını inceleyen kıdemli bir Finansal Analistsin.
Sana verilen KAP metinlerini ve kaynakları kullanarak sorulan soruya doğrudan, net, maddeli ve profesyonel bir yanıt ver.

CEVAP YAPISI:
📋 **[ŞİRKET_KODU] KAP Bildirim Analizi & Yanıt**

[Soruya verilen net ve detaylı yanıt.]

📌 **Öne Çıkan Gelişmeler & Yönetim Kararları:**
- [Gelişme 1]
- [Gelişme 2]"""


def get_foundry_base_url() -> str:
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


def clean_str(s: str) -> str:
    s = s.upper()
    replacements = {
        'İ': 'I', 'I': 'I', 'ı': 'I', 'Ğ': 'G', 'ğ': 'G',
        'Ü': 'U', 'ü': 'U', 'Ş': 'S', 'ş': 'S', 'Ö': 'O', 'ö': 'O',
        'Ç': 'C', 'ç': 'C'
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s


def extract_real_financial_facts(db: sqlite3.Connection, company: str) -> dict:
    comp_str = company.upper()
    
    rows = db.execute(
        """
        SELECT date, title, text, source_type, attachment_filename 
        FROM chunks 
        WHERE (company = ? OR company LIKE ?) AND type = 'FR'
        ORDER BY date DESC
        LIMIT 200
        """,
        (comp_str, f"%{comp_str}%"),
    ).fetchall()

    if not rows:
        return {}

    fin_rows = [r for r in rows if r["title"] and ("Finansal Rapor" in r["title"] or "Bilanço" in r["title"])]
    target_pool = fin_rows if fin_rows else rows

    latest_date_prefix = target_pool[0]["date"][:10]
    period_rows = [r for r in target_pool if r["date"].startswith(latest_date_prefix)]

    facts = {}
    
    patterns = {
        "donen_varliklar": [r"TOPLAM\s+DONEN\s+VARLIKLAR", r"DONEN\s+VARLIKLAR\s+TOPLAMI", r"DONEN\s+VARLIKLAR", r"TOTAL\s+CURRENT\s+ASSETS"],
        "duran_varliklar": [r"TOPLAM\s+DURAN\s+VARLIKLAR", r"DURAN\s+VARLIKLAR\s+TOPLAMI", r"DURAN\s+VARLIKLAR", r"TOTAL\s+NON.?CURRENT\s+ASSETS"],
        "toplam_varliklar": [r"TOPLAM\s+VARLIKLAR", r"VARLIKLAR\s+TOPLAMI", r"TOTAL\s+ASSETS"],
        "kisa_vadeli_borclar": [r"TOPLAM\s+KISA\s+VADELI\s+YUKUMLULUKLER", r"KISA\s+VADELI\s+YUKUMLULUKLER\s+TOPLAMI", r"TOTAL\s+CURRENT\s+LIABILITIES"],
        "uzun_vadeli_borclar": [r"TOPLAM\s+UZUN\s+VADELI\s+YUKUMLULUKLER", r"UZUN\s+VADELI\s+YUKUMLULUKLER\s+TOPLAMI", r"TOTAL\s+NON.?CURRENT\s+LIABILITIES"],
        "toplam_yukumlulukler": [r"TOPLAM\s+YUKUMLULUKLER", r"YUKUMLULUKLER\s+TOPLAMI", r"TOTAL\s+LIABILITIES"],
        "ozkaynaklar": [r"TOPLAM\s+OZKAYNAKLAR", r"OZKAYNAKLAR\s+TOPLAMI", r"TOTAL\s+EQUITY", r"TOPLAM\s+OZ\s+KAYNAKLAR"],
        "hasilat": [r"HASILAT", r"SATIS\s+GELIRLERI", r"REVENUE", r"TOTAL\s+REVENUE"],
        "net_kar": [r"DONEM\s+KARI?\s*\(?ZARARI\)?", r"DONEM\s+NET\s+KARI?", r"NET\ PROFIT", r"PROFIT\s+FOR\s+THE\s+PERIOD"]
    }

    unit = "Bin TL"

    for r in period_rows:
        raw_text = r["text"]
        if "1.000.000 TL" in raw_text or "1.000.000 USD" in raw_text:
            unit = "Milyon TL/USD"
        lines = raw_text.splitlines()
        
        for j, line in enumerate(lines):
            c_line = clean_str(line.strip())
            if not c_line:
                continue

            for key, pat_list in patterns.items():
                if key in facts:
                    continue
                for pat in pat_list:
                    if re.search(pat, c_line):
                        for offset in range(0, 5):
                            if j + offset < len(lines):
                                check_line = lines[j + offset].strip()
                                found_nums = re.findall(r"\(?-?\d{1,3}(?:\.\d{3})+(?:,\d+)?\)?", check_line)
                                if found_nums:
                                    facts[key] = found_nums[0]
                                    break
                        if key in facts:
                            break

    facts["date"] = period_rows[0]["date"] if period_rows else latest_date_prefix
    facts["para_birimi"] = unit

    def parse_val(v_str):
        if not v_str:
            return None
        cleaned = v_str.replace("(", "-").replace(")", "").replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    donen = parse_val(facts.get("donen_varliklar"))
    kisa_borc = parse_val(facts.get("kisa_vadeli_borclar"))
    ozk = parse_val(facts.get("ozkaynaklar"))
    toplam_borc = parse_val(facts.get("toplam_yukumlulukler")) or ((parse_val(facts.get("kisa_vadeli_borclar")) or 0) + (parse_val(facts.get("uzun_vadeli_borclar")) or 0))

    if donen and kisa_borc and kisa_borc > 0:
        facts["cari_oran"] = round(donen / kisa_borc, 2)
    if toplam_borc and ozk and ozk > 0:
        facts["borc_ozkaynak_orani"] = round(toplam_borc / ozk, 2)

    return facts


def detect_intent(question: str) -> tuple[str, str]:
    q = question.lower()

    temettu_kw = ["temettü", "temettu", "kar payı", "kâr payı", "bedelsiz", "bedelli", "sermaye artırımı", "sermaye artirimi", "hak kullanım", "temettü ödemesi"]
    if any(k in q for k in temettu_kw):
        return "TEMETTU", PROMPT_TEMETTU

    yatirim_kw = ["yeni iş", "yeni is", "sözleşme", "sozlesme", "ihale", "yatırım", "yatirim", "fabrika", "kapasite", "anlaşma", "anlasma", "sipariş", "siparis"]
    if any(k in q for k in yatirim_kw):
        return "YATIRIM", PROMPT_YATIRIM

    gelir_kw = ["ciro", "hasılat", "hasilat", "net kar", "net kâr", "satışlar", "satislar", "karlılık", "karlilik", "kar marjı", "faaliyet karı", "gelir tablosu"]
    if any(k in q for k in gelir_kw):
        return "GELIR", PROMPT_GELIR

    bilanco_kw = ["bilanço", "bilanco", "karne", "likidite", "borç", "borc", "varlık", "varlik", "özkaynak", "ozkaynak", "cari oran", "rasyo", "skor", "not"]
    if any(k in q for k in bilanco_kw):
        return "BILANCO", PROMPT_BILANCO

    return "GENEL", PROMPT_GENEL


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

    intent_code, selected_prompt = detect_intent(question)

    real_facts_summary = ""
    matched_chunks = []
    seen_ids = set()

    # Gerçek bilanço verisi ayıklama (Bilanço ve Gelir modlarında)
    if company_filter and intent_code in ("BILANCO", "GELIR"):
        facts = extract_real_financial_facts(db, company_filter)
        if facts:
            fact_lines = [f"• {k.upper()}: {v}" for k, v in facts.items() if k != "date"]
            real_facts_summary = f"BİLANÇO DÖNEMİ: {facts.get('date')} (Birim: {facts.get('para_birimi')})\nAYIKLANAN GERÇEK VERİLER VE RASYOLAR:\n" + "\n".join(fact_lines)

    # Niyete özel hassas başlık filtresi
    if company_filter:
        comp_str = company_filter.upper()

        if intent_code in ("BILANCO", "GELIR"):
            rows = db.execute(
                """
                SELECT * FROM chunks 
                WHERE (company = ? OR company LIKE ?) AND type = 'FR'
                ORDER BY date DESC
                LIMIT 6
                """,
                (comp_str, f"%{comp_str}%"),
            ).fetchall()
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    matched_chunks.append(r)

        elif intent_code == "TEMETTU":
            # Kar Payı ve Temettü bildirimlerini doğrudan başlığa göre filtrele!
            rows = db.execute(
                """
                SELECT * FROM chunks 
                WHERE (company = ? OR company LIKE ?) 
                  AND (title LIKE '%Kar Payı%' OR title LIKE '%Temettü%' OR title LIKE '%Sermaye Artırımı%' OR text LIKE '%Kar Payı Dağıtım%')
                ORDER BY date DESC
                LIMIT 6
                """,
                (comp_str, f"%{comp_str}%"),
            ).fetchall()
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    matched_chunks.append(r)

        elif intent_code == "YATIRIM":
            # Yeni iş ve Yatırım bildirimlerini doğrudan başlığa göre filtrele!
            rows = db.execute(
                """
                SELECT * FROM chunks 
                WHERE (company = ? OR company LIKE ?) 
                  AND (title LIKE '%Yeni İş%' OR title LIKE '%Sözleşme%' OR title LIKE '%İhale%' OR title LIKE '%Yatırım%' OR title LIKE '%Kapasite%' OR text LIKE '%yeni iş ilişkisi%')
                ORDER BY date DESC
                LIMIT 6
                """,
                (comp_str, f"%{comp_str}%"),
            ).fetchall()
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    matched_chunks.append(r)

    # Vektör Araması ile Destekleme
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
            "query_time_ms": round((time.time() - start) * 1000, 1),
            "intent": intent_code,
        }

    context_parts = []
    if real_facts_summary:
        context_parts.append(f"[DOĞRUDAN GERÇEK BİLANÇO RAKAMLARI VE HESAPLANAN RASYOLAR]\n{real_facts_summary}")

    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - {chunk['type']} | Tarih: {chunk['date']}] {chunk['company']} — {chunk['title'] or ''}"
        snippet = chunk['text'][:850]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    subprocess.run(["foundry", "model", "load", CHAT_MODEL], capture_output=True)
    messages = [
        {"role": "system", "content": selected_prompt},
        {
            "role": "user",
            "content": f"KAP GERÇEK BİLDİRİM METİNLERİ VE VERİLER:\n{context}\n\n"
                       f"SORU: {question}\n\n"
                       f"Yukarıdaki metinlerde yer alan GERÇEK RAKAMLARI ve TARİHLERİ kullanarak soruyu yanıtla:",
        },
    ]

    chat_res = client.chat.completions.create(
        model=chat_model_name,
        messages=messages,
        max_tokens=650,
        temperature=0.1,
    )
    answer = chat_res.choices[0].message.content
    if "<think>" in answer and "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

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
        "intent": intent_code,
    }


def print_result(result: dict):
    print(f"\n{'='*60}")
    print(f"🎯 Mod (Intent): {result.get('intent', 'GENEL')}")
    print(f"📝 Cevap:\n")
    print(result["answer"])

    print(f"\n{'─'*60}")
    print(f"📎 Kaynaklar ({len(result['sources'])} bildirim):\n")

    for i, src in enumerate(result["sources"]):
        icon = "📊" if src["type"] == "FR" else ("📄" if src["type"] == "ODA" else "📜")
        line = f"  {i+1}. {icon} [{src['date']}] {src['company']} ({src['type']}) — {src['title']}"
        if src["source_type"] == "pdf_attachment" and src["attachment_filename"]:
            line += f"\n     📁 PDF: {src['attachment_filename']}"
        line += f"\n     🔗 {src['url']}"
        print(line)

    print(f"\n{'─'*60}")
    print(f"⚡ {result['chunks_used']} chunk kullanıldı, {result['query_time_ms']:.0f}ms")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="KAP RAG Sorgu Motoru (5 Analiz Modu)")
    parser.add_argument("question", nargs="?", help="Sorulacak soru")
    parser.add_argument("--company", "-c", help="Şirket kodu filtresi (THYAO, AKBNK...)")
    parser.add_argument("--type", "-t", help="Bildirim türü filtresi (ODA, FR, DUY)")
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
