from django.db import models
from apps.academics.models import Student


class FaceEmbedding(models.Model):
    """Encrypted face embedding. Raw face images are NEVER stored."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="face_embeddings")
    vector = models.BinaryField()          # Fernet-encrypted float32 bytes
    backend = models.CharField(max_length=20, default="classical")
    quality = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Face[{self.student.roll_no}] {self.backend} q={self.quality:.2f}"


class IrisTemplate(models.Model):
    """Encrypted binary iris code + noise mask. Raw eye images are NEVER stored."""
    EYES = [("L", "Left"), ("R", "Right"), ("U", "Unspecified")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="iris_templates")
    eye = models.CharField(max_length=1, choices=EYES, default="U")
    code = models.BinaryField()            # Fernet-encrypted packed bits
    mask = models.BinaryField()
    shape = models.CharField(max_length=20, default="")
    quality = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Iris[{self.student.roll_no}-{self.eye}] q={self.quality:.2f}"
