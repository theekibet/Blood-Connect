from django.db import models
from django.contrib.auth.models import User
# from donor.models import Donor  # Commented out to break circular import
from blood.models import DonationCenter
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Nurse(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_pic = models.ImageField(upload_to='nurse_profiles/', null=True, blank=True)
    license_number = models.CharField(max_length=50, unique=True)
    center = models.ForeignKey(DonationCenter, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Nurse: {self.user.get_full_name()}"
class Appointment(models.Model):
    # For donor donations
    donor = models.ForeignKey('donor.Donor', on_delete=models.CASCADE, null=True, blank=True)
    
    # GenericForeignKey to link to either BloodDonate or HospitalBloodRequest
    request_content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='appointment_requests'
    )
    request_object_id = models.PositiveIntegerField(null=True, blank=True)
    request = GenericForeignKey('request_content_type', 'request_object_id')
    
    # Common fields
    date = models.DateTimeField()
    center = models.ForeignKey(DonationCenter, on_delete=models.CASCADE)
    nurse = models.ForeignKey(Nurse, on_delete=models.CASCADE)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['request_content_type', 'request_object_id']),
        ]
    
    def __str__(self):
        if self.donor:
            return f"Donation: {self.donor.user.get_full_name()} - {self.date}"
        elif self.request:
            return f"Request: {self.request} - {self.date}"
        return f"Appointment {self.id} - {self.date}"
    
    def clean(self):
        # Must have either a donor OR a request, but not both
        if self.donor and self.request:
            raise ValidationError("Appointment cannot be linked to both donor and request")
        if not self.donor and not self.request:
            raise ValidationError("Appointment must have either a donor or a request")
        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError("Invalid status")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)