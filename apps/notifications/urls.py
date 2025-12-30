from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='list'),
    path('<int:notification_id>/read/', views.mark_as_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('<int:notification_id>/delete/', views.delete_notification, name='delete'),
    path('clear-all/', views.clear_all, name='clear_all'),
    
    # API endpoints
    path('api/', views.api_get_notifications, name='api_list'),
    path('api/<int:notification_id>/read/', views.api_mark_read, name='api_mark_read'),
]
