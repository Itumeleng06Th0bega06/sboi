from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from . import views
from .admin_forms import EmailOrUsernameAdminAuthenticationForm

# Staff sign in to the admin with a username *or* an email address.
admin.site.login_form = EmailOrUsernameAdminAuthenticationForm

handler400 = views.handler400
handler403 = views.handler403
handler404 = views.handler404
handler500 = views.handler500

urlpatterns = [
    # Staff password reset, kept under the secret admin path so it stays off
    # the public site. The "admin_"-prefixed names match the link rendered by
    # templates/admin/login.html ({% url 'admin_password_reset' %}).
    path(
        settings.ADMIN_URL + 'password_reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('admin_password_reset_done'),
        ),
        name='admin_password_reset',
    ),
    path(
        settings.ADMIN_URL + 'password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='admin_password_reset_done',
    ),
    path(
        settings.ADMIN_URL + 'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('admin_password_reset_complete'),
        ),
        name='admin_password_reset_confirm',
    ),
    path(
        settings.ADMIN_URL + 'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='admin_password_reset_complete',
    ),
    path(settings.ADMIN_URL + 'notifications/', admin.site.admin_view(views.admin_notifications_api), name='admin_notifications'),
    path(settings.ADMIN_URL + 'search/', admin.site.admin_view(views.admin_search), name='admin_search'),
    path(settings.ADMIN_URL + 'section/<str:app_label>/', admin.site.admin_view(views.admin_section), name='admin_section'),
    path(settings.ADMIN_URL, admin.site.urls),
    path('', include('home.urls')),
    path('about/', include('about.urls')),
    path('values/', include('values.urls')),
    path('blackboard/', include('blackboard.urls')),
    path('contact/', include('contact.urls')),
    path('gallery/', include('gallery.urls')),
    path('members/', include('members.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
