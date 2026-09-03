# KAP RAG — Adım Adım Kurulum ve Çalıştırma Tutorialı 🛠️

Bu rehber, **KAP RAG** projesini daha önce hiç görmemiş bir kişinin sıfırdan kendi bilgisayarına kurup çalıştırabilmesi için **adım adım** hazırlanmış kapsamlı bir kılavuzdur.

---

## 💻 1. Sistem Gereksinimleri

Projeyi sorunsuz çalıştırabilmek için aşağıdaki donanım ve yazılımlar gereklidir:

### Donanım Gereksinimleri:
- **İşletim Sistemi:** Windows 10 veya Windows 11 (64-bit)
- **Ekran Kartı (GPU):** NVIDIA GPU (Minimum 6 GB VRAM önerilir - RTX 3050, RTX 4050, RTX 3060 veya üstü)
- **RAM:** Minimum 16 GB Sistem RAM
- **Depolama:** Minimum 5 GB boş SSD alanı

### Yazılım Gereksinimleri:
- **Python:** Python 3.10 veya 3.11 (64-bit)
- **Git:** Sürüm kontrol sistemi
- **Microsoft Foundry Local SDK:** Yerel model yönetimi için CLI aracı

---

## 📥 2. Adım Adım Kurulum

### Adım 1: Depoyu (Repository) Klonlayın veya Proje Klasörüne Gidin

Komut satırını (PowerShell veya CMD) açın ve proje dizinine gidin:

```powershell
cd c:\Users\user\Desktop\kapkann
```

---

### Adım 2: Python Sanal Ortamı (Virtual Environment) Oluşturun

Paket çakışmalarını önlemek için sanal ortam kullanılması önerilir:

```powershell
# Sanal ortam oluştur
python -m venv venv

# Sanal ortamı aktifleştir (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

*(Not: Eğer PowerShell yetki hatası verirse `Set-ExecutionPolicy Unrestricted -Scope Process` komutunu çalıştırabilirsiniz.)*

---

### Adım 3: Gerekli Python Kütüphanelerini Yükleyin

Projenin ihtiyaç duyduğu tüm kütüphaneler `requirements.txt` dosyasında tanımlanmıştır:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

#### `requirements.txt` İçeriği:
```text
foundry-local-sdk-winml
sqlite-vec
numpy
fastapi
uvicorn[standard]
PyMuPDF
requests
```

---

### Adım 4: Microsoft Foundry Local Kurulumu ve Kontrolü

Proje yerel LLM ve Embedding modellerini Microsoft Foundry Local üzerinden çalıştırır.

1. Foundry CLI'nın sisteminizde kurulu ve çalışır durumda olduğunu doğrulayın:
```powershell
foundry status
```

2. Eğer servis çalışmıyorsa başlatın:
```powershell
foundry server start
```

3. Gerekli modellerin Foundry kataloğunda olduğunu kontrol edin:
```powershell
foundry model list
```
Gerekli modeller:
- `phi-4-mini` (Chat LLM modeli)
- `qwen3-embedding-0.6b` (Vektör Embedding modeli)

---

## 🗄️ 3. Veritabanı ve İndeksleme (Sıfırdan İndeks Oluşturma)

Proje dizininde önceden hazırlanmış `kap_vectors.db` (616 MB) veritabanı yer almaktadır. Ancak sıfırdan indeksleme yapmak veya verileri güncellemek isterseniz aşağıdaki adımları izleyebilirsiniz:

### 1. KAP JSON Verilerini İnceleme (İsteğe Bağlı)
`KAP_DATA/` klasöründeki verileri analiz etmek için:
```powershell
python analyze_attachments.py
```

### 2. Metinleri Chunking Yapma ve İndeksleme
Tüm KAP JSON verilerini `sqlite-vec` veritabanına indekslemek için:
```powershell
python index_foundry.py
```
*(Bu işlem 22.701 bildirimi işler ve GPU performansınıza bağlı olarak 10-20 dakika sürebilir.)*

---

## 🚀 4. Projeyi Çalıştırma ve Kullanım

### Seçenek A: Terminal Üzerinden Sorgu Yapma (`ask_foundry.py`)

Tekli sorgular veya testler için CLI motorunu kullanabilirsiniz:

#### 1. Genel Şirket Sorgusu:
```powershell
python ask_foundry.py "THYAO Sidney uçuşları ve filo kararları" --company THYAO
```

#### 2. Otomatik Bilanço Karnesi Sorgusu (Önerilen):
```powershell
python ask_foundry.py "THYAO'nun karnesi nasıl?" --company THYAO
```

#### 3. Banka Bilanço Sorgusu:
```powershell
python ask_foundry.py "AKBNK son finansal rapor özeti" --company AKBNK
```

---

### Seçenek B: REST API Sunucusunu Başlatma (`server.py`)

Dış uygulamalar veya Web Dashboard bağlantıları için API sunucusunu başlatın:

```powershell
python server.py --port 8000
```

Sunucu başladıktan sonra şu adresten erişilebilir:
- **API Base URL:** `http://127.0.0.1:8000`
- **Otomatik Swagger Dokümantasyonu:** `http://127.0.0.1:8000/docs`
- **Sistem Sağlık Kontrolü:** `http://127.0.0.1:8000/api/health`

---

## 🧪 5. API Test Etme Örnekleri

### cURL ile Soru Sorma Testi:

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/ask' \
  -H 'Content-Type: application/json' \
  -d '{
  "question": "THYAO son finansal rapor ve ciro durumu",
  "company": "THYAO",
  "top_k": 4
}'
```

### Python `requests` ile Bağlantı Örneği:

```python
import requests

url = "http://127.0.0.1:8000/api/ask"
payload = {
    "question": "THYAO'nun karnesi nasıl?",
    "company": "THYAO",
    "top_k": 4
}

response = requests.post(url, json=payload)
data = response.json()

print("📝 Cevap:\n", data["answer"])
print("\n📎 Kullanılan Kaynak Sayısı:", data["chunks_used"])
```
