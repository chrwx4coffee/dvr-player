import cv2
import numpy as np
import threading
import time
from datetime import datetime
import config

def rtsp_url(channel, stream):
    return (
        f"rtsp://{config.USER}:{config.PASS}@{config.IP}:{config.PORT}"
        f"/user={config.USER}&password={config.PASS}"
        f"&channel={channel}&stream={stream}.sdp?real_stream"
    )

def fast_improve_image(frame):
    """HIZLI görüntü iyileştirme - sadece gerekli işlemler"""
    if frame is None:
        return frame
    
    if config.ENABLE_CONTRAST:
        gamma = config.GAMMA_VALUE
        if gamma <= 0.1: 
            gamma = 0.1
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        frame = cv2.LUT(frame, table)
    
    if config.ENABLE_SHARPENING:
        alpha = config.SHARPEN_VALUE
        kernel = np.array([[0, -alpha, 0], [-alpha, 1 + 4*alpha, -alpha], [0, -alpha, 0]])
        frame = cv2.filter2D(frame, -1, kernel)
    
    return frame

def is_black_frame(frame, threshold=None):
    if threshold is None:
        threshold = config.BLACKNESS_THRESHOLD
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(np.mean(gray))
    return mean < threshold, round(mean, 2)

def check_camera(channel, stream):
    url = rtsp_url(channel, stream)
    result = {"channel": channel, "stream": stream, "url": url,
              "status": "unknown", "brightness": None, "note": ""}

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, config.CONNECT_TIMEOUT * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, config.CONNECT_TIMEOUT * 1000)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, config.BUFFER_SIZE)

    if not cap.isOpened():
        result["status"] = "no_signal"
        result["note"] = "Bağlantı kurulamadı"
        cap.release()
        return result

    black_count, brightness_vals = 0, []
    for _ in range(config.FRAME_CHECK_COUNT):
        ret, frame = cap.read()
        if not ret or frame is None:
            black_count += 1
            continue
        is_black, brightness = is_black_frame(frame)
        brightness_vals.append(brightness)
        if is_black:
            black_count += 1
    cap.release()

    avg = round(sum(brightness_vals) / len(brightness_vals), 2) if brightness_vals else 0.0
    result["brightness"] = avg

    if black_count == config.FRAME_CHECK_COUNT:
        result["status"] = "black"
        result["note"]   = f"Siyah ekran (ort. parlaklık: {avg})"
    elif black_count > 0:
        result["status"] = "intermittent"
        result["note"]   = f"Kararsız sinyal ({black_count}/{config.FRAME_CHECK_COUNT} siyah frame)"
    else:
        result["status"] = "ok"
        result["note"]   = f"Görüntü var (ort. parlaklık: {avg})"
    return result

def scan_all(channels, streams, log_q, result_q, stop_event):
    total, done = len(channels) * len(streams), 0
    for ch in channels:
        if stop_event.is_set():
            break
        for st in streams:
            if stop_event.is_set():
                break
            log_q.put(f"[{datetime.now().strftime('%H:%M:%S')}] Deneniyor → Kanal {ch}, Stream {st}...")
            res = check_camera(ch, st)
            icon = {"ok": "✅", "black": "⬛", "no_signal": "❌", "intermittent": "⚠️"}.get(res["status"], "❓")
            log_q.put(f"{icon} Kanal {ch:02d} | Stream {st} | {res['status'].upper()} | {res['note']}")
            result_q.put(res)
            done += 1
            log_q.put(f"__PROGRESS__{done}/{total}")
    log_q.put("__DONE__")


class CamWorker:
    def __init__(self, channel, stream):
        self.channel = channel
        self.stream  = stream
        self.url     = rtsp_url(channel, stream)
        self._frame  = None
        self._display_frame = None  # Tkinter için hazır resize edilmiş frame
        self._lock   = threading.Lock()
        self._stop   = threading.Event()
        self.paused  = False  # Diğer kamera kayıt yaparken durdurmak için
        
        # Kayıt değişkenleri
        self.is_recording = False
        self.video_writer = None
        self.record_filename = ""
        self.fps = config.FPS_TARGET
        
        # Performans için frame buffer
        self.frame_count = 0
        self.last_time = time.time()
        
        threading.Thread(target=self._run, daemon=True).start()

    def start_recording(self, filename):
        self.record_filename = filename
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None

    def pause(self):
        """Kamera akışını durdur ve ağı serbest bırak"""
        self.paused = True
        with self._lock:
            # Siyah ekran ve bilgi metni oluştur
            blank = np.zeros((config.CELL_H, config.CELL_W, 3), dtype=np.uint8)
            cv2.putText(blank, "DURDURULDU", (config.CELL_W//2 - 60, config.CELL_H//2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 255), 2)
            self._display_frame = blank

    def resume(self):
        """Kamera akışını tekrar başlat"""
        self.paused = False

    def _run(self):
        while not self._stop.is_set():
            if self.paused:
                time.sleep(0.2) # Paused ise bağlantı kurmaya çalışma, bekle
                continue
                
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            
            # KRİTİK: Performans için optimize edilmiş capture ayarları
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, config.BUFFER_SIZE)
            
            if not cap.isOpened():
                time.sleep(1)
                continue
            
            real_fps = cap.get(cv2.CAP_PROP_FPS)
            if real_fps > 0 and real_fps < 100:
                self.fps = real_fps
            
            frame_time = 1.0 / self.fps
            last_frame_time = time.time()
            
            while not self._stop.is_set() and not self.paused:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if config.ENABLE_DENOISING or config.ENABLE_SHARPENING or config.ENABLE_CONTRAST:
                    frame = fast_improve_image(frame)
                
                # FPS sırrı: Ana arayüz kasmasın diye resize işlemi Thread içinde yapılıyor!
                try:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    disp = cv2.resize(rgb, (config.CELL_W, config.CELL_H), interpolation=cv2.INTER_NEAREST)
                except Exception:
                    disp = None

                with self._lock:
                    self._frame = frame
                    self._display_frame = disp

                # Kayıt işlemi
                if self.is_recording:
                    if self.video_writer is None:
                        h, w = frame.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        self.video_writer = cv2.VideoWriter(
                            self.record_filename, fourcc, self.fps, (w, h)
                        )
                    self.video_writer.write(frame)
                
                current_time = time.time()
                elapsed = current_time - last_frame_time
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)
                last_frame_time = current_time
                
                self.frame_count += 1
                if self.frame_count % self.fps == 0:
                    now = time.time()
                    self.last_time = now

            # Eğer paused olduysa bağlantıyı TAMAMEN kopar ki network rahatlasın!
            cap.release()
            if self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None

            if not self._stop.is_set():
                time.sleep(0.5)

    def get_display_frame(self):
        """Tkinter grid'i için optimize edilmiş frame"""
        with self._lock:
            return self._display_frame.copy() if self._display_frame is not None else None

    def get_frame(self):
        """Orijinal boyuttaki frame (Büyük pencere için)"""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        self._stop.set()
        self.stop_recording()
