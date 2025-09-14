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
        }
        help_texts = {
            'password': "Password must be at least 8 characters long and include at least one letter and one number.",
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password:
            if len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters long.")
            if not any(char.isdigit() for char in password):
                self.add_error('password', "Password must include at least one numeric character.")
            if not any(char.isalpha() for char in password):
                self.add_error('password', "Password must include at least one letter.")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password') # <-- Password hashing 
        user.set_password(password)
        if commit:
            user.save()
        return user




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
        validators=[RegexValidator(r'^\d{8}$', message="National ID must be 8 digits.")],
        widget=forms.TextInput(attrs={'placeholder': 'Enter (e.g., 12345678)'}),
        required=True
    )

    mobile = forms.CharField(
        validators=[RegexValidator(r'^\+254\d{9}$', message="Mobile number must be in +254 format and 12 digits long.")],
        widget=forms.TextInput(attrs={'placeholder': 'Enter (e.g +254712345678)'}),
        required=True
    )

    address = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter (e.g., Nairobi, Kenya)'}),
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
            'bloodgroup', 'national_id', 'mobile', 'address',
            'dob', 'latitude', 'longitude', 'profile_pic'
        ]

    def clean_dob(self):
        dob = self.cleaned_data['dob']
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise ValidationError("You must be at least 18 years old to register.")
        if age > 120:
            raise ValidationError("Please enter a valid date of birth.")
        return dob


class DonorLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'input--style-5', 'placeholder': 'Enter Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input--style-5', 'placeholder': 'Enter Password'})
    )


class DonorProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )

    last_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )

    class Meta:
        model = Donor
        fields = ['bloodgroup', 'address', 'mobile', 'profile_pic']
        widgets = {
            'bloodgroup': forms.Select(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter your address'
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your phone number'
            }),
            'profile_pic': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }


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
class BloodDonateForm(forms.ModelForm):
    BLOOD_GROUPS = [
        ('O+', 'O+'), ('O-', 'O-'),
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
    ]

    first_name = forms.CharField(
        label="First Name", max_length=30, required=True,
        widget=forms.TextInput()
    )
    last_name = forms.CharField(
        label="Last Name", max_length=30, required=True,
        widget=forms.TextInput()
    )
    national_id = forms.CharField(
        label="National ID", max_length=20, required=False, disabled=True,
        widget=forms.TextInput(attrs={'readonly': 'readonly'})
    )
    mobile = forms.CharField(
        label="Mobile Number", max_length=20, required=True,
        widget=forms.TextInput()
    )
    bloodgroup = forms.ChoiceField(
        choices=[('', 'Select blood group (optional)')] + BLOOD_GROUPS,
        widget=forms.Select(),
        label="Blood Group",
        required=False
    )
    unit = forms.IntegerField(
        min_value=1,
        label="Unit (ml)",
        widget=forms.NumberInput(),
        required=False
    )
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={'id': 'donationCenterSelect'}),
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
    
    # Updated field name to match template expectations
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Select appointment date',
        }),
        label="Appointment Date",
        required=True
    )
    
    # Hidden field for time - will be populated by JavaScript
    appointment_time = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    def __init__(self, *args, donor=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, forms.HiddenInput):
                existing_classes = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing_classes + ' form-control').strip()

        # Pre-populate donor information
        if donor:
            self.fields['first_name'].initial = donor.user.first_name
            self.fields['last_name'].initial = donor.user.last_name
            self.fields['national_id'].initial = getattr(donor, 'national_id', '')
            self.fields['mobile'].initial = getattr(donor, 'mobile', '')

        # Handle nurse dropdown based on donation center
        if 'donation_center' in self.data:
            try:
                center_id = int(self.data.get('donation_center'))
                self.fields['nurse'].queryset = Nurse.objects.filter(
                    donation_center_id=center_id
                ).order_by('user__first_name')
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

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get('appointment_date')
        appointment_time = cleaned_data.get('appointment_time')
        nurse = cleaned_data.get('nurse')

        # Validate appointment time is selected
        if not appointment_time:
            raise forms.ValidationError("Please select an appointment time.")

        # Combine date and time into datetime
        if appointment_date and appointment_time:
            try:
                # Parse time (format: "09:00 AM")
                time_obj = datetime.strptime(appointment_time, "%I:%M %p").time()
                appointment_datetime = datetime.combine(appointment_date, time_obj)
                cleaned_data['appointment_datetime'] = appointment_datetime
            except ValueError:
                raise forms.ValidationError("Invalid appointment time format.")

        # Validate appointment is in the future
        if 'appointment_datetime' in cleaned_data:
            if cleaned_data['appointment_datetime'] <= datetime.now():
                raise forms.ValidationError("Appointment must be scheduled for a future date and time.")

        return cleaned_data

    class Meta:
        model = BloodDonate
        fields = [
            'bloodgroup', 'unit', 'donation_center', 'nurse'
        ]