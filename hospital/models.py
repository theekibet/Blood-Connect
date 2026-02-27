from django.db import models
from django.contrib.auth.models import User
from blood.models import DonationCenter
import uuid

class Hospital(models.Model):
    """Registered hospitals that can request blood"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=50, unique=True)
    county = models.CharField(max_length=100)
    
    # Location tracking (similar to DonationCenter)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Contact details
    contact_person = models.CharField(max_length=100, help_text="Lab in-charge name")
    contact_phone = models.CharField(max_length=15)
    email = models.EmailField()
    alternative_phone = models.CharField(max_length=15, blank=True)
    
    # Operational details
    has_blood_storage = models.BooleanField(default=True, help_text="Does hospital have blood bank fridge?")
    serving_centre = models.ForeignKey(
        DonationCenter, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        help_text="Which donation centre serves this hospital"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    verified = models.BooleanField(default=False, help_text="Has hospital been verified?")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"
    
    def __str__(self):
        return self.name
    
    def get_location(self):
        """Return location as tuple (lat, long)"""
        if self.latitude and self.longitude:
            return (self.latitude, self.longitude)
        return None
    
    def get_location_name(self):
        """Return readable location name"""
        if self.county:
            return self.county
        return "Unknown location"


class HospitalUser(models.Model):
    """Hospital staff who can access the system"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='users')
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    ROLE_CHOICES = [
        ('lab_tech', 'Laboratory Technician'),
        ('admin', 'Hospital Administrator'),
        ('viewer', 'View Only'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='lab_tech')
    
    is_primary_contact = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['hospital', 'user']
        verbose_name = "Hospital User"
        verbose_name_plural = "Hospital Users"
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.hospital.name}"


class HospitalBloodRequest(models.Model):
    """Hospital blood requests"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_number = models.CharField(max_length=50, unique=True, blank=True)
    
    # Who requested
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='blood_requests')
    requested_by = models.ForeignKey(HospitalUser, on_delete=models.SET_NULL, null=True, related_name='requests_made')
    
    # Blood details
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES)
    units_requested = models.PositiveIntegerField()
    units_dispatched = models.PositiveIntegerField(default=0)
    
    # Patient details
    patient_first_name = models.CharField(max_length=100)
    patient_last_name = models.CharField(max_length=100)
    patient_age = models.IntegerField(null=True, blank=True)
    patient_gender = models.CharField(max_length=10, blank=True)
    patient_id = models.CharField(max_length=50, blank=True, help_text="Hospital's patient ID")
    
    # Doctor's information
    doctor_name = models.CharField(max_length=200)
    doctor_license = models.CharField(max_length=50, blank=True)
    
    # Urgency
    URGENCY_CHOICES = [
        ('routine', 'Routine (24-48 hrs)'),
        ('urgent', 'Urgent (4-6 hrs)'),
        ('emergency', 'Emergency (Immediate)'),
    ]
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='routine')
    
    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved - Ready for Pickup'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered to Hospital'),
        ('partially_dispatched', 'Partially Dispatched'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected - No Stock'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Assignment
    assigned_centre = models.ForeignKey(
        DonationCenter, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='hospital_requests'
    )
    
    # Approval tracking
    approved_by = models.ForeignKey(
        'blood_bank_technician.BloodBankTechProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_hospital_requests'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Dispatch tracking
    dispatched_by = models.ForeignKey(
        'blood_bank_technician.BloodBankTechProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatched_hospital_requests'
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    
    # Rejection reason
    rejection_reason = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Hospital Blood Request"
        verbose_name_plural = "Hospital Blood Requests"
    
    def __str__(self):
        return f"{self.request_number} - {self.hospital.name}"
    
    def save(self, *args, **kwargs):
        if not self.request_number:
            # Generate request number: REQ-2025-0001
            from django.utils import timezone
            year = timezone.now().year
            last_request = HospitalBloodRequest.objects.filter(
                request_number__startswith=f"REQ-{year}"
            ).order_by('-request_number').first()
            
            if last_request:
                last_num = int(last_request.request_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.request_number = f"REQ-{year}-{new_num:04d}"
        
        super().save(*args, **kwargs)
    
    @property
    def patient_full_name(self):
        return f"{self.patient_first_name} {self.patient_last_name}".strip()
    
    @property
    def is_fully_dispatched(self):
        return self.units_dispatched >= self.units_requested
    
    @property
    def is_partially_dispatched(self):
        return self.units_dispatched > 0 and self.units_dispatched < self.units_requested