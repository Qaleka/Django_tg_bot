from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('oauth_callback', views.oauth_callback, name='oauth_callback'),
    path('student_events', views.student_events, name='student_events'),
    path('auth_success', views.auth_success),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)