from django.db import models
from donor.models import Donor
from donor.models import BloodDonate
from blood.models import DonationCenter  # Add this import

class BloodTest(models.Model):
    """Blood testing model for lab technologist"""
    
    RESULT_CHOICES = (
        ('pending', 'Pending'),
        ('safe', 'Safe'),
        ('unsafe', 'Unsafe'),
    )
    
    # Link to the blood collected by nurse
    blood_collection = models.OneToOneField(
        BloodDonate, 
        on_delete=models.CASCADE,
        related_name='lab_test',
        limit_choices_to={'status': 'collected'}  # Only collected blood can be tested
    )
    
    # Test results
    blood_group = models.CharField(max_length=5, blank=True, choices=[
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ])
    
    # Infectious disease markers
    hiv = models.BooleanField(null=True, blank=True, verbose_name="HIV")
    hepatitis_b = models.BooleanField(null=True, blank=True, verbose_name="Hepatitis B")
    hepatitis_c = models.BooleanField(null=True, blank=True, verbose_name="Hepatitis C")
    syphilis = models.BooleanField(null=True, blank=True, verbose_name="Syphilis")
    malaria = models.BooleanField(null=True, blank=True, verbose_name="Malaria")
    
    # Test metadata
    tested_by = models.ForeignKey(
        'lab_technologist.LabTechnologistProfile',
        on_delete=models.SET_NULL,
        null=True,
        related_name='tests_performed'
    )
    test_date = models.DateTimeField(auto_now_add=True)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    
    def mark_safe(self):
        """Mark blood as safe - automatically determines based on test results"""
        if self.hiv is False and self.hepatitis_b is False and \
           self.hepatitis_c is False and self.syphilis is False and \
           self.malaria is False:
            self.result = 'safe'
            # Update the blood collection status
            self.blood_collection.status = 'tested_safe'
            self.blood_collection.save()
        else:
            self.result = 'unsafe'
            self.blood_collection.status = 'tested_unsafe'
            self.blood_collection.save()
        self.save()
    
    def __str__(self):
        return f"Test for {self.blood_collection.barcode} - {self.result}"

class LabTechnologistProfile(models.Model):
    """Lab Technologist profile"""
    
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='lab_tech_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    profile_pic = models.ImageField(upload_to='labtech_profiles/', null=True, blank=True)
    center = models.ForeignKey(
        DonationCenter,
        on_delete=models.SET_NULL, 
        null=True,
        blank=True
    )
    phone = models.CharField(max_length=15)
    qualification = models.CharField(max_length=200, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    # ADD THESE MISSING FIELDS
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "Lab Technologist"
        verbose_name_plural = "Lab Technologists"
        ordering = ['-created_at']

    def __str__(self):
        return f"Lab Tech: {self.user.get_full_name()} - {self.employee_id}"

    def clean(self):
        """Validate that user doesn't already have another profile"""
        super().clean()
        
        if not self.user:
            return
            
        user = self.user
        
        # Check for existing profiles
        if hasattr(user, 'patient') and user.patient and (not self.pk or user.patient != getattr(self, 'patient_ptr', None)):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'user': f"User '{user.username}' already has a Patient profile. A user cannot have multiple profiles."
            })
        
        if hasattr(user, 'donor') and user.donor and (not self.pk or user.donor != getattr(self, 'donor_ptr', None)):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'user': f"User '{user.username}' already has a Donor profile. A user cannot have multiple profiles."
            })
        
        if hasattr(user, 'nurse') and user.nurse and (not self.pk or user.nurse != getattr(self, 'nurse_ptr', None)):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'user': f"User '{user.username}' already has a Nurse profile. A user cannot have multiple profiles."
            })
        
        if hasattr(user, 'blood_bank_tech_profile') and user.blood_bank_tech_profile and \
           (not self.pk or user.blood_bank_tech_profile != getattr(self, 'bloodbanktechprofile_ptr', None)):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'user': f"User '{user.username}' already has a Blood Bank Technician profile. A user cannot have multiple profiles."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def is_available(self):
        return self.is_active and self.center is not None