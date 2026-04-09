import queue

# ─── Bağlantı Ayarları ──────────────────────────────────────────────────────
IP                  = "192.168.1.XXX"   # DVR IP adresi
USER                = "admin"            # Kullanıcı adı
PASS                = ""                 # Şifre
PORT                = 554

# ─── Tarama ve Kamera Ayarları ─────────────────────────────────────────────
CHANNELS            = list(range(1, 31))
STREAMS             = [0, 1]

BLACKNESS_THRESHOLD = 15
FRAME_CHECK_COUNT   = 3
CONNECT_TIMEOUT     = 8

# ─── Arayüz ve Görünüm Ayarları ────────────────────────────────────────────
CELL_W, CELL_H      = 320, 180
GRID_COLS           = 4
REFRESH_MS          = 33  # ~30 FPS için (1000/30 ≈ 33ms)

# ─── Performans Ayarları ───────────────────────────────────────────────────
ENABLE_DENOISING    = False   
ENABLE_SHARPENING   = False   
ENABLE_CONTRAST     = False   
BUFFER_SIZE         = 1       
FPS_TARGET          = 30      

# ─── Paylaşılan Kuyruklar ──────────────────────────────────────────────────
log_queue    = queue.Queue()
result_queue = queue.Queue()
