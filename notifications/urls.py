from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.bell_api, name='feed'),
    path('history/', views.history_public, name='history'),
    path('history/staff/', views.history_staff, name='history_staff'),
    path('<int:pk>/read/', views.read_notification, name='read'),
    path('<int:pk>/dismiss/', views.dismiss_notification, name='dismiss'),
    path('<int:pk>/archive/', views.archive_notification, name='archive'),
]
