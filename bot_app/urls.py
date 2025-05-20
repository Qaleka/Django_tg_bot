from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

urlpatterns = [
    path('oauth_callback', views.oauth_callback, name='oauth_callback'),
    path('student_events', views.student_events, name='student_events'),
    path('auth_success', views.auth_success),
    path('calendar/', views.calendar_mini_app, name='calendar_mini_app'),
    path('api/calendar/events/', views.get_calendar_events, name='calendar_events_api'),
    path('api/calendar/export_ics/', views.export_ics, name='export_ics'),
    path('', lambda request: HttpResponse("✅ Всё работает!")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)