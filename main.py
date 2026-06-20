#!/usr/bin/env python3
"""
Fabrika Kamera Tarama & Canlı İzleme Aracı - YÜKSEK FPS VERSİYONU
─────────────────────────────────────────────────────────────
"""
import os

# FFmpeg ve OpenCV'nin detaylı uyarı loglarını susturarak terminal kirliliğini önlüyoruz
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

# OpenCV'nin RTSP yayınlarını UDP yerine TCP ile çekmesini zorluyoruz
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

from ui import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
