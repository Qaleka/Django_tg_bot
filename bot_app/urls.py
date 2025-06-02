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
    path('select_date/', views.select_date_webapp, name='select_date'),
    path('api/save_selected_date/', views.save_selected_date, name='save_selected_date'),
    path('', lambda request: HttpResponse("✅ Всё работает!")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)