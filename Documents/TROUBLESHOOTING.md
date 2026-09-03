# KAP RAG — Hatalar ve Çözüm Yolları (Troubleshooting) ❓

Bu doküman, **KAP RAG** projesinin kurulumu, çalıştırılması veya geliştirilmesi sırasında karşılaşılabilecek olası hataları ve bunların kesin çözüm adımlarını içerir.

---

## 🚨 1. Donanım ve GPU Bellek (VRAM) Hataları

### Hata: `InternalServerError: Error code: 500 - Failed to allocate memory ... BFCArena::AllocateRawInternal`

#### Nedeni:
Ekran kartının VRAM kapasitesi (örn: 6 GB RTX 4050) dolmuştur. Bu durum genellikle aynı anda hem Embedding hem de Chat LLM modeli bellekte tutulduğunda veya LLM'e iletilen metin bağlamı (context) çok uzun olduğunda yaşanır.

#### Çözüm Adımları:
1. Foundry belleğindeki tüm modelleri temizleyin:
```powershell
foundry model unload phi-4-mini
foundry model unload qwen3-embedding-0.6b
```
2. Eğer sorun devam ederse Foundry sunucusunu yeniden başlatın:
```powershell
foundry server stop
foundry server start
```
3. `ask_foundry.py` veya `server.py` içerisinde `top_k` değerini maksimum 4 veya 5 chunk ile sınırlayın.

---

### Hata: `BadRequestError: Error code: 400 - Model 'qwen3-embedding-0.6b' is not loaded`

#### Nedeni:
Foundry Local servisinden embedding vektörü istenmiş ancak `qwen3-embedding-0.6b` modeli GPU belleğine yüklenmemiştir.

#### Çözüm Adımları:
1. Modeli manuel olarak yükleyin:
```powershell
foundry model load qwen3-embedding-0.6b
```
2. `ask_foundry.py` veya `server.py` kodunda `client.embeddings.create` çağrılmadan önce `subprocess.run(["foundry", "model", "load", EMBEDDING_MODEL])` komutunun çalıştığından emin olun.

---

## 🔤 2. Kodlama ve Türkçe Karakter Hataları

### Hata: `UnicodeEncodeError: 'charmap' codec can't encode character ...`

#### Nedeni:
Windows varsayılan CMD/PowerShell terminal kodlaması (`CP1254` veya `CP1252`) Türkçe karakterleri yazdırırken hata verir.

#### Çözüm Adımları:
1. Python komutunu çalıştırırken `-X utf8` bayrağını ekleyin:
```powershell
python -X utf8 ask_foundry.py "THYAO karnesi" --company THYAO
```
2. Veya PowerShell ortam kodlamasını UTF-8 olarak ayarlayın:
```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
```

---

## 🗄️ 3. Veritabanı ve sqlite-vec Hataları

### Hata: `sqlite3.OperationalError: no such module: vec0` veya `sqlite_vec load error`

#### Nedeni:
`sqlite-vec` Python eklentisi yüklenememiştir veya veritabanı bağlantısında `enable_load_extension` çağrısı yapılmamıştır.

#### Çözüm Adımları:
1. `sqlite-vec` paketinin yüklü olduğunu doğrulayın:
```powershell
pip install --force-reinstall sqlite-vec
```
2. Kod içerisinde veritabanı açılırken şu sıranın izlendiğinden emin olun:
```python
import sqlite3
import sqlite_vec

db = sqlite3.connect("kap_vectors.db")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)
```

---

## 🌐 4. Sunucu ve Bağlantı Hataları

### Hata: `openai.APIConnectionError / httpx2.ConnectError: [WinError 10061] Hedef makine etkin olarak reddettiğinden bağlantı kurulamadı`

#### Nedeni:
Microsoft Foundry Local servisi yeniden başlatıldığında port numarası dinamik olarak değişmiştir (örneğin `51667` yerine `59812` portu açılmıştır) veya Foundry servisi kapalıdır.

#### Çözüm Adımları:
1. Foundry servisinin çalıştığından emin olun ve aktif portu görün:
```powershell
foundry status
```
2. Eğer servis kapalıysa başlatın:
```powershell
foundry server start
```
3. `ask_foundry.py` ve `server.py` içerisinde `get_foundry_base_url()` fonksiyonu Windows dinamik port tespitine sahiptir (`shell=True` ile aktif port olan `http://127.0.0.1:59812/v1` adresini otomatik yakalar).
