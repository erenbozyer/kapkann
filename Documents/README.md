# KAP RAG — Yerel BİST KAP Bildirimleri ve Finansal Analiz Motoru 🚀

**KAP RAG**, Türkiye Kamu Aydınlatma Platformu (KAP) üzerinde yayınlanan 22.000'den fazla şirket bildirimini ve çeyreklik finansal raporu yerel GPU (NVIDIA RTX 4050 6GB) üzerinde, sıfır bulut bağımlılığı ve tam gizlilik ile analiz eden yüksek performanslı bir Yapay Zeka (RAG) backend sistemidir.

---

## 🎯 Projenin Amacı ve Ne Yaptığı

Finansal piyasalarda ve BİST (Borsa İstanbul) üzerinde işlem gören şirketlerin KAP bildirimleri çok büyük bir veri kümesi oluşturur (bilançolar, özel durum açıklamaları, ihraç tavanları, uçuş ve ortaklık kararları). Klasik LLM'ler güncel KAP verilerine erişemez veya büyük bilanço verilerini işlerken yüksek bulut maliyetlerine neden olur.

**KAP RAG'ın Çözümü:**
1. **%100 Yerel Çalışma:** Microsoft Foundry Local SDK (`phi-4-mini` ve `qwen3-embedding-0.6b`) kullanarak veriyi yerel GPU üzerinde işler, API/Bulut ücretini sıfırlar.
2. **22.701 KAP Bildirim İndeksi:** 191 BİST şirketine ait 95.387 metin parçası (chunk) `sqlite-vec` vektör veritabanında saklanır.
3. **Akıllı Finansal Analiz & Karne:** Sadece anlamsal (vektörel) arama yapmakla kalmaz; veritabanından **Hasılat, Dönen Varlıklar, Kısa/Uzun Borçlar, Özkaynaklar** rakamlarını %100 gerçek sayılarla çeker ve 5 üzerinden **Otomatik Bilanço Karnesi** ile **Çeyreklik Trend Grafikleri** üretir.
4. **Güncellik Önceliği (Recency-First):** 2026 yılı güncel KAP duyurularını geçmiş yıllara ait bildirimlerin önünde tutar.

---

## 🌟 Öne Çıkan Özellikler

- **🕒 Recency-First Arama Motoru:** Vektör benzerlik aramasından sonra sonuçları kronolojik olarak `ORDER BY date DESC` ile sıralar.
- 🎯 **Akıllı Finansal Niyet Algılama (Intent Routing):** "Bilanço", "finansal rapor", "kâr", "hasılat" terimleri otomatik algılanarak `FR` (Finansal Rapor) bildirimlerine öncelik verilir.
- 📋 **Otomatik Bilanço Karnesi:** Kârlılık, Likidite, Borçluluk ve Özkaynak Gücü kategorilerinde 5 üzerinden matematiksel skorlama yapar.
- 📊 **Çeyreklik Trend Grafiği:** Son 6-8 çeyreğe ait net kâr ve finansal durum trendini görsel ve metinsel olarak sunar.
- ⚡ **Dinamik VRAM Yönetimi:** 6 GB VRAM'e sahip RTX 4050 ekran kartında embedding ve chat modellerini sırayla yükleyip boşaltarak GPU bellek taşmalarını (`500 Allocation Error`) önler.
- 🌐 **FastAPI REST API Sunucusu:** Dış uygulamalar, mobil ve web dashboard'ları için OpenAI uyumlu `/api/ask` endpoint'i sunar.

---

## 🚀 Hızlı Başlangıç

### 1. Gereksinimler
- **İşletim Sistemi:** Windows 10/11 (64-bit)
- **GPU:** NVIDIA GPU (Minimum 6 GB VRAM önerilir - RTX 3050/4050+)
- **Python:** Python 3.10+
- **Foundry CLI:** Microsoft Foundry Local CLI kurulu olmalıdır.

### 2. Kurulum ve Çalıştırma (3 Adımda)

```bash
# 1. Depoyu klonlayın veya dizine gidin
cd c:\Users\user\Desktop\kapkann

# 2. Bağımlılıkları yükleyin
pip install -r requirements.txt

# 3. CLI Sorgu Motorunu Çalıştırın
python ask_foundry.py "THYAO son finansal rapor ve genel durum" --company THYAO
```

### 3. REST API Sunucusunu Başlatma

```bash
python server.py --port 8000
```
Swagger Dokümantasyonu: `http://127.0.0.1:8000/docs`

---

## 📚 Dokümantasyon İndeksi

Proje detayları aşağıdaki dokümanlarda kategorize edilmiştir:

| Doküman | İçerik |
| :--- | :--- |
| 🛠️ [SETUP.md](./SETUP.md) | Sıfırdan Adım Adım Kurulum ve Çalıştırma Tutorialı |
| 📐 [ARCHITECTURE.md](./ARCHITECTURE.md) | Sistem Mimarisi, VRAM Yönetimi ve Vektör Arama Mantığı |
| ✨ [FEATURES.md](./FEATURES.md) | Tüm Özellikler, Karne Motoru ve Sorgu Detayları |
| 📂 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) | Klasör Yapısı, Dosyalar ve Fonksiyon Görevleri |
| 💻 [DEVELOPMENT.md](./DEVELOPMENT.md) | Teknik Detaylar, Mühendislik Kuralları ve Roadmap |
| ❓ [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | Sık Karşılaşılan Hatalar ve Çözüm Yolları |

---

## 📄 Lisans
Bu proje özel/yerel kullanım için geliştirilmiştir. KAP bildirim verileri Kamu Aydınlatma Platformu'na (kap.org.tr) aittir.
