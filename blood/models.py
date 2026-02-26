from django.db import models
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid
from django.contrib.auth.models import User
from nurse.models import Appointment
from django.core.validators import FileExtensionValidator
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
    BLOOD_GROUP_CHOICES = Stock.BLOOD_GROUP_CHOICES
    
    SAFETY_STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('safe', 'Safe for Use'),
        ('unsafe', 'Unsafe - Do Not Use'),
    ]

    # Who added this to stock
    ADDED_BY_ROLE_CHOICES = [
        ('nurse', 'Nurse'),
        ('lab_tech', 'Lab Technologist'),
        ('system', 'System'),
    ]

    bloodgroup = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    unit = models.PositiveIntegerField(default=0)
    center = models.ForeignKey('blood.DonationCenter', on_delete=models.CASCADE)
    expiry_date = models.DateField()
    
    # ===== BARCODE - MUST come from pre-generated blood bag =====
    barcode = models.CharField(
        max_length=100, 
        unique=True, 
        blank=False,  # Changed to False - barcode is required
        null=False,   # Changed to False - barcode is required
        help_text='Barcode from pre-generated blood bag'
    )
    
    added_on = models.DateTimeField(auto_now_add=True)
    
    # ===== NEW: Link to the pre-generated blood bag barcode =====
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
            ('contamination', 'Contamination Detected'),
            ('disease_markers', 'Disease Markers Present'),
            ('quality_issues', 'Quality Issues'),
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
        default='nurse',
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

    def clean(self):
        # Allow zero units, disallow negative
        if self.unit < 0:
            raise ValidationError("Unit must be zero or a positive integer.")
        if self.expiry_date < timezone.now().date():
            raise ValidationError("Expiry date cannot be in the past.")
        
        # Validate that barcode is provided
        if not self.barcode:
            raise ValidationError("Barcode is required. Must come from pre-generated blood bag.")
        
        # Validate safety status
        if self.safety_status == 'unsafe' and not self.unsafe_reason:
            raise ValidationError("Unsafe reason is required when marking blood as unsafe.")
        
        # Auto-quarantine unsafe blood
        if self.safety_status == 'unsafe':
            self.is_quarantined = True

    @property
    def is_available_for_use(self):
        """Check if stock unit is available for issuance"""
        return (
            self.safety_status == 'safe' and
            not self.is_quarantined and
            self.unit > 0 and
            self.expiry_date >= timezone.now().date()
        )
    
    @property
    def safety_status_display(self):
        """Human-readable safety status with icon"""
        status_icons = {
            'pending': '⏳',
            'safe': '✅',
            'unsafe': '⚠️',
        }
        return f"{status_icons.get(self.safety_status, '')} {self.get_safety_status_display()}"

    def mark_safe(self, verified_by_user, role='nurse', notes=None):
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
            self.blood_bag_barcode.mark_tested()
    
    def mark_unsafe(self, verified_by_user, role='nurse', reason=None, notes=None):
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
        self.save(update_fields=[
            'safety_status',
            'safety_verified_by',
            'safety_verified_by_role',
            'safety_verified_at',
            'unsafe_reason',
            'safety_notes',
            'is_quarantined',
            'unit'
        ])
        
        # Also update the blood bag barcode status
        if self.blood_bag_barcode:
            self.blood_bag_barcode.discard()

    def save(self, *args, **kwargs):
        self.clean()
        # Removed barcode generation - barcode must come from blood bag
        super().save(*args, **kwargs)

    def __str__(self):
        safety = f"[{self.get_safety_status_display()}]"
        bag_info = f" (Bag: {self.blood_bag_barcode.barcode})" if self.blood_bag_barcode else ""
        return f"{self.bloodgroup} - {self.unit}ml at {self.center.name} {safety}{bag_info} (Expires: {self.expiry_date})"
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
    blood_request = models.ForeignKey('patient.BloodRequest', on_delete=models.CASCADE, null=True, blank=True)
    # ⭐ FIXED: Added 'donor.' prefix for cross-app reference
    donor_blood_request = models.ForeignKey('donor.DonorBloodRequest', on_delete=models.CASCADE, null=True, blank=True)
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


class Banner(models.Model):
    """Moving/rotating banners for announcements"""
    BANNER_TYPES = [
        ('info', 'Information'),
        ('urgent', 'Urgent'),
        ('success', 'Success Story'),
        ('event', 'Event'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField(max_length=500)
    banner_type = models.CharField(max_length=20, choices=BANNER_TYPES, default='info')
    link_text = models.CharField(max_length=50, blank=True, help_text="Button text (optional)")
    link_url = models.URLField(blank=True, help_text="Button link (optional)")
    background_image = models.ImageField(upload_to='banners/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry")
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', '-created_at']
        verbose_name = "Banner"
        verbose_name_plural = "Banners"

    def __str__(self):
        return self.title

    @property
    def is_current(self):
        now = timezone.now()
        if self.end_date:
            return self.start_date <= now <= self.end_date
        return self.start_date <= now


class Testimonial(models.Model):
    """User testimonials and success stories"""
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, help_text="e.g., 'Blood Donor', 'Patient', 'Nurse'")
    avatar = models.ImageField(upload_to='testimonials/', blank=True, null=True)
    testimonial = models.TextField(max_length=800)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    is_featured = models.BooleanField(default=False, help_text="Show on homepage")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', '-created_at']
        verbose_name = "Testimonial"
        verbose_name_plural = "Testimonials"

    def __str__(self):
        return f"{self.name} - {self.role}"


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
    

class DonationFunFact(models.Model):
    """Interactive fun facts that users can explore"""
    FACT_CATEGORIES = [
        ('blood', 'Blood Science & Biology'),  # Updated label
        ('donation', 'Donation Process & Impact'),  # Updated label
        ('health', 'Health Benefits'),
        ('myths', 'Myth Busters'),
        ('fun', 'Fun Facts & History'),  # Added - used in fact_data.py
        ('local', 'Kenyan Context'),  # Added - used in fact_data.py
    ]
    
    category = models.CharField(max_length=20, choices=FACT_CATEGORIES)
    title = models.CharField(max_length=200)
    fact_text = models.TextField()
    image_url = models.CharField(max_length=500, blank=True, null=True, 
                                help_text="URL to an image (can be Unsplash, Pexels, etc.)")
    is_verified = models.BooleanField(default=True)
    
    # Interactive elements
    has_quiz = models.BooleanField(default=False)
    quiz_question = models.TextField(blank=True, null=True)
    correct_answer = models.CharField(max_length=200, blank=True, null=True)
    wrong_answer_1 = models.CharField(max_length=200, blank=True, null=True)
    wrong_answer_2 = models.CharField(max_length=200, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    
    # Engagement metrics
    likes = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    times_viewed = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Added - good practice
    
    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Donation Fun Fact"
        verbose_name_plural = "Donation Fun Facts"
class UserFactInteraction(models.Model):
    """Track how users interact with facts"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    fact = models.ForeignKey(DonationFunFact, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    
    INTERACTION_TYPES = [
        ('view', 'Viewed'),
        ('like', 'Liked'),
        ('share', 'Shared'),
        ('quiz_attempt', 'Quiz Attempted'),
        ('quiz_correct', 'Quiz Correct'),
        ('quiz_wrong', 'Quiz Wrong'),
    ]
    
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    user_answer = models.CharField(max_length=500, blank=True, null=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "User Fact Interaction"
        verbose_name_plural = "User Fact Interactions"
    
    def __str__(self):
        user_display = self.user.username if self.user else f"Anonymous ({self.session_id[:8]}...)"
        return f"{user_display} - {self.get_interaction_type_display()} - {self.fact.title}"

class DailyFactChallenge(models.Model):
    """Daily challenge for users"""
    date = models.DateField(unique=True)
    fact = models.ForeignKey(DonationFunFact, on_delete=models.CASCADE)
    total_participants = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-date']
        verbose_name = "Daily Fact Challenge"
        verbose_name_plural = "Daily Fact Challenges"
    
    def __str__(self):
        return f"Challenge: {self.date} - {self.fact.title}"
    
    @property
    def accuracy_percentage(self):
        if self.total_participants > 0:
            return round((self.correct_answers / self.total_participants) * 100, 1)
        return 0

class QuizAttempt(models.Model):
    """Track quiz attempts and scores - MISSING FROM YOUR MODELS"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_questions = models.IntegerField()
    correct_answers = models.IntegerField()
    score = models.DecimalField(max_digits=5, decimal_places=2)  # Percentage
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.score}% ({self.created_at})"
    
    class Meta:
        ordering = ['-created_at']


class FactContribution(models.Model):
    """Allow users to suggest new facts - MISSING FROM YOUR MODELS"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=DonationFunFact.FACT_CATEGORIES)
    title = models.CharField(max_length=200)
    fact_text = models.TextField()
    source = models.URLField(blank=True, null=True, help_text="Source URL for verification")
    
    # Optional quiz elements
    has_quiz = models.BooleanField(default=False)
    quiz_question = models.TextField(blank=True, null=True)
    correct_answer = models.CharField(max_length=200, blank=True, null=True)
    wrong_answer_1 = models.CharField(max_length=200, blank=True, null=True)
    wrong_answer_2 = models.CharField(max_length=200, blank=True, null=True)
    
    # Moderation
    is_approved = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, 
                                    null=True, blank=True, related_name='reviewed_facts')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Contribution by {self.user.username}: {self.title}"
    
    class Meta:
        ordering = ['-created_at']
# blood/models.py - Add this new model

class BloodBagBarcode(models.Model):
    """Pre-generated barcodes for blood collection bags"""
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('assigned', 'Assigned to Donor'),
        ('collected', 'Blood Collected'),
        ('tested', 'Tested'),
        ('discarded', 'Discarded'),
    ]
    
    barcode = models.CharField(max_length=50, unique=True, db_index=True)
    bag_type = models.CharField(
        max_length=20,
        choices=[
            ('single', 'Single Blood Bag'),
            ('double', 'Double Blood Bag'),
            ('triple', 'Triple Blood Bag'),
            ('pediatric', 'Pediatric Blood Bag'),
        ],
        default='single'
    )
    volume_ml = models.IntegerField(default=450, help_text="Standard volume in ml")
    anticoagulant = models.CharField(
        max_length=50,
        choices=[
            ('cpd', 'CPD (Citrate Phosphate Dextrose)'),
            ('cpda1', 'CPDA-1'),
            ('sagm', 'SAG-Mannitol'),
        ],
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
    
    # Manufacturing details
    manufacturer = models.CharField(max_length=100, blank=True)
    lot_number = models.CharField(max_length=50, blank=True)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
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
    
    def __str__(self):
        return f"{self.barcode} - {self.get_status_display()}"

    def assign_to_donor(self, donor, user):
        """Assign this barcode to a donor"""
        self.status = 'assigned'
        self.assigned_to_donor = donor
        self.assigned_by = user
        self.assigned_at = timezone.now()
        self.save()
    
    def mark_collected(self, user, blood_donation):
        """Mark this barcode as collected"""
        self.status = 'collected'
        self.collected_by = user
        self.collected_at = timezone.now()
        self.blood_donation = blood_donation
        self.save()
    
    def mark_tested(self):
        """Mark as tested (safe or unsafe)"""
        self.status = 'tested'
        self.save()
    
    def discard(self):
        """Mark as discarded"""
        self.status = 'discarded'
        self.save()