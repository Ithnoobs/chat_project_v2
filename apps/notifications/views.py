from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator

from .models import Notification


@login_required
def notification_list(request):
    """List all notifications for the current user"""
    notifications = Notification.objects.filter(recipient=request.user)
    
    # Filter by type if specified
    notif_type = request.GET.get('type', 'all')
    if notif_type != 'all':
        notifications = notifications.filter(notification_type=notif_type)
    
    # Filter by read status
    read_filter = request.GET.get('read', 'all')
    if read_filter == 'unread':
        notifications = notifications.filter(is_read=False)
    elif read_filter == 'read':
        notifications = notifications.filter(is_read=True)
    
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page')
    notifications = paginator.get_page(page)
    
    unread_count = Notification.objects.filter(
        recipient=request.user, 
        is_read=False
    ).count()
    
    context = {
        'notifications': notifications,
        'unread_count': unread_count,
        'notif_type': notif_type,
        'read_filter': read_filter,
    }
    return render(request, 'notifications/list.html', context)


@login_required
def mark_as_read(request, notification_id):
    """Mark a single notification as read"""
    notification = get_object_or_404(
        Notification, 
        id=notification_id, 
        recipient=request.user
    )
    notification.mark_as_read()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    # Redirect based on notification type
    if notification.related_room:
        return redirect('chat:room_detail', slug=notification.related_room.slug)
    
    return redirect('notifications:list')


@login_required
def mark_all_read(request):
    """Mark all notifications as read"""
    if request.method == 'POST':
        Notification.objects.filter(
            recipient=request.user, 
            is_read=False
        ).update(is_read=True)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
    
    return redirect('notifications:list')


@login_required
def delete_notification(request, notification_id):
    """Delete a notification"""
    notification = get_object_or_404(
        Notification, 
        id=notification_id, 
        recipient=request.user
    )
    
    if request.method == 'POST':
        notification.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
    
    return redirect('notifications:list')


@login_required
def clear_all(request):
    """Delete all notifications"""
    if request.method == 'POST':
        Notification.objects.filter(recipient=request.user).delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
    
    return redirect('notifications:list')


# API endpoints
@login_required
def api_get_notifications(request):
    """Get unread notifications count and recent notifications"""
    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    recent = Notification.objects.filter(
        recipient=request.user
    )[:5]
    
    notifications_data = [{
        'id': n.id,
        'type': n.notification_type,
        'title': n.title,
        'message': n.message,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
        'room_slug': n.related_room.slug if n.related_room else None,
    } for n in recent]
    
    return JsonResponse({
        'unread_count': unread_count,
        'notifications': notifications_data
    })


@login_required
def api_mark_read(request, notification_id):
    """API endpoint to mark notification as read"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=request.user
        )
        notification.mark_as_read()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'error': 'Notification not found'}, status=404)
