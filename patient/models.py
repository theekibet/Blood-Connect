from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from blood.models import Notification
from datetime import date
from django.core.exceptions import ValidationError
from donor.models import KENYAN_COUNTIES


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
    
    # ==========================================
    # BLOOD GROUP VERIFICATION FIELDS (NEW)
    # ==========================================
    bloodgroup_verified = models.BooleanField(
        default=False, 
        help_text="Blood group verified by nurse on first blood request"
    )
    bloodgroup_verified_by = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='verified_patient_bloodgroups',
        help_text="Nurse who verified the blood group"
    )
    bloodgroup_verified_at = models.DateTimeField(null=True, blank=True)
    
    nurse = models.ForeignKey('nurse.Nurse', on_delete=models.SET_NULL, null=True, blank=True)
    mobile = models.CharField(max_length=20)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    emergency_contact = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    county = models.CharField(max_length=50, choices=KENYAN_COUNTIES, null=True, blank=True)
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
    
    
# ------------------------
# Blood Request Model
# ------------------------
class BloodRequest(models.Model):
    
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    request_by_patient = models.ForeignKey(
        'patient.Patient',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name='blood_requests'
    )

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    patient_age = models.PositiveIntegerField()
    contact_number = models.CharField(max_length=20)
    emergency_contact = models.CharField(max_length=20, blank=True, null=True)
    national_id = models.CharField(max_length=50, blank=True, null=True)

    bloodgroup = models.CharField(
        max_length=10,
        choices=BLOOD_GROUP_CHOICES,
        blank=True,
        null=True,
        help_text="Patient's blood group"
    )
    unit = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Required blood volume in ml (450-2700)"
    )

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.CASCADE,
        null=False,
        blank=False
    )

    consent_confirmed = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    is_seen = models.BooleanField(default=False)
    stock_deducted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    appointments = GenericRelation(
        'nurse.Appointment',
        content_type_field='request_content_type',
        object_id_field='request_object_id',
        related_query_name='blood_requests'
    )

    approved_by_nurse = models.ForeignKey(
        'nurse.Nurse',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_blood_requests_nurse'
    )
    approved_at_nurse = models.DateTimeField(null=True, blank=True)

    rejected_by = models.CharField(max_length=20, null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)

    cancelled_by = models.CharField(max_length=20, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)

    completed_by_nurse = models.ForeignKey(
        'nurse.Nurse',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='completed_blood_requests_nurse'
    )
    completed_at_nurse = models.DateTimeField(null=True, blank=True)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def clean(self):
        super().clean()
        if not self.request_by_patient:
            raise ValidationError("A patient must be associated with this blood request.")
        if self.unit and (self.unit < 450 or self.unit > 2700):
            raise ValidationError("Blood unit must be between 450ml and 2700ml.")
        if self.unit and self.unit % 50 != 0:
            raise ValidationError("Blood unit must be in multiples of 50ml.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Blood Request by {self.get_full_name()} ({self.bloodgroup or 'Unknown'}) - {self.status}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Blood Request"
        verbose_name_plural = "Blood Requests"