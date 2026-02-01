from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator, EmailValidator
from .models import Patient
from nurse.models import Appointment, Nurse
from datetime import date
from blood.models import DonationCenter
from .models import BloodRequest
from django.utils.safestring import mark_safe
from donor.models import KENYAN_COUNTIES


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
    """
    Patient profile form with blood group verification logic
    """
    BLOOD_GROUPS = [
        ('', '---------'),
        ('O+', 'O+'), ('O-', 'O-'), ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'), ('AB+', 'AB+'), ('AB-', 'AB-'),
    ]
    
    county = forms.ChoiceField(
        choices=KENYAN_COUNTIES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="County",
        required=True
    )

    dob = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Select your date of birth',
            'max': date.today().strftime('%Y-%m-%d')
        }),
        label="Date of Birth",
        required=True
    )

    bloodgroup = forms.ChoiceField(
        choices=BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        label="Blood Group"
    )

    profile_pic = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
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
            'profile_pic', 'gender', 'dob', 'bloodgroup', 'national_id',
            'mobile', 'emergency_contact', 'county', 'latitude', 'longitude'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ==========================================
        # BLOOD GROUP VERIFICATION LOGIC
        # ==========================================
        if self.instance and self.instance.pk:
            if self.instance.bloodgroup_verified:
                # Blood group is verified - makes it completely read-only
                verified_bg = self.instance.bloodgroup
                
                # Change to text input (read-only) instead of select
                self.fields['bloodgroup'] = forms.CharField(
                    initial=verified_bg,
                    widget=forms.TextInput(attrs={
                        'readonly': 'readonly',
                        'disabled': 'disabled',
                        'class': 'form-control',
                        'style': 'background-color: #d4edda; cursor: not-allowed; font-weight: bold; font-size: 1.1rem; color: #155724; border: 2px solid #28a745;',
                        'title': f'Verified blood group: {verified_bg}'
                    }),
                    required=False,
                    label="Blood Group (Verified)"
                )
                
                # Add verification info to help text
                verified_by = self.instance.bloodgroup_verified_by.get_full_name() if self.instance.bloodgroup_verified_by else 'nurse'
                verified_date = self.instance.bloodgroup_verified_at.strftime('%B %d, %Y') if self.instance.bloodgroup_verified_at else 'during first blood request'
                
                self.fields['bloodgroup'].help_text = mark_safe(
                    f"<div class='alert alert-success mt-2 mb-0 p-2'>"
                    f"<i class='fas fa-check-circle'></i> "
                    f"<strong>✅ Verified by {verified_by}</strong> on {verified_date}. "
                    f"<br><small class='text-muted'>"
                    f"<i class='fas fa-lock'></i> Blood group cannot be changed after nurse verification for safety and data integrity."
                    f"</small></div>"
                )
            else:
                # Blood group not yet verified - can be changed but with warning
                self.fields['bloodgroup'].help_text = mark_safe(
                    "<div class='alert alert-warning mt-2 mb-0 p-2'>"
                    "<i class='fas fa-exclamation-triangle'></i> "
                    "<strong>⚠️ Not yet verified.</strong> Your blood group will be verified by a nurse during your first blood request appointment. "
                    "You can update it here, but the nurse's verification will be final and cannot be changed."
                    "</div>"
                )

    def clean_bloodgroup(self):
        """
        Prevent changing verified blood group.
        Always return the original verified blood group if it exists.
        """
        bloodgroup = self.cleaned_data.get('bloodgroup')
        
        # CRITICAL: If blood group is verified, ignore any form input
        if self.instance and self.instance.pk and self.instance.bloodgroup_verified:
            # Return the verified blood group from database, ignore form data
            return self.instance.bloodgroup
        
        # For unverified patients, allow changes
        return bloodgroup if bloodgroup else None


   
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
        
        
class RequestForm(forms.ModelForm):
    BLOOD_GROUPS = [
        ('', 'Select blood group (optional)'),
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    first_name = forms.CharField(
        label="First Name",
        widget=forms.TextInput(attrs={'class': 'input--style-5'}),
    )
    last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={'class': 'input--style-5'}),
    )
    patient_age = forms.IntegerField(
        label="Patient Age",
        widget=forms.NumberInput(attrs={'class': 'input--style-5'}),
        min_value=0,
    )

    bloodgroup = forms.ChoiceField(
        choices=BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'input--style-5'}),
        required=False,
        help_text="If unknown, you may leave this blank."
    )

    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={'class': 'input--style-5'}),
        label="Donation Center"
    )

    contact_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'input--style-5'}),
        label="Contact Number"
    )

    emergency_contact = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'input--style-5'}),
        label="Emergency Contact"
    )

    national_id = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'input--style-5'}),
        label="National ID"
    )

    unit = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'input--style-5',
            'placeholder': '450–2700 ml',
            'min': 450,
            'max': 2700,
            'step': 50,
        }),
        help_text="Enter units if known, or leave blank if unsure."
    )

    class Meta:
        model = BloodRequest
        fields = [
            'first_name',
            'last_name',
            'patient_age',
            'contact_number',
            'emergency_contact',
            'national_id',
            'bloodgroup',
            'unit',
            'donation_center',
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Prefill and lock patient fields if user is a patient
        if self.user and hasattr(self.user, "patient") and self.user.patient:
            patient = self.user.patient
            user_obj = getattr(patient, 'user', None)

            # Prefill basic info
            self.fields['first_name'].initial = user_obj.first_name if user_obj else ''
            self.fields['last_name'].initial = user_obj.last_name if user_obj else ''
            self.fields['patient_age'].initial = patient.age
            self.fields['contact_number'].initial = patient.mobile
            self.fields['emergency_contact'].initial = getattr(patient, "emergency_contact", "")
            self.fields['national_id'].initial = getattr(patient, "national_id", "")

            if patient.bloodgroup_verified and patient.bloodgroup:
                verified_bg = patient.bloodgroup

                self.fields['bloodgroup'] = forms.CharField(
                    initial=verified_bg,
                    widget=forms.TextInput(attrs={
                        'readonly': 'readonly',
                        'disabled': 'disabled',
                        'class': 'input--style-5',
                        'style': 'background-color: #d4edda; cursor: not-allowed; font-weight: bold; font-size: 1.1rem; color: #155724; border: 2px solid #28a745;',
                        'title': f'Your verified blood group: {verified_bg}'
                    }),
                    required=False,
                    label="Blood Group (Verified)"
                )
                self.fields['bloodgroup'].help_text = mark_safe(
                    f'<div class="alert alert-success mt-2 mb-0 p-2">'
                    f'<i class="fas fa-check-circle"></i> '
                    f'✓ Verified blood group: <strong>{verified_bg}</strong> '
                    f'(Confirmed by nurse during your first blood request)'
                    f'</div>'
                )
            else:
                self.fields['bloodgroup'].help_text = mark_safe(
                    '<div class="alert alert-info mt-2 mb-0 p-2">'
                    '<i class="fas fa-info-circle"></i> '
                    '<strong>Optional</strong> - Your blood group will be verified by the nurse during this appointment. '
                    'Once verified, it will be locked for all future requests.'
                    '</div>'
                )
                if patient.bloodgroup:
                    self.fields['bloodgroup'].initial = patient.bloodgroup

            readonly_fields = [
                'first_name', 'last_name', 'patient_age',
                'contact_number', 'emergency_contact', 'national_id'
            ]
            for f in readonly_fields:
                self.fields[f].widget.attrs['readonly'] = True
                self.fields[f].required = False

    def clean_bloodgroup(self):
        bloodgroup = self.cleaned_data.get('bloodgroup')
        if self.user and hasattr(self.user, 'patient'):
            patient = self.user.patient
            if patient.bloodgroup_verified and patient.bloodgroup:
                return patient.bloodgroup
        return bloodgroup if bloodgroup else None

    def clean_unit(self):
        unit = self.cleaned_data.get("unit")
        if unit is None:
            return unit
        if unit < 450 or unit > 2700 or unit % 50 != 0:
            raise forms.ValidationError(
                "Unit must be between 450 ml and 2700 ml in multiples of 50."
            )
        return unit

    def clean_first_name(self):
        if self.user and hasattr(self.user, "patient") and getattr(self.user.patient, 'user', None):
            return self.user.patient.user.first_name
        return self.cleaned_data.get("first_name")

    def clean_last_name(self):
        if self.user and hasattr(self.user, "patient") and getattr(self.user.patient, 'user', None):
            return self.user.patient.user.last_name
        return self.cleaned_data.get("last_name")

    def clean_patient_age(self):
        if self.user and hasattr(self.user, "patient"):
            return self.user.patient.age
        return self.cleaned_data.get("patient_age")

    def clean_contact_number(self):
        if self.user and hasattr(self.user, "patient"):
            return self.user.patient.mobile
        return self.cleaned_data.get("contact_number")

    def clean_emergency_contact(self):
        if self.user and hasattr(self.user, "patient"):
            return getattr(self.user.patient, "emergency_contact", "")
        return self.cleaned_data.get("emergency_contact")

    def clean_national_id(self):
        if self.user and hasattr(self.user, "patient"):
            return getattr(self.user.patient, "national_id", "")
        return self.cleaned_data.get("national_id")
