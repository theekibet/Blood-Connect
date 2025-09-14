import uuid
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.exceptions import ValidationError


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
    phone = models.CharField(max_length=20, blank=True, null=True)

    registration_number = models.CharField(
        max_length=30,
        unique=True,
        help_text="Official nurse registration/license number",
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
        help_text="Upload a profile picture"
    )

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL,
        null=True,
        related_name='nurses'
    )

    bio = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self):
        # Returns the full name anchored to User fields as a fallback
        first = self.first_name if self.first_name else self.user.first_name
        last = self.last_name if self.last_name else self.user.last_name
        return f"{first} {last}"

    def __str__(self):
        return f"{self.full_name} - {self.get_specialization_display()}"

    def request_blood(self, bloodgroup, required_units):
        """
        Request blood from nearby donation centers based on low stock in nurse's center.
        Avoid import circularity by importing here below.
        """
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
    ]

    CANCELLED_BY_CHOICES = [
        ('donor', 'Donor'),
        ('nurse', 'Nurse'),
        ('system', 'System'),
        ('unknown', 'Unknown'),
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
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    # Tracking status changes (always nurse-driven)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointment_status_updates'
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
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Nurse actions only
    approved_by_nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='nurse_approved_appointments'
    )
    approved_at_nurse = models.DateTimeField(null=True, blank=True)

    completed_by_nurse = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='nurse_completed_appointments'
    )
    completed_at_nurse = models.DateTimeField(null=True, blank=True)

    rejected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date']

    @property
    def is_donation(self):
        """Return True if this is a pure donation appointment (donor only)."""
        return self.request_content_type is None and self.donor is not None

    @property
    def is_blood_request(self):
        """True if linked to a BloodRequest or DonorBloodRequest."""
        return self.request_content_type is not None

    def __str__(self):
        participants = []
        if self.donor:
            participants.append(f"Donor {self.donor.user.username}")
        if self.patient:
            participants.append(f"Patient {self.patient.user.username}")
        participant_str = " & ".join(participants) if participants else "No participant"
        return f"Appointment on {self.date.strftime('%Y-%m-%d %H:%M')} with Nurse {self.nurse.last_name} and {participant_str}"

    def set_status(self, status, user):
        """
        Nurse-only method for updating appointment status.
        Admins cannot change status; they only view/report.
        """
        if not hasattr(user, 'nurse'):
            raise ValidationError("Only nurses can update appointment status.")

        self.status = status
        self.status_changed_at = timezone.now()
        self.status_changed_by = user

        if status == 'approved':
            self.approved_by_nurse = user
            self.approved_at_nurse = timezone.now()
        elif status == 'completed':
            self.completed_by_nurse = user
            self.completed_at_nurse = timezone.now()
        elif status == 'rejected':
            self.rejected_at = timezone.now()
        elif status == 'cancelled':
            self.cancelled_by = 'nurse'
            self.cancelled_at = timezone.now()
            self.cancelled_by_user = user

        self.save()

    def clean(self):
        """
        Validate donor vs patient rules and request consistency.
        """
        from blood.models import BloodRequest, DonorBloodRequest
        from donor.models import BloodDonate

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
        super().save(*args, **kwargs)
class NurseBloodRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_FULFILLED = 'fulfilled'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_FULFILLED, 'Fulfilled'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Use local BLOOD_GROUP_CHOICES constant to avoid import problems
    BLOOD_GROUP_CHOICES = BLOOD_GROUP_CHOICES

    URGENCY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    requester = models.ForeignKey(
        'nurse.Nurse',
        on_delete=models.CASCADE,
        related_name='blood_requests_made',
        help_text='Nurse who made the blood request.'
    )
    supplying_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.CASCADE,
        related_name='outgoing_requests',
        help_text='Donation center supplying the requested blood.'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUP_CHOICES,
        help_text='Blood group requested.'
    )
    units = models.PositiveIntegerField(
        help_text='Quantity of blood requested in milliliters.'
    )
    urgency_level = models.CharField(
        max_length=10,
        choices=URGENCY_CHOICES,
        default='medium',
        help_text='Indicate the urgency of this blood request.'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text='Current status of the blood request.'
    )
    reason = models.TextField(
        blank=True,
        null=True,
        help_text='Reason or notes for this blood request.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    used_stock_units = models.ManyToManyField(
        'blood.StockUnit',
        through='NurseBloodRequestStockUnit',
        related_name='blood_requests',
        blank=True,
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nurse Blood Request'
        verbose_name_plural = 'Nurse Blood Requests'

    def __str__(self):
        nurse_name = getattr(self.requester, 'get_full_name', None)
        nurse_display = nurse_name() if callable(nurse_name) else str(self.requester)
        if not nurse_display:
            nurse_display = self.requester.last_name
        return f"{self.units}ml {self.blood_group} requested from {self.supplying_center.name} by Nurse {nurse_display}"


class NurseBloodRequestStockUnit(models.Model):
    blood_request = models.ForeignKey('nurse.NurseBloodRequest', on_delete=models.CASCADE)
    stock_unit = models.ForeignKey('blood.StockUnit', on_delete=models.CASCADE)
    units_used = models.PositiveIntegerField(help_text='Amount of blood (ml) used from this stock unit.')

    class Meta:
        unique_together = ('blood_request', 'stock_unit')

    def __str__(self):
        return f"{self.units_used}ml from {self.stock_unit} for request #{self.blood_request.id}"
