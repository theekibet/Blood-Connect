from datetime import datetime, timedelta
import json
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.utils.safestring import mark_safe
from django.core.serializers.json import DjangoJSONEncoder
from django.views.decorators.http import require_GET
from phlebotomist.models import Phlebotomist, Appointment
from .models import Donor, DonorEligibility, BloodDonate
from blood.models import BloodDriveEvent, DonationCenter
from .forms import (
    DonorSignupForm, UsernameSelectionForm, DonorProfileForm, DonorEligibilityForm,
    BloodDonateForm, DonorLoginForm
)
from .decorators import username_required, onboarding_complete_required
from django.core.exceptions import PermissionDenied
from utils.models import Notification
from phlebotomist.forms import AppointmentForm
from datetime import date, time,time as datetime_time
import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.html import strip_tags
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.conf import settings
import re
import random
from blood.utils.notifications import create_notification

logger = logging.getLogger(__name__)

def get_available_time_slots(phlebotomist_id, appointment_date, duration_minutes=30):
    """
    Generate available time slots for a phlebotomist on a given date.
    
    Args:
        phlebotomist_id: ID of the phlebotomist
        appointment_date: Date object for the appointment
        duration_minutes: Slot duration (default 30 minutes)
    
    Returns:
        List of available time slots in format "HH:MM"
    """
    # Define working hours (8 AM to 5 PM)
    WORK_START = 8  # 8:00 AM
    WORK_END = 17   # 5:00 PM
    
    # Generate all possible slots
    all_slots = []
    current_time = datetime.combine(appointment_date, datetime_time(WORK_START, 0))
    end_time = datetime.combine(appointment_date, datetime_time(WORK_END, 0))
    
    while current_time < end_time:
        all_slots.append(current_time.strftime('%H:%M'))
        current_time += timedelta(minutes=duration_minutes)
    
    # Get booked slots
    booked_slots = Appointment.objects.filter(
        phlebotomist_id=phlebotomist_id,
        date__date=appointment_date,
    ).exclude(
        status__in=['cancelled', 'rejected']
    ).values_list('date', flat=True)
    
    # Convert booked datetimes to time strings
    booked_times = [dt.strftime('%H:%M') for dt in booked_slots]
    
    # Filter available slots
    available_slots = [slot for slot in all_slots if slot not in booked_times]
    
    logger.info(f"🔍 Phlebotomist {phlebotomist_id} on {appointment_date}:")
    logger.info(f"   Total slots: {len(all_slots)}, Booked: {len(booked_times)}, Available: {len(available_slots)}")
    
    return available_slots
def generate_username_suggestions(base_username, count=5):
    """
    Generate unique username suggestions based on the provided username.
    """
    suggestions = []
    base_clean = re.sub(r'[^a-zA-Z0-9]', '', base_username.lower())

    # Strategy 1: Add numbers
    for i in range(1, 20):
        suggestion = f"{base_clean}{i}"
        if not User.objects.filter(username=suggestion).exists():
            suggestions.append(suggestion)
            if len(suggestions) >= count:
                break

    # Strategy 2: Add suffixes
    if len(suggestions) < count:
        suffixes = ['_donor', '_blood', '_user', str(random.randint(100, 999)), str(random.randint(10, 99))]
        for suffix in suffixes:
            if len(suggestions) >= count:
                break
            suggestion = f"{base_clean}{suffix}"
            if not User.objects.filter(username=suggestion).exists():
                suggestions.append(suggestion)

    # Strategy 3: Add current year
    if len(suggestions) < count:
        year = datetime.now().year
        suggestion = f"{base_clean}{year}"
        if not User.objects.filter(username=suggestion).exists():
            suggestions.append(suggestion)

    # Strategy 4: Add keyword combinations
    if len(suggestions) < count:
        combo_suffixes = ['donor', 'blood', 'hero', 'saver', 'life']
        for suffix in combo_suffixes:
            if len(suggestions) >= count:
                break
            suggestion = f"{base_clean}_{suffix}"
            if not User.objects.filter(username=suggestion).exists():
                suggestions.append(suggestion)

    return suggestions[:count]


def check_profile_completion(donor):
    """
    Check if donor has completed required profile fields for donation.
    Blood group is now optional - not required for profile completion.
    Returns (is_complete, missing_fields)
    """
    missing_fields = []
    
    if not donor.mobile:
        missing_fields.append("Mobile Number")
    if not donor.national_id:
        missing_fields.append("National ID")
    if not donor.county:
        missing_fields.append("County")
    if not donor.dob:
        missing_fields.append("Date of Birth")
    
    is_complete = len(missing_fields) == 0
    return is_complete, missing_fields


def get_time_based_greeting(name):
    """Return greeting based on time of day"""
    from datetime import datetime
    current_hour = datetime.now().hour
    
    if current_hour < 12:
        return f"Good morning, {name}!"
    elif current_hour < 17:
        return f"Good afternoon, {name}!"
    elif current_hour < 21:
        return f"Good evening, {name}!"
    else:
        return f"Good night, {name}!"
    
    
def redirect_based_on_onboarding_status(request):
    """
    Helper function to redirect user based on their onboarding completion status.
    Returns appropriate redirect based on what step they're on.
    """
    user = request.user
    
    # Check if has donor profile
    if not hasattr(user, 'donor'):
        logout(request)
        messages.error(request, "Donor profile not found. Please sign up.")
        return redirect('donor:donorsignup')
    
    donor = user.donor
    
    # STEP 1: Check if username needs to be set
    if user.username == user.email:
        request.session['needs_username'] = True
        request.session['onboarding_step'] = 'username'
        request.session['onboarding_progress'] = 0
        messages.info(request, f"Welcome back! Please choose your username to continue.")
        return redirect('donor:choose-username')
    
    # STEP 2: Check if profile is complete
    is_complete, missing_fields = check_profile_completion(donor)
    
    if not is_complete:
        request.session['onboarding_step'] = 'profile'
        request.session['onboarding_progress'] = 50
        messages.warning(
            request,
            f"Please complete your profile. Missing: {', '.join(missing_fields)}"
        )
        return redirect('donor:donor-edit-profile')
    
    # STEP 3: Onboarding complete - go to dashboard
    # Clear any onboarding session variables
    for key in ['needs_username', 'onboarding_step', 'onboarding_progress']:
        if key in request.session:
            del request.session[key]
    
    messages.success(request, f"Welcome back, {user.first_name or user.username}!")
    return redirect('donor:donor-dashboard')

def check_dashboard_access(user):
    """
    Helper function to check dashboard access and provide appropriate context.
    Returns a dict with access info and suggestions.
    """
    try:
        donor = user.donor
        
        # Check eligibility
        try:
            eligibility = DonorEligibility.objects.get(donor=donor)
            is_eligible = eligibility.approved
        except DonorEligibility.DoesNotExist:
            is_eligible = None
        
        # Check if unsafe donor
        is_unsafe = BloodDonate.objects.filter(donor=donor, status='tested_unsafe').exists()
        
        context = {
            'show_eligibility_modal': is_eligible is None,
            'show_support_options': is_unsafe or (is_eligible is False),
            'volunteer_suggestions': [],
            'motivational_message': ''
        }
        
        # Add volunteer suggestions if can't donate
        if is_unsafe or (is_eligible is False):
            context['volunteer_suggestions'] = [
                {
                    'icon': 'fa-hands-helping',
                    'title': 'Volunteer at Blood Drives',
                    'description': 'Help organize and run blood donation events',
                    'url': 'donor:volunteer'
                },
                {
                    'icon': 'fa-share-alt',
                    'title': 'Spread Awareness',
                    'description': 'Share the importance of blood donation on social media',
                    'url': 'donor:share-impact'
                },
                {
                    'icon': 'fa-users',
                    'title': 'Recruit Donors',
                    'description': 'Encourage friends and family to donate',
                    'url': 'donor:impact'
                }
            ]
            
            if is_unsafe:
                context['motivational_message'] = "Thank you for your past contributions. There are still many ways you can help save lives!"
            else:
                context['motivational_message'] = "Everyone has a role in saving lives. Let's find yours!"
        
        return context
        
    except Exception as e:
        logger.error(f"Error in check_dashboard_access: {e}")
        return {
            'show_eligibility_modal': False,
            'show_support_options': False,
            'volunteer_suggestions': [],
            'motivational_message': ''
        }



@login_required(login_url='donor:donorlogin')
def choose_username_view(request):
    """
    First-time donors choose their permanent username.
    Only accessible if username is still set to email.
    """
    user = request.user
    
    # Check if user actually needs to set username
    if user.username != user.email:
        # Username already set, redirect based on profile completion
        return redirect_based_on_onboarding_status(request)
    
    # Ensure has donor profile
    if not hasattr(user, 'donor'):
        messages.error(request, "Donor profile not found.")
        logout(request)
        return redirect('donor:donorsignup')
    
    # Get user's first name
    first_name = user.first_name or "there"
    
    logger.debug(f"🔍 Username view - User: {user.username}")
    logger.debug(f"   First name from user: '{user.first_name}'")
    logger.debug(f"   First name variable: '{first_name}'")
    
    # Generate username suggestions
    base_name = f"{user.first_name}{user.last_name}".lower()
    suggestions = generate_username_suggestions(base_name, count=8)
    
    if request.method == 'POST':
        form = UsernameSelectionForm(request.POST, user=user)
        
        if form.is_valid():
            new_username = form.cleaned_data['username']
            
            # Update username
            user.username = new_username
            user.save()
            
            logger.info(f"✅ Username updated to: {new_username}")
            
            # Clear username flag, update session
            if 'needs_username' in request.session:
                del request.session['needs_username']
            request.session['onboarding_step'] = 'profile'
            request.session['onboarding_progress'] = 50
            
            messages.success(
                request,
                f"✨ Great choice, {first_name}! Now let's complete your profile."
            )
            
            return redirect('donor:donor-edit-profile')
        else:
            # If username taken, generate new suggestions
            if 'username' in form.errors:
                taken_username = form.data.get('username', '')
                if taken_username:
                    suggestions = generate_username_suggestions(taken_username, count=8)
    else:
        form = UsernameSelectionForm(user=user)
    
    context = {
        'form': form,
        'suggestions': suggestions,
        'email': user.email,
        'first_name': first_name,
        'time_greeting': get_time_based_greeting(first_name),
        'user': user,
    }
    return render(request, 'donor/choose_username.html', context)

# -------------------------------
# After Signup - Redirect to Edit Profile
# -------------------------------
def donor_signup_view(request):
    """
    Donor signup - collects minimal data (name, email, password).
    Username is set to email temporarily until they choose one.
    User is auto-logged in after signup and redirected to username selection.
    """
    if request.user.is_authenticated:
        return redirect_based_on_onboarding_status(request)
    
    if request.method == 'POST':
        form = DonorSignupForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Extract form data
                    email = form.cleaned_data.get('email').lower()
                    password = form.cleaned_data.get('password1')
                    first_name = form.cleaned_data.get('first_name').strip().title()
                    last_name = form.cleaned_data.get('last_name').strip().title()
                    
                    # Create user with email as temporary username
                    user = User.objects.create_user(
                        username=email,  # Temporary - will be changed during onboarding
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                        is_active=True
                    )
                    
                    logger.info(f"✅ User created: {user.username}")
                    logger.info(f"   First name: {user.first_name}")
                    logger.info(f"   Last name: {user.last_name}")
                    
                    # Create donor profile with minimal data
                    donor = Donor.objects.create(
                        user=user,
                        # All other fields will be filled during onboarding
                    )
                    
                    logger.info(f"✅ Donor profile created for {user.username}")
                    
                    # Add to donor group
                    donor_group, created = Group.objects.get_or_create(name='DONOR')
                    user.groups.add(donor_group)
                
                # CRITICAL FIX: Move login and session management outside transaction
                # Clear any existing session data before login
                request.session.flush()
                
                # Auto-login the user
                login(request, user, backend='donor.backends.EmailOrUsernameBackend')
                
                # Set onboarding flags AFTER login completes
                request.session['needs_username'] = True
                request.session['onboarding_step'] = 'username'
                request.session['onboarding_progress'] = 0
                request.session.modified = True  # Mark session as modified
                
                messages.success(
                    request,
                    f"🎉 Welcome, {first_name}! Let's set up your account."
                )
                
                # Redirect to username selection
                return redirect('donor:choose-username')
                    
            except Exception as e:
                logger.error(f"❌ Signup error: {str(e)}", exc_info=True)
                messages.error(request, "An error occurred during signup. Please try again.")
        else:
            # Form has errors
            logger.error(f"❌ Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = DonorSignupForm()
    
    context = {
        'form': form,
        'page_title': 'Donor Signup',
    }
    return render(request, 'donor/donorsignup.html', context)

def donorlogin_view(request):
    """
    Login view - supports login with BOTH username and email.
    Uses custom authentication backend (EmailOrUsernameBackend).
    Redirects based on onboarding status.
    """
    if request.user.is_authenticated:
        return redirect_based_on_onboarding_status(request)
    
    if request.method == 'POST':
        form = DonorLoginForm(request.POST)
        
        if form.is_valid():
            username_or_email = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            # Authenticate using custom backend (works with username OR email)
            user = authenticate(request, username=username_or_email, password=password)
            
            if user is not None:
                # Check if user has donor profile
                if hasattr(user, 'donor'):
                    login(request, user)
                    
                    logger.info(f"✅ User logged in: {user.username}")
                    logger.info(f"   First name: '{user.first_name}'")
                    logger.info(f"   Last name: '{user.last_name}'")
                    
                    # Redirect based on onboarding status
                    return redirect_based_on_onboarding_status(request)
                else:
                    messages.error(request, "This account is not registered as a donor.")
            else:
                messages.error(request, "Invalid username/email or password.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = DonorLoginForm()
    
    context = {
        'form': form,
        'page_title': 'Donor Login',
    }
    return render(request, 'donor/donorlogin.html', context)

def get_donor_engagement_path(user):
    """
    Determines the appropriate engagement path for a donor.
    Returns a dictionary with engagement recommendations.
    """
    try:
        donor = Donor.objects.get(user=user)
    except Donor.DoesNotExist:
        return {'path': 'complete_profile', 'redirect': 'donor-profile'}
    
    # Check if eligibility form exists
    eligibility_exists = DonorEligibility.objects.filter(donor=donor).exists()
    
    if not eligibility_exists:
        # New donor - show dashboard with awareness modal
        return {
            'path': 'new_donor',
            'show_awareness_modal': True,
            'redirect': None  # Stay on dashboard
        }
    
    # Has eligibility form - check if approved
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
        if eligibility.approved:
            return {
                'path': 'eligible_donor',
                'can_donate': True,
                'redirect': None
            }
        else:
            return {
                'path': 'non_eligible_donor',
                'can_donate': False,
                'show_support_options': True,
                'redirect': None
            }
    except DonorEligibility.DoesNotExist:
        return {
            'path': 'new_donor',
            'show_awareness_modal': True,
            'redirect': None
        }

def needs_eligibility_check(user):
    """
    UPDATED: Now returns False for new donors - they can access dashboard with awareness modal.
    Only redirects if there's a specific reason to force eligibility completion.
    """
    try:
        donor = Donor.objects.get(user=user)
    except Donor.DoesNotExist:
        return False
    
    # Check if eligibility form exists
    eligibility_exists = DonorEligibility.objects.filter(donor=donor).exists()
    
    # NEW LOGIC: Don't force redirect, just track status for UI
    return False  # Never force redirect - let dashboard handle UX

def should_show_eligibility_modal(user):
    """
    Determines if the eligibility awareness modal should be shown.
    Shows for new donors who haven't completed eligibility form.
    """
    try:
        donor = Donor.objects.get(user=user)
        eligibility_exists = DonorEligibility.objects.filter(donor=donor).exists()
        
        # Show modal for new donors (no eligibility form)
        return not eligibility_exists
    except Donor.DoesNotExist:
        return False

def get_donor_eligibility_status(user):
    """
    Returns detailed eligibility status for dashboard display.
    """
    status = {
        'has_profile': False,
        'has_eligibility': False,
        'is_eligible': False,
        'can_donate': False,
        'needs_eligibility_form': False,
        'show_support_options': False,
        'eligibility_reasons': [],
        'support_options': []
    }
    
    try:
        donor = Donor.objects.get(user=user)
        status['has_profile'] = True
        
        # Check eligibility
        try:
            eligibility = DonorEligibility.objects.get(donor=donor)
            status['has_eligibility'] = True
            status['is_eligible'] = eligibility.approved
            
            if eligibility.approved:
                # Check if they can donate now (waiting period)
                from datetime import date, timedelta
                if donor.last_donation_date:
                    next_date = donor.last_donation_date + timedelta(days=56)
                    status['can_donate'] = date.today() >= next_date
                else:
                    status['can_donate'] = True  # First-time eligible donor
            else:
                status['show_support_options'] = True
                
        except DonorEligibility.DoesNotExist:
            status['needs_eligibility_form'] = True
            status['show_support_options'] = True  # Show support options for new donors
            
    except Donor.DoesNotExist:
        pass
    
    return status

def get_volunteer_suggestions(user):
    """
    Returns volunteer opportunities based on donor status.
    """
    suggestions = [
        {
            'title': 'Blood Drive Ambassador',
            'description': 'Organize blood drives in your community',
            'icon': 'fa-flag',
            'url': '/volunteer/blood-drive/',
            'for_anyone': True
        },
        {
            'title': 'Social Media Advocate',
            'description': 'Share donation stories and urgent needs',
            'icon': 'fa-share-alt',
            'url': '/volunteer/advocate/',
            'for_anyone': True
        },
        {
            'title': 'Transportation Volunteer',
            'description': 'Help donors get to donation centers',
            'icon': 'fa-truck',
            'url': '/volunteer/transport/',
            'for_anyone': True
        },
        {
            'title': 'Administrative Support',
            'description': 'Help with paperwork and coordination',
            'icon': 'fa-file-signature',
            'url': '/volunteer/admin/',
            'for_anyone': True
        },
    ]
    
    # Add donor-specific suggestions if they're eligible
    try:
        donor = Donor.objects.get(user=user)
        
        # Check if eligibility exists
        try:
            eligibility = DonorEligibility.objects.get(donor=donor)
            if eligibility.approved:
                suggestions.append({
                    'title': 'Become a Mentor',
                    'description': 'Guide new donors through their first donation',
                    'icon': 'fa-chalkboard-teacher',
                    'url': '/volunteer/mentor/',
                    'for_anyone': False
                })
        except DonorEligibility.DoesNotExist:
            # Donor doesn't have eligibility record yet
            pass
            
    except Donor.DoesNotExist:
        # User is not a donor
        pass
    
    return suggestions


# -------------------------------
# Eligibility
# -------------------------------
@login_required(login_url='donor:donorlogin')
@username_required
def donor_eligibility_view(request):
    """
    Enhanced donor eligibility view with REAL-WORLD blood donation criteria.
    """
    donor = get_object_or_404(Donor, user=request.user)

    # CRITICAL: Check if donor has DOB
    if not donor.dob:
        messages.error(
            request, 
            "Please complete your profile with your date of birth before checking eligibility."
        )
        return redirect('donor:donor-profile')

    # Check if eligibility already exists
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
        messages.info(request, "You've already completed the eligibility form. View your status below.")
        return redirect('donor:donor-eligibility-status')
    except DonorEligibility.DoesNotExist:
        eligibility = None

    # Calculate age from donor's DOB
    age = DonorEligibilityForm.calculate_age(donor.dob)

    if request.method == 'POST':
        form = DonorEligibilityForm(request.POST, instance=eligibility, donor=donor)
        if form.is_valid():
            try:
                with transaction.atomic():
                    eligibility_instance = form.save(commit=False)
                    eligibility_instance.donor = donor
                    
                    # CRITICAL FIX: Explicitly set the age field
                    eligibility_instance.age = age
                    
                    # Get all form data
                    weight = eligibility_instance.weight
                    good_health = bool(eligibility_instance.good_health)
                    travel_history = bool(eligibility_instance.travel_history)
                    
                    # Get additional fields from form
                    recent_surgery = form.cleaned_data.get('recent_surgery', False)
                    recent_tattoo = form.cleaned_data.get('recent_tattoo', False)
                    recent_childbirth = form.cleaned_data.get('recent_childbirth', False)
                    breastfeeding = form.cleaned_data.get('breastfeeding', False)
                    medications = form.cleaned_data.get('medications', '')
                    medical_conditions = form.cleaned_data.get('medical_conditions', '')
                    pregnant = form.cleaned_data.get('pregnant', False)
                    
                    # ==========================================
                    # ELIGIBILITY CRITERIA
                    # ==========================================
                    
                    reasons = []
                    recommendations = []
                    is_eligible = True
                    
                    # 1. AGE CHECK
                    if age < 16:
                        reasons.append(f"• Minimum age requirement: 16 years (you are {age} years old)")
                        recommendations.append("You can register to donate when you turn 16.")
                        is_eligible = False
                    elif age > 65:
                        reasons.append(f"• Donors over 65 need physician approval (you are {age} years old)")
                        recommendations.append("Please consult your doctor and bring a medical clearance note.")
                        is_eligible = False
                    
                    # 2. WEIGHT CHECK
                    if weight < 50:
                        reasons.append(f"• Minimum weight requirement: 50kg (you entered {weight}kg)")
                        recommendations.append("Focus on healthy weight gain through balanced nutrition.")
                        is_eligible = False
                    
                    # 3. HEALTH STATUS
                    if not good_health:
                        reasons.append("• You must be in good health on the day of donation")
                        recommendations.append("Wait until you're fully recovered from any illness.")
                        is_eligible = False
                    
                    # 4. TATTOO/PERCING
                    if recent_tattoo:
                        reasons.append("• Recent tattoo/piercing requires 6-month waiting period")
                        recommendations.append("You can donate 6 months after getting a tattoo/piercing.")
                        is_eligible = False
                    
                    # 5. SURGERY
                    if recent_surgery:
                        reasons.append("• Recent surgery requires waiting period (usually 3-12 months)")
                        recommendations.append("Consult with our medical staff about your specific surgery.")
                        is_eligible = False
                    
                    # 6. PREGNANCY
                    if pregnant:
                        reasons.append("• Pregnancy temporarily prevents blood donation")
                        recommendations.append("You can donate 6 weeks after pregnancy ends.")
                        is_eligible = False
                    
                    # Set eligibility
                    eligibility_instance.approved = is_eligible
                    eligibility_instance.save()

                    # Messages and notifications
                    if is_eligible:
                        messages.success(
                            request, 
                            "✅ Great news! Based on your responses, you appear eligible to donate blood."
                        )
                    else:
                        messages.info(
                            request,
                            "🌟 You can still be a hero! While you may have temporary deferrals, there are many other ways to support our mission."
                        )
                        
                        if reasons:
                            messages.warning(
                                request,
                                "📋 Reasons for deferral:\n" + "\n".join(reasons[:3])
                            )
                        
                        if recommendations:
                            messages.info(
                                request,
                                "💡 Recommendations:\n" + "\n".join(recommendations[:2])
                            )

                    return redirect('donor:donor-eligibility-status')
                    
            except Exception as e:
                logger.error(f"Eligibility save error: {str(e)}")
                messages.error(request, "An error occurred while saving. Please try again.")
        else:
            error_count = len(form.errors)
            messages.error(
                request, 
                f"⚠️ Please correct the {error_count} error(s) highlighted below."
            )
    else:
        form = DonorEligibilityForm(instance=eligibility, donor=donor)

    context = {
        'eligibility_form': form,
        'donor_age': age,
        'is_first_time': eligibility is None,
        'donor': donor,
    }
    
    return render(request, 'donor/donor_eligibility_form.html', context)

# -------------------------------
# Eligibility status badge
# -------------------------------   
@login_required(login_url='donor:donorlogin')
@username_required
def donor_eligibility_status_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        # No eligibility record
        context = {
            'status': 'no_record',
            'badge_type': 'secondary',
            'badge_text': '📋 NOT STARTED',
            'badge_icon': 'fa-clipboard-list',
            'badge_color': 'bg-secondary',
            'title': 'Eligibility Check Not Started',
            'message': "You haven't completed your eligibility assessment yet.",
            'main_action_text': 'Start Assessment',
            'main_action_url': 'donor:donor-eligibility',
            'secondary_action_text': 'Learn About Eligibility',
            'secondary_action_url': 'donor:faqs',
            'show_support_options': True,
        }
        return render(request, 'donor/donor_eligibility_status.html', context)

    age = DonorEligibilityForm.calculate_age(donor.dob) if donor.dob else None
    
    # Get all eligibility details
    is_eligible = eligibility.approved
    
    # Prepare eligibility details for display
    eligibility_details = {
        'age': age,
        'weight': eligibility.weight,
        'gender': eligibility.get_gender_display() if hasattr(eligibility, 'get_gender_display') else eligibility.gender,
        'good_health': 'Yes' if eligibility.good_health else 'No',
        'travel_history': 'Yes' if eligibility.travel_history else 'No',
        'medical_conditions': eligibility.medical_conditions or 'None reported',
        'submitted_on': eligibility.updated_at.strftime("%B %d, %Y") if hasattr(eligibility, 'updated_at') else 'N/A',
        'last_updated': eligibility.updated_at.strftime("%B %d, %Y") if hasattr(eligibility, 'updated_at') else 'N/A',
    }
    
    if is_eligible:
        # Check if they can donate now (waiting period)
        from datetime import date, timedelta
        can_donate_now = True
        wait_message = None
        next_date = None
        
        if donor.last_donation_date:
            next_date = donor.last_donation_date + timedelta(days=56)
            today = date.today()
            if today < next_date:
                can_donate_now = False
                days_left = (next_date - today).days
                wait_message = f"Next eligible donation: {next_date.strftime('%b %d, %Y')} ({days_left} days)"
        
        context = {
            'status': 'eligible',
            'badge_type': 'success',
            'badge_text': '✅ ELIGIBLE DONOR',
            'badge_icon': 'fa-certificate',
            'badge_color': 'bg-success',
            'title': 'Congratulations! You Are Eligible to Donate Blood',
            'message': 'Based on your responses, you meet all the criteria for blood donation. Your generosity can save up to 3 lives with each donation!',
            'can_donate_now': can_donate_now,
            'wait_message': wait_message,
            'next_donation_date': next_date.strftime("%B %d, %Y") if next_date else None,
            'main_action_text': 'Schedule Donation',
            'main_action_url': 'donor:donate-blood',
            'secondary_action_text': 'View Donation History',
            'secondary_action_url': 'donor:donation-history',
            'eligibility_details': eligibility_details,
            'show_verification_option': not donor.bloodgroup_verified,
            'show_contact_option': True,
        }
    else:
        # Get specific reasons from the eligibility record
        reasons = []
        recommendations = []
        
        if age and age < 16:
            reasons.append("• Minimum age requirement: 16 years")
            recommendations.append("You'll be eligible when you turn 16.")
        elif age and age > 65:
            reasons.append("• Donors over 65 need physician approval")
            recommendations.append("Please bring a doctor's note if you wish to donate.")
        
        if eligibility.weight < 50:
            reasons.append(f"• Minimum weight: 50kg (your weight: {eligibility.weight}kg)")
            recommendations.append("Focus on healthy weight gain through balanced nutrition.")
        
        if not eligibility.good_health:
            reasons.append("• You indicated you're not in good health")
            recommendations.append("Please donate when you're feeling well.")
        
        if eligibility.travel_history:
            reasons.append("• Recent travel may require waiting period")
            recommendations.append("Travel to certain areas requires a waiting period (usually 6 months).")
        
        # Default reasons if none captured
        if not reasons:
            reasons.append("• Based on your responses, you have temporary or permanent deferrals")
            recommendations.append("Please review the guidelines below or contact us for clarification.")
        
        context = {
            'status': 'not_eligible',
            'badge_type': 'warning',
            'badge_text': '⚠️ DEFERRED',
            'badge_icon': 'fa-clock',
            'badge_color': 'bg-warning text-dark',
            'title': 'Thank You for Your Interest!',
            'message': 'While you may not be eligible to donate blood at this time, there are many other ways to support our mission and save lives.',
            'reasons': reasons,
            'recommendations': recommendations,
            'main_action_text': 'Explore Volunteer Options',
            'main_action_url': 'donor:volunteer',
            'secondary_action_text': 'Health Tips',
            'secondary_action_url': 'donor:health-tips',
            'eligibility_details': eligibility_details,
            'show_verification_option': not donor.bloodgroup_verified and age and age >= 16,
            'show_contact_option': True,
        }
    
    # Add common context
    context.update({
        'donor': donor,
        'eligibility': eligibility,
        'last_updated': eligibility.updated_at.strftime("%B %d, %Y") if hasattr(eligibility, 'updated_at') else 'N/A',
        'show_support_options': True,
        'contact_email': 'support@bloodconnect.org',
        'contact_phone': '+254 700 123 456',
        'nearest_center_url': 'donor:nearby-centers',
    })
    
    return render(request, 'donor/donor_eligibility_status.html', context)

# -------------------------------
# Dashboard
# -------------------------------
@login_required(login_url='donor:donorlogin')
@onboarding_complete_required  # This ensures username AND profile are complete
def donor_dashboard_view(request):
    """
    Main donor dashboard - only accessible after completing onboarding.
    Blood group is optional and does not block dashboard access.
    """
    user = request.user
    logger.debug(f"Accessing donor dashboard for user '{user.username}'")

    # Get donor profile (onboarding_complete_required ensures this exists)
    donor = user.donor
    
    # Check if user just completed onboarding (for welcome message)
    just_completed = request.session.pop('just_completed_onboarding', False)
    
    # Get dashboard access context from helper function
    access_context = check_dashboard_access(user)

    # ==========================================
    # DETERMINE DONOR SAFETY STATUS
    # ==========================================
    unsafe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_unsafe'
    ).first()
    
    safe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_safe'
    ).first()
    
    pending_tests = BloodDonate.objects.filter(
        donor=donor,
        status='collected'
    ).count()
    
    safe_count = BloodDonate.objects.filter(donor=donor, status='tested_safe').count()
    unsafe_count = BloodDonate.objects.filter(donor=donor, status='tested_unsafe').count()
    
    is_unsafe_donor = unsafe_donation is not None
    is_safe_donor = safe_donation is not None
    is_first_time_donor = not BloodDonate.objects.filter(donor=donor).exists()
    
    logger.info(f"Donor {donor.id} dashboard: unsafe={is_unsafe_donor}, safe={is_safe_donor}, first_time={is_first_time_donor}")

    # ==========================================
    # GET UNSAFE REASON - FIX FOR MISSING FIELD
    # ==========================================
    unsafe_reason = None
    if unsafe_donation:
        try:
            # Try to get reason from related LabTest model
            from blood.models import LabTest
            
            lab_test = LabTest.objects.filter(
                donation=unsafe_donation,
                result='unsafe'
            ).order_by('-tested_at').first()
            
            if lab_test:
                # Try different possible field names
                if hasattr(lab_test, 'unsafe_reason'):
                    unsafe_reason = lab_test.unsafe_reason
                elif hasattr(lab_test, 'reason'):
                    unsafe_reason = lab_test.reason
                elif hasattr(lab_test, 'notes'):
                    unsafe_reason = lab_test.notes
                elif hasattr(lab_test, 'remarks'):
                    unsafe_reason = lab_test.remarks
                else:
                    unsafe_reason = "Medical reasons - please contact us for details"
            else:
                # No lab test found, check if donation has notes
                if hasattr(unsafe_donation, 'collection_notes') and unsafe_donation.collection_notes:
                    unsafe_reason = unsafe_donation.collection_notes
                elif hasattr(unsafe_donation, 'phlebotomist_notes') and unsafe_donation.phlebotomist_notes:
                    unsafe_reason = unsafe_donation.phlebotomist_notes
                else:
                    unsafe_reason = "Medical reasons - please contact us for details"
        except ImportError:
            logger.warning("LabTest model not found, using default unsafe reason")
            unsafe_reason = "Medical reasons - please contact us for details"
        except Exception as e:
            logger.warning(f"Could not get unsafe reason: {e}")
            unsafe_reason = "Medical reasons - please contact us for details"

    # ==========================================
    # ENHANCED GREETING SYSTEM
    # ==========================================
    try:
        from blood.utils.greetings import get_donor_greeting
        last_donation_for_greeting = BloodDonate.objects.filter(
            donor=donor, 
            status__in=['approved', 'completed', 'tested_safe', 'tested_unsafe']
        ).order_by('-date').first()
        
        from phlebotomist.models import Appointment
        upcoming_appointments = Appointment.objects.filter(
            donor=donor,
            date__gte=timezone.now(),
            status='scheduled'
        ).order_by('date')[:3]
        
        greeting_data = get_donor_greeting(
            donor=donor,
            last_donation=last_donation_for_greeting,
            upcoming_appointments=upcoming_appointments
        )
        
        # Add onboarding celebration if just completed
        if just_completed:
            greeting_data['celebration'] = True
            greeting_data['message'] = "🎉 You're all set! Welcome to your dashboard."
            
    except ImportError:
        # Fallback greeting
        if just_completed:
            greeting_message = f"Welcome to your dashboard, {donor.user.username}! 🎉"
            context_message = "Your profile is complete. You're ready to start your donation journey!"
            icon = "🎉"
        elif is_unsafe_donor:
            greeting_message = f"Hello {donor.user.first_name or 'donor'}"
            context_message = "We appreciate your past donations. Let's discuss your next steps."
            icon = "🤝"
        elif is_safe_donor:
            greeting_message = f"Welcome back, hero! 🦸"
            context_message = "Thank you for your life-saving donations!"
            icon = "🦸"
        else:
            greeting_message = f"Welcome, {donor.user.first_name or 'new donor'}! 👋"
            context_message = "Everyone has a role in saving lives. Let's find yours!"
            icon = "🌟"
            
        greeting_data = {
            'greeting': greeting_message,
            'context_message': context_message,
            'user_type': 'donor',
            'icon': icon,
            'is_hero': safe_count >= 1,
            'profile_pic': donor.profile_pic.url if donor.profile_pic and hasattr(donor.profile_pic, 'url') else None,
            'celebration': just_completed
        }

    # ==========================================
    # LAST DONATION & NEXT ELIGIBILITY
    # ==========================================
    last_donation = BloodDonate.objects.filter(
        donor=donor, 
        status__in=['approved', 'completed', 'tested_safe']
    ).order_by('-date').first()

    if last_donation:
        last_donation_date = last_donation.date.date() if hasattr(last_donation.date, 'date') else last_donation.date
        
        if not donor.last_donation_date or donor.last_donation_date < last_donation_date:
            donor.last_donation_date = last_donation_date
            donor.save(update_fields=['last_donation_date'])
            logger.debug(f"Updated last_donation_date for donor {donor.id}")

        next_donation_date = donor.next_eligible_donation_date()
        days_until_next = donor.days_until_next_donation()
        next_donation_date_iso = next_donation_date.isoformat() if next_donation_date else None
    else:
        next_donation_date = None
        days_until_next = 0
        next_donation_date_iso = None

    # ==========================================
    # TOTAL POINTS & DONATIONS
    # ==========================================
    total_safe_donations = BloodDonate.objects.filter(
        donor=donor,
        status='tested_safe'
    ).count()
    
    points_per_donation = 10
    computed_points = total_safe_donations * points_per_donation

    if donor.points != computed_points:
        donor.points = computed_points
        donor.save(update_fields=['points'])
        logger.debug(f"Updated points to {computed_points} for donor {donor.id}")

    # ==========================================
    # PROGRESS VISUALIZATION
    # ==========================================
    goal = 10
    progress = min(int((total_safe_donations / goal) * 100), 100) if goal else 0
    circumference = 2 * 3.1416 * 65
    stroke_dashoffset = circumference * (1 - progress / 100)

    # ==========================================
    # INFO CARDS
    # ==========================================
    info_cards = [
        {'icon': 'fa-heartbeat', 'title': 'Health Tips', 'desc': 'Stay hydrated and eat healthy foods before donating blood.', 'url': 'health-tips', 'color': 'primary'},
        {'icon': 'fa-question-circle', 'title': 'FAQs', 'desc': 'Find answers to common questions about blood donation.', 'url': 'faqs', 'color': 'info'},
        {'icon': 'fa-comments', 'title': 'Donor Advice', 'desc': 'How to prepare for your next donation and what to expect.', 'url': 'donor-advice', 'color': 'success'},
        {'icon': 'fa-book', 'title': 'Donor Resources', 'desc': 'Learn more about blood donation processes and guidelines.', 'url': 'donor-resources', 'color': 'warning'},
    ]

    # ==========================================
    # RECENT DONATIONS WITH STATUS
    # ==========================================
    recent_donations = BloodDonate.objects.filter(donor=donor).select_related('donation_center').order_by('-date')[:5]
    
    for donation in recent_donations:
        if donation.status == 'tested_safe':
            donation.display_result = 'safe'
            donation.result_badge = 'success'
        elif donation.status == 'tested_unsafe':
            donation.display_result = 'unsafe'
            donation.result_badge = 'danger'
        elif donation.status == 'collected':
            donation.display_result = 'pending_test'
            donation.result_badge = 'info'
        else:
            donation.display_result = 'pending'
            donation.result_badge = 'warning'

    # ==========================================
    # ELIGIBILITY STATUS
    # ==========================================
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
        is_eligible = eligibility.approved
        eligibility_completed = True
    except DonorEligibility.DoesNotExist:
        is_eligible = False
        eligibility_completed = False

    can_donate_now = is_eligible and not is_unsafe_donor and (days_until_next == 0 or is_first_time_donor)

    # ==========================================
    # MILESTONES
    # ==========================================
    milestones = [5, 10, 25, 50, 100]
    next_milestone = next((m for m in milestones if total_safe_donations < m), None)
    donations_to_milestone = next_milestone - total_safe_donations if next_milestone else 0

    # ==========================================
    # UPCOMING APPOINTMENTS
    # ==========================================
    try:
        from phlebotomist.models import Appointment
        upcoming_appointments = Appointment.objects.filter(
            donor=donor,
            date__gte=timezone.now(),
            status='scheduled'
        ).select_related('phlebotomist', 'phlebotomist__donation_center').order_by('date')[:3]
    except:
        upcoming_appointments = []

    # ==========================================
    # HERO STATUS & BADGES
    # ==========================================
    hero_level = "Bronze"
    hero_badge = None
    
    if total_safe_donations >= 10:
        hero_level = "Gold"
        hero_badge = "🏆"
    elif total_safe_donations >= 5:
        hero_level = "Silver"
        hero_badge = "🥈"
    elif total_safe_donations >= 1:
        hero_level = "Bronze"
        hero_badge = "🥉"
    
    if total_safe_donations >= 1 and 'is_hero' not in greeting_data:
        greeting_data['is_hero'] = True
    if hero_badge and 'hero_badge' not in greeting_data:
        greeting_data['hero_badge'] = hero_badge
        greeting_data['hero_level'] = hero_level

    # ==========================================
    # PREPARE METADATA FOR GREETING CARD
    # ==========================================
    meta_items = []
    if hasattr(donor, 'bloodgroup') and donor.bloodgroup:
        meta_items.append({
            'icon': 'fas fa-tint',
            'text': f"Blood Group: {donor.bloodgroup}"
        })
    else:
        meta_items.append({
            'icon': 'fas fa-question-circle',
            'text': "Blood Group: Unknown (Optional)",
            'color': 'text-info'
        })
    
    meta_items.append({
        'icon': 'fas fa-heart',
        'text': f"{total_safe_donations} safe donations"
    })
    
    if is_unsafe_donor:
        meta_items.append({
            'icon': 'fas fa-exclamation-triangle',
            'text': "Contact Required",
            'color': 'text-danger'
        })
    else:
        meta_items.append({
            'icon': 'fas fa-trophy',
            'text': f"{hero_level} Hero"
        })
    
    if 'meta_items' not in greeting_data and meta_items:
        greeting_data['meta_items'] = meta_items

    # ==========================================
    # QUICK ACTION BUTTONS
    # ==========================================
    quick_actions = [
        {
            'url': 'donor:donor-eligibility',
            'icon': 'fa-clipboard-check',
            'text': 'Check Eligibility',
            'color': 'primary',
            'show': not eligibility_completed
        },
        {
            'url': 'donor:donate-blood',
            'icon': 'fa-hand-holding-heart',
            'text': 'Schedule Donation',
            'color': 'success',
            'show': can_donate_now
        },
        {
            'url': 'donor:volunteer',
            'icon': 'fa-hands-helping',
            'text': 'Volunteer Opportunities',
            'color': 'info',
            'show': not can_donate_now or is_unsafe_donor
        },
        {
            'url': 'donor:events',
            'icon': 'fa-calendar-alt',
            'text': 'Find Events',
            'color': 'warning',
            'show': True
        },
    ]
    
    # Add "Find Blood Type" button only if blood group not set
    if not donor.bloodgroup:
        quick_actions.append({
            'url': '#',  # Replace with actual URL
            'icon': 'fa-question-circle',
            'text': 'Learn Your Blood Type',
            'color': 'info',
            'show': True
        })

    # ==========================================
    # NOTIFICATION COUNT
    # ==========================================
    notification_count = 0
    if hasattr(donor, 'id'):
        try:
            donor_content_type = ContentType.objects.get_for_model(Donor)
            notification_count = Notification.objects.filter(
                recipient_content_type=donor_content_type,
                recipient_object_id=donor.id,
                is_read=False
            ).count()
        except:
            notification_count = 0

    # ==========================================
    # BUILD COMPREHENSIVE CONTEXT
    # ==========================================
    context = {
        'user': user,
        'donor': donor,
        'points': donor.points,
        'total_safe_donations': total_safe_donations,
        'total_unsafe_donations': unsafe_count,
        'pending_tests': pending_tests,
        'goal': goal,
        'progress': progress,
        'stroke_dashoffset': stroke_dashoffset,
        'next_donation_date': next_donation_date.strftime("%b %d, %Y") if next_donation_date else None,
        'days_until_next': days_until_next,
        'next_donation_date_iso': next_donation_date_iso,
        'can_donate_now': can_donate_now,
        'is_eligible': is_eligible,
        'is_unsafe_donor': is_unsafe_donor,
        'is_safe_donor': is_safe_donor,
        'is_first_time_donor': is_first_time_donor,
        'info_cards': info_cards,
        'recent_donations': recent_donations,
        'upcoming_appointments': upcoming_appointments,
        'next_milestone': next_milestone,
        'donations_to_milestone': donations_to_milestone,
        'last_donation_date': donor.last_donation_date,
        'hero_level': hero_level,
        'hero_badge': hero_badge,
        'greeting_data': greeting_data,
        'current_date': timezone.now().date(),
        'unsafe_reason': unsafe_reason,  # FIXED: Use the variable we created above instead of unsafe_donation.unsafe_reason
        'just_completed_onboarding': just_completed,
        
        # INCLUSIVE MESSAGING FEATURES
        'eligibility_completed': eligibility_completed,
        'show_eligibility_modal': access_context.get('show_eligibility_modal', False),
        'show_support_options': access_context.get('show_support_options', False),
        'support_options_heading': "Everyone Has a Role in Saving Lives",
        'support_options_message': "Whether you're eligible to donate or not, you can still make a meaningful impact.",
        'volunteer_suggestions': access_context.get('volunteer_suggestions', []),
        'motivational_message': access_context.get('motivational_message', ''),
        'quick_actions': quick_actions,
        'donor_unread_notification_count': notification_count,
        'donor_support_options': access_context.get('volunteer_suggestions', []),
        'donor_dashboard_stats': {
            'total_safe_donations': total_safe_donations,
            'total_points': donor.points,
            'blood_group': donor.bloodgroup,
            'blood_group_verified': donor.bloodgroup_verified,
            'hero_level': hero_level,
        }
    }

    logger.debug(f"Rendering donor dashboard for user '{user.username}' with {total_safe_donations} safe donations and {donor.points} points")
    return render(request, 'donor/donor_dashboard.html', context)

# -------------------------------
# DonateBloodView - COMPLETE UPDATED VERSION
# -------------------------------
# -------------------------------
# DonateBloodView - COMPLETE UPDATED VERSION WITH REVIEW TRIGGER
# -------------------------------
@login_required(login_url='donor:donorlogin')
@username_required
def donate_blood_view(request):
    """
    View for donors to schedule blood donation appointments.
    Now includes double-booking prevention with real-time availability checking
    and triggers review prompt after successful booking.
    """
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "⚠️ You must complete your donor profile before donating blood.")
        return redirect('donor:donor-profile')

    # ==========================================
    # CHECK PROFILE COMPLETION FIRST
    # ==========================================
    is_profile_complete, missing_fields = check_profile_completion(donor)
    
    if not is_profile_complete:
        messages.error(
            request, 
            f"⚠️ Please complete your donor profile before scheduling a donation. Missing: {', '.join(missing_fields)}"
        )
        return redirect('donor:donor-profile')

    # ==========================================
    # DETERMINE DONOR SAFETY STATUS
    # ==========================================
    unsafe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_unsafe'
    ).first()
    
    safe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_safe'
    ).first()
    
    is_unsafe_donor = unsafe_donation is not None
    is_safe_donor = safe_donation is not None
    is_first_time_donor = not BloodDonate.objects.filter(donor=donor).exists()
    
    # ==========================================
    # GET UNSAFE REASON - FIX FOR MISSING FIELD
    # ==========================================
    unsafe_reason = None
    if is_unsafe_donor:
        try:
            # Try to get reason from related LabTest model
            from blood.models import LabTest
            
            latest_unsafe = BloodDonate.objects.filter(
                donor=donor,
                status='tested_unsafe'
            ).order_by('-date').first()
            
            if latest_unsafe:
                lab_test = LabTest.objects.filter(
                    donation=latest_unsafe,
                    result='unsafe'
                ).order_by('-tested_at').first()
                
                if lab_test:
                    # Try different possible field names
                    if hasattr(lab_test, 'unsafe_reason'):
                        unsafe_reason = lab_test.unsafe_reason
                    elif hasattr(lab_test, 'reason'):
                        unsafe_reason = lab_test.reason
                    elif hasattr(lab_test, 'notes'):
                        unsafe_reason = lab_test.notes
                    elif hasattr(lab_test, 'remarks'):
                        unsafe_reason = lab_test.remarks
                    else:
                        unsafe_reason = "Medical reasons - please contact us for details"
                else:
                    # No lab test found, check if donation has notes
                    if hasattr(latest_unsafe, 'collection_notes') and latest_unsafe.collection_notes:
                        unsafe_reason = latest_unsafe.collection_notes
                    elif hasattr(latest_unsafe, 'phlebotomist_notes') and latest_unsafe.phlebotomist_notes:
                        unsafe_reason = latest_unsafe.phlebotomist_notes
                    else:
                        unsafe_reason = "Medical reasons - please contact us for details"
            else:
                unsafe_reason = "Medical reasons - please contact us for details"
        except ImportError:
            logger.warning("LabTest model not found, using default unsafe reason")
            unsafe_reason = "Medical reasons - please contact us for details"
        except Exception as e:
            logger.warning(f"Could not get unsafe reason: {e}")
            unsafe_reason = "Medical reasons - please contact us for details"
    
    # ==========================================
    # HANDLE UNSAFE DONOR
    # ==========================================
    if is_unsafe_donor:
        donate_form = BloodDonateForm(donor=donor)
        
        context = {
            'donation_form': donate_form,
            'donor': donor,
            'active_donation': None,
            'bloodgroup_verified': donor.bloodgroup_verified,
            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
            'unsafe_reason': unsafe_reason,
            'is_unsafe': True,
            'has_unsafe_donation': True,
            'show_contact_banner': True,
            'form_hidden': True,
        }
        return render(request, 'donor/donate_blood.html', context)

    # ==========================================
    # CHECK ELIGIBILITY
    # ==========================================
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        messages.info(request, "ℹ️ Please complete your eligibility form before donating blood.")
        return redirect('donor:donor-eligibility')

    if not eligibility.approved:
        messages.warning(request, "⚠️ Your eligibility has not been approved yet.")
        return redirect('donor:donor-eligibility-status')

    # ==========================================
    # CALCULATE NEXT ELIGIBLE DATE - FIXED TIMEZONE HANDLING
    # ==========================================
    days_until_next = None
    next_donation_date = None
    hours_until_next = 0
    minutes_until_next = 0
    seconds_until_next = 0
    
    if is_safe_donor and donor.last_donation_date:
        # Convert last_donation_date to a date object if it's a datetime
        if isinstance(donor.last_donation_date, datetime):
            last_donation_date = donor.last_donation_date.date()
        else:
            last_donation_date = donor.last_donation_date
        
        # Calculate next donation date (56 days after last donation)
        next_donation_date = last_donation_date + timedelta(days=56)
        
        # Get today's date (timezone-aware)
        today = timezone.now().date()
        
        # Calculate days until next donation
        days_until_next = (next_donation_date - today).days if next_donation_date > today else 0
        
        if days_until_next > 0:
            # Calculate hours, minutes, seconds for countdown
            # Make next_donation_date timezone-aware for proper comparison
            next_datetime = timezone.make_aware(
                datetime.combine(next_donation_date, datetime_time(0, 0))
            )
            now = timezone.now()
            time_diff = next_datetime - now
            
            # Extract time components
            total_seconds = int(time_diff.total_seconds())
            hours_until_next = (total_seconds % 86400) // 3600
            minutes_until_next = (total_seconds % 3600) // 60
            seconds_until_next = total_seconds % 60

    # Check for active donation
    active_donation = BloodDonate.objects.filter(
        donor=donor,
        status__in=['pending', 'approved']
    ).first()

    # ==========================================
    # HANDLE POST REQUEST (FORM SUBMISSION)
    # ==========================================
    if request.method == 'POST':
        logger.info(f"📝 Donation form submitted by {donor.user.username}")
        logger.info(f"📝 POST data: {request.POST}")
        
        donate_form = BloodDonateForm(request.POST, donor=donor)
        
        if donate_form.is_valid():
            try:
                logger.info(f"✅ Form validation passed for {donor.user.username}")
                
                # Save the donation
                donation = donate_form.save(commit=False)
                donation.donor = donor
                donation.status = 'pending'
                
                # Get values from form
                donation_center = donation.donation_center
                phlebotomist = donation.phlebotomist
                
                # The date is already combined by the form's save method
                donation_datetime = donation.date
                
                logger.info(f"💉 Donation details:")
                logger.info(f"  - Center: {donation_center}")
                logger.info(f"  - Phlebotomist: {phlebotomist}")
                logger.info(f"  - DateTime: {donation_datetime}")
                logger.info(f"  - Blood Group: {donation.bloodgroup}")
                logger.info(f"  - Unit: {donation.unit}")
                
                # Validate required fields
                if not donation_center:
                    messages.error(request, "❌ Donation center is required.")
                    logger.error("❌ Missing donation center")
                    return render(request, 'donor/donate_blood.html', {
                        'donation_form': donate_form,
                        'donor': donor,
                        'active_donation': active_donation,
                        'bloodgroup_verified': donor.bloodgroup_verified,
                        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        'days_until_next': days_until_next,
                        'hours_until_next': hours_until_next,
                        'minutes_until_next': minutes_until_next,
                        'seconds_until_next': seconds_until_next,
                        'next_donation_date': next_donation_date,
                        'is_unsafe': False,
                        'has_unsafe_donation': False,
                        'has_safe_donation': is_safe_donor,
                        'is_first_time_donor': is_first_time_donor
                    })
                
                if not phlebotomist:
                    messages.error(request, "❌ Phlebotomist selection is required.")
                    logger.error("❌ Missing phlebotomist")
                    return render(request, 'donor/donate_blood.html', {
                        'donation_form': donate_form,
                        'donor': donor,
                        'active_donation': active_donation,
                        'bloodgroup_verified': donor.bloodgroup_verified,
                        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        'days_until_next': days_until_next,
                        'hours_until_next': hours_until_next,
                        'minutes_until_next': minutes_until_next,
                        'seconds_until_next': seconds_until_next,
                        'next_donation_date': next_donation_date,
                        'is_unsafe': False,
                        'has_unsafe_donation': False,
                        'has_safe_donation': is_safe_donor,
                        'is_first_time_donor': is_first_time_donor
                    })
                
                # ==========================================
                # SERVER-SIDE DOUBLE-BOOKING PREVENTION
                # ==========================================
                # Check if this phlebotomist is already booked at this time
                existing_appointment = Appointment.objects.filter(
                    phlebotomist=phlebotomist,
                    date=donation_datetime,
                ).exclude(
                    status__in=['cancelled', 'rejected']
                ).exists()

                if existing_appointment:
                    logger.warning(f"⚠️ Double-booking attempt: Phlebotomist {phlebotomist.id} already booked at {donation_datetime}")
                    messages.error(
                        request, 
                        "❌ This time slot is no longer available. The selected nurse is already booked at this time. Please select another time."
                    )
                    return render(request, 'donor/donate_blood.html', {
                        'donation_form': donate_form,
                        'donor': donor,
                        'active_donation': active_donation,
                        'bloodgroup_verified': donor.bloodgroup_verified,
                        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        'days_until_next': days_until_next,
                        'hours_until_next': hours_until_next,
                        'minutes_until_next': minutes_until_next,
                        'seconds_until_next': seconds_until_next,
                        'next_donation_date': next_donation_date,
                        'is_unsafe': False,
                        'has_unsafe_donation': False,
                        'has_safe_donation': is_safe_donor,
                        'is_first_time_donor': is_first_time_donor
                    })

                # Optional: Check if donor already has an appointment at this time
                donor_existing = Appointment.objects.filter(
                    donor=donor,
                    date=donation_datetime,
                ).exclude(
                    status__in=['cancelled', 'rejected']
                ).exists()

                if donor_existing:
                    logger.warning(f"⚠️ Donor {donor.id} already has appointment at {donation_datetime}")
                    messages.error(
                        request, 
                        "❌ You already have an appointment scheduled at this time. Please select another time."
                    )
                    return render(request, 'donor/donate_blood.html', {
                        'donation_form': donate_form,
                        'donor': donor,
                        'active_donation': active_donation,
                        'bloodgroup_verified': donor.bloodgroup_verified,
                        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        'days_until_next': days_until_next,
                        'hours_until_next': hours_until_next,
                        'minutes_until_next': minutes_until_next,
                        'seconds_until_next': seconds_until_next,
                        'next_donation_date': next_donation_date,
                        'is_unsafe': False,
                        'has_unsafe_donation': False,
                        'has_safe_donation': is_safe_donor,
                        'is_first_time_donor': is_first_time_donor
                    })
                
                # Save the donation first
                donation.save()
                logger.info(f"✅ BloodDonate saved with ID: {donation.id}")
                
                # ==========================================
                # CREATE APPOINTMENT FOR PHLEBOTOMIST
                # ==========================================
                try:
                    # Get ContentType for BloodDonate
                    blood_donate_ct = ContentType.objects.get_for_model(BloodDonate)
                    logger.info(f"📋 BloodDonate ContentType ID: {blood_donate_ct.id}")
                    
                    # Create the appointment
                    appointment = Appointment.objects.create(
                        donor=donor,
                        request_content_type=blood_donate_ct,
                        request_object_id=donation.id,
                        date=donation_datetime,
                        center=donation_center,
                        phlebotomist=phlebotomist,
                        status='pending',
                        notes=f"Blood donation appointment - {donor.user.get_full_name() or donor.user.username}"
                    )
                    
                    logger.info(f"✅✅✅ APPOINTMENT CREATED SUCCESSFULLY!")
                    logger.info(f"  - Appointment ID: {appointment.id}")
                    logger.info(f"  - Donation ID: {donation.id}")
                    logger.info(f"  - Donor: {donor.user.username}")
                    logger.info(f"  - Phlebotomist: {phlebotomist.user.username}")
                    logger.info(f"  - Center: {donation_center.name}")
                    logger.info(f"  - Date: {donation_datetime}")
                    logger.info(f"  - Status: {appointment.status}")
                    
                    # ==========================================
                    # SET SESSION FLAGS FOR REVIEW PROMPT
                    # ==========================================
                    request.session['just_donated'] = True
                    request.session['donation_center_name'] = donation_center.name
                    request.session['donation_date'] = donation_datetime.strftime('%B %d, %Y')
                    request.session['donation_time'] = donation_datetime.strftime('%I:%M %p')
                    
                    messages.success(request, "✅ Your blood donation appointment has been scheduled successfully!")
                    
                    # Check if user already has a review
                    from blood.models import UserReview
                    has_review = UserReview.objects.filter(user=request.user).exists()
                    
                    if not has_review:
                        # Add a special message encouraging review
                        from django.utils.safestring import mark_safe
                        messages.info(
                            request, 
                            mark_safe(
                                "🌟 We'd love to hear about your experience! "
                                f"<a href='{reverse('submit_review')}' class='alert-link'>Click here to leave a review</a> "
                                "and help others know what to expect."
                            )
                        )
                    
                    return redirect('donor:donation-history')
                    
                except Exception as e:
                    logger.error(f"❌ FAILED to create appointment for donation {donation.id}")
                    logger.error(f"❌ Error: {str(e)}")
                    logger.error(f"❌ Error type: {type(e).__name__}")
                    import traceback
                    logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    # Delete the donation since appointment creation failed
                    donation.delete()
                    logger.info(f"🗑️ Deleted donation {donation.id} due to appointment creation failure")
                    
                    messages.error(
                        request, 
                        f"❌ Failed to create appointment: {str(e)}. Please try again or contact support."
                    )
                
            except Exception as e:
                logger.error(f"❌ Error saving donation: {str(e)}")
                logger.error(f"❌ Error type: {type(e).__name__}")
                import traceback
                logger.error(f"❌ Traceback: {traceback.format_exc()}")
                messages.error(request, f"❌ An error occurred: {str(e)}")
        else:
            # Form has errors
            logger.warning(f"⚠️ Form validation failed for {donor.user.username}")
            logger.warning(f"⚠️ Form errors: {donate_form.errors}")
            messages.error(request, "❌ Please correct the errors below.")
    else:
        # ==========================================
        # HANDLE GET REQUEST (DISPLAY FORM)
        # ==========================================
        donate_form = BloodDonateForm(donor=donor)
        
        # Pre-fill form with donor data
        initial_data = {
            'first_name': donor.user.first_name,
            'last_name': donor.user.last_name,
            'mobile': donor.mobile,
        }
        
        if donor.bloodgroup:
            initial_data['bloodgroup'] = donor.bloodgroup
            
        donate_form.initial.update(initial_data)

    # ==========================================
    # COMMON CONTEXT FOR BOTH GET AND POST
    # ==========================================
    context = {
        'donation_form': donate_form,
        'donor': donor,
        'active_donation': active_donation,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
        'days_until_next': days_until_next,
        'hours_until_next': hours_until_next,
        'minutes_until_next': minutes_until_next,
        'seconds_until_next': seconds_until_next,
        'next_donation_date': next_donation_date,
        'is_unsafe': False,
        'has_unsafe_donation': False,
        'has_safe_donation': is_safe_donor,
        'is_first_time_donor': is_first_time_donor
    }

    return render(request, 'donor/donate_blood.html', context)
# Donation History
# -------------------------------
@login_required(login_url='donorlogin')
@username_required
@onboarding_complete_required
def donation_history_view(request):
    try:
        donor_instance = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "No donor profile found for this user.")
        return redirect('donor-profile')

    # Fetch all BloodDonate records for this donor, ordered by most recent date
    donations = BloodDonate.objects.filter(donor=donor_instance).order_by('-date')
    has_donations = donations.exists()

    # Use ContentType for BloodDonate for filtering related appointments
    content_type = ContentType.objects.get_for_model(BloodDonate)

    # Fetch all appointments linked to these donations
    appointments = Appointment.objects.filter(
        request_content_type=content_type,
        request_object_id__in=donations.values_list('id', flat=True)
    )

    # Map appointments by related donation id for quick lookup
    appointment_map = {appt.request_object_id: appt for appt in appointments}

    # Inject appointment and display status into each donation for template use
    for donation in donations:
        donation.appointment = appointment_map.get(donation.id)
        # Prefer appointment status if exists, otherwise fallback to donation status
        donation.display_status = (donation.appointment.status if donation.appointment else donation.status)

    return render(request, 'donor/donation_history.html', {
        'donations': donations,
        'has_donations': has_donations,
    })

# -------------------------------
# Cancel Donation Appointment
# -------------------------------
@login_required(login_url='donorlogin')
def cancel_donation_request_view(request, donation_id):
    """
    Allow donors to cancel their own donation request & linked appointment,
    only if still in 'pending' or 'approved' status and scheduled for the future.
    """
    user = request.user
    donation = get_object_or_404(BloodDonate, id=donation_id)

    if not hasattr(user, 'donor') or donation.donor.user != user:
        raise PermissionDenied("You do not have permission to cancel this donation.")

    if donation.status.lower() in ['completed', 'rejected', 'cancelled']:
        messages.warning(request, "This donation has already been finalized and cannot be cancelled.")
        return redirect('donation-history')

    content_type = ContentType.objects.get_for_model(BloodDonate)
    appointment = Appointment.objects.filter(
        donor=user.donor,
        request_content_type=content_type,
        request_object_id=donation.id,
    ).first()

    now = timezone.now()

    if not appointment:
        messages.warning(request, "No appointment found to cancel for this donation.")
        return redirect('donation-history')

    if appointment.date <= now:
        messages.warning(request, "This appointment cannot be cancelled because the date/time has passed or is ongoing.")
        return redirect('donation-history')

    if appointment.status.lower() in ['completed', 'rejected', 'cancelled']:
        messages.warning(request, "This appointment has already been finalized and cannot be cancelled.")
        return redirect('donation-history')

    # Cancel donation
    if donation.status.lower() in ['pending', 'approved']:
        donation.status = 'cancelled'
        donation.save(update_fields=['status'])
        logger.info(f"Donation ID {donation.id} cancelled by donor {user.id}.")

    # Cancel appointment
    if appointment.status.lower() in ['pending', 'approved']:
        appointment.status = 'cancelled'
        appointment.cancelled_by = 'donor'
        appointment.cancelled_by_user = user
        appointment.cancelled_at = now
        appointment.status_changed_by = user
        appointment.status_changed_at = now
        appointment.save()
        logger.info(f"Appointment ID {appointment.id} cancelled by donor {user.id}.")

        # Notify phlebotomists at the donation center
        try:
            center = getattr(appointment, 'donation_center', None) or getattr(donation, 'donation_center', None)
            phlebotomists = Phlebotomist.objects.filter(donation_center=center) if center else Phlebotomist.objects.all()
            for phlebotomist in phlebotomists:
                Notification.objects.create(
                    title="Donation Appointment Cancelled",
                    message=(
                        f"Donor {user.get_full_name() or user.username} cancelled their donation appointment "
                        f"(ID: {appointment.id}) scheduled for {appointment.date.strftime('%b %d, %Y %I:%M %p')}."
                    ),
                    recipient=phlebotomist,
                    sender=user.donor
                )
            logger.info(f"Nurses at {center} notified about donor cancellation (Appointment ID: {appointment.id}).")
        except Exception as e:
            logger.warning(f"Failed to notify phlebotomists about donor cancellation (Appointment ID: {appointment.id}): {e}")

    messages.success(request, "Your donation request and appointment have been cancelled successfully.")
    return redirect('donation-history')


# -------------------------------
# Profile View (READ-ONLY - View Only)
# -------------------------------
# -------------------------------
# Profile View (READ-ONLY - View Only)
# -------------------------------
@login_required(login_url='donor:donorlogin')
@onboarding_complete_required
def donor_profile_view(request):
    """
    READ-ONLY view - displays donor information.
    For viewing only - no editing here.
    """
    donor = get_object_or_404(Donor, user=request.user)
    user = request.user

    # Calculate next eligible donation date
    next_donation_date = donor.next_eligible_donation_date()
    days_until_next = donor.days_until_next_donation()
    
    # Get profile picture URL with fallback to default
    profile_pic_url = None
    if donor.profile_pic and hasattr(donor.profile_pic, 'url') and donor.profile_pic.name:
        profile_pic_url = donor.profile_pic.url
    
    # ===== FORMAT MOBILE NUMBER FOR DISPLAY =====
    mobile_display = donor.mobile
    if donor.mobile and donor.mobile.startswith('+254'):
        # Convert +254712345678 to 0712345678 for display
        mobile_display = '0' + donor.mobile[4:]
    
    context = {
        'donor': donor,
        'user': user,
        'next_donation_date': next_donation_date,
        'days_until_next': days_until_next,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
        'verified_by': donor.bloodgroup_verified_by.get_full_name() if donor.bloodgroup_verified_by else None,
        'verified_at': donor.bloodgroup_verified_at,
        'profile_pic_url': profile_pic_url,
        'mobile_display': mobile_display,  # Add formatted mobile number
    }
    return render(request, 'donor/donor_profile.html', context)

# -------------------------------
# Edit Profile View (EDITABLE - Profile Completion)
# -------------------------------

@login_required(login_url='donorlogin')
@username_required
def donor_edit_profile_view(request):
    """
    Edit donor profile. Handles both initial onboarding and later edits.
    During onboarding, certain fields are required.
    Blood group is OPTIONAL.
    County is non-editable once set.
    NOW SUPPORTS IMAGE CROPPING.
    """
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "Please create a donor profile first.")
        return redirect('donor:donorsignup')
    
    user = request.user
    
    # Check if in onboarding mode
    is_complete, missing_fields = check_profile_completion(donor)
    is_onboarding = not is_complete
    
    if request.method == 'POST':
        # Create a mutable copy of POST data
        post_data = request.POST.copy()
        
        # Ensure first_name and last_name are set
        post_data['first_name'] = user.first_name
        post_data['last_name'] = user.last_name
        post_data['email'] = user.email
        
        # IMPORTANT: If county is already set, ensure it's in POST data
        # This handles the case where county field is readonly and not submitted
        if donor.county and 'county' not in post_data:
            post_data['county'] = donor.county
        
        # ====== NEW: Handle cropped image from base64 ======
        cropped_image_data = request.POST.get('cropped_image', '')
        
        # Create a mutable FILES dictionary
        files = request.FILES.copy()
        
        if cropped_image_data and cropped_image_data.startswith('data:image'):
            try:
                # Extract base64 data
                format, imgstr = cropped_image_data.split(';base64,')
                ext = format.split('/')[-1]  # Get extension (jpeg, png, etc)
                
                # Decode base64 string
                img_data = base64.b64decode(imgstr)
                
                # Create a file-like object
                img_file = ContentFile(img_data, name=f'profile_{user.username}.{ext}')
                
                # Add to FILES
                files['profile_pic'] = img_file
                
                logger.info(f"✅ Cropped image processed: {len(img_data)} bytes")
            except Exception as e:
                logger.error(f"❌ Error processing cropped image: {e}", exc_info=True)
                messages.error(request, "Error processing image. Please try again.")
        # ====== END NEW CODE ======
        
        form = DonorProfileForm(post_data, files, instance=donor)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the donor profile
                    donor = form.save()
                    
                    # Handle profile picture removal
                    if 'remove_profile_pic' in request.POST and request.POST.get('remove_profile_pic') == 'true':
                        if donor.profile_pic:
                            donor.profile_pic.delete(save=False)
                        donor.profile_pic = None
                        donor.save()
                        logger.info(f"🗑️ Profile picture removed for {user.username}")
                    
                    # Check if profile is now complete
                    is_complete, missing = check_profile_completion(donor)
                    
                    logger.debug(f"🔍 Profile completion check: {is_complete}")
                    logger.debug(f"   Missing: {missing}")
                    logger.debug(f"   Blood group: {donor.bloodgroup} (optional)")
                    
                    if is_complete and is_onboarding:
                        # Onboarding just completed!
                        # Clear onboarding session
                        for key in ['onboarding_step', 'onboarding_progress', 'needs_username', 
                                  'username_completed', 'onboarding_started']:
                            if key in request.session:
                                del request.session[key]
                        
                        request.session['just_completed_onboarding'] = True
                        messages.success(
                            request, 
                            f"🎉 All set, {user.first_name}! Welcome to BloodConnect!"
                        )
                        return redirect('donor:donor-dashboard')
                    elif is_complete:
                        # Profile updated (not onboarding)
                        messages.success(request, "✅ Profile updated successfully!")
                        return redirect('donor:donor-profile')
                    else:
                        # Still missing fields
                        messages.warning(
                            request,
                            f"Please complete these fields: {', '.join(missing)}"
                        )
                    
            except Exception as e:
                logger.error(f"Error saving profile: {e}", exc_info=True)
                messages.error(request, f"Error saving profile: {str(e)}")
        else:
            # Show specific error messages
            for field, errors in form.errors.items():
                for error in errors:
                    # Skip county error if county is already set
                    if field == 'county' and donor.county:
                        continue
                    messages.error(request, f"{field}: {error}")
    else:
        form = DonorProfileForm(instance=donor, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })
    
    # Calculate completion - EXCLUDE blood group
    completed_fields = sum([
        bool(donor.mobile),
        bool(donor.national_id),
        bool(donor.county),
        bool(donor.dob)
    ])
    completion_percentage = (completed_fields / 4) * 100 if completed_fields > 0 else 0
    
    missing_fields_list = []
    if not donor.mobile:
        missing_fields_list.append("Mobile Number")
    if not donor.national_id:
        missing_fields_list.append("National ID")
    if not donor.county:
        missing_fields_list.append("County")
    if not donor.dob:
        missing_fields_list.append("Date of Birth")
    
    # Add optional note about blood group
    if not donor.bloodgroup:
        missing_fields_list.append("Blood Group (optional)")
    
    # ===== FORMAT MOBILE NUMBER FOR DISPLAY IN THE FORM =====
    mobile_display = donor.mobile
    if donor.mobile and donor.mobile.startswith('+254'):
        mobile_display = '0' + donor.mobile[4:]
    
    context = {
        'profile_form': form,
        'donor': donor,
        'user': user,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'is_first_time': is_onboarding,
        'is_onboarding': is_onboarding,
        'completed_fields': completed_fields,
        'total_required_fields': 4,
        'completion_percentage': completion_percentage,
        'missing_fields': missing_fields_list,
        'profile_pic_url': donor.profile_pic.url if donor.profile_pic and hasattr(donor.profile_pic, 'url') else None,
        'page_title': 'Complete Your Profile' if is_onboarding else 'Edit Profile',
        'mobile_display': mobile_display,  # Add formatted mobile number
    }
    return render(request, 'donor/donor_edit_profile.html', context)

# -------------------------------
# Notifications
# -------------------------------
@login_required(login_url='donorlogin')
@username_required
def donor_notifications_view(request):
    donor = get_object_or_404(Donor, user=request.user)
    donor_ct = ContentType.objects.get_for_model(donor)

    notifications = Notification.objects.filter(
        recipient_content_type=donor_ct,
        recipient_object_id=donor.id
    ).order_by('-created_at')

    # FIX: Changed from 'read' to 'is_read'
    unread_count = notifications.filter(is_read=False).count()

    return render(request, 'donor/donor_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })
    
# -------------------------------
# Mark Notifications as Read
# -------------------------------
@login_required(login_url='donorlogin')
def mark_notification_read(request, pk):
    donor = get_object_or_404(Donor, user=request.user)
    donor_ct = ContentType.objects.get_for_model(donor)
    
    # Get the notification
    notification = get_object_or_404(
        Notification, 
        id=pk, 
        recipient_content_type=donor_ct, 
        recipient_object_id=donor.id
    )
    
    # FIX: Changed from 'read' to 'is_read'
    notification.is_read = True
    notification.save()
    
    # Optional: Add a success message
    messages.success(request, "Notification marked as read.")
    
    # FIX: Use namespace in redirect
    return redirect('donor:donor-notifications')


# ==========================================
# VOLUNTEER OPPORTUNITIES VIEWS
# ==========================================

@login_required(login_url='donorlogin')
@username_required
def volunteer_opportunities_view(request):
    """Show all volunteer opportunities"""
    context = {
        'page_title': 'Volunteer Opportunities',
        'page_icon': 'fa-hands-helping',
        'opportunities': [

            {
                'title': 'Social Media Advocate',
                'description': 'Share donation stories, urgent needs, and awareness content on social media.',
                'icon': 'fa-share-alt',
                'color': 'info',
                'url_name': 'donor:social-media-advocate',
                'commitment': '1-2 hours/week',
                'requirements': 'Active on social media'
            },
            {
                'title': 'Transportation Volunteer',
                'description': 'Help donors get to and from donation centers.',
                'icon': 'fa-truck',
                'color': 'success',
                'url_name': 'donor:transport-volunteer',
                'commitment': 'Flexible schedule',
                'requirements': 'Valid driver\'s license'
            },


        ]
    }
    return render(request, 'donor/volunteer/volunteer_opportunities.html', context)




@login_required(login_url='donorlogin')
def social_media_advocate_view(request):
    """Social media advocacy program"""
    context = {
        'page_title': 'Social Media Advocate',
        'page_icon': 'fa-share-alt',
        'description': 'Use your social media presence to spread awareness and encourage donation!',
        'benefits': [
            'Work from home - completely remote',
            'Flexible time commitment (1-2 hours/week)',
            'Reach thousands of potential donors',
            'Get exclusive content to share',
            'Be part of our digital ambassador network'
        ],
        'requirements': [
            'Active on at least one social platform',
            'Willingness to share our messages',
            'Positive and engaging communication style',
            'Basic understanding of social media'
        ],
        'contact_email': 'social@bloodconnect.org'
    }
    return render(request, 'donor/volunteer/social_media_advocate.html', context)


@login_required(login_url='donorlogin')
def transport_volunteer_view(request):
    """Transportation volunteer program"""
    context = {
        'page_title': 'Transportation Volunteer',
        'page_icon': 'fa-truck',
        'description': 'Help donors get to donation centers and blood reach hospitals!',
        'benefits': [
            'Flexible schedule - choose your hours',
            'Mileage reimbursement provided',
            'Critical role in the donation process',
            'Meet amazing donors and healthcare workers',
            'Training and support provided'
        ],
        'requirements': [
            'Valid driver\'s license',
            'Clean driving record',
            'Reliable vehicle',
            'Valid insurance',
            'Willingness to undergo background check'
        ],
        'contact_email': 'transport@bloodconnect.org'
    }
    return render(request, 'donor/volunteer/transport_volunteer.html', context)


# ==========================================
# AWARENESS & EDUCATION VIEWS
# ==========================================

@login_required(login_url='donorlogin')
@username_required
def awareness_hub_view(request):
    """Central hub for awareness campaigns"""
    context = {
        'page_title': 'Awareness Hub',
        'page_icon': 'fa-bullhorn',
        'active_campaigns': [
            {
                'name': 'World Blood Donor Day',
                'date': 'June 14, 2025',
                'description': 'Join us in celebrating donors worldwide',
                'badge': 'primary',
                'badge_text': 'June 14'
            },
            {
                'name': 'Emergency Blood Drive',
                'date': 'Ongoing',
                'description': 'Critical shortage of O- blood type',
                'badge': 'danger',
                'badge_text': 'Urgent'
            },
            {
                'name': 'Youth Donor Campaign',
                'date': 'Ongoing',
                'description': 'Encouraging young donors to step forward',
                'badge': 'success',
                'badge_text': 'Ongoing'
            },
            {
                'name': 'Workplace Giving Challenge',
                'date': 'May-June 2025',
                'description': 'Corporate teams compete to donate',
                'badge': 'info',
                'badge_text': 'Coming Soon'
            },
        ]
    }
    return render(request, 'donor/awareness/awareness_hub.html', context)


@login_required(login_url='donorlogin')
def awareness_campaigns_view(request):
    """All awareness campaigns"""
    context = {
        'page_title': 'Awareness Campaigns',
        'page_icon': 'fa-calendar-alt',
        'campaigns': [
            {
                'title': 'World Blood Donor Day',
                'date': 'June 14, 2025',
                'description': 'Global celebration of blood donors',
                'status': 'Upcoming',
                'status_color': 'primary',
                'image': 'images/campaigns/wbdd.jpg'
            },
            {
                'title': 'Emergency O- Drive',
                'date': 'March-April 2025',
                'description': 'Critical need for O- blood type',
                'status': 'Active',
                'status_color': 'success',
                'image': 'images/campaigns/emergency.jpg'
            },
            {
                'title': 'College Donor Challenge',
                'date': 'September 2025',
                'description': 'Universities compete to donate',
                'status': 'Planning',
                'status_color': 'warning',
                'image': 'images/campaigns/college.jpg'
            },
        ]
    }
    return render(request, 'donor/awareness/awareness_campaigns.html', context)


@login_required(login_url='donorlogin')
def share_awareness_view(request):
    """Share awareness content"""
    context = {
        'page_title': 'Share Awareness',
        'page_icon': 'fa-share-alt',
        'share_options': [
            {
                'platform': 'Facebook',
                'icon': 'fa-facebook',
                'color': 'primary',
                'url': 'https://facebook.com/sharer/sharer.php?u=',
                'message': 'Join me in saving lives with BloodConnect!'
            },
            {
                'platform': 'Twitter',
                'icon': 'fa-twitter',
                'color': 'info',
                'url': 'https://twitter.com/intent/tweet?text=',
                'message': 'Every drop counts! Donate blood and save lives with @BloodConnect'
            },
            {
                'platform': 'WhatsApp',
                'icon': 'fa-whatsapp',
                'color': 'success',
                'url': 'https://wa.me/?text=',
                'message': 'Check out BloodConnect - a platform to save lives through blood donation!'
            },
            {
                'platform': 'LinkedIn',
                'icon': 'fa-linkedin',
                'color': 'secondary',
                'url': 'https://www.linkedin.com/sharing/share-offsite/?url=',
                'message': 'Proud to support BloodConnect in their mission to save lives.'
            },
        ],
        'sample_posts': [
            {
                'text': 'Just completed my 5th blood donation with BloodConnect! Every donation saves up to 3 lives. 🩸❤️ #BloodDonation #SaveLives',
                'image': 'images/samples/donation.jpg'
            },
            {
                'text': 'Did you know? One blood donation can save up to three lives. Join me at BloodConnect to make a difference!',
                'image': 'images/samples/info.jpg'
            },
        ]
    }
    return render(request, 'donor/awareness/share_awareness.html', context)





# ==========================================
# EDUCATIONAL RESOURCES VIEWS
# ==========================================

@login_required(login_url='donorlogin')
def donor_resources_view(request):
    """Central resources hub"""
    context = {
        'page_title': 'Donor Resources',
        'page_icon': 'fa-book',
        'resources': [
            {
                'title': 'Health Tips',
                'description': 'Stay healthy and ready to donate',
                'icon': 'fa-heartbeat',
                'color': 'primary',
                'url_name': 'donor:health-tips',
                'items': ['Pre-donation tips', 'Post-donation care', 'Nutrition advice']
            },
            {
                'title': 'FAQs',
                'description': 'Answers to common questions',
                'icon': 'fa-question-circle',
                'color': 'info',
                'url_name': 'donor:faqs',
                'items': ['Eligibility', 'Process', 'Safety', 'After donation']
            },
            {
                'title': 'Donor Advice',
                'description': 'Tips from experienced donors',
                'icon': 'fa-comments',
                'color': 'success',
                'url_name': 'donor:donor-advice',
                'items': ['First-time tips', 'What to expect', 'Stories']
            },
            {
                'title': 'Blood Types Guide',
                'description': 'Understanding blood types',
                'icon': 'fa-tint',
                'color': 'danger',
                'url_name': 'donor:blood-types',
                'items': ['Compatibility', 'Distribution', 'Facts']
            },
        ]
    }
    return render(request, 'donor/resources/donor_resources.html', context)


@login_required(login_url='donorlogin')
@username_required
def health_tips_view(request):
    """Health tips for donors"""
    context = {
        'page_title': 'Health Tips',
        'page_icon': 'fa-heartbeat',
        'pre_donation': [
            'Drink plenty of water the day before and day of donation',
            'Eat a healthy meal rich in iron (spinach, red meat, beans)',
            'Get a good night\'s sleep (7-8 hours)',
            'Avoid fatty foods before donation',
            'Bring ID and donor card if available',
            'Wear comfortable clothing with sleeves that can be rolled up'
        ],
        'during_donation': [
            'Relax and breathe normally',
            'Let staff know if you feel uncomfortable',
            'The actual donation takes 8-10 minutes',
            'Only about 1 pint of blood is taken'
        ],
        'post_donation': [
            'Rest for 10-15 minutes at the center',
            'Enjoy refreshments provided',
            'Drink extra fluids for next 24-48 hours',
            'Avoid heavy lifting or strenuous exercise for 5 hours',
            'Keep the bandage on for several hours',
            'If you feel dizzy, lie down with feet elevated'
        ],
        'long_term': [
            'Maintain healthy iron levels through diet',
            'Regular exercise helps maintain good circulation',
            'Stay hydrated daily',
            'Track your donations to maintain regular schedule'
        ]
    }
    return render(request, 'donor/resources/health_tips.html', context)


@login_required(login_url='donorlogin')
@username_required
def faqs_view(request):
    """Frequently asked questions"""
    return render(request, 'donor/resources/faqs.html')


@login_required(login_url='donorlogin')
@username_required
def donor_advice_view(request):
    """Advice from experienced donors"""
    context = {
        'page_title': 'Donor Advice',
        'page_icon': 'fa-comments',
        'tips': [
            {
                'from': 'Michael, 25 donations',
                'tip': 'Drink extra water the day before. Makes the process much smoother!',
                'avatar': 'images/avatars/michael.jpg'
            },
            {
                'from': 'Sarah, first-time donor',
                'tip': 'I was nervous, but the staff was amazing. Bring a friend for support!',
                'avatar': 'images/avatars/sarah.jpg'
            },
            {
                'from': 'Dr. James, phlebotomist',
                'tip': 'Eat a good meal beforehand and wear comfortable clothes with short sleeves.',
                'avatar': 'images/avatars/james.jpg'
            },
            {
                'from': 'Rachel, 10 donations',
                'tip': 'Schedule your next appointment before leaving. It helps you stay on track!',
                'avatar': 'images/avatars/rachel.jpg'
            },
        ],
        'videos': [
            {'title': 'What to Expect During Your First Donation', 'duration': '3:45'},
            {'title': 'Donor Tips and Tricks', 'duration': '5:30'},
            {'title': 'Life After Donation', 'duration': '4:15'},
        ]
    }
    return render(request, 'donor/resources/donor_advice.html', context)



@login_required(login_url='donor:donorlogin')
@username_required
def events_view(request):
    """Display upcoming events from BloodDriveEvent model"""
    try:
        now = timezone.now()
        
        # Fetch upcoming events created by admin
        upcoming_events = BloodDriveEvent.objects.filter(
            is_active=True,
            event_date__gte=now  # Compare datetime with datetime
        ).order_by('display_order', 'event_date')
        
        # Fetch past events
        past_events = BloodDriveEvent.objects.filter(
            is_active=True,
            event_date__lt=now
        ).order_by('-event_date')[:5]
        
        # Format the data for display
        events_data = []
        for event in upcoming_events:
            events_data.append({
                'id': event.id,
                'title': event.title,
                'date': event.event_date.strftime('%B %d, %Y'),
                'time': event.event_date.strftime('%I:%M %p'),  # Extract time from event_date
                'location': event.location,
                'address': event.address,
                'description': event.description,
                'capacity': event.capacity if hasattr(event, 'capacity') else 50,
                'registered': event.registered_count if hasattr(event, 'registered_count') else 0,
                'available_slots': event.available_slots if hasattr(event, 'available_slots') else 50,
                'status': 'upcoming',
                'image': event.image.url if event.image else None,
                'organizer': event.organizer_name if hasattr(event, 'organizer_name') else 'Blood Drive Team',
                'contact_phone': event.contact_phone,
                'contact_email': event.contact_email,
                'end_date': event.end_date.strftime('%B %d, %Y at %I:%M %p') if event.end_date else None,
            })
        
        # Format past events
        past_events_data = []
        for event in past_events:
            past_events_data.append({
                'id': event.id,
                'title': event.title,
                'date': event.event_date.strftime('%B %d, %Y'),
                'location': event.location,
                'image': event.image.url if event.image else None,
            })
        
        context = {
            'page_title': 'Community Blood Drive Events',
            'page_icon': 'fa-calendar-alt',
            'events': events_data,
            'past_events': past_events_data,
            'has_events': bool(events_data or past_events_data),
        }
        
        return render(request, 'donor/events.html', context)
        
    except Exception as e:
        logger.error(f"Error in events_view: {e}", exc_info=True)
        context = {
            'page_title': 'Community Events',
            'page_icon': 'fa-calendar-alt',
            'events': [],
            'past_events': [],
            'has_events': False,
            'error_message': 'Unable to load events at this time. Please try again later.'
        }
        return render(request, 'donor/events.html', context)


@login_required(login_url='donor:donorlogin')
@username_required
def event_detail_view(request, event_id):
    """Display details for a specific event"""
    try:
        event = get_object_or_404(BloodDriveEvent, id=event_id, is_active=True)
        
        # Check if event is in the past
        is_past = event.event_date < timezone.now()
        
        context = {
            'event': event,
            'page_title': event.title,
            'is_past': is_past,
            'is_upcoming': event.is_upcoming,
            'formatted_date': event.event_date.strftime('%B %d, %Y at %I:%M %p'),
            'formatted_end_date': event.end_date.strftime('%B %d, %Y at %I:%M %p') if event.end_date else None,
            'capacity': event.capacity if hasattr(event, 'capacity') else 50,
            'registered': event.registered_count if hasattr(event, 'registered_count') else 0,
            'available_slots': event.available_slots if hasattr(event, 'available_slots') else 50,
        }
        return render(request, 'donor/event_detail.html', context)
        
    except BloodDriveEvent.DoesNotExist:
        messages.error(request, "Event not found.")
        return redirect('donor:events')
    except Exception as e:
        logger.error(f"Error in event_detail_view: {e}", exc_info=True)
        messages.error(request, "Error loading event details.")
        return redirect('donor:events')




# ==========================================
# IMPACT TRACKING VIEWS
# ==========================================

@login_required(login_url='donorlogin')
@username_required
def impact_view(request):
    """Show collective impact of donors and supporters"""
    context = {
        'page_title': 'Our Collective Impact',
        'page_icon': 'fa-chart-line',
        'stats': {
            'total_donations': 15420,
            'total_volunteer_hours': 8760,
            'lives_impacted': 46260,
            'active_donors': 5230,
            'active_volunteers': 845,
            'partner_organizations': 127,
            'blood_drives': 342,
            'communities_served': 23,
        },
        'monthly_stats': [
            {'month': 'Jan', 'donations': 1250},
            {'month': 'Feb', 'donations': 1180},
            {'month': 'Mar', 'donations': 1420},
            {'month': 'Apr', 'donations': 1350},
            {'month': 'May', 'donations': 1510},
            {'month': 'Jun', 'donations': 1620},
        ],
        'achievements': [
            {'year': 2025, 'title': 'Reached 15,000 donations', 'description': 'Milestone achievement'},
            {'year': 2024, 'title': 'Expanded to 5 new counties', 'description': 'Growth'},
            {'year': 2023, 'title': 'Launched volunteer program', 'description': 'Engagement'},
        ]
    }
    return render(request, 'donor/impact/impact.html', context)


@login_required(login_url='donorlogin')
def share_impact_view(request):
    """Share impact on social media"""
    context = {
        'page_title': 'Share Our Impact',
        'page_icon': 'fa-share-alt',
        'stats': {
            'donations': 15420,
            'lives': 46260,
            'volunteers': 845,
        },
        'share_messages': [
            {
                'platform': 'Twitter',
                'message': 'Proud to support @BloodConnect - they\'ve saved 46,260 lives through 15,420 donations! Join the movement. 🩸❤️ #BloodDonation #SaveLives'
            },
            {
                'platform': 'Facebook',
                'message': 'I\'m proud to be part of the BloodConnect community. Together we\'ve saved 46,260 lives! Join us in making a difference.'
            },
            {
                'platform': 'LinkedIn',
                'message': 'BloodConnect has facilitated 15,420 blood donations, impacting 46,260 lives. Proud to contribute to this life-saving work.'
            },
        ]
    }
    return render(request, 'donor/impact/share_impact.html', context)

@login_required(login_url='donor:donorlogin')
@require_GET
def ajax_get_available_times(request):
    """
    AJAX endpoint to get available time slots for a phlebotomist on a specific date.
    Returns only unbooked times.
    """
    phlebotomist_id = request.GET.get('phlebotomist_id')
    date_str = request.GET.get('date')
    
    logger.info(f"🔍 Checking available times - Phlebotomist: {phlebotomist_id}, Date: {date_str}")
    
    if not phlebotomist_id or not date_str:
        return JsonResponse({
            'available_times': [],
            'error': 'Missing parameters'
        }, status=400)
    
    try:
        # Validate phlebotomist exists
        phlebotomist = get_object_or_404(Phlebotomist, id=phlebotomist_id, is_approved=True)
        
        # Parse date
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get available slots
        available_slots = get_available_time_slots(phlebotomist_id, appointment_date)
        
        # Format for template (12-hour with AM/PM)
        formatted_slots = []
        for slot in available_slots:
            time_obj = datetime.strptime(slot, '%H:%M')
            formatted_slots.append({
                'value': slot,
                'display': time_obj.strftime('%I:%M %p')
            })
        
        logger.info(f"✅ Found {len(formatted_slots)} available slots")
        
        return JsonResponse({
            'available_times': formatted_slots,
            'phlebotomist_name': phlebotomist.user.get_full_name() or phlebotomist.user.username,
            'date': date_str
        })
        
    except Phlebotomist.DoesNotExist:
        logger.warning(f"⚠️ Phlebotomist not found: {phlebotomist_id}")
        return JsonResponse({
            'available_times': [],
            'error': 'Phlebotomist not found'
        }, status=404)
        
    except ValueError as e:
        logger.warning(f"⚠️ Invalid date format: {date_str}")
        return JsonResponse({
            'available_times': [],
            'error': 'Invalid date format'
        }, status=400)
        
    except Exception as e:
        logger.error(f"❌ Error getting available times: {str(e)}", exc_info=True)
        return JsonResponse({
            'available_times': [],
            'error': str(e)
        }, status=500)
