"""
Roblox Boss Alarm
Ekrandaki "Rebirth X: Y/Z Bosses" yazısını okur,
Kullanıcının belirlediği boss sayısına ulaşıldığında veya Y == Z olduğunda alarm çalar.
"""

import tkinter as tk
import threading
import time
import re
import winsound
import ctypes
import os
import screen_ocr
from PIL import ImageGrab, Image, ImageTk, ImageEnhance

# ── DPI Awareness ──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────
#  PARSER
# ─────────────────────────────────────────────

PATTERNS = [
    re.compile(r'rebirth\s*\d+[\s\:\-\.\|]*(\d+)\s*[/\\|\s]+(\d+)\s*boss', re.IGNORECASE),
    re.compile(r'(\d+)\s*[/\\|]\s*(\d+)\s*boss', re.IGNORECASE),
    re.compile(r'(\d+)\s*[/\\|]\s*(\d+)', re.IGNORECASE),
]

def parse_boss_text(text: str):
    if not text:
        return None
    
    clean_text = text.lower().replace('\n', ' ')
    for pat in PATTERNS:
        match = pat.search(clean_text)
        if match:
            try:
                curr = int(match.group(1))
                tot = int(match.group(2))
                if curr <= tot and tot > 0:
                    return curr, tot
            except ValueError:
                continue
    return None


# ─────────────────────────────────────────────
#  REGION SELECTOR
# ─────────────────────────────────────────────

class RegionSelector:
    def __init__(self, parent, callback):
        self.callback = callback
        self.start_x_root = self.start_y_root = 0
        self.start_canvas_x = self.start_canvas_y = 0
        self.rect_id = None

        self.win = tk.Toplevel(parent)
        self.win.attributes('-fullscreen', True)
        self.win.attributes('-alpha', 0.35)
        self.win.attributes('-topmost', True)
        self.win.configure(bg='black')

        self.canvas = tk.Canvas(
            self.win, bg='black',
            cursor='crosshair', highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)

        self.canvas.create_text(
            self.win.winfo_screenwidth() // 2, 40,
            text='Yazının ("Rebirth... / Bosses") TAMAMINI içine alacak şekilde kutu çizin (ESC = İptal)',
            fill='#00ffcc', font=('Segoe UI', 16, 'bold')
        )

        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',        self._on_drag)
        self.canvas.bind('<ButtonRelease-1>',  self._on_release)
        self.win.bind('<Escape>', lambda e: self.win.destroy())

    def _on_press(self, event):
        self.start_x_root, self.start_y_root = event.x_root, event.y_root
        self.start_canvas_x, self.start_canvas_y = event.x, event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_canvas_x, self.start_canvas_y, event.x, event.y,
            outline='#00ffcc', width=3,
            fill='#00ffcc', stipple='gray25'
        )

    def _on_release(self, event):
        x1 = min(self.start_x_root, event.x_root)
        y1 = min(self.start_y_root, event.y_root)
        x2 = max(self.start_x_root, event.x_root)
        y2 = max(self.start_y_root, event.y_root)
        self.win.destroy()
        if x2 - x1 > 10 and y2 - y1 > 10:
            self.callback((x1, y1, x2, y2))


# ─────────────────────────────────────────────
#  ALARM
# ─────────────────────────────────────────────

def play_alarm(stop_event: threading.Event):
    while not stop_event.is_set():
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        time.sleep(0.6)


# ─────────────────────────────────────────────
#  OCR VE GÖRÜNTÜ İŞLEME
# ─────────────────────────────────────────────

def preprocess_image(img: Image.Image) -> Image.Image:
    w, h = img.size
    img_resized = img.resize((w * 3, h * 3), Image.LANCZOS)
    gray = img_resized.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    contrast = enhancer.enhance(2.0)
    return contrast

def capture_and_ocr(region, reader) -> tuple[str, Image.Image, Image.Image]:
    x1, y1, x2, y2 = region
    shot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    processed = preprocess_image(shot)
    
    res1 = reader.read_image(shot).as_string()
    res2 = reader.read_image(processed).as_string()
    
    if parse_boss_text(res1):
        return res1, shot, processed
    if parse_boss_text(res2):
        return res2, shot, processed
        
    combined = res1 + " " + res2
    return combined, shot, processed


# ─────────────────────────────────────────────
#  ANA UYGULAMA
# ─────────────────────────────────────────────

class RobloxAlarmApp:
    def __init__(self):
        self.region       = None
        self.running      = False
        self.alarm_active = False
        self.scan_thread  = None
        self.alarm_stop   = threading.Event()
        self.ocr_reader   = screen_ocr.Reader.create_quality_reader()
        self.preview_img  = None
        
        # Canlı Geri Sayım Zamanlayıcısı Değişkenleri
        self.current_remaining = 0.0
        self.timer_thread      = None
        
        self._build_gui()

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title('Roblox Boss Alarm')
        self.root.geometry('520x760')
        self.root.resizable(False, False)
        self.root.configure(bg='#0d1117')

        # Başlık
        tk.Label(
            self.root, text='🎮  Roblox Boss Alarm',
            bg='#0d1117', fg='#00ffcc',
            font=('Segoe UI', 17, 'bold')
        ).pack(pady=(16, 2))

        tk.Label(
            self.root, text='Boss hedefine ulaşıldığında otomatik alarm çalar',
            bg='#0d1117', fg='#8b949e',
            font=('Segoe UI', 10)
        ).pack(pady=(0, 10))

        # ── Bölge kartı ──
        rc = tk.Frame(self.root, bg='#161b22')
        rc.pack(fill='x', padx=20, pady=5)

        tk.Label(rc, text='📍  Ekran Bölgesi ve Canlı Önizleme',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(10,2))

        self.region_var = tk.StringVar(value='Henüz bölge seçilmedi')
        tk.Label(rc, textvariable=self.region_var,
                 bg='#161b22', fg='#00ffcc',
                 font=('Segoe UI', 9)).pack(anchor='w', padx=14, pady=(0,4))

        self.preview_label = tk.Label(rc, bg='#0d1117', text='(Seçilen bölgenin görüntüsü burada görünecek)', fg='#484f58', height=4)
        self.preview_label.pack(fill='x', padx=14, pady=4)

        btn_row = tk.Frame(rc, bg='#161b22')
        btn_row.pack(anchor='w', padx=14, pady=(4,10))

        tk.Button(
            btn_row, text='  🎯 Bölge Seç  ',
            bg='#238636', fg='white', activebackground='#2ea043',
            relief='flat', bd=0, padx=12, pady=6,
            font=('Segoe UI', 9, 'bold'), cursor='hand2',
            command=self._select_region
        ).pack(side='left', padx=(0,8))

        tk.Button(
            btn_row, text='🔬 OCR Anlık Test Et',
            bg='#21262d', fg='#e3b341', activebackground='#30363d',
            relief='flat', bd=0, padx=10, pady=6,
            font=('Segoe UI', 9), cursor='hand2',
            command=self._run_debug
        ).pack(side='left')

        # ── AYARLAR KARTI (Hedef Boss & Süre) ──
        ac = tk.Frame(self.root, bg='#161b22')
        ac.pack(fill='x', padx=20, pady=5)

        tk.Label(ac, text='⚙️  Alarm & Tarama Ayarları',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(8,4))

        target_frame = tk.Frame(ac, bg='#161b22')
        target_frame.pack(fill='x', padx=14, pady=2)

        self.target_mode_var = tk.StringVar(value='auto')

        rb_auto = tk.Radiobutton(
            target_frame, text='Otomatik (Ekrandaki maksimum boss sayısı dolunca: X/X)',
            variable=self.target_mode_var, value='auto',
            bg='#161b22', fg='#c9d1d9', selectcolor='#0d1117',
            activebackground='#161b22', activeforeground='#00ffcc',
            font=('Segoe UI', 9)
        )
        rb_auto.pack(anchor='w')

        custom_row = tk.Frame(target_frame, bg='#161b22')
        custom_row.pack(anchor='w', pady=(2,4))

        rb_custom = tk.Radiobutton(
            custom_row, text='Özel Hedef Boss Sayısı:',
            variable=self.target_mode_var, value='custom',
            bg='#161b22', fg='#c9d1d9', selectcolor='#0d1117',
            activebackground='#161b22', activeforeground='#00ffcc',
            font=('Segoe UI', 9)
        )
        rb_custom.pack(side='left')

        self.target_entry = tk.Entry(
            custom_row, width=6, bg='#0d1117', fg='#00ffcc',
            insertbackground='white', font=('Segoe UI', 10, 'bold'),
            bd=1, relief='solid'
        )
        self.target_entry.insert(0, '19')
        self.target_entry.pack(side='left', padx=6)
        
        tk.Label(custom_row, text='Boss (Örn: 19, 22)', bg='#161b22', fg='#8b949e', font=('Segoe UI', 8)).pack(side='left')

        interval_row = tk.Frame(ac, bg='#161b22')
        interval_row.pack(anchor='w', padx=14, pady=(4,10))

        tk.Label(interval_row, text='⏱️ Tarama Sıklığı:', bg='#161b22', fg='#c9d1d9', font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(0,6))
        
        self.interval_entry = tk.Entry(
            interval_row, width=5, bg='#0d1117', fg='#00ffcc',
            insertbackground='white', font=('Segoe UI', 10, 'bold'),
            bd=1, relief='solid'
        )
        self.interval_entry.insert(0, '10')
        self.interval_entry.pack(side='left', padx=4)

        tk.Label(interval_row, text='saniyede bir tara', bg='#161b22', fg='#8b949e', font=('Segoe UI', 9)).pack(side='left')


        # ── OCR & İLERLEME KARTI ──
        oc = tk.Frame(self.root, bg='#161b22')
        oc.pack(fill='x', padx=20, pady=5)

        tk.Label(oc, text='📖  Okunan Yazı',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(8,2))

        self.ocr_var = tk.StringVar(value='—')
        tk.Label(oc, textvariable=self.ocr_var,
                 bg='#161b22', fg='#e6edf3',
                 font=('Segoe UI', 10, 'bold'),
                 wraplength=450).pack(anchor='w', padx=14, pady=(0,4))

        # --- Boss Progress Bar (Mavi/Cyan) ---
        tk.Label(oc, text='📊  Boss İlerlemesi (X/Y)',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(4,2))

        pb_frame = tk.Frame(oc, bg='#161b22')
        pb_frame.pack(fill='x', padx=14, pady=(0,2))

        self.progress_bg   = tk.Frame(pb_frame, bg='#30363d', height=14)
        self.progress_bg.pack(fill='x', pady=1)
        self.progress_fill = tk.Frame(self.progress_bg, bg='#00ffcc', height=14)
        self.progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0.0)

        self.progress_var = tk.StringVar(value='— / — Bosses')
        tk.Label(oc, textvariable=self.progress_var,
                 bg='#161b22', fg='#8b949e',
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=14, pady=(1,6))


        # --- Canlı Tarama Zamanlayıcısı Barı (YEŞİL CANLI BAR) ---
        tk.Label(oc, text='⏳  Sonraki Taramaya Kalan Süre',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(4,2))

        scan_pb_frame = tk.Frame(oc, bg='#161b22')
        scan_pb_frame.pack(fill='x', padx=14, pady=(0,2))

        self.scan_bg   = tk.Frame(scan_pb_frame, bg='#30363d', height=14)
        self.scan_bg.pack(fill='x', pady=1)
        # YEŞİL RENK (#2ea043)
        self.scan_fill = tk.Frame(self.scan_bg, bg='#2ea043', height=14)
        self.scan_fill.place(x=0, y=0, relheight=1.0, relwidth=1.0)

        self.scan_timer_var = tk.StringVar(value='10.0 sn (Bekliyor)')
        tk.Label(oc, textvariable=self.scan_timer_var,
                 bg='#161b22', fg='#2ea043',
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=14, pady=(1,8))


        # ── Durum ──
        sc = tk.Frame(self.root, bg='#161b22')
        sc.pack(fill='x', padx=20, pady=5)

        tk.Label(sc, text='⚡  Sistem Durumu',
                 bg='#161b22', fg='#c9d1d9',
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(8,2))

        self.status_var = tk.StringVar(value='Bölge seçimi bekleniyor...')
        self.status_lbl = tk.Label(
            sc, textvariable=self.status_var,
            bg='#161b22', fg='#8b949e',
            font=('Segoe UI', 10)
        )
        self.status_lbl.pack(anchor='w', padx=14, pady=(0,8))

        # ── Butonlar ──
        bf = tk.Frame(self.root, bg='#0d1117')
        bf.pack(pady=12)

        self.start_btn = tk.Button(
            bf, text='▶   BAŞLAT',
            bg='#238636', fg='white', activebackground='#2ea043',
            relief='flat', bd=0, padx=24, pady=10,
            font=('Segoe UI', 11, 'bold'), cursor='hand2',
            command=self._start
        )
        self.start_btn.pack(side='left', padx=5)

        self.stop_btn = tk.Button(
            bf, text='⏹   Durdur',
            bg='#21262d', fg='#c9d1d9', activebackground='#30363d',
            relief='flat', bd=0, padx=20, pady=10,
            font=('Segoe UI', 11, 'bold'), cursor='hand2',
            state='disabled', command=self._stop
        )
        self.stop_btn.pack(side='left', padx=5)

        self.mute_btn = tk.Button(
            bf, text='🔇  Sessize Al',
            bg='#da3633', fg='white', activebackground='#b91c1c',
            relief='flat', bd=0, padx=14, pady=10,
            font=('Segoe UI', 11, 'bold'), cursor='hand2',
            state='disabled', command=self._mute_alarm
        )
        self.mute_btn.pack(side='left', padx=5)

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.mainloop()

    def _get_target_boss(self, parsed_total: int) -> int:
        mode = self.target_mode_var.get()
        if mode == 'custom':
            try:
                val = int(self.target_entry.get().strip())
                if val > 0:
                    return val
            except ValueError:
                pass
        return parsed_total

    def _get_scan_interval(self) -> float:
        try:
            val = float(self.interval_entry.get().strip())
            if val >= 1:
                return val
        except ValueError:
            pass
        return 10.0

    # ── Bölge seç ────────────────────────────

    def _select_region(self):
        self.root.withdraw()
        time.sleep(0.2)
        RegionSelector(self.root, self._on_region_selected)

    def _on_region_selected(self, region):
        self.root.deiconify()
        self.region = region
        x1, y1, x2, y2 = region
        self.region_var.set(f'x:{x1} y:{y1} → x:{x2} y:{y2} ({x2-x1}×{y2-y1}px)')
        self._update_preview()
        self._set_status('Bölge seçildi. Test yapabilir veya Başlatabilirsiniz.', '#3fb950')

    def _update_preview(self, img=None):
        if not self.region:
            return
        if img is None:
            x1, y1, x2, y2 = self.region
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        
        w, h = img.size
        target_h = 70
        if h > 0:
            target_w = int(w * (target_h / h))
            img_thumb = img.resize((min(target_w, 460), target_h), Image.LANCZOS)
            self.preview_img = ImageTk.PhotoImage(img_thumb)
            self.preview_label.config(image=self.preview_img, text='', height=target_h)

    # ── OCR Debug ────────────────────────────

    def _run_debug(self):
        if not self.region:
            self._set_status('⚠ Önce "Bölge Seç" butonuna basıp alanı seçin!', '#f85149')
            return

        self._set_status('🔬 OCR Okuma testi yapılıyor...', '#e3b341')

        def do_debug():
            try:
                text, shot, processed = capture_and_ocr(self.region, self.ocr_reader)

                shot.save(os.path.join(SCRIPT_DIR, 'debug_capture.png'))
                processed.save(os.path.join(SCRIPT_DIR, 'debug_processed.png'))
                
                with open(os.path.join(SCRIPT_DIR, 'debug_ocr.txt'), 'w', encoding='utf-8') as f:
                    f.write(f'Okunan Metin: {text}\nParse: {parse_boss_text(text)}')

                result = parse_boss_text(text)
                
                self.root.after(0, self._update_preview, shot)
                self.root.after(0, self._update_display, text, result)

                if result:
                    curr, tot = result
                    target = self._get_target_boss(tot)
                    self.root.after(0, self._set_status, f'✅ OKUNDU: {curr}/{tot} Boss (Hedef: {target})', '#3fb950')
                else:
                    self.root.after(0, self._set_status, f'❌ Metin okundu ama parse edilemedi ("{text.strip()}")', '#f85149')

            except Exception as e:
                self.root.after(0, self._set_status, f'Hata: {e}', '#f85149')

        threading.Thread(target=do_debug, daemon=True).start()

    # ── Başlat / Durdur ──────────────────────

    def _start(self):
        if not self.region:
            self._set_status('⚠ Önce ekran bölgesi seçin!', '#f85149')
            return

        self.running      = True
        self.alarm_active = False
        self.alarm_stop.set()

        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.mute_btn.config(state='disabled')
        interval = self._get_scan_interval()
        self._set_status(f'🔍 Taranıyor... (Her {interval:.0f} saniyede bir)', '#58a6ff')

        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()

    def _stop(self):
        self.running = False
        self._mute_alarm()
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.mute_btn.config(state='disabled')
        
        # Geri sayım barını sıfırla
        self.scan_fill.place(relwidth=0.0)
        self.scan_timer_var.set('Durduruldu')
        self._set_status('Durduruldu.', '#8b949e')

    def _mute_alarm(self):
        self.alarm_stop.set()
        self.alarm_active = False
        self.mute_btn.config(state='disabled')
        self.root.configure(bg='#0d1117')

    # ── Tarama döngüsü ───────────────────────

    def _scan_loop(self):
        while self.running:
            total_interval = self._get_scan_interval()
            start_time = time.time()
            
            # Anlık OCR Okuması Yap
            try:
                text, shot, _ = capture_and_ocr(self.region, self.ocr_reader)
                result = parse_boss_text(text)
                
                self.root.after(0, self._update_display, text, result)
                self.root.after(0, self._update_preview, shot)

                if result:
                    current, parsed_total = result
                    target_boss = self._get_target_boss(parsed_total)
                    
                    if current >= target_boss and target_boss > 0 and not self.alarm_active:
                        self.alarm_active = True
                        self.root.after(0, self._trigger_alarm, current, target_boss)

            except Exception as e:
                self.root.after(0, self._set_status, f'Hata: {e}', '#f85149')

            # --- Canlı Yeşil Geri Sayım Döngüsü (Pürüzsüz 0.1s güncellemeli) ---
            while self.running:
                elapsed = time.time() - start_time
                remaining = max(0.0, total_interval - elapsed)
                ratio = remaining / total_interval if total_interval > 0 else 0
                
                self.root.after(0, self._update_scan_bar, remaining, ratio)
                
                if remaining <= 0:
                    break
                time.sleep(0.1)

    def _update_scan_bar(self, remaining: float, ratio: float):
        if self.running:
            self.scan_fill.place(relwidth=ratio)
            self.scan_timer_var.set(f'⏳ Sonraki taramaya: {remaining:.1f} sn')

    # ── UI güncellemeleri ────────────────────

    def _update_display(self, raw: str, result):
        clean = raw.strip().replace('\n', ' | ')
        self.ocr_var.set(clean if clean else '(metin okunamadı)')

        if result:
            current, parsed_total = result
            target_boss = self._get_target_boss(parsed_total)
            
            self.progress_var.set(f'{current} / {target_boss} Boss (Ekrandaki Toplam: {parsed_total})')
            ratio = min(current / target_boss, 1.0) if target_boss > 0 else 0
            self.progress_fill.place(relwidth=ratio)
            
            if current >= target_boss:
                self.progress_fill.config(bg='#f85149')
                self._set_status(f'🔔 ALARM! Hedefe Ulaşıldı ({current}/{target_boss})!', '#f85149')
            else:
                self.progress_fill.config(bg='#00ffcc')
                interval = self._get_scan_interval()
                self._set_status(f'🔍 Taranıyor... ({current}/{target_boss} Boss — {interval:.0f}s)', '#58a6ff')
        else:
            if self.running:
                interval = self._get_scan_interval()
                self._set_status(f'🔍 Taranıyor... (Metin okunamadı — {interval:.0f}s)', '#8b949e')

    def _trigger_alarm(self, current: int, target: int):
        self._set_status(f'🔔 ALARM! Hedef Boss Tamamlandı ({current}/{target})!', '#f85149')
        self.mute_btn.config(state='normal')
        self.alarm_stop.clear()
        threading.Thread(target=play_alarm, args=(self.alarm_stop,), daemon=True).start()
        self._flash_window()

    def _flash_window(self, count=0):
        if self.alarm_stop.is_set() or count > 20:
            self.root.configure(bg='#0d1117')
            return
        color = '#4a0404' if count % 2 == 0 else '#0d1117'
        self.root.configure(bg=color)
        self.root.after(400, self._flash_window, count + 1)

    def _set_status(self, msg: str, color: str = '#8b949e'):
        self.status_var.set(msg)
        self.status_lbl.config(fg=color)

    def _on_close(self):
        self.running = False
        self.alarm_stop.set()
        self.root.destroy()


if __name__ == '__main__':
    RobloxAlarmApp()
