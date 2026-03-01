from django.db.models.signals import post_save
from django.dispatch import receiver
from phlebotomist.models import Phlebotomist
@receiver(post_save, sender=Phlebotomist)
def set_user_staff_status(sender, instance, created, **kwargs):
    if created:
        user = instance.user
        if not user.is_staff:
            user.is_staff = True
            user.save()
