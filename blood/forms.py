from django import forms
from .models import Contact, DonationCenter
from .models import Stock
import datetime
from .models import StockUnit
from django.core.exceptions import ValidationError

from django.utils import timezone
import re
class AdminLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your username",
            "autofocus": "autofocus",
            "name": "username",
        }),
        label="Username",
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your password",
            "name": "password",
        }),
        label="Password",
    )

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
    BARCODE_REGEX = re.compile(r'^[A-Z0-9\-]{8,20}$')

    class Meta:
        model = StockUnit
        fields = ['center', 'bloodgroup', 'unit', 'expiry_date', 'barcode']
        widgets = {
            'center': forms.Select(attrs={'class': 'form-select'}),
            'bloodgroup': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '1'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Leave empty for auto-generation'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        # HTML5 constraints for better UX (server-side validation still enforced)
        self.fields['expiry_date'].widget.attrs['min'] = today.isoformat()
        self.fields['barcode'].required = False  # Make barcode optional
        self.fields['barcode'].widget.attrs['pattern'] = r'[A-Z0-9\-]{8,20}'
        self.fields['barcode'].widget.attrs['title'] = 'Optional: 8-20 chars, A-Z, 0-9, and "-" only. Leave empty for auto-generation.'

    def clean_unit(self):
        unit = self.cleaned_data.get('unit')
        if unit is None or unit <= 0:
            raise ValidationError("Units must be a positive integer.")
        if unit > 10000:
            raise ValidationError("Units cannot exceed 10000 ml.")
        return unit

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date is None:
            raise ValidationError("Expiry date is required.")
        if expiry_date < timezone.localdate():
            raise ValidationError("Expiry date cannot be in the past.")
        return expiry_date

    def clean_barcode(self):
        barcode = (self.cleaned_data.get('barcode') or '').strip().upper()
        
        # If barcode is empty, it will be auto-generated, so return empty string
        if not barcode:
            return ''
        
        # If barcode is provided, validate it
        if not self.BARCODE_REGEX.match(barcode):
            raise ValidationError("Barcode must be 8–20 chars (A–Z, 0–9, '-') only.")
        
        # Check for duplicates (excluding current instance if editing)
        existing = StockUnit.objects.filter(barcode=barcode)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        
        if existing.exists():
            raise ValidationError("Barcode already exists.")
        
        return barcode

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Auto-generate barcode if not provided
        if not instance.barcode:
            instance.generate_unique_barcode()
        
        if commit:
            instance.save()
        
        return instance
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
