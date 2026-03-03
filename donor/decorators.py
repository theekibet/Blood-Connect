# donor/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def username_required(view_func):
    """
    Decorator to ensure donor has set their username before accessing views.
    Redirects to username selection if still using email as username.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return redirect('donor:donorlogin')
        
        # Check if user has donor profile
        if not hasattr(request.user, 'donor'):
            messages.error(request, "Access denied. Donor profile not found.")
            return redirect('donor:donorlogin')
        
        # Check if username is still email (needs to choose username)
        if request.user.username == request.user.email:
            request.session['needs_username'] = True
            messages.info(request, "Please choose a username to continue.")
            return redirect('donor:choose-username')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def profile_complete_required(view_func):
    """
    Decorator to ensure donor has completed their profile before accessing views.
    Redirects to profile completion if required fields are missing.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # First check if authenticated
        if not request.user.is_authenticated:
            return redirect('donor:donorlogin')
        
        # Check if has donor profile
        if not hasattr(request.user, 'donor'):
            messages.error(request, "Access denied. Donor profile not found.")
            return redirect('donor:donorlogin')
        
        donor = request.user.donor
        
        # Check if username is set (first step)
        if request.user.username == request.user.email:
            request.session['needs_username'] = True
            return redirect('donor:choose-username')
        
        # Check required profile fields (excluding blood_group - it's optional)
        missing_fields = []
        if not donor.mobile:
            missing_fields.append('Mobile Number')
        if not donor.national_id:
            missing_fields.append('National ID')
        if not donor.county:
            missing_fields.append('County')
        if not donor.dob:
            missing_fields.append('Date of Birth')
        
        # If any required fields missing, redirect to profile edit
        if missing_fields:
            messages.warning(
                request, 
                f"Please complete your profile. Missing: {', '.join(missing_fields)}"
            )
            return redirect('donor:donor-edit-profile')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def onboarding_complete_required(view_func):
    """
    Comprehensive decorator that ensures both username is set AND profile is complete.
    This is the main decorator to use for dashboard and other protected views.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Authentication check
        if not request.user.is_authenticated:
            return redirect('donor:donorlogin')
        
        # Donor profile check
        if not hasattr(request.user, 'donor'):
            messages.error(request, "Access denied. Donor profile not found.")
            return redirect('donor:donorlogin')
        
        donor = request.user.donor
        
        # STEP 1: Check username (must be different from email)
        if request.user.username == request.user.email:
            request.session['needs_username'] = True
            request.session['onboarding_step'] = 'username'
            return redirect('donor:choose-username')
        
        # STEP 2: Check profile completion (required fields only)
        missing_fields = []
        if not donor.mobile:
            missing_fields.append('Mobile Number')
        if not donor.national_id:
            missing_fields.append('National ID')
        if not donor.county:
            missing_fields.append('County')
        if not donor.dob:
            missing_fields.append('Date of Birth')
        
        if missing_fields:
            request.session['onboarding_step'] = 'profile'
            messages.warning(
                request, 
                f"Please complete your profile to access the dashboard. Missing: {', '.join(missing_fields)}"
            )
            return redirect('donor:donor-edit-profile')
        
        # Clear onboarding flags if everything is complete
        if 'onboarding_step' in request.session:
            del request.session['onboarding_step']
        if 'needs_username' in request.session:
            del request.session['needs_username']
        
        return view_func(request, *args, **kwargs)
    
    return wrapper