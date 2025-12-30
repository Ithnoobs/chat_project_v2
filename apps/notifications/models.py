from django.db import models
from django.contrib.auth.models import User


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('mention', 'Mention'),
        ('message', 'New Message'),
        ('invite', 'Room Invitation'),
        ('reply', 'Reply'),
        ('warning', 'Warning'),
        ('moderation', 'Moderation Action'),
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    
    # Optional related objects
    related_room = models.ForeignKey(
        'chat.Room', on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications'
    )
    related_message = models.ForeignKey(
        'chat.Message', on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications'
    )
    related_user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='caused_notifications'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.notification_type}: {self.title} for {self.recipient.username}"
    
    class Meta:
        ordering = ['-created_at']
    
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
