from django.urls import path

from . import views

app_name = 'values'

urlpatterns = [
    path('', views.values, name='values'),
]
