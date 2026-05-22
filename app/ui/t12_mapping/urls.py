"""
t12_mapping/urls.py — aggregates page URLs.

This is the one place to see the whole T12 flow. Each include() points to
a self-contained page module under pages/.
"""

from django.urls import include, path


urlpatterns = [
    path("", include("t12_mapping.pages.upload.urls")),
    path("", include("t12_mapping.pages.noi_verification.urls")),
]
