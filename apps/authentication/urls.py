from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Account management
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile_view, name='edit_profile'),
    path('account/edit/', views.edit_account_view, name='edit_account'),
    path('account/password/', views.change_password_view, name='change_password'),
    path('account/delete/', views.delete_account_view, name='delete_account'),
    # Settings alias (points to edit_account)
    path('settings/', views.edit_account_view, name='settings'),
]