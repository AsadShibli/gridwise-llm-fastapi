from django.urls import path

from console import views

urlpatterns = [
    path("", views.run_list, name="run_list"),
    path("runs/", views.run_list, name="run_list_alias"),
    path("runs/new/", views.run_new, name="run_new"),
    path("runs/<int:pk>/", views.run_detail, name="run_detail"),
]
