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
        
        # Check if user is banned
        is_banned = await self.check_if_banned()
        if is_banned:
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
        
        # Join user-specific group for targeted messages (kick/ban)
        self.user_group_name = f'user_{self.user.id}'
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send mute status on connect
        if is_muted:
            mute_info = await self.get_mute_info()
            await self.send(text_data=json.dumps({
                'type': 'mute_status',
                'is_muted': True,
                'expires_at': mute_info
            }))
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'message')
        
        if message_type == 'message':
            message = data.get('message', '')
            username = data.get('username', '')
            image_url = data.get('image_url', None)
            
            # Refresh mute status
            is_muted = await self.check_if_muted()
            if is_muted:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You are muted in this room'
                }))
                return
            
            # Check if banned
            is_banned = await self.check_if_banned()
            if is_banned:
                await self.send(text_data=json.dumps({
                    'type': 'force_disconnect',
                    'reason': 'You are banned from this room'
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
                    'image_url': image_url,
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
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'username': event['username'],
            'image_url': event.get('image_url'),
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
    
    async def force_disconnect(self, event):
        """Handle kick/ban - force user to disconnect"""
        await self.send(text_data=json.dumps({
            'type': 'force_disconnect',
            'reason': event.get('reason', 'You have been removed from this room')
        }))
        await self.close()
    
    async def mute_status(self, event):
        """Update mute status for user"""
        await self.send(text_data=json.dumps({
            'type': 'mute_status',
            'is_muted': event.get('is_muted', False),
            'expires_at': event.get('expires_at')
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
    
    @database_sync_to_async
    def get_mute_info(self):
        from apps.moderation.models import RoomMute
        from apps.chat.models import Room
        
        try:
            room = Room.objects.get(slug=self.room_slug)
            mute = RoomMute.objects.filter(user=self.user, room=room).first()
            if mute and mute.expires_at:
                return mute.expires_at.isoformat()
            return None
        except:
            return None
    
    @database_sync_to_async
    def check_if_banned(self):
        from apps.moderation.models import ModerationAction
        from apps.chat.models import Room
        from apps.authentication.models import UserProfile
        
        # Check global ban
        try:
            profile = UserProfile.objects.get(user=self.user)
            if profile.is_currently_banned:
                return True
        except UserProfile.DoesNotExist:
            pass
        
        # Check room ban
        try:
            room = Room.objects.get(slug=self.room_slug)
            ban = ModerationAction.objects.filter(
                target_user=self.user,
                room=room,
                action_type='ban',
                is_active=True
            ).first()
            
            if not ban:
                return False
            
            if ban.expires_at and timezone.now() > ban.expires_at:
                ban.is_active = False
                ban.save()
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
        
        await self.channel_layer.group_add(
            self.presence_group,
            self.channel_name
        )
        
        await self.update_status('online')
        
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
            await self.update_status('offline')
            
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'user_status',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': 'offline'
                }
            )
            
            await self.channel_layer.group_discard(
                self.presence_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'heartbeat':
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
        
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name
        )
        
        await self.accept()
        
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