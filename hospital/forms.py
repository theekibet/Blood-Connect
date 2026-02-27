from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Hospital, HospitalUser, HospitalBloodRequest
from blood.models import DonationCenter
import re

class HospitalRegistrationForm(forms.ModelForm):
    """Form for registering a new hospital"""
    
    # Hospital details
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Hospital Name'})
    )
    registration_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Registration Number'})
    )
    county = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'County'})
    )
    
    # Contact details
    contact_person = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person Name'})
    )
    contact_phone = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Phone'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )
    alternative_phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Alternative Phone (Optional)'})
    )
    
    # Operational details
    has_blood_storage = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    serving_centre = forms.ModelChoiceField(
        queryset=DonationCenter.objects.filter(is_active=True),
        required=False,
        empty_label="-- Select Donation Center --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Location
    latitude = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Latitude', 'step': 'any'})
    )
    longitude = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Longitude', 'step': 'any'})
    )
    
    class Meta:
        model = Hospital
        fields = [
            'name', 'registration_number', 'county', 'contact_person',
            'contact_phone', 'email', 'alternative_phone', 'has_blood_storage',
            'serving_centre', 'latitude', 'longitude'
        ]
    
    def clean_registration_number(self):
        reg_num = self.cleaned_data['registration_number'].strip().upper()
        if Hospital.objects.filter(registration_number=reg_num).exists():
            raise ValidationError("A hospital with this registration number already exists.")
        return reg_num
    
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Hospital.objects.filter(email=email).exists():
            raise ValidationError("A hospital with this email already exists.")
        return email
    
    def clean_contact_phone(self):
        phone = self.cleaned_data['contact_phone'].strip()
        phone_clean = phone.replace(' ', '').replace('-', '')
        if not re.match(r'^\+?1?\d{9,15}$', phone_clean):
            raise ValidationError("Enter a valid phone number in format: +254XXXXXXXXX")
        return phone


class HospitalUserSignupForm(forms.ModelForm):
    """Form for creating a hospital user account"""
    
    # User fields
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'})
    )
    
    # Hospital selection
    hospital = forms.ModelChoiceField(
        queryset=Hospital.objects.filter(is_active=True, verified=True),
        empty_label="-- Select Hospital --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    role = forms.ChoiceField(
        choices=HospitalUser.ROLE_CHOICES,
        initial='lab_tech',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = HospitalUser
        fields = ['hospital', 'role']
    
    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username=username).exists():
            raise ValidationError("Username already taken.")
        return username
    
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already registered.")
        return email
    
    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match.")
        
        return cleaned_data
    
    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )
        
        hospital_user = super().save(commit=False)
        hospital_user.user = user
        
        if commit:
            hospital_user.save()
        
        return hospital_user


class HospitalLoginForm(forms.Form):
    """Form for hospital user login"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )


class HospitalBloodRequestForm(forms.ModelForm):
    """Form for creating a blood request"""
    
    patient_first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Patient First Name'})
    )
    patient_last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Patient Last Name'})
    )
    patient_age = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Patient Age'})
    )
    patient_gender = forms.ChoiceField(
        choices=[('', '-- Select Gender --'), ('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    patient_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Patient ID (Optional)'})
    )
    
    blood_group = forms.ChoiceField(
        choices=HospitalBloodRequest.BLOOD_GROUP_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    units_requested = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Units Required'})
    )
    
    doctor_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Doctor Name'})
    )
    doctor_license = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Doctor License (Optional)'})
    )
    
    urgency = forms.ChoiceField(
        choices=HospitalBloodRequest.URGENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = HospitalBloodRequest
        fields = [
            'patient_first_name', 'patient_last_name', 'patient_age', 'patient_gender', 'patient_id',
            'blood_group', 'units_requested', 'doctor_name', 'doctor_license', 'urgency'
        ]
    
    def clean_units_requested(self):
        units = self.cleaned_data['units_requested']
        if units < 1:
            raise ValidationError("Units must be at least 1.")
        return units


class HospitalProfileForm(forms.ModelForm):
    """Form for updating hospital details"""
    
    class Meta:
        model = Hospital
        fields = [
            'contact_person', 'contact_phone', 'email', 'alternative_phone',
            'has_blood_storage', 'serving_centre', 'latitude', 'longitude'
        ]
        widgets = {
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'alternative_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'has_blood_storage': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'serving_centre': forms.Select(attrs={'class': 'form-select'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
        }