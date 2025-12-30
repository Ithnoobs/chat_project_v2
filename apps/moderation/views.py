from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator

from .models import Report, ModerationAction, RoomMute, Warning
from .forms import (
    ReportForm, ReportReviewForm, BanUserForm, MuteUserForm, 
    WarnUserForm, KickUserForm, AdminUserEditForm
)
from apps.chat.models import Room, RoomMembership, Message
from apps.authentication.models import UserProfile


def is_staff_or_admin(user):
    """Check if user is staff or admin"""
    return user.is_staff or user.is_superuser


def can_moderate_room(user, room):
    """Check if user can moderate a specific room"""
    if user.is_staff or user.is_superuser:
        return True
    # Room creator can moderate
    if room.created_by == user:
        return True
    # Check if user has admin/moderator role in room
    membership = RoomMembership.objects.filter(user=user, room=room).first()
    return membership and membership.role in ['admin', 'moderator']


# =============================================================================
# Report Views
# =============================================================================

@login_required
def report_message(request, message_id):
    """Allow users to report a message"""
    message = get_object_or_404(Message, id=message_id)
    
    # Can't report own messages
    if message.sender == request.user:
        messages.error(request, "You cannot report your own messages.")
        return redirect('chat:room_detail', slug=message.room.slug)
    
    # Check if already reported by this user
    existing_report = Report.objects.filter(
        reported_by=request.user, 
        message=message,
        status='pending'
    ).exists()
    
    if existing_report:
        messages.warning(request, "You have already reported this message.")
        return redirect('chat:room_detail', slug=message.room.slug)
    
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reported_by = request.user
            report.message = message
            report.save()
            messages.success(request, "Message reported. A moderator will review it.")
            return redirect('chat:room_detail', slug=message.room.slug)
    else:
        form = ReportForm()
    
    return render(request, 'moderation/report_message.html', {
        'form': form,
        'message': message
    })


# =============================================================================
# Moderation Panel Views
# =============================================================================

@login_required
def moderation_dashboard(request):
    """Main moderation dashboard"""
    user = request.user
    
    # Get rooms user can moderate
    if user.is_staff or user.is_superuser:
        moderable_rooms = Room.objects.all()
        pending_reports = Report.objects.filter(status='pending')
        is_global_admin = True
    else:
        # Get rooms where user is creator or has admin/moderator role
        created_rooms = Room.objects.filter(created_by=user)
        admin_memberships = RoomMembership.objects.filter(
            user=user, 
            role__in=['admin', 'moderator']
        ).values_list('room_id', flat=True)
        moderable_rooms = Room.objects.filter(
            Q(created_by=user) | Q(id__in=admin_memberships)
        ).distinct()
        
        # Only show reports for rooms user can moderate
        pending_reports = Report.objects.filter(
            status='pending',
            message__room__in=moderable_rooms
        )
        is_global_admin = False
    
    if not moderable_rooms.exists() and not user.is_staff:
        messages.info(request, "You don't have moderation permissions for any rooms.")
        return redirect('chat:room_list')
    
    # Get recent actions
    if is_global_admin:
        recent_actions = ModerationAction.objects.all()[:10]
    else:
        recent_actions = ModerationAction.objects.filter(room__in=moderable_rooms)[:10]
    
    context = {
        'moderable_rooms': moderable_rooms,
        'pending_reports_count': pending_reports.count(),
        'pending_reports': pending_reports[:5],
        'recent_actions': recent_actions,
        'is_global_admin': is_global_admin,
    }
    return render(request, 'moderation/dashboard.html', context)


@login_required
def reports_list(request):
    """List all reports (filtered by moderator's scope)"""
    user = request.user
    status_filter = request.GET.get('status', 'all')
    
    if user.is_staff or user.is_superuser:
        reports = Report.objects.all()
    else:
        moderable_rooms = get_moderable_rooms(user)
        reports = Report.objects.filter(message__room__in=moderable_rooms)
    
    if status_filter != 'all':
        reports = reports.filter(status=status_filter)
    
    paginator = Paginator(reports, 20)
    page = request.GET.get('page')
    reports = paginator.get_page(page)
    
    return render(request, 'moderation/reports_list.html', {
        'reports': reports,
        'status_filter': status_filter,
    })


@login_required
def review_report(request, report_id):
    """Review and act on a report"""
    report = get_object_or_404(Report, id=report_id)
    user = request.user
    
    # Check permissions
    if not user.is_staff and not user.is_superuser:
        if not can_moderate_room(user, report.message.room):
            return HttpResponseForbidden("You don't have permission to review this report.")
    
    if request.method == 'POST':
        form = ReportReviewForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save(commit=False)
            report.reviewed_by = user
            report.reviewed_at = timezone.now()
            report.save()
            messages.success(request, f"Report marked as {report.status}.")
            return redirect('moderation:reports_list')
    else:
        form = ReportReviewForm(instance=report)
    
    return render(request, 'moderation/review_report.html', {
        'report': report,
        'form': form,
    })


# =============================================================================
# User Moderation Actions
# =============================================================================

@login_required
def ban_user(request, user_id, room_id=None):
    """Ban a user (globally if admin, or from specific room)"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id) if room_id else None
    
    # Permission check
    if room:
        if not can_moderate_room(request.user, room):
            return HttpResponseForbidden("You don't have permission to moderate this room.")
    else:
        if not request.user.is_staff and not request.user.is_superuser:
            return HttpResponseForbidden("Only administrators can issue global bans.")
    
    # Can't ban yourself
    if target_user == request.user:
        messages.error(request, "You cannot ban yourself.")
        return redirect('moderation:dashboard')
    
    # Can't ban admins unless you're superuser
    if target_user.is_staff and not request.user.is_superuser:
        messages.error(request, "You cannot ban staff members.")
        return redirect('moderation:dashboard')
    
    if request.method == 'POST':
        form = BanUserForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            duration = form.cleaned_data.get('duration')
            is_global = form.cleaned_data.get('is_global', False)
            
            expires_at = None
            if duration:
                expires_at = timezone.now() + timezone.timedelta(minutes=duration)
            
            if is_global and (request.user.is_staff or request.user.is_superuser):
                # Global ban - update user profile
                profile, _ = UserProfile.objects.get_or_create(user=target_user)
                profile.is_banned = True
                profile.ban_reason = reason
                profile.banned_until = expires_at
                profile.save()
                
                action_room = None
            else:
                # Room-specific ban - remove from room
                RoomMembership.objects.filter(user=target_user, room=room).delete()
                action_room = room
            
            # Log the action
            ModerationAction.objects.create(
                moderator=request.user,
                target_user=target_user,
                action_type='ban',
                reason=reason,
                room=action_room,
                duration=duration,
                expires_at=expires_at
            )
            
            scope = "globally" if is_global and not room else f"from {room.name}" if room else "globally"
            messages.success(request, f"{target_user.username} has been banned {scope}.")
            return redirect('moderation:dashboard')
    else:
        form = BanUserForm()
    
    return render(request, 'moderation/ban_user.html', {
        'form': form,
        'target_user': target_user,
        'room': room,
    })


@login_required
def unban_user(request, user_id, room_id=None):
    """Unban a user"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id) if room_id else None
    
    # Permission check
    if room:
        if not can_moderate_room(request.user, room):
            return HttpResponseForbidden("You don't have permission.")
    else:
        if not request.user.is_staff and not request.user.is_superuser:
            return HttpResponseForbidden("Only administrators can remove global bans.")
    
    if request.method == 'POST':
        if not room:
            # Remove global ban
            profile = get_object_or_404(UserProfile, user=target_user)
            profile.is_banned = False
            profile.ban_reason = ''
            profile.banned_until = None
            profile.save()
        
        # Log the action
        ModerationAction.objects.create(
            moderator=request.user,
            target_user=target_user,
            action_type='unban',
            reason='Ban removed',
            room=room
        )
        
        messages.success(request, f"{target_user.username} has been unbanned.")
        return redirect('moderation:dashboard')
    
    return render(request, 'moderation/unban_user.html', {
        'target_user': target_user,
        'room': room,
    })


@login_required
def mute_user(request, user_id, room_id):
    """Mute a user in a specific room"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id)
    
    if not can_moderate_room(request.user, room):
        return HttpResponseForbidden("You don't have permission to moderate this room.")
    
    if target_user == request.user:
        messages.error(request, "You cannot mute yourself.")
        return redirect('moderation:room_moderation', room_id=room.id)
    
    if request.method == 'POST':
        form = MuteUserForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            duration = form.cleaned_data.get('duration')
            
            expires_at = None
            if duration:
                expires_at = timezone.now() + timezone.timedelta(minutes=duration)
            
            # Create or update mute
            mute, created = RoomMute.objects.update_or_create(
                user=target_user,
                room=room,
                defaults={
                    'muted_by': request.user,
                    'reason': reason,
                    'expires_at': expires_at
                }
            )
            
            # Log the action
            ModerationAction.objects.create(
                moderator=request.user,
                target_user=target_user,
                action_type='mute',
                reason=reason,
                room=room,
                duration=duration,
                expires_at=expires_at
            )
            
            messages.success(request, f"{target_user.username} has been muted in {room.name}.")
            return redirect('moderation:room_moderation', room_id=room.id)
    else:
        form = MuteUserForm()
    
    return render(request, 'moderation/mute_user.html', {
        'form': form,
        'target_user': target_user,
        'room': room,
    })


@login_required
def unmute_user(request, user_id, room_id):
    """Unmute a user in a specific room"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id)
    
    if not can_moderate_room(request.user, room):
        return HttpResponseForbidden("You don't have permission.")
    
    if request.method == 'POST':
        RoomMute.objects.filter(user=target_user, room=room).delete()
        
        ModerationAction.objects.create(
            moderator=request.user,
            target_user=target_user,
            action_type='unmute',
            reason='Mute removed',
            room=room
        )
        
        messages.success(request, f"{target_user.username} has been unmuted.")
        return redirect('moderation:room_moderation', room_id=room.id)
    
    return render(request, 'moderation/unmute_user.html', {
        'target_user': target_user,
        'room': room,
    })


@login_required
def kick_user(request, user_id, room_id):
    """Kick a user from a room (remove membership)"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id)
    
    if not can_moderate_room(request.user, room):
        return HttpResponseForbidden("You don't have permission to moderate this room.")
    
    if target_user == request.user:
        messages.error(request, "You cannot kick yourself.")
        return redirect('moderation:room_moderation', room_id=room.id)
    
    if target_user == room.created_by:
        messages.error(request, "You cannot kick the room creator.")
        return redirect('moderation:room_moderation', room_id=room.id)
    
    if request.method == 'POST':
        form = KickUserForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            
            # Remove membership
            RoomMembership.objects.filter(user=target_user, room=room).delete()
            
            # Also remove any mutes
            RoomMute.objects.filter(user=target_user, room=room).delete()
            
            # Log the action
            ModerationAction.objects.create(
                moderator=request.user,
                target_user=target_user,
                action_type='kick',
                reason=reason,
                room=room
            )
            
            messages.success(request, f"{target_user.username} has been kicked from {room.name}.")
            return redirect('moderation:room_moderation', room_id=room.id)
    else:
        form = KickUserForm()
    
    return render(request, 'moderation/kick_user.html', {
        'form': form,
        'target_user': target_user,
        'room': room,
    })


@login_required
def warn_user(request, user_id, room_id=None):
    """Warn a user"""
    target_user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id) if room_id else None
    
    if room:
        if not can_moderate_room(request.user, room):
            return HttpResponseForbidden("You don't have permission.")
    else:
        if not request.user.is_staff and not request.user.is_superuser:
            return HttpResponseForbidden("Only administrators can issue global warnings.")
    
    if request.method == 'POST':
        form = WarnUserForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            
            Warning.objects.create(
                user=target_user,
                issued_by=request.user,
                room=room,
                reason=reason
            )
            
            ModerationAction.objects.create(
                moderator=request.user,
                target_user=target_user,
                action_type='warn',
                reason=reason,
                room=room
            )
            
            scope = f"in {room.name}" if room else "globally"
            messages.success(request, f"Warning issued to {target_user.username} {scope}.")
            
            if room:
                return redirect('moderation:room_moderation', room_id=room.id)
            return redirect('moderation:dashboard')
    else:
        form = WarnUserForm()
    
    return render(request, 'moderation/warn_user.html', {
        'form': form,
        'target_user': target_user,
        'room': room,
    })


@login_required
def delete_message(request, message_id):
    """Delete a message (soft delete)"""
    message = get_object_or_404(Message, id=message_id)
    
    if not can_moderate_room(request.user, message.room):
        return HttpResponseForbidden("You don't have permission.")
    
    if request.method == 'POST':
        message.is_deleted = True
        message.save()
        
        ModerationAction.objects.create(
            moderator=request.user,
            target_user=message.sender,
            action_type='delete',
            reason=f'Message deleted: "{message.content[:50]}..."',
            room=message.room
        )
        
        messages.success(request, "Message has been deleted.")
        return redirect('chat:room_detail', slug=message.room.slug)
    
    return render(request, 'moderation/delete_message.html', {'message': message})


# =============================================================================
# Room Moderation
# =============================================================================

@login_required
def room_moderation(request, room_id):
    """Moderation panel for a specific room"""
    room = get_object_or_404(Room, id=room_id)
    
    if not can_moderate_room(request.user, room):
        return HttpResponseForbidden("You don't have permission to moderate this room.")
    
    members = room.members.all().select_related('profile')
    muted_users = RoomMute.objects.filter(room=room, expires_at__gt=timezone.now()) | \
                  RoomMute.objects.filter(room=room, expires_at__isnull=True)
    
    recent_reports = Report.objects.filter(message__room=room).order_by('-created_at')[:10]
    recent_actions = ModerationAction.objects.filter(room=room).order_by('-created_at')[:10]
    
    context = {
        'room': room,
        'members': members,
        'muted_users': muted_users,
        'recent_reports': recent_reports,
        'recent_actions': recent_actions,
    }
    return render(request, 'moderation/room_moderation.html', context)


# =============================================================================
# Admin User Management
# =============================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def admin_user_list(request):
    """List all users for admin management"""
    search = request.GET.get('search', '')
    users = User.objects.all().select_related('profile')
    
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )
    
    paginator = Paginator(users, 25)
    page = request.GET.get('page')
    users = paginator.get_page(page)
    
    return render(request, 'moderation/admin_user_list.html', {
        'users': users,
        'search': search,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def admin_user_edit(request, user_id):
    """Edit user account (admin only)"""
    target_user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    
    if request.method == 'POST':
        form = AdminUserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
            
            # Handle profile disable
            is_disabled = request.POST.get('is_disabled') == 'on'
            profile.is_disabled = is_disabled
            profile.save()
            
            messages.success(request, f"User {target_user.username} updated.")
            return redirect('moderation:admin_user_list')
    else:
        form = AdminUserEditForm(instance=target_user)
    
    return render(request, 'moderation/admin_user_edit.html', {
        'form': form,
        'target_user': target_user,
        'profile': profile,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def admin_user_delete(request, user_id):
    """Delete user account (admin only)"""
    target_user = get_object_or_404(User, id=user_id)
    
    if target_user == request.user:
        messages.error(request, "You cannot delete your own account from here.")
        return redirect('moderation:admin_user_list')
    
    if target_user.is_superuser and not request.user.is_superuser:
        messages.error(request, "Only superusers can delete other superusers.")
        return redirect('moderation:admin_user_list')
    
    if request.method == 'POST':
        username = target_user.username
        target_user.delete()
        messages.success(request, f"User {username} has been deleted.")
        return redirect('moderation:admin_user_list')
    
    return render(request, 'moderation/admin_user_delete.html', {
        'target_user': target_user,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def moderation_logs(request):
    """View all moderation action logs"""
    action_type = request.GET.get('type', 'all')
    actions = ModerationAction.objects.all().select_related(
        'moderator', 'target_user', 'room'
    )
    
    if action_type != 'all':
        actions = actions.filter(action_type=action_type)
    
    paginator = Paginator(actions, 50)
    page = request.GET.get('page')
    actions = paginator.get_page(page)
    
    return render(request, 'moderation/logs.html', {
        'actions': actions,
        'action_type': action_type,
        'action_types': ModerationAction.ACTION_TYPES,
    })


# =============================================================================
# Helper Functions
# =============================================================================

def get_moderable_rooms(user):
    """Get all rooms a user can moderate"""
    if user.is_staff or user.is_superuser:
        return Room.objects.all()
    
    created_rooms = Room.objects.filter(created_by=user)
    admin_memberships = RoomMembership.objects.filter(
        user=user,
        role__in=['admin', 'moderator']
    ).values_list('room_id', flat=True)
    
    return Room.objects.filter(
        Q(created_by=user) | Q(id__in=admin_memberships)
    ).distinct()


# =============================================================================
# AJAX Endpoints
# =============================================================================

@login_required
def check_user_muted(request, user_id, room_id):
    """Check if a user is muted in a room (AJAX)"""
    user = get_object_or_404(User, id=user_id)
    room = get_object_or_404(Room, id=room_id)
    
    mute = RoomMute.objects.filter(user=user, room=room).first()
    is_muted = mute and mute.is_active if mute else False
    
    return JsonResponse({
        'is_muted': is_muted,
        'expires_at': mute.expires_at.isoformat() if mute and mute.expires_at else None
    })
