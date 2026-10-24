"""Adapter model MediaPipe; frame tidak pernah disimpan atau dikirim."""

import cv2
import mediapipe as mp
import numpy as np

from .geometry import ADJUST_MESSAGE, measure_face


class FaceTracker:
    def __init__(self, model_path):
        if not model_path.is_file():
            raise FileNotFoundError("Model belum tersedia. Jalankan: python download_model.py")
        options = mp.tasks.vision.FaceLandmarkerOptions(
            # Buffer juga mendukung path Windows dengan karakter non-ASCII.
            base_options=mp.tasks.BaseOptions(model_asset_buffer=model_path.read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.6,
            min_face_presence_confidence=0.6,
            min_tracking_confidence=0.6,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self.last_timestamp = -1

    def process(self, bgr_frame, now):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        timestamp = max(self.last_timestamp + 1, int(now * 1000))
        self.last_timestamp = timestamp
        result = self.landmarker.detect_for_video(image, timestamp)
        landmarks = result.face_landmarks[0] if result.face_landmarks else None
        height, width = bgr_frame.shape[:2]
        ears, eyes, reason = measure_face(landmarks, width, height)
        if ears is not None:
            # Cahaya rata-rata ROI wajah sebagai gate konservatif sederhana.
            xs = [p.x * width for p in landmarks]
            ys = [p.y * height for p in landmarks]
            x0, x1 = max(0, int(min(xs))), min(width, int(max(xs)) + 1)
            y0, y1 = max(0, int(min(ys))), min(height, int(max(ys)) + 1)
            roi = bgr_frame[y0:y1, x0:x1]
            if roi.size == 0 or cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean() < 35:
                return None, (), ADJUST_MESSAGE
        return ears, eyes, reason

    def close(self):
        self.landmarker.close()


def draw_eyes(frame, eyes, warning=False):
    color = (93, 210, 125) if not warning else (90, 120, 255)
    for eye in eyes:
        points = np.array(eye, dtype=np.int32)
        cv2.polylines(frame, [points], True, color, 1, cv2.LINE_AA)
        for point in points:
            cv2.circle(frame, tuple(point), 2, color, -1, cv2.LINE_AA)
