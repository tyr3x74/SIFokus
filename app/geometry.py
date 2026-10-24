"""EAR dalam koordinat piksel dan pemeriksaan geometri wajah sederhana."""

import math


# Urutan p1,p2,p3,p4,p5,p6 mengelilingi kelopak; sisi anatomi pengguna.
LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
ADJUST_MESSAGE = "Sesuaikan posisi wajah atau pencahayaan"
NO_FACE_MESSAGE = "Wajah tidak terdeteksi"


def eye_aspect_ratio(points):
    if len(points) != 6 or not all(math.isfinite(v) for p in points for v in p):
        raise ValueError("Enam titik mata harus terhingga.")
    width = math.dist(points[0], points[3])
    if width < 1e-6:
        raise ValueError("Lebar mata nol.")
    return (math.dist(points[1], points[5]) + math.dist(points[2], points[4])) / (2 * width)


def measure_face(landmarks, width, height):
    """Kembalikan (EAR kiri/kanan, titik overlay, alasan invalid).

    Gate pose berupa heuristik 2D, bukan estimasi sudut kepala klinis.
    Tidak ada batas minimum bukaan kelopak: mata sempit/tutup tetap valid.
    """
    if not landmarks:
        return None, (), NO_FACE_MESSAGE
    if len(landmarks) < 468:
        return None, (), ADJUST_MESSAGE
    selected = set(LEFT_EYE + RIGHT_EYE + (1, 152))
    coords = {}
    for index in selected:
        p = landmarks[index]
        if (not math.isfinite(p.x) or not math.isfinite(p.y)
                or not 0 <= p.x <= 1 or not 0 <= p.y <= 1):
            return None, (), ADJUST_MESSAGE
        coords[index] = (p.x * width, p.y * height)
    left = [coords[i] for i in LEFT_EYE]
    right = [coords[i] for i in RIGHT_EYE]
    left_width = math.dist(left[0], left[3])
    right_width = math.dist(right[0], right[3])
    if min(left_width, right_width) < 12:
        return None, (), ADJUST_MESSAGE
    if min(left_width, right_width) / max(left_width, right_width) < 0.55:
        return None, (), ADJUST_MESSAGE
    # Titik tengah sudut kelopak tidak berubah banyak ketika mata ditutup.
    a = tuple((right[0][i] + right[3][i]) / 2 for i in (0, 1))
    b = tuple((left[0][i] + left[3][i]) / 2 for i in (0, 1))
    distance = math.dist(a, b)
    if distance < 35:
        return None, (), ADJUST_MESSAGE
    ux, uy = (b[0] - a[0]) / distance, (b[1] - a[1]) / distance
    if abs(math.degrees(math.atan2(uy, ux))) > 30:
        return None, (), ADJUST_MESSAGE
    nose, chin = coords[1], coords[152]
    nose_side = ((nose[0] - a[0]) * ux + (nose[1] - a[1]) * uy) / distance
    nose_down = (-(nose[0] - a[0]) * uy + (nose[1] - a[1]) * ux)
    chin_down = (-(chin[0] - a[0]) * uy + (chin[1] - a[1]) * ux)
    if not 0.26 <= nose_side <= 0.74 or chin_down <= 20:
        return None, (), ADJUST_MESSAGE
    if not 0.12 <= nose_down / chin_down <= 0.65:
        return None, (), ADJUST_MESSAGE
    ears = (eye_aspect_ratio(left), eye_aspect_ratio(right))
    if not all(0 <= e <= 0.7 for e in ears):
        return None, (), ADJUST_MESSAGE
    return ears, (left, right), ""
