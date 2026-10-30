from django.urls import path

from . import views

app_name = 'about'

urlpatterns = [
    path('', views.about, name='about'),
    path('leadership/', views.leadership, name='leadership'),
    path('founder/', views.founder, name='founder'),
    path('story/', views.story, name='story'),
    path('vision/', views.vision, name='vision'),
    path('mission/', views.mission, name='mission'),
]
