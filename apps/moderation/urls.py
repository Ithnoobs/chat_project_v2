from django.urls import path
from . import views

app_name = 'moderation'

urlpatterns = [
    # Dashboard
    path('', views.moderation_dashboard, name='dashboard'),
    
    # Reports
    path('reports/', views.reports_list, name='reports_list'),
    path('reports/<int:report_id>/review/', views.review_report, name='review_report'),
    path('report/<int:message_id>/', views.report_message, name='report_message'),
    
    # User Actions
    path('ban/<int:user_id>/', views.ban_user, name='ban_user'),
    path('ban/<int:user_id>/room/<int:room_id>/', views.ban_user, name='ban_user_room'),
    path('unban/<int:user_id>/', views.unban_user, name='unban_user'),
    path('unban/<int:user_id>/room/<int:room_id>/', views.unban_user, name='unban_user_room'),
    path('mute/<int:user_id>/room/<int:room_id>/', views.mute_user, name='mute_user'),
    path('unmute/<int:user_id>/room/<int:room_id>/', views.unmute_user, name='unmute_user'),
    path('kick/<int:user_id>/room/<int:room_id>/', views.kick_user, name='kick_user'),
    path('warn/<int:user_id>/', views.warn_user, name='warn_user'),
    path('warn/<int:user_id>/room/<int:room_id>/', views.warn_user, name='warn_user_room'),
    path('delete-message/<int:message_id>/', views.delete_message, name='delete_message'),
    
    # Room Moderation
    path('room/<int:room_id>/', views.room_moderation, name='room_moderation'),
    
    # Admin User Management
    path('users/', views.admin_user_list, name='admin_user_list'),
    path('users/<int:user_id>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('users/<int:user_id>/delete/', views.admin_user_delete, name='admin_user_delete'),
    
    # Logs
    path('logs/', views.moderation_logs, name='logs'),
    
    # AJAX
    path('api/check-muted/<int:user_id>/<int:room_id>/', views.check_user_muted, name='check_muted'),
]
