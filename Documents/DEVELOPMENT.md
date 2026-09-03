# KAP RAG — Geliştirme ve Teknik Detaylar 💻

Bu doküman, **KAP RAG** projesini geliştirmeye devam edecek mühendisler ve geliştiriciler için mimari kuralları, teknik püf noktalarını ve gelecek yol haritasını (roadmap) içerir.

---

## 🛠️ Temel Mühendislik Kuralları

Projeyi geliştirirken aşağıdaki kurallara kesinlikle uyulmalıdır:

### 1. VRAM Sıfırlama ve Model Offloading Kuralı
NVIDIA RTX 4050 (6 GB VRAM) ekran kartında bellek taşmalarını (`ONNX Runtime BFCArena Allocation Error`) engellemek için:
- **Embedding Yükleme/Boşaltma:** Embedding modeli (`qwen3-embedding-0.6b`) sadece vektör oluşturulurken yüklenmeli, vektör alındığı an `foundry model unload qwen3-embedding-0.6b` ile bellekten atılmalıdır.
- **Context Uzunluğu Sınırı:** LLM'e iletilen metin bağlamı 4 chunk'ı (~3.500 karakter) geçmemelidir. Metin uzadıkça KV-Cache bellek kullanımı katlanarak artar.

### 2. Finansal Doğruluk Kuralı (Zero Hallucination)
- LLM'in finansal tablolardaki sayıları uydurmasını engellemek için `SYSTEM_PROMPT` içerisinde kesinlikle hardcoded varsayılan sayısal örnekler verilmemelidir.
- Gerçek veriler SQLite veritabanından `extract_real_financial_facts` fonksiyonu ile ayıklanarak ham text olarak bağlama eklenmelidir.

### 3. Windows UTF-8 Kodlama Kuralı
Windows konsolunda Türkçe karakterlerin (`ş, ğ, ç, ı, ö, ü`) bozulmaması için Python komutları çalıştırılırken `-X utf8` parametresi tercih edilmelidir:
```powershell
python -X utf8 ask_foundry.py "THYAO karnesi" --company THYAO
```

---

## 🔄 Yeni Şirket veya Bildirim Ekleme Geliştirmesi

Yeni bir şirkete ait KAP JSON bildirimleri eklendiğinde izlenecek adımlar:

1. `KAP_DATA/<YENI_SIRKET_KODU>/` klasörünü oluşturun ve JSON dosyalarını ekleyin.
2. İndeksleme betiğini çalıştırın:
```powershell
python index_foundry.py
```
`index_foundry.py` veritabanında daha önce eklenmiş olan bildirimleri korur ve yalnızca yeni verileri `sqlite-vec` veritabanına ekler.

---

## 🚀 Gelecek Yol Haritası (Roadmap) ve Eksik Kalan Noktalar

### Faz 2: PDF Eklerinin Derinlemesine İndekslenmesi
- **Mevcut Durum:** Projede 12.344 adet PDF ekinin metadata bilgileri taranmıştır (`analyze_attachments.py`).
- **Geliştirme Planı:** `PyMuPDF` (`fitz`) kütüphanesi kullanılarak PDF dosyaları içerisindeki metinler ve finansal dipnotlar okunup `source_type = 'pdf_attachment'` olarak `kap_vectors.db` veritabanına eklenecektir.

### Faz 3: Web Dashboard & Visual Charting
- **Mevcut Durum:** `server.py` FastAPI REST API servisi hazırdır.
- **Geliştirme Planı:** React.js veya Vue.js tabanlı modern bir Web Arayüzü hazırlanarak `/api/ask` endpoint'inden gelen Karne ve Trend verileri Recharts/Chart.js ile görsel grafiklere dönüştürülecektir.
