from django.contrib import admin
from .models import Report, ModerationAction, RoomMute, Warning


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['reported_by', 'message', 'status', 'created_at', 'reviewed_by']
    list_filter = ['status', 'created_at']
    search_fields = ['reported_by__username', 'reason']
    readonly_fields = ['created_at', 'reviewed_at']


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ['action_type', 'target_user', 'moderator', 'room', 'created_at', 'is_active']
    list_filter = ['action_type', 'is_active', 'created_at']
    search_fields = ['target_user__username', 'moderator__username', 'reason']
    readonly_fields = ['created_at']


@admin.register(RoomMute)
class RoomMuteAdmin(admin.ModelAdmin):
    list_display = ['user', 'room', 'muted_by', 'created_at', 'expires_at']
    list_filter = ['created_at', 'expires_at']
    search_fields = ['user__username', 'room__name']


@admin.register(Warning)
class WarningAdmin(admin.ModelAdmin):
    list_display = ['user', 'issued_by', 'room', 'acknowledged', 'created_at']
    list_filter = ['acknowledged', 'created_at']
    search_fields = ['user__username', 'reason']
