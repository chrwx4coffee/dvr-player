import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageTk
import threading
import time
import cv2
import socket


import config
from camera import CamWorker, scan_all

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
        
        conn_frame = tk.Frame(self, bg="#0d0d1a")
        conn_frame.pack(fill="x", padx=10, pady=(5, 5))
        
        tk.Label(conn_frame, text="IP:", bg="#0d0d1a", fg="#aaa").pack(side="left")
        self.ip_var = tk.StringVar(value=config.IP)
        tk.Entry(conn_frame, textvariable=self.ip_var, width=15, bg="#16213e", fg="#00d4ff").pack(side="left", padx=5)
        
        tk.Label(conn_frame, text="Port:", bg="#0d0d1a", fg="#aaa").pack(side="left")
        self.port_var = tk.StringVar(value=str(config.PORT))
        tk.Entry(conn_frame, textvariable=self.port_var, width=6, bg="#16213e", fg="#00d4ff").pack(side="left", padx=5)
        
        tk.Label(conn_frame, text="Kullanıcı:", bg="#0d0d1a", fg="#aaa").pack(side="left")
        self.user_var = tk.StringVar(value=config.USER)
        tk.Entry(conn_frame, textvariable=self.user_var, width=10, bg="#16213e", fg="#00d4ff").pack(side="left", padx=5)
        
        tk.Label(conn_frame, text="Şifre:", bg="#0d0d1a", fg="#aaa").pack(side="left")
        self.pass_var = tk.StringVar(value=config.PASS)
        tk.Entry(conn_frame, textvariable=self.pass_var, width=10, bg="#16213e", fg="#00d4ff", show="*").pack(side="left", padx=5)
        
        def save_config():
            config.IP = self.ip_var.get()
            try:
                config.PORT = int(self.port_var.get())
            except ValueError:
                pass
            config.USER = self.user_var.get()
            config.PASS = self.pass_var.get()
            messagebox.showinfo("Bilgi", "Bağlantı ayarları kaydedildi.")

        ttk.Button(conn_frame, text="💾 Kaydet", command=save_config).pack(side="left", padx=10)

        def find_camera():
            self.find_cam_btn.configure(state="disabled", text="Taranıyor...")
            threading.Thread(target=self._scan_ports_thread, daemon=True).start()

        self.find_cam_btn = ttk.Button(conn_frame, text="🔍 Kamera Bul", command=find_camera)
        self.find_cam_btn.pack(side="left", padx=5)

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
        self.thresh_var = tk.IntVar(value=config.BLACKNESS_THRESHOLD)
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
        self.grid_cols_var = tk.IntVar(value=config.GRID_COLS)
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

        effects_frame = tk.Frame(tab, bg="#111122", pady=4)
        effects_frame.pack(fill="x")
        
        tk.Label(effects_frame, text="✨ Kalite:", bg="#111122", fg="#00d4ff", font=("Consolas", 9, "bold")).pack(side="left", padx=8)

        def set_mode(mode):
            if mode == "max_fps":
                config.ENABLE_SHARPENING = False
                config.ENABLE_CONTRAST = False
            elif mode == "balanced":
                config.ENABLE_SHARPENING = True
                config.ENABLE_CONTRAST = True
                self.sharpen_scale.set(0.5)
                self.gamma_scale.set(1.2)
            elif mode == "max_quality":
                config.ENABLE_SHARPENING = True
                config.ENABLE_CONTRAST = True
                self.sharpen_scale.set(1.5)
                self.gamma_scale.set(0.9)
            update_sliders()

        def update_sliders(*args):
            config.SHARPEN_VALUE = float(self.sharpen_scale.get())
            config.GAMMA_VALUE = float(self.gamma_scale.get())

        ttk.Button(effects_frame, text="🚀 Maks FPS", command=lambda: set_mode("max_fps")).pack(side="left", padx=3)
        ttk.Button(effects_frame, text="⚖️ Orta", command=lambda: set_mode("balanced")).pack(side="left", padx=3)
        ttk.Button(effects_frame, text="🌟 Maks Kalite", command=lambda: set_mode("max_quality")).pack(side="left", padx=3)

        tk.Label(effects_frame, text="Netlik:", bg="#111122", fg="#aaa").pack(side="left", padx=(15, 2))
        self.sharpen_scale = ttk.Scale(effects_frame, from_=0.0, to=3.0, orient="horizontal", command=update_sliders)
        self.sharpen_scale.set(config.SHARPEN_VALUE)
        self.sharpen_scale.pack(side="left", padx=2)

        tk.Label(effects_frame, text="Kontrast:", bg="#111122", fg="#aaa").pack(side="left", padx=(15, 2))
        self.gamma_scale = ttk.Scale(effects_frame, from_=0.5, to=3.0, orient="horizontal", command=update_sliders)
        self.gamma_scale.set(config.GAMMA_VALUE)
        self.gamma_scale.pack(side="left", padx=2)

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
                               width=config.CELL_W, height=config.CELL_H)
            img_lbl.configure(width=config.CELL_W, height=config.CELL_H)
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
        
        tk.Label(control_bar, text=f"CH {ch:02d}  |  Stream {st}  |  {config.IP}",
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

        config.BLACKNESS_THRESHOLD = self.thresh_var.get()

        total = len(channels) * len(config.STREAMS)
        self.progress_bar.configure(maximum=total)
        self.progress_lbl.configure(text=f"Taranıyor: 0/{total}")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.live_btn.configure(state="disabled")

        threading.Thread(target=scan_all,
                         args=(channels, config.STREAMS, config.log_queue, config.result_queue, self.stop_event),
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
        while not config.log_queue.empty():
            msg = config.log_queue.get_nowait()
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

        while not config.result_queue.empty():
            res = config.result_queue.get_nowait()
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

        self.after(config.REFRESH_MS, self._poll)

    def _scan_ports_thread(self):
        target_ip = self.ip_var.get()
        ports_to_test = [80, 554, 8000, 8080, 34567, 37777]
        open_ports = []
        
        config.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Kamera port taraması başlatıldı: {target_ip}")
        for port in ports_to_test:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                res = s.connect_ex((target_ip, port))
                if res == 0:
                    open_ports.append(port)
                    config.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ PORT AÇIK: {port}")
                s.close()
            except Exception as e:
                pass

        config.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Port taraması bitti. Açık portlar: {open_ports}")
        
        def _restore_button():
            self.find_cam_btn.configure(state="normal", text="🔍 Kamera Bul")
            if open_ports:
                msg = f"Aygıt {target_ip} üzerinde açık portlar bulundu:\n\n" + ", ".join(map(str, open_ports))
                messagebox.showinfo("Kamera Bulundu", msg)
            else:
                messagebox.showwarning("Bulunamadı", f"{target_ip} üzerinde hiçbir test portu açık değil.")
                
        self.after(100, _restore_button)

    def _on_close(self):
        self.stop_event.set()
        for w in self.workers.values():
            w.stop()
        self.destroy()

