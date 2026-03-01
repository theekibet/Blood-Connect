from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re
from blood.models import DonationCenter
from .models import Phlebotomist, Appointment


# -------------------------
# Login Form
# -------------------------
class PhlebotomistLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter username', 'class': 'form-control'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter password', 'class': 'form-control'})
    )


# -------------------------
# Signup Form
# -------------------------
class PhlebotomistSignupForm(forms.ModelForm):
    # -------------------------
    # User-related fields
    # -------------------------
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Username', 'class': 'form-control'}),
        max_length=150,
        min_length=4,
        help_text="4-150 characters. Letters, digits and @/./+/-/_ only."
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Email address', 'class': 'form-control'}),
        help_text="Enter a valid email address"
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'First Name', 'class': 'form-control'}),
        min_length=2,
        max_length=50,
        help_text="2-50 characters"
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Last Name', 'class': 'form-control'}),
        min_length=2,
        max_length=50,
        help_text="2-50 characters"
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}),
        label="Password",
        min_length=8,
        help_text="At least 8 characters with letters and numbers"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password', 'class': 'form-control'}),
        label="Confirm Password",
        help_text="Enter the same password again for verification"
    )

    terms = forms.BooleanField(
        label="I agree to the terms and conditions",
        required=True,
        error_messages={'required': 'You must agree to the terms and conditions to register.'}
    )

    license_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., RN123456',
            'pattern': '[A-Z0-9]{5,30}',
            'title': '5-30 uppercase letters and numbers only'
        }),
        help_text='Your official phlebotomist registration/license number (5-30 alphanumeric characters)'
    )
    
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        empty_label="-- Select Donation Center --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the donation center you'll be assigned to",
        required=False
    )
    
    phone = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1234567890',
            'pattern': r'^\+?1?\d{9,15}$',
            'title': 'Enter phone number: +999999999 (9-15 digits)'
        }),
        help_text='Enter phone number in international format: +999999999'
    )
    
    profile_pic = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        help_text='Upload a professional photo (max 5MB, JPG/PNG)'
    )

    class Meta:
        model = Phlebotomist
        fields = [
            'license_number',
            'donation_center',
            'phone',
            'profile_pic',
        ]

    # -------------------------
    # Validation Methods
    # -------------------------
    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        
        # Check length
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
        
        # Check for valid characters
        if not re.match(r'^[\w.@+-]+$', username):
            raise ValidationError("Username can only contain letters, numbers, and @/./+/-/_ characters.")
        
        # Check uniqueness
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        
        # Check uniqueness
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered. Please use another email or login.")
        
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data['first_name'].strip()
        
        if len(first_name) < 2:
            raise ValidationError("First name must be at least 2 characters long.")
        
        # Only allow letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", first_name):
            raise ValidationError("First name can only contain letters, spaces, hyphens, and apostrophes.")
        
        return first_name.title()

    def clean_last_name(self):
        last_name = self.cleaned_data['last_name'].strip()
        
        if len(last_name) < 2:
            raise ValidationError("Last name must be at least 2 characters long.")
        
        # Only allow letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", last_name):
            raise ValidationError("Last name can only contain letters, spaces, hyphens, and apostrophes.")
        
        return last_name.title()

    def clean_password1(self):
        pwd1 = self.cleaned_data.get("password1")
        
        if len(pwd1) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        
        # Check for at least one letter and one number
        if not re.search(r'[a-zA-Z]', pwd1):
            raise ValidationError("Password must contain at least one letter.")
        
        if not re.search(r'\d', pwd1):
            raise ValidationError("Password must contain at least one number.")
        
        # Check for common passwords
        common_passwords = ['password', '12345678', 'qwerty', 'abc123']
        if pwd1.lower() in common_passwords:
            raise ValidationError("This password is too common. Please choose a stronger password.")
        
        return pwd1

    def clean_password2(self):
        pwd1 = self.cleaned_data.get("password1")
        pwd2 = self.cleaned_data.get("password2")
        
        if pwd1 and pwd2 and pwd1 != pwd2:
            raise ValidationError("The two password fields didn't match.")
        
        return pwd2

    def clean_license_number(self):
        license_num = self.cleaned_data['license_number'].strip().upper()
        
        # Check format
        if not re.match(r'^[A-Z0-9]{5,30}$', license_num):
            raise ValidationError(
                "License number must be 5-30 characters and contain only uppercase letters and numbers."
            )
        
        # Check uniqueness
        if Phlebotomist.objects.filter(license_number=license_num).exists():
            raise ValidationError(
                "This license number is already in use. If this is your number, please contact support."
            )
        
        return license_num

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        
        # Remove spaces and dashes for validation
        phone_clean = phone.replace(' ', '').replace('-', '')
        
        # Check format
        if not re.match(r'^\+?1?\d{9,15}$', phone_clean):
            raise ValidationError(
                "Enter a valid phone number in format: +999999999 (9-15 digits)"
            )
        
        # Check if phone already exists
        if Phlebotomist.objects.filter(phone=phone_clean).exists():
            raise ValidationError("This phone number is already registered.")
        
        return phone_clean

    def clean_profile_pic(self):
        profile_pic = self.cleaned_data.get('profile_pic')
        
        if profile_pic:
            # Check file size (max 5MB)
            if profile_pic.size > 5 * 1024 * 1024:
                raise ValidationError("Profile picture size cannot exceed 5MB.")
            
            # Check file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if profile_pic.content_type not in allowed_types:
                raise ValidationError("Only JPG, PNG, and GIF images are allowed.")
        
        return profile_pic

    # -------------------------
    # Save Method
    # -------------------------
    def save(self, commit=True):
        """Create both User and Phlebotomist objects."""
        user = User(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()

        phlebotomist = super().save(commit=False)
        phlebotomist.user = user
        phlebotomist.is_approved = False  # Set to pending approval
        phlebotomist.is_active = True
        
        if commit:
            phlebotomist.save()
        
        return phlebotomist


# -------------------------
# Edit Forms
# -------------------------
class PhlebotomistUserForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
            'style': 'background-color: #e9ecef; cursor: not-allowed;'
        }),
        label="Email Address (Cannot be changed)",
        help_text="Contact your administrator if you need to change your email address."
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make email field truly disabled
        if self.instance and self.instance.pk:
            self.fields['email'].disabled = True


class PhlebotomistForm(forms.ModelForm):
    # READ-ONLY fields for display
    license_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
            'style': 'background-color: #e9ecef; cursor: not-allowed;'
        }),
        label="License Number (Cannot be changed)",
        help_text="Your official phlebotomist license number is locked for verification purposes."
    )
    
    donation_center = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'disabled': 'disabled',
            'style': 'background-color: #e9ecef; cursor: not-allowed;'
        }),
        label="Donation Center (Cannot be changed)",
        help_text="Contact your administrator to change your assigned donation center."
    )

    class Meta:
        model = Phlebotomist
        fields = ['phone', 'profile_pic', 'license_number', 'donation_center']
        widgets = {
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your phone number'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        from blood.models import DonationCenter
        
        # Set the queryset for donation_center
        self.fields['donation_center'].queryset = DonationCenter.objects.all()
        
        # Make license_number and donation_center truly read-only
        if self.instance and self.instance.pk:
            self.fields['license_number'].disabled = True
            self.fields['donation_center'].disabled = True
        
        # Pre-populate the read-only fields with instance data
        if self.instance and self.instance.pk:
            self.fields['license_number'].initial = self.instance.license_number
            self.fields['donation_center'].initial = self.instance.center


# -------------------------
# Appointment Form
# -------------------------
class AppointmentForm(forms.ModelForm):
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Donation Centre"
    ) 
    phlebotomist = forms.ModelChoiceField(
        queryset=Phlebotomist.objects.none(),  # Initially empty, filtered dynamically
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Phlebotomist"
    )
    date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'form-control',
            'placeholder': 'Select appointment date and time',
        }),
        input_formats=['%Y-%m-%dT%H:%M'],
        required=True,
        label="Appointment Date"
    )

    class Meta:
        model = Appointment
        fields = ['donation_center', 'phlebotomist', 'date']

    def __init__(self, *args, **kwargs):
        self.donor_instance = kwargs.pop('donor_instance', None)
        center = kwargs.pop('center', None)

        if 'instance' not in kwargs or kwargs['instance'] is None:
            kwargs['instance'] = Appointment()
            kwargs['instance'].donor = None
        elif self.donor_instance:
            kwargs['instance'].donor = self.donor_instance
            kwargs['instance'].patient = None

        super().__init__(*args, **kwargs)

        self.fields['phlebotomist'].queryset = Phlebotomist.objects.none()
        if center:
            self.fields['phlebotomist'].queryset = Phlebotomist.objects.filter(
                donation_center=center,
                is_approved=True  
            ).order_by('user__first_name')
        elif 'donation_center' in self.data:
            try:
                center_id = int(self.data.get('donation_center'))
                self.fields['phlebotomist'].queryset = Phlebotomist.objects.filter(
                    donation_center_id=center_id,
                    is_approved=True  
                ).order_by('user__first_name')
            except (ValueError, TypeError):
                self.fields['phlebotomist'].queryset = Phlebotomist.objects.none()
        elif self.instance.pk and self.instance.donation_center:
            self.fields['phlebotomist'].queryset = self.instance.donation_center.phlebotomists.filter(
                is_approved=True
            ).order_by('user__first_name')

    def save(self, commit=True):
        appointment = super().save(commit=False)
        # patient and donor are assigned in __init__, so no need to reassign here
        if commit:
            appointment.save()
        return appointment