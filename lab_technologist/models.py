# lab_technologist/models.py

from datetime import date
from django.db import models
from donor.models import Donor
from donor.models import BloodDonate
from blood.models import DonationCenter  

class BloodTest(models.Model):
    """Blood testing model for lab technologist"""
    
    RESULT_CHOICES = (
        ('pending', 'Pending'),
        ('safe', 'Safe'),
        ('unsafe', 'Unsafe'),
    )
    
    # Link to the blood collected by phlebotomist
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
    
    def get_barcode(self):
        """
        Helper method to get barcode from related objects
        Used by admin and templates
        """
        if not self.blood_collection:
            return None
            
        # Try to get from blood bag barcode
        try:
            from blood.models import BloodBagBarcode
            blood_bag = BloodBagBarcode.objects.filter(
                blood_donation=self.blood_collection
            ).first()
            if blood_bag:
                return blood_bag.barcode
        except (ImportError, Exception):
            pass
            
        # Try to get from stock unit
        try:
            from blood.models import StockUnit
            stock_unit = StockUnit.objects.filter(
                blood_donation=self.blood_collection
            ).first()
            if stock_unit:
                return stock_unit.barcode
        except (ImportError, Exception):
            pass
            
        # Fallback - return donation ID as string
        return f"DON-{self.blood_collection.id}"
    
    def __str__(self):
        """Safe string representation - handles missing barcode gracefully"""
        if self.blood_collection:
            barcode = self.get_barcode()
            if barcode:
                return f"Test for {barcode} - {self.result}"
            return f"Test for Donation #{self.blood_collection.id} - {self.result}"
        return f"Test #{self.id} - {self.result}"
    
    class Meta:
        verbose_name = "Blood Test"
        verbose_name_plural = "Blood Tests"
        ordering = ['-test_date']
        indexes = [
            models.Index(fields=['result']),
            models.Index(fields=['test_date']),
        ]


class LabTechnologistProfile(models.Model):
    """Lab Technologist profile with admin approval"""
    
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='lab_tech_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    profile_pic = models.ImageField(upload_to='labtech_profiles/', null=True, blank=True)
    center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='lab_technologists'
    )
    phone = models.CharField(max_length=15)
    qualification = models.CharField(max_length=200, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    # ===== ADMIN APPROVAL FIELDS =====
    is_approved = models.BooleanField(
        default=False,
        help_text="Whether admin has approved this lab technologist"
    )
    approved_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When admin approved this technologist"
    )
    approved_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_lab_techs',
        help_text="Admin who approved this technologist"
    )
    # ===== END APPROVAL FIELDS =====
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    specialization = models.CharField(max_length=100, blank=True, 
                                      help_text="E.g., Hematology, Microbiology, Immunology")
    years_of_experience = models.PositiveIntegerField(default=0)
    
    certification_date = models.DateField(null=True, blank=True)
    certification_expiry = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Lab Technologist"
        verbose_name_plural = "Lab Technologists"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                name='unique_labtech_user'
            ),
            models.UniqueConstraint(
                fields=['employee_id'],
                name='unique_labtech_employee_id'
            ),
            models.UniqueConstraint(
                fields=['license_number'],
                name='unique_labtech_license',
                condition=models.Q(license_number__isnull=False) & ~models.Q(license_number='')
            ),
        ]
        indexes = [
            models.Index(fields=['center', 'is_active']),
            models.Index(fields=['specialization']),
            models.Index(fields=['certification_expiry']),
            models.Index(fields=['is_approved']),  # ADDED for faster approval queries
        ]

    def __str__(self):
        status = "✅ Approved" if self.is_approved else "⏳ Pending"
        return f"Lab Tech: {self.user.get_full_name()} - {self.employee_id} ({status})"

    def clean(self):
        """
        Validate that user doesn't have other profiles
        Called automatically by ModelForm in admin
        """
        from django.core.exceptions import ValidationError
        from datetime import date
        
        # Skip validation during signup (when no user exists yet)
        if not hasattr(self, 'user') or not self.user_id:
            return
        
        super().clean()
        
        # Skip profile validation during signup
        if not self.pk:
            # This is a new profile - skip validation that requires existing user
            pass
        else:
            # Existing profile - do full validation
            # Validate no duplicate profiles across system
            try:
                from blood.utils.validators import validate_single_profile
                validate_single_profile(
                    user=self.user,
                    current_profile_type='lab_tech_profile',
                    exclude_self=True
                )
            except ValidationError:
                raise ValidationError({
                    'user': f"This user already has a different profile. Each user can only have one role in the system."
                })
            except ImportError:
                # If validator not available, skip
                pass
        
        # Validate license format if provided
        if self.license_number:
            self._validate_license_format()
        
        # Validate certification dates
        if self.certification_date and self.certification_expiry:
            if self.certification_expiry < self.certification_date:
                raise ValidationError({
                    'certification_expiry': "Expiry date cannot be before certification date."
                })
        
        # Validate phone format (basic)
        if self.phone and not self.phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise ValidationError({
                'phone': "Phone number should contain only digits, spaces, +, or -"
            })
        
        # Validate experience
        if self.years_of_experience and self.years_of_experience > 50:
            raise ValidationError({
                'years_of_experience': "Years of experience seems unrealistic (max 50 years)"
            })

    def _validate_license_format(self):
        """Validate license number format"""
        from django.core.exceptions import ValidationError
        import re
        
        if not re.match(r'^[A-Z0-9-]+$', self.license_number.upper()):
            raise ValidationError({
                'license_number': "License number should contain only uppercase letters, numbers, and hyphens"
            })

    def save(self, *args, **kwargs):
        """
        Override save to ensure validation runs and handle approval timestamp
        """
        # Handle approval timestamp - if approved and no timestamp, set it now
        if self.is_approved and not self.approved_at:
            from django.utils import timezone
            self.approved_at = timezone.now()
        
        # Only run full_clean if this is an existing profile
        if self.pk:
            self.full_clean()
        
        # Auto-calculate years of experience if certification date is set
        if self.certification_date and not self.years_of_experience:
            from datetime import date
            self.years_of_experience = (date.today().year - self.certification_date.year)
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Handle cleanup when profile is deleted"""
        # Add any cleanup logic here if needed
        # For example, reassign pending tests to another tech
        super().delete(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def approval_status(self):
        """Get human-readable approval status"""
        if self.is_approved:
            return f"Approved on {self.approved_at.strftime('%b %d, %Y')}" if self.approved_at else "Approved"
        return "Pending Approval"

    @property
    def is_available(self):
        """Check if technologist is available for work"""
        return self.is_active and self.is_approved and self.center is not None and self.certification_valid

    @property
    def certification_valid(self):
        """Check if certification is still valid"""
        if not self.certification_expiry:
            return False
        from datetime import date
        return date.today() <= self.certification_expiry

    @property
    def days_until_certification_expiry(self):
        """Get days until certification expires"""
        if not self.certification_expiry:
            return None
        from datetime import date
        delta = (self.certification_expiry - date.today()).days
        return max(delta, 0)

    def get_tests_pending(self):
        """Get count of pending tests assigned to this technologist"""
        if hasattr(self, 'bloodtest_set'):
            return self.bloodtest_set.filter(result='pending').count()
        return 0

    def get_completed_tests_today(self):
        """Get count of tests completed today"""
        if hasattr(self, 'bloodtest_set'):
            from datetime import date
            return self.bloodtest_set.filter(
                test_date__date=date.today()
            ).exclude(result='pending').count()
        return 0

    def can_perform_test(self, test_type):
        """Check if technologist can perform specific test type"""
        if not self.is_available:
            return False
        
        if self.specialization and test_type:
            return test_type.lower() in self.specialization.lower()
        
        return True

    @classmethod
    def get_available_at_center(cls, center_id):
        """Get all available technologists at a specific center"""
        from datetime import date
        return cls.objects.filter(
            center_id=center_id,
            is_active=True,
            is_approved=True,
            certification_expiry__gte=date.today()
        )

    @classmethod
    def get_pending_approval(cls):
        """Get all lab technologists awaiting approval"""
        return cls.objects.filter(
            is_approved=False,
            is_active=True
        ).order_by('-created_at')

    @classmethod
    def get_expiring_certifications(cls, days=30):
        """Get technologists whose certifications expire within specified days"""
        from datetime import date, timedelta
        expiry_threshold = date.today() + timedelta(days=days)
        return cls.objects.filter(
            certification_expiry__lte=expiry_threshold,
            certification_expiry__gte=date.today(),
            is_active=True,
            is_approved=True
        )