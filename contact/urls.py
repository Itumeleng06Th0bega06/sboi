from django.urls import path

from . import views

app_name = 'contact'

urlpatterns = [
    path('', views.contact, name='contact'),
    path(
        'messages/attachment/<int:pk>/',
        views.message_attachment,
        name='attachment',
    ),
]
