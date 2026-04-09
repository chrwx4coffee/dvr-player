#!/usr/bin/env python3
"""
Fabrika Kamera Tarama & Canlı İzleme Aracı - YÜKSEK FPS VERSİYONU
─────────────────────────────────────────────────────────────
"""
import os

# OpenCV'nin RTSP yayınlarını UDP yerine TCP ile çekmesini zorluyoruz
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

from ui import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
