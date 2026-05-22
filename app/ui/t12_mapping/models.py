"""
t12_mapping/models.py

Upload — one row per T12 file the user submits.
Tracks lifecycle (draft → complete), which step the user is on, and the
original file via FileField (Django handles cloud storage transparently
via default_storage when DEFAULT_FILE_STORAGE is swapped in prod).
"""

import uuid

from django.conf import settings
from django.db import models


def _upload_to(instance, filename: str) -> str:
    """Place the original file under <upload_id>/original/<filename>."""
    return f"{instance.id}/original/{filename}"


class Upload(models.Model):
    STATUS_DRAFT    = "draft"
    STATUS_COMPLETE = "complete"
    STATUS_CHOICES  = [
        (STATUS_DRAFT,    "Draft"),
        (STATUS_COMPLETE, "Complete"),
    ]

    STEP_UPLOAD           = "upload"
    STEP_NOI_VERIFICATION = "noi_verification"
    STEP_DATA_REVIEW      = "data_review"
    STEP_ANALYTICS        = "analytics"
    STEP_CHOICES = [
        (STEP_UPLOAD,           "Upload"),
        (STEP_NOI_VERIFICATION, "NOI Verification"),
        (STEP_DATA_REVIEW,      "Data Review"),
        (STEP_ANALYTICS,        "Analytics"),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file          = models.FileField(upload_to=_upload_to)
    file_name     = models.CharField(max_length=255)
    property_name = models.CharField(max_length=255, blank=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    current_step  = models.CharField(max_length=50, choices=STEP_CHOICES, default=STEP_UPLOAD)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    user          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="t12_uploads",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.id})"
