from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import MemberLoginForm

app_name = 'members'

urlpatterns = [
    path('', views.members_home, name='home'),
    path('register/', views.register, name='register'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='members/login.html',
            redirect_authenticated_user=True,
            authentication_form=MemberLoginForm,
        ),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),
]
