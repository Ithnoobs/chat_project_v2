# Django Chat Application

A real-time chat application built with Django Channels, featuring comprehensive moderation tools and account management.

## Features

### Authentication & Account Management
- User registration and login
- Profile management (bio, avatar)
- Account settings (username, email, name)
- Password change
- Account deletion
- Online/offline status tracking

### Chat
- Public and private rooms
- Real-time messaging via WebSockets
- Typing indicators
- Auto-join for public rooms
- Room creation and management
- User invitations for private rooms

### Moderation Tools
- **Custom Moderation Panel** accessible to moderators/admins
- **Report System**: Users can report inappropriate messages
- **User Actions**:
  - Ban (global for admins, room-specific for moderators)
  - Mute (prevent sending messages)
  - Kick (remove from room)
  - Warn (issue warnings)
  - Delete messages
- **Scope Control**:
  - Global admins can moderate all rooms
  - Room creators/moderators can only moderate their specific rooms
- **Action Logs**: Complete audit trail of all moderation actions
- **Admin User Management**: Edit, disable, or delete user accounts

### Notifications
- Real-time notifications via WebSocket
- Support for mentions, messages, invites, replies, warnings
- Mark as read/unread
- Notification history

## Bug Fixes Applied

### UserProfile Signal Bug (Authentication)
**Issue**: When setting up on a new laptop, there was a bug with UserProfile not being saved properly.

**Fix**: Updated the `save_user_profile` signal handler in `apps/authentication/models.py`:
```python
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance)
```

The previous implementation used `hasattr()` which always returns `True` for related managers even if no object exists. The fix uses try/except to properly handle the case where the profile doesn't exist.

## Setup Instructions

### Using Docker (Recommended)

1. Clone the repository
2. Run Docker Compose:
   ```bash
   docker-compose up -d
   ```
3. Run migrations:
   ```bash
   docker-compose exec web python manage.py migrate
   ```
4. Create a superuser:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```
5. Access the application at http://localhost:8000

### Manual Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up PostgreSQL**:
   - Create a database named `chat_db`
   - Update database credentials in settings or environment variables

3. **Set up Redis**:
   - Install and start Redis server
   - Default: localhost:6379

4. **Configure environment variables** (optional):
   ```bash
   export SECRET_KEY='your-secret-key'
   export DEBUG=True
   export DB_NAME=chat_db
   export DB_USER=postgres
   export DB_PASSWORD=postgres
   export DB_HOST=localhost
   export REDIS_HOST=localhost
   ```

5. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**:
   ```bash
   daphne chat_project.asgi:application
   ```

## Project Structure

```
chat_project/
├── apps/
│   ├── authentication/    # User auth, profiles, account management
│   ├── chat/              # Rooms, messages, WebSocket consumers
│   ├── moderation/        # Reports, actions, admin panel
│   └── notifications/     # Notification system
├── chat_project/          # Project settings
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── routing.py         # WebSocket URL routing
├── templates/             # HTML templates
├── static/                # Static files
├── media/                 # User uploads
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── manage.py
```

## Moderation Hierarchy

1. **Superusers**: Full access to everything
2. **Staff (Global Admins)**: 
   - Can moderate all rooms
   - Can issue global bans
   - Can manage users (edit, disable, delete)
   - Access to moderation logs
3. **Room Creators/Moderators**:
   - Can moderate their specific rooms only
   - Can ban/mute/kick/warn users in their rooms
   - Can review reports for their rooms
   - Cannot issue global bans

## URLs

- `/` - Home (redirects to room list)
- `/auth/login/` - Login
- `/auth/register/` - Registration
- `/auth/profile/` - User profile
- `/auth/account/edit/` - Edit account settings
- `/auth/account/password/` - Change password
- `/auth/account/delete/` - Delete account
- `/chat/` - Chat room list
- `/chat/room/<slug>/` - Chat room
- `/moderation/` - Moderation dashboard
- `/moderation/reports/` - View reports
- `/moderation/users/` - Admin user management
- `/moderation/logs/` - Moderation action logs
- `/notifications/` - Notification center

## Technologies

- **Backend**: Django 4.2+, Django Channels
- **Database**: PostgreSQL
- **Cache/Message Broker**: Redis
- **WebSocket Server**: Daphne
- **Frontend**: Bootstrap 5, Bootstrap Icons
- **Static Files**: WhiteNoise
