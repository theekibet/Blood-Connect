from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from blood.models import Notification
from datetime import date


class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    profile_pic = models.ImageField(upload_to='profile_pic/Patient/', null=True, blank=True)

    gender = models.CharField(
        max_length=10,
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        default='M'
    )

    dob = models.DateField("Date of Birth", null=True, blank=True)

    bloodgroup = models.CharField(max_length=10, null=True, blank=True)

    nurse = models.ForeignKey('nurse.Nurse', on_delete=models.SET_NULL, null=True, blank=True)

    
    mobile = models.CharField(max_length=20)


    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    emergency_contact = models.CharField(max_length=20, null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_name = models.CharField(max_length=255, null=True, blank=True)
    notifications = GenericRelation(
        Notification,
        content_type_field='recipient_content_type',
        object_id_field='recipient_object_id',
        related_query_name='patient_notifications'
    )

    def __str__(self):
        return self.get_name() if self.user else "Unnamed Patient"

    def get_name(self):
        if self.user:
            return f"{self.user.first_name} {self.user.last_name}".strip()
        return "Unnamed Patient"

    def get_notifications(self):
        return self.notifications.all()

    @property
    def age(self):
        if self.dob:
            today = date.today()
            years = today.year - self.dob.year
            if (today.month, today.day) < (self.dob.month, self.dob.day):
                years -= 1
            return years
        return None