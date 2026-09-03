# KAP RAG — Klasör ve Dosya Yapısı 📂

Bu doküman, **KAP RAG** projesinin klasör hiyerarşisini, dosyalarını ve kod içerisindeki kritik fonksiyon/sınıf görevlerini ayrıntılı olarak açıklar.

---

## 🌳 Klasör Ağacı Yapısı

```text
c:\Users\user\Desktop\kapkann\
├── Documents/                     # Proje Dokümantasyon Klasörü
│   ├── README.md                  # Genel Bakış ve Hızlı Başlangıç
│   ├── ARCHITECTURE.md            # Mimari ve Çalışma Mantığı
│   ├── FEATURES.md                # Özellikler ve Kullanım Mantığı
│   ├── SETUP.md                   # Sıfırdan Adım Adım Kurulum Tutorialı
│   ├── PROJECT_STRUCTURE.md       # Klasör ve Dosya Yapısı (Bu Doküman)
│   ├── DEVELOPMENT.md             # Geliştirme ve Teknik Detaylar
│   └── TROUBLESHOOTING.md         # Hatalar ve Çözüm Yolları
├── KAP_DATA/                      # Ham KAP Bildirim Verileri (JSON)
│   ├── THYAO/                     # Şirket Kodlarına Göre Klasörler
│   ├── AKBNK/
│   └── ... (191 Şirket Klasörü)
├── analyze_attachments.py         # PDF ve Ek Dosya İstatistik Analiz Betiği
├── ask_foundry.py                 # CLI İnteraktif Sorgu ve Karne Motoru Betiği
├── chunker.py                     # KAP Metinlerini Akıllı Parçalama (Chunking) Modülü
├── index_foundry.py               # Vektörleştirme ve SQLite Kayıt Boru Hattı
├── kap_vectors.db                 # sqlite-vec Destekli Vektör Veritabanı (616 MB)
├── requirements.txt               # Proje Bağımlılıkları
├── server.py                      # FastAPI REST API Sunucusu
└── .gitignore                     # Git Tarafından İzlenmeyecek Dosya Kuralları
```

---

## 📄 Dosya Görevleri ve Kritik Fonksiyonlar

### 1. `ask_foundry.py` (CLI Sorgu Motoru)
Terminal üzerinden interaktif soru-cevap ve karne üretimi yapar.

#### Önemli Fonksiyonlar:
- `extract_real_financial_facts(db, company)`: SQLite DB'den şirketin en son FR bildirimindeki **Hasılat, Dönen Varlıklar, Kısa/Uzun Borçlar, Özkaynaklar** değerlerini doğrudan ayıklar.
- `ask_kap(question, db, client, ...)`: Kullanıcı sorusunu işler, Intent Router ile finansal niyet tespiti yapar, vektör araması çalıştırır, Recency-First sıralaması uygular ve `phi-4-mini` modelinden yanıt üretir.
- `get_foundry_base_url()`: Sistemdeki Microsoft Foundry Local servis adresini (`http://127.0.0.1:51667/v1`) dinamik olarak tespit eder.
- `serialize_f32(vec)`: Vektör dizisini `sqlite-vec` uyumlu ikili (binary) formata dönüştürür.

---

### 2. `server.py` (FastAPI REST API Sunucusu)
Web ve mobil uygulamalar için HTTP REST API uç noktaları sağlar.

#### Önemli Sınıf ve Uç Noktalar:
- `AppState`: Veritabanı bağlantısı ve OpenAI istemcisini saklayan genel uygulama durumu.
- `POST /api/ask`: Soru-cevap ve karne üretim uç noktası (`AskRequest` alır, `AskResponse` döner).
- `GET /api/companies`: İndekslenmiş tüm şirketlerin listesini döndürür.
- `GET /api/stats`: Toplam chunk sayılarını, şirket dağılımını ve bildirim türü istatistiklerini verir.
- `GET /api/health`: Sunucu sağlık durumunu kontrol eder.

---

### 3. `chunker.py` (Metin Parçalama Modülü)
KAP JSON verilerini anlamlı parçalara böler.

#### Önemli Fonksiyonlar:
- `chunk_disclosure(disclosure_data)`: Tek bir KAP bildirim JSON'unu alır, bildirim türüne göre (`FR` veya `ODA`) uygun uzunlukta chunk'lara ayırır.
- Finansal tablo etiketlerini (`kap-fr_...`) koruyarak tabloların parçalanmasını engeller.

---

### 4. `index_foundry.py` (İndeksleme ve Vektörleştirme)
`KAP_DATA/` altındaki tüm JSON dosyalarını tarar ve vektör veritabanına işler.

#### Önemli Fonksiyonlar:
- `create_tables(db)`: SQLite üzerinde `chunks` ve `vec_chunks` (sqlite-vec) tablolarını oluşturur.
- `index_all_disclosures(...)`: Tüm şirket klasörlerini gezer, `chunker.py` ile parçalar, `qwen3-embedding-0.6b` modeli ile 1024 boyutlu vektörlerini alır ve toplu (batch) olarak veritabanına yazar.

---

### 5. `analyze_attachments.py` (Ek Dosya Analiz Betiği)
KAP bildirimlerindeki ekleri (`.pdf`, `.xlsx`, `.docx`) analiz eder.

#### Önemli İstatistikler:
- Hangi şirketlerin ne kadar PDF veya finansal tablo eki olduğunu raporlar (Faz 2 PDF indeksleme adımı için altlık oluşturur).

---

### 6. `kap_vectors.db` (sqlite-vec Veritabanı)
- **Boyut:** ~616 MB
- **Teknoloji:** C tabanlı hızlı SQLite vektör arama eklentisi (`sqlite-vec` 0.1.9).
- **Kapasite:** 22.701 KAP Bildirimi, 95.387 Vektör Parçası.
