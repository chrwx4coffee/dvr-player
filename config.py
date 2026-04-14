import queue

# ─── Bağlantı Ayarları ──────────────────────────────────────────────────────
IP                  = "192.168.1.XXX"   # DVR IP adresi
USER                = "admin"            # Kullanıcı adı
PASS                = ""                 # Şifre
PORT                = 554
FORCE_TCP           = True             # Bazı eski kameralar RTSP TCP desteklemez, bu nedenle False yapmak garanti çözüm sunar.

# ─── Tarama ve Kamera Ayarları ─────────────────────────────────────────────
CHANNELS            = list(range(1, 9))
STREAMS             = [0, 1]

BLACKNESS_THRESHOLD = 15
FRAME_CHECK_COUNT   = 3
CONNECT_TIMEOUT     = 10    # FFMPEG C++ timeout — yavaş uyanান kameralar için 10sn

# ─── Arayüz ve Görünüm Ayarları ────────────────────────────────────────────
CELL_W, CELL_H      = 320, 180
GRID_COLS           = 4
REFRESH_MS          = 33  # ~30 FPS için (1000/30 ≈ 33ms)

# ─── Performans Ayarları ───────────────────────────────────────────────────
ENABLE_DENOISING    = False   
ENABLE_SHARPENING   = False   
ENABLE_CONTRAST     = False   
GAMMA_VALUE         = 1.2
SHARPEN_VALUE       = 1.0
BUFFER_SIZE         = 1       # 1 = sadece son frame, gecikme/eski frame birikimi yok
FPS_TARGET          = 30      

# ─── Paylaşılan Kuyruklar ──────────────────────────────────────────────────
log_queue    = queue.Queue()
result_queue = queue.Queue()
