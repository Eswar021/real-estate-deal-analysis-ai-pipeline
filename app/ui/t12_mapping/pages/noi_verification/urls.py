from django.urls import path

from . import views


urlpatterns = [
    path("<uuid:upload_id>/noi/", views.verify, name="noi_verify"),
]
