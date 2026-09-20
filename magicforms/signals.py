from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import EmployeeProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_employee_profile(sender, instance, created, **kwargs):
    """Every user gets a profile row for mapping keys and HR fields."""
    EmployeeProfile.objects.get_or_create(user=instance)
