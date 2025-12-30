from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    online_status = models.CharField(
        max_length=20,
        choices=[
            ('online', 'Online'),
            ('away', 'Away'),
            ('offline', 'Offline'),
        ],
        default='offline'
    )
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Account management fields
    is_banned = models.BooleanField(default=False)
    ban_reason = models.TextField(blank=True)
    banned_until = models.DateTimeField(null=True, blank=True)
    is_disabled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}'s profile"
    
    @property
    def is_currently_banned(self):
        """Check if user is currently banned (considering temporary bans)"""
        if not self.is_banned:
            return False
        if self.banned_until:
            from django.utils import timezone
            return timezone.now() < self.banned_until
        return True  # Permanent ban


# Automatically create profile when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # FIX: Use try/except to handle case where profile doesn't exist
    # hasattr() always returns True for related managers, even if no object exists
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        # Profile doesn't exist, create it
        UserProfile.objects.create(user=instance)
