from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from datetime import date, timedelta
from django.utils import timezone
from blood.models import DonationCenter
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Phlebotomist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='phlebotomist'
    )
    profile_pic = models.ImageField(upload_to='phlebotomist_profiles/', null=True, blank=True)
    license_number = models.CharField(max_length=50, unique=True)
    center = models.ForeignKey(
        'blood.DonationCenter', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='phlebotomists'
    )
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional useful fields
    qualification = models.CharField(max_length=200, blank=True, 
                                     help_text="Phlebotomist qualification/degree")
    specialization = models.CharField(max_length=100, blank=True,
                                     help_text="E.g., Blood Bank, Emergency, ICU")
    license_expiry = models.DateField(null=True, blank=True,
                                     help_text="License expiration date")
    years_of_experience = models.PositiveIntegerField(default=0)
    is_approved = models.BooleanField(default=False,
                                     help_text="Whether phlebotomist account is approved by admin")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_phlebotomists'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Phlebotomist"
        verbose_name_plural = "phlebotomists"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                name='unique_phlebotomist_user'
            ),
            models.UniqueConstraint(
                fields=['license_number'],
                name='unique_phlebotomist_license'
            ),
        ]
        indexes = [
            models.Index(fields=['center', 'is_active']),
            models.Index(fields=['license_expiry']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['specialization']),
        ]
    
    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"Phlebotomist: {name} - {self.license_number}"
    
    # ===== FIXED: Indentation corrected - these methods are INSIDE the class =====
    def clean(self):
        """
        Validate that user doesn't have other profiles
        """
        from django.core.exceptions import ValidationError, ObjectDoesNotExist
        from blood.utils.validators import validate_single_profile  
        from datetime import date
        
        # Check if user exists before accessing it
        try:
            has_user = self.user is not None
        except ObjectDoesNotExist:
            # This catches the RelatedObjectDoesNotExist error
            has_user = False
        
        # Skip validation if no user is assigned yet
        if not has_user:
            return
        
        # If we get here, user exists and is accessible
        if not self.pk:
            # For new instances, validate the user doesn't have other profiles
            try:
                validate_single_profile(
                    user=self.user,
                    current_profile_type='phlebotomist',
                    exclude_self=True
                )
            except ValidationError as e:
                raise ValidationError({
                    'user': "This user already has a different profile. Each user can only have one role in the system."
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
        """Get phlebotomist's full name"""
        return self.user.get_full_name() or self.user.username
    
    @property
    def email(self):
        """Get phlebotomist's email"""
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
                date__date=date.today()
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
        """Check if phlebotomist can conduct blood donation"""
        return (self.is_active and 
                self.is_approved and 
                self.is_license_valid and 
                self.center is not None)
    
    def get_upcoming_appointments(self, days=7):
        """Get appointments for the next X days"""
        if hasattr(self, 'appointment_set'):
            end_date = date.today() + timedelta(days=days)
            return self.appointment_set.filter(
                date__date__gte=date.today(),
                date__date__lte=end_date
            ).order_by('date')
        return []
    
    def verify_donor_blood_group(self, donor, blood_group):
        """
        Verify a donor's blood group during first donation
        """
        from django.utils import timezone
        
        if not self.can_conduct_donation():
            raise PermissionError("Phlebotomist not authorized to verify blood groups")
        
        donor.bloodgroup = blood_group
        donor.bloodgroup_verified = True
        donor.bloodgroup_verified_by = self.user
        donor.bloodgroup_verified_at = timezone.now()
        donor.save()
        
        return True
    
    @classmethod
    def get_available_phlebotomists(cls, center_id=None):
        """Get all available phlebotomists, optionally filtered by center"""
        queryset = cls.objects.filter(
            is_active=True,
            is_approved=True
        )
        if center_id:
            queryset = queryset.filter(center_id=center_id)
        return queryset
    
    @classmethod
    def get_phlebotomists_with_expiring_licenses(cls, days=30):
        """Get phlebotomists whose licenses expire within specified days"""
        expiry_threshold = date.today() + timedelta(days=days)
        return cls.objects.filter(
            license_expiry__lte=expiry_threshold,
            license_expiry__gte=date.today(),
            is_active=True
        )
    
    @classmethod
    def get_pending_approval(cls):
        """Get phlebotomists waiting for approval"""
        return cls.objects.filter(
            is_approved=False,
            is_active=True
        )


class Appointment(models.Model):
    """
    Appointment model for tracking donor blood donation appointments.
    Links donors to phlebotomists at specific centers.
    """
    
    # For donor donations - used for easy filtering/querying
    donor = models.ForeignKey(
        'donor.Donor', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Donor associated with this appointment (for blood donations)"
    )
    
    # GenericForeignKey to link to BloodDonate
    request_content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='appointment_requests',
        help_text="Content type of the related object (e.g., BloodDonate)"
    )
    request_object_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="ID of the related object"
    )
    request = GenericForeignKey('request_content_type', 'request_object_id')
    
    # Common fields
    date = models.DateTimeField(help_text="Appointment date and time")
    center = models.ForeignKey(
        DonationCenter, 
        on_delete=models.CASCADE,
        help_text="Donation center where appointment takes place"
    )
    phlebotomist = models.ForeignKey(
        'phlebotomist.Phlebotomist', 
        on_delete=models.CASCADE,
        help_text="Phlebotomist assigned to this appointment"
    )
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('collected', 'Sample Collected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        help_text="Current status of the appointment"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or comments about the appointment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ===== NEW: BARCODE FIELD =====
    barcode = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Blood bag barcode assigned to this donation"
    )
    
    # ===== NEW: SAFETY TRACKING FIELD =====
    sent_to_lab_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this sample was sent to the lab for testing"
    )
    
    # ===== NEW: REJECTION REASON FIELD =====
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for rejection (if applicable)"
    )
    
    # ===== NEW: ROLE TRACKING FIELDS =====
    approved_by_role = models.CharField(
        max_length=20,
        choices=[
            ('phlebotomist', 'Phlebotomist'),
            ('system', 'System'),
            ('admin', 'Admin'),
        ],
        null=True,
        blank=True,
        help_text="Role of the user who approved this appointment"
    )
    
    rejected_by_role = models.CharField(
        max_length=20,
        choices=[
            ('phlebotomist', 'Phlebotomist'),
            ('system', 'System'),
            ('admin', 'Admin'),
        ],
        null=True,
        blank=True,
        help_text="Role of the user who rejected this appointment"
    )
    
    collected_by_role = models.CharField(
        max_length=20,
        choices=[
            ('phlebotomist', 'Phlebotomist'),
            ('system', 'System'),
            ('admin', 'Admin'),
        ],
        null=True,
        blank=True,
        help_text="Role of the user who collected this blood sample"
    )
    
    cancelled_by_role = models.CharField(
        max_length=20,
        choices=[
            ('phlebotomist', 'Phlebotomist'),
            ('donor', 'Donor'),
            ('system', 'System'),
            ('admin', 'Admin'),
        ],
        null=True,
        blank=True,
        help_text="Role of the user who cancelled this appointment"
    )
    
    status_changed_by_role = models.CharField(
        max_length=20,
        choices=[
            ('phlebotomist', 'Phlebotomist'),
            ('lab_tech', 'Lab Technologist'),
            ('blood_bank_tech', 'Blood Bank Technician'),
            ('donor', 'Donor'),
            ('system', 'System'),
            ('admin', 'Admin'),
        ],
        null=True,
        blank=True,
        help_text="Role of the user who last changed the status"
    )
    
    # Tracking fields for status changes (existing)
    approved_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_appointments'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    rejected_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_appointments'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    collected_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_appointments'
    )
    collected_at = models.DateTimeField(null=True, blank=True)
    
    cancelled_by_user = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_appointments'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    status_changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='status_changed_appointments'
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['request_content_type', 'request_object_id']),
            models.Index(fields=['donor', 'status']),
            models.Index(fields=['phlebotomist', 'status']),
            models.Index(fields=['center', 'date']),
            models.Index(fields=['barcode']),  # NEW: index for barcode lookups
        ]
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
    
    def __str__(self):
        if self.donor:
            donor_name = self.donor.user.get_full_name() or self.donor.user.username
            return f"Donation Appointment: {donor_name} - {self.date.strftime('%Y-%m-%d %H:%M')}"
        elif self.request:
            return f"Request Appointment: {self.request} - {self.date.strftime('%Y-%m-%d %H:%M')}"
        return f"Appointment {self.id} - {self.date.strftime('%Y-%m-%d %H:%M')}"
    
    def clean(self):
        """
        Validation rules for Appointment model.
        """
        # Check if we have at least one way to identify what this appointment is for
        if not self.donor and not self.request:
            raise ValidationError(
                "Appointment must have either a donor or a request object"
            )
        
        # Validate status
        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError(f"Invalid status: {self.status}")
        
        # If we have a request, validate the content type
        if self.request_content_type and not self.request_object_id:
            raise ValidationError(
                "If request_content_type is set, request_object_id must also be set"
            )
        
        if self.request_object_id and not self.request_content_type:
            raise ValidationError(
                "If request_object_id is set, request_content_type must also be set"
            )
    
    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def appointment_type(self):
        """Return the type of appointment (donation, request, etc.)"""
        if self.donor and self.request_content_type:
            # Check if it's a BloodDonate
            from donor.models import BloodDonate
            donate_ct = ContentType.objects.get_for_model(BloodDonate)
            if self.request_content_type == donate_ct:
                return "blood_donation"
        
        if self.donor:
            return "donor_appointment"
        
        if self.request:
            return "request_appointment"
        
        return "unknown"
    
    @property
    def is_past_due(self):
        """Check if the appointment date has passed."""
        from django.utils import timezone
        return self.date < timezone.now()
    
    @property
    def can_be_approved(self):
        """Check if appointment can be approved."""
        return self.status == 'pending'
    
    @property
    def can_be_collected(self):
        """Check if blood sample can be collected."""
        return self.status == 'approved'
    
    @property
    def can_be_cancelled(self):
        """Check if appointment can be cancelled."""
        return self.status in ['pending', 'approved']
    
    def get_related_donation(self):
        """Get the related BloodDonate object if this is a donation appointment."""
        if self.request_content_type and self.request_object_id:
            from donor.models import BloodDonate
            donate_ct = ContentType.objects.get_for_model(BloodDonate)
            if self.request_content_type == donate_ct:
                try:
                    return BloodDonate.objects.get(id=self.request_object_id)
                except BloodDonate.DoesNotExist:
                    return None
        return None