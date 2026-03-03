
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to login with either
    their username or email address.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user with either username or email
        """
        if username is None or password is None:
            return None
        
        try:
            # Try to find user by username OR email
            user = User.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            
            # Check if the password is correct
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            # Run the default password hasher once to reduce timing
            # difference between existing and non-existing users
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # If multiple users share the same email (shouldn't happen with proper validation)
            # Fall back to exact username match
            try:
                user = User.objects.get(username__iexact=username)
                if user.check_password(password):
                    return user
            except User.DoesNotExist:
                return None
        
        return None
    
    def get_user(self, user_id):
        """
        Get a user by ID (required by Django)
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None