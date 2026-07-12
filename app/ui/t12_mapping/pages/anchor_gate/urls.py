from django.urls import path

from . import views


urlpatterns = [
    path("<uuid:upload_id>/anchors/", views.anchors, name="anchor_gate"),
]
