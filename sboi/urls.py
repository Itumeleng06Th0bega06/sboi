import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('', include('home.urls')),
    path('about/', include('about.urls')),
    path('blackboard/', include('blackboard.urls')),
    path('contact/', include('contact.urls')),
    path('gallery/', include('gallery.urls')),
    path('members/', include('members.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
elif os.environ.get('SERVE_MEDIA', 'true').lower() == 'true':
    # Testing phase only — serves seeded media from Render's local disk.
    # Replace with S3-compatible storage before real admin uploads go live.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
