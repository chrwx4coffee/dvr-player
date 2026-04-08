# 📷 DVR Kamera Tarama & Canlı İzleme Aracı

RTSP protokolü üzerinden DVR/NVR sistemlerine bağlanmayı, kanalları taramayı ve canlı görüntü akışını izlemeyi sağlayan Python masaüstü uygulaması.

## Özellikler

- **Kanal Tarama** – Belirtilen kanal aralığında tüm RTSP akışlarını otomatik olarak tarar; görüntü durumu (OK / Siyah / Sinyal Yok / Kararsız) raporlanır
- **Canlı İzleme** – Çalışan kameraları ızgara görünümünde (~30 FPS) eş zamanlı izleme
- **Büyük Ekran** – Herhangi bir kamera görüntüsüne tıklayarak tam ekran izleme
- **Video Kayıt** – Seçili kameradan MP4 formatında kayıt alma (izole kayıt: kayıt sırasında diğer kameralar duraklatılır, ağ yükü azaltılır)
- **Görüntü İyileştirme** – İsteğe bağlı gürültü giderme, keskinleştirme ve kontrast artırma filtreleri
- **Özelleştirilebilir Izgara** – 2×, 3×, 4×, 5×, 6× sütun düzeni desteği

## Gereksinimler

```
Python 3.8+
opencv-python
numpy
Pillow
tkinter  (Python standart kütüphanesi)
```

Bağımlılıkları yüklemek için:

```bash
pip install opencv-python numpy Pillow
```

## Kurulum & Kullanım

1. Depoyu klonlayın:
   ```bash
   git clone https://github.com/KULLANICI_ADINIZ/dvr.git
   cd dvr
   ```

2. `camv2.py` dosyasını açın ve `# AYARLAR` bölümündeki değerleri kendi DVR cihazınıza göre düzenleyin:

   ```python
   IP   = "192.168.1.XXX"  # DVR IP adresi
   USER = "admin"           # Kullanıcı adı
   PASS = ""                # Şifre
   PORT = 554
   ```

3. Uygulamayı başlatın:
   ```bash
   python camv2.py
   ```

## Kullanım Kılavuzu

| Sekme | Açıklama |
|-------|----------|
| 🔍 Tarama | Kanal aralığı ve siyahlık eşiği girerek taramayı başlatın |
| 📺 Canlı İzle | Tarama sonrası "Canlı İzle →" butonuna tıklayın |

- **Kayıt:** Izgara görünümünde kamera kutusunun sağ üst köşesindeki 🔴 butonuna tıklayın  
- **Büyük Ekran:** Kamera görüntüsüne tıklayın  
- **Izgara Düzeni:** Üst çubuktan sütun sayısını seçin (2×–6×)

## Güvenlik Notu



## Lisans

MIT
