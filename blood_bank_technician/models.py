from django.db import models
from django.conf import settings
from blood.models import DonationCenter, StockUnit

class BloodBankTechProfile(models.Model):
    """Blood Bank Technician profile"""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blood_bank_tech_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    profile_pic = models.ImageField(upload_to='bloodbank_profiles/', null=True, blank=True)
    center = models.ForeignKey(
        DonationCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blood_bank_technicians'
    )
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Blood Bank Tech: {self.user.get_full_name()} - {self.employee_id}"

class BloodDispatch(models.Model):
    """Record of blood dispatched to hospitals"""
    
    stock_unit = models.ForeignKey(
        StockUnit,
        on_delete=models.CASCADE,
        related_name='dispatches',
        help_text="Stock unit that was dispatched"
    )
    
    # Use string references instead of direct imports
    hospital_request = models.ForeignKey(
        'hospital.HospitalBloodRequest',  # String reference
        on_delete=models.CASCADE,
        related_name='dispatches',
        help_text="Hospital blood request this dispatch fulfills"
    )
    
    dispatched_by = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='dispatches_made'
    )
    dispatch_date = models.DateTimeField(auto_now_add=True)
    
    collected_by_name = models.CharField(
        max_length=200,
        help_text="Name of hospital staff who collected"
    )
    collected_by_id = models.CharField(
        max_length=50,
        help_text="ID number of hospital staff"
    )
    collected_by_phone = models.CharField(
        max_length=15,
        blank=True,
        help_text="Contact phone of hospital staff"
    )
    collection_time = models.DateTimeField(
        help_text="When the blood was picked up"
    )
    
    # Use string reference for Hospital
    hospital = models.ForeignKey(
        'hospital.Hospital',  # String reference
        on_delete=models.CASCADE,
        related_name='received_dispatches',
        help_text="Hospital receiving the blood"
    )
    hospital_authorization = models.CharField(
        max_length=100,
        blank=True,
        help_text="Authorization number/reference from hospital"
    )
    
    STATUS_CHOICES = [
        ('pending', 'Pending Pickup'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered to Hospital'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    notes = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_to = models.CharField(max_length=200, blank=True)
    delivery_notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Blood Dispatch"
        verbose_name_plural = "Blood Dispatches"
        ordering = ['-dispatch_date']
    
    def __str__(self):
        # Use a safe string representation that doesn't require loading related objects
        return f"Dispatch {self.id}: {self.stock_unit.bloodgroup} to {self.hospital_id}"

class InventoryAlert(models.Model):
    """Alerts for low inventory or expiring blood"""
    
    center = models.ForeignKey(
        DonationCenter,
        on_delete=models.CASCADE,
        related_name='inventory_alerts'
    )
    
    ALERT_TYPE_CHOICES = [
        ('low_stock', 'Low Stock'),
        ('expiring', 'Expiring Soon'),
        ('out_of_stock', 'Out of Stock'),
    ]
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    blood_group = models.CharField(
        max_length=5,
        choices=StockUnit.BLOOD_GROUP_CHOICES,
        blank=True,
        null=True
    )
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.center.name}"

class HospitalCommunication(models.Model):
    """Track communication with hospitals"""
    
    # Use string reference for Hospital
    hospital = models.ForeignKey(
        'hospital.Hospital',  # String reference
        on_delete=models.CASCADE,
        related_name='communications'
    )
    blood_bank_tech = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='hospital_communications'
    )
    
    COMMUNICATION_TYPE_CHOICES = [
        ('request_received', 'Request Received'),
        ('request_approved', 'Request Approved'),
        ('request_rejected', 'Request Rejected'),
        ('ready_for_pickup', 'Ready for Pickup'),
        ('dispatched', 'Dispatched'),
        ('follow_up', 'Follow Up'),
        ('general', 'General')
    ]
    
    comm_type = models.CharField(max_length=20, choices=COMMUNICATION_TYPE_CHOICES)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    
    # Use string reference for BloodRequest
    related_request = models.ForeignKey(
        'hospital.HospitalBloodRequest',  # String reference
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='communications'
    )
    
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.get_comm_type_display()} - {self.hospital_id} - {self.sent_at}"
