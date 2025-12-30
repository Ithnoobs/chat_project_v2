import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['room_slug']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check if user is muted
        is_muted = await self.check_if_muted()
        self.is_muted = is_muted
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'message')
        
        if message_type == 'message':
            message = data.get('message', '')
            username = data.get('username', '')
            
            # Check if user is muted
            is_muted = await self.check_if_muted()
            if is_muted:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You are muted in this room'
                }))
                return
            
            # Save message to database
            saved_message = await self.save_message(message)
            
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'username': username,
                    'message_id': saved_message.id if saved_message else None,
                    'timestamp': timezone.now().isoformat()
                }
            )
        
        elif message_type == 'typing':
            username = data.get('username', '')
            is_typing = data.get('is_typing', False)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'username': username,
                    'is_typing': is_typing
                }
            )
    
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'username': event['username'],
            'message_id': event.get('message_id'),
            'timestamp': event.get('timestamp')
        }))
    
    async def typing_indicator(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
            'is_typing': event['is_typing']
        }))
    
    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id']
        }))
    
    @database_sync_to_async
    def save_message(self, content):
        from apps.chat.models import Room, Message
        
        try:
            room = Room.objects.get(slug=self.room_slug)
            message = Message.objects.create(
                room=room,
                sender=self.user,
                content=content
            )
            return message
        except Room.DoesNotExist:
            return None
    
    @database_sync_to_async
    def check_if_muted(self):
        from apps.moderation.models import RoomMute
        from apps.chat.models import Room
        
        try:
            room = Room.objects.get(slug=self.room_slug)
            mute = RoomMute.objects.filter(user=self.user, room=room).first()
            
            if not mute:
                return False
            
            if mute.expires_at and timezone.now() > mute.expires_at:
                mute.delete()
                return False
            
            return True
        except Room.DoesNotExist:
            return False


class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.presence_group = 'presence'
        
        # Join presence group
        await self.channel_layer.group_add(
            self.presence_group,
            self.channel_name
        )
        
        # Update user status to online
        await self.update_status('online')
        
        # Broadcast status to all users
        await self.channel_layer.group_send(
            self.presence_group,
            {
                'type': 'user_status',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': 'online'
            }
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Update user status to offline
            await self.update_status('offline')
            
            # Broadcast status to all users
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'user_status',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': 'offline'
                }
            )
            
            # Leave presence group
            await self.channel_layer.group_discard(
                self.presence_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'heartbeat':
            # Keep connection alive and update last seen
            await self.update_last_seen()
        
        elif message_type == 'status_change':
            new_status = data.get('status', 'online')
            await self.update_status(new_status)
            
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'user_status',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': new_status
                }
            )
    
    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'status',
            'user_id': event['user_id'],
            'username': event['username'],
            'status': event['status']
        }))
    
    @database_sync_to_async
    def update_status(self, status):
        from apps.authentication.models import UserProfile
        
        try:
            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.online_status = status
            profile.save(update_fields=['online_status'])
        except Exception:
            pass
    
    @database_sync_to_async
    def update_last_seen(self):
        from apps.authentication.models import UserProfile
        
        try:
            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.last_seen = timezone.now()
            profile.save(update_fields=['last_seen'])
        except Exception:
            pass


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.notification_group = f'notifications_{self.user.id}'
        
        # Join user's notification group
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name
        )
        
        await self.accept()
        
        # Send unread count on connect
        unread_count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'unread_count',
            'count': unread_count
        }))
    
    async def disconnect(self, close_code):
        if hasattr(self, 'notification_group'):
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'mark_read':
            notification_id = data.get('notification_id')
            await self.mark_notification_read(notification_id)
            
            unread_count = await self.get_unread_count()
            await self.send(text_data=json.dumps({
                'type': 'unread_count',
                'count': unread_count
            }))
    
    async def new_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))
    
    async def unread_count_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'unread_count',
            'count': event['count']
        }))
    
    @database_sync_to_async
    def get_unread_count(self):
        from apps.notifications.models import Notification
        return Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).count()
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from apps.notifications.models import Notification
        
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.mark_as_read()
        except Notification.DoesNotExist:
            pass
