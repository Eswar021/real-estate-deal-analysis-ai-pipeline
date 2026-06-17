from django.urls import path

from . import views


urlpatterns = [
    path("<uuid:upload_id>/review/", views.review, name="data_review"),
]
