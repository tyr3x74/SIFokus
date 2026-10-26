"""Satu thread kamera/model; thread Tkinter tidak pernah menunggu inferensi."""

from pathlib import Path
import queue
import sys
import threading
import time
from datetime import datetime

import cv2

from .logic import ALERT_MESSAGE, Calibrator, Detection, EyeMonitor, MAX_SAMPLE_GAP
from .vision import FaceTracker, draw_eyes


MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"


class ReminderSound:
    def __init__(self, muted, stopped):
        self.muted = muted
        self.stopped = stopped
        self.thread = None

    def play(self):
        if self.muted.is_set() or self.stopped.is_set():
            return
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._beep, daemon=True)
            self.thread.start()

    def _beep(self):
        try:
            if sys.platform == "win32":
                import winsound
                for frequency in (740, 880):
                    if self.muted.is_set() or self.stopped.is_set():
                        break
                    winsound.Beep(frequency, 180)
            else:
                # Dukungan utama Windows; BEL adalah fallback terminal.
                print("\a", end="", flush=True)
        except (OSError, RuntimeError):
            # Gangguan audio tidak menghentikan pengingat visual/video.
            pass


class SessionWorker(threading.Thread):
    def __init__(self, camera_index=0, trigger=2.0, cooldown=8.0):
        super().__init__(daemon=True, name="SIFocus-camera")
        self.camera_index = camera_index
        self.trigger = trigger
        self.cooldown = cooldown
        self.stopped = threading.Event()
        self.muted = threading.Event()
        self.commands = queue.Queue()
        self.output = queue.Queue(maxsize=1)  # Hanya frame terbaru, hindari tumpukan.
        self.sound = ReminderSound(self.muted, self.stopped)

    def publish(self, packet):
        try:
            self.output.get_nowait()
        except queue.Empty:
            pass
        self.output.put_nowait(packet)

    def _open_camera(self):
        backends = (cv2.CAP_DSHOW, cv2.CAP_MSMF) if sys.platform == "win32" else (cv2.CAP_ANY,)
        for backend in backends:
            if self.stopped.is_set():
                return None
            capture = cv2.VideoCapture(self.camera_index, backend)
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                capture.set(cv2.CAP_PROP_FPS, 30)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return capture
            capture.release()
        raise RuntimeError(
            "Kamera tidak tersedia atau gagal diakses. Tutup aplikasi kamera lain, "
            "izinkan akses kamera di pengaturan Windows, atau ubah indeks kamera."
        )

    def run(self):
        capture = tracker = None
        try:
            tracker = FaceTracker(MODEL_PATH)
            if self.stopped.is_set():
                return
            capture = self._open_camera()
            if capture is None:
                return
            calibrator = None
            monitor = None
            warning_count = 0
            failures = 0
            previous_frame = None
            fps = 0.0
            while not self.stopped.is_set():
                while True:
                    try:
                        command, value = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    if command == "calibrate":
                        calibrator = None
                        monitor = None
                    elif command == "settings":
                        self.trigger, self.cooldown = value
                        if monitor:
                            monitor.configure(self.trigger, self.cooldown)
                            monitor.reset_tracking()
                ok, frame = capture.read()
                now = time.monotonic()
                if self.stopped.is_set():
                    break
                if calibrator is None:
                    calibrator = Calibrator(now)
                if not ok or frame is None:
                    failures += 1
                    if monitor:
                        monitor.update(None, now)
                    calibrator.update(now, None)
                    self.publish({"kind": "waiting", "message": "Kamera gagal membaca frame. Penghitung direset."})
                    if failures >= 15:
                        raise RuntimeError("Kamera terputus atau gagal membaca video. Periksa kamera lalu mulai ulang.")
                    self.stopped.wait(0.05)
                    continue
                failures = 0
                if frame.shape[1] > 640:
                    scale = 640 / frame.shape[1]
                    frame = cv2.resize(frame, (640, round(frame.shape[0] * scale)))
                ears, eyes, reason = tracker.process(frame, now)
                if time.monotonic() - now > MAX_SAMPLE_GAP:
                    ears, eyes, reason = None, (), "Pemrosesan terlalu lambat. Penghitung direset."
                if previous_frame is not None:
                    dt = now - previous_frame
                    if dt > 0:
                        fps = 0.8 * fps + 0.2 / dt if fps else 1 / dt
                previous_frame = now
                calibrator.update(now, ears)
                detection = Detection("Kalibrasi berlangsung")
                if calibrator.profile:
                    if monitor is None:
                        monitor = EyeMonitor(calibrator.profile, self.trigger, self.cooldown)
                    detection = monitor.update(ears, now, self.muted.is_set())
                    if detection.closed_event:
                        print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] "
                              "Mata tertutup terdeteksi.", flush=True)
                    if detection.event:
                        warning_count += 1
                    if detection.sound and not self.stopped.is_set():
                        self.sound.play()
                elif calibrator.error:
                    detection = Detection("Perlu kalibrasi ulang")
                if reason:
                    detection = Detection(reason)
                draw_eyes(frame, eyes, detection.warning)
                display = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                self.publish({
                    "kind": "frame", "image": display, "timestamp": now,
                    "detection": detection, "ears": ears, "fps": fps,
                    "cal_stage": calibrator.stage, "cal_remaining": calibrator.remaining(now),
                    "cal_error": calibrator.error, "profile": calibrator.profile,
                    "warnings": warning_count, "reason": reason,
                    "message": ALERT_MESSAGE if detection.warning else "",
                    "samples": {k: len(v) for k, v in calibrator.samples.items()},
                })
        except Exception as exc:
            # Pesan tetap terlihat di GUI, detail diagnostik ada di terminal.
            import traceback
            traceback.print_exc()
            self.publish({"kind": "error", "message": str(exc) or type(exc).__name__})
        finally:
            if capture is not None:
                capture.release()
            if tracker is not None:
                tracker.close()
