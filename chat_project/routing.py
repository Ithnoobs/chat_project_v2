from django.urls import re_path
from apps.chat import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_slug>[\w-]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/presence/$', consumers.PresenceConsumer.as_asgi()),
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
