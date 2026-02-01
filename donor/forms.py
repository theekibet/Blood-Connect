from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator, EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from blood.models import DonationCenter
from .models import Donor, DonorEligibility, BloodDonate
from nurse.models import Nurse
from datetime import date
from datetime import datetime
from donor.models import DonorBloodRequest,BLOODGROUP_CHOICES
from donor.models import KENYAN_COUNTIES

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
    Blood group becomes read-only after nurse verification.
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
                verified_by = self.instance.bloodgroup_verified_by.get_full_name() if self.instance.bloodgroup_verified_by else 'nurse'
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
                    "<strong>Not yet verified.</strong> Your blood group will be verified by a nurse during your first donation. "
                    "You can update it here, but the nurse's verification will be final."
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
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your weight in kg'}),
        help_text='Enter your weight in kilograms (minimum 50kg).'
    )
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Select your gender.'
    )
    good_health = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true'],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Are you in good health?",
        help_text='You must be in good health to donate.'
    )
    travel_history = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true'],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Have you traveled outside your country recently?",
        help_text='Travel outside may affect eligibility.'
    )
    pregnant = forms.TypedChoiceField(
        choices=BOOLEAN_CHOICES,
        coerce=lambda x: x in [True, 'True', 'true'],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Are you currently pregnant?",
        required=False,
        help_text='Applicable only if you are female.'
    )
    medical_conditions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'List any medical conditions or allergies'}),
        help_text='List chronic conditions or allergies if any.'
    )
    agree_to_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to the terms and conditions and confirm that the information provided is true.",
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

    def clean(self):
        cleaned_data = super().clean()
        gender = cleaned_data.get('gender')
        pregnant = cleaned_data.get('pregnant')
        good_health = cleaned_data.get('good_health')

        if good_health is False:
            self.add_error('good_health', "You must be in good health to donate.")

        if gender == 'Female':
            if pregnant is None:
                self.add_error('pregnant', 'Please specify if you are currently pregnant.')
        else:
            cleaned_data['pregnant'] = False

        # Age check
        age = cleaned_data.get('age')
        if age is None and self.donor and self.donor.dob:
            age = self.calculate_age(self.donor.dob)
            cleaned_data['age'] = age

        if age is not None and (age < 18 or age > 65):
            raise ValidationError("Your age must be between 18 and 65 years based on your date of birth.")

        return cleaned_data

    @staticmethod
    def calculate_age(dob):
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
# -------------------------------
# BloodDonate
# -------------------------------
class BloodDonateForm(forms.ModelForm):
    BLOOD_GROUPS = list(BLOODGROUP_CHOICES)

    first_name = forms.CharField(
        label="First Name", 
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    last_name = forms.CharField(
        label="Last Name", 
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    national_id = forms.CharField(
        label="National ID", 
        max_length=20, 
        required=False, 
        disabled=True,
        widget=forms.TextInput(attrs={
            'readonly': 'readonly',
            'class': 'form-control'
        })
    )
    
    mobile = forms.CharField(
        label="Mobile Number", 
        max_length=20, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    bloodgroup = forms.ChoiceField(
        choices=[('', 'Select blood group (optional)')] + BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Blood Group",
        required=False
    )
    
    unit = forms.IntegerField(
    label="Unit (ml)",
    min_value=350,
    max_value=450,
    required=False,  # Optional field
    widget=forms.NumberInput(attrs={
        'class': 'form-control',
        'placeholder': 'volume 350-450 ml(optional)*=1unit*'
    }),
    help_text="Optional. If provided, must be between 350 ml and 450 ml."
)

    
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={
            'id': 'donationCenterSelect',
            'class': 'form-select'
        }),
        label="Donation Center",
        required=True
    )
    
    nurse = forms.ModelChoiceField(
        queryset=Nurse.objects.none(),
        widget=forms.Select(attrs={
            'id': 'nurseSelect',
            'disabled': 'disabled',
            'class': 'form-select'
        }),
        label="Nurse",
        required=True
    )
    
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Select appointment date',
        }),
        label="Appointment Date",
        required=True
    )
    
    # Hidden field for time - populated by JavaScript
    appointment_time = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )

    def __init__(self, *args, donor=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Store donor instance for later use
        self.donor = donor

        # Pre-populate donor information
        if donor:
            self.fields['first_name'].initial = donor.user.first_name
            self.fields['last_name'].initial = donor.user.last_name
            self.fields['national_id'].initial = getattr(donor, 'national_id', '')
            self.fields['mobile'].initial = getattr(donor, 'mobile', '')
            
            # ==========================================
            # BLOOD GROUP VERIFICATION LOGIC
            # ==========================================
            if donor.bloodgroup_verified and donor.bloodgroup:
                # Blood group is verified - make it read-only and pre-filled
                self.fields['bloodgroup'].initial = donor.bloodgroup
                self.fields['bloodgroup'].widget.attrs.update({
                    'readonly': 'readonly',
                    'disabled': 'disabled',
                    'style': 'background-color: #e9ecef; cursor: not-allowed; font-weight: bold; font-size: 1.1rem;',
                    'title': f'Your verified blood group: {donor.bloodgroup}'
                })
                self.fields['bloodgroup'].help_text = (
                    f'✓ Verified blood group: <strong>{donor.bloodgroup}</strong> '
                    f'(Confirmed by nurse on first donation)'
                )
                self.fields['bloodgroup'].required = False
                
                # Override choices to show only verified blood group
                self.fields['bloodgroup'].choices = [(donor.bloodgroup, donor.bloodgroup)]
                
            else:
                # First donation - blood group is optional
                self.fields['bloodgroup'].help_text = (
                    'Optional - Your blood group will be verified by the nurse during your first donation'
                )
                self.fields['bloodgroup'].widget.attrs.update({
                    'class': 'form-select',
                    'style': 'font-size: 1rem;'
                })

        # Handle nurse dropdown based on donation center selection
        if 'donation_center' in self.data:
            try:
                center_id = int(self.data.get('donation_center'))
                self.fields['nurse'].queryset = Nurse.objects.filter(
                    donation_center_id=center_id
                ).select_related('user').order_by('user__first_name')
                # Enable nurse dropdown when center is selected
                self.fields['nurse'].widget.attrs.pop('disabled', None)
            except (ValueError, TypeError):
                self.fields['nurse'].queryset = Nurse.objects.none()
                self.fields['nurse'].widget.attrs['disabled'] = 'disabled'
        elif self.instance.pk and hasattr(self.instance, 'donation_center') and self.instance.donation_center:
            self.fields['nurse'].queryset = self.instance.donation_center.nurses.order_by('user__first_name')
            self.fields['nurse'].widget.attrs.pop('disabled', None)
        else:
            self.fields['nurse'].queryset = Nurse.objects.none()
            self.fields['nurse'].widget.attrs['disabled'] = 'disabled'

    def clean_appointment_time(self):
        appointment_time = self.cleaned_data.get('appointment_time')
        if not appointment_time:
            raise ValidationError("Please select an appointment time.")
        return appointment_time

    def clean_appointment_date(self):
        appointment_date = self.cleaned_data.get('appointment_date')
        
        if appointment_date:
            today = timezone.now().date()
            if appointment_date < today:
                raise ValidationError("Appointment date cannot be in the past.")
        
        return appointment_date
    def clean_unit(self):
        unit = self.cleaned_data.get('unit')
        if unit is None:
            raise forms.ValidationError("Donation volume is required.")
        if unit < 350:
            raise forms.ValidationError("The minimum allowed donation volume is 350 ml.")
        if unit > 450:
            raise forms.ValidationError("The maximum allowed donation volume is 450 ml.")
        return unit

    def clean_bloodgroup(self):
        """
        Clean blood group field with verification logic.
        If donor has verified blood group, always use it regardless of form input.
        """
        bloodgroup = self.cleaned_data.get('bloodgroup')
        
        # If donor exists and has verified blood group, use it
        if self.donor and self.donor.bloodgroup_verified:
            return self.donor.bloodgroup
        
        # For first-time donors, blood group is optional
        return bloodgroup if bloodgroup else None

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        nurse = cleaned_data.get('nurse')
        donation_center = cleaned_data.get('donation_center')

        # Validate nurse belongs to selected donation center
        if nurse and donation_center:
            if nurse.donation_center != donation_center:
                raise ValidationError({
                    'nurse': 'Selected nurse does not belong to the selected donation center.'
                })

        # Validate appointment time format and combine with date
        if appointment_date and appointment_time:
            try:
                # Parse time (format: "09:00 AM" or "09:00")
                if 'AM' in appointment_time or 'PM' in appointment_time:
                    time_obj = datetime.strptime(appointment_time.strip(), "%I:%M %p").time()
                else:
                    # Handle 24-hour format
                    time_obj = datetime.strptime(appointment_time.strip(), "%H:%M").time()
                
                appointment_datetime = datetime.combine(appointment_date, time_obj)
                cleaned_data['appointment_datetime'] = appointment_datetime
                
                # Validate appointment is in the future
                if timezone.make_aware(appointment_datetime) <= timezone.now():
                    raise ValidationError(
                        "Appointment must be scheduled for a future date and time."
                    )
                    
            except ValueError as e:
                raise ValidationError(f"Invalid appointment time format: {str(e)}")

        # Blood group validation for verified donors
        if self.donor and self.donor.bloodgroup_verified:
            # Force the verified blood group
            cleaned_data['bloodgroup'] = self.donor.bloodgroup

        return cleaned_data
    

    class Meta:
        model = BloodDonate
        fields = [
            'bloodgroup', 'unit', 'donation_center', 'nurse'
        ]
        
# -------------------------------
# DonorBloodRequest(on behalf of a patient)
# -------------------------------        
class DonorBloodRequestForm(forms.ModelForm):
    class Meta:
        model = DonorBloodRequest
        fields = [
            'patient_first_name',
            'patient_last_name',
            'patient_dob',
            'contact_number',
            'bloodgroup',
            'unit',
            'donation_center',
            'consent_confirmed',
        ]
        widgets = {
            'consent_confirmed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'patient_dob': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_unit(self):
        unit = self.cleaned_data.get("unit")
        if unit is None:
            return unit
        if unit < 450 or unit > 2700:
            raise forms.ValidationError("Unit must be between 450ml and 2700ml.")
        return unit

    def clean_consent_confirmed(self):
        consent = self.cleaned_data.get("consent_confirmed")
        if not consent:
            raise forms.ValidationError("You must confirm consent to proceed.")
        return consent

    def clean_patient_dob(self):
        dob = self.cleaned_data.get('patient_dob')
        if dob and dob > date.today():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return dob
