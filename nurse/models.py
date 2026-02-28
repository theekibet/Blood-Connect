from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from datetime import date, timedelta
from django.utils import timezone
from blood.models import DonationCenter
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Nurse(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='nurse'  # Explicitly set related_name
    )
    profile_pic = models.ImageField(upload_to='nurse_profiles/', null=True, blank=True)
    license_number = models.CharField(max_length=50, unique=True)
    center = models.ForeignKey(
        'blood.DonationCenter', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='nurses'  # Add related_name for reverse query
    )
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Add for tracking updates
    
    # Additional useful fields
    qualification = models.CharField(max_length=200, blank=True, 
                                     help_text="Nursing qualification/degree")
    specialization = models.CharField(max_length=100, blank=True,
                                     help_text="E.g., Blood Bank, Emergency, ICU")
    license_expiry = models.DateField(null=True, blank=True,
                                     help_text="License expiration date")
    years_of_experience = models.PositiveIntegerField(default=0)
    is_approved = models.BooleanField(default=False,
                                     help_text="Whether nurse account is approved by admin")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_nurses'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Nurse"
        verbose_name_plural = "Nurses"
        ordering = ['-created_at']
        # Add database constraints
        constraints = [
            # Ensure user is unique
            models.UniqueConstraint(
                fields=['user'],
                name='unique_nurse_user'
            ),
            # Ensure license_number is unique (already set, but explicit)
            models.UniqueConstraint(
                fields=['license_number'],
                name='unique_nurse_license'
            ),
        ]
        # Add indexes for frequently queried fields
        indexes = [
            models.Index(fields=['center', 'is_active']),
            models.Index(fields=['license_expiry']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['specialization']),
        ]
    
    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"Nurse: {name} - {self.license_number}"
    
    def clean(self):
        """
        Validate that user doesn't have other profiles
        """
        from django.core.exceptions import ValidationError
        from blood.utils.validators import validate_single_profile  
        
        # Skip validation if this is an existing instance being updated
        if not self.user:
            return
            
        if not self.pk:
            # For new instances, validate the user doesn't have other profiles
            try:
                validate_single_profile(
                    user=self.user,
                    current_profile_type='nurse',
                    exclude_self=True
                )
            except ValidationError as e:
                raise ValidationError({
                    'user': f"This user already has a different profile. Each user can only have one role in the system."
                })
        
        # Validate license expiry
        if self.license_expiry and self.license_expiry < date.today():
            raise ValidationError({
                'license_expiry': f"License has already expired on {self.license_expiry}. Please renew."
            })
        
        # Validate phone format
        if self.phone and not self.phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise ValidationError({
                'phone': "Phone number should contain only digits, spaces, +, or -"
            })
    
    def save(self, *args, **kwargs):
        """
        Override save to ensure validation runs
        """
        # Handle approval timestamp
        if self.is_approved and not self.approved_at:
            self.approved_at = timezone.now()
        
        # Auto-calculate years of experience if not set
        if not self.years_of_experience and self.license_expiry:
            # Rough estimate: assume got license at 22 and worked since
            estimated_start = self.license_expiry.year - 5  # Rough estimate
            self.years_of_experience = max(0, date.today().year - estimated_start)
        
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        """Get nurse's full name"""
        return self.user.get_full_name() or self.user.username
    
    @property
    def email(self):
        """Get nurse's email"""
        return self.user.email
    
    @property
    def is_license_valid(self):
        """Check if license is still valid"""
        if not self.license_expiry:
            return False
        return date.today() <= self.license_expiry
    
    @property
    def days_until_license_expiry(self):
        """Get days until license expires"""
        if not self.license_expiry:
            return None
        delta = (self.license_expiry - date.today()).days
        return max(delta, 0)
    
    @property
    def total_appointments_today(self):
        """Get count of appointments for today"""
        if hasattr(self, 'appointment_set'):
            return self.appointment_set.filter(
                appointment_date__date=date.today()
            ).count()
        return 0
    
    @property
    def pending_appointments(self):
        """Get count of pending appointments"""
        if hasattr(self, 'appointment_set'):
            return self.appointment_set.filter(
                status='pending'
            ).count()
        return 0
    
    def can_conduct_donation(self):
        """Check if nurse can conduct blood donation"""
        return (self.is_active and 
                self.is_approved and 
                self.is_license_valid and 
                self.center is not None)
    
    def get_upcoming_appointments(self, days=7):
        """Get appointments for the next X days"""
        if hasattr(self, 'appointment_set'):
            end_date = date.today() + timedelta(days=days)
            return self.appointment_set.filter(
                appointment_date__date__gte=date.today(),
                appointment_date__date__lte=end_date
            ).order_by('appointment_date')
        return []
    
    def verify_donor_blood_group(self, donor, blood_group):
        """
        Verify a donor's blood group during first donation
        """
        from django.utils import timezone
        
        if not self.can_conduct_donation():
            raise PermissionError("Nurse not authorized to verify blood groups")
        
        donor.bloodgroup = blood_group
        donor.bloodgroup_verified = True
        donor.bloodgroup_verified_by = self.user
        donor.bloodgroup_verified_at = timezone.now()
        donor.save()
        
        return True
    
    @classmethod
    def get_available_nurses(cls, center_id=None):
        """Get all available nurses, optionally filtered by center"""
        queryset = cls.objects.filter(
            is_active=True,
            is_approved=True,
            is_license_valid=True
        )
        if center_id:
            queryset = queryset.filter(center_id=center_id)
        return queryset
    
    @classmethod
    def get_nurses_with_expiring_licenses(cls, days=30):
        """Get nurses whose licenses expire within specified days"""
        expiry_threshold = date.today() + timedelta(days=days)
        return cls.objects.filter(
            license_expiry__lte=expiry_threshold,
            license_expiry__gte=date.today(),
            is_active=True
        )
    
    @classmethod
    def get_pending_approval(cls):
        """Get nurses waiting for approval"""
        return cls.objects.filter(
            is_approved=False,
            is_active=True
        )
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