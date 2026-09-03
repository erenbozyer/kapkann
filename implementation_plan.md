# KAP RAG Backend — Microsoft Foundry Local ile Yerel AI Sistemi

## Proje Özeti

KAP (Kamu Aydınlatma Platformu) üzerinden BIST şirketleri için çekilmiş ham bildirimleri, tamamen yerelde çalışan bir RAG (Retrieval-Augmented Generation) pipeline'ı ile sorgulanabilir hale getiriyoruz. Hiçbir cloud API'si veya API key gerekmeyecek — tüm işlem RTX 4050 GPU üzerinde çalışacak.

---

## 1. Elimizdeki Veri — Mevcut Durum

### Disk Yapısı
```
c:\Users\user\Desktop\kapkann\
└── KAP_DATA/
    ├── THYAO/          (171 JSON dosya)
    ├── AKBNK/          
    ├── ALARK/          
    ├── ASELS/          
    ├── ...             
    └── (toplam 191 şirket klasörü, 22,701 JSON dosya)
```

### JSON Şeması (Her Bildirim Dosyası)
```json
{
  "id": "4028328d916b98a0019173be88fb375d",
  "index": 1326563,
  "company": "THYAO",
  "company_name": "TÜRK HAVA YOLLARI A.O.",
  "title": "Finansal Duran Varlık Edinimi",
  "date": "2024.08.21 10:20:42",
  "type": "ODA",
  "summary": "Yeni Şirket Kuruluş Kararı",
  "content": "Finansal Duran Varlık Edinimi\nNoncurrent Financial...",
  "attachments": [
    {
      "id": "4028328c919f164a0191dc7aba063579",
      "filename": "ASELSAN SPK RAPORU 30.06.2024.pdf",
      "extension": "pdf",
      "url": "https://www.kap.org.tr/tr/api/file/download/..."
    }
  ],
  "url": "https://www.kap.org.tr/tr/Bildirim/1326563"
}
```

### Bildirim Türleri ve Kategorileri
| Tür | Açıklama | İçerik Karakteri |
|-----|----------|-------------------|
| **ODA** | Özel Durum Açıklamaları | Pay alım/satım, genel kurul kararları, temettü, yeni iş ilişkileri. Kısa, operasyonel. |
| **FR** | Finansal Raporlar | Bilanço, gelir tablosu, nakit akım. Yoğun sayısal veri. |
| **DG** | Diğer / Bilgi Formları | Kurumsal yönetim uyum, katılım finansı ilkeleri. Soru-cevap formatı. |

### Attachment İstatistikleri (Analiz Sonuçları)
| Metrik | Değer |
|--------|-------|
| Toplam bildirim | 22,701 |
| Attachment'lı bildirim | **7,127** (%31.4) |
| Toplam attachment dosyası | **12,344** |
| Dosya formatı | **%100 PDF** |

> [!IMPORTANT]
> Bildirimlerin neredeyse **üçte biri** PDF eki içeriyor. Bu PDF'ler genellikle SPK raporları, finansal tablolar, bağımsız denetim raporları ve kurumsal sunum dosyaları. RAG kalitesi için bu verilerin de indekslenmesi kritik.

### Yapılan Temizlikler (Gemini ile)
- XBRL etiketleri (`oda_ExplanationTextBlock|` vb.) temizlendi
- Boş parantezler `[]`, `{}` ve `http://www.xbrl.org/` URL'leri çıkarıldı
- Satır sonu `\n` düzeni korundu (chunking algoritması için kritik)
- Her bildirim ayrı dosya → RAM şişmesi engellendi

---

## 2. Model Seçimi (Doğrulanmış)

Foundry Local katalogundaki modeller `foundry model list` ile doğrulandı:

| Bileşen | Model | Boyut | Durum |
|---------|-------|-------|-------|
| **Embedding** | `qwen3-embedding-0.6b` | 478 MB | ✅ Katalogda mevcut |
| **Chat LLM (Birincil)** | `phi-4-mini` | 3.6 GB | ✅ Tool calling destekli |
| **Chat LLM (Yedek/Hafif)** | `phi-3.5-mini` | 2.1 GB | ✅ Daha hafif alternatif |
| **Chat LLM (Güçlü)** | `qwen3-8b` | 5.5 GB | ✅ Tool calling + daha iyi Türkçe |

> [!NOTE]
> `phi-4-mini` (3.6 GB) ilk tercihimiz — tool calling desteği var, RTX 4050'de rahatlıkla çalışır. Türkçe performansı yetersiz kalırsa `qwen3-4b` veya `qwen3-8b`'ye geçeriz. Kullanıcıya runtime'da model seçme imkanı da vereceğiz.

---

## 3. Teknoloji Stack'i

| Bileşen | Teknoloji | Neden? |
|---------|-----------|--------|
| **AI Runtime** | Microsoft Foundry Local (WinML) | Yerel, cloud-free, RTX 4050 GPU hızlandırma |
| **Embedding Model** | `qwen3-embedding-0.6b` | Hafif, hızlı, Foundry katalogunda mevcut |
| **Chat LLM** | `phi-4-mini` | 3.6 GB, tool calling, iyi performans |
| **Vector Store** | SQLite + `sqlite-vec` | Tek dosya DB, pip ile kurulur, native vector search |
| **PDF Extraction** | `PyMuPDF (fitz)` | C bazlı, hızlı, tablo ve metin çıkarma |
| **Backend API** | FastAPI (Python) | Async, hızlı, kolay REST endpoint |
| **Chunking** | RecursiveCharacterTextSplitter (custom) | `\n` bazlı, 1500 karakter, 200 overlap |

---

## 4. PDF Attachment Handling Stratejisi

### Sorun
12,344 PDF dosyası KAP sunucularında duruyor. İçerikleri:
- SPK raporları (bağımsız denetim, sorumluluk beyanları)
- Finansal tablolar (bilanço, gelir tablosu detayları)
- Kurumsal sunumlar
- Yatırımcı bilgi notları

### Çözüm: 2 Fazlı Yaklaşım

#### Faz 1 — Content-Only RAG (Hemen)
İlk olarak **sadece `content` alanı** ile çalışan RAG sistemini kuracağız. Bu zaten 22,701 bildirimin metin gövdesini kapsar. Birçok bildirimin `content` alanı zaten PDF'deki bilgilerin yapılandırılmış özetini içerir.

#### Faz 2 — PDF İndirme + Extraction (Sonra)
PDF'leri KAP'tan indirip metin çıkararak RAG'ı zenginleştireceğiz.

**PDF Pipeline:**
```
KAP_DATA/{TICKER}/{INDEX}.json
    │
    ▼ attachments[] URL'lerini oku
    │
    ▼ (download_pdfs.py)
KAP_DATA/{TICKER}/attachments/{ATT_ID}.pdf
    │
    ▼ (PyMuPDF ile metin çıkar)
    │
    ▼ (Chunk + Embed)
    │
    ▼ SQLite'a yaz (source_type = "pdf_attachment")
```

**Disk Yapısı (Faz 2 sonrası):**
```
KAP_DATA/
├── THYAO/
│   ├── 1326563.json
│   ├── 1332647.json
│   └── attachments/
│       ├── 4028328c...3579.pdf    (ASELSAN SPK RAPORU)
│       └── 4028328c...357a.pdf    (ASELSAN CMB Report)
├── ASELS/
│   └── ...
```

**download_pdfs.py özellikleri:**
- KAP WAF korumasına karşı session yönetimi + rate limiting (Gemini'de kurduğumuz aynı mekanizma)
- Resume desteği: İndirilmiş PDF'leri atlama
- Progress tracking: Toplam/kalan dosya sayısı
- Paralel worker: 3-5 thread (KAP'a nazik oluyoruz)

**PDF → Metin çıkarma kuralları:**
- `PyMuPDF (fitz)` ile sayfa sayfa metin çıkar
- Boş sayfaları atla
- Her sayfanın metnini `[Sayfa X/{TOPLAM}]` tag'i ile işaretle
- Tablo yapıları için satır/sütun düzenini korumaya çalış
- OCR gerekiyorsa atlansın (KAP PDF'leri %99 dijital)

**chunks tablosundaki farklılık:**
```sql
-- Faz 2'de eklenen kolon
source_type TEXT DEFAULT 'content'  -- 'content' veya 'pdf_attachment'
attachment_filename TEXT             -- 'ASELSAN SPK RAPORU 30.06.2024.pdf'
```

> [!TIP]
> **Neden 2 faz?** 12,344 PDF indirmek + metin çıkarmak saatlerce sürebilir. İlk fazda sistemi çalışır hale getirip test edebilirsin. PDF'ler arka planda inerken RAG zaten kullanılabilir.

---

## 5. RAG Pipeline Mimarisi

```
┌──────────────────────────────────────────────────────────────┐
│                    INDEXING (Tek Seferlik)                    │
│                                                              │
│  Faz 1: KAP_DATA/*.json → content alanı                     │
│  Faz 2: KAP_DATA/*/attachments/*.pdf → PyMuPDF metin        │
│       │                                                      │
│       ▼                                                      │
│  [RecursiveChunker: 1500 char, 200 overlap]                  │
│  [+ Metadata: company, type, date, source_type]              │
│       │                                                      │
│       ▼                                                      │
│  [qwen3-embedding-0.6b → 1024-dim vektör]                   │
│       │                                                      │
│       ▼                                                      │
│  [SQLite + sqlite-vec: kap_vectors.db]                       │
│  ┌──────────────────────────────────────────┐                │
│  │ chunks (id, company, type, date, title,  │                │
│  │   text, source_url, source_type,         │                │
│  │   attachment_filename)                    │                │
│  │ vec_chunks (embedding float[1024])        │                │
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    QUERY (Her Sorgu)                          │
│                                                              │
│  Kullanıcı Sorusu + (Opsiyonel) Şirket / Tür Filtresi       │
│       │                                                      │
│       ▼                                                      │
│  [qwen3-embedding-0.6b → Sorgu Vektörü]                     │
│       │                                                      │
│       ▼                                                      │
│  [sqlite-vec MATCH → Top-K benzer chunk]                     │
│  [+ WHERE company/type/source_type filtresi]                 │
│       │                                                      │
│       ▼                                                      │
│  [Prompt: System + Context Chunks + Soru]                    │
│       │                                                      │
│       ▼                                                      │
│  [phi-4-mini (veya seçili LLM) → Kaynaklı Cevap]            │
│       │                                                      │
│       ▼                                                      │
│  JSON: {answer, sources[], chunks_used}                      │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Dosya Yapısı (Oluşturulacak)

```
c:\Users\user\Desktop\kapkann\
├── KAP_DATA/                    # ✅ Mevcut (22,701 JSON)
├── requirements.txt             # 🆕 Bağımlılıklar
├── chunker.py                   # 🆕 Metin bölme modülü
├── index_foundry.py             # 🆕 Faz 1: Content vektör indeksleme
├── ask_foundry.py               # 🆕 RAG sorgu + test scripti
├── server.py                    # 🆕 FastAPI backend
├── download_pdfs.py             # 🆕 Faz 2: PDF indirme scripti
├── index_pdfs.py                # 🆕 Faz 2: PDF metin çıkar + indeksle
└── kap_vectors.db               # 🆕 (oluşacak) SQLite vektör DB
```

---

## 7. Detaylı Uygulama Adımları

### Adım 1: `requirements.txt`
```
foundry-local-sdk-winml
sqlite-vec
numpy
fastapi
uvicorn[standard]
PyMuPDF
requests
```

### Adım 2: `chunker.py` — Metin Bölme Modülü

Bildirimleri 1500 karakterlik parçalara bölecek. Her chunk'a metadata eklenecek:
- `company`: Şirket kodu (THYAO, AKBNK, vb.)
- `company_name`: Tam unvan
- `type`: Bildirim türü (ODA/FR/DG)
- `date`: Tarih
- `title`: Başlık
- `source_url`: KAP linki
- `source_index`: Bildirim numarası
- `source_type`: "content" veya "pdf_attachment"
- `attachment_filename`: PDF dosya adı (varsa)

**Chunking stratejisi:**
- Öncelik sırası: `\n\n` → `\n` → `. ` → ` `
- Max chunk: 1500 karakter
- Overlap: 200 karakter
- Kısa bildirimler (< 1500 char) tek chunk olarak kalır

### Adım 3: `index_foundry.py` — Faz 1 Vektör İndeksleme

1. Foundry Local SDK'yı başlat
2. `qwen3-embedding-0.6b` modelini indir/yükle
3. `KAP_DATA/` altındaki tüm JSON dosyalarının `content` alanını tara
4. Her dosyayı oku → chunk'la → embed et
5. SQLite + sqlite-vec'e yaz
6. Progress bar ile ilerleme göster

**SQLite Şeması:**
```sql
-- Metadata tablosu
CREATE TABLE chunks (
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
);

-- Vektör tablosu (sqlite-vec)
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    id INTEGER PRIMARY KEY,
    embedding float[1024]
);

-- Hızlı filtreleme için indeksler
CREATE INDEX idx_company ON chunks(company);
CREATE INDEX idx_type ON chunks(type);
CREATE INDEX idx_date ON chunks(date);
CREATE INDEX idx_source_type ON chunks(source_type);
```

> [!IMPORTANT]
> Faz 1: 22,701 JSON × ortalama 3-5 chunk = ~70,000-110,000 vektör. RTX 4050'de tahmini süre: **15-30 dakika**.

### Adım 4: `ask_foundry.py` — RAG Sorgu Motoru

Core fonksiyon:
```python
def ask_kap(question: str, company_filter: str = None, 
            type_filter: str = None, top_k: int = 5) -> dict:
    """
    KAP bildirimleri üzerinde RAG sorgusu yapar.
    
    Returns:
        {
            "answer": "...",
            "sources": [
                {"company": "THYAO", "title": "...", "date": "...", 
                 "url": "...", "source_type": "content"},
                ...
            ],
            "chunks_used": 5
        }
    """
```

**System prompt (Türkçe):**
```
Sen bir KAP (Kamu Aydınlatma Platformu) uzman analistsin.
Sana verilen KAP bildirimlerini kullanarak kullanıcının sorusunu yanıtla.
- Sadece verilen kaynaklardaki bilgilere dayanarak cevap ver.
- Her bilgiyi hangi şirketin hangi tarihli bildirimine dayandığını belirt.
- Bilgi yoksa "Bu konuda KAP verilerinde bilgi bulunamadı" de.
- Finansal verilerde rakamları doğru aktar.
- Türkçe yanıt ver.
```

### Adım 5: `server.py` — FastAPI Backend

```
POST /api/ask
  Body: {"question": "...", "company": "THYAO", "type": "ODA"}
  Response: {"answer": "...", "sources": [...]}

GET /api/companies
  Response: ["THYAO", "AKBNK", "ALARK", ...]

GET /api/stats
  Response: {"total_chunks": 85000, "total_companies": 191, 
             "pdf_chunks": 0, "content_chunks": 85000}

GET /api/models
  Response: {"embedding": "qwen3-embedding-0.6b", "chat": "phi-4-mini"}
```

### Adım 6 (Faz 2): `download_pdfs.py` — PDF İndirme

- JSON dosyalardan `attachments` URL'lerini topla
- KAP'tan rate-limited indirme (3-5 worker, session yönetimi)
- `KAP_DATA/{TICKER}/attachments/{ATT_ID}.pdf` olarak kaydet
- Resume desteği + progress tracking

### Adım 7 (Faz 2): `index_pdfs.py` — PDF → Vektör

- PyMuPDF ile PDF'lerden metin çıkar
- Sayfa bazlı chunk'la + embed et
- Mevcut `kap_vectors.db`'ye `source_type='pdf_attachment'` ile ekle

---

## 8. Önemli Tasarım Kararları

### Neden `sqlite-vec` (Saf NumPy Cosine Sim yerine)?
- **Performans**: Native C kodu, Python loop'undan 10-50x hızlı
- **Filtreleme**: SQL ile `WHERE company = 'THYAO'` + vektör araması birlikte
- **Ölçeklenebilirlik**: 100K+ vektör sorunsuz
- **Tek Dosya**: Tüm veri + vektörler `kap_vectors.db` içinde

### Neden `phi-4-mini` (phi-3.5-mini yerine)?
- Tool calling desteği var (ileride function calling eklenebilir)
- 3.6 GB, RTX 4050'de rahat çalışır
- `phi-3.5-mini` (2.1 GB) yedek olarak kalıyor

### Neden 2 Fazlı PDF Yaklaşım?
- 12,344 PDF indirmek + çıkarmak uzun sürer
- Faz 1 ile RAG hemen çalışır hale gelir
- PDF eklendikçe kalite artar ama sistem zaten kullanılabilir

---

## 9. Doğrulama Planı

### Otomatik Testler
1. **Index testi**: `index_foundry.py` çalıştır, DB boyutu ve kayıt sayısı kontrol
2. **Sorgu testi**: Bilinen bildirimlere soru sor, doğru chunk'ların geldiğini doğrula
3. **API testi**: FastAPI endpoint'lerini curl ile test et

### Manuel Test Soruları
```
1. "THYAO Sidney'e uçuş başlatma kararı ne zaman alındı?"
   → Beklenen: 2024.09.12 tarihli ODA bildirimi
   
2. "ALARK'ın son temettü kararı nedir?"
   → Beklenen: İlgili ODA bildirimi

3. "AKBNK'ın son finansal rapor özeti?"
   → Beklenen: FR tipi bildirim chunk'ları
```

---

## Open Questions

> [!NOTE]
> **Klasör İsimlendirme Sorunu**: Bazı şirket klasörleri birden fazla ticker içeriyor (örn: `ISATR, ISBTR, ISCTR, ISKUR, TIB`). İndeksleme sırasında JSON'daki `company` alanını kullanacağız (klasör adı değil).

> [!NOTE]
> **LLM Model Tercihi**: `phi-4-mini` (3.6 GB, tool calling) mi yoksa `qwen3-4b` (2.6 GB, tool calling) mi tercih edersin? İkisi de Foundry'de mevcut. Qwen3 Türkçe'de biraz daha iyi olabilir.

> [!NOTE]
> **PDF İndirme Zamanlaması**: Faz 2 PDF indirme işlemini ne zaman başlatmak istersin? Faz 1 RAG çalışır çalışmaz mı, yoksa önce RAG'ı test edip memnun kaldıktan sonra mı?
