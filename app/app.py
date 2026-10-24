"""Antarmuka Tkinter. Seluruh pembaruan widget terjadi di thread utama."""

import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .logic import ALERT_MESSAGE
from .worker import MODEL_PATH, SessionWorker


BG = "#0e1524"
CARD = "#182235"
VIDEO = "#101a2a"
TEXT = "#edf3fa"
MUTED = "#9aaec5"
ACCENT = "#94e2bb"
ORANGE = "#ffc28e"


class SIFocusApp:
    def __init__(self, root):
        self.root = root
        self.worker = None
        self.closing = False
        self.started_at = None
        self.last_packet_at = None
        self.photo = None
        self.trigger = 2.0
        self.cooldown = 8.0
        self.camera_var = tk.StringVar(value="0")
        self.trigger_var = tk.StringVar(value="2.0")
        self.cooldown_var = tk.StringVar(value="8")
        self.mute_var = tk.BooleanVar(value=False)
        self.technical_var = tk.BooleanVar(value=False)
        self.root.title("SIFocus · Pemantauan mata")
        window_width = min(1180, max(960, self.root.winfo_screenwidth() - 80))
        window_height = min(850, max(640, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(960, 640)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._styles()
        self._build()
        self.poll_id = self.root.after(40, self.poll)

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 9),
                        background="#293950", foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#38506b"), ("disabled", "#202d40")],
                  foreground=[("disabled", "#64748b")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#11261c")
        style.map("Accent.TButton", background=[("active", "#b5f0d1"), ("disabled", "#344c46")],
                  foreground=[("disabled", "#7d918a")])
        style.configure("TCheckbutton", font=("Segoe UI", 10), background=CARD,
                        foreground=TEXT, padding=(0, 5))
        style.map("TCheckbutton", background=[("active", CARD)])
        style.configure("TSpinbox", fieldbackground="#0e1727", foreground=TEXT,
                        arrowcolor=TEXT, padding=5, borderwidth=0)
        style.configure("Horizontal.TProgressbar", background=ACCENT,
                        troughcolor="#29364b", borderwidth=0)

    def label(self, parent, text="", size=10, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                        bg=parent.cget("bg"), fg=color, anchor="w", **kwargs)

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(22, 18))
        badge = tk.Label(header, text="SF", bg=ACCENT, fg="#11261c",
                         font=("Segoe UI", 15, "bold"), padx=11, pady=9)
        badge.pack(side="left", padx=(0, 14))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        self.label(brand, "SIFocus", 25, bold=True).pack(anchor="w")
        self.label(brand, "Pemantauan mata dan pengingat jeda", 10, MUTED).pack(anchor="w")
        self.label(header, "PROTOTIPE COMPUTER VISION", 9, MUTED).pack(side="right")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=28)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=334)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        rail = tk.Frame(body, bg=CARD)
        rail.grid(row=0, column=1, sticky="nsew")
        rail_canvas = tk.Canvas(rail, bg=CARD, width=318, highlightthickness=0)
        rail_scroll = ttk.Scrollbar(rail, orient="vertical", command=rail_canvas.yview)
        rail_scroll.pack(side="right", fill="y")
        rail_canvas.pack(side="left", fill="both", expand=True)
        rail_canvas.configure(yscrollcommand=rail_scroll.set)
        right = tk.Frame(rail_canvas, bg=CARD, padx=18, pady=18)
        rail_window = rail_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda event: rail_canvas.configure(scrollregion=rail_canvas.bbox("all")))
        rail_canvas.bind("<Configure>", lambda event: rail_canvas.itemconfigure(rail_window, width=event.width))

        video_header = tk.Frame(left, bg=BG)
        video_header.pack(fill="x", pady=(0, 10))
        self.label(video_header, "KAMERA LANGSUNG", 10, bold=True).pack(side="left")
        self.session_label = self.label(video_header, "Sesi belum dimulai", 10, MUTED)
        self.session_label.pack(side="right")
        self.video_label = tk.Label(left, text="Kamera siap saat Anda siap.\n\n"
                                   "Klik Mulai, lalu ikuti kalibrasi mata.",
                                   bg=VIDEO, fg=MUTED, font=("Segoe UI", 13),
                                   width=1, height=1)
        self.video_label.pack(fill="both", expand=True)
        self.connection_label = self.label(left, "●  KAMERA NONAKTIF", 9, MUTED)
        self.connection_label.pack(fill="x", pady=(8, 12))

        stats = tk.Frame(left, bg=BG)
        stats.pack(fill="x")
        self.eye_label = self._stat(stats, "KONDISI MATA", "Belum dipantau", 0, 2)
        self.duration_label = self._stat(stats, "TERTUTUP", "0.0 s", 1, 1)
        self.count_label = self._stat(stats, "PERINGATAN", "0", 2, 1)
        self.duration_bar = ttk.Progressbar(left, maximum=self.trigger)
        self.duration_bar.pack(fill="x", pady=(9, 12))
        self.banner = tk.Label(left, text="Mulai sesi untuk melakukan kalibrasi individual.",
                               bg=CARD, fg=TEXT, font=("Segoe UI", 11), anchor="w",
                               justify="left", padx=16, pady=12, wraplength=610, height=2)
        self.banner.pack(fill="x")
        left.bind("<Configure>", lambda event: self.banner.configure(wraplength=max(200, event.width - 32)))

        self.label(right, "Sesi Fokus", 18, bold=True).pack(anchor="w")
        self.label(right, "Satu pengguna · wajah menghadap kamera", 9, MUTED).pack(anchor="w", pady=(3, 14))
        buttons = tk.Frame(right, bg=CARD)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="▶  Mulai", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="■  Berhenti", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", fill="x", expand=True)

        self.label(right, "01  KALIBRASI INDIVIDUAL", 10, ACCENT, True).pack(anchor="w", pady=(22, 8))
        self.calibration_label = self.label(right, "Belum dikalibrasi", 11, bold=True,
                                             wraplength=275, justify="left")
        self.calibration_label.pack(fill="x")
        self.calibration_hint = self.label(right, "Buka mata normal ±5 detik, lalu tutup ±2 detik. "
                                           "Jangan membelalakkan mata.", 10, MUTED,
                                           wraplength=275, justify="left")
        self.calibration_hint.pack(fill="x", pady=(5, 10))
        self.recalibrate_button = ttk.Button(right, text="Kalibrasi ulang", command=self.recalibrate,
                                            state="disabled")
        self.recalibrate_button.pack(fill="x")

        self.label(right, "02  PENGATURAN PENGINGAT", 10, ACCENT, True).pack(anchor="w", pady=(20, 8))
        self.camera_spin = self._setting(right, "Indeks kamera", self.camera_var, 0, 9, 1)
        self._setting(right, "Durasi pemicu (detik)", self.trigger_var, 0.5, 10, 0.5)
        self._setting(right, "Cooldown bunyi (detik)", self.cooldown_var, 2, 60, 1)
        self.label(right, "Parameter prototipe, bukan standar medis.", 9, MUTED).pack(anchor="w", pady=(1, 7))
        ttk.Button(right, text="Terapkan pengaturan", command=self.apply_settings).pack(fill="x")
        ttk.Checkbutton(right, text="Mute bunyi pengingat", variable=self.mute_var,
                        command=self.set_mute).pack(anchor="w", pady=(7, 0))
        ttk.Checkbutton(right, text="Tampilkan panel teknis", variable=self.technical_var,
                        command=self.toggle_technical).pack(anchor="w")
        self.technical = tk.Frame(left, bg="#101a2a", padx=10, pady=8)
        self.technical_label = tk.Label(self.technical, text="EAR tersedia setelah kamera aktif.",
                                       font=("Consolas", 9), bg="#101a2a", fg=MUTED,
                                       anchor="w", justify="left")
        self.technical_label.pack(fill="x")
        ttk.Button(right, text="Keluar", command=self.close).pack(side="bottom", fill="x", pady=(10, 0))

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(16, 18))
        self.label(footer, "●  Diproses lokal · tanpa rekaman otomatis", 9, ACCENT).pack(anchor="w")
        self.label(footer, "Pengingat indikasi kantuk, bukan diagnosis. Kacamata, pantulan, dan cahaya rendah "
                   "dapat menurunkan akurasi.", 9, MUTED).pack(anchor="w", pady=(4, 0))

    def _stat(self, parent, title, value, column, weight):
        parent.columnconfigure(column, weight=weight)
        box = tk.Frame(parent, bg=CARD, padx=12, pady=10)
        box.grid(row=0, column=column, sticky="nsew", padx=(0, 8 if column < 2 else 0))
        self.label(box, title, 8, MUTED, True).pack(anchor="w")
        label = self.label(box, value, 12, bold=True, wraplength=215 if column == 0 else 100)
        label.pack(anchor="w", pady=(5, 0))
        return label

    def _setting(self, parent, title, variable, minimum, maximum, step):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        self.label(row, title, 10, MUTED).pack(side="left")
        spin = ttk.Spinbox(row, from_=minimum, to=maximum, increment=step,
                           textvariable=variable, width=5, font=("Segoe UI", 10))
        spin.pack(side="right")
        return spin

    def read_settings(self):
        try:
            camera = int(self.camera_var.get())
            trigger = float(self.trigger_var.get().replace(",", "."))
            cooldown = float(self.cooldown_var.get().replace(",", "."))
            if not (0 <= camera <= 9 and 0.5 <= trigger <= 10 and 2 <= cooldown <= 60):
                raise ValueError
        except ValueError:
            messagebox.showerror("Pengaturan tidak valid", "Indeks kamera: 0–9\nDurasi pemicu: 0,5–10 detik\n"
                                 "Cooldown: 2–60 detik", parent=self.root)
            return None
        return camera, trigger, cooldown

    def apply_settings(self):
        settings = self.read_settings()
        if settings is None:
            return
        _, self.trigger, self.cooldown = settings
        self.duration_bar.configure(maximum=self.trigger, value=0)
        if self.worker and self.worker.is_alive() and not self.worker.stopped.is_set():
            self.worker.commands.put(("settings", (self.trigger, self.cooldown)))
        else:
            self.set_banner("Pengaturan diterapkan. Klik Mulai untuk membuka kamera.")

    def start(self):
        if self.worker is not None:
            return
        settings = self.read_settings()
        if settings is None:
            return
        if not MODEL_PATH.is_file():
            self.set_banner("Model belum tersedia. Jalankan python download_model.py, lalu klik Mulai.", True)
            return
        camera, self.trigger, self.cooldown = settings
        self.worker = SessionWorker(camera, self.trigger, self.cooldown)
        self.set_mute()
        self.started_at = time.monotonic()
        self.last_packet_at = time.monotonic()
        self.eye_label.configure(text="Menyiapkan kamera")
        self.count_label.configure(text="0")
        self.duration_label.configure(text="0.0 s")
        self.duration_bar.configure(maximum=self.trigger, value=0)
        self.calibration_label.configure(text="Menyiapkan kalibrasi")
        self.technical_label.configure(text="Memuat model dan kamera...")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.camera_spin.configure(state="disabled")
        self.set_banner("Memuat model dan membuka kamera. Kalibrasi akan dimulai otomatis.")
        self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.stopped.set()
            self.stop_button.configure(state="disabled")
            self.recalibrate_button.configure(state="disabled")
            self.duration_label.configure(text="0.0 s")
            self.duration_bar.configure(value=0)
            self.eye_label.configure(text="Sesi dihentikan")
            self.video_label.configure(image="", text="Sesi dihentikan.\nKlik Mulai untuk sesi baru.")
            self.photo = None
            self.set_banner("Menghentikan kamera...")

    def recalibrate(self):
        if self.worker and not self.worker.stopped.is_set():
            self.worker.commands.put(("calibrate", None))
            self.duration_label.configure(text="0.0 s")
            self.duration_bar.configure(value=0)
            self.set_banner("Kalibrasi ulang dimulai. Bunyi pengingat dinonaktifkan selama kalibrasi.")

    def set_mute(self):
        if self.worker:
            if self.mute_var.get():
                self.worker.muted.set()
            else:
                self.worker.muted.clear()

    def toggle_technical(self):
        if self.technical_var.get():
            self.technical.pack(fill="x", pady=(5, 0))
        else:
            self.technical.pack_forget()

    def set_banner(self, text, warning=False):
        self.banner.configure(text=text, bg="#3c2b28" if warning else CARD,
                              fg=ORANGE if warning else TEXT)

    def show_frame(self, packet):
        image = Image.fromarray(packet["image"])
        image.thumbnail((max(1, self.video_label.winfo_width()),
                         max(1, self.video_label.winfo_height())), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image, master=self.root)
        self.video_label.configure(image=self.photo, text="")
        self.connection_label.configure(text="●  KAMERA AKTIF · tampilan cermin", fg=ACCENT)
        detection = packet["detection"]
        self.eye_label.configure(text=detection.status, fg=ORANGE if detection.warning or packet["reason"] else TEXT)
        self.duration_label.configure(text=f"{detection.duration:.1f} s")
        self.duration_bar.configure(value=min(self.trigger, detection.duration))
        self.count_label.configure(text=str(packet["warnings"]))
        self.recalibrate_button.configure(state="normal")
        stage, remaining = packet["cal_stage"], packet["cal_remaining"]
        instructions = {
            "prepare_open": (f"Bersiap · {remaining:.1f} s", "Hadapkan wajah ke kamera. Sebentar lagi buka mata normal."),
            "open": (f"Buka mata normal · {remaining:.1f} s", "Tetap rileks, jangan membelalakkan mata. Kedipan sesekali boleh."),
            "prepare_closed": (f"Bersiap menutup · {remaining:.1f} s", "Tunggu hitungan selesai, lalu tutup kedua mata sekitar 2 detik."),
            "closed": (f"Tutup kedua mata · {remaining:.1f} s", "Tutup sekitar 2 detik, lalu buka kembali untuk mulai memantau."),
            "failed": ("Kalibrasi perlu diulang", packet["cal_error"]),
            "ready": ("Kalibrasi siap", "Buka kedua mata untuk mengaktifkan pemantauan. Kalibrasi ulang jika posisi berubah."),
        }
        title, hint = instructions[stage]
        self.calibration_label.configure(text=title, fg=ORANGE if stage == "failed" else TEXT)
        self.calibration_hint.configure(text=hint)
        if packet["reason"]:
            self.set_banner(packet["reason"] + ". Durasi mata tertutup direset.", True)
        elif stage == "failed":
            self.set_banner(packet["cal_error"], True)
        elif detection.warning:
            self.set_banner(ALERT_MESSAGE, True)
        elif stage != "ready":
            self.set_banner(f"Kalibrasi: {title}. Bunyi pengingat nonaktif.")
        else:
            self.set_banner("Pemantauan aktif. Jaga posisi wajah dan pencahayaan yang cukup."
                            if detection.status != "Buka kedua mata untuk mulai" else detection.status + ".")
        self.update_technical(packet)

    def update_technical(self, packet):
        def pair(value):
            return "— / —" if value is None else f"{value[0]:.3f} / {value[1]:.3f}"
        lines = ["                   Kiri / Kanan", f"EAR mentah   {pair(packet['ears'])}",
                 f"EAR halus    {pair(packet['detection'].smoothed)}"]
        profile = packet["profile"]
        if profile:
            for caption, field in (("Acuan buka", "opened"), ("Acuan tutup", "closed"),
                                   ("Ambang tutup", "close_at"), ("Ambang buka", "reopen_at")):
                lines.append(f"{caption:12} {pair((getattr(profile.left, field), getattr(profile.right, field)))}")
        else:
            samples = packet["samples"]
            lines.append(f"Sampel buka/tutup: {samples['open']} / {samples['closed']}")
        lines.append(f"FPS proses: {packet['fps']:.1f}")
        self.technical_label.configure(text="\n".join(lines))

    def poll(self):
        if self.closing:
            return
        if self.worker:
            try:
                packet = self.worker.output.get_nowait()
            except queue.Empty:
                packet = None
            if packet and not self.worker.stopped.is_set():
                self.last_packet_at = time.monotonic()
                if packet["kind"] == "frame":
                    self.show_frame(packet)
                else:
                    self.set_banner(packet["message"], True)
                    self.eye_label.configure(text="Kamera tidak valid", fg=ORANGE)
                    self.duration_label.configure(text="0.0 s")
                    self.duration_bar.configure(value=0)
                    self.video_label.configure(image="", text=packet["message"], wraplength=560)
                    self.photo = None
            if not self.worker.is_alive():
                stopped = self.worker.stopped.is_set()
                self.worker = None
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.recalibrate_button.configure(state="disabled")
                self.camera_spin.configure(state="normal")
                self.connection_label.configure(text="●  KAMERA NONAKTIF", fg=MUTED)
                if stopped:
                    self.set_banner("Sesi selesai. Klik Mulai untuk sesi baru dan kalibrasi baru.")
            elif not self.worker.stopped.is_set():
                elapsed = int(time.monotonic() - self.started_at)
                self.session_label.configure(text=f"Sesi {elapsed // 60:02d}:{elapsed % 60:02d}")
                if time.monotonic() - self.last_packet_at > 1.0:
                    self.eye_label.configure(text="Menunggu frame valid", fg=MUTED)
                    self.duration_label.configure(text="0.0 s")
                    self.duration_bar.configure(value=0)
                    self.video_label.configure(image="", text="Menunggu kamera / model...")
                    self.photo = None
                    self.set_banner("Menunggu frame baru. Pemantauan durasi memerlukan frame valid berkelanjutan.")
        self.poll_id = self.root.after(40, self.poll)

    def close(self):
        self.closing = True
        self.root.after_cancel(self.poll_id)
        if self.worker:
            self.worker.stopped.set()
        # Thread daemon menjadi pengaman bila driver kamera macet permanen.
        self.root.destroy()


def run():
    root = tk.Tk()
    SIFocusApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()