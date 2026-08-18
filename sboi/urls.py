from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

handler400 = views.handler400
handler403 = views.handler403
handler404 = views.handler404
handler500 = views.handler500

urlpatterns = [
    path(settings.ADMIN_URL + 'search/', admin.site.admin_view(views.admin_search), name='admin_search'),
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
