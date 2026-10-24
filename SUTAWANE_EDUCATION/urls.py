"""
URL configuration for SUTAWANE_EDUCATION project.
Production-ready routing with fail-safe media serving.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('MyApp.urls')),
]

# Ensure media files (student photos, institutional logos, bill attachments)
# remain accessible in both development and standalone/containerized production servers.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
