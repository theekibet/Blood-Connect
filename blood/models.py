from django.db import models
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from django.conf import settings
import logging
logger = logging.getLogger(__name__)
class HoneypotAttempt(models.Model):
    """Track fake admin login attempts"""
    ip = models.GenericIPAddressField()
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)  
    user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Honeypot Attempt"
        verbose_name_plural = "Honeypot Attempts"
    
    def __str__(self):
        return f"Attack from {self.ip} at {self.timestamp}"

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
    is_active = models.BooleanField(default=True) 
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
    """Individual blood unit in inventory - expiry set by lab tech after testing"""
    
    BLOOD_GROUP_CHOICES = Stock.BLOOD_GROUP_CHOICES
    
    SAFETY_STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('safe', 'Safe for Use'),
        ('unsafe', 'Unsafe - Do Not Use'),
    ]

    # Who added this to stock
    ADDED_BY_ROLE_CHOICES = [
        ('phlebotomist', 'Phlebotomist'),
        ('lab_tech', 'Lab Technologist'),
        ('system', 'System'),
    ]
    
    # Component type - determines expiry length
    COMPONENT_TYPE_CHOICES = [
        ('whole_blood', '🩸 Whole Blood (35 days)'),
        ('rbc', '🔴 Packed Red Blood Cells (42 days)'),
        ('platelets', '🟡 Platelets (5 days)'),
        ('ffp', '❄️ Fresh Frozen Plasma (1 year)'),
        ('cryo', '🧊 Cryoprecipitate (1 year)'),
    ]

    bloodgroup = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    unit = models.PositiveIntegerField(default=0)
    center = models.ForeignKey('blood.DonationCenter', on_delete=models.CASCADE)
    
    # ===== EXPIRY DATE - NULL for unsafe blood =====
    expiry_date = models.DateField(
        null=True,  # ← CHANGED: Allow null for unsafe blood
        blank=True,  # ← CHANGED: Allow blank for unsafe blood
        help_text='When the blood expires. NULL for unsafe/discarded blood.'
    )
    
    # ===== COMPONENT TYPE - Added to calculate expiry =====
    component_type = models.CharField(
        max_length=20,
        choices=COMPONENT_TYPE_CHOICES,
        default='whole_blood',
        help_text='Type of blood component - determines expiry period'
    )
    
    # ===== BARCODE - MUST come from pre-generated blood bag =====
    barcode = models.CharField(
        max_length=100, 
        unique=True, 
        blank=False,
        null=False,
        help_text='Barcode from pre-generated blood bag'
    )
    
    added_on = models.DateTimeField(auto_now_add=True)
    
    # ===== Link to the pre-generated blood bag barcode =====
    blood_bag_barcode = models.OneToOneField(
        'blood.BloodBagBarcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_unit',
        help_text='The pre-generated blood bag barcode used for this donation'
    )
    
    # Link to blood donation
    blood_donation = models.ForeignKey(
        'donor.BloodDonate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_units',
        help_text='Blood donation that produced this unit'
    )
    
    # ===== SAFETY VERIFICATION FIELDS =====
    safety_status = models.CharField(
        max_length=20,
        choices=SAFETY_STATUS_CHOICES,
        default='pending',
        help_text='Safety verification status of this blood unit'
    )
    
    safety_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_stock_units',
        help_text='User who verified the safety status'
    )
    
    safety_verified_by_role = models.CharField(
        max_length=20,
        choices=ADDED_BY_ROLE_CHOICES,
        null=True,
        blank=True,
        help_text='Role of the person who verified safety'
    )
    
    safety_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the safety verification was done'
    )
    
    safety_notes = models.TextField(
        blank=True,
        null=True,
        help_text='Notes about safety verification (e.g., test results, issues found)'
    )
    
    # For unsafe units - record why they're unsafe
    unsafe_reason = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        choices=[
            ('hiv_positive', 'HIV Positive'),
            ('hepatitis_b_positive', 'Hepatitis B Positive'),
            ('hepatitis_c_positive', 'Hepatitis C Positive'),
            ('syphilis_positive', 'Syphilis Positive'),
            ('malaria_positive', 'Malaria Positive'),
            ('multiple_markers', 'Multiple Disease Markers'),
            ('contamination', 'Bacterial Contamination'),
            ('hemolysis', 'Hemolysis Detected'),
            ('lipemic', 'Lipemic Sample'),
            ('improper_storage', 'Improper Storage'),
            ('expired', 'Expired'),
            ('other', 'Other Reason'),
        ],
        help_text='Reason why blood is marked unsafe'
    )
    
    # Quarantine status for unsafe units
    is_quarantined = models.BooleanField(
        default=False,
        help_text='Whether this unit is quarantined and cannot be used'
    )
    
    # ===== TRACK WHO ADDED TO INVENTORY =====
    added_to_inventory_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='added_stock_units',
        help_text='User who added this to inventory'
    )
    
    added_to_inventory_by_role = models.CharField(
        max_length=20,
        choices=ADDED_BY_ROLE_CHOICES,
        default='phlebotomist',
        null=True,
        blank=True,
        help_text='Role of the person who added to inventory'
    )
    
    added_to_inventory_at = models.DateTimeField(
        null=True,
        blank=True,
        auto_now_add=True,
        help_text='When this was added to inventory'
    )

    class Meta:
        unique_together = ('center', 'barcode')
        verbose_name = "Stock Unit"
        verbose_name_plural = "Stock Units"
        ordering = ['-added_on']
        indexes = [
            models.Index(fields=['expiry_date']),
            models.Index(fields=['safety_status']),
            models.Index(fields=['bloodgroup']),
        ]

    def clean(self):
        # Unit validation
        if self.unit < 0:
            raise ValidationError("Unit must be zero or a positive integer.")
        
        # For safe blood, expiry date must be set and valid
        if self.safety_status == 'safe':
            if not self.expiry_date:
                raise ValidationError("Expiry date is required for safe blood.")
            if self.expiry_date < timezone.now().date():
                raise ValidationError("Expiry date cannot be in the past.")
        
        # For unsafe blood, expiry date should be null
        if self.safety_status == 'unsafe' and self.expiry_date:
            # Auto-clear expiry date for unsafe blood
            self.expiry_date = None
        
        # Validate that barcode is provided
        if not self.barcode:
            raise ValidationError("Barcode is required. Must come from pre-generated blood bag.")
        
        # Validate safety status
        if self.safety_status == 'unsafe' and not self.unsafe_reason:
            raise ValidationError("Unsafe reason is required when marking blood as unsafe.")
        
        # Auto-quarantine unsafe blood
        if self.safety_status == 'unsafe':
            self.is_quarantined = True
            self.unit = 0  # Zero out units for unsafe blood

    @property
    def is_available_for_use(self):
        """Check if stock unit is available for issuance"""
        if self.safety_status != 'safe':
            return False
        if self.is_quarantined:
            return False
        if self.unit <= 0:
            return False
        if not self.expiry_date:
            return False
        return self.expiry_date >= timezone.now().date()
    
    @property
    def is_expired(self):
        """Check if blood is expired (for safe blood only)"""
        if not self.expiry_date or self.safety_status != 'safe':
            return False
        return self.expiry_date < timezone.now().date()
    
    @property
    def days_until_expiry(self):
        """Get days until expiry (for safe blood only)"""
        if not self.expiry_date or self.safety_status != 'safe':
            return None
        return (self.expiry_date - timezone.now().date()).days
    
    @property
    def expiry_status(self):
        """Get human-readable expiry status with icon"""
        if self.safety_status != 'safe':
            return "⏸️ Not applicable"
        if not self.expiry_date:
            return "❓ No expiry set"
        
        days = self.days_until_expiry
        if days < 0:
            return "⚠️ EXPIRED"
        elif days < 7:
            return f"🔴 Expiring soon ({days} days)"
        elif days < 14:
            return f"🟡 {days} days remaining"
        else:
            return f"🟢 {days} days remaining"
    
    @property
    def safety_status_display(self):
        """Human-readable safety status with icon"""
        status_icons = {
            'pending': '⏳',
            'safe': '✅',
            'unsafe': '⚠️',
        }
        return f"{status_icons.get(self.safety_status, '')} {self.get_safety_status_display()}"
    
    @property
    def summary(self):
        """Quick summary for display"""
        parts = [
            f"{self.bloodgroup}",
            f"{self.unit}ml",
            f"{self.get_component_type_display()}",
            self.safety_status_display,
        ]
        if self.safety_status == 'safe' and self.expiry_date:
            parts.append(self.expiry_status)
        return " | ".join(parts)

    def mark_safe(self, verified_by_user, role='lab_tech', notes=None):
        """Mark this stock unit as safe for use"""
        self.safety_status = 'safe'
        self.safety_verified_by = verified_by_user
        self.safety_verified_by_role = role
        self.safety_verified_at = timezone.now()
        if notes:
            self.safety_notes = notes
        self.is_quarantined = False
        self.save(update_fields=[
            'safety_status', 
            'safety_verified_by',
            'safety_verified_by_role',
            'safety_verified_at',
            'safety_notes',
            'is_quarantined'
        ])
        
        # Also update the blood bag barcode status
        if self.blood_bag_barcode:
            self.blood_bag_barcode.mark_tested_safe()
    
    def mark_unsafe(self, verified_by_user, role='lab_tech', reason=None, notes=None):
        """Mark this stock unit as unsafe and quarantine it"""
        self.safety_status = 'unsafe'
        self.safety_verified_by = verified_by_user
        self.safety_verified_by_role = role
        self.safety_verified_at = timezone.now()
        if reason:
            self.unsafe_reason = reason
        if notes:
            self.safety_notes = notes
        self.is_quarantined = True
        self.unit = 0  # Zero out the unit to prevent use
        self.expiry_date = None  # Clear expiry date for unsafe blood
        self.save(update_fields=[
            'safety_status',
            'safety_verified_by',
            'safety_verified_by_role',
            'safety_verified_at',
            'unsafe_reason',
            'safety_notes',
            'is_quarantined',
            'unit',
            'expiry_date'
        ])
        
        # Also update the blood bag barcode status
        if self.blood_bag_barcode:
            self.blood_bag_barcode.mark_discarded(reason)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        # Base string
        base = f"{self.bloodgroup} - {self.unit}ml at {self.center.name}"
        
        # Add component type
        component = self.get_component_type_display().split(' ')[0]  # Get just the type
        
        # Add safety status
        safety = self.safety_status_display
        
        # Add expiry info for safe blood
        if self.safety_status == 'safe' and self.expiry_date:
            expiry = f"Expires: {self.expiry_date} ({self.days_until_expiry} days)"
            return f"{base} [{component}] {safety} | {expiry}"
        elif self.safety_status == 'unsafe':
            reason = dict(self.unsafe_reason).get(self.unsafe_reason, 'Unsafe')
            return f"{base} [{component}] {safety} | Reason: {reason}"
        else:
            return f"{base} [{component}] {safety}"
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
# class Notification(models.Model):
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
    reason = models.TextField(blank=True, null=True)  # phlebotomist’s reason if reject/cancel
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
#     blood_request = models.ForeignKey('patient.BloodRequest', on_delete=models.CASCADE, null=True, blank=True)
    # ⭐ FIXED: Added 'donor.' prefix for cross-app reference
# #     donor_blood_request = models.ForeignKey('donor.DonorBloodRequest', on_delete=models.CASCADE, null=True, blank=True)
    appointment = models.ForeignKey('phlebotomist.Appointment', on_delete=models.CASCADE, null=True, blank=True)
    
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
        return None
    
class BloodDriveEvent(models.Model):
    """Blood drive locations and events"""
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='blood_drives/', 
                             validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    location = models.CharField(max_length=300)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    event_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    display_order = models.IntegerField(default=0, help_text="Lower numbers appear first")

    class Meta:
        ordering = ['display_order', '-event_date']
        verbose_name = "Blood Drive Event"
        verbose_name_plural = "Blood Drive Events"

    def __str__(self):
        return f"{self.title} - {self.location}"

    @property
    def is_upcoming(self):
        return self.event_date > timezone.now()


class Testimonial(models.Model):
    """User testimonials and success stories"""
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, help_text="e.g., 'Blood Donor', 'Patient', 'Phlebotomist'")
    avatar = models.ImageField(upload_to='testimonials/', blank=True, null=True)
    testimonial = models.TextField(max_length=800)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    is_featured = models.BooleanField(default=False, help_text="Show on homepage")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    display_order = models.IntegerField(default=0)
    source_review = models.OneToOneField(
        'UserReview',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='featured_testimonial'
    )

    class Meta:
        ordering = ['display_order', '-created_at']
        verbose_name = "Testimonial"
        verbose_name_plural = "Testimonials"

    def __str__(self):
        return f"{self.name} - {self.role}"
    
    def save(self, *args, **kwargs):
        # If this testimonial is from a review and has no avatar, try to get it from user profile
        if self.source_review and not self.avatar:
            user = self.source_review.user
            
            # Check donor profile
            if hasattr(user, 'donor') and user.donor.profile_pic:
                self.avatar = user.donor.profile_pic
            # Check phlebotomist profile
            elif hasattr(user, 'phlebotomist') and user.phlebotomist.profile_pic:
                self.avatar = user.phlebotomist.profile_pic
            # Check hospital user profile
            elif hasattr(user, 'hospitaluser') and user.hospitaluser.profile_pic:
                self.avatar = user.hospitaluser.profile_pic
        
        super().save(*args, **kwargs)
class UserReview(models.Model):
    """All user reviews/feedback - admin sees ALL of these"""
    user = models.OneToOneField(  
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='review'  
    )
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5 stars
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)  # So admin knows which are new
    
    class Meta:
        ordering = ['-created_at']
        # Add this to ensure only one review per user
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                name='unique_user_review'
            )
        ]
    
    def __str__(self):
        return f"Review by {self.user.username} - {self.rating}★"
class ReviewSurvey(models.Model):
    """Optional survey data linked to user reviews"""
    SATISFACTION_CHOICES = [
        (5, 'Very Satisfied'),
        (4, 'Satisfied'),
        (3, 'Neutral'),
        (2, 'Unsatisfied'),
        (1, 'Very Unsatisfied'),
    ]
    
    RECOMMEND_CHOICES = [
        (1, 'Yes, definitely!'),
        (0, 'Maybe'),
        (-1, 'Not yet'),
    ]
    
    review = models.OneToOneField(
        'UserReview',
        on_delete=models.CASCADE,
        related_name='survey'
    )
    satisfaction = models.IntegerField(choices=SATISFACTION_CHOICES, null=True, blank=True)
    favorite_features = models.JSONField(default=list, blank=True)  
    recommend = models.IntegerField(choices=RECOMMEND_CHOICES, null=True, blank=True)
    improvement = models.TextField(blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Review Survey"
        verbose_name_plural = "Review Surveys"
    
    def __str__(self):
        return f"Survey for {self.review.user.username}"

class HomePageStats(models.Model):
    """Dynamic stats for homepage"""
    stat_name = models.CharField(max_length=100, help_text="e.g., 'Active Donors'")
    stat_value = models.IntegerField()
    icon_class = models.CharField(max_length=100, default="fas fa-users", 
                                  help_text="Font Awesome class (e.g., 'fas fa-users')")
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order']
        verbose_name = "Homepage Stat"
        verbose_name_plural = "Homepage Stats"

    def __str__(self):
        return self.stat_name
    


class BloodBagBarcode(models.Model):
    """Pre-generated barcodes for blood collection bags"""
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('assigned', 'Assigned to Donor'),
        ('collected', 'Blood Collected'),
        ('tested', 'Tested - Safe'),
        ('discarded', 'Discarded - Unsafe'),
    ]
    
    BAG_TYPE_CHOICES = [
        ('single', 'Single Blood Bag'),
        ('double', 'Double Blood Bag'),
        ('triple', 'Triple Blood Bag'),
        ('pediatric', 'Pediatric Blood Bag'),
    ]
    
    ANTICOAGULANT_CHOICES = [
        ('cpd', 'CPD (Citrate Phosphate Dextrose)'),
        ('cpda1', 'CPDA-1'),
        ('sagm', 'SAG-Mannitol'),
    ]
    
    barcode = models.CharField(max_length=50, unique=True, db_index=True)
    bag_type = models.CharField(
        max_length=20,
        choices=BAG_TYPE_CHOICES,
        default='single'
    )
    volume_ml = models.IntegerField(default=450, help_text="Standard volume in ml")
    anticoagulant = models.CharField(
        max_length=50,
        choices=ANTICOAGULANT_CHOICES,
        default='cpd'
    )
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Assignment tracking
    assigned_to_donor = models.ForeignKey(
        'donor.Donor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_barcodes'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_barcodes'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    # Collection tracking
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_barcodes'
    )
    collected_at = models.DateTimeField(null=True, blank=True)
    
    # Link to blood donation once collected
    blood_donation = models.OneToOneField(
        'donor.BloodDonate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blood_bag_barcode'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_barcodes'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['status']),
            models.Index(fields=['assigned_to_donor']),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-generate barcode if not provided"""
        if not self.barcode or self.barcode.strip() == '':
            self.barcode = self.generate_barcode()
        super().save(*args, **kwargs)
    
    def generate_barcode(self):
        """Generate a unique barcode"""
        import random
        from datetime import datetime
        
        # Format: BLD-YYYYMMDD-XXXXX
        date_part = datetime.now().strftime('%Y%m%d')
        
        # Try up to 10 times to generate a unique barcode
        for _ in range(10):
            random_part = ''.join([str(random.randint(0, 9)) for _ in range(5)])
            barcode = f"BLD-{date_part}-{random_part}"
            
            # Check if barcode already exists
            if not BloodBagBarcode.objects.filter(barcode=barcode).exists():
                return barcode
        
        # If all attempts fail, add a timestamp to ensure uniqueness
        import time
        timestamp = int(time.time())[-6:]
        return f"BLD-{date_part}-{timestamp}"
    
    def __str__(self):
        status_icon = {
            'available': '📦',
            'assigned': '📝',
            'collected': '🩸',
            'tested': '✅',
            'discarded': '🗑️',
        }.get(self.status, '📋')
        
        return f"{status_icon} {self.barcode} - {self.get_status_display()}"

    def assign_to_donor(self, donor, user):
        """Assign this barcode to a donor"""
        if self.status != 'available':
            raise ValidationError(f"Cannot assign barcode with status '{self.status}'. Only available barcodes can be assigned.")
        
        self.status = 'assigned'
        self.assigned_to_donor = donor
        self.assigned_by = user
        self.assigned_at = timezone.now()
        self.save()
        
        logger.info(f"Barcode {self.barcode} assigned to donor {donor.id} by {user.username}")
    
    def mark_collected(self, user, blood_donation):
        """Mark this barcode as collected"""
        if self.status != 'assigned':
            raise ValidationError(f"Cannot mark barcode with status '{self.status}' as collected. Only assigned barcodes can be collected.")
        
        self.status = 'collected'
        self.collected_by = user
        self.collected_at = timezone.now()
        self.blood_donation = blood_donation
        self.save()
        
        logger.info(f"Barcode {self.barcode} collected by {user.username} for donation {blood_donation.id}")
    
    def mark_tested_safe(self):
        """Mark as tested and safe"""
        if self.status != 'collected':
            raise ValidationError(f"Cannot mark barcode with status '{self.status}' as tested. Only collected barcodes can be tested.")
        
        self.status = 'tested'
        self.save()
        
        logger.info(f"Barcode {self.barcode} marked as tested (SAFE)")
    
    def mark_discarded(self, reason=None):
        """Mark as discarded (unsafe blood)"""
        self.status = 'discarded'
        self.save()
        
        logger.info(f"Barcode {self.barcode} discarded. Reason: {reason or 'Unsafe blood'}")
    
    @property
    def is_available(self):
        """Check if barcode is available for assignment"""
        return self.status == 'available'
    
    @property
    def is_in_use(self):
        """Check if barcode is in use (assigned or collected)"""
        return self.status in ['assigned', 'collected']
    
    @property
    def lifecycle_stage(self):
        """Get human-readable lifecycle stage"""
        stages = {
            'available': '📦 Ready for use',
            'assigned': '📝 Assigned to donor',
            'collected': '🩸 Blood collected - awaiting testing',
            'tested': '✅ Tested and safe - in inventory',
            'discarded': '🗑️ Discarded - not usable',
        }
        return stages.get(self.status, self.status)