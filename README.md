# SIFokus — Pemantauan Mata dan Pengingat Jeda

SIFokus adalah prototipe desktop Python untuk mendeteksi mata tertutup dari webcam dan memberi pengingat visual serta bunyi ketika kedua mata tetap tertutup melewati durasi pemicu. Pemrosesan kamera dilakukan lokal. Aplikasi tidak menyimpan atau mengirim rekaman.

## Tujuan dan ruang lingkup

Aplikasi membantu pengguna menyadari periode mata tertutup yang berlangsung lama saat menggunakan komputer. Ini adalah prototipe Computer Vision untuk demonstrasi, bukan alat medis, diagnosis, atau pengukur kantuk yang tervalidasi.

## Metode dan alur sistem

```text
Webcam → MediaPipe Face Landmarker → landmark wajah/mata → EAR per mata
       → kalibrasi personal dan penghalusan sinyal → durasi kedua mata tertutup
       → overlay kamera, status/pengingat visual, dan bunyi
```

MediaPipe Face Landmarker mendeteksi satu wajah pada mode video. Enam landmark di setiap mata digunakan untuk menghitung Eye Aspect Ratio (EAR), yaitu rasio jarak vertikal dan horizontal kelopak. Nilai EAR dikalibrasi terpisah untuk mata kiri dan kanan, dihaluskan, lalu dibandingkan dengan dua ambang (hysteresis) agar status tidak mudah berubah karena noise. Pengingat baru aktif setelah kedua mata terbuka dahulu dan kemudian tertutup melewati durasi pemicu.

## Kebutuhan

- Windows 64-bit
- Python 3.11 atau 3.12
- Webcam dan izin akses kamera
- Berkas model `models/face_landmarker.task` (sudah disertakan)
- Dependensi pada `requirements.txt`; jangan pasang distribusi OpenCV lain bersamaan dengan `opencv-contrib-python`

## Instalasi

Buka PowerShell di folder proyek:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika `py -3.11` tidak tersedia, gunakan `py -3.12`. Kebijakan PowerShell lokal mungkin membatasi aktivasi skrip; alternatifnya jalankan `\.venv\Scripts\python.exe` untuk perintah Python dan pip.

## Menjalankan aplikasi

```powershell
python main.py
```

Klik **Mulai**, posisikan wajah menghadap kamera dan ikuti kalibrasi otomatis: mata terbuka rileks selama sekitar 5 detik, kemudian mata tertutup sekitar 2 detik. Setelah kalibrasi, buka kedua mata sekali untuk memulai pemantauan. Pastikan wajah dan pencahayaan cukup terang.

## Input dan output

- **Input:** video langsung dari webcam yang dipilih melalui indeks kamera (awal `0`, opsi `0–9`). Aplikasi memproses maksimal satu wajah.
- **Output:** pratinjau kamera dengan penanda mata, status buka/tertutup, durasi tertutup, hitungan peringatan, peringatan visual, dan bunyi. Panel teknis opsional menampilkan EAR, ambang kalibrasi, serta FPS pemrosesan.
- **Log terminal:** setiap transisi ke keadaan kedua mata tertutup yang terdeteksi setelah kalibrasi menghasilkan satu baris `Mata tertutup terdeteksi` dengan waktu lokal. Log tidak dicetak berulang untuk setiap frame selama mata tetap tertutup.

## Pengaturan pengingat

Ubah nilai lalu klik **Terapkan pengaturan**. Durasi pemicu yang diizinkan adalah `0,5–10` detik (awal `2,0` detik); cooldown bunyi `2–60` detik (awal `8` detik). Keduanya dapat diterapkan saat sesi berjalan dan penghitung durasi direset agar pengukuran berikut memakai parameter baru. Indeks kamera dapat diubah sebelum memulai sesi berikutnya. **Mute bunyi pengingat** menghentikan bunyi, namun status dan pengingat visual tetap berjalan.

## Pengujian dan evaluasi

Evaluasi yang sesuai untuk demonstrasi: kalibrasi dengan mata terbuka dan tertutup, uji penutupan singkat dan berkepanjangan, uji satu mata/pose yang tidak valid, serta ubah durasi pemicu, cooldown, dan mute. Bandingkan waktu transisi/pengingat aktual dengan parameter yang dipilih dan catat kegagalan deteksi pada kondisi berbeda. Jangan mengklaim angka akurasi sebelum pengujian terukur dilakukan. Hasil bergantung pada kamera, pencahayaan, pose, kacamata/pantulan, dan kualitas kalibrasi.

## Keterbatasan

- Mengandalkan satu webcam dan satu wajah; kamera harus tetap terbuka selama sesi.
- Cahaya rendah, pantulan/kacamata, wajah miring, posisi terlalu jauh, dan kamera yang lambat dapat mengganggu landmark atau mereset penghitung.
- Kalibrasi bersifat individual dan perlu diulang ketika posisi berubah atau hasilnya buruk.
- Penutupan mata merupakan indikasi sederhana, bukan bukti kantuk atau kondisi kesehatan.
- Performa bergantung pada perangkat dan dapat berbeda antar pengguna; belum ada klaim metrik akurasi tervalidasi.

## Model dan referensi teknis

Model yang diperlukan: `models/face_landmarker.task`, memakai MediaPipe Tasks Vision Face Landmarker. Dokumentasi metode dan model tersedia pada [panduan Face Landmarker MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) dan [referensi API Python](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/FaceLandmarker). Dependensi dan versi yang digunakan dicantumkan pada `requirements.txt`. Kode pengukuran landmark dan EAR berada di `app/geometry.py`, pemrosesan model di `app/vision.py`, logika kalibrasi/pengingat di `app/logic.py`, dan GUI/thread kamera di `app/app.py` serta `app/worker.py`.

Untuk penyerahan akhir, catat URL unduhan spesifik dan lisensi yang disertakan oleh distribusi `face_landmarker.task` yang digunakan. Tambahkan tautan repository, laporan, slide, video demonstrasi, dan rincian anggota kelompok sebelum pengumpulan; informasi tersebut tidak tersedia dalam folder proyek ini.
