from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import (
    UserRegistrationForm, 
    UserProfileForm, 
    UserAccountForm, 
    CustomPasswordChangeForm,
    DeleteAccountForm
)
from .models import UserProfile


def register_view(request):
    if request.user.is_authenticated:
        return redirect('chat:room_list')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'authentication/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('chat:room_list')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                # Check if user is banned or disabled
                try:
                    profile = user.profile
                    if profile.is_disabled:
                        messages.error(request, 'Your account has been disabled. Please contact support.')
                        return render(request, 'authentication/login.html', {'form': form})
                    if profile.is_currently_banned:
                        ban_msg = 'Your account has been banned.'
                        if profile.banned_until:
                            ban_msg += f' Ban expires: {profile.banned_until.strftime("%Y-%m-%d %H:%M")}'
                        if profile.ban_reason:
                            ban_msg += f' Reason: {profile.ban_reason}'
                        messages.error(request, ban_msg)
                        return render(request, 'authentication/login.html', {'form': form})
                except UserProfile.DoesNotExist:
                    # Create profile if it doesn't exist
                    UserProfile.objects.create(user=user)
                
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('chat:room_list')
    else:
        form = AuthenticationForm()
    
    return render(request, 'authentication/login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('login')
    return redirect('chat:room_list')


@login_required
def profile_view(request):
    """View and edit user profile"""
    # Ensure profile exists
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    context = {
        'profile': profile,
        'user': request.user,
    }
    return render(request, 'authentication/profile.html', context)


@login_required
def edit_profile_view(request):
    """Edit user profile (bio, avatar)"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'authentication/edit_profile.html', {'form': form})


@login_required
def edit_account_view(request):
    """Edit user account details (username, email)"""
    if request.method == 'POST':
        form = UserAccountForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account details updated successfully!')
            return redirect('profile')
    else:
        form = UserAccountForm(instance=request.user)
    
    return render(request, 'authentication/edit_account.html', {'form': form})


@login_required
def change_password_view(request):
    """Change user password"""
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Keep the user logged in after password change
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'authentication/change_password.html', {'form': form})


@login_required
def delete_account_view(request):
    """Delete user account"""
    if request.method == 'POST':
        form = DeleteAccountForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']
            if request.user.check_password(password):
                # Store username for message
                username = request.user.username
                # Delete the user (this will cascade to profile and other related data)
                request.user.delete()
                messages.success(request, f'Account "{username}" has been permanently deleted.')
                return redirect('login')
            else:
                messages.error(request, 'Incorrect password. Please try again.')
    else:
        form = DeleteAccountForm()
    
    return render(request, 'authentication/delete_account.html', {'form': form})
