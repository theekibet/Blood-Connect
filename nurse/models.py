import uuid
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

BLOOD_GROUP_CHOICES = [
    ('A+', 'A+'), ('A-', 'A-'),
    ('B+', 'B+'), ('B-', 'B-'),
    ('AB+', 'AB+'), ('AB-', 'AB-'),
    ('O+', 'O+'), ('O-', 'O-'),
]


class Nurse(models.Model):
    SPECIALIZATION_CHOICES = [
        ('Blood Bank Nurse', 'Blood Bank Nurse'),
        ('Transfusion Nurse', 'Transfusion Nurse'),
        ('Clinical Nurse Specialist', 'Clinical Nurse Specialist'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    
    # Phone validator
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=20,
        blank=False,
        null=False,
        help_text="Enter phone number in format: +999999999"
    )

    # Registration number validator
    registration_number_regex = RegexValidator(
        regex=r'^[A-Z0-9]{5,30}$',
        message="Registration number must be 5-30 characters (uppercase letters and numbers only)."
    )
    registration_number = models.CharField(
        max_length=30,
        unique=True,
        validators=[registration_number_regex],
        help_text="Official nurse registration/license number (5-30 alphanumeric characters)",
    )

    specialization = models.CharField(
        max_length=50,
        choices=SPECIALIZATION_CHOICES,
        null=False,
        blank=False,
        help_text="Select specialization relevant to blood donation",
    )

    profile_pic = models.ImageField(
        upload_to='nurse_profiles/', 
        blank=True, 
        null=True,
        help_text="Upload a profile picture (max 5MB)"
    )

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL,
        null=True,
        related_name='nurses'
    )

    bio = models.TextField(
        blank=True, 
        null=True,
        max_length=500,
        help_text="Brief bio (max 500 characters)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # NEW APPROVAL FIELDS
    is_approved = models.BooleanField(
        default=False,
        help_text="Admin approval status - nurse cannot access system until approved"
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_nurses',
        help_text="Admin who approved this nurse"
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the nurse was approved"
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for rejection if applicable"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nurse'
        verbose_name_plural = 'Nurses'

    def clean(self):
        """Custom validation"""
        super().clean()
        
        # Validate phone
        if self.phone:
            # Remove spaces and dashes
            phone_clean = self.phone.replace(' ', '').replace('-', '')
            if len(phone_clean) < 10:
                raise ValidationError({'phone': 'Phone number must be at least 10 digits.'})
        
        # Validate bio length
        if self.bio and len(self.bio) > 500:
            raise ValidationError({'bio': 'Bio cannot exceed 500 characters.'})
        
        # Validate profile picture size (max 5MB)
        if self.profile_pic:
            if self.profile_pic.size > 5 * 1024 * 1024:  # 5MB
                raise ValidationError({'profile_pic': 'Profile picture size cannot exceed 5MB.'})

    def save(self, *args, **kwargs):
        self.full_clean()  # Always validate before saving
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Returns the full name anchored to User fields as a fallback"""
        first = self.first_name if self.first_name else self.user.first_name
        last = self.last_name if self.last_name else self.user.last_name
        return f"{first} {last}"

    @property
    def approval_status(self):
        """Get readable approval status"""
        if self.is_approved:
            return "Approved"
        elif self.rejection_reason:
            return "Rejected"
        else:
            return "Pending"

    def approve(self, approved_by_user):
        """Approve the nurse account"""
        self.is_approved = True
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = None
        self.save()

    def reject(self, reason, rejected_by_user):
        """Reject the nurse account"""
        self.is_approved = False
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def __str__(self):
        status = " [PENDING]" if not self.is_approved else ""
        return f"{self.full_name} - {self.get_specialization_display()}{status}"

    def request_blood(self, bloodgroup, required_units):
        """
        Request blood from nearby donation centers based on low stock in nurse's center.
        Only available for approved nurses.
        """
        if not self.is_approved:
            return "Your account is not approved yet. Please wait for admin approval."
        
        from blood.models import Stock, BloodRequest, StockUnit

        LOW_STOCK_THRESHOLD = 500  # ml threshold, adjust as needed

        if not self.donation_center:
            return "Nurse is not assigned to any donation center."

        try:
            stock = Stock.objects.get(center=self.donation_center, bloodgroup=bloodgroup)
        except Stock.DoesNotExist:
            return f"No stock data available for blood group {bloodgroup} at your donation center."

        if stock.unit > LOW_STOCK_THRESHOLD:
            return f"Stock level for {bloodgroup} is sufficient in your donation center."

        expiry_threshold = timezone.now().date() + timedelta(days=7)

        nearby_stock_units = StockUnit.objects.filter(
            center__city=self.donation_center.city,
            bloodgroup=bloodgroup,
            unit__gte=required_units,
            expiry_date__lte=expiry_threshold
        ).exclude(center=self.donation_center).order_by('expiry_date')

        if not nearby_stock_units.exists():
            return "No nearby donation centers have the required blood group units close to expiry."

        donor_stock_unit = nearby_stock_units.first()

        blood_request = BloodRequest.objects.create(
            patient_name=f"Requested by Nurse {self.full_name}",
            patient_age=0,
            contact_number='',
            reason='Request due to low stock and near expiry availability at other centers',
            bloodgroup=bloodgroup,
            unit=required_units,
            urgency_level='Medium',
            donation_center=donor_stock_unit.center,
            consent_confirmed=True,
            status='Pending',
            request_by_donor=None,
            request_by_patient=None,
        )

        return f"Blood request created successfully for {required_units}ml of {bloodgroup} from {donor_stock_unit.center.name}."
    
    
class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('collected', 'Collected - Awaiting Testing'),  # NEW STATUS
    ]

    CANCELLED_BY_CHOICES = [
        ('donor', 'Donor'),
        ('nurse', 'Nurse'),
        ('system', 'System'),
        ('unknown', 'Unknown'),
    ]

    # ===== ROLE CHOICES =====
    ROLE_CHOICES = [
        ('nurse', 'Nurse/Phlebotomist'),
        ('lab_tech', 'Lab Technologist'),
        ('blood_bank_tech', 'Blood Bank Technician'),
        ('system', 'System'),
    ]

    nurse = models.ForeignKey(
        'nurse.Nurse',
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    patient = models.ForeignKey(
        'patient.Patient',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments'
    )
    donor = models.ForeignKey(
        'donor.Donor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments'
    )
    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments'
    )

    # Generic foreign key linking to BloodRequest, DonorBloodRequest, or BloodDonate
    request_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    request_object_id = models.PositiveIntegerField(null=True, blank=True)
    request = GenericForeignKey('request_content_type', 'request_object_id')
    date = models.DateTimeField()
    status = models.CharField(
        max_length=20,  # Increased from 10 to accommodate 'collected'
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Barcode field
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Tracking status changes
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointment_status_updates'
    )
    status_changed_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True,
        help_text='Role of the person who last changed status'
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)

    # Cancellation tracking
    cancelled_by = models.CharField(
        max_length=10,
        choices=CANCELLED_BY_CHOICES,
        null=True,
        blank=True
    )
    cancelled_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments_cancelled'
    )
    cancelled_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Approval tracking (nurse/phlebotomist)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_appointments'
    )
    approved_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True,
        default='nurse'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Collection tracking (nurse/phlebotomist)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='collected_appointments'
    )
    collected_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True,
        default='nurse'
    )
    collected_at = models.DateTimeField(null=True, blank=True)

    # Lab testing tracking
    sent_to_lab_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When blood was sent to lab for testing'
    )
    lab_received_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When lab received the sample'
    )
    lab_tested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='tested_appointments'
    )
    lab_tested_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    lab_tested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When lab completed testing'
    )

    # Completion tracking (can be nurse or lab tech depending on workflow)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='completed_appointments'
    )
    completed_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    # Rejection tracking
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rejected_appointments'
    )
    rejected_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    # ===== SAFETY VERIFICATION TRACKING =====
    safety_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='safety_verified_appointments'
    )
    safety_verified_by_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    safety_verified_at = models.DateTimeField(null=True, blank=True)
    safety_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Verification'),
            ('safe', 'Safe'),
            ('unsafe', 'Unsafe'),
        ],
        default='pending'
    )

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['donor']),
            models.Index(fields=['patient']),
            models.Index(fields=['-date']),
        ]

    @property
    def is_donation(self):
        """Return True if this is a pure donation appointment (donor only)."""
        return self.request_content_type is None and self.donor is not None

    @property
    def is_blood_request(self):
        """True if linked to a BloodRequest or DonorBloodRequest."""
        return self.request_content_type is not None

    @property
    def current_phase(self):
        """Return current workflow phase"""
        if self.status == 'pending':
            return 'pending_approval'
        elif self.status == 'approved':
            return 'awaiting_collection'
        elif self.status == 'collected':
            return 'awaiting_testing'
        elif self.status == 'completed':
            if self.safety_status == 'safe':
                return 'completed_safe'
            elif self.safety_status == 'unsafe':
                return 'completed_unsafe'
            return 'completed'
        elif self.status in ['rejected', 'cancelled']:
            return 'terminated'
        return self.status

    def __str__(self):
        participants = []
        if self.donor:
            participants.append(f"Donor {self.donor.user.username}")
        if self.patient:
            participants.append(f"Patient {self.patient.user.username}")
        participant_str = " & ".join(participants) if participants else "No participant"
        return f"Appointment {self.barcode or self.id} - {self.get_status_display()} - {participant_str}"

    def generate_unique_barcode(self):
        """Generate a unique barcode for the appointment."""
        for _ in range(10):
            candidate = f"APT-{uuid.uuid4().hex[:10].upper()}"
            if not Appointment.objects.filter(barcode=candidate).exists():
                self.barcode = candidate
                return
        raise ValidationError("Failed to generate a unique barcode for Appointment after several attempts.")

    def set_status(self, status, user, role='nurse', **kwargs):
        """
        Update appointment status with role tracking
        """
        self.status = status
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.status_changed_by_role = role

        if status == 'approved':
            self.approved_by = user
            self.approved_by_role = role
            self.approved_at = timezone.now()
            
        elif status == 'collected':
            self.collected_by = user
            self.collected_by_role = role
            self.collected_at = timezone.now()
            self.sent_to_lab_at = timezone.now()
            
        elif status == 'completed':
            self.completed_by = user
            self.completed_by_role = role
            self.completed_at = timezone.now()
            
        elif status == 'rejected':
            self.rejected_by = user
            self.rejected_by_role = role
            self.rejected_at = timezone.now()
            self.rejection_reason = kwargs.get('reason', '')
            
        elif status == 'cancelled':
            self.cancelled_by = kwargs.get('cancelled_by', 'nurse')
            self.cancelled_by_user = user
            self.cancelled_by_role = role
            self.cancelled_at = timezone.now()

        self.save()

    def mark_safety_verified(self, user, role, safety_status, notes=None):
        """Mark safety verification status"""
        self.safety_verified_by = user
        self.safety_verified_by_role = role
        self.safety_verified_at = timezone.now()
        self.safety_status = safety_status
        if notes:
            self.safety_notes = notes
        self.save(update_fields=[
            'safety_verified_by', 'safety_verified_by_role',
            'safety_verified_at', 'safety_status'
        ])

    def clean(self):
        """
        Validate donor vs patient rules and request consistency.
        """
        from donor.models import DonorBloodRequest
        from donor.models import BloodDonate
        from patient.models import BloodRequest

        if self.donor and not self.patient:
            if self.request_content_type is not None:
                if not (isinstance(self.request, DonorBloodRequest) or isinstance(self.request, BloodDonate)):
                    raise ValidationError("Donation appointments cannot be linked to a BloodRequest.")
            return

        if self.patient and not self.donor:
            if not self.request or not isinstance(self.request, BloodRequest):
                raise ValidationError("Patient appointments must link to a BloodRequest.")
            return

        if self.is_blood_request:
            if not (isinstance(self.request, BloodRequest) or isinstance(self.request, DonorBloodRequest)):
                raise ValidationError("Blood request appointments must link to BloodRequest or DonorBloodRequest.")
            return

        if not self.donor and not self.patient:
            raise ValidationError("Appointment must involve at least a donor or a patient.")

        if self.donor and self.patient:
            raise ValidationError("Appointment cannot be linked to both donor and patient.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.barcode:
            self.generate_unique_barcode()
        super().save(*args, **kwargs)
        
