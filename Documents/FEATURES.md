# KAP RAG — Özellikler ve Kullanım Mantığı ✨

Bu doküman, **KAP RAG** projesinde yer alan tüm özellikleri, iş mantığını ve çıktı formatlarını detaylı bir şekilde açıklar.

---

## 📋 Özellik Listesi ve Özet Tablo

| Özellik | Açıklama | Dosya/Bileşen |
| :--- | :--- | :--- |
| **Recency-First Arama** | Sorgularda en güncel 2026 KAP bildirimlerini önceliklendirir. | `ask_foundry.py`, `server.py` |
| **Smart Intent Routing** | Finansal terimlerde doğrudan `FR` (Bilanço) türünü sorgular. | `ask_foundry.py`, `server.py` |
| **Doğrudan Veri Ayıklama** | SQLite'tan gerçek Hasılat, Borç ve Özkaynak sayılarını çeker. | `extract_real_financial_facts` |
| **Otomatik Bilanço Karnesi** | Kârlılık, Likidite, Borçluluk ve Özkaynak için 5 üzerinden puan verir. | `SYSTEM_PROMPT` |
| **Çeyreklik Trend Grafiği** | Çeyreklik net kâr/bilanço görünümünü görselleştirir. | `SYSTEM_PROMPT` |
| **REST API Servisi** | Dış entegrasyonlar için FastAPI tabanlı HTTP API sunar. | `server.py` |
| **CLI Sorgu Motoru** | Terminal üzerinden interaktif ve hızlı arama sağlar. | `ask_foundry.py` |

---

## 🕒 1. Recency-First (Güncellik Odaklı) Arama

### Ne İş Yapar?
Finansal piyasalarda geçmiş kararlar yerine en son açıklanan KAP bildirimleri kritiktir. Recency-First özelliği, vektör araması sonucunda elde edilen aday bildirimleri tarih bilgisine göre (`ORDER BY date DESC`) yeniden sıralar.

### Nasıl Çalışır?
1. Kullanıcı bir soru sorduğunda vektör benzerliği ile 60 adet aday chunk (`top_k * 15`) bulunur.
2. SQLite sorgusunda bu adaylar `date` alanına göre yeniden eskiye dizilir.
3. Böylece `2026.08.05` tarihli son çeyrek kararları `2024` yılındaki duyuruların önüne geçer.

---

## 🎯 2. Akıllı Finansal Niyet Algılama (Smart Intent Routing)

### Ne İş Yapar?
Kullanıcının sorusunda *"bilanço"*, *"finansal rapor"*, *"hasılat"*, *"kâr"*, *"borç"*, *"özkaynak"* gibi finansal terimler geçtiğinde sistem, genel şirket duyuruları (ODA) yerine doğrudan **`FR` (Finansal Rapor)** bildirimlerini sorgular.

### Örnek Çalışma:
- **Soru:** `"THYAO son genel kurul kararları"` ➡️ Genel Özel Durum Açıklamaları (`ODA`) taranır.
- **Soru:** `"THYAO son finansal rapor ve ciro"` ➡️ Otomatik olarak `type = 'FR'` Finansal Rapor tabloları taranır.

---

## 🔍 3. Doğrudan Veri Ayıklama Motoru (Zero-Hallucination)

### Ne İş Yapar?
Yapay zeka modellerinin sayıları uydurmasını (hallucination) veya ezber şablonları tekrarlamasını engeller.

### Nasıl Çalışır?
`extract_real_financial_facts` fonksiyonu SQLite veritabanındaki en son bildirim metinlerini regex ile tarar ve şu ana kalemlerin gerçek sayısal karşılıklarını (TL / Bin TL) ayıklar:
- **Hasılat / Ciro**
- **TOPLAM DÖNEN VARLIKLAR**
- **TOPLAM KISA VADELİ YÜKÜMLÜLÜKLER**
- **TOPLAM UZUN VADELİ YÜKÜMLÜLÜKLER**
- **TOPLAM ÖZKAYNAKLAR**

Bu gerçek veriler LLM'e ham gerçeklik olarak iletilir.

---

## 📋 4. Otomatik Bilanço Karnesi

### Ne İş Yapar?
Şirketin açıklanan son bilançosunu 4 temel finansal kategoride 5 üzerinden matematiksel olarak puanlar:

1. 📈 **Kârlılık & Ciro (Profitability):** Ciro seviyesi ve kârlılık marjı.
2. 💧 **Likidite & Dönen Varlıklar (Liquidity):** Cari Oran ($\frac{\text{Dönen Varlıklar}}{\text{Kısa Vadeli Borçlar}}$) dengesi.
3. 🛡️ **Borçlar & Yükümlülükler (Leverage):** Kaldıraç oranı ve borç yapısı.
4. ⚙️ **Özkaynak Gücü (Equity):** Özkaynak büyüklüğü ve bilanço sağlamlığı.
5. ⭐ **Genel Skor:** Tüm kategorilerin genel değerlendirmesi (Zayıf / Orta / İyi / Çok İyi).

---

## 📊 5. Çeyreklik Trend Grafiği

### Ne İş Yapar?
Son 6-8 çeyreğe ait net kâr veya bilanço büyüklüğünün çeyreklik değişimini metinsel ASCII veya Markdown formatında görselleştirir:

```text
2025/3  : █ █ █ █ █ █ █ ░ ░ ░ (18.2 Milyar TL)
2025/6  : █ █ █ █ █ █ █ █ █ ░ (24.5 Milyar TL)
2025/9  : █ █ █ █ █ █ █ █ █ █ (29.1 Milyar TL)
2025/12 : █ █ █ █ █ ░ ░ ░ ░ ░ (12.4 Milyar TL)
2026/3  : █ █ █ █ █ █ ░ ░ ░ ░ (15.8 Milyar TL)
2026/6  : █ █ █ █ █ █ █ ░ ░ ░ (18.8 Milyar TL)
```

---

## 🌐 6. REST API Endpoints (`server.py`)

FastAPI sunucusu dış dünyayla iletişim kurmak için aşağıdaki uç noktaları (endpoints) sunar:

### `POST /api/ask`
Soru-cevap uç noktası.

**İstek Body:**
```json
{
  "question": "THYAO'nun karnesi nasıl?",
  "company": "THYAO",
  "type": null,
  "top_k": 4
}
```

**Yanıt Body:**
```json
{
  "answer": "📋 [THYAO] Bilanço Karnesi...\n⭐ Genel Finansal Skor: 3.5/5...",
  "sources": [
    {
      "company": "THYAO",
      "company_name": "TÜRK HAVA YOLLARI AO",
      "title": "Finansal Rapor",
      "date": "2026.08.05 08:00:21",
      "type": "FR",
      "url": "https://www.kap.org.tr/tr/Bildirim/1643238",
      "source_type": "content",
      "relevance_rank": 1
    }
  ],
  "chunks_used": 4,
  "query_time_ms": 1420.5
}
```

### `GET /api/companies`
Sistemde indekslenmiş tüm şirketlerin listesini ve şirket isimlerini döndürür.

### `GET /api/stats`
İndekslenen toplam bildirim sayısı, chunk sayıları, bildirim türü dağılımı ve aktif LLM modellerini döndürür.

### `GET /api/health`
Sunucu ve veritabanı durumunu kontrol eder.
