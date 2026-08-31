"""Analyze attachment statistics across all KAP_DATA JSON files."""
import json, os
from collections import Counter, defaultdict

data_dir = os.path.join(os.path.dirname(__file__), "KAP_DATA")

total_files = 0
files_with_attachments = 0
total_attachments = 0
ext_counter = Counter()
ext_combo_counter = Counter()
attachment_sizes = []
sample_per_ext = defaultdict(list)

for company_dir in os.listdir(data_dir):
    company_path = os.path.join(data_dir, company_dir)
    if not os.path.isdir(company_path):
        continue
    for fname in os.listdir(company_path):
        if not fname.endswith(".json"):
            continue
        total_files += 1
        fpath = os.path.join(company_path, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                continue
        atts = data.get("attachments", [])
        if atts:
            files_with_attachments += 1
            total_attachments += len(atts)
            exts = sorted(set(a.get("extension", "?") for a in atts))
            ext_combo = ",".join(exts)
            ext_combo_counter[ext_combo] += 1
            for a in atts:
                ext = a.get("extension", "?")
                ext_counter[ext] += 1
                if len(sample_per_ext[ext]) < 2:
                    sample_per_ext[ext].append({
                        "company": data.get("company"),
                        "filename": a.get("filename"),
                        "url": a.get("url"),
                        "bildirim_url": data.get("url"),
                    })

print(f"Toplam JSON dosya: {total_files}")
print(f"Attachment'lı bildirim: {files_with_attachments} ({files_with_attachments/total_files*100:.1f}%)")
print(f"Toplam attachment sayısı: {total_attachments}")
print()
print("=== Dosya Uzantılarına Göre Dağılım ===")
for ext, cnt in ext_counter.most_common():
    print(f"  .{ext}: {cnt} dosya")
print()
print("=== Uzantı Kombinasyonları ===")
for combo, cnt in ext_combo_counter.most_common(10):
    print(f"  [{combo}]: {cnt} bildirim")
print()
print("=== Örnek Dosyalar (her uzantıdan 2) ===")
for ext, samples in sample_per_ext.items():
    print(f"\n  .{ext}:")
    for s in samples:
        print(f"    {s['company']} - {s['filename']}")
        print(f"    URL: {s['url']}")
