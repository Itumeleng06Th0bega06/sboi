from django.urls import path

from . import views

app_name = 'blackboard'

urlpatterns = [
    path('', views.blackboard, name='blackboard'),
    path('rsvp/', views.event_rsvp, name='rsvp'),
]
