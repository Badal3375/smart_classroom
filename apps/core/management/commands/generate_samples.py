"""python manage.py generate_samples  -> writes synthetic face/eye PNGs into sample_data/ for upload-based demos."""
import cv2
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.biometrics.services import synthetic as S


class Command(BaseCommand):
    help = "Create sample face/eye images (and a short demo video) for demo-mode uploads."

    def handle(self, *a, **o):
        out = settings.BASE_DIR / "sample_data"
        out.mkdir(exist_ok=True)
        for seed in (100, 101, 102):
            for v in (1, 2):
                cv2.imwrite(str(out / f"student_seed{seed}_face_{v}.png"), S.synth_face(seed, v))
                cv2.imwrite(str(out / f"student_seed{seed}_eye_{v}.png"), S.synth_eye(seed, v))
        cv2.imwrite(str(out / "spoof_example.png"), S.make_spoof(S.synth_face(100, 9)))
        cv2.imwrite(str(out / "unknown_person.png"), S.synth_face(987654, 1))
        vw = cv2.VideoWriter(str(out / "demo_classroom.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 2, (160, 160))
        for seed in (100, 101, 102, 987654):
            for v in range(4):
                vw.write(S.synth_face(seed, v + 20))
        vw.release()
        self.stdout.write(self.style.SUCCESS(f"Samples written to {out}"))
