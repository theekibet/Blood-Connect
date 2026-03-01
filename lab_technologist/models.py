from datetime import date
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
    
    def __str__(self):
        return f"Test for {self.blood_collection.barcode} - {self.result}"
class LabTechnologistProfile(models.Model):
    """Lab Technologist profile"""
    
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='lab_tech_profile'  # This will be 'lab_tech_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    profile_pic = models.ImageField(upload_to='labtech_profiles/', null=True, blank=True)
    center = models.ForeignKey(
        'blood.DonationCenter',
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='lab_technologists'  # Added related_name for reverse query
    )
    phone = models.CharField(max_length=15)
    qualification = models.CharField(max_length=200, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    # ADD THESE MISSING FIELDS
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Optional fields for specialization
    specialization = models.CharField(max_length=100, blank=True, 
                                      help_text="E.g., Hematology, Microbiology, Immunology")
    years_of_experience = models.PositiveIntegerField(default=0)
    
    # Certification tracking
    certification_date = models.DateField(null=True, blank=True)
    certification_expiry = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Lab Technologist"
        verbose_name_plural = "Lab Technologists"
        ordering = ['-created_at']
        # Add database constraints
        constraints = [
            # Ensure user is unique (already OneToOne, but adds explicit constraint)
            models.UniqueConstraint(
                fields=['user'],
                name='unique_labtech_user'
            ),
            # Ensure employee_id is unique (already set, but explicit)
            models.UniqueConstraint(
                fields=['employee_id'],
                name='unique_labtech_employee_id'
            ),
            # Ensure license_number is unique when provided
            models.UniqueConstraint(
                fields=['license_number'],
                name='unique_labtech_license',
                condition=models.Q(license_number__isnull=False) & ~models.Q(license_number='')
            ),
        ]
        # Add indexes for frequently queried fields
        indexes = [
            models.Index(fields=['center', 'is_active']),
            models.Index(fields=['specialization']),
            models.Index(fields=['certification_expiry']),
        ]

    def __str__(self):
        return f"Lab Tech: {self.user.get_full_name()} - {self.employee_id}"

    def clean(self):
        """
        Validate that user doesn't have other profiles
        Called automatically by ModelForm in admin
        """
        from django.core.exceptions import ValidationError
        from datetime import date
        
        # IMPORTANT FIX: Skip validation during signup (when no user exists yet)
        if not hasattr(self, 'user') or not self.user_id:
            return
        
        # Call parent clean
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
        
        # Example: Basic alphanumeric validation (adjust based on your country's format)
        if not re.match(r'^[A-Z0-9-]+$', self.license_number.upper()):
            raise ValidationError({
                'license_number': "License number should contain only uppercase letters, numbers, and hyphens"
            })

    def save(self, *args, **kwargs):
        """
        Override save to ensure validation runs
        """
        # IMPORTANT FIX: Only run full_clean if this is an existing profile
        if self.pk:
            self.full_clean()
        
        # Auto-calculate years of experience if certification date is set
        if self.certification_date and not self.years_of_experience:
            from datetime import date
            self.years_of_experience = (date.today().year - self.certification_date.year)
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Handle cleanup when profile is deleted
        """
        # Add any cleanup logic here if needed
        # For example, reassign pending tests to another tech
        super().delete(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def is_available(self):
        """Check if technologist is available for work"""
        return self.is_active and self.center is not None and self.certification_valid

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
        # Assuming you have a BloodTest model in the same app
        if hasattr(self, 'bloodtest_set'):
            return self.bloodtest_set.filter(status='pending').count()
        return 0

    def get_completed_tests_today(self):
        """Get count of tests completed today"""
        if hasattr(self, 'bloodtest_set'):
            from datetime import date
            return self.bloodtest_set.filter(
                status='completed',
                completed_at__date=date.today()
            ).count()
        return 0

    def can_perform_test(self, test_type):
        """Check if technologist can perform specific test type"""
        # This could be expanded based on specialization
        if not self.is_available:
            return False
        
        # If specialization is set, check if test_type matches
        if self.specialization and test_type:
            # Simple matching - can be made more sophisticated
            return test_type.lower() in self.specialization.lower()
        
        return True

    @classmethod
    def get_available_at_center(cls, center_id):
        """Get all available technologists at a specific center"""
        from datetime import date
        return cls.objects.filter(
            center_id=center_id,
            is_active=True,
            certification_expiry__gte=date.today()
        )

    @classmethod
    def get_expiring_certifications(cls, days=30):
        """Get technologists whose certifications expire within specified days"""
        from datetime import date, timedelta
        expiry_threshold = date.today() + timedelta(days=days)
        return cls.objects.filter(
            certification_expiry__lte=expiry_threshold,
            certification_expiry__gte=date.today(),
            is_active=True
        )
