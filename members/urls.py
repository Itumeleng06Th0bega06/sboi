from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import MemberLoginForm

app_name = 'members'

urlpatterns = [
    path('', views.members_home, name='home'),
    # Step 1: choose User or Church Member.
    path('register/', views.register, name='register'),
    path('register/user/', views.register_user, name='register_user'),
    path('register/church/', views.register_church, name='register_church'),
    # Existing account joins the church membership later.
    path('join-church/', views.join_church, name='join_church'),
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
