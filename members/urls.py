from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from sboi.password_reset import (
    DebugLinkPasswordResetDoneView,
    DebugLinkPasswordResetView,
)

from . import account, views, views_comms
from .forms import MemberSetPasswordForm

app_name = 'members'

urlpatterns = [
    path('', views.members_home, name='home'),
    # Member account portal (all views require authentication).
    path('account/', account.account_home, name='account'),
    path('account/profile/', account.account_profile, name='account_profile'),
    path('account/posts/', account.account_posts, name='account_posts'),
    path('account/saved/', account.account_saved, name='account_saved'),
    path('account/profile/edit/', account.account_profile_edit, name='account_profile_edit'),
    path('account/membership/request/', account.account_membership_request, name='account_membership_request'),
    path('account/membership/edit/', account.account_membership_edit, name='account_membership_edit'),
    path('account/children/', account.account_children, name='account_children'),
    path('account/children/add/', account.account_child_add, name='account_child_add'),
    path('account/children/<int:index>/edit/', account.account_child_edit, name='account_child_edit'),
    path('account/children/<int:index>/remove/', account.account_child_remove, name='account_child_remove'),
    path('account/activities/', account.account_activities, name='account_activities'),
    path('account/messages/', account.account_messages, name='account_messages'),
    path('account/messages/send/', account.account_message_send, name='account_message_send'),
    path('account/messages/poll/', account.account_message_poll, name='account_message_poll'),
    path('account/messages/start/', account.account_direct_start, name='account_direct_start'),
    path('account/messages/direct/<int:pk>/send/', account.account_direct_send, name='account_direct_send'),
    path('account/messages/direct/<int:pk>/poll/', account.account_direct_poll, name='account_direct_poll'),
    path('account/block/<str:username>/', account.account_block_member, name='account_block_member'),
    path('account/unblock/<str:username>/', account.account_unblock_member, name='account_unblock_member'),
    path('account/notifications/', account.account_notifications, name='account_notifications'),
    path('account/notifications/read/', account.account_notification_read, name='account_notification_read'),
    path('account/notifications/<int:pk>/', account.account_notification_open, name='account_notification_open'),
    path('account/settings/', account.account_settings, name='account_settings'),
    path('account/delete/', account.account_delete, name='account_delete'),
    path('account/counts/', account.account_counts, name='account_counts'),
    # Members-only community feed. Every view requires a signed-in account.
    path('feed/post/create/', views_comms.feed_post_create, name='feed_post_create'),
    path('feed/post/<int:pk>/edit/', views_comms.feed_post_edit, name='feed_post_edit'),
    path('feed/post/<int:pk>/share/', views_comms.feed_post_share, name='feed_post_share'),
    path('feed/post/<int:pk>/react/', views_comms.feed_post_react, name='feed_post_react'),
    path('feed/post/<int:pk>/comment/', views_comms.feed_post_comment, name='feed_post_comment'),
    path('feed/post/<int:pk>/save/', views_comms.feed_post_save, name='feed_post_save'),
    path('feed/post/<int:pk>/delete/', views_comms.feed_post_delete, name='feed_post_delete'),
    path('feed/comment/<int:pk>/delete/', views_comms.feed_comment_delete, name='feed_comment_delete'),
    path('feed/report/', views_comms.feed_report, name='feed_report'),
    path('feed/load-more/', views_comms.feed_load_more, name='feed_load_more'),
    path('feed/attachment/<int:pk>/', views_comms.feed_attachment_download, name='feed_attachment_download'),
    path('feed/poll/', views_comms.feed_poll, name='feed_poll'),
    # Signed-in member profiles (never public, never expose contact details).
    path('community/member/<str:username>/', account.account_member_profile, name='member_profile'),
    # Step 1: choose User or Church Member.
    path('register/', views.register, name='register'),
    path('register/user/', views.register_user, name='register_user'),
    path('register/church/', views.register_church, name='register_church'),
    # Existing account joins the church membership later.
    path('join-church/', views.join_church, name='join_church'),
    path(
        'login/',
        views.MemberLoginView.as_view(),
        name='login',
    ),
    path(
        'password-reset/',
        DebugLinkPasswordResetView.as_view(
            template_name='members/password_reset_form.html',
            email_template_name='members/password_reset_email.txt',
            subject_template_name='members/password_reset_subject.txt',
            success_url=reverse_lazy('members:password_reset_done'),
            reset_url_name='members:password_reset_confirm',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        DebugLinkPasswordResetDoneView.as_view(
            template_name='members/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='members/password_reset_confirm.html',
            form_class=MemberSetPasswordForm,
            success_url=reverse_lazy('members:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='members/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),
]
