# SmartAttend AI - Multimodal Face + Iris Smart Classroom Attendance System

Django 4.2+/6.x project (Python 3.10+) that identifies students from a classroom camera using **face recognition + iris recognition + score-level fusion**, marks attendance automatically, stores it in MySQL, and provides Admin / Teacher / Student portals, analytics, notifications and CSV/Excel/PDF reports.

## 1. Quick start (5 minutes, no hardware needed)

```bash
python -m venv venv
venv\Scripts\activate            # Windows      |   source venv/bin/activate   (Linux/macOS)
pip install -r requirements.txt
copy .env.example .env           # (cp on Linux/macOS)  - already included as .env for SQLite quick start
python manage.py migrate
python manage.py seed_demo       # admin, teachers, 12 students, timetable, demo biometrics, 3 weeks of history
python manage.py runserver
```
Open http://127.0.0.1:8000

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `Admin@12345` |
| Teacher | `teacher1` / `teacher2` | `Teacher@12345` |
| Student | `student1` ... `student12` | `Student@12345` |

**Change these passwords before any real use.**

## 2. MySQL configuration
```sql
CREATE DATABASE smart_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Edit `.env`:
```
DB_ENGINE=mysql
DB_NAME=smart_attendance
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=127.0.0.1
DB_PORT=3306
```
Then `python manage.py migrate && python manage.py seed_demo`. (PyMySQL is used, so no C compiler / mysqlclient is needed.)

Generate a biometric encryption key for `.env` (otherwise a key is derived from `DJANGO_SECRET_KEY` - fine for dev only):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
**Keep this key safe - without it stored templates cannot be decrypted.**

## 3. Demo walkthrough (for your viva / presentation)
1. Login as **teacher1** → *Start session* (camera source: **Demo mode**).
2. On the live page use:
   * **Simulate student** - synthetic frame goes through the real pipeline: face detection → liveness → embedding → match → attendance row. Face score ≥ high threshold ⇒ method `face`.
   * **Low-confidence face (iris fallback)** - face is partly occluded, score falls in the grey zone, the system verifies the iris and fuses both scores ⇒ method `face+iris`.
   * **Unknown person** - rejected, nothing is stored.
   * **Spoof attempt** - screen-replay pattern rejected by the liveness module.
   * **Auto-simulate class** - keeps marking students; counters and the recognised list update in real time. Repeats are ignored (duplicate prevention).
3. **End session** → remaining students become *Absent*, absence notifications are sent, low-attendance warnings are raised.
4. Session details → pencil icon → **authorised correction** (reason + password re-entry; audited; older than N days needs Admin approval).
5. Register & Reports → filter → export **CSV / Excel / PDF**.
6. Admin → AI Analytics, Audit Log, Settings (late minutes, min %, thresholds, fusion weights ...).
7. Login as a student → profile, registered biometrics (status only), timetable, history, subject-wise %, predictions, notifications.

### Using real input
* **Webcam**: *Start camera* on the live page (browser asks permission; use `localhost` or HTTPS).
* **Prerecorded video / images**: "Prerecorded video" and "Upload frame(s)" buttons. `python manage.py generate_samples` creates `sample_data/` (synthetic faces, eyes, spoof, `demo_classroom.mp4`). In demo sessions images that are already face crops are accepted.
* **Registration**: Admin → Students → fingerprint icon → capture with webcam or upload photos / eye close-ups. Only encrypted templates are stored.

## 4. Architecture
```
config/                  settings, urls
apps/accounts/           custom User (role), RBAC decorators, throttled login, audit on login/logout
apps/academics/          Course, Subject, Classroom, Student, Teacher, Timetable + admin CRUD UI
apps/biometrics/         FaceEmbedding, IrisTemplate, enrollment views
  services/face_service.py   detect -> align -> preprocess -> embed -> match
  services/iris_service.py   eye detect -> segment -> quality -> rubber-sheet -> Gabor code -> Hamming match
  services/liveness.py       passive anti-spoofing
  services/recognition.py    multimodal fusion pipeline + enrollment + demo probes
  services/crypto.py         Fernet encryption of templates
  services/synthetic.py      synthetic faces/eyes for Demo Mode
apps/attendance/         AttendanceSession, Attendance, AttendanceCorrection, engine (services.py), live views, reports
apps/core/               Notification, AuditLog, SystemSetting, analytics + prediction, dashboards, seed_demo
templates/  static/      Bootstrap 5 + Chart.js UI, live.js (camera/feed), enroll.js
```
### Fusion logic (`recognition.py`)
| Face score | Action |
|---|---|
| liveness fails | **Spoof** - rejected |
| ≥ `face_high_confidence` (0.70) | accept on face alone (`face`) |
| `face_low_confidence` (0.12) ≤ score < high | **iris verification** of the best candidate; `fused = w_f·face + w_i·iris`; accept if fused ≥ `fusion_threshold` and iris ≥ 0.5 (`face+iris`); no usable iris ⇒ not marked |
| < low | Unknown person |

Scores are calibrated sigmoids so 0.5 sits exactly at each modality's decision threshold (cosine similarity for face, fractional Hamming distance for iris). All thresholds/weights are editable in **Admin → Settings**.

### Attendance rules
Present / Late (after `late_after_minutes`) / Absent (auto at session end) / Excused (manual). Percentage = (Present + Late) / (Present + Late + Absent); Excused is excluded; set `late_counts_as_present=0` to change. Unique constraint `(session, student)` guarantees no duplicates even with concurrent frames.

### Security & privacy
Password hashing (PBKDF2-SHA256), CSRF on all forms and AJAX, role-based decorators on every view, server-side validation (Django forms + password validators), login throttling (5 fails / 15 min), audit log (logins, CRUD, enrolment, corrections, exports, settings), security headers/cookie flags (`DJANGO_DEBUG=False` enables secure cookies), **no raw biometric images are written to disk** - frames are decoded in memory and only Fernet-encrypted embeddings / iris codes are stored; students can see only the status of their biometrics; admins can delete templates.

## 5. Deep-learning backend (TensorFlow / PyTorch)
The default face embedder is a CPU-only OpenCV descriptor (HOG + LBP) so the project runs anywhere. For production-grade accuracy install PyTorch + FaceNet and set `FACE_BACKEND=torch` in `.env`:
```bash
pip install torch facenet-pytorch
```
Then re-enrol students (embeddings are backend-specific). `face_service.extract_embedding` is the single place to swap in a TensorFlow/Keras model (e.g. ArcFace) if you prefer.

## 6. Honest limitations (mention in your report)
* Iris recognition normally needs a near-infrared close-range camera; ordinary classroom webcams rarely give usable iris texture, so iris acts as a **second factor** (kiosk / close-up capture) rather than a far-field identifier. Quality checks reject poor samples.
* Default thresholds (`iris_hd_threshold=0.16`, face 0.92) are calibrated on the built-in synthetic data. **Re-calibrate on your own dataset** (typical real NIR iris threshold ≈ 0.32; FaceNet cosine ≈ 0.65). Plot genuine vs impostor score distributions and report EER/FAR/FRR.
* Liveness is passive (sharpness, moiré/FFT peaks, glare, texture); it is a baseline, not a certified PAD system.
* Shortage prediction is a transparent recency-weighted projection; swap in scikit-learn models if you want to compare approaches.

## 7. Commands
```bash
python manage.py migrate | seed_demo [--students N] [--no-history] | generate_samples | test | createsuperuser
```
Run tests: `python manage.py test` (biometrics, liveness, fusion, duplicate prevention, RBAC).

## 8. Production notes
Set `DJANGO_DEBUG=False`, strong `DJANGO_SECRET_KEY`, real `ALLOWED_HOSTS`, `BIOMETRIC_ENCRYPTION_KEY`, serve over HTTPS (needed for webcam access off localhost), `python manage.py collectstatic`, run with gunicorn/uwsgi behind nginx, and use a shared cache (Redis) if running several workers (login throttling + template cache).
