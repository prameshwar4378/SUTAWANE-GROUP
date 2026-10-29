"""
URL configuration for SUTAWANE_EDUCATION project.
Production-ready routing with fail-safe media serving.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.views.decorators.cache import cache_control

# Wrap media serving with 24-hour browser caching for student photos and logos
cached_media_serve = cache_control(public=True, max_age=86400)(serve)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('MyApp.urls')),
]

# Ensure media files (student photos, institutional logos, bill attachments)
# are served with browser caching to eliminate repetitive disk and socket reads.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', cached_media_serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
