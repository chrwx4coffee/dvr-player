#!/usr/bin/env python3
"""
Fabrika Kamera Tarama & Canlı İzleme Aracı - YÜKSEK FPS VERSİYONU
─────────────────────────────────────────────────────────────
"""

import cv2
import numpy as np
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
import queue
from PIL import Image, ImageTk
import os

# OpenCV'nin RTSP yayınlarını UDP yerine TCP ile çekmesini zorluyoruz
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# ─── AYARLAR ────────────────────────────────────────────────────────────────
# TODO: Aşağıdaki değerleri kendi DVR cihazınıza göre güncelleyin.
IP                  = "192.168.1.XXX"   # DVR IP adresi
USER                = "admin"            # Kullanıcı adı
PASS                = ""                 # Şifre
PORT                = 554
CHANNELS            = list(range(1, 31))
STREAMS             = [0, 1]

BLACKNESS_THRESHOLD = 15
FRAME_CHECK_COUNT   = 3
CONNECT_TIMEOUT     = 8

CELL_W, CELL_H      = 320, 180
GRID_COLS           = 4
REFRESH_MS          = 33  # ~30 FPS için (1000/30 ≈ 33ms)

# Performans ayarları
ENABLE_DENOISING    = False   
ENABLE_SHARPENING   = False   
ENABLE_CONTRAST     = False   
BUFFER_SIZE         = 1       
FPS_TARGET          = 30      
# ─────────────────────────────────────────────────────────────────────────────

log_queue    = queue.Queue()
result_queue = queue.Queue()


def rtsp_url(channel, stream):
    return (
        f"rtsp://{USER}:{PASS}@{IP}:{PORT}"
        f"/user={USER}&password={PASS}"
        f"&channel={channel}&stream={stream}.sdp?real_stream"
    )


def fast_improve_image(frame):
    """HIZLI görüntü iyileştirme - sadece gerekli işlemler"""
    if frame is None:
        return frame
    
    if ENABLE_CONTRAST:
        gamma = 1.2
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        frame = cv2.LUT(frame, table)
    
    if ENABLE_SHARPENING:
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]]) / 1.0
        frame = cv2.filter2D(frame, -1, kernel)
    
    return frame


def is_black_frame(frame, threshold=BLACKNESS_THRESHOLD):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(np.mean(gray))
    return mean < threshold, round(mean, 2)


def check_camera(channel, stream):
    url = rtsp_url(channel, stream)
    result = {"channel": channel, "stream": stream, "url": url,
              "status": "unknown", "brightness": None, "note": ""}

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, CONNECT_TIMEOUT * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, CONNECT_TIMEOUT * 1000)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, BUFFER_SIZE)

    if not cap.isOpened():
        result["status"] = "no_signal"
        result["note"] = "Bağlantı kurulamadı"
        cap.release()
        return result

    black_count, brightness_vals = 0, []
    for _ in range(FRAME_CHECK_COUNT):
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

    if black_count == FRAME_CHECK_COUNT:
        result["status"] = "black"
        result["note"]   = f"Siyah ekran (ort. parlaklık: {avg})"
    elif black_count > 0:
        result["status"] = "intermittent"
        result["note"]   = f"Kararsız sinyal ({black_count}/{FRAME_CHECK_COUNT} siyah frame)"
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


# ════════════════════════════════════════════════════════════════════════════
# OPTİMİZE EDİLMİŞ Canlı kamera worker (Yüksek FPS)
# ════════════════════════════════════════════════════════════════════════════

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
        self.fps = FPS_TARGET
        
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
            blank = np.zeros((CELL_H, CELL_W, 3), dtype=np.uint8)
            cv2.putText(blank, "DURDURULDU", (CELL_W//2 - 60, CELL_H//2), 
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
            cap.set(cv2.CAP_PROP_BUFFERSIZE, BUFFER_SIZE)
            
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
                
                if ENABLE_DENOISING or ENABLE_SHARPENING or ENABLE_CONTRAST:
                    frame = fast_improve_image(frame)
                
                # FPS sırrı: Ana arayüz kasmasın diye resize işlemi Thread içinde yapılıyor! (INTER_NEAREST en hızlısıdır)
                try:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    disp = cv2.resize(rgb, (CELL_W, CELL_H), interpolation=cv2.INTER_NEAREST)
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


# ════════════════════════════════════════════════════════════════════════════
# Ana GUI
# ════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fabrika Kamera Sistemi - Yüksek FPS")
        self.geometry("1280x760")
        self.configure(bg="#0d0d1a")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.stop_event  = threading.Event()
        self.results     = []
        self.ok_results  = []
        self.workers     = {}
        self.selected_cam = None
        self._big_win    = None
        
        # Sadece bir kameradan kayıt almak için global flag
        self.active_recording_cam = None
        
        # FPS göstergesi
        self.fps_counter = 0
        self.last_fps_time = time.time()

        self._build_styles()
        self._build_ui()
        self._poll()

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        BG, FG, ACC = "#0d0d1a", "#e0e0e0", "#00d4ff"
        s.configure("TLabel",      background=BG,       foreground=FG,  font=("Consolas", 10))
        s.configure("TButton",     background="#16213e", foreground=ACC, font=("Consolas", 10, "bold"),
                    borderwidth=1, focusthickness=0)
        s.map("TButton",           background=[("active", "#0f3460")],
                                   foreground=[("disabled", "#555")])
        s.configure("TProgressbar", troughcolor="#16213e", background=ACC)
        s.configure("TNotebook",   background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background="#16213e", foreground=ACC,
                    font=("Consolas", 11, "bold"), padding=[14, 6])
        s.map("TNotebook.Tab",     background=[("selected", "#0f3460")],
              foreground=[("selected", "#ffffff")])
        s.configure("Treeview",    background="#16213e", foreground=FG,
                    fieldbackground="#16213e", rowheight=24, font=("Consolas", 9))
        s.configure("Treeview.Heading", background="#0f3460", foreground=ACC,
                    font=("Consolas", 9, "bold"))
        s.map("Treeview",          background=[("selected", "#0f3460")])

    def _build_ui(self):
        top_bar = tk.Frame(self, bg="#0d0d1a")
        top_bar.pack(fill="x", padx=10, pady=(10, 0))
        
        tk.Label(top_bar, text="📷  Fabrika Kamera Sistemi",
                 font=("Consolas", 16, "bold"), bg="#0d0d1a", fg="#00d4ff").pack(side="left")
        
        self.fps_label = tk.Label(top_bar, text="GUI FPS: --", 
                                  font=("Consolas", 10, "bold"), 
                                  bg="#0d0d1a", fg="#2ecc71")
        self.fps_label.pack(side="right", padx=10)
        
        tk.Label(self, text=f"DVR: {IP}:{PORT}  |  Kullanıcı: {USER}",
                 font=("Consolas", 9), bg="#0d0d1a", fg="#555").pack()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=8)
        self._build_scan_tab()
        self._build_live_tab()

    def _build_scan_tab(self):
        tab = tk.Frame(self.notebook, bg="#0d0d1a")
        self.notebook.add(tab, text="🔍  Tarama")

        cfg = tk.Frame(tab, bg="#0d0d1a")
        cfg.pack(pady=6)
        tk.Label(cfg, text="Kanallar:", bg="#0d0d1a", fg="#aaa").grid(row=0, column=0, padx=4)
        self.ch_var = tk.StringVar(value="1-30")
        tk.Entry(cfg, textvariable=self.ch_var, width=10,
                 bg="#16213e", fg="#00d4ff", insertbackground="#00d4ff").grid(row=0, column=1, padx=4)
        tk.Label(cfg, text="Siyahlık eşiği:", bg="#0d0d1a", fg="#aaa").grid(row=0, column=2, padx=4)
        self.thresh_var = tk.IntVar(value=BLACKNESS_THRESHOLD)
        tk.Spinbox(cfg, from_=0, to=100, textvariable=self.thresh_var, width=5,
                   bg="#16213e", fg="#00d4ff", buttonbackground="#0f3460").grid(row=0, column=3, padx=4)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_lbl = ttk.Label(tab, text="Hazır")
        self.progress_lbl.pack()
        self.progress_bar = ttk.Progressbar(tab, variable=self.progress_var, maximum=100, length=1200)
        self.progress_bar.pack(padx=16, pady=2)

        btn = tk.Frame(tab, bg="#0d0d1a")
        btn.pack(pady=4)
        self.start_btn = ttk.Button(btn, text="▶  Taramayı Başlat", command=self._start)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.stop_btn = ttk.Button(btn, text="■  Durdur", command=self._stop, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=5)
        ttk.Button(btn, text="🔴  Sorunluları Göster", command=self._filter_black).grid(row=0, column=2, padx=5)
        ttk.Button(btn, text="📋  Tümünü Göster",      command=self._filter_all).grid(row=0, column=3, padx=5)
        self.live_btn = ttk.Button(btn, text="📺  Canlı İzle →", command=self._goto_live, state="disabled")
        self.live_btn.grid(row=0, column=4, padx=5)

        tf = tk.Frame(tab, bg="#0d0d1a")
        tf.pack(fill="both", expand=True, padx=16, pady=4)
        cols = ("Kanal", "Stream", "Durum", "Parlaklık", "Not")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=14)
        for c, w in zip(cols, [70, 70, 120, 90, 420]):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center" if c != "Not" else "w")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("ok",          foreground="#2ecc71")
        self.tree.tag_configure("black",        foreground="#e74c3c")
        self.tree.tag_configure("no_signal",    foreground="#7f8c8d")
        self.tree.tag_configure("intermittent", foreground="#f39c12")

        lf = tk.Frame(tab, bg="#0d0d1a")
        lf.pack(fill="x", padx=16, pady=4)
        tk.Label(lf, text="Log:", bg="#0d0d1a", fg="#00d4ff", font=("Consolas", 9, "bold")).pack(anchor="w")
        self.log_box = scrolledtext.ScrolledText(lf, height=6, bg="#080814", fg="#bbb",
                                                 font=("Consolas", 8), state="disabled", wrap="word")
        self.log_box.pack(fill="x")

    def _build_live_tab(self):
        tab = tk.Frame(self.notebook, bg="#080814")
        self.notebook.add(tab, text="📺  Canlı İzle")

        ctrl = tk.Frame(tab, bg="#0d0d1a", pady=4)
        ctrl.pack(fill="x")
        
        tk.Label(ctrl, text="Izgara:", bg="#0d0d1a", fg="#aaa", font=("Consolas", 9)).pack(side="left", padx=8)
        self.grid_cols_var = tk.IntVar(value=GRID_COLS)
        for c in [2, 3, 4, 5, 6]:
            tk.Radiobutton(ctrl, text=f"{c}×", variable=self.grid_cols_var, value=c,
                           bg="#0d0d1a", fg="#00d4ff", selectcolor="#0f3460",
                           font=("Consolas", 9, "bold"),
                           command=self._rebuild_grid).pack(side="left", padx=3)
        ttk.Button(ctrl, text="⟳  Yenile", command=self._rebuild_grid).pack(side="left", padx=10)
        
        self.record_btn = ttk.Button(ctrl, text="🔴  Kayıt Başlat", command=self._start_recording, state="disabled")
        self.record_btn.pack(side="left", padx=5)
        self.stop_record_btn = ttk.Button(ctrl, text="⏹  Kaydı Durdur", command=self._stop_recording, state="disabled")
        self.stop_record_btn.pack(side="left", padx=5)
        
        self.perf_label = tk.Label(ctrl, text="⚡ İzole Kayıt & Multi-Threading Aktif",
                                   bg="#0d0d1a", fg="#2ecc71", font=("Consolas", 8, "bold"))
        self.perf_label.pack(side="left", padx=20)
        
        self.live_status = tk.Label(ctrl, text="— kamera yok —",
                                    bg="#0d0d1a", fg="#555", font=("Consolas", 9))
        self.live_status.pack(side="right", padx=10)

        self.canvas = tk.Canvas(tab, bg="#080814", highlightthickness=0)
        vbar = ttk.Scrollbar(tab, orient="vertical",   command=self.canvas.yview)
        hbar = ttk.Scrollbar(tab, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        hbar.pack(side="bottom", fill="x")
        vbar.pack(side="right",  fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.grid_frame = tk.Frame(self.canvas, bg="#080814")
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.cells = {}

    def _rebuild_grid(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.cells.clear()

        cols = self.grid_cols_var.get()

        if not self.ok_results:
            tk.Label(self.grid_frame,
                     text="Henüz tarama yapılmadı veya çalışan kamera yok.\n",
                     bg="#080814", fg="#555", font=("Consolas", 11)).pack(expand=True, pady=60)
            self.live_status.configure(text="— kamera yok —")
            self.record_btn.configure(state="disabled")
            self.stop_record_btn.configure(state="disabled")
            return

        self.live_status.configure(text=f"{len(self.ok_results)} aktif kamera izleniyor")
        self.record_btn.configure(state="normal")
        self.stop_record_btn.configure(state="normal")

        for idx, res in enumerate(self.ok_results):
            key = (res["channel"], res["stream"])
            row, col = divmod(idx, cols)

            cell = tk.Frame(self.grid_frame, bg="#111122",
                            highlightbackground="#1e2a4a", highlightthickness=1)
            cell.grid(row=row, column=col, padx=2, pady=2)

            img_lbl = tk.Label(cell, bg="#080808", cursor="hand2",
                               width=CELL_W, height=CELL_H)
            img_lbl.configure(width=CELL_W, height=CELL_H)
            img_lbl.pack()

            title_frame = tk.Frame(cell, bg="#0d0d1a")
            title_frame.pack(fill="x")
            
            title_lbl = tk.Label(title_frame,
                                  text=f"CH {res['channel']:02d} | ST {res['stream']}",
                                  bg="#0d0d1a", fg="#00d4ff",
                                  font=("Consolas", 8, "bold"), anchor="w")
            title_lbl.pack(side="left", fill="x", expand=True)
            
            record_cam_btn = tk.Button(title_frame, text="🔴", 
                                       bg="#0d0d1a", fg="#ff4444",
                                       font=("Consolas", 8),
                                       command=lambda k=key: self._toggle_cam_recording(k))
            record_cam_btn.pack(side="right")
            
            # Eğer halihazırda başka kamera kayıt yapıyorsa, bu butonu devre dışı bırak
            if self.active_recording_cam is not None and self.active_recording_cam != key:
                record_cam_btn.configure(state="disabled")
                
            self.cells[key] = {"lbl": img_lbl, "photo": None, "recording": False, "btn": record_cam_btn}

            if key not in self.workers:
                self.workers[key] = CamWorker(res["channel"], res["stream"])

            img_lbl.bind("<Button-1>", lambda e, k=key: self._open_big(k))

    def _toggle_cam_recording(self, key):
        """Tek bir kameranın kaydını başlat/durdur ve DİĞERLERİNİ İPTAL ET"""
        if key not in self.workers:
            return
        
        worker = self.workers[key]
        
        if not worker.is_recording:
            # Başka bir kamera zaten kayıttaysa engelle
            if self.active_recording_cam is not None and self.active_recording_cam != key:
                messagebox.showwarning("Uyarı", "Zaten başka bir kamera kayıt yapıyor. Önce onu durdurun.")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"kamera_ch{key[0]}_st{key[1]}_{timestamp}.mp4"
            
            filepath = filedialog.asksaveasfilename(
                defaultextension=".mp4",
                filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
                initialfile=filename
            )
            
            if filepath:
                self.active_recording_cam = key
                worker.start_recording(filepath)
                
                # Sadece Seçili Kamerayı Açık Tut, Diğer Tüm Kameraları "DURDUR/İPTAL ET"
                for k, w in self.workers.items():
                    if k != key:
                        w.pause()  # RTSP bağlantısını keser, Network ve CPU'yu rahatlatır
                        if k in self.cells:
                            self.cells[k]["btn"].configure(state="disabled")

                if key in self.cells:
                    self.cells[key]["recording"] = True
                    self.cells[key]["btn"].configure(text="⏹", fg="#ffaa00")
                
                # Büyük pencere butonu güncellemesi
                if self._big_win and self.selected_cam == key and hasattr(self, 'big_record_btn'):
                    self.big_record_btn.configure(text="⏹ Kaydı Durdur", fg="#ffaa00")

                self._log(f"İzole Kayıt Başlatıldı. Diğer kameralar duraklatıldı. Dosya: {filepath}")
        else:
            worker.stop_recording()
            self.active_recording_cam = None
            
            # Kayıt bitti, DİĞER KAMERALARI GERİ BAŞLAT
            for k, w in self.workers.items():
                if k != key:
                    w.resume()
                    if k in self.cells:
                        self.cells[k]["btn"].configure(state="normal")
                        
            if key in self.cells:
                self.cells[key]["recording"] = False
                self.cells[key]["btn"].configure(text="🔴", fg="#ff4444")
            
            # Büyük pencere butonu güncellemesi
            if self._big_win and self.selected_cam == key and hasattr(self, 'big_record_btn'):
                self.big_record_btn.configure(text="🔴 Kayıt Başlat", fg="#ff4444")

            self._log(f"Kayıt durduruldu: Kanal {key[0]}. Diğer kameralar aktif ediliyor...")

    def _start_recording(self):
        """Seçili büyük kameranın kaydını başlat"""
        if not self.selected_cam:
            messagebox.showwarning("Uyarı", "Lütfen önce bir kamerayı büyük ekranda açın veya bir kameranın kırmızı butonuna tıklayın!")
            return
        self._toggle_cam_recording(self.selected_cam)
    
    def _stop_recording(self):
        """Aktif kaydı durdur"""
        if self.active_recording_cam:
            self._toggle_cam_recording(self.active_recording_cam)

    def _open_big(self, key):
        self.selected_cam = key
        if self._big_win and self._big_win.winfo_exists():
            self._big_win.lift()
            return
        ch, st = key
        self._big_win = tk.Toplevel(self, bg="#080814")
        self._big_win.title(f"Kanal {ch:02d} | Stream {st} — Canlı (Yüksek FPS)")
        self._big_win.geometry("960x560")
        
        control_bar = tk.Frame(self._big_win, bg="#0d0d1a")
        control_bar.pack(fill="x")
        
        # Eğer bu kamera kayıt yapıyorsa butonu doğru göster
        is_rec = (self.active_recording_cam == key)
        btn_text = "⏹ Kaydı Durdur" if is_rec else "🔴 Kayıt Başlat"
        btn_fg = "#ffaa00" if is_rec else "#ff4444"
        
        self.big_record_btn = tk.Button(control_bar, text=btn_text, 
                                        bg="#0d0d1a", fg=btn_fg,
                                        font=("Consolas", 10, "bold"),
                                        command=lambda: self._toggle_cam_recording(key))
        
        # Eğer BAŞKA kamera kayıt yapıyorsa bu butonu devre dışı bırak
        if self.active_recording_cam is not None and self.active_recording_cam != key:
            self.big_record_btn.configure(state="disabled")
            
        self.big_record_btn.pack(side="left", padx=10, pady=5)
        
        self.big_fps_label = tk.Label(control_bar, text="FPS: --", 
                                      bg="#0d0d1a", fg="#2ecc71",
                                      font=("Consolas", 9, "bold"))
        self.big_fps_label.pack(side="left", padx=10)
        
        tk.Label(control_bar, text=f"CH {ch:02d}  |  Stream {st}  |  {IP}",
                 bg="#0d0d1a", fg="#00d4ff", font=("Consolas", 10)).pack(side="left", padx=20)
        
        self._big_lbl = tk.Label(self._big_win, bg="#080814")
        self._big_lbl.pack(fill="both", expand=True)

        def _close():
            self.selected_cam = None
            self._big_win.destroy()
            self._big_win = None
        self._big_win.protocol("WM_DELETE_WINDOW", _close)

    def _parse_channels(self):
        raw, channels = self.ch_var.get().strip(), []
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")
                channels.extend(range(int(a), int(b) + 1))
            else:
                channels.append(int(part))
        return sorted(set(channels))

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _add_row(self, res):
        icon = {"ok": "✅ OK", "black": "⬛ SİYAH",
                "no_signal": "❌ SİNYAL YOK", "intermittent": "⚠️ KARARSIZ"}.get(res["status"], res["status"])
        brightness = str(res["brightness"]) if res["brightness"] is not None else "-"
        self.tree.insert("", "end",
                         values=(res["channel"], res["stream"], icon, brightness, res["note"]),
                         tags=(res["status"],))

    def _populate_tree(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in results:
            self._add_row(r)

    def _filter_black(self):
        self._populate_tree([r for r in self.results if r["status"] != "ok"])

    def _filter_all(self):
        self._populate_tree(self.results)

    def _start(self):
        try:
            channels = self._parse_channels()
        except Exception as e:
            self._log(f"Kanal hatası: {e}")
            return
        self.results.clear()
        self.ok_results.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress_var.set(0)
        self.stop_event.clear()

        global BLACKNESS_THRESHOLD
        BLACKNESS_THRESHOLD = self.thresh_var.get()

        total = len(channels) * len(STREAMS)
        self.progress_bar.configure(maximum=total)
        self.progress_lbl.configure(text=f"Taranıyor: 0/{total}")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.live_btn.configure(state="disabled")

        threading.Thread(target=scan_all,
                         args=(channels, STREAMS, log_queue, result_queue, self.stop_event),
                         daemon=True).start()

    def _stop(self):
        self.stop_event.set()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._log("⏹ Durduruldu.")

    def _goto_live(self):
        self._rebuild_grid()
        self.notebook.select(1)

    # ── Frame güncelleme (Optimize edilmiş) ─────────────────────────────────

    def _update_cell(self, key, disp_frame):
        cell = self.cells.get(key)
        if not cell:
            return
        try:
            # Artık cv2.resize yok! Direkt Thread'den gelen hazır fotoğrafı basıyoruz.
            photo = ImageTk.PhotoImage(image=Image.fromarray(disp_frame))
            cell["photo"] = photo
            cell["lbl"].configure(image=photo)
        except Exception:
            pass

    def _update_big(self, key, orig_frame):
        if not self._big_win or not self._big_win.winfo_exists():
            return
        if key != self.selected_cam:
            return
        try:
            w = self._big_lbl.winfo_width() or 960
            h = self._big_lbl.winfo_height() or 520
            if w > 10 and h > 10:
                rgb = cv2.cvtColor(orig_frame, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
                photo = ImageTk.PhotoImage(image=Image.fromarray(resized))
                self._big_lbl._photo = photo
                self._big_lbl.configure(image=photo)
            
            if hasattr(self, 'big_fps_label') and key in self.workers:
                worker = self.workers[key]
                if worker.frame_count > 0:
                    fps = worker.fps
                    self.big_fps_label.configure(text=f"FPS: {fps:.1f}")
        except Exception:
            pass

    # ── Polling (Optimize edilmiş) ─────────────────────────────────────────

    def _poll(self):
        while not log_queue.empty():
            msg = log_queue.get_nowait()
            if msg.startswith("__PROGRESS__"):
                done, total = msg.replace("__PROGRESS__", "").split("/")
                self.progress_var.set(int(done))
                self.progress_bar.configure(maximum=int(total))
                self.progress_lbl.configure(text=f"Taranıyor: {done}/{total}")
            elif msg == "__DONE__":
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
                self.progress_lbl.configure(text="✅ Tarama tamamlandı.")
                self._log("=" * 55)
                ok    = sum(1 for r in self.results if r["status"] == "ok")
                black = sum(1 for r in self.results if r["status"] == "black")
                ns    = sum(1 for r in self.results if r["status"] == "no_signal")
                self._log(f"ÖZET → Görüntü var: {ok}  |  Siyah: {black}  |  Sinyal yok: {ns}")
                if ok > 0:
                    self.live_btn.configure(state="normal")
            else:
                self._log(msg)

        while not result_queue.empty():
            res = result_queue.get_nowait()
            self.results.append(res)
            self._add_row(res)
            if res["status"] == "ok":
                self.ok_results.append(res)

        if self.notebook.index("current") == 1:
            for key, worker in list(self.workers.items()):
                # Eğer kamerayı kayıttan dolayı durdurduysak, "DURDURULDU" siyah ekranını alıp basar
                disp_frame = worker.get_display_frame()
                if disp_frame is not None:
                    self._update_cell(key, disp_frame)
                    
                if key == self.selected_cam:
                    orig_frame = worker.get_frame()
                    if orig_frame is not None:
                        self._update_big(key, orig_frame)
            
            self.fps_counter += 1
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                fps = self.fps_counter / (current_time - self.last_fps_time)
                self.fps_label.configure(text=f"GUI FPS: {fps:.1f}")
                self.fps_counter = 0
                self.last_fps_time = current_time

        self.after(REFRESH_MS, self._poll)

    def _on_close(self):
        self.stop_event.set()
        for w in self.workers.values():
            w.stop()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()


