"""
server.py — KAP RAG FastAPI Backend (Groq API / Local Foundry + 5 Analiz Modu + Web UI)

Groq API (qwen/qwen3.6-27b) veya yerel Foundry (phi-4-mini)
üzerinde çalışarak KAP bildirimlerinden %100 gerçek verilerle finansal raporlar üretir.
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
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn


# ──────────────────────────── Config ────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__) or ".", "kap_vectors.db")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__) or ".", "public")
EMBEDDING_MODEL = "qwen3-embedding-0.6b"
LOCAL_CHAT_MODEL = "phi-4-mini"
GROQ_CHAT_MODEL = "qwen/qwen3.6-27b"
DEFAULT_GROQ_KEY = "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"

# ──────────────────────────── System Prompts ────────────────────────────

PROMPT_BILANCO = """Sen BİST şirketlerinin bilanço ve likidite durumunu inceleyen kıdemli bir Finansal Analistsin.
Sana verilen GERÇEK BİLANÇO RAKAMLARINI (Dönen/Duran Varlıklar, Borçlar, Özkaynaklar) ve hesaplanan Cari Oran değerlerini kullanarak 100% gerçek verili bir Bilanço Karnesi üret.

KURALLAR:
1. Metinde sağlanan somut finansal verileri (TL / Milyon TL) birebir tabloya yansıt. Tablodaki puan sütununa somut puanları yaz!
2. Cari Oran (Dönen Varlıklar / Kısa Borçlar) ve Borç/Özkaynak dengesine dayanarak 5 üzerinden puanla.
3. SADECE AŞAĞIDAKİ CEVAP YAPISINI KULLANARAK YANIT VER.

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
Sana verilen GERÇEK KAP Kar Payı Dağıtım Bildirimi metinlerini ve kesin rakamları kullanarak Kar Payı Karnesi üret.

ÖNEMLİ KURALLAR:
1. TABLODAKİ SÜTUNLARA SADECE DOĞRU BİLGİLERİ YAZ:
   - "Hisse Başı Brüt (TL)": Sadece 10,38 TL, 6,75 TL gibi hisse başına düşen küçük TL tutarlarını yaz. Toplam milyarlık tutarları sakın buraya yazma!
   - "Toplam Nakit Kar Payı": 20 Milyar TL, 13 Milyar TL veya 33 Milyar TL gibi toplam dağıtılan tutarları yaz.
2. Tahvil, Bono, Kupon İtfası, Borçlanma Aracı bildirimlerini KESİNLİKLE Temettü / Kar Payı ile karıştırma!
3. Metinde açıkça yazmayan veriler için "- (Belirtilmedi)" yaz.
4. SADECE AŞAĞIDAKİ CEVAP YAPISINI KULLANARAK YANIT VER.

CEVAP YAPISI:
💰 **[ŞİRKET_KODU] Temettü & Sermaye Artırımı Karar Karnesi**

| Karar / Taksit Türü | Hisse Başı Brüt (TL) | Hisse Başı Net (TL) | Ödeme / Hak Kullanım Tarihi | Toplam Nakit Kar Payı | Durum |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 💵 **1. Taksit Temettü** | [Küçük TL Tutarı] | [Küçük TL Tutarı] | [Tarih] | [Toplam TL] | Genel Kurul Onaylandı |
| 💵 **2. Taksit Temettü** | [Küçük TL Tutarı] | [Küçük TL Tutarı] | [Tarih] | [Toplam TL] | Genel Kurul Onaylandı |
| 📈 **Bedelsiz Sermaye Artırımı** | - | - | - | % Oran Yok | Varsa Belirtilmedi |

📝 **Yatırımcı Notu & Analist Değerlendirmesi:**
[2-3 cümlelik net açıklama, toplam temettü tutarı, taksit ödeme tarihleri ve karar özeti]"""

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


def get_chat_client(groq_key: str = None) -> tuple[OpenAI, str, str]:
    key = groq_key or os.environ.get("GROQ_API_KEY") or DEFAULT_GROQ_KEY
    if key and key.strip():
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key.strip())
        model_name = os.environ.get("GROQ_MODEL", GROQ_CHAT_MODEL)
        return client, model_name, f"Groq Cloud ({model_name})"

    base_url = get_foundry_base_url()
    client = OpenAI(base_url=base_url, api_key="none")
    return client, LOCAL_CHAT_MODEL, "Local Foundry (phi-4-mini)"


class AppState:
    db: sqlite3.Connection = None
    client: OpenAI = None
    chat_model_name: str = LOCAL_CHAT_MODEL
    provider_name: str = "Local Foundry"
    groq_key: Optional[str] = DEFAULT_GROQ_KEY

state = AppState()


def serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


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


# ──────────────────────────── Önbellek Fonksiyonları ────────────────────────────

def init_cache_table(db: sqlite3.Connection):
    db.execute("""
        CREATE TABLE IF NOT EXISTS qa_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_normalized TEXT UNIQUE,
            question_raw TEXT,
            company TEXT,
            answer TEXT,
            sources_json TEXT,
            chunks_used INTEGER,
            query_time_ms REAL,
            intent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()


def normalize_q(q: str, company: str = None) -> str:
    q_clean = re.sub(r"\s+", " ", q.strip().lower())
    if company:
        comp = company.strip().lower()
        if comp not in q_clean:
            q_clean = f"{comp} {q_clean}"
    return q_clean


def get_cached_answer(db: sqlite3.Connection, question: str, company: str = None) -> dict | None:
    norm_q = normalize_q(question, company)
    row = db.execute("""
        SELECT * FROM qa_cache 
        WHERE question_normalized = ? 
          AND created_at >= datetime('now', '-7 days')
        ORDER BY created_at DESC
        LIMIT 1
    """, (norm_q,)).fetchone()

    if row:
        sources = json.loads(row["sources_json"]) if row["sources_json"] else []
        return {
            "answer": row["answer"],
            "sources": sources,
            "chunks_used": row["chunks_used"],
            "query_time_ms": 25.0,
            "intent": row["intent"],
            "cached": True,
            "created_at": row["created_at"]
        }
    return None


def set_cached_answer(db: sqlite3.Connection, question: str, company: str, result: dict):
    norm_q = normalize_q(question, company)
    sources_json = json.dumps(result.get("sources", []), ensure_ascii=False)
    db.execute("""
        INSERT INTO qa_cache (question_normalized, question_raw, company, answer, sources_json, chunks_used, query_time_ms, intent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(question_normalized) DO UPDATE SET
            answer=excluded.answer,
            sources_json=excluded.sources_json,
            chunks_used=excluded.chunks_used,
            query_time_ms=excluded.query_time_ms,
            intent=excluded.intent,
            created_at=datetime('now')
    """, (
        norm_q,
        question,
        company or "",
        result.get("answer", ""),
        sources_json,
        result.get("chunks_used", 0),
        result.get("query_time_ms", 0),
        result.get("intent", "GENEL"),
    ))
    db.commit()


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


def extract_dividend_facts(db: sqlite3.Connection, company: str) -> str:
    comp_str = company.upper()
    rows = db.execute("""
        SELECT date, title, text 
        FROM chunks 
        WHERE (company = ? OR company LIKE ?)
          AND (title LIKE '%Kar Payı%' OR text LIKE '%Kar Payı Dağıtım%')
        ORDER BY date DESC
        LIMIT 10
    """, (comp_str, f"%{comp_str}%")).fetchall()

    if not rows:
        return ""

    taksit_info = []

    for r in rows:
        text = r["text"]

        tot_match = re.search(r"dağıtılması önerilen toplam ([0-9\.,]+)\s*TL", text, re.IGNORECASE)
        taksit1_tot = re.search(r"([0-9\.,]+)\s*TL tutarındaki ilk taksit", text, re.IGNORECASE)
        taksit2_tot = re.search(r"([0-9\.,]+)\s*TL tutarındaki ikinci taksit", text, re.IGNORECASE)
        taksit1_date = re.search(r"ilk taksit için ödeme tarihinin\s*([0-9A-Za-z\s]+)", text, re.IGNORECASE)
        taksit2_date = re.search(r"ikinci taksit için ise\s*([0-9A-Za-z\s]+)", text, re.IGNORECASE)

        if tot_match:
            taksit_info.append(f"• TOPLAM DAĞITILAN NAKİT KAR PAYI: {tot_match.group(1)} TL")
        if taksit1_tot and taksit1_date:
            taksit_info.append(f"• 1. TAKSİT TEMETTÜ: {taksit1_tot.group(1)} TL | Ödeme Tarihi: {taksit1_date.group(1).strip()}")
        if taksit2_tot and taksit2_date:
            taksit_info.append(f"• 2. TAKSİT TEMETTÜ: {taksit2_tot.group(1)} TL | Ödeme Tarihi: {taksit2_date.group(1).strip()}")

        brut_1 = re.search(r"1\.\s*Taksit\s*\n\s*([0-9,]+)", text)
        brut_2 = re.search(r"2\.\s*Taksit\s*\n\s*([0-9,]+)", text)

        if brut_1:
            taksit_info.append(f"• 1. TAKSİT HİSSE BAŞI BRÜT: {brut_1.group(1)} TL")
        if brut_2:
            taksit_info.append(f"• 2. TAKSİT HİSSE BAŞI BRÜT: {brut_2.group(1)} TL")

    if taksit_info:
        unique_facts = list(dict.fromkeys(taksit_info))
        return "[DOĞRUDAN KAP BİLDİRİMİNDEN HESAPLANAN KESİN TEMETTÜ RAKAMLARI]\n" + "\n".join(unique_facts)
    return ""


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[+] DB ve LLM Client baslatiliyor...")

    if not os.path.exists(DB_PATH):
        print(f"[-] Veritabani bulunamadi: {DB_PATH}")
        sys.exit(1)

    state.db = sqlite3.connect(DB_PATH, check_same_thread=False)
    state.db.enable_load_extension(True)
    sqlite_vec.load(state.db)
    state.db.enable_load_extension(False)
    state.db.row_factory = sqlite3.Row
    init_cache_table(state.db)
    print(f"[+] DB & Önbellek tablosu acildi: {DB_PATH}")

    state.client, state.chat_model_name, state.provider_name = get_chat_client(state.groq_key)
    print(f"[+] LLM Sağlayıcısı: {state.provider_name} | Model: {state.chat_model_name}")

    print("\n[+] KAP RAG Sunucu hazir!\n")

    yield

    print("\n[-] Kapatiliyor...")
    if state.db:
        state.db.close()


app = FastAPI(
    title="KAP RAG API",
    description="Groq API (qwen/qwen3.6-27b) & Local Foundry Destekli BİST RAG Engine + Web UI",
    version="2.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Web UI Static Files
if os.path.exists(PUBLIC_DIR):
    app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


@app.get("/")
async def read_index():
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "KAP RAG API running"}


@app.get("/style.css")
async def read_css():
    css_path = os.path.join(PUBLIC_DIR, "style.css")
    if os.path.exists(css_path):
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(404, "style.css not found")


@app.get("/app.js")
async def read_js():
    js_path = os.path.join(PUBLIC_DIR, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(404, "app.js not found")


class AskRequest(BaseModel):
    question: str = Field(..., description="Sorulacak soru")
    company: Optional[str] = Field(None, description="Şirket kodu filtresi (THYAO, AKBNK...)")
    type: Optional[str] = Field(None, description="Bildirim türü filtresi (ODA, FR, DUY)")
    top_k: int = Field(5, ge=1, le=30, description="Getirilecek chunk sayısı")
    force_refresh: bool = Field(False, description="Önbelleği baypas edip yeniden AI ile üret")

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
    intent: str
    cached: bool = False


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    start = time.time()

    if not req.question.strip():
        raise HTTPException(400, "Soru boş olamaz")

    if not req.force_refresh:
        cached_res = get_cached_answer(state.db, req.question, req.company)
        if cached_res:
            sources_objs = [Source(**s) for s in cached_res["sources"]]
            return AskResponse(
                answer=cached_res["answer"],
                sources=sources_objs,
                chunks_used=cached_res["chunks_used"],
                query_time_ms=cached_res["query_time_ms"],
                intent=cached_res["intent"],
                cached=True,
            )

    intent_code, selected_prompt = detect_intent(req.question)

    comp_name = req.company.upper() if req.company else "BİST ŞİRKETİ"
    selected_prompt = selected_prompt.replace("[ŞİRKET_KODU]", comp_name)

    real_facts_summary = ""
    matched_chunks = []
    seen_ids = set()

    if req.company and intent_code in ("BILANCO", "GELIR"):
        facts = extract_real_financial_facts(state.db, req.company)
        if facts:
            fact_lines = [f"• {k.upper()}: {v}" for k, v in facts.items() if k != "date"]
            real_facts_summary = f"BİLANÇO DÖNEMİ: {facts.get('date')} (Birim: {facts.get('para_birimi')})\nAYIKLANAN GERÇEK VERİLER VE RASYOLAR:\n" + "\n".join(fact_lines)

    elif req.company and intent_code == "TEMETTU":
        div_facts = extract_dividend_facts(state.db, req.company)
        if div_facts:
            real_facts_summary = div_facts

    if req.company:
        comp_str = req.company.upper()

        if intent_code in ("BILANCO", "GELIR"):
            rows = state.db.execute(
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
            rows = state.db.execute(
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
            rows = state.db.execute(
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

    if len(matched_chunks) < req.top_k:
        emb_client, _, _ = get_chat_client(groq_key=None)
        try:
            subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL], capture_output=True)
            q_res = emb_client.embeddings.create(model=EMBEDDING_MODEL, input=req.question)
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
        except Exception as e:
            print(f"[-] Vektör arama uyarısı: {e}")

    matched_chunks = matched_chunks[:req.top_k]

    if not matched_chunks:
        return AskResponse(
            answer="Bu filtrelerle KAP verilerinde bilgi bulunamadı.",
            sources=[],
            chunks_used=0,
            query_time_ms=round((time.time() - start) * 1000, 1),
            intent=intent_code,
            cached=False,
        )

    context_parts = []
    if real_facts_summary:
        context_parts.append(f"[AYIKLANAN DOĞRUDAN KAP BİLGİLERİ VE VERİLER]\n{real_facts_summary}")

    for i, chunk in enumerate(matched_chunks):
        header = f"[Kaynak {i+1} - {chunk['type']} | Tarih: {chunk['date']}] {chunk['company']} — {chunk['title'] or ''}"
        snippet = chunk['text'][:850]
        context_parts.append(f"{header}\n{snippet}")

    context = "\n\n---\n\n".join(context_parts)

    if "groq.com" not in str(state.client.base_url):
        subprocess.run(["foundry", "model", "load", state.chat_model_name], capture_output=True)

    messages = [
        {"role": "system", "content": selected_prompt},
        {
            "role": "user",
            "content": f"KAP GERÇEK BİLDİRİM METİNLERİ VE VERİLER:\n{context}\n\n"
                       f"SORU: {req.question}\n\n"
                       f"Yukarıdaki metinlerde yer alan GERÇEK RAKAMLARI VE TARİHLERİ kullanarak soruyu yanıtla:",
        },
    ]

    chat_res = state.client.chat.completions.create(
        model=state.chat_model_name,
        messages=messages,
        max_tokens=650,
        temperature=0.1,
    )
    answer = chat_res.choices[0].message.content
    
    # Clean reasoning blocks (<think> or numbered internal CoT steps)
    if "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()
    elif "<think>" in answer:
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

    # Extract clean response starting at title emoji / markdown header
    for header_symbol in ["📋", "📈", "💰", "🤝", "⭐", "# "]:
        if header_symbol in answer:
            answer = header_symbol + answer.split(header_symbol, 1)[-1]
            break

    # Clean any trailing prompt quotation leftover
    if answer.endswith("'. Never include English thinking steps or internal logic in t"):
        answer = answer.replace("'. Never include English thinking steps or internal logic in t", "").strip()

    if "Lütfen bildiğiniz verilerde" in answer:
        answer = answer.split("Lütfen bildiğiniz verilerde")[0].strip()

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

    query_time = (time.time() - start) * 1000

    result_dict = {
        "answer": answer,
        "sources": [s.model_dump() for s in sources],
        "chunks_used": len(matched_chunks),
        "query_time_ms": round(query_time, 1),
        "intent": intent_code,
    }

    set_cached_answer(state.db, req.question, req.company, result_dict)

    return AskResponse(
        answer=answer,
        sources=sources,
        chunks_used=len(matched_chunks),
        query_time_ms=round(query_time, 1),
        intent=intent_code,
        cached=False,
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

    cache_count = state.db.execute("SELECT COUNT(*) as c FROM qa_cache").fetchone()["c"]

    return {
        "total_chunks": total,
        "total_companies": companies,
        "content_chunks": content,
        "pdf_chunks": pdf,
        "cached_queries": cache_count,
        "provider": state.provider_name,
        "model": state.chat_model_name,
        "type_distribution": {r["type"]: r["c"] for r in types},
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "db_connected": state.db is not None,
        "client_ready": state.client is not None,
        "provider": state.provider_name,
        "model": state.chat_model_name,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KAP RAG API Sunucusu (Groq API & Local Foundry)")
    parser.add_argument("--host", default="0.0.0.0", help="Sunucu adresi")
    parser.add_argument("--port", type=int, default=8000, help="Port numarası")
    parser.add_argument("--groq-key", default=DEFAULT_GROQ_KEY, help="Groq API anahtarı (gsk_...)")
    args = parser.parse_args()

    state.groq_key = args.groq_key

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
