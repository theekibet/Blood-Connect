from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from blood.models import DonationCenter
from .models import Nurse, Appointment, NurseBloodRequest


# -------------------------
# Login Form
# -------------------------
class NurseLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter username', 'class': 'form-control'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter password', 'class': 'form-control'})
    )


# -------------------------
# Signup Form (User + Nurse)
# -------------------------
class NurseSignupForm(forms.ModelForm):
    # -------------------------
    # User-related fields
    # -------------------------
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Username', 'class': 'form-control'}),
        max_length=150
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Email address', 'class': 'form-control'})
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'First Name', 'class': 'form-control'})
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Last Name', 'class': 'form-control'})
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}),
        label="Password"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password', 'class': 'form-control'}),
        label="Confirm Password"
    )

    terms = forms.BooleanField(label="I agree to the terms and conditions")

    # -------------------------
    # Dropdown for Donation Center
    # -------------------------
    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        empty_label="-- Select Donation Center --",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Nurse
        fields = [
            'registration_number',
            'specialization',
            'donation_center',
            'phone',
            'profile_pic',
            'bio',
        ]
        widgets = {
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'specialization': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    # -------------------------
    # Validation
    # -------------------------
    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise ValidationError("Username already taken, kindly retry.")
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already registered.")
        return email

    def clean_password2(self):
        pwd1 = self.cleaned_data.get("password1")
        pwd2 = self.cleaned_data.get("password2")
        if pwd1 and pwd2 and pwd1 != pwd2:
            raise ValidationError("Passwords do not match.")
        return pwd2

    # -------------------------
    # Save Method
    # -------------------------
    def save(self, commit=True):
        """Create both User and Nurse objects."""
        user = User(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
        user.set_password(self.cleaned_data['password1']) # <-- Password hashing 
        if commit:
            user.save()

        nurse = super().save(commit=False)
        nurse.user = user
        if commit:
            nurse.save()
        return nurse

# -------------------------
# Edit Forms
# -------------------------
class NurseUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class NurseForm(forms.ModelForm):
    class Meta:
        model = Nurse
        fields = ['phone', 'specialization', 'profile_pic', 'bio', 'donation_center']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'specialization': forms.Select(attrs={'class': 'form-control'}),  # dropdown
            'bio': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'donation_center': forms.Select(attrs={'class': 'form-control'}),  # dropdown
        }
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
    nurse = forms.ModelChoiceField(
        queryset=Nurse.objects.none(),  # Initially empty, filtered dynamically
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Nurse"
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
        fields = ['donation_center', 'nurse', 'date']

    def __init__(self, *args, **kwargs):
        self.patient_instance = kwargs.pop('patient_instance', None)
        self.donor_instance = kwargs.pop('donor_instance', None)
        center = kwargs.pop('center', None)

        # Assign patient or donor to the model instance before calling super
        if 'instance' not in kwargs or kwargs['instance'] is None:
            kwargs['instance'] = Appointment()
        if self.patient_instance:
            kwargs['instance'].patient = self.patient_instance
            kwargs['instance'].donor = None
        elif self.donor_instance:
            kwargs['instance'].donor = self.donor_instance
            kwargs['instance'].patient = None

        super().__init__(*args, **kwargs)

        # Dynamically filter nurses based on Donation Center selection
        self.fields['nurse'].queryset = Nurse.objects.none()
        if center:
            self.fields['nurse'].queryset = Nurse.objects.filter(
                donation_center=center
            ).order_by('user__first_name')
        elif 'donation_center' in self.data:
            try:
                center_id = int(self.data.get('donation_center'))
                self.fields['nurse'].queryset = Nurse.objects.filter(
                    donation_center_id=center_id
                ).order_by('user__first_name')
            except (ValueError, TypeError):
                self.fields['nurse'].queryset = Nurse.objects.none()
        elif self.instance.pk and self.instance.donation_center:
            self.fields['nurse'].queryset = self.instance.donation_center.nurses.order_by('user__first_name')

    def save(self, commit=True):
        appointment = super().save(commit=False)
        # patient and donor are assigned in __init__, so no need to reassign here
        if commit:
            appointment.save()
        return appointment
# -------------------------
# Blood Request Form
# -------------------------
class BloodRequestForm(forms.ModelForm):
    class Meta:
        model = NurseBloodRequest
        fields = ['supplying_center', 'blood_group', 'units', 'reason', 'urgency_level']

        widgets = {
            'supplying_center': forms.Select(attrs={'class': 'form-select'}),
            'blood_group': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'units': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '10'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'urgency_level': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_units(self):
        units = self.cleaned_data.get('units')
        if units is None or units < 1:
            raise forms.ValidationError("Units must be at least 1 ml.")
        if units % 10 != 0:
            raise forms.ValidationError("Please enter units in multiples of 10 ml.")
        return units
