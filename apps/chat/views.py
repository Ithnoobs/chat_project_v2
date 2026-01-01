from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Room, RoomMembership, Message
from .forms import RoomForm, MessageForm


def can_moderate_room(user, room):
    """Check if user can moderate a specific room"""
    if user.is_staff or user.is_superuser:
        return True
    if room.created_by == user:
        return True
    membership = RoomMembership.objects.filter(user=user, room=room).first()
    return membership and membership.role in ['admin', 'moderator']


def is_user_muted(user, room):
    """Check if user is muted in a room"""
    from apps.moderation.models import RoomMute
    
    mute = RoomMute.objects.filter(user=user, room=room).first()
    if not mute:
        return False, None
    
    if mute.expires_at and timezone.now() > mute.expires_at:
        mute.delete()
        return False, None
    
    return True, mute


def is_user_banned_from_room(user, room):
    """Check if user is banned from a specific room"""
    from apps.moderation.models import ModerationAction
    
    # Check for active room ban
    ban = ModerationAction.objects.filter(
        target_user=user,
        room=room,
        action_type='ban',
        is_active=True
    ).first()
    
    if not ban:
        return False
    
    # Check if ban has expired
    if ban.expires_at and timezone.now() > ban.expires_at:
        ban.is_active = False
        ban.save()
        return False
    
    return True


@login_required
def room_list(request):
    """List all public rooms and user's private rooms"""
    # Get rooms user is a member of or created
    user_room_ids = RoomMembership.objects.filter(user=request.user).values_list('room_id', flat=True)
    
    # Public rooms EXCLUDING ones the user has already joined or created
    public_rooms = Room.objects.filter(room_type='public').exclude(
        Q(id__in=user_room_ids) | Q(created_by=request.user)
    )
    
    # User's rooms (joined or created)
    user_rooms = Room.objects.filter(
        Q(id__in=user_room_ids) | Q(created_by=request.user)
    ).distinct()
    
    context = {
        'public_rooms': public_rooms,
        'user_rooms': user_rooms,
    }
    return render(request, 'chat/room_list.html', context)


@login_required
def room_detail(request, slug):
    """View a chat room"""
    room = get_object_or_404(Room, slug=slug)
    
    # Check if user is banned from this room
    if is_user_banned_from_room(request.user, room):
        messages.error(request, "You are banned from this room.")
        return redirect('chat:room_list')
    
    # Check global ban
    try:
        if request.user.profile.is_currently_banned:
            messages.error(request, "Your account is banned.")
            return redirect('chat:room_list')
    except:
        pass
    
    # Check if user can access the room
    if room.room_type == 'private':
        is_member = RoomMembership.objects.filter(user=request.user, room=room).exists()
        if not is_member and room.created_by != request.user:
            messages.error(request, "You don't have access to this private room.")
            return redirect('chat:room_list')
    
    # Auto-join public rooms
    if room.room_type == 'public':
        membership, created = RoomMembership.objects.get_or_create(
            user=request.user, 
            room=room,
            defaults={'role': 'member'}
        )
    
    # Update last_read_at for the user
    membership = RoomMembership.objects.filter(user=request.user, room=room).first()
    if membership:
        membership.last_read_at = timezone.now()
        membership.save(update_fields=['last_read_at'])
    
    # Get messages (exclude deleted for non-moderators)
    room_messages = room.messages.select_related('sender', 'sender__profile').all()
    
    # Get members with fresh profile data
    members = room.members.all().select_related('profile')
    
    # Check moderation permissions
    user_can_moderate = can_moderate_room(request.user, room)
    
    # Check if user is muted
    is_muted, mute_info = is_user_muted(request.user, room)
    
    # Check if user can leave (not the creator)
    can_leave = room.created_by != request.user
    
    context = {
        'room': room,
        'messages': room_messages,
        'members': members,
        'can_moderate': user_can_moderate,
        'is_muted': is_muted,
        'mute_info': mute_info,
        'can_leave': can_leave,
    }
    return render(request, 'chat/room_detail.html', context)


@login_required
def create_room(request):
    """Create a new chat room"""
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.created_by = request.user
            room.save()
            
            # Add creator as admin member
            RoomMembership.objects.create(
                user=request.user,
                room=room,
                role='admin'
            )
            
            messages.success(request, f'Room "{room.name}" created successfully!')
            return redirect('chat:room_detail', slug=room.slug)
    else:
        form = RoomForm()
    
    return render(request, 'chat/create_room.html', {'form': form})


@login_required
def join_room(request, slug):
    """Join a chat room"""
    room = get_object_or_404(Room, slug=slug)
    
    # Check if banned
    if is_user_banned_from_room(request.user, room):
        messages.error(request, "You are banned from this room.")
        return redirect('chat:room_list')
    
    if room.room_type == 'private':
        messages.error(request, "This is a private room. You need an invitation to join.")
        return redirect('chat:room_list')
    
    membership, created = RoomMembership.objects.get_or_create(
        user=request.user,
        room=room,
        defaults={'role': 'member'}
    )

    if created:
        messages.success(request, f'You have joined "{room.name}"!')

        # Broadcast member joined via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'chat_{room.slug}',
            {
                'type': 'member_added',
                'user_id': request.user.id,
                'username': request.user.username,
                'is_owner': False
            }
        )
    else:
        messages.info(request, f'You are already a member of "{room.name}".')

    return redirect('chat:room_detail', slug=room.slug)


@login_required
def leave_room(request, slug):
    """Leave a chat room"""
    room = get_object_or_404(Room, slug=slug)
    
    if room.created_by == request.user:
        messages.error(request, "You cannot leave a room you created. Delete it instead.")
        return redirect('chat:room_detail', slug=room.slug)
    
    if request.method == 'POST':
        membership = RoomMembership.objects.filter(user=request.user, room=room).first()
        if membership:
            membership.delete()
            messages.success(request, f'You have left "{room.name}".')

            # Broadcast member left via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'chat_{room.slug}',
                {
                    'type': 'member_removed',
                    'user_id': request.user.id,
                    'username': request.user.username
                }
            )
        return redirect('chat:room_list')

    return render(request, 'chat/leave_room.html', {'room': room})


@login_required
def delete_room(request, slug):
    """Delete a chat room (creator only)"""
    room = get_object_or_404(Room, slug=slug)
    
    if room.created_by != request.user and not request.user.is_staff:
        messages.error(request, "Only the room creator can delete this room.")
        return redirect('chat:room_detail', slug=room.slug)
    
    if request.method == 'POST':
        room_name = room.name
        room.delete()
        messages.success(request, f'Room "{room_name}" has been deleted.')
        return redirect('chat:room_list')
    
    return render(request, 'chat/delete_room.html', {'room': room})


@login_required
def invite_user(request, slug):
    """Invite a user to a private room"""
    room = get_object_or_404(Room, slug=slug)
    
    if room.room_type != 'private':
        messages.error(request, "This room is public. Anyone can join.")
        return redirect('chat:room_detail', slug=room.slug)
    
    if not can_moderate_room(request.user, room):
        messages.error(request, "You don't have permission to invite users.")
        return redirect('chat:room_detail', slug=room.slug)
    
    # Get all users except current members
    current_member_ids = room.members.values_list('id', flat=True)
    available_users = User.objects.exclude(
        Q(id__in=current_member_ids) | Q(id=room.created_by.id)
    ).select_related('profile')
    
    if request.method == 'POST':
        user_ids = request.POST.getlist('user_ids')
        invited_count = 0
        
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                membership, created = RoomMembership.objects.get_or_create(
                    user=user,
                    room=room,
                    defaults={'role': 'member'}
                )
                
                if created:
                    invited_count += 1
                    # Create notification
                    from apps.notifications.models import Notification
                    Notification.objects.create(
                        recipient=user,
                        notification_type='invite',
                        title='Room Invitation',
                        message=f'{request.user.username} invited you to join "{room.name}"',
                        related_room=room
                    )

                    # Broadcast member added via WebSocket
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f'chat_{room.slug}',
                        {
                            'type': 'member_added',
                            'user_id': user.id,
                            'username': user.username,
                            'is_owner': False
                        }
                    )
            except User.DoesNotExist:
                continue

        if invited_count > 0:
            messages.success(request, f'{invited_count} user(s) have been invited to the room.')
        else:
            messages.info(request, 'No new users were invited.')

        return redirect('chat:room_detail', slug=room.slug)
    
    return render(request, 'chat/invite_user.html', {
        'room': room,
        'available_users': available_users,
    })


@login_required
def report_user(request, slug, user_id):
    """Report a user in a room"""
    room = get_object_or_404(Room, slug=slug)
    target_user = get_object_or_404(User, id=user_id)
    
    if target_user == request.user:
        messages.error(request, "You cannot report yourself.")
        return redirect('chat:room_detail', slug=slug)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if reason:
            from apps.moderation.models import Report
            # Create a report without a specific message
            Report.objects.create(
                reported_by=request.user,
                message=None,
                reported_user=target_user,
                room=room,
                reason=reason
            )
            messages.success(request, f"User {target_user.username} has been reported.")
        return redirect('chat:room_detail', slug=slug)
    
    return render(request, 'chat/report_user.html', {
        'room': room,
        'target_user': target_user,
    })


# API Views
@login_required
def api_send_message(request, slug):
    """API endpoint to send a message with optional image"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    room = get_object_or_404(Room, slug=slug)
    
    # Check if user is banned
    if is_user_banned_from_room(request.user, room):
        return JsonResponse({'error': 'You are banned from this room'}, status=403)
    
    # Check if user is muted
    is_muted, _ = is_user_muted(request.user, room)
    if is_muted:
        return JsonResponse({'error': 'You are muted in this room'}, status=403)
    
    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')
    
    if not content and not image:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)
    
    message = Message.objects.create(
        room=room,
        sender=request.user,
        content=content,
        image=image
    )
    
    return JsonResponse({
        'id': message.id,
        'content': message.content,
        'image_url': message.image.url if message.image else None,
        'sender': message.sender.username,
        'created_at': message.created_at.isoformat()
    })


@login_required
def api_get_messages(request, slug):
    """API endpoint to get messages"""
    room = get_object_or_404(Room, slug=slug)
    
    last_id = request.GET.get('last_id', 0)
    room_messages = room.messages.filter(id__gt=last_id).select_related('sender')[:50]
    
    messages_data = [{
        'id': msg.id,
        'content': msg.content if not msg.is_deleted else '[Message deleted]',
        'image_url': msg.image.url if msg.image and not msg.is_deleted else None,
        'sender': msg.sender.username,
        'created_at': msg.created_at.isoformat(),
        'is_deleted': msg.is_deleted
    } for msg in room_messages]
    
    return JsonResponse({'messages': messages_data})