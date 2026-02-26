from django.db import models
from django.conf import settings
from patient.models import BloodRequest
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
    """Record of blood dispatched to patients"""
    
    # Using StockUnit directly
    stock_unit = models.ForeignKey(
        StockUnit,
        on_delete=models.CASCADE,
        related_name='dispatches',
        help_text="Stock unit that was dispatched"
    )
    
    # Either blood_request (patient) or donor_blood_request (donor)
    blood_request = models.ForeignKey(
        'patient.BloodRequest',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dispatches'
    )
    donor_blood_request = models.ForeignKey(
        'donor.DonorBloodRequest',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dispatches'
    )
    
    dispatched_by = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='dispatches_made'
    )
    dispatch_date = models.DateTimeField(auto_now_add=True)
    
    # Hospital staff who collected
    collected_by_name = models.CharField(max_length=200)
    collected_by_id = models.CharField(max_length=50)
    collection_time = models.DateTimeField()
    
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Blood Dispatch"
        verbose_name_plural = "Blood Dispatches"
        ordering = ['-dispatch_date']
    
    def __str__(self):
        donor_name = "Unknown"
        if self.stock_unit.blood_donation and self.stock_unit.blood_donation.donor:
            donor_name = self.stock_unit.blood_donation.donor.user.get_full_name()
        
        if self.blood_request:
            return f"Dispatch {self.id}: {self.stock_unit.bloodgroup} to patient #{self.blood_request.id}"
        elif self.donor_blood_request:
            return f"Dispatch {self.id}: {self.stock_unit.bloodgroup} to donor request #{self.donor_blood_request.id}"
        return f"Dispatch {self.id}: {self.stock_unit.bloodgroup}"