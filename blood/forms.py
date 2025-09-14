from django import forms
from .models import Contact, DonationCenter, BloodRequest
from .models import Stock
import datetime
from .models import StockUnit
from django.core.exceptions import ValidationError
from blood.models import DonorBloodRequest
class BloodForm(forms.ModelForm):
    expiry_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
        error_messages={'required': 'Expiry date is required.'}
    )

    class Meta:
        model = Stock
        fields = ['bloodgroup', 'unit', 'expiry_date']
        widgets = {
            'bloodgroup': forms.Select(choices=Stock.BLOOD_GROUP_CHOICES),
            'unit': forms.NumberInput(attrs={'min': 0}),
        }

    def clean_unit(self):
        unit = self.cleaned_data.get('unit')
        if unit is None or unit < 0:
            raise forms.ValidationError("Unit must be a positive number.")
        return unit

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date and expiry_date < datetime.date.today():
            raise forms.ValidationError("Expiry date cannot be in the past.")
        return expiry_date

class RequestForm(forms.ModelForm):
    BLOOD_GROUPS = [
        ('', 'Select blood group (optional)'),
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    URGENCY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Emergency', 'Emergency'),
    ]

    bloodgroup = forms.ChoiceField(
        choices=BLOOD_GROUPS,
        widget=forms.Select(attrs={'class': 'input--style-5'}),
        required=False,
        help_text="If unknown, you may leave this blank."
    )

    donation_center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={'class': 'input--style-5'})
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

    reason = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input--style-5',
            'placeholder': 'Reason for request (optional)'
        }),
        label="Reason"
    )

    urgency_level = forms.ChoiceField(
        choices=URGENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'input--style-5'}),
        label="Urgency Level"
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
            'patient_name',
            'patient_age',
            'contact_number',
            'emergency_contact',
            'national_id',
            'reason',
            'bloodgroup',
            'unit',
            'donation_center',
            'urgency_level',
        ]
        widgets = {
            'patient_name': forms.TextInput(attrs={'class': 'input--style-5'}),
            'patient_age': forms.NumberInput(attrs={'class': 'input--style-5'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)  # current logged-in user
        super().__init__(*args, **kwargs)

        # Only patients should use this form
        if self.user and hasattr(self.user, "patient"):
            patient = self.user.patient

            # Prefill patient fields from profile
            self.fields['patient_name'].initial = patient.get_name()
            self.fields['patient_age'].initial = patient.age
            self.fields['contact_number'].initial = patient.mobile
            self.fields['emergency_contact'].initial = getattr(patient, "emergency_contact", "")
            self.fields['national_id'].initial = getattr(patient, "national_id", "")
            self.fields['bloodgroup'].initial = patient.bloodgroup

            # Lock down these fields as readonly
            readonly_fields = [
                'patient_name',
                'patient_age',
                'contact_number',
                'emergency_contact',
                'national_id',
                'bloodgroup',
            ]
            for f in readonly_fields:
                self.fields[f].widget.attrs['readonly'] = True
                self.fields[f].required = False

    def clean_unit(self):
        unit = self.cleaned_data.get("unit")
        if unit is None:
            return unit
        if unit < 450 or unit > 2700 or unit % 50 != 0:
            raise forms.ValidationError(
                "Unit must be between 450 ml and 2700 ml in multiples of 50."
            )
        return unit

    # Protect readonly fields from tampering
    def clean_patient_name(self):
        if self.user and hasattr(self.user, "patient"):
            return self.user.patient.get_name()
        return self.cleaned_data.get("patient_name")

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

    def clean_bloodgroup(self):
        if self.user and hasattr(self.user, "patient"):
            return self.user.patient.bloodgroup
        return self.cleaned_data.get("bloodgroup")

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'email', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }

class StockUnitForm(forms.ModelForm):
    class Meta:
        model = StockUnit
        fields = ['center', 'bloodgroup', 'unit', 'expiry_date', 'barcode']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_expiry_date(self):
        expiry = self.cleaned_data['expiry_date']
        if expiry and expiry < datetime.date.today():
            raise forms.ValidationError("Expiry date cannot be in the past.")
        return expiry

    def clean_barcode(self):
        barcode = self.cleaned_data.get('barcode')
        # Allow empty barcode to let utility function assign one
        return barcode or None
class DonationCenterForm(forms.ModelForm):
    class Meta:
        model = DonationCenter
        fields = ['name', 'address', 'city', 'latitude', 'longitude', 'contact_number', 'open_hours']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'latitude': forms.NumberInput(attrs={'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'step': 'any'}),
            'open_hours': forms.TextInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        city = cleaned_data.get('city')
        if name and city:
            exists = DonationCenter.objects.filter(name__iexact=name.strip(), city__iexact=city.strip()).exists()
            if exists:
                raise ValidationError("A donation center with this name and city already exists.")
        return cleaned_data
class DonorBloodRequestForm(forms.ModelForm):
    class Meta:
        model = DonorBloodRequest
        fields = [
            'patient_name',
            'patient_age',
            'contact_number',
            'reason',
            'bloodgroup',
            'unit',
            'urgency_level',
            'donation_center',
            'consent_confirmed',
        ]
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Reason for blood request'}),
            'consent_confirmed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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

