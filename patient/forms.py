from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator, EmailValidator
from .models import Patient
from nurse.models import Appointment, Nurse
from datetime import date

class PatientUserForm(forms.ModelForm):
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm Password',
            'class': 'form-control'
        }),
        label="Confirm Password",
        required=True
    )
    email = forms.EmailField(
        validators=[EmailValidator(message="Invalid Email Address")],
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email',
            'class': 'form-control'
        })
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'password', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter Password'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter Email'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password:
            if len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters.")
            if not any(c.isdigit() for c in password):
                self.add_error('password', "Password must include at least one number.")
            if not any(c.isalpha() for c in password):
                self.add_error('password', "Password must include at least one letter.")

        if password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data



class PatientForm(forms.ModelForm):
    BLOOD_GROUPS = [
        ('', '---------'),  # empty choice for optional selection
        ('O+', 'O+'), ('O-', 'O-'), ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'), ('AB+', 'AB+'), ('AB-', 'AB-'),
    ]

    dob = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Select your date of birth',
            'max': date.today().strftime('%Y-%m-%d')  # Disallow future dates
        }),
        label="Date of Birth",
        required=True
    )

    bloodgroup = forms.ChoiceField(
        choices=BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False  #  optional
    )

    profile_pic = forms.ImageField(
        required=False,  #  optional
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    national_id = forms.CharField(
        validators=[RegexValidator(r'^\d{8}$', message="National ID must be 8 digits.")],
        widget=forms.TextInput(attrs={'placeholder': '12345678', 'class': 'form-control'})
    )

    mobile = forms.CharField(
        validators=[RegexValidator(r'^07\d{8}$', message="Phone must start with 07 and be 10 digits.")],
        widget=forms.TextInput(attrs={'placeholder': '0712345678', 'class': 'form-control'})
    )

    emergency_contact = forms.CharField(
        validators=[RegexValidator(r'^07\d{8}$', message="Emergency contact must be valid.")],
        widget=forms.TextInput(attrs={'placeholder': '0712345678', 'class': 'form-control'})
    )

    latitude = forms.FloatField(widget=forms.HiddenInput(), required=False)
    longitude = forms.FloatField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Patient
        fields = [
            'profile_pic', 'gender', 'dob', 'bloodgroup',
             'mobile', 'national_id', 'emergency_contact',
            'latitude', 'longitude'
        ]


   
class PatientLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter Username', 'class': 'form-control'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter Password', 'class': 'form-control'})
    )


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['profile_pic', 'bloodgroup', 'mobile']
        widgets = {
            'bloodgroup': forms.Select(attrs={'class': 'form-control'}),
            
            'mobile': forms.TextInput(attrs={'class': 'form-control'}),
        }
