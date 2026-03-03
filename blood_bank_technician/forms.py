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
    
    # Read-only display fields for regular users
    email_display = forms.EmailField(
        required=False,
        disabled=True,
        label="Email",
        help_text="Email cannot be changed. Contact admin for updates."
    )
    
    employee_id_display = forms.CharField(
        max_length=50,
        required=False,
        disabled=True,
        label="Employee ID",
        help_text="Employee ID cannot be changed"
    )
    
    center_display = forms.CharField(
        required=False,
        disabled=True,
        label="Center",
        help_text="Center assignment can only be changed by administrator"
    )
    
    is_active_display = forms.BooleanField(
        required=False,
        disabled=True,
        label="Active Status",
        help_text="Account status can only be changed by administrator"
    )
    
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
        # Check if user is superuser
        self.user = kwargs.pop('user', None)
        self.is_superuser = kwargs.pop('is_superuser', False)
        
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if field_name not in ['is_active', 'is_active_display', 'employee_id_display', 
                                 'center_display', 'email_display', 'profile_pic']:
                field.widget.attrs['class'] = 'form-control'
            elif field_name == 'is_active':
                field.widget.attrs['class'] = 'form-check-input'
        
        # Make is_active a checkbox
        self.fields['is_active'].widget.attrs['class'] = 'form-check-input'
        
        # Add user fields if instance exists
        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            
            # Set display field values
            self.fields['email_display'].initial = self.instance.user.email
            self.fields['employee_id_display'].initial = self.instance.employee_id
            self.fields['center_display'].initial = str(self.instance.center) if self.instance.center else "Not Assigned"
            self.fields['is_active_display'].initial = self.instance.is_active
        
        # Configure field permissions based on user role
        if not self.is_superuser:
            # Make all sensitive fields read-only for regular users
            sensitive_fields = ['employee_id', 'is_active', 'center', 'email']
            
            for field in sensitive_fields:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].widget = forms.HiddenInput()
                    if field == 'center':
                        self.fields[field].required = False
            
            # Also hide the email field from the form
            if 'email' in self.fields:
                self.fields['email'].widget = forms.HiddenInput()
    
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
    
    def clean(self):
        cleaned_data = super().clean()
        
        # For regular users, ensure sensitive fields aren't being changed
        if not self.is_superuser and self.instance and self.instance.pk:
            # For center, use the original instance
            if 'center' in cleaned_data:
                cleaned_data['center'] = self.instance.center
            
            # Restore other sensitive fields
            sensitive_fields = {
                'employee_id': self.instance.employee_id,
                'is_active': self.instance.is_active,
            }
            
            for field, original_value in sensitive_fields.items():
                if field in cleaned_data and cleaned_data.get(field) != original_value:
                    cleaned_data[field] = original_value
            
            # Also restore email
            if self.instance.user.email != cleaned_data.get('email'):
                cleaned_data['email'] = self.instance.user.email
        
        return cleaned_data
    
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
            # Update user information (only non-sensitive fields)
            user = instance.user
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            
            # Only update email if user is superuser
            if self.is_superuser and 'email' in self.cleaned_data:
                user.email = self.cleaned_data['email']
            
            user.save()
            
            instance.save()
            self.save_m2m()
            print(f"✅ Profile saved with picture: {instance.profile_pic}")
        
        return instance