from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re
import os
from .models import BloodBankTechProfile
from blood.models import DonationCenter

class BloodBankTechSignupForm(forms.ModelForm):
    # User fields
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'})
    )
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'})
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        help_text="Your password must contain at least 8 characters."
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'})
    )
    
    # Profile fields
    employee_id = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employee ID'})
    )
    center = forms.ModelChoiceField(
        queryset=DonationCenter.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        empty_label="-- Select Center --"
    )
    phone = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'})
    )
    
    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to the terms and conditions"
    )
    
    class Meta:
        model = BloodBankTechProfile
        fields = ['employee_id', 'center', 'phone']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mark that this form doesn't have an instance yet
        if not self.instance.pk:
            self.instance._state.adding = True
    
    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Username already exists.")
        return username
    
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Email already registered.")
        return email
    
    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        if not re.search(r'[A-Z]', password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[0-9]', password):
            raise ValidationError("Password must contain at least one number.")
        return password
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords don't match.")
        return password2
    
    def clean_employee_id(self):
        emp_id = self.cleaned_data['employee_id'].strip().upper()
        if BloodBankTechProfile.objects.filter(employee_id=emp_id).exists():
            raise ValidationError("Employee ID already exists.")
        return emp_id
    
    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        # Remove spaces and dashes
        phone = re.sub(r'[\s\-]', '', phone)
        if not re.match(r'^\+?[0-9]{10,15}$', phone):
            raise ValidationError("Enter a valid phone number (10-15 digits).")
        return phone
    
    def save(self, commit=True):
        # Create user first
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            is_active=True
        )
        
        # Create profile instance
        profile = super().save(commit=False)
        profile.user = user
        profile.is_active = False
        
        if commit:
            profile.save()
        
        return profile
class BloodBankTechProfileForm(forms.ModelForm):
    """Form for Blood Bank Technician profile"""
    
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    email = forms.EmailField(required=False)
    
    class Meta:
        model = BloodBankTechProfile
        fields = ['employee_id', 'center', 'phone', 'is_active', 'profile_pic']
        widgets = {
            'center': forms.Select(attrs={'class': 'form-control'}),
            'profile_pic': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if field_name != 'is_active' and field_name != 'profile_pic':
                field.widget.attrs['class'] = 'form-control'
        
        # Make is_active a checkbox
        self.fields['is_active'].widget.attrs['class'] = 'form-check-input'
        
        # Add user fields if instance exists
        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
    
    def clean_profile_pic(self):
        profile_pic = self.cleaned_data.get('profile_pic')
        if profile_pic:
            # Check file size (max 5MB)
            if profile_pic.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Image file too large ( > 5MB )")
            
            # Check file extension
            ext = os.path.splitext(profile_pic.name)[1].lower()
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            if ext not in valid_extensions:
                raise forms.ValidationError("Unsupported file extension. Allowed: .jpg, .jpeg, .png, .gif")
        
        return profile_pic
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Handle profile picture
        if self.cleaned_data.get('profile_pic'):
            # Delete old image if it exists and is different
            if instance.pk:
                try:
                    old_instance = BloodBankTechProfile.objects.get(pk=instance.pk)
                    if old_instance.profile_pic and old_instance.profile_pic != self.cleaned_data['profile_pic']:
                        if os.path.isfile(old_instance.profile_pic.path):
                            os.remove(old_instance.profile_pic.path)
                            print(f"✅ Deleted old profile picture: {old_instance.profile_pic.path}")
                except BloodBankTechProfile.DoesNotExist:
                    pass
                except Exception as e:
                    print(f"⚠️ Error deleting old picture: {e}")
        
        if commit:
            # Update user information
            user = instance.user
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.email = self.cleaned_data['email']
            user.save()
            
            instance.save()
            self.save_m2m()
        
        return instance
