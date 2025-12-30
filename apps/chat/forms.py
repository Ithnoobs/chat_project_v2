from django import forms
from .models import Room, Message


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'description', 'room_type']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter room name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe your room (optional)'
            }),
            'room_type': forms.Select(attrs={
                'class': 'form-select'
            }),
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Type your message...',
                'autocomplete': 'off'
            }),
        }
