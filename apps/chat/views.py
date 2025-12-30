from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q

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
    from django.utils import timezone
    
    mute = RoomMute.objects.filter(user=user, room=room).first()
    if not mute:
        return False, None
    
    if mute.expires_at and timezone.now() > mute.expires_at:
        # Mute has expired, delete it
        mute.delete()
        return False, None
    
    return True, mute.expires_at


@login_required
def room_list(request):
    """List all public rooms and user's private rooms"""
    public_rooms = Room.objects.filter(room_type='public')
    user_rooms = Room.objects.filter(
        Q(members=request.user) | Q(created_by=request.user)
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
    
    # Get messages (exclude deleted for non-moderators)
    room_messages = room.messages.select_related('sender', 'sender__profile').all()
    
    # Get members
    members = room.members.all().select_related('profile')
    
    # Check moderation permissions
    user_can_moderate = can_moderate_room(request.user, room)
    
    # Check if user is muted
    is_muted, mute_expires = is_user_muted(request.user, room)
    
    context = {
        'room': room,
        'messages': room_messages,
        'members': members,
        'can_moderate': user_can_moderate,
        'is_muted': is_muted,
        'mute_expires': mute_expires,
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
    
    membership = RoomMembership.objects.filter(user=request.user, room=room).first()
    if membership:
        membership.delete()
        messages.success(request, f'You have left "{room.name}".')
    
    return redirect('chat:room_list')


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
    
    if request.method == 'POST':
        username = request.POST.get('username')
        from django.contrib.auth.models import User
        
        try:
            user = User.objects.get(username=username)
            membership, created = RoomMembership.objects.get_or_create(
                user=user,
                room=room,
                defaults={'role': 'member'}
            )
            
            if created:
                messages.success(request, f'{username} has been invited to the room.')
                
                # Create notification
                from apps.notifications.models import Notification
                Notification.objects.create(
                    recipient=user,
                    notification_type='invite',
                    title=f'Room Invitation',
                    message=f'{request.user.username} invited you to join "{room.name}"',
                    related_room=room
                )
            else:
                messages.info(request, f'{username} is already a member.')
        except User.DoesNotExist:
            messages.error(request, f'User "{username}" not found.')
    
    return render(request, 'chat/invite_user.html', {'room': room})


# API Views
@login_required
def api_send_message(request, slug):
    """API endpoint to send a message"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    room = get_object_or_404(Room, slug=slug)
    
    # Check if user is muted
    is_muted, _ = is_user_muted(request.user, room)
    if is_muted:
        return JsonResponse({'error': 'You are muted in this room'}, status=403)
    
    content = request.POST.get('content', '').strip()
    if not content:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)
    
    message = Message.objects.create(
        room=room,
        sender=request.user,
        content=content
    )
    
    return JsonResponse({
        'id': message.id,
        'content': message.content,
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
        'sender': msg.sender.username,
        'created_at': msg.created_at.isoformat(),
        'is_deleted': msg.is_deleted
    } for msg in room_messages]
    
    return JsonResponse({'messages': messages_data})
