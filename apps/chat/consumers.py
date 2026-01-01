import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.auth.models import User


class ChatConsumer(AsyncWebsocketConsumer):
    # Track connected users per room (class-level)
    room_users = {}  # {room_slug: {user_id: channel_name}}
    
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['room_slug']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check if user is banned or not a member
        is_allowed = await self.check_room_access()
        if not is_allowed:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Join user-specific group for targeted messages (mute, kick, ban, warn)
        self.user_group_name = f'user_{self.user.id}_{self.room_slug}'
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Track user in room
        if self.room_slug not in ChatConsumer.room_users:
            ChatConsumer.room_users[self.room_slug] = {}
        
        is_new_connection = self.user.id not in ChatConsumer.room_users[self.room_slug]
        ChatConsumer.room_users[self.room_slug][self.user.id] = self.channel_name
        
        # Check mute status
        self.is_muted = await self.check_mute_status()
        
        # Broadcast user online status change (update the dot)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_status_change',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': 'online'
            }
        )
        
        # Update user online status in database
        await self.set_user_online(True)
    
    async def disconnect(self, close_code):
        # Remove user from room tracking
        if self.room_slug in ChatConsumer.room_users:
            if hasattr(self, 'user') and self.user.id in ChatConsumer.room_users[self.room_slug]:
                del ChatConsumer.room_users[self.room_slug][self.user.id]
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Leave user-specific group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        
        # Broadcast user offline status (update the dot)
        if hasattr(self, 'user') and self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status_change',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'status': 'offline'
                }
            )
            
            # Update user online status in database
            await self.set_user_online(False)
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')
            
            if message_type == 'message':
                await self.handle_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat()
        except json.JSONDecodeError:
            await self.send_error('Invalid message format')
    
    async def handle_message(self, data):
        message = data.get('message', '').strip()
        image_url = data.get('image_url')
        message_id = data.get('message_id')
        
        # Check if user is muted
        if await self.check_mute_status():
            await self.send_error('You are muted in this room')
            return
        
        if not message and not image_url:
            return
        
        # Save message to database if not already saved (text-only messages)
        if not message_id and message:
            message_id = await self.save_message(message)
        
        # Broadcast to room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': self.user.username,
                'user_id': self.user.id,
                'image_url': image_url,
                'message_id': message_id,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    async def handle_typing(self, data):
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'username': self.user.username,
                'user_id': self.user.id,
                'is_typing': is_typing
            }
        )
    
    async def handle_heartbeat(self):
        # Update last activity timestamp
        await self.set_user_online(True)
    
    # =========================================================================
    # Event Handlers (received from channel layer)
    # =========================================================================
    
    async def chat_message(self, event):
        """Handle incoming chat message"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event.get('message'),
            'username': event.get('username'),
            'user_id': event.get('user_id'),
            'image_url': event.get('image_url'),
            'message_id': event.get('message_id'),
            'timestamp': event.get('timestamp')
        }))
    
    async def typing_indicator(self, event):
        """Handle typing indicator"""
        # Don't send to the user who is typing
        if event.get('user_id') == self.user.id:
            return
        
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event.get('username'),
            'is_typing': event.get('is_typing')
        }))
    
    async def message_deleted(self, event):
        """Handle message deletion"""
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event.get('message_id')
        }))
    
    async def user_status_change(self, event):
        """Handle user online/offline status change - update dots only"""
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'user_id': event.get('user_id'),
            'username': event.get('username'),
            'status': event.get('status')
        }))
    
    async def member_added(self, event):
        """Handle new member being added to room (via invitation)"""
        await self.send(text_data=json.dumps({
            'type': 'member_added',
            'user_id': event.get('user_id'),
            'username': event.get('username'),
            'is_owner': event.get('is_owner', False)
        }))
    
    async def member_removed(self, event):
        """Handle member being removed from room (kick/ban/leave)"""
        await self.send(text_data=json.dumps({
            'type': 'member_removed',
            'user_id': event.get('user_id'),
            'username': event.get('username')
        }))
    
    async def mute_status(self, event):
        """
        Handle mute status update.
        Only process if this message is for the current user.
        Updates UI without disconnecting.
        """
        target_user_id = event.get('user_id')
        
        # Only process if this message is for the current user
        if target_user_id and target_user_id != self.user.id:
            return
        
        is_muted = event.get('is_muted', False)
        expires_at = event.get('expires_at')
        
        # Update local state
        self.is_muted = is_muted
        
        # Send mute status to client - DO NOT close connection
        await self.send(text_data=json.dumps({
            'type': 'mute_status',
            'is_muted': is_muted,
            'expires_at': expires_at
        }))
    
    async def force_disconnect(self, event):
        """
        Handle forced disconnect (kick/ban).
        Only process if this message is for the current user.
        Sends alert data BEFORE closing connection.
        """
        target_user_id = event.get('user_id')
        
        # Only process if this message is for the current user
        if target_user_id and target_user_id != self.user.id:
            return
        
        action = event.get('action', 'removed')
        reason = event.get('reason', 'You have been removed from this room.')
        
        # Send disconnect notice to client FIRST
        await self.send(text_data=json.dumps({
            'type': 'force_disconnect',
            'action': action,
            'reason': reason
        }))
        
        # Then close the connection
        await self.close()
    
    async def warning_received(self, event):
        """
        Handle warning notification.
        Only process if this message is for the current user.
        Shows warning dialog to the user.
        """
        target_user_id = event.get('user_id')
        
        # Only process if this message is for the current user
        if target_user_id and target_user_id != self.user.id:
            return
        
        # Send warning to client
        await self.send(text_data=json.dumps({
            'type': 'warning',
            'reason': event.get('reason', 'You have received a warning.'),
            'issued_by': event.get('issued_by', 'Moderator'),
            'room_name': event.get('room_name', '')
        }))
    
    async def send_error(self, message):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
    
    # =========================================================================
    # Database Operations
    # =========================================================================
    
    @database_sync_to_async
    def check_room_access(self):
        """Check if user can access this room (is member and not banned)"""
        from apps.chat.models import Room, RoomMembership
        from apps.moderation.models import ModerationAction
        from django.db.models import Q
        
        try:
            room = Room.objects.get(slug=self.room_slug)
            self.room = room
            
            # Check if user is a member
            is_member = RoomMembership.objects.filter(
                user=self.user,
                room=room
            ).exists()
            
            if not is_member:
                return False
            
            # Check if user is banned from this room
            is_banned = ModerationAction.objects.filter(
                target_user=self.user,
                room=room,
                action_type='ban',
                is_active=True
            ).filter(
                Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
            ).exists()
            
            return not is_banned
            
        except Room.DoesNotExist:
            return False
    
    @database_sync_to_async
    def check_mute_status(self):
        """Check if user is muted in this room"""
        from apps.moderation.models import RoomMute
        from django.db.models import Q
        
        mute = RoomMute.objects.filter(
            user=self.user,
            room=self.room
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).first()
        
        return mute is not None
    
    @database_sync_to_async
    def save_message(self, content):
        """Save a text message to the database"""
        from apps.chat.models import Message
        
        message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content=content
        )
        return message.id
    
    @database_sync_to_async
    def set_user_online(self, is_online):
        """Update user's online status"""
        from apps.authentication.models import UserProfile
        
        try:
            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.online_status = 'online' if is_online else 'offline'
            profile.last_seen = timezone.now()
            profile.save(update_fields=['online_status', 'last_seen'])
        except Exception:
            pass


class PresenceConsumer(AsyncWebsocketConsumer):
    """
    Handles user presence (online/offline status) across the application.
    """
    
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
        
        await self.accept()
        
        # Set user online
        await self.set_user_status('online')
        
        # Broadcast status change
        await self.channel_layer.group_send(
            self.presence_group,
            {
                'type': 'status_update',
                'user_id': self.user.id,
                'status': 'online'
            }
        )
    
    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Set user offline
            await self.set_user_status('offline')
            
            # Broadcast status change
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'status_update',
                    'user_id': self.user.id,
                    'status': 'offline'
                }
            )
        
        # Leave presence group
        if hasattr(self, 'presence_group'):
            await self.channel_layer.group_discard(
                self.presence_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'heartbeat':
                # Update last activity
                await self.set_user_status('online')
        except json.JSONDecodeError:
            pass
    
    async def status_update(self, event):
        """Handle status update from other users"""
        await self.send(text_data=json.dumps({
            'type': 'status',
            'user_id': event.get('user_id'),
            'status': event.get('status')
        }))
    
    @database_sync_to_async
    def set_user_status(self, status):
        """Update user's online status in database"""
        from apps.authentication.models import UserProfile
        
        try:
            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            profile.online_status = status
            profile.last_seen = timezone.now()
            profile.save(update_fields=['online_status', 'last_seen'])
        except Exception:
            pass


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time notifications for users.
    """
    
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
    
    async def disconnect(self, close_code):
        if hasattr(self, 'notification_group'):
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_read':
                notification_id = data.get('notification_id')
                if notification_id:
                    await self.mark_notification_read(notification_id)
            elif message_type == 'mark_all_read':
                await self.mark_all_notifications_read()
        except json.JSONDecodeError:
            pass
    
    async def send_notification(self, event):
        """Send notification to user"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'id': event.get('id'),
            'title': event.get('title'),
            'message': event.get('message'),
            'notification_type': event.get('notification_type'),
            'link': event.get('link'),
            'created_at': event.get('created_at')
        }))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a specific notification as read"""
        from apps.notifications.models import Notification
        
        try:
            Notification.objects.filter(
                id=notification_id,
                recipient=self.user
            ).update(is_read=True)
        except Exception:
            pass
    
    @database_sync_to_async
    def mark_all_notifications_read(self):
        """Mark all notifications as read"""
        from apps.notifications.models import Notification
        
        try:
            Notification.objects.filter(
                recipient=self.user,
                is_read=False
            ).update(is_read=True)
        except Exception:
            pass