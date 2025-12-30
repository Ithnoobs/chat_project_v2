from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('create/', views.create_room, name='create_room'),
    path('room/<slug:slug>/', views.room_detail, name='room_detail'),
    path('room/<slug:slug>/join/', views.join_room, name='join_room'),
    path('room/<slug:slug>/leave/', views.leave_room, name='leave_room'),
    path('room/<slug:slug>/delete/', views.delete_room, name='delete_room'),
    path('room/<slug:slug>/invite/', views.invite_user, name='invite_user'),
    
    # API endpoints
    path('api/room/<slug:slug>/messages/', views.api_get_messages, name='api_messages'),
    path('api/room/<slug:slug>/send/', views.api_send_message, name='api_send'),
]
