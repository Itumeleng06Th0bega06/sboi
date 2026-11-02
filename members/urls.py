from django.contrib.auth import views as auth_views
from django.urls import path

from . import account, views
from .forms import MemberLoginForm

app_name = 'members'

urlpatterns = [
    path('', views.members_home, name='home'),
    # Member account portal (all views require authentication).
    path('account/', account.account_home, name='account'),
    path('account/profile/edit/', account.account_profile_edit, name='account_profile_edit'),
    path('account/membership/edit/', account.account_membership_edit, name='account_membership_edit'),
    path('account/children/', account.account_children, name='account_children'),
    path('account/children/add/', account.account_child_add, name='account_child_add'),
    path('account/children/<int:index>/edit/', account.account_child_edit, name='account_child_edit'),
    path('account/children/<int:index>/remove/', account.account_child_remove, name='account_child_remove'),
    path('account/activities/', account.account_activities, name='account_activities'),
    path('account/messages/', account.account_messages, name='account_messages'),
    path('account/messages/send/', account.account_message_send, name='account_message_send'),
    path('account/messages/poll/', account.account_message_poll, name='account_message_poll'),
    path('account/notifications/', account.account_notifications, name='account_notifications'),
    path('account/notifications/read/', account.account_notification_read, name='account_notification_read'),
    path('account/notifications/<int:pk>/', account.account_notification_open, name='account_notification_open'),
    path('account/settings/', account.account_settings, name='account_settings'),
    path('account/counts/', account.account_counts, name='account_counts'),
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
