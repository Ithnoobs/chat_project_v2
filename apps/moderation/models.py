from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.chat.models import Message, Room


class Report(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reports')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='reports_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Report by {self.reported_by.username} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']


class ModerationAction(models.Model):
    ACTION_TYPES = [
        ('ban', 'Ban User'),
        ('unban', 'Unban User'),
        ('mute', 'Mute User'),
        ('unmute', 'Unmute User'),
        ('kick', 'Kick User'),
        ('delete', 'Delete Message'),
        ('warn', 'Warn User'),
    ]
    
    moderator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='moderation_actions')
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_actions')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    reason = models.TextField()
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, null=True, blank=True,
        related_name='moderation_actions',
        help_text="If null, action is global (admin only)"
    )
    duration = models.IntegerField(
        null=True, blank=True, 
        help_text="Duration in minutes for temporary actions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        scope = f"in {self.room.name}" if self.room else "globally"
        return f"{self.action_type} - {self.target_user.username} {scope} by {self.moderator.username}"
    
    def save(self, *args, **kwargs):
        # Calculate expires_at if duration is set
        if self.duration and not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=self.duration)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    class Meta:
        ordering = ['-created_at']


class RoomMute(models.Model):
    """Track muted users in specific rooms"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_mutes')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='muted_users')
    muted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mutes_given')
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['user', 'room']
    
    def __str__(self):
        return f"{self.user.username} muted in {self.room.name}"
    
    @property
    def is_active(self):
        if not self.expires_at:
            return True  # Permanent mute
        return timezone.now() < self.expires_at


class Warning(models.Model):
    """Track warnings given to users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='warnings')
    issued_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='warnings_issued')
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, null=True, blank=True,
        related_name='warnings'
    )
    reason = models.TextField()
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        scope = f"in {self.room.name}" if self.room else "globally"
        return f"Warning to {self.user.username} {scope}"
    
    class Meta:
        ordering = ['-created_at']
