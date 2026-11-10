from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.bell_api, name='feed'),
    path('history/', views.history_public, name='history'),
    path('history/staff/', views.history_staff, name='history_staff'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('delete-selected/', views.delete_selected, name='delete_selected'),
    path('<int:pk>/read/', views.read_notification, name='read'),
    path('<int:pk>/open/', views.open_notification, name='open'),
    path('<int:pk>/dismiss/', views.dismiss_notification, name='dismiss'),
    path('<int:pk>/archive/', views.archive_notification, name='archive'),
]
