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
from datetime import datetime,timedelta
from donor.models import BLOODGROUP_CHOICES
from donor.models import KENYAN_COUNTIES
from datetime import datetime, timedelta, time as datetime_time
# -------------------------------
# DonorUserForm
# -------------------------------
class DonorUserForm(forms.ModelForm):
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
        label="Confirm Password",
        required=True,
        help_text="Must match the password above."
    )
    email = forms.EmailField(
        validators=[EmailValidator(message="Invalid Email Address")],
        widget=forms.EmailInput(attrs={'placeholder': 'Enter your email'}),
        required=True
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'password', 'email']
        widgets = {
            'password': forms.PasswordInput(attrs={'placeholder': 'Enter Password'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Enter first name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Enter last name'}),
            'username': forms.TextInput(attrs={'placeholder': 'Choose a username'}),
        }
        help_texts = {
            'password': "Password must be at least 8 characters long and include at least one letter and one number.",
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Check if username already exists
            if User.objects.filter(username__iexact=username).exists():
                raise ValidationError(
                    f"Username '{username}' is already taken. Please choose a different one."
                )
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError(
                    "This email address is already registered. Please use a different email or login."
                )
        return email.lower()

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        # Validate password requirements
        if password:
            if len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters long.")
            if not any(char.isdigit() for char in password):
                self.add_error('password', "Password must include at least one numeric character.")
            if not any(char.isalpha() for char in password):
                self.add_error('password', "Password must include at least one letter.")

        # Validate password match
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        user.set_password(password)
        user.email = self.cleaned_data.get('email').lower()
        if commit:
            user.save()
        return user

# -------------------------------
# DonorForm
# -------------------------------
class DonorForm(forms.ModelForm):
    BLOOD_GROUPS = [
        ('', '---------'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
    ]

    bloodgroup = forms.ChoiceField(
        choices=BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )
    national_id = forms.CharField(
        validators=[RegexValidator(r'^\d{8}$', message="National ID must be exactly 8 digits.")],
        widget=forms.TextInput(attrs={'placeholder': 'Enter 8 digits (e.g., 12345678)'}),
        required=True
    )
    mobile = forms.CharField(
        validators=[RegexValidator(r'^\+254\d{9}$', message="Mobile number must be in +254 format (e.g., +254712345678).")],
        widget=forms.TextInput(attrs={'placeholder': 'Enter (e.g +254712345678)'}),
        required=True
    )
    dob = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=True,
        label="Date of Birth",
        help_text="Enter your date of birth"
    )
    latitude = forms.FloatField(widget=forms.HiddenInput(), required=False)
    longitude = forms.FloatField(widget=forms.HiddenInput(), required=False)
    profile_pic = forms.ImageField(required=False)

    class Meta:
        model = Donor
        fields = [
            'bloodgroup', 'national_id', 'mobile', 'county',
            'dob', 'latitude', 'longitude', 'profile_pic'
        ]
        widgets = {
            'county': forms.Select(attrs={'class': 'form-control'}),
        }
        labels={
            'county':'Select Your County'
        }

    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if national_id:
            # Check if national ID already exists
            if Donor.objects.filter(national_id=national_id).exists():
                raise ValidationError(
                    f"National ID '{national_id}' is already registered. Each person can only register once."
                )
        return national_id

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if mobile:
            # Check if mobile number already exists
            if Donor.objects.filter(mobile=mobile).exists():
                raise ValidationError(
                    f"Mobile number '{mobile}' is already registered. Please use a different number."
                )
        return mobile

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            if age < 18:
                raise ValidationError("You must be at least 18 years old to register as a donor.")
            if age > 120:
                raise ValidationError("Please enter a valid date of birth.")
            
            # Check if date is in the future
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
        
        return dob

# -------------------------------
# DonorLogin
# -------------------------------
class DonorLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'input--style-5', 'placeholder': 'Enter Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input--style-5', 'placeholder': 'Enter Password'})
    )

# -------------------------------
# DonorProfile
# -------------------------------
class DonorProfileForm(forms.ModelForm):
    """
    Form for editing donor profile.
    Blood group becomes read-only after phlebotomist verification.
    Email is always read-only for security.
    """
    
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        }),
        label="First Name"
    )

    last_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        }),
        label="Last Name"
    )

    # Email - Always read-only
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
            'style': 'background-color: #e9ecef; cursor: not-allowed;',
            'title': 'Email cannot be changed. Contact support if needed.'
        }),
        label="Email Address",
        help_text="<i class='fas fa-lock text-warning'></i> Cannot be changed. Contact support if you need to update your email."
    )

    # Blood group - Conditionally read-only
    bloodgroup = forms.ChoiceField(
        choices=[('', '---------')] + list(BLOODGROUP_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Blood Group",
        required=False
    )

    # Address
    county = forms.ChoiceField(
        choices=[('', '---------')] + list(KENYAN_COUNTIES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Select Your County"
    )   


    # Mobile
    mobile = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your mobile number'
        }),
        label="Mobile Number"
    )

    # Profile picture
    profile_pic = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        label="Profile Picture"
    )

    class Meta:
        model = Donor
        fields = ['bloodgroup', 'county', 'mobile', 'profile_pic']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make email field truly disabled
        if self.instance and self.instance.pk:
            self.fields['email'].disabled = True
            
            # ==========================================
            # BLOOD GROUP VERIFICATION LOGIC
            # ==========================================
            if self.instance.bloodgroup_verified:
                # Blood group is verified - make it read-only
                self.fields['bloodgroup'].widget = forms.TextInput(attrs={
                    'readonly': 'readonly',
                    'disabled': 'disabled',
                    'class': 'form-control',
                    'style': 'background-color: #d4edda; cursor: not-allowed; font-weight: bold; font-size: 1.1rem; color: #155724; border: 2px solid #28a745;',
                    'title': f'Verified blood group: {self.instance.bloodgroup}'
                })
                self.fields['bloodgroup'].choices = [(self.instance.bloodgroup, self.instance.bloodgroup)]
                
                # Add verification info to help text
                verified_by = self.instance.bloodgroup_verified_by.get_full_name() if self.instance.bloodgroup_verified_by else 'phlebotomist'
                verified_date = self.instance.bloodgroup_verified_at.strftime('%B %d, %Y') if self.instance.bloodgroup_verified_at else 'first donation'
                
                self.fields['bloodgroup'].help_text = (
                    f"<div class='alert alert-success mt-2 mb-0 p-2'>"
                    f"<i class='fas fa-check-circle'></i> "
                    f"<strong>Verified by {verified_by}</strong> on {verified_date}. "
                    f"<br><small class='text-muted'>"
                    f"<i class='fas fa-lock'></i> Blood group cannot be changed after verification for safety and integrity."
                    f"</small></div>"
                )
            else:
                # Blood group not yet verified - can be changed but with warning
                self.fields['bloodgroup'].help_text = (
                    "<div class='alert alert-warning mt-2 mb-0 p-2'>"
                    "<i class='fas fa-exclamation-triangle'></i> "
                    "<strong>Not yet verified.</strong> Your blood group will be verified by a lab technologist during your first donation. "
                    "You can update it here for now, but the lab test's verification will be final and automatically updated and unchangeable after."
                    "</div>"
                )

    def clean_bloodgroup(self):
        """
        Prevent changing verified blood group.
        Always return the original verified blood group if it exists.
        """
        bloodgroup = self.cleaned_data.get('bloodgroup')
        
        if self.instance and self.instance.bloodgroup_verified:
            # Return original verified blood group, ignore any attempted changes
            return self.instance.bloodgroup
        
        return bloodgroup

    def clean_email(self):
        """Prevent email changes"""
        if self.instance and self.instance.pk:
            return self.instance.user.email
        return self.cleaned_data.get('email')

# Constants for Choices
GENDER_CHOICES = [
    ('Male', 'Male'),
    ('Female', 'Female'),
    ('Other', 'Other'),
]

BOOLEAN_CHOICES = [
    (True, 'Yes'),
    (False, 'No'),
]


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