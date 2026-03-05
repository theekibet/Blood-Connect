from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from blood.models import DonationCenter
from .models import Donor, DonorEligibility, BloodDonate
from phlebotomist.models import Phlebotomist
from datetime import date
import re
from datetime import datetime,timedelta
from donor.models import BLOODGROUP_CHOICES
from donor.models import KENYAN_COUNTIES
from datetime import datetime, timedelta, time as datetime_time
# ADD THIS NEW FORM (replace the deleted ones)
GENDER_CHOICES = [
    ('', '--------- Select Gender ---------'),
    ('Male', 'Male'),
    ('Female', 'Female'),
    ('Other', 'Other'),
]
BOOLEAN_CHOICES = [
    (True, 'Yes'),
    (False, 'No'),
]
class DonorSignupForm(forms.Form):
    """
    Simplified signup form - only collects essential information.
    Username is temporarily set to email and changed during onboarding.
    """
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        }),
        required=True,
        label="First Name"
    )
    
    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        }),
        required=True,
        label="Last Name"
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        }),
        required=True,
        label="Email Address",
        help_text="You'll choose your username after signup"
    )
    
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password'
        }),
        required=True,
        help_text="At least 8 characters with letters and numbers"
    )
    
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password'
        }),
        required=True
    )
    
    terms_agreed = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to the terms and conditions",
        error_messages={'required': 'You must agree to the terms and conditions.'}
    )

    def clean_email(self):
        """Validate email uniqueness (case-insensitive)"""
        email = self.cleaned_data.get('email', '').strip().lower()
        
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered. Please login instead.")
        
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("This email cannot be used. Please use a different email.")
        
        return email

    def clean_password1(self):
        """Validate password strength"""
        password = self.cleaned_data.get('password1')
        
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        
        if not any(char.isdigit() for char in password):
            raise ValidationError("Password must contain at least one number.")
        
        if not any(char.isalpha() for char in password):
            raise ValidationError("Password must contain at least one letter.")
        
        return password

    def clean_password2(self):
        """Validate passwords match"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match.")
        
        return password2


class UsernameSelectionForm(forms.Form):
    """
    Form for choosing permanent username after first signup/login.
    Only shown when user's username is still their email.
    """
    username = forms.CharField(
        max_length=150,
        min_length=3,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose your username',
            'autocomplete': 'off'
        }),
        required=True,
        label="Choose Your Username",
        help_text="3-150 characters. Letters, numbers, and @/./+/-/_ only."
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
    
    def clean_username(self):
        """Validate username format and uniqueness"""
        username = self.cleaned_data.get('username', '').strip()
        
        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters long.")
        
        if not re.match(r'^[a-zA-Z0-9@.+-_]+$', username):
            raise ValidationError("Username can only contain letters, numbers, and @/./+/-/_ characters.")
        
        if self.user:
            if User.objects.filter(username__iexact=username).exclude(pk=self.user.pk).exists():
                raise ValidationError("This username is already taken. Please try another.")
        else:
            if User.objects.filter(username__iexact=username).exists():
                raise ValidationError("This username is already taken. Please try another.")
        
        return username
# -------------------------------
# DonorLogin
# -------------------------------
class DonorLoginForm(forms.Form):
    """
    Login form that accepts BOTH username and email.
    Works with EmailOrUsernameBackend authentication backend.
    """
    username = forms.CharField(
        label='Username or Email',
        max_length=254,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username or email',
            'autocomplete': 'username'
        }),
        help_text="You can login with either your username or email"
    )
    
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password'
        })
    )

# -------------------------------
# DonorProfile
# -------------------------------
class DonorProfileForm(forms.ModelForm):
    """
    Form for editing donor profile.
    Blood group is OPTIONAL - not required for onboarding completion.
    Required fields: mobile, national_id, county, dob
    """
    
    # Read-only user fields (for display only)
    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-light',
            'readonly': 'readonly',
            'disabled': 'disabled'
        }),
        label="First Name"
    )

    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-light',
            'readonly': 'readonly',
            'disabled': 'disabled'
        }),
        label="Last Name"
    )

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control bg-light',
            'readonly': 'readonly',
            'disabled': 'disabled'
        }),
        label="Email Address"
    )

    # Blood group - OPTIONAL (can be unknown initially)
    bloodgroup = forms.ChoiceField(
        choices=[('', "I don't know yet")] + list(BLOODGROUP_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Blood Group",
        required=False,  
        help_text="Don't know your blood type? Leave this blank - it will be verified during your first donation appointment."
    )

    # Gender - Optional
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Gender"
    )

    # National ID - REQUIRED
    national_id = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '12345678'
        }),
        label="National ID Number",
        help_text="8 digits (required for identity verification)",
        error_messages={'required': 'National ID is required for verification.'}
    )

    # Date of Birth - REQUIRED
    dob = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label="Date of Birth",
        error_messages={'required': 'Date of birth is required to verify eligibility.'}
    )

    # County - REQUIRED
    county = forms.ChoiceField(
        choices=[('', 'Select your county of residence')] + list(KENYAN_COUNTIES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="County",
        error_messages={'required': 'Please select your county.'}
    )

    # ===== UPDATED: Mobile with 0712345678 format =====
    mobile = forms.CharField(
        max_length=10,  # Exactly 10 digits (0 + 9 digits)
        min_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0712345678',
            'maxlength': '10',
            'pattern': '07[0-9]{8}',
            'title': 'Enter 10 digits starting with 07',
            'inputmode': 'numeric'
        }),
        label="Mobile Number",
        help_text="Format: 0712345678 (10 digits starting with 07)",
        error_messages={
            'required': 'Mobile number is required for appointment communication.',
            'max_length': 'Mobile number must be exactly 10 digits.',
            'min_length': 'Mobile number must be exactly 10 digits.'
        }
    )

    # Profile Picture - Optional
    profile_pic = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        label="Profile Picture (Optional)",
        help_text="Upload a profile photo (optional)"
    )

    class Meta:
        model = Donor
        fields = [
            'bloodgroup', 'gender', 'national_id', 'dob', 
            'county', 'mobile', 'profile_pic'  
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            # Set initial values for user fields
            if hasattr(self.instance, 'user') and self.instance.user:
                self.fields['first_name'].initial = self.instance.user.first_name
                self.fields['last_name'].initial = self.instance.user.last_name
                self.fields['email'].initial = self.instance.user.email
            
            # Blood group verification - make read-only if verified
            if self.instance.bloodgroup_verified:
                self.fields['bloodgroup'].widget = forms.TextInput(attrs={
                    'readonly': 'readonly',
                    'disabled': 'disabled',
                    'class': 'form-control bg-success text-white',
                    'style': 'font-weight: bold;',
                })
                self.fields['bloodgroup'].initial = self.instance.bloodgroup
                self.fields['bloodgroup'].help_text = f"✅ Verified: {self.instance.bloodgroup} (cannot be changed)"
                self.fields['bloodgroup'].required = False
            
            # Make certain fields read-only after initial entry
            if self.instance.national_id:
                self.fields['national_id'].widget.attrs.update({
                    'readonly': 'readonly',
                    'class': 'form-control bg-light'
                })
                self.fields['national_id'].help_text = "Cannot be changed after initial entry"
                self.fields['national_id'].required = False
                
            if self.instance.dob:
                self.fields['dob'].widget.attrs.update({
                    'readonly': 'readonly',
                    'class': 'form-control bg-light'
                })
                self.fields['dob'].help_text = "Cannot be changed after initial entry"
                self.fields['dob'].required = False
            
            # Format mobile number for display (remove any existing formatting)
            if self.instance.mobile:
                # If stored as +254..., convert to 07... for display
                if self.instance.mobile.startswith('+254'):
                    self.fields['mobile'].initial = '0' + self.instance.mobile[4:]
                else:
                    self.fields['mobile'].initial = self.instance.mobile

    def clean_national_id(self):
        """Validate national ID"""
        national_id = self.cleaned_data.get('national_id')
        
        # Skip validation if already has value
        if self.instance and self.instance.national_id:
            return self.instance.national_id
        
        if not national_id:
            raise ValidationError("National ID is required.")
        
        # Remove any spaces or dashes
        national_id = re.sub(r'[\s\-]', '', national_id)
        
        # Check uniqueness
        if Donor.objects.filter(national_id=national_id).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This National ID is already registered.")
        
        # Validate format (8 digits)
        if not re.match(r'^\d{8}$', national_id):
            raise ValidationError("National ID must be exactly 8 digits (e.g., 12345678).")
        
        return national_id

    # ===== UPDATED: Mobile validation for 0712345678 format =====
    def clean_mobile(self):
        """Validate mobile number - must be 0712345678 format (0 followed by 9 digits)"""
        mobile = self.cleaned_data.get('mobile')
        
        if not mobile:
            raise ValidationError("Mobile number is required.")
        
        # Remove any spaces, dashes, parentheses
        mobile = re.sub(r'[\s\-\(\)]', '', mobile)
        
        # Check if it's empty after stripping
        if not mobile:
            raise ValidationError("Mobile number is required.")
        
        # Check length (must be 10 digits: 0 + 9 digits)
        if len(mobile) != 10:
            raise ValidationError(f"Mobile number must be 10 digits. You entered {len(mobile)} digits.")
        
        # Check if all characters are digits
        if not mobile.isdigit():
            raise ValidationError("Mobile number must contain only digits.")
        
        # Check if it starts with 0
        if not mobile.startswith('0'):
            raise ValidationError("Mobile number must start with 0 (e.g., 0712345678)")
        
        # Check if it starts with 07 (common Kenyan prefix)
        if not mobile.startswith('07'):
            raise ValidationError("Mobile number should start with 07 (e.g., 0712345678)")
        
        # Check uniqueness (exclude current donor)
        if Donor.objects.filter(mobile=mobile).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This mobile number is already registered.")
        
        return mobile

    def clean_dob(self):
        """Validate date of birth"""
        dob = self.cleaned_data.get('dob')
        
        # Skip validation if already has value
        if self.instance and self.instance.dob:
            return self.instance.dob
        
        if not dob:
            raise ValidationError("Date of birth is required.")
        
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
        if age < 18:
            raise ValidationError("You must be at least 18 years old to donate blood.")
        
        if age > 120:
            raise ValidationError("Please enter a valid date of birth.")
        
        if dob > today:
            raise ValidationError("Date of birth cannot be in the future.")
        
        return dob

    def clean_county(self):
        """Validate county"""
        county = self.cleaned_data.get('county')
        
        if not county:
            raise ValidationError("Please select your county.")
        
        return county

    def clean_bloodgroup(self):
        """Blood group is optional"""
        bloodgroup = self.cleaned_data.get('bloodgroup')
        
        # If verified, can't be changed
        if self.instance and self.instance.bloodgroup_verified:
            return self.instance.bloodgroup
        
        # Return None if empty
        return bloodgroup if bloodgroup else None

    def save(self, commit=True):
        """Save donor profile"""
        instance = super().save(commit=False)
        
        # Convert 07... to +254... for storage (optional - keeps consistent format)
        if instance.mobile and instance.mobile.startswith('0'):
            # Store as +2547... for consistency
            instance.mobile = '+254' + instance.mobile[1:]
        
        if commit:
            instance.save()
        
        return instance


# Validator functions
def validate_age(value):
    if not (18 <= value <= 65):
        raise ValidationError('Age must be between 18 and 65.')


def validate_weight(value):
    if value < 50:
        raise ValidationError('Weight must be at least 50 kg.')

# -------------------------------
# DonorEligibility
# -------------------------------
class DonorEligibilityForm(forms.ModelForm):
    age = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    weight = forms.FloatField(
        validators=[validate_weight],
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Enter your weight in kg',
            'min': '30',
            'max': '200',
            'step': '0.1'
        }),
        help_text='Enter your weight in kilograms (minimum 50kg).'
    )
    
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Select your gender.'
    )
    
    good_health = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Are you currently in good general health?",
        help_text='You must be feeling well and healthy on the day of donation.'
    )
    
    travel_history = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Have you traveled outside your country in the past 3 months?",
        help_text='Travel to certain areas may require a waiting period.'
    )
    
    # Additional travel details (conditional)
    travel_destination = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Where did you travel?'
        }),
        label="Travel destination"
    )
    
    travel_duration = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Duration in days'
        }),
        label="Duration of stay (days)"
    )
    
    pregnant = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Are you currently pregnant?",
        required=False,
        help_text='Applicable only if you are female.'
    )
    
    recent_childbirth = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Have you given birth in the last 6 months?",
        required=False
    )
    
    breastfeeding = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Are you currently breastfeeding?",
        required=False
    )
    
    medical_conditions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 
            'rows': 3, 
            'placeholder': 'List any medical conditions, medications, or allergies'
        }),
        help_text='List chronic conditions, current medications, or allergies if any.'
    )
    
    # New fields for better assessment
    recent_surgery = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Have you had any surgery in the past 6 months?",
        required=False
    )
    
    recent_tattoo = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true', '1', 1],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Have you gotten a tattoo or piercing in the past 6 months?",
        required=False,
        help_text='Tattoos/piercings may require a waiting period.'
    )
    
    medications = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'List any medications you are currently taking'
        }),
        label="Current medications"
    )
    
    agree_to_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I confirm that all information provided is true and accurate to the best of my knowledge.",
        error_messages={'required': 'You must agree before submitting.'}
    )

    class Meta:
        model = DonorEligibility
        fields = [
            'weight', 'gender', 'good_health', 'travel_history',
            'pregnant', 'medical_conditions', 'agree_to_terms', 'age'
        ]

    def __init__(self, *args, donor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.donor = donor
        # If donor exists, populate hidden age field
        if donor and donor.dob:
            self.initial['age'] = self.calculate_age(donor.dob)
            self.age_value = self.initial['age']

    def clean(self):
        cleaned_data = super().clean()
        gender = cleaned_data.get('gender')
        pregnant = cleaned_data.get('pregnant')
        good_health = cleaned_data.get('good_health')
        travel_history = cleaned_data.get('travel_history')
        travel_destination = cleaned_data.get('travel_destination')
        recent_surgery = cleaned_data.get('recent_surgery')
        recent_tattoo = cleaned_data.get('recent_tattoo')
        
        # Validate travel details if travel_history is True
        if travel_history:
            if not travel_destination:
                self.add_error('travel_destination', 'Please specify your travel destination.')
            if not cleaned_data.get('travel_duration'):
                self.add_error('travel_duration', 'Please specify the duration of your stay.')

        if good_health is False:
            self.add_error('good_health', "You must be in good health to donate.")

        if gender == 'Female':
            if pregnant is None:
                self.add_error('pregnant', 'Please specify if you are currently pregnant.')
        else:
            cleaned_data['pregnant'] = False
            cleaned_data['recent_childbirth'] = False
            cleaned_data['breastfeeding'] = False

        # Age check
        age = cleaned_data.get('age')
        if age is None and self.donor and self.donor.dob:
            age = self.calculate_age(self.donor.dob)
            cleaned_data['age'] = age

        if age is not None:
            if age < 18:
                raise ValidationError("You must be at least 18 years old to donate blood.")
            elif age > 65:
                # First-time donors over 65 need physician approval
                if not hasattr(self, 'physician_approved') or not self.physician_approved:
                    self.add_error(None, "First-time donors over 65 require physician approval. Please consult your doctor.")

        return cleaned_data

    @staticmethod
    def calculate_age(dob):
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
# -------------------------------
# BloodDonate
# -------------------------------
class BloodDonateForm(forms.ModelForm):
    """
    Form for donors to schedule blood donation appointments.
    MATCHES TEMPLATE: Uses separate appointment_date and appointment_time fields.
    """
    
    # Optional fields that donors might fill (readonly)
    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name',
            'readonly': 'readonly'
        })
    )
    
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name',
            'readonly': 'readonly'
        })
    )
    
    mobile = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mobile Number',
            'readonly': 'readonly'
        })
    )
    
    # Donation center selection
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.filter(is_active=True),
        required=True,
        empty_label="Select Donation Center",
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text='Select your preferred donation center'
    )
    
    # Phlebotomist selection (will be populated via AJAX)
    phlebotomist = forms.ModelChoiceField(
        queryset=Phlebotomist.objects.none(),  # Populated dynamically
        required=True,
        empty_label="Select a center first",
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text='Select a phlebotomist (nurse)'
    )
    
    # Separate date and time fields (matching template)
    appointment_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'min': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        }),
        help_text='Select appointment date (Monday-Friday only)'
    )
    
    # Time slot choices (8 AM to 5 PM)
    TIME_CHOICES = [
        ('', 'Select Time'),
        ('08:00', '8:00 AM'),
        ('08:30', '8:30 AM'),
        ('09:00', '9:00 AM'),
        ('09:30', '9:30 AM'),
        ('10:00', '10:00 AM'),
        ('10:30', '10:30 AM'),
        ('11:00', '11:00 AM'),
        ('11:30', '11:30 AM'),
        ('12:00', '12:00 PM'),
        ('12:30', '12:30 PM'),
        ('13:00', '1:00 PM'),
        ('13:30', '1:30 PM'),
        ('14:00', '2:00 PM'),
        ('14:30', '2:30 PM'),
        ('15:00', '3:00 PM'),
        ('15:30', '3:30 PM'),
        ('16:00', '4:00 PM'),
        ('16:30', '4:30 PM'),
    ]
    
    appointment_time = forms.ChoiceField(
        choices=TIME_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text='Select appointment time (8 AM - 5 PM)'
    )
    
    # Unit choices
    UNIT_CHOICES = [
        (450, '450 ml (Standard)'),
        (350, '350 ml (Reduced)'),
    ]
    
    unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial=450,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text='Standard donation amount'
    )
    
    class Meta:
        model = BloodDonate
        fields = ['bloodgroup', 'unit', 'donation_center', 'phlebotomist']
        widgets = {
            'bloodgroup': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
    
    def __init__(self, *args, donor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.donor = donor
        
        # If donor is provided and has a verified blood group, lock it
        if donor and donor.bloodgroup_verified and donor.bloodgroup:
            self.fields['bloodgroup'].initial = donor.bloodgroup
            self.fields['bloodgroup'].disabled = True
            self.fields['bloodgroup'].widget.attrs['readonly'] = True
        
        # Populate phlebotomists based on selected center (for edit forms)
        if 'donation_center' in self.data:
            try:
                center_id = int(self.data.get('donation_center'))
                self.fields['phlebotomist'].queryset = Phlebotomist.objects.filter(
                    center_id=center_id
                ).select_related('user')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.donation_center:
            self.fields['phlebotomist'].queryset = Phlebotomist.objects.filter(
                center=self.instance.donation_center
            ).select_related('user')
    
    def clean_appointment_date(self):
        """Validate appointment date."""
        date = self.cleaned_data.get('appointment_date')
        
        if date:
            today = timezone.now().date()
            
            # Must be in the future
            if date <= today:
                raise forms.ValidationError("Appointment date must be in the future.")
            
            # Cannot be more than 3 months in advance
            max_date = today + timedelta(days=90)
            if date > max_date:
                raise forms.ValidationError("Appointments cannot be scheduled more than 3 months in advance.")
            
            # Must be a weekday (Monday-Friday)
            if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                raise forms.ValidationError("Appointments are only available Monday through Friday.")
        
        return date
    
    def clean_appointment_time(self):
        """Validate appointment time."""
        time_str = self.cleaned_data.get('appointment_time')
        
        if not time_str:
            raise forms.ValidationError("Please select an appointment time.")
        
        return time_str
    
    def clean(self):
        """Additional validation and combine date+time."""
        cleaned_data = super().clean()
        
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        
        # Combine date and time into a datetime object
        if appointment_date and appointment_time:
            try:
                # Parse time string (format: "HH:MM")
                hour, minute = map(int, appointment_time.split(':'))
                
                # Create datetime object
                appointment_datetime = timezone.make_aware(
                    datetime.combine(appointment_date, datetime_time(hour, minute))
                )
                
                # Store in cleaned_data for use in view
                cleaned_data['combined_datetime'] = appointment_datetime
                
            except (ValueError, AttributeError) as e:
                raise forms.ValidationError(f"Invalid time format: {e}")
        
        # Check donor eligibility (56 days between donations)
        if self.donor and self.donor.last_donation_date:
            next_eligible_date = self.donor.last_donation_date + timedelta(days=56)
            
            if appointment_date and appointment_date < next_eligible_date:
                raise forms.ValidationError(
                    f"You are not eligible to donate until {next_eligible_date.strftime('%B %d, %Y')}. "
                    f"You must wait 56 days between donations."
                )
        
        # Check for pending donations
        if self.donor:
            pending_donations = BloodDonate.objects.filter(
                donor=self.donor,
                status='pending'
            )
            
            if self.instance.pk:
                pending_donations = pending_donations.exclude(pk=self.instance.pk)
            
            if pending_donations.exists():
                raise forms.ValidationError(
                    "You already have a pending donation appointment. "
                    "Please complete or cancel it before scheduling a new one."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save with combined datetime."""
        instance = super().save(commit=False)
        
        # Get the combined datetime from cleaned_data
        if hasattr(self, 'cleaned_data') and 'combined_datetime' in self.cleaned_data:
            instance.date = self.cleaned_data['combined_datetime']
        
        if commit:
            instance.save()
        
        return instance