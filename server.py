"""
server.py — KAP RAG FastAPI Backend (Gerçek Veri Bilanço & Analiz Engine)

REST API ile KAP RAG sistemini dışarıya açar.
Foundry Local (phi-4-mini & qwen3-embedding-0.6b) üzerinde çalışır.
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
from contextlib import asynccontextmanager
from typing import Optional

import sqlite3
import sqlite_vec
from openai import OpenAI

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn


# ──────────────────────────── Config ────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__) or ".", "kap_vectors.db")
EMBEDDING_MODEL = "qwen3-embedding-0.6b"
DEFAULT_CHAT_MODEL = "phi-4-mini"

SYSTEM_PROMPT = """Sen BİST şirketlerinin KAP verilerini derinlemesine inceleyen bağımsız ve kıdemli bir Finansal Analist yapay zekasısın.

Sana verilen GERÇEK BİLANÇO RAKAMLARINI (Hasılat, Dönen Varlıklar, Borçlar, Özkaynaklar) ve KAP bildirim metinlerini kullanarak kullanıcıya 100% gerçek verili ve profesyonel bir Bilanço Karnesi üret.

KURALLAR:
1. **Gerçek Rakamları Kullan**: Metinde sağlanan somut finansal verileri (TL / Bin TL) birebir tabloya ve analize yansıt. Tablodaki puan sütununa somut puanları yaz!
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


class AppState:
    db: sqlite3.Connection = None
    client: OpenAI = None
    chat_model_name: str = DEFAULT_CHAT_MODEL

state = AppState()


def serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def extract_real_financial_facts(db: sqlite3.Connection, company: str) -> dict:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[+] DB ve OpenAI Client baslatiliyor...")

    if not os.path.exists(DB_PATH):
        print(f"[-] Veritabani bulunamadi: {DB_PATH}")
        sys.exit(1)

    state.db = sqlite3.connect(DB_PATH, check_same_thread=False)
    state.db.enable_load_extension(True)
    sqlite_vec.load(state.db)
    state.db.enable_load_extension(False)
    state.db.row_factory = sqlite3.Row
    print(f"[+] DB acildi: {DB_PATH}")

    base_url = get_foundry_base_url()
    state.client = OpenAI(base_url=base_url, api_key="none")

    try:
        res = state.client.embeddings.create(model=EMBEDDING_MODEL, input="health")
        print(f"[+] Foundry Local Server baglantisi basarili ({base_url})")
    except Exception as e:
        print(f"[-] Foundry Server uyarisi: {e}")

    print("\n[+] KAP RAG Sunucu hazir!\n")

    yield

    print("\n[-] Kapatiliyor...")
    if state.db:
        state.db.close()


app = FastAPI(
    title="KAP RAG API",
    description="KAP bildirimleri ve Gerçek Bilanço Karnesi soru-cevap sistemi",
    version="1.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., description="Sorulacak soru")
    company: Optional[str] = Field(None, description="Şirket kodu filtresi (THYAO, AKBNK...)")
    type: Optional[str] = Field(None, description="Bildirim türü filtresi (ODA, FR, DG)")
    top_k: int = Field(4, ge=1, le=30, description="Getirilecek chunk sayısı")

class Source(BaseModel):
    company: str
    company_name: Optional[str]
    title: Optional[str]
    date: Optional[str]
    type: Optional[str]
    url: Optional[str]
    source_type: str
    attachment_filename: Optional[str]
    relevance_rank: int

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    chunks_used: int
    query_time_ms: float


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    start = time.time()

    if not req.question.strip():
        raise HTTPException(400, "Soru boş olamaz")

    q_lower = req.question.lower()
    karne_keywords = ["karne", "skor", "not", "derece", "karne nasıl", "performans", "trend", "net kar"]
    fin_keywords = ["finansal", "rapor", "bilanço", "bilanco", "gelir", "kar", "kâr", "zarar", "hasılat", "ciro", "özkaynak", "borç", "marj"]

    is_karne_query = any(w in q_lower for w in karne_keywords)
    is_financial_query = is_karne_query or any(w in q_lower for w in fin_keywords)

    real_facts_summary = ""
    matched_chunks = []
    seen_ids = set()

    if req.company:
        facts = extract_real_financial_facts(state.db, req.company)
        if facts:
            fact_lines = [f"• {k.upper()}: {v}" for k, v in facts.items() if k != "date"]
            real_facts_summary = f"BİLANÇO TARİHİ: {facts.get('date')}\nAYIKLANAN DOĞRUDAN VERİLER:\n" + "\n".join(fact_lines)

    if is_financial_query and req.company and not req.type:
        comp_str = req.company.upper()
        fr_rows = state.db.execute(
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

    if len(matched_chunks) < req.top_k:
        subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL], capture_output=True)
        q_res = state.client.embeddings.create(model=EMBEDDING_MODEL, input=req.question)
        subprocess.run(["foundry", "model", "unload", EMBEDDING_MODEL], capture_output=True)

        q_embedding = q_res.data[0].embedding
        q_blob = serialize_f32(q_embedding)

        fetch_count = req.top_k * 15 if (req.company or req.type) else req.top_k * 5
        vec_rows = state.db.execute(
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

                if req.company:
                    sql += " AND (company = ? OR company LIKE ?)"
                    params.extend([req.company.upper(), f"%{req.company.upper()}%"])
                if req.type:
                    sql += " AND type = ?"
                    params.append(req.type.upper())

                sql += " ORDER BY date DESC"
                vec_matched = state.db.execute(sql, params).fetchall()
                for r in vec_matched:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        matched_chunks.append(r)
                        if len(matched_chunks) >= req.top_k:
                            break

    matched_chunks = matched_chunks[:req.top_k]

    if not matched_chunks:
        return AskResponse(
            answer="Bu filtrelerle KAP verilerinde bilgi bulunamadı.",
            sources=[],
            chunks_used=0,
            query_time_ms=round((time.time() - start) * 1000, 1),
        )

    context_parts = []
    if real_facts_summary:
        context_parts.append(f"[DOĞRUDAN GERÇEK BİLANÇO KALEMLERİ]\n{real_facts_summary}")

    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - {chunk['type']} | Tarih: {chunk['date']}] {chunk['company']} — {chunk['title'] or ''}"
        snippet = chunk['text'][:700]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    subprocess.run(["foundry", "model", "load", state.chat_model_name], capture_output=True)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"KAP GERÇEK BİLANÇO RAKAMLARI VE METİNLERİ:\n{context}\n\n"
                       f"SORU: {req.question}\n\n"
                       f"Yukarıdaki GERÇEK RAKAMLARI kullanarak soruları yanıtla, tablodaki puanları doldur ve Bilanço Karnesi oluştur:",
        },
    ]

    chat_res = state.client.chat.completions.create(
        model=state.chat_model_name,
        messages=messages,
        max_tokens=600,
        temperature=0.1,
    )
    answer = chat_res.choices[0].message.content
    if "<think>" in answer and "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

    seen = set()
    sources = []
    for i, chunk in enumerate(matched_chunks):
        key = (chunk["source_index"], chunk["source_type"], chunk["attachment_filename"])
        if key not in seen:
            seen.add(key)
            sources.append(Source(
                company=chunk["company"],
                company_name=chunk["company_name"],
                title=chunk["title"],
                date=chunk["date"],
                type=chunk["type"],
                url=chunk["source_url"],
                source_type=chunk["source_type"],
                attachment_filename=chunk["attachment_filename"],
                relevance_rank=i + 1,
            ))

    return AskResponse(
        answer=answer,
        sources=sources,
        chunks_used=len(matched_chunks),
        query_time_ms=round((time.time() - start) * 1000, 1),
    )


@app.get("/api/companies")
async def list_companies():
    rows = state.db.execute(
        "SELECT DISTINCT company, company_name FROM chunks ORDER BY company"
    ).fetchall()
    return [{"code": r["company"], "name": r["company_name"]} for r in rows]


@app.get("/api/stats")
async def get_stats():
    total = state.db.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
    companies = state.db.execute("SELECT COUNT(DISTINCT company) as c FROM chunks").fetchone()["c"]

    content = state.db.execute(
        "SELECT COUNT(*) as c FROM chunks WHERE source_type = 'content'"
    ).fetchone()["c"]
    pdf = state.db.execute(
        "SELECT COUNT(*) as c FROM chunks WHERE source_type = 'pdf_attachment'"
    ).fetchone()["c"]

    types = state.db.execute(
        "SELECT type, COUNT(*) as c FROM chunks GROUP BY type ORDER BY c DESC"
    ).fetchall()

    return {
        "total_chunks": total,
        "total_companies": companies,
        "content_chunks": content,
        "pdf_chunks": pdf,
        "type_distribution": {r["type"]: r["c"] for r in types},
        "models": {
            "embedding": EMBEDDING_MODEL,
            "chat": state.chat_model_name,
        },
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "db_connected": state.db is not None,
        "client_ready": state.client is not None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KAP RAG API Sunucusu")
    parser.add_argument("--host", default="0.0.0.0", help="Sunucu adresi")
    parser.add_argument("--port", type=int, default=8000, help="Port numarası")
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL, help="Chat LLM modeli")
    args = parser.parse_args()

    state.chat_model_name = args.chat_model

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
