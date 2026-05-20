from django.urls import path
from . import views

urlpatterns = [
    path("",                                  views.home,           name="home"),
    path("t12/",                              views.upload,         name="t12_upload"),
    path("t12/<str:upload_id>/subtotals/",    views.subtotals_stub, name="t12_subtotals"),
]
