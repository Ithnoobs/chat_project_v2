from django import forms
from django.contrib.auth.models import User
from .models import Report, ModerationAction, RoomMute, Warning
from apps.chat.models import Room


class ReportForm(forms.ModelForm):
    """Form for users to report messages"""
    class Meta:
        model = Report
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe why you are reporting this message...'
            }),
        }


class ReportReviewForm(forms.ModelForm):
    """Form for moderators to review reports"""
    class Meta:
        model = Report
        fields = ['status', 'resolution_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'resolution_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add resolution notes...'
            }),
        }


class BanUserForm(forms.Form):
    """Form for banning users"""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for banning...'
        })
    )
    duration = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Leave empty for permanent ban'
        }),
        help_text='Duration in minutes (leave empty for permanent ban)'
    )
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label='Global ban (admin only)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class MuteUserForm(forms.Form):
    """Form for muting users in a room"""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for muting...'
        })
    )
    duration = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Leave empty for permanent mute'
        }),
        help_text='Duration in minutes (leave empty for permanent mute)'
    )


class WarnUserForm(forms.Form):
    """Form for warning users"""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for warning...'
        })
    )


class KickUserForm(forms.Form):
    """Form for kicking users from a room"""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for kicking...'
        })
    )


class AdminUserEditForm(forms.ModelForm):
    """Form for admins to edit user accounts"""
    is_active = forms.BooleanField(required=False, label='Account Active')
    is_staff = forms.BooleanField(required=False, label='Staff Status')
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
