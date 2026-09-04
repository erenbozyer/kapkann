# 📋 KAP RAG — 5 Spesifik Analiz Modu & Soru Şablonları Rehberi

Bu rehber, KAP RAG sistemi üzerinden BİST şirketleri için sorabileceğiniz **5 spesifik analiz kategorisini** ve her kategoriye uygun **hazır örnek soru şablonlarını** içerir.

Sistem, sorunuzu otomatik olarak analiz ederek uygun finansal şablonu ve veri ayıklama motorunu devreye sokar.

---

## 📊 1. Bilanço & Likidite Karnesi Modu (BILANCO)
Şirketlerin finansal durum tablosunu (bilanço), likidite gücünü, borç yükünü ve özkaynak dengesini 100% gerçek verilerle incelemek için kullanılır.

### ❓ Örnek Soru Şablonları:
- `[ŞİRKET_KODU]` bilanço ve borçluluk durumu nasıl? (Ör: *THYAO bilanço ve borçluluk durumu nasıl?*)
- `[ŞİRKET_KODU]` bilanço karnesi ve likidite oranları (Ör: *AEFES bilanço karnesi ve likidite oranları*)
- `[ŞİRKET_KODU]` cari oranı, varlıkları ve borç yapısı nedir? (Ör: *EREGL cari oranı, varlıkları ve borç yapısı nedir?*)
- `[ŞİRKET_KODU]` özkaynak gücü ve finansal skoru kaç? (Ör: *BIMAS özkaynak gücü ve finansal skoru kaç?*)

---

## 📈 2. Gelir Tablosu & Karlılık Analizi Modu (GELIR)
Şirketlerin satış hacmini (ciro/hasılat), esas faaliyet karlılığını, net dönem karını ve marj performansını incelemek için kullanılır.

### ❓ Örnek Soru Şablonları:
- `[ŞİRKET_KODU]` ciro ve net dönem karı ne kadar? (Ör: *TUPRS ciro ve net dönem karı ne kadar?*)
- `[ŞİRKET_KODU]` gelir tablosu özeti ve karlılığı nasıl? (Ör: *SISE gelir tablosu özeti ve karlılığı nasıl?*)
- `[ŞİRKET_KODU]` satış gelirleri ve net karı arttı mı? (Ör: *AKBNK satış gelirleri ve net karı arttı mı?*)
- `[ŞİRKET_KODU]` faaliyet karı ve ciro performansı analizi (Ör: *THYAO faaliyet karı ve ciro performansı analizi*)

---

## 💰 3. Temettü & Sermaye Artırımı Modu (TEMETTU)
Şirketlerin kar payı (temettü) dağıtım kararlarını, hisse başı brüt/net tutarları, bedelsiz/bedelli sermaye artırımı ve hak kullanım tarihlerini öğrenmek için kullanılır.

### ❓ Örnek Soru Şablonları:
- `[ŞİRKET_KODU]` temettü dağıtacak mı, kar payı kararı var mı? (Ör: *THYAO temettü dağıtacak mı, kar payı kararı var mı?*)
- `[ŞİRKET_KODU]` bedelsiz sermaye artırımı kararı var mı, oranı kaç? (Ör: *EREGL bedelsiz sermaye artırımı kararı var mı, oranı kaç?*)
- `[ŞİRKET_KODU]` temettü ödeme tarihi ve hisse başı net tutarı nedir? (Ör: *TUPRS temettü ödeme tarihi ve hisse başı net tutarı nedir?*)
- `[ŞİRKET_KODU]` sermaye artırımı ve temettü detayları (Ör: *BIMAS sermaye artırımı ve temettü detayları*)

---

## 🤝 4. Yeni İş İlişkileri & Yatırım Kararları Modu (YATIRIM)
Şirketlerin yeni imzaladığı sözleşmeleri, kazandığı ihaleleri, iş ortaklıklarını ve fabrika/kapasite yatırım duyurularını takip etmek için kullanılır.

### ❓ Örnek Soru Şablonları:
- `[ŞİRKET_KODU]` yeni iş ilişkisi veya sözleşme duyurdu mu? (Ör: *SISE yeni iş ilişkisi veya sözleşme duyurdu mu?*)
- `[ŞİRKET_KODU]` yeni yatırım veya fabrika kapasite kararı var mı? (Ör: *THYAO yeni yatırım veya fabrika kapasite kararı var mı?*)
- `[ŞİRKET_KODU]` son ihale ve sözleşme bedelleri ne kadar? (Ör: *AEFES son ihale ve sözleşme bedelleri ne kadar?*)
- `[ŞİRKET_KODU]` yeni iş anlaşmalarının ciroya etkisi (Ör: *EREGL yeni iş anlaşmalarının ciroya etkisi*)

---

## 📰 5. Genel KAP Bildirim Özeti & Şirket Haberleri Modu (GENEL)
Şirketlerin genel kurul kararlarını, yönetim kurulu açıklamalarını ve en son KAP duyurularını genel analist özet olarak incelemek için kullanılır.

### ❓ Örnek Soru Şablonları:
- `[ŞİRKET_KODU]` son KAP bildirimlerinde öne çıkanlar nelerdir? (Ör: *AKBNK son KAP bildirimlerinde öne çıkanlar nelerdir?*)
- `[ŞİRKET_KODU]` genel kurul kararları ne oldu? (Ör: *THYAO genel kurul kararları ne oldu?*)
- `[ŞİRKET_KODU]` son dönem haberleri ve yönetim kurulu duyuruları (Ör: *TUPRS son dönem haberleri ve yönetim kurulu duyuruları*)

---

## 💡 İpuçları (CLI ve API Kullanımı):

### CLI Kullanımı:
```bash
# Bilanço Sorusu:
python ask_foundry.py "THYAO bilanço ve borçluluk durumu nasıl?" --company THYAO

# Temettü Sorusu:
python ask_foundry.py "EREGL temettü dağıtacak mı?" --company EREGL

# Yeni İş Sorusu:
python ask_foundry.py "SISE yeni yatırım duyurdu mu?" --company SISE
```

### REST API (FastAPI) Kullanımı:
`POST /api/ask`
```json
{
  "question": "THYAO bilanço ve borçluluk durumu nasıl?",
  "company": "THYAO"
}
```
