from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

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
