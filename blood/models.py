from django.db import models
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid
from nurse.models import Appointment
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from django.conf import settings

# ------------------------
# Donation Center Model
# ------------------------
class DonationCenter(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    contact_number = models.CharField(max_length=15)
    open_hours = models.CharField(max_length=100)

    class Meta:
        unique_together = ('name', 'city')

    def __str__(self):
        return f"{self.name} ({self.city})"


# ------------------------
# Stock Aggregate Model
# ------------------------
class Stock(models.Model):
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    bloodgroup = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    unit = models.PositiveIntegerField(default=0)  # Total amount in ml for this bloodgroup and center
    center = models.ForeignKey('blood.DonationCenter', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('center', 'bloodgroup')
        verbose_name = "Stock"
        verbose_name_plural = "Stock"

    def __str__(self):
        return f"{self.bloodgroup} - {self.unit}ml at {self.center.name}"

# ------------------------
# Stock Unit Model
# ------------------------
class StockUnit(models.Model):
    BLOOD_GROUP_CHOICES = Stock.BLOOD_GROUP_CHOICES

    bloodgroup = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    unit = models.PositiveIntegerField(default=0)
    center = models.ForeignKey('blood.DonationCenter', on_delete=models.CASCADE)
    expiry_date = models.DateField()
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    added_on = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # Allow zero units, disallow negative
        if self.unit < 0:
            raise ValidationError("Unit must be zero or a positive integer.")
        if self.expiry_date < timezone.now().date():
            raise ValidationError("Expiry date cannot be in the past.")

    def generate_unique_barcode(self):
        for _ in range(10):
            candidate = f"STK-{uuid.uuid4().hex[:10].upper()}"
            if not StockUnit.objects.filter(barcode=candidate).exists():
                self.barcode = candidate
                return
        raise ValidationError("Failed to generate a unique barcode for StockUnit after several attempts.")

    def save(self, *args, **kwargs):
        self.clean()
        if not self.barcode:
            self.generate_unique_barcode()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bloodgroup} - {self.unit}ml at {self.center.name} (Expires: {self.expiry_date})"

# Signal to update Stock aggregate whenever StockUnit changes
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=StockUnit)
@receiver(post_delete, sender=StockUnit)
def update_stock_aggregate(sender, instance, **kwargs):
    total_units = StockUnit.objects.filter(
        center=instance.center,
        bloodgroup=instance.bloodgroup,
        expiry_date__gte=timezone.now().date()
    ).aggregate(total=Sum('unit'))['total'] or 0

    stock, created = Stock.objects.get_or_create(
        center=instance.center,
        bloodgroup=instance.bloodgroup,
        defaults={'unit': total_units}
    )
    if not created:
        stock.unit = total_units
        stock.save()
        

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

    URGENCY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Emergency', 'Emergency'),
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

    patient_name = models.CharField(max_length=30)
    patient_age = models.PositiveIntegerField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact = models.CharField(max_length=20, blank=True, null=True)
    national_id = models.CharField(max_length=50, blank=True, null=True)

    reason = models.CharField(max_length=500, blank=True)

    bloodgroup = models.CharField(
        max_length=10,
        choices=BLOOD_GROUP_CHOICES,
        blank=True,
        null=True
    )
    unit = models.PositiveIntegerField(
        default=0,
        blank=True,
        null=True
    )

    urgency_level = models.CharField(
        max_length=20,
        choices=URGENCY_CHOICES,
        default='Medium'
    )

    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.CASCADE,
        null=True,
        blank=True
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

    # Nurse action logging only (no admin fields)
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

    def save(self, *args, **kwargs):
        if not self.request_by_patient:
            raise ValidationError("A patient must be associated with this blood request.")

        if self.status.lower() not in dict(self.STATUS_CHOICES).keys():
            raise ValidationError(f"Invalid status value: {self.status}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Blood Request by {self.patient_name} ({self.bloodgroup}) - {self.status}"

# ------------------------
# Contact Models
# ------------------------
class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()


class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return self.name


# ------------------------
# Notification Model
# ------------------------
class Notification(models.Model):
    title = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    recipient_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    recipient_object_id = models.PositiveIntegerField(null=True, blank=True)
    recipient = GenericForeignKey('recipient_content_type', 'recipient_object_id')

    sender_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name='sender_content_type', null=True, blank=True
    )
    sender_object_id = models.PositiveIntegerField(null=True, blank=True)
    sender = GenericForeignKey('sender_content_type', 'sender_object_id')

    read = models.BooleanField(default=False)

    # 👉  for richer notifications
    action = models.CharField(max_length=20, blank=True, null=True)  # e.g. approved, rejected, completed
    reason = models.TextField(blank=True, null=True)  # nurse’s reason if reject/cancel
    appointment_date = models.DateTimeField(blank=True, null=True)
    bloodgroup = models.CharField(max_length=10, blank=True, null=True)
    unit = models.PositiveIntegerField(blank=True, null=True)

    def __str__(self):
        if self.recipient:
            return f"{self.title} for {self.recipient}"
        return f"{self.title} - No recipient specified"

class StockTransaction(models.Model):
    TRANSACTION_CHOICES = [
        ('deduction', 'Deduction'),
        ('addition', 'Addition'),
    ]
    
    stockunit = models.ForeignKey('StockUnit', on_delete=models.CASCADE)
    blood_request = models.ForeignKey('BloodRequest', on_delete=models.CASCADE, null=True, blank=True)
    donor_blood_request = models.ForeignKey('DonorBloodRequest', on_delete=models.CASCADE, null=True, blank=True)
    appointment = models.ForeignKey('nurse.Appointment', on_delete=models.CASCADE, null=True, blank=True)
    
    # When blood is taken out for a request: record quantity_deducted
    quantity_deducted = models.PositiveIntegerField(null=True, blank=True)
    # When blood is added from a donation: record quantity_added
    quantity_added = models.PositiveIntegerField(null=True, blank=True)
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_CHOICES)
    transaction_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Additional field for transaction notes/description
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the transaction")
    
    class Meta:
        verbose_name = "Stock Transaction"
        verbose_name_plural = "Stock Transactions"
        ordering = ['-transaction_at']
        
        # Add constraint to ensure only one quantity field is set
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(transaction_type='addition', quantity_added__isnull=False, quantity_deducted__isnull=True) |
                    models.Q(transaction_type='deduction', quantity_deducted__isnull=False, quantity_added__isnull=True)
                ),
                name='quantity_matches_transaction_type'
            )
        ]

    def clean(self):
        """Validate that quantity fields match transaction type"""
        if self.transaction_type == 'addition':
            if not self.quantity_added or self.quantity_deducted:
                raise ValidationError("Addition transactions must have quantity_added and not quantity_deducted")
        elif self.transaction_type == 'deduction':
            if not self.quantity_deducted or self.quantity_added:
                raise ValidationError("Deduction transactions must have quantity_deducted and not quantity_added")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.transaction_type == 'deduction':
            return f"Deducted {self.quantity_deducted}ml from {self.stockunit.barcode} for appointment {self.appointment_id}"
        elif self.transaction_type == 'addition':
            return f"Added {self.quantity_added}ml to {self.stockunit.barcode} from donation appointment {self.appointment_id}"
        else:
            return f"Stock transaction on {self.stockunit.barcode} @ {self.transaction_at}"

    @property
    def quantity(self):
        """Return the relevant quantity based on transaction type"""
        return self.quantity_added if self.transaction_type == 'addition' else self.quantity_deducted

    @property
    def related_request(self):
        """Return the related request object (BloodRequest or DonorBloodRequest)"""
        return self.blood_request or self.donor_blood_request
class DonorBloodRequest(models.Model):
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    URGENCY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Emergency', 'Emergency'),
    ]

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    request_by_donor = models.ForeignKey(
        'donor.Donor',
        on_delete=models.CASCADE,
        related_name='submitted_patient_requests'
    )

    patient_name = models.CharField(max_length=50)
    patient_age = models.PositiveIntegerField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    reason = models.CharField(max_length=500, blank=True)

    bloodgroup = models.CharField(max_length=10, choices=BLOOD_GROUP_CHOICES)
    unit = models.PositiveIntegerField(default=450, help_text="Requested amount in ml")

    urgency_level = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='Medium')
    donation_center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    consent_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_seen = models.BooleanField(default=False)
    stock_deducted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    appointments = GenericRelation(
        'nurse.Appointment',
        content_type_field='request_content_type',
        object_id_field='request_object_id',
        related_query_name='donor_blood_requests'
    )

    # === Nurse Action Logging Fields only ===
    approved_by_nurse = models.ForeignKey(
        'nurse.Nurse',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_donor_patient_requests_nurse'
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
        related_name='completed_donor_patient_requests_nurse'
    )
    completed_at_nurse = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.request_by_donor:
            raise ValidationError("A donor must be associated with this blood request.")

        if self.status.lower() not in dict(self.STATUS_CHOICES).keys():
            raise ValidationError(f"Invalid status value: {self.status}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Request by Donor {self.request_by_donor.user.username} for Patient {self.patient_name} ({self.bloodgroup})"