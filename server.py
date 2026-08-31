"""
server.py — KAP RAG FastAPI Backend (Rakip Düzeyi Bilanço & Analiz)

REST API ile KAP RAG sistemini dışarıya açar.
Foundry Local (phi-4-mini & qwen3-embedding-0.6b) üzerinde çalışır.

Kullanım:
    python server.py
    python server.py --port 8000 --chat-model phi-4-mini
"""

from __future__ import annotations

import argparse
import json
import os
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

SYSTEM_PROMPT = """Sen BİST şirketlerinin KAP bildirimlerini ve finansal raporlarını analiz eden kıdemli bir Finansal Analist yapay zekasısın.

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

- Sadece sağlanan KAP kaynaklarındaki somut rakam ve bilgilere dayan. Türkçe dilini profesyonel kullan."""


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


# ──────────────────────────── Global State ────────────────────────────

class AppState:
    db: sqlite3.Connection = None
    client: OpenAI = None
    chat_model_name: str = DEFAULT_CHAT_MODEL

state = AppState()


# ──────────────────────────── Helpers ────────────────────────────

def serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


# ──────────────────────────── Lifespan ────────────────────────────

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


# ──────────────────────────── FastAPI ────────────────────────────

app = FastAPI(
    title="KAP RAG API",
    description="KAP bildirimleri ve finansal raporlar üzerinde RAG soru-cevap sistemi",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────── Models ────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., description="Sorulacak soru")
    company: Optional[str] = Field(None, description="Şirket kodu filtresi (THYAO, AKBNK...)")
    type: Optional[str] = Field(None, description="Bildirim türü filtresi (ODA, FR, DG)")
    top_k: int = Field(5, ge=1, le=30, description="Getirilecek chunk sayısı")

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


# ──────────────────────────── Endpoints ────────────────────────────

@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    start = time.time()

    if not req.question.strip():
        raise HTTPException(400, "Soru boş olamaz")

    # 0. Finansal Terim Niyet Algılama
    fin_keywords = [
        "finansal", "rapor", "bilanço", "bilanco", "gelir", "kar", "kâr", 
        "zarar", "hasılat", "ciro", "özkaynak", "ozkaynak", "varlık", "borç", "borc", "marj", "durum"
    ]
    is_financial_query = any(w in req.question.lower() for w in fin_keywords)

    matched_chunks = []
    seen_ids = set()

    # Doğrudan FR (Finansal Rapor) bildirimlerini önceliklendir
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

    # Vektör Araması ile Tamamla
    if len(matched_chunks) < req.top_k:
        subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL], capture_output=True)
        q_res = state.client.embeddings.create(model=EMBEDDING_MODEL, input=req.question)
        subprocess.run(["foundry", "model", "unload", EMBEDDING_MODEL], capture_output=True)

        q_embedding = q_res.data[0].embedding
        q_blob = serialize_f32(q_embedding)

        fetch_count = req.top_k * 20 if (req.company or req.type) else req.top_k * 5
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

    # Context
    context_parts = []
    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - Tür: {chunk['type']} | Tarih: {chunk['date']}] Şirket: {chunk['company']} | Başlık: {chunk['title'] or ''}"
        snippet = chunk['text'][:1200]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    # LLM (phi-4-mini)
    subprocess.run(["foundry", "model", "load", state.chat_model_name], capture_output=True)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"KAP FİNANSAL RAPOR VE BİLDİRİM KAYNAKLARI:\n{context}\n\n"
                       f"SORU: {req.question}\n\n"
                       f"Yukarıdaki KAP verilerindeki rakamları kullanarak soruları Markdown Tablosu (📊) ve analiz başlıkları (🔑, 💰, ⚠️) halinde yanıtla:",
        },
    ]

    chat_res = state.client.chat.completions.create(
        model=state.chat_model_name,
        messages=messages,
        max_tokens=700,
        temperature=0.2,
    )
    answer = chat_res.choices[0].message.content
    if "<think>" in answer and "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

    # Sources
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
