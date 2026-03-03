from django import forms
from .models import BloodTest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re
import os
from .models import LabTechnologistProfile
from blood.models import DonationCenter


class LabTechnologistSignupForm(forms.Form):  # Changed from ModelForm to Form
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
    qualification = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Qualification'})
    )
    license_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'License number'})
    )
    profile_pic = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    
    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="I agree to the terms and conditions"
    )
    
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
        if LabTechnologistProfile.objects.filter(employee_id=emp_id).exists():
            raise ValidationError("Employee ID already exists.")
        return emp_id
    
    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        # Remove spaces and dashes
        phone = re.sub(r'[\s\-]', '', phone)
        if not re.match(r'^\+?[0-9]{10,15}$', phone):
            raise ValidationError("Enter a valid phone number (10-15 digits).")
        return phone
    
    def save(self):
        """Create user and profile"""
        try:
            # Create user first
            user = User.objects.create_user(
                username=self.cleaned_data['username'],
                email=self.cleaned_data['email'],
                password=self.cleaned_data['password1'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                is_active=True  # User is active but needs profile approval
            )
            
            # Then create profile with user reference
            profile = LabTechnologistProfile.objects.create(
                user=user,
                employee_id=self.cleaned_data['employee_id'].upper(),
                center=self.cleaned_data.get('center'),
                phone=self.cleaned_data['phone'],
                qualification=self.cleaned_data.get('qualification', ''),
                license_number=self.cleaned_data.get('license_number', ''),
                profile_pic=self.cleaned_data.get('profile_pic'),
                is_active=False  # Requires admin approval
            )
            
            return profile
            
        except Exception as e:
            # If profile creation fails, delete the user to maintain consistency
            if 'user' in locals():
                user.delete()
            raise e



class LabTechnologistProfileForm(forms.ModelForm):
    """Form for Lab Technologist profile"""
    
    # Read-only display fields for regular users
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    
    # Email - will be made read-only for regular users
    email_display = forms.EmailField(
        required=False,
        disabled=True,
        label="Email",
        help_text="Email cannot be changed. Contact admin for updates."
    )
    
    # Employee ID - read-only for regular users
    employee_id_display = forms.CharField(
        max_length=50,
        required=False,
        disabled=True,
        label="Employee ID",
        help_text="Employee ID cannot be changed"
    )
    
    # License Number - read-only for regular users
    license_number_display = forms.CharField(
        max_length=50,
        required=False,
        disabled=True,
        label="License Number",
        help_text="License number cannot be changed. Contact admin for updates."
    )
    
    # Center - read-only for regular users (using CharField for display)
    center_display = forms.CharField(
        required=False,
        disabled=True,
        label="Center",
        help_text="Center assignment can only be changed by administrator"
    )
    
    # Active Status - read-only for regular users
    is_active_display = forms.BooleanField(
        required=False,
        disabled=True,
        label="Active Status",
        help_text="Account status can only be changed by administrator"
    )
    
    class Meta:
        model = LabTechnologistProfile
        fields = ['employee_id', 'center', 'phone', 'qualification', 
                 'license_number', 'is_active', 'profile_pic', 'specialization',
                 'years_of_experience', 'certification_date', 'certification_expiry']
        widgets = {
            'qualification': forms.Textarea(attrs={'rows': 3}),
            'profile_pic': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'certification_date': forms.DateInput(attrs={'type': 'date'}),
            'certification_expiry': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        # Check if user is superuser (you'll pass this from the view)
        self.user = kwargs.pop('user', None)
        self.is_superuser = kwargs.pop('is_superuser', False)
        
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if field_name not in ['is_active', 'is_active_display', 'employee_id_display', 
                                 'license_number_display', 'center_display', 'email_display']:
                if field_name != 'is_active':
                    field.widget.attrs['class'] = 'form-control'
            elif field_name == 'is_active':
                field.widget.attrs['class'] = 'form-check-input'
        
        # Add user fields if instance exists
        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            
            # Set display field values
            self.fields['email_display'].initial = self.instance.user.email
            self.fields['employee_id_display'].initial = self.instance.employee_id
            self.fields['license_number_display'].initial = self.instance.license_number
            self.fields['center_display'].initial = str(self.instance.center) if self.instance.center else "Not Assigned"
            self.fields['is_active_display'].initial = self.instance.is_active
        
        # Configure field permissions based on user role
        if not self.is_superuser:
            # Make all sensitive fields read-only for regular users
            sensitive_fields = ['employee_id', 'license_number', 'is_active', 'center', 
                              'email', 'specialization', 'years_of_experience', 
                              'certification_date', 'certification_expiry']
            
            for field in sensitive_fields:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].widget = forms.HiddenInput()
                    # Make center field optional since it's hidden
                    if field == 'center':
                        self.fields[field].required = False
            
            # Also hide the email field from the form (we'll show display version)
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
            # Restore original values if someone tries to bypass disabled fields
            # For center, we need to set the actual DonationCenter instance
            if 'center' in cleaned_data:
                # Always use the original center instance for regular users
                cleaned_data['center'] = self.instance.center
            
            # For other fields, restore original values
            sensitive_fields = {
                'employee_id': self.instance.employee_id,
                'license_number': self.instance.license_number,
                'is_active': self.instance.is_active,
                'specialization': self.instance.specialization,
                'years_of_experience': self.instance.years_of_experience,
                'certification_date': self.instance.certification_date,
                'certification_expiry': self.instance.certification_expiry,
            }
            
            for field, original_value in sensitive_fields.items():
                if field in cleaned_data and cleaned_data.get(field) != original_value:
                    cleaned_data[field] = original_value
            
            # Also restore email for the user
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
                    old_instance = LabTechnologistProfile.objects.get(pk=instance.pk)
                    if old_instance.profile_pic and old_instance.profile_pic != self.cleaned_data['profile_pic']:
                        if os.path.isfile(old_instance.profile_pic.path):
                            os.remove(old_instance.profile_pic.path)
                            print(f"✅ Deleted old profile picture: {old_instance.profile_pic.path}")
                except LabTechnologistProfile.DoesNotExist:
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
class BloodTestForm(forms.ModelForm):
    class Meta:
        model = BloodTest
        fields = [
            'blood_group',
            'hiv', 'hepatitis_b', 'hepatitis_c',
            'syphilis', 'malaria',
            'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'hiv': 'HIV Test',
            'hepatitis_b': 'Hepatitis B',
            'hepatitis_c': 'Hepatitis C',
        }
