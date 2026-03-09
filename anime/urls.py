from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("home/", views.home, name="home"),
    path("anime/<int:mal_id>/", views.anime_detail, name="anime"),
    path("watch/<int:mal_id>/<int:episode>/", views.watch, name="watch"),
]