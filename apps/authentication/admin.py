from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'online_status', 'is_banned', 'is_disabled', 'last_seen']
    list_filter = ['online_status', 'is_banned', 'is_disabled']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'last_seen']
