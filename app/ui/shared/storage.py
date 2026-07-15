"""
storage.py — JSON I/O abstraction for page-to-page handoff.

All pages and pipeline_bridge use these helpers instead of raw open()/Path().
Backed by Django's default_storage so swapping to S3/GCS in production is
a one-line settings change (DEFAULT_FILE_STORAGE) with zero code changes here.

Files live under MEDIA_ROOT/<upload_id>/pipeline/<filename> in dev.
"""

import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def _path(upload_id, filename: str) -> str:
    return f"{upload_id}/pipeline/{filename}"


def read_json(upload_id, filename: str) -> dict:
    with default_storage.open(_path(upload_id, filename), "rb") as f:
        return json.loads(f.read())


def write_json(upload_id, filename: str, data: dict) -> None:
    path = _path(upload_id, filename)
    if default_storage.exists(path):
        default_storage.delete(path)
    # default=str keeps the write total: Excel date cells arrive as datetime in the
    # cell_grid; stringify them (as the pipeline's own save_cell_grid does) rather than crash.
    default_storage.save(path, ContentFile(json.dumps(data, indent=2, default=str)))


def exists(upload_id, filename: str) -> bool:
    return default_storage.exists(_path(upload_id, filename))


def get_local_path(file_field_or_upload_id, filename: str = None) -> str:
    """
    Returns a local filesystem path for handing to libraries that can't
    read from a stream (e.g. openpyxl).

    For dev (FileSystemStorage), this is just the absolute path on disk.
    For prod with S3, this would download to a temp file inside the function
    so callers don't change.
    """
    if filename is None:
        return default_storage.path(file_field_or_upload_id.name)
    return default_storage.path(_path(file_field_or_upload_id, filename))
