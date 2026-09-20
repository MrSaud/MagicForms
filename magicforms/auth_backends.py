"""Authentication backends for MagicForms studio."""

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model


class EntityDirectoryBackend(BaseBackend):
    """
    Marks users signed in via the organization directory API.
    Actual verification happens in :class:`magicforms.studio_login.StudioAuthenticationForm`.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        return None

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
