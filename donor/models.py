from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from blood.models import Notification, DonationCenter
from nurse.models import Nurse
from django.utils import timezone
from datetime import date, timedelta
from nurse.models import Appointment
from django.core.exceptions import ValidationError
import logging

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
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_pic = models.ImageField(upload_to='profile_pic/Donor/', null=True, blank=True)
    bloodgroup = models.CharField(max_length=10, choices=BLOODGROUP_CHOICES, null=True, blank=True)
    address = models.CharField(max_length=40)
    mobile = models.CharField(max_length=20, unique=True)
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

    class Meta:
        verbose_name = "Donor"
        verbose_name_plural = "Donors"
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} - {self.bloodgroup}"
logger = logging.getLogger(__name__)


class BloodDonate(models.Model):
    donor = models.ForeignKey('donor.Donor', on_delete=models.CASCADE)

    bloodgroup = models.CharField(
        max_length=10,
        choices=BLOODGROUP_CHOICES,
        blank=True,
        null=True
    )
    unit = models.PositiveIntegerField(default=0, blank=True, null=True)  # optional unit
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    date = models.DateField(default=timezone.now)
    is_seen = models.BooleanField(default=False)

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    nurse = models.ForeignKey(
        'nurse.Nurse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Nurse responsible for this donation"
    )

    # --- Approval fields (only nurse) ---
    approved_by_nurse = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='nurse_approved_donations'
    )
    approved_at_nurse = models.DateTimeField(null=True, blank=True)

    # --- Completion fields (only nurse) ---
    completed_by_nurse = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='nurse_completed_donations'
    )
    completed_at_nurse = models.DateTimeField(null=True, blank=True)

    # --- Rejection / cancellation (nurse or donor only) ---
    rejected_by = models.CharField(
        max_length=10,
        choices=[('nurse', 'Nurse')],
        null=True,
        blank=True
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    cancelled_by = models.CharField(
        max_length=10,
        choices=[('nurse', 'Nurse'), ('donor', 'Donor')],
        null=True,
        blank=True
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # --- Stock update (nurse only) ---
    stock_added_by_nurse = models.BooleanField(default=False)

    # --- Appointment relation ---
    appointments = GenericRelation(
        Appointment,
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
            donation_date = self.date
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
        """Check if donation has been approved by a nurse."""
        return bool(self.approved_by_nurse)

    def get_action_actor(self):
        """
        Returns a human-readable actor string for finalized actions.
        Example: "Nurse Jane", "the Donor", or "system".
        """
        if self.completed_by_nurse:
            return f"Nurse {self.completed_by_nurse.get_full_name() or self.completed_by_nurse.username}"
        if self.rejected_by == 'nurse':
            return "a Nurse"
        if self.cancelled_by == 'nurse':
            return "a Nurse"
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
