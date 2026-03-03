from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from utils.models import Notification
from django.utils import timezone
from datetime import date, timedelta
from utils.models import Notification
# from phlebotomist.models import Appointment  # Commented out to break circular import
from django.core.exceptions import ValidationError
import logging
KENYAN_COUNTIES = [
        ('Baringo', 'Baringo'),
        ('Bomet', 'Bomet'),
        ('Bungoma', 'Bungoma'),
        ('Busia', 'Busia'),
        ('Elgeyo-Marakwet', 'Elgeyo-Marakwet'),
        ('Embu', 'Embu'),
        ('Garissa', 'Garissa'),
        ('Homa Bay', 'Homa Bay'),
        ('Isiolo', 'Isiolo'),
        ('Kajiado', 'Kajiado'),
        ('Kakamega', 'Kakamega'),
        ('Kericho', 'Kericho'),
        ('Kiambu', 'Kiambu'),
        ('Kilifi', 'Kilifi'),
        ('Kirinyaga', 'Kirinyaga'),
        ('Kisii', 'Kisii'),
        ('Kisumu', 'Kisumu'),
        ('Kitui', 'Kitui'),
        ('Kwale', 'Kwale'),
        ('Laikipia', 'Laikipia'),
        ('Lamu', 'Lamu'),
        ('Machakos', 'Machakos'),
        ('Makueni', 'Makueni'),
        ('Mandera', 'Mandera'),
        ('Marsabit', 'Marsabit'),
        ('Meru', 'Meru'),
        ('Migori', 'Migori'),
        ('Mombasa', 'Mombasa'),
        ('Murang’a', 'Murang’a'),
        ('Nairobi', 'Nairobi'),
        ('Nakuru', 'Nakuru'),
        ('Nandi', 'Nandi'),
        ('Narok', 'Narok'),
        ('Nyamira', 'Nyamira'),
        ('Nyandarua', 'Nyandarua'),
        ('Nyeri', 'Nyeri'),
        ('Samburu', 'Samburu'),
        ('Siaya', 'Siaya'),
        ('Taita-Taveta', 'Taita-Taveta'),
        ('Tana River', 'Tana River'),
        ('Tharaka-Nithi', 'Tharaka-Nithi'),
        ('Trans Nzoia', 'Trans Nzoia'),
        ('Turkana', 'Turkana'),
        ('Uasin Gishu', 'Uasin Gishu'),
        ('Vihiga', 'Vihiga'),
        ('Wajir', 'Wajir'),
        ('West Pokot', 'West Pokot'),
    ]
# Blood group options
BLOODGROUP_CHOICES = (
    ('A+', 'A+'),
    ('A-', 'A-'),
    ('B+', 'B+'),
    ('B-', 'B-'),
    ('AB+', 'AB+'),
    ('AB-', 'AB-'),
    ('O+', 'O+'),
    ('O-', 'O-'),
)


# Blood donation status choices 
STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
)


# Gender choices for donor eligibility
GENDER_CHOICES = (
    ('Male', 'Male'),
    ('Female', 'Female'),
    ('Other', 'Other'),
)


class Donor(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='donor'  # Explicitly set related_name
    )
    profile_pic = models.ImageField(upload_to='profile_pic/Donor/', null=True, blank=True)
    bloodgroup = models.CharField(max_length=10, choices=BLOODGROUP_CHOICES, null=True, blank=True)
    bloodgroup_verified = models.BooleanField(default=False, help_text="Blood group verified by lab technician on first donation")
    bloodgroup_verified_by = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='verified_donor_bloodgroups',
        help_text="lab tech who verified the blood group"
    )
    bloodgroup_verified_at = models.DateTimeField(null=True, blank=True)
    total_donations = models.PositiveIntegerField(default=0, help_text="Total number of successful donations")
    county = models.CharField(max_length=50, choices=KENYAN_COUNTIES, null=True, blank=True)
    mobile = models.CharField(max_length=20, unique=True, null=True, blank=True)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    location_name = models.CharField(max_length=255, null=True, blank=True)
    points = models.PositiveIntegerField(default=0, help_text="Points earned by donor for successful donations")
    last_donation_date = models.DateField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    notifications = GenericRelation(
        Notification,
        content_type_field='recipient_content_type',
        object_id_field='recipient_object_id',
        related_query_name='donor_notifications'
    )
    
    # Add timestamp for when profile was created/updated
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Donor"
        verbose_name_plural = "Donors"
        ordering = ['user__username']
        # Add database constraints
        constraints = [
            # Ensure user is unique (already OneToOne, but this adds explicit constraint)
            models.UniqueConstraint(
                fields=['user'],
                name='unique_donor_user'
            ),
            # Ensure mobile is unique (already set, but explicit)
            models.UniqueConstraint(
                fields=['mobile'],
                name='unique_donor_mobile'
            ),
            # Ensure national_id is unique when not null
            models.UniqueConstraint(
                fields=['national_id'],
                name='unique_donor_national_id',
                condition=models.Q(national_id__isnull=False)
            ),
        ]
        # Add indexes for frequently queried fields
        indexes = [
            models.Index(fields=['bloodgroup']),
            models.Index(fields=['county']),
            models.Index(fields=['last_donation_date']),
        ]

    @property
    def age(self):
        if self.dob:
            today = date.today()
            return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))
        return None

    def next_eligible_donation_date(self):
        if self.last_donation_date:
            return self.last_donation_date + timedelta(days=56)
        return None

    def days_until_next_donation(self):
        next_date = self.next_eligible_donation_date()
        if next_date:
            delta = (next_date - timezone.now().date()).days
            return max(delta, 0)
        return 0

    @property
    def total_donations(self):
        return self.blooddonate_set.filter(status='approved').count()
        
    def get_age_group(self):
        """Helper method for donor segmentation"""
        age = self.age
        if age is None:
            return 'Unknown'
        elif age < 18:
            return 'Under 18'
        elif age < 30:
            return '18-29'
        elif age < 45:
            return '30-44'
        elif age < 60:
            return '45-59'
        else:
            return '60+'
            
    def can_donate(self):
        """Check if donor is eligible to donate"""
        if not self.is_eligible():
            return False, "Donor not eligible"
        
        days_until = self.days_until_next_donation()
        if days_until > 0:
            return False, f"Must wait {days_until} more days"
            
        # Add other eligibility checks here
        return True, "Eligible to donate"

    def is_eligible(self):
        """Basic eligibility check (override with actual logic)"""
        # This should be customized based on your eligibility criteria
        if self.age and self.age < 18:
            return False
        if not self.bloodgroup:
            return False
        # Add more eligibility criteria
        return True

    def __str__(self):
        return f"{self.user.username if self.user else 'No user'} - {self.bloodgroup or 'No blood group'}"

    def clean(self):
        """
        Validate that user doesn't have other profiles
        Called automatically by ModelForm in admin
        """
        from django.core.exceptions import ValidationError
        from blood.utils.validators import validate_single_profile  
        
        # Skip validation if this is an existing instance being updated
        if self.pk:
            return
        
        # Only validate if user is set
        if self.user:
            try:
                validate_single_profile(
                    user=self.user,
                    current_profile_type='donor',
                    exclude_self=True
                )
            except ValidationError as e:
                # Add a more user-friendly message
                raise ValidationError({
                    'user': f"This user already has a different profile. Each user can only have one role in the system."
                })
        
        # Validate age if dob is provided
        if self.dob and self.age and self.age < 16:  # Assuming 16 is minimum age
            raise ValidationError({
                'dob': f"Donor must be at least 16 years old. Current age: {self.age}"
            })

    def save(self, *args, **kwargs):
        """
        Override save to ensure validation runs
        """
        # Call full_clean() which will call clean() and field validation
        self.full_clean()
        
        # If user is set but no username exists in string representation
        if self.user and not self.pk:
            # Any pre-save logic here
            pass
            
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Optional: Handle cleanup when donor is deleted
        """
   
        super().delete(*args, **kwargs)
logger = logging.getLogger(__name__)
class BloodDonate(models.Model):
    donor = models.ForeignKey('donor.Donor', on_delete=models.CASCADE)

    bloodgroup = models.CharField(
        max_length=10,
        choices=BLOODGROUP_CHOICES,
        blank=True,
        null=True
    )
    unit = models.PositiveIntegerField(default=450, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    
    # UPDATED: Changed from DateField to DateTimeField to support appointments
    date = models.DateTimeField(default=timezone.now)
    
    is_seen = models.BooleanField(default=False)

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Changed from 'nurse' to 'phlebotomist'
    phlebotomist = models.ForeignKey(
        'phlebotomist.Phlebotomist',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Phlebotomist responsible for this donation"
    )

    # ===== NEW FIELDS FOR ENHANCED COLLECTION =====
    # Vital Signs
    temperature = models.DecimalField(
        max_digits=4, 
        decimal_places=1, 
        null=True, 
        blank=True,
        help_text="Body temperature in °C"
    )
    pulse = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Heart rate in beats per minute"
    )
    blood_pressure_systolic = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Systolic blood pressure (top number)"
    )
    blood_pressure_diastolic = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Diastolic blood pressure (bottom number)"
    )
    haemoglobin = models.DecimalField(
        max_digits=4, 
        decimal_places=1, 
        null=True, 
        blank=True,
        help_text="Haemoglobin level in g/dL"
    )

    # Donation Details
    DONATION_TYPE_CHOICES = [
        ('whole_blood', 'Whole Blood'),
        ('double_red', 'Double Red Cells'),
        ('platelets', 'Platelets'),
        ('plasma', 'Plasma'),
        ('pediatric', 'Pediatric'),
    ]
    
    donation_type = models.CharField(
        max_length=20,
        choices=DONATION_TYPE_CHOICES,
        default='whole_blood'
    )

    bleed_time_start = models.TimeField(
        null=True, 
        blank=True,
        help_text="Time when blood collection started"
    )
    bleed_time_end = models.TimeField(
        null=True, 
        blank=True,
        help_text="Time when blood collection completed"
    )
    
    BLEED_COMPLETION_CHOICES = [
        ('complete', 'Complete - Full Unit'),
        ('partial', 'Partial - Underweight'),
        ('incomplete', 'Incomplete - Stopped Early'),
    ]
    
    bleed_completion = models.CharField(
        max_length=20,
        choices=BLEED_COMPLETION_CHOICES,
        default='complete'
    )

    # Arm/Vein Details
    ARM_CHOICES = [
        ('left', 'Left Arm'),
        ('right', 'Right Arm'),
    ]
    
    arm_used = models.CharField(
        max_length=10, 
        choices=ARM_CHOICES, 
        null=True, 
        blank=True
    )
    
    VEIN_QUALITY_CHOICES = [
        ('good', 'Good - Easy access'),
        ('fair', 'Fair - Acceptable'),
        ('poor', 'Poor - Difficult'),
    ]
    
    vein_quality = models.CharField(
        max_length=20,
        choices=VEIN_QUALITY_CHOICES,
        null=True,
        blank=True
    )
    
    attempts_count = models.IntegerField(
        default=1,
        help_text="Number of venipuncture attempts"
    )
    
    phlebotomist_notes = models.TextField(
        blank=True,
        help_text="Phlebotomist's observations during collection"
    )

    # Adverse Events
    ADVERSE_EVENT_CHOICES = [
        ('none', 'None'),
        ('hematoma', 'Hematoma'),
        ('fainting', 'Fainting/Syncope'),
        ('nausea', 'Nausea/Vomiting'),
        ('pain', 'Excessive Pain'),
        ('other', 'Other'),
    ]
    
    adverse_event = models.CharField(
        max_length=20,
        choices=ADVERSE_EVENT_CHOICES,
        default='none'
    )
    
    adverse_event_details = models.TextField(
        blank=True,
        help_text="Description of adverse event if occurred"
    )

    # Collection Notes
    collection_notes = models.TextField(
        blank=True,
        help_text="General notes about the collection process"
    )

    # ===== EXISTING FIELDS (KEEP AS IS) =====
    # Approval fields - updated field names
    approved_by_phlebotomist = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='phlebotomist_approved_donations'
    )
    approved_at_phlebotomist = models.DateTimeField(null=True, blank=True)

    # Completion fields - updated field names
    completed_by_phlebotomist = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='phlebotomist_completed_donations'
    )
    completed_at_phlebotomist = models.DateTimeField(null=True, blank=True)

    # Rejection / cancellation
    REJECTED_BY_CHOICES = [
        ('phlebotomist', 'Phlebotomist'),
        ('admin', 'Admin'),
    ]
    
    rejected_by = models.CharField(
        max_length=15,
        choices=REJECTED_BY_CHOICES,
        null=True,
        blank=True
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    CANCELLED_BY_CHOICES = [
        ('phlebotomist', 'Phlebotomist'),
        ('donor', 'Donor'),
        ('admin', 'Admin'),
    ]
    
    cancelled_by = models.CharField(
        max_length=15,
        choices=CANCELLED_BY_CHOICES,
        null=True,
        blank=True
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Stock update
    stock_added_by_phlebotomist = models.BooleanField(default=False)

    # Appointment relation
    appointments = GenericRelation(
        'phlebotomist.Appointment',
        content_type_field='request_content_type',
        object_id_field='request_object_id',
        related_query_name='blood_donations'
    )

    class Meta:
        ordering = ['-date']
        verbose_name = "Blood Donation"
        verbose_name_plural = "Blood Donations"

    def __str__(self):
        donor_name = self.donor.user.get_full_name() or self.donor.user.username
        return f"Donation on {self.date} by {donor_name} ({self.status})"

    @property
    def donor_age(self):
        """Return donor's age at time of donation if DOB and date are set."""
        if self.donor and self.donor.dob and self.date:
            birth_date = self.donor.dob
            donation_date = self.date.date() if hasattr(self.date, 'date') else self.date
            age = donation_date.year - birth_date.year - (
                (donation_date.month, donation_date.day) < (birth_date.month, birth_date.day)
            )
            return age
        return None

    @property
    def was_finalized(self):
        """Check if donation is in a terminal state."""
        return self.status in ['completed', 'cancelled', 'rejected']

    @property
    def is_approved(self):
        """Check if donation has been approved by a phlebotomist."""
        return bool(self.approved_by_phlebotomist)
    
    @property
    def blood_pressure(self):
        """Return formatted blood pressure string."""
        if self.blood_pressure_systolic and self.blood_pressure_diastolic:
            return f"{self.blood_pressure_systolic}/{self.blood_pressure_diastolic}"
        return None
    
    @property
    def bleed_duration_minutes(self):
        """Calculate bleed duration in minutes."""
        if self.bleed_time_start and self.bleed_time_end:
            from datetime import datetime, timedelta
            dummy_date = datetime.now().date()
            start = datetime.combine(dummy_date, self.bleed_time_start)
            end = datetime.combine(dummy_date, self.bleed_time_end)
            if end < start:
                end += timedelta(days=1)
            duration = (end - start).total_seconds() / 60
            return round(duration, 1)
        return None

    def get_action_actor(self):
        """
        Returns a human-readable actor string for finalized actions.
        Example: "Phlebotomist Jane", "the Donor", or "system".
        """
        if self.completed_by_phlebotomist:
            return f"Phlebotomist {self.completed_by_phlebotomist.get_full_name() or self.completed_by_phlebotomist.username}"
        if self.rejected_by == 'phlebotomist':
            return "a Phlebotomist"
        if self.cancelled_by == 'phlebotomist':
            return "a Phlebotomist"
        if self.cancelled_by == 'donor':
            return "the Donor"
        return "system"

    def clean(self):
        """Prevent donor from having multiple pending donations."""
        if hasattr(self, 'donor') and self.donor and self.status == 'pending':
            qs = BloodDonate.objects.filter(donor=self.donor, status='pending')
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    "You already have a pending donation request. Please resolve it before creating a new one."
                )
class DonorEligibility(models.Model):
    donor = models.OneToOneField(Donor, on_delete=models.CASCADE)
    age = models.IntegerField(default=0)
    weight = models.FloatField(default=0.0)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Other')
    good_health = models.BooleanField(default=True)
    travel_history = models.BooleanField(default=False)
    pregnant = models.BooleanField(default=False)
    medical_conditions = models.TextField(default='', blank=True)
    approved = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Donor Eligibility"
        verbose_name_plural = "Donor Eligibilities"

    def __str__(self):
        return f"Eligibility - {self.donor.user.username}"
