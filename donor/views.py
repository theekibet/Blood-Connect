from datetime import datetime,timedelta
import json
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
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
from nurse.models import Nurse, Appointment
from .models import Donor, DonorEligibility, BloodDonate

from .forms import (
    DonorUserForm, DonorForm, DonorProfileForm, DonorEligibilityForm,
    BloodDonateForm, DonorLoginForm
)
from django.core.exceptions import PermissionDenied
from donor.models import DonorBloodRequest
from blood.models import Notification,  DonationCenter
from patient.models import  BloodRequest
from nurse.forms import AppointmentForm
from blood.utils.geolocation import find_nearby_compatible_patients
from datetime import date
import logging
from django.db import transaction
from donor.forms import DonorBloodRequestForm
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.html import strip_tags
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
import re
import random
from blood.utils.notifications import create_notification
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

def donor_signup_view(request):
    """
    Handles donor registration.
    Assigns new users to the DONOR group.
    """
    username_suggestions = None
    
    if request.method == 'POST':
        user_form = DonorUserForm(request.POST)
        donor_form = DonorForm(request.POST, request.FILES)
        
        # Check for username conflict specifically to generate suggestions
        attempted_username = request.POST.get('username', '').strip()
        if attempted_username and User.objects.filter(username__iexact=attempted_username).exists():
            username_suggestions = generate_username_suggestions(attempted_username, count=5)
        
        # Validate both forms
        if user_form.is_valid() and donor_form.is_valid():
            try:
                # Use transaction to ensure both user and donor are created together
                with transaction.atomic():
                    # Save user as active immediately
                    user = user_form.save(commit=False)
                    user.is_active = True
                    user.save()
                    
                    # Save donor profile
                    donor = donor_form.save(commit=False)
                    donor.user = user
                    donor.save()
                    
                    # Add user to DONOR group
                    donor_group, created = Group.objects.get_or_create(name='DONOR')
                    donor_group.user_set.add(user)
                
                # Log the registration
                logger.info(f"New donor registration: {user.username} - Account active")
                
                # Success message
                messages.success(
                    request, 
                    f"🎉 Registration successful, {user.first_name}! "
                    f"Your account has been created. You can now login."
                )
                
                # Redirect to donor login
                return redirect('donorlogin')
                
            except Exception as e:
                # Log the error for debugging
                logger.error(f"Donor signup error: {str(e)}", exc_info=True)
                
                # Clean up: delete the user if donor creation fails
                if 'user' in locals():
                    user.delete()
                
                messages.error(
                    request, 
                    f"⚠️ An unexpected error occurred during registration. "
                    f"Please try again or contact support if the issue persists."
                )
        else:
            # Display form validation errors
            if user_form.errors or donor_form.errors:
                error_count = len(user_form.errors) + len(donor_form.errors)
                messages.error(
                    request, 
                    f"⚠️ Please correct the {error_count} error(s) highlighted below in red."
                )
    else:
        user_form = DonorUserForm()
        donor_form = DonorForm()
    
    return render(request, 'donor/donorsignup.html', {
        'user_form': user_form,
        'donor_form': donor_form,
        'username_suggestions': username_suggestions,
    })
# -------------------------------
# Login
# -------------------------------
def donorlogin_view(request):
    """
    Handles donor login WITHOUT email verification requirement.
    Restricts login to users in DONOR group only.
    Redirects to eligibility form if not completed.
    Supports redirecting to 'next' url after successful login.
    """
    # If user is already authenticated and is a donor, redirect to dashboard
    if request.user.is_authenticated and request.user.groups.filter(name='DONOR').exists():
        return redirect('donor-dashboard')
    
    next_url = request.GET.get('next') or request.POST.get('next') or None

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                # CHECK 1: REMOVED EMAIL VERIFICATION CHECK
                # Users can now login even if email is not verified
                
                # CHECK 2: Donor Group Authorization
                if user.groups.filter(name='DONOR').exists():
                    # CHECK 3: Donor Profile Exists
                    if not hasattr(user, 'donor'):
                        messages.error(
                            request, 
                            '❌ Donor profile not found. '
                            'Please contact support to complete your registration.'
                        )
                        return render(request, 'donor/donorlogin.html', {
                            'form': form,
                            'next': next_url,
                        })
                    
                    # All checks passed - Login successful
                    login(request, user)
                    
                    # Check if email is verified
                    if not user.is_active:
                        messages.warning(
                            request,
                            f'⚠️ Please verify your email to access all features. '
                            f'Check your inbox for the verification email sent to {user.email}. '
                            f'<a href="{reverse("resend_verification")}" class="alert-link">'
                            f'Click here to resend verification email</a>'
                        )
                    
                    # Check eligibility completion
                    try:
                        donor = Donor.objects.get(user=user)
                        eligibility_completed = DonorEligibility.objects.filter(donor=donor).exists()
                    except Donor.DoesNotExist:
                        eligibility_completed = False
                    
                    # Log successful login
                    logger.info(f"Donor login successful: {user.username} ({user.email}) - Active: {user.is_active}")
                    
                    # Redirect in priority order
                    if next_url:
                        return redirect(next_url)
                    if not eligibility_completed:
                        messages.info(
                            request, 
                            "📋 Welcome! Please complete your eligibility form to start donating blood."
                        )
                        return redirect('donor-eligibility')
                    
                    messages.success(
                        request, 
                        f"👋 Welcome back, {user.first_name or user.username}! "
                        f"Ready to save lives today?"
                    )
                    return redirect('donor-dashboard')
                    
                else:
                    # User exists but not in DONOR group
                    messages.error(
                        request, 
                        '❌ You are not authorized to log in as a donor. '
                        'Please use the appropriate login page for your account type.'
                    )
                    
                    # Suggest correct login based on user's groups
                    if user.groups.filter(name='PATIENT').exists():
                        messages.info(
                            request,
                            f'It looks like you have a patient account. '
                            f'<a href="{reverse("central_login")}?user_type=patient" class="alert-link">'
                            f'Click here to login as a patient</a>'
                        )
                    elif user.groups.filter(name='NURSE').exists():
                        messages.info(
                            request,
                            f'It looks like you have a nurse account. '
                            f'<a href="{reverse("central_login")}?user_type=nurse" class="alert-link">'
                            f'Click here to login as a nurse</a>'
                        )
                    
            else:
                # Authentication failed
                messages.error(request, "❌ Invalid username or password.")
                
                # Provide helpful suggestions
                messages.info(
                    request,
                    'Forgot your password? '
                    f'<a href="{reverse("password_reset")}" class="alert-link">'
                    f'Click here to reset it</a>'
                )
        else:
            # Form validation errors
            messages.error(request, "⚠️ There was an error in your form. Please correct it.")
    else:
        form = AuthenticationForm()

    return render(request, 'donor/donorlogin.html', {
        'form': form,
        'next': next_url,
        'show_central_login_link': True,  # Add this to template context
    })

logger = logging.getLogger(__name__)


def needs_eligibility_check(user):
    """
    Returns True if donor exists but has NOT completed eligibility form.
    """
    try:
        donor = Donor.objects.get(user=user)
    except Donor.DoesNotExist:
        return False
    return not DonorEligibility.objects.filter(donor=donor).exists()

# -------------------------------
# Eligibility
# -------------------------------
@login_required(login_url='donorlogin')
def donor_eligibility_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        eligibility = None

    age = DonorEligibilityForm.calculate_age(donor.dob) if donor.dob else None

    if request.method == 'POST':
        form = DonorEligibilityForm(request.POST, instance=eligibility, donor=donor)
        if form.is_valid():
            eligibility_instance = form.save(commit=False)
            eligibility_instance.donor = donor

            # Ensure booleans are properly stored
            eligibility_instance.good_health = bool(eligibility_instance.good_health)
            eligibility_instance.travel_history = bool(eligibility_instance.travel_history)
            eligibility_instance.pregnant = bool(eligibility_instance.pregnant)

            # Eligibility check
            is_eligible = (
                age is not None and 18 <= age <= 65 and
                eligibility_instance.weight >= 50 and
                eligibility_instance.good_health and
                not eligibility_instance.travel_history and
                (eligibility_instance.gender != 'Female' or not eligibility_instance.pregnant)
            )

            eligibility_instance.approved = is_eligible
            eligibility_instance.save()

            if is_eligible:
                messages.success(request, "You are eligible to donate blood.")
            else:
                messages.warning(request, "Thank you for your interest! Currently, you are not eligible to donate blood.")

            return redirect('donor-dashboard')
        else:
            messages.error(request, "There were errors in the form. Please correct them.")
    else:
        form = DonorEligibilityForm(instance=eligibility, donor=donor)

    return render(request, 'donor/donor_eligibility_form.html', {
        'eligibility_form': form,
        'donor_age': age,
    })
    
 # -------------------------------
# Eligibility status badge
# -------------------------------   
@login_required(login_url='donorlogin')
def donor_eligibility_status_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        # Not eligible/no record -> redirect elsewhere or show message
        return redirect('donor-dashboard')  

    if not eligibility.approved:
       
        return redirect('donor-dashboard')

    # Eligible donors only reach here
    last_donation_date_display = "No previous donations recorded."

    last_donation = BloodDonate.objects.filter(donor=donor, status='approved').order_by('-id').first()
    if last_donation and last_donation.appointment_date:
        last_donation_date_display = last_donation.appointment_date.strftime("%B %Y")
    elif last_donation and hasattr(last_donation, 'created_at'):
        last_donation_date_display = last_donation.created_at.strftime("%B %Y")

    context = {
        'eligible': True,
        'last_donation_date': last_donation_date_display,
    }
    return render(request, 'donor/donor_eligibility.html', context)
# -------------------------------
# Dashboard
# -------------------------------
@login_required(login_url='donorlogin')
def donor_dashboard_view(request):
    """
    Donor dashboard with updated stats, points, eligibility, milestones, and recent donations.
    """
    user = request.user
    logger.debug(f"Accessing donor dashboard for user '{user.username}'")

    # Redirect if donor needs eligibility check
    if hasattr(user, 'donor') and user.donor and needs_eligibility_check(user):
        return redirect('donor-eligibility')

    donor = get_object_or_404(Donor, user=user)

    # ------------------------
    # Enhanced greeting system
    # ------------------------
    try:
        from blood.utils.greetings import get_donor_greeting
        # Get last donation for greeting
        last_donation_for_greeting = BloodDonate.objects.filter(
            donor=donor, 
            status__in=['approved', 'completed']
        ).order_by('-date').first()
        
        # Get upcoming appointments for greeting
        from nurse.models import Appointment
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
    except ImportError:
        # Fallback greeting if utils not available
        greeting_data = {
            'greeting': f"Welcome back, {donor.user.first_name or 'hero'}! 🦸",
            'context_message': "Your donations save lives every day!",
            'user_type': 'donor',
            'icon': '🦸',
            'is_hero': total_donations >= 1,
            'profile_pic': donor.profile_pic if hasattr(donor, 'profile_pic') else None
        }

    # ------------------------
    # Last donation & next eligibility
    # ------------------------
    last_donation = BloodDonate.objects.filter(
        donor=donor, 
        status__in=['approved', 'completed']
    ).order_by('-date').first()

    if last_donation:
        # Update donor.last_donation_date if outdated
        if not donor.last_donation_date or donor.last_donation_date < last_donation.date:
            donor.last_donation_date = last_donation.date
            donor.save(update_fields=['last_donation_date'])
            logger.debug(f"Updated last_donation_date for donor {donor.id}")

        next_donation_date = donor.next_eligible_donation_date()
        days_until_next = donor.days_until_next_donation()
        next_donation_date_iso = next_donation_date.isoformat() if next_donation_date else None
    else:
        next_donation_date = None
        days_until_next = 0
        next_donation_date_iso = None

    # ------------------------
    # Total points & donations
    # ------------------------
    total_donations = BloodDonate.objects.filter(
        donor=donor,
        status__in=['approved', 'completed']
    ).count()
    points_per_donation = 10
    computed_points = total_donations * points_per_donation

    # Sync points with database
    if donor.points != computed_points:
        donor.points = computed_points
        donor.save(update_fields=['points'])
        logger.debug(f"Updated points to {computed_points} for donor {donor.id}")

    # ------------------------
    # Progress visualization
    # ------------------------
    goal = 10
    progress = min(int((total_donations / goal) * 100), 100) if goal else 0
    circumference = 2 * 3.1416 * 65
    stroke_dashoffset = circumference * (1 - progress / 100)

    # ------------------------
    # Blood request stats
    # ------------------------
    dashboard_stats = [
        {'icon': 'fa-paper-plane', 'label': 'Requests Made', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor).count(), 'color': 'requests-made-icon', 'description': 'Blood requests submitted'},
        {'icon': 'fa-clock', 'label': 'Pending Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='pending').count(), 'color': 'pending-requests-icon', 'description': 'Awaiting approval'},
        {'icon': 'fa-check-circle', 'label': 'Approved Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='approved').count(), 'color': 'approved-requests-icon', 'description': 'Successfully approved'},
        {'icon': 'fa-times-circle', 'label': 'Rejected Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='rejected').count(), 'color': 'rejected-requests-icon', 'description': 'Not approved'},
    ]

    # ------------------------
    # Info cards
    # ------------------------
    info_cards = [
        {'icon': 'fa-heartbeat', 'title': 'Health Tips', 'desc': 'Stay hydrated and eat healthy foods before donating blood.', 'url': 'health_tips', 'color': 'health-tips'},
        {'icon': 'fa-question-circle', 'title': 'FAQs', 'desc': 'Find answers to common questions about blood donation.', 'url': 'faqs', 'color': 'faqs'},
        {'icon': 'fa-comments', 'title': 'Donor Advice', 'desc': 'How to prepare for your next donation and what to expect.', 'url': 'donor_advice', 'color': 'advice'},
        {'icon': 'fa-book', 'title': 'Donor Resources', 'desc': 'Learn more about blood donation processes and guidelines.', 'url': 'donor_resources', 'color': 'resources'},
    ]

    # ------------------------
    # Recent donations
    # ------------------------
    recent_donations = BloodDonate.objects.filter(donor=donor).select_related('donation_center').order_by('-date')[:5]

    # ------------------------
    # Eligibility
    # ------------------------
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
        is_eligible = eligibility.approved
    except DonorEligibility.DoesNotExist:
        is_eligible = False

    can_donate_now = is_eligible and (days_until_next == 0)

    # ------------------------
    # Milestones
    # ------------------------
    milestones = [5, 10, 25, 50, 100]
    next_milestone = next((m for m in milestones if total_donations < m), None)
    donations_to_milestone = next_milestone - total_donations if next_milestone else 0

    # ------------------------
    # Upcoming appointments
    # ------------------------
    try:
        from nurse.models import Appointment
        upcoming_appointments = Appointment.objects.filter(
            donor=donor,
            date__gte=timezone.now(),
            status='scheduled'
        ).select_related('nurse', 'nurse__donation_center').order_by('date')[:3]
    except:
        upcoming_appointments = []

    # ------------------------
    # Hero status & badges
    # ------------------------
    hero_level = "Bronze"
    hero_badge = None
    
    if total_donations >= 10:
        hero_level = "Gold"
        hero_badge = "🏆"
    elif total_donations >= 5:
        hero_level = "Silver"
        hero_badge = "🥈"
    elif total_donations >= 1:
        hero_level = "Bronze"
        hero_badge = "🥉"
    
    # Add hero info to greeting data
    if total_donations >= 1 and 'is_hero' not in greeting_data:
        greeting_data['is_hero'] = True
    if hero_badge and 'hero_badge' not in greeting_data:
        greeting_data['hero_badge'] = hero_badge
        greeting_data['hero_level'] = hero_level

    # Prepare metadata for greeting card
    meta_items = []
    if hasattr(donor, 'bloodgroup') and donor.bloodgroup:
        meta_items.append({
            'icon': 'fas fa-tint',
            'text': f"Blood Group: {donor.bloodgroup}"
        })
    
    meta_items.append({
        'icon': 'fas fa-heart',
        'text': f"{total_donations} donations"
    })
    
    meta_items.append({
        'icon': 'fas fa-trophy',
        'text': f"{hero_level} Hero"
    })
    
    # Add metadata to greeting data if not already present
    if 'meta_items' not in greeting_data and meta_items:
        greeting_data['meta_items'] = meta_items

    context = {
        'user': user,
        'donor': donor,
        'points': donor.points,
        'total_donations': total_donations,
        'goal': goal,
        'progress': progress,
        'stroke_dashoffset': stroke_dashoffset,
        'next_donation_date': next_donation_date.strftime("%b %d, %Y") if next_donation_date else None,
        'days_until_next': days_until_next,
        'next_donation_date_iso': next_donation_date_iso,
        'can_donate_now': can_donate_now,
        'is_eligible': is_eligible,
        'dashboard_stats': dashboard_stats,
        'info_cards': info_cards,
        'recent_donations': recent_donations,
        'upcoming_appointments': upcoming_appointments,
        'next_milestone': next_milestone,
        'donations_to_milestone': donations_to_milestone,
        'last_donation_date': donor.last_donation_date,
        'hero_level': hero_level,
        'hero_badge': hero_badge,
        'greeting_data': greeting_data,  # Add greeting data
        'current_date': timezone.now().date(),  # For the shared greeting template
    }

    logger.debug(f"Rendering donor dashboard for user '{user.username}' with {total_donations} approved/completed donations and {donor.points} points")
    return render(request, 'donor/donor_dashboard.html', context)

# -------------------------------
# DonateBloodView
# -------------------------------
logger = logging.getLogger(__name__)

@login_required(login_url='donorlogin')
def donate_blood_view(request):
    """
    View for donors to schedule blood donation appointments.
    Handles blood group verification:
    - First-time donors: Blood group is optional, will be verified by nurse
    - Verified donors: Blood group is pre-filled and read-only
    """
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "⚠️ You must complete your donor profile before donating blood.")
        return redirect('donor-profile')

    blocking_statuses = ['pending', 'approved']

    # Check for active donation
    active_donation = BloodDonate.objects.filter(
        donor=donor,
        status__in=blocking_statuses
    ).first()

    if active_donation:
        logger.info(f"Donor {donor.id} has active donation with status '{active_donation.status}'")
        # Show form but disable submission
        donate_form = BloodDonateForm(donor=donor)
        donate_form.fields['donation_center'].disabled = True
        donate_form.fields['nurse'].disabled = True
        donate_form.fields['appointment_date'].disabled = True
        donate_form.fields['appointment_time'].disabled = True
        
        return render(request, 'donor/donate_blood.html', {
            'donation_form': donate_form,
            'donor': donor,
            'active_donation': active_donation
        })
        
    # Check eligibility
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        messages.info(request, "ℹ️ Please complete your eligibility form before donating blood.")
        return redirect('donor-eligibility')

    if not eligibility.approved:
        messages.warning(request, "⚠️ Your eligibility has not been approved yet. Please wait for approval.")
        return redirect('donor-eligibility')

    # Log blood group verification status
    logger.info(f"Donor {donor.id} blood group verification status: {donor.bloodgroup_verified}")
    if donor.bloodgroup_verified:
        logger.info(f"Donor {donor.id} verified blood group: {donor.bloodgroup}")

    if request.method == 'POST':
        logger.info("📝 POST request received for donation form")
        
        # Log POST data for debugging
        logger.debug(f"POST data: {request.POST}")
        
        # Create form with POST data and donor context
        donate_form = BloodDonateForm(request.POST, donor=donor)
        
        if donate_form.is_valid():
            logger.info("✅ Form is valid")
            try:
                with transaction.atomic():
                    # Log cleaned data
                    logger.debug(f"Cleaned form data: {donate_form.cleaned_data}")
                    
                    # Update user profile
                    user = request.user
                    first_name = donate_form.cleaned_data.get('first_name')
                    last_name = donate_form.cleaned_data.get('last_name')
                    mobile = donate_form.cleaned_data.get('mobile')
                    bloodgroup = donate_form.cleaned_data.get('bloodgroup')
                    unit = donate_form.cleaned_data.get('unit', 0)
                    
                    if first_name and first_name != user.first_name:
                        user.first_name = first_name
                        user.save()
                        logger.info(f"Updated first name: {first_name}")
                    
                    if last_name and last_name != user.last_name:
                        user.last_name = last_name
                        user.save()
                        logger.info(f"Updated last name: {last_name}")
                    
                    if mobile and mobile != donor.mobile:
                        donor.mobile = mobile
                        logger.info(f"Updated mobile: {mobile}")

                    # Create donation request
                    donation = donate_form.save(commit=False)
                    donation.donor = donor
                    donation.status = 'pending'
                    
                    # ==========================================
                    # BLOOD GROUP HANDLING
                    # ==========================================
                    if donor.bloodgroup_verified:
                        # Use verified blood group regardless of form input
                        donation.bloodgroup = donor.bloodgroup
                        logger.info(f"✅ Using verified blood group {donor.bloodgroup} for donation")
                    else:
                        # First donation - blood group is optional (will be verified by nurse)
                        donation.bloodgroup = bloodgroup if bloodgroup else None
                        logger.info(f"ℹ️ First donation - blood group: {donation.bloodgroup or 'Not provided (will be verified by nurse)'}")
                    
                    # Set donation date from appointment_date form field
                    appointment_date = donate_form.cleaned_data.get('appointment_date')
                    if appointment_date:
                        donation.date = appointment_date  # Map to model's 'date' field
                        logger.info(f"Setting donation date to: {appointment_date}")
                    else:
                        donation.date = timezone.now().date()
                        logger.warning(f"No appointment date provided, using current date: {donation.date}")
                    
                    # Set donation volume (unit)
                    donation.unit = unit
                    logger.info(f"Setting donation unit to: {donation.unit} ml")
                    
                    # Save donor if mobile was updated
                    donor.save()
                    
                    # Save donation
                    donation.save()
                    logger.info(f"✅ Created BloodDonate ID: {donation.id}")
                    logger.info(f"   ├─ Donation Center: {donation.donation_center}")
                    logger.info(f"   ├─ Nurse: {donation.nurse}")
                    logger.info(f"   ├─ Date: {donation.date}")  # Changed from appointment_date to date
                    logger.info(f"   ├─ Unit: {donation.unit} ml")
                    logger.info(f"   └─ Status: {donation.status}")

                    # ==========================================
                    # CRITICAL FIX: Get ContentType for BloodDonate MODEL CLASS
                    # ==========================================
                    donation_ct = ContentType.objects.get_for_model(BloodDonate)
                    
                    # Detailed logging for verification
                    logger.info(f"🔍 ContentType Details:")
                    logger.info(f"   ├─ App Label: {donation_ct.app_label}")
                    logger.info(f"   ├─ Model: {donation_ct.model}")
                    logger.info(f"   └─ ID: {donation_ct.id}")
                    logger.info(f"🔍 BloodDonate ID to link: {donation.id}")

                    # Get appointment datetime from form data
                    appointment_date = donate_form.cleaned_data.get('appointment_date')
                    appointment_time_str = donate_form.cleaned_data.get('appointment_time')

                    if not appointment_date or not appointment_time_str:
                        logger.error("❌ Missing appointment date or time")
                        messages.error(request, "❌ Please select a valid appointment date and time.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor,
                            'bloodgroup_verified': donor.bloodgroup_verified,
                            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        })

                    try:
                        # Handle both string and time object types
                        if isinstance(appointment_time_str, str):
                            # Handle 24-hour format (09:00, 10:30, etc.)
                            if ':' in appointment_time_str:
                                if len(appointment_time_str) == 5:  # 09:00 format
                                    appointment_time = datetime.strptime(appointment_time_str.strip(), '%H:%M').time()
                                else:
                                    appointment_time = datetime.strptime(appointment_time_str.strip(), '%I:%M %p').time()
                            else:
                                raise ValueError(f"Invalid time format: {appointment_time_str}")
                        else:
                            appointment_time = appointment_time_str
                        logger.info(f"Parsed appointment time: {appointment_time}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Time parsing error: {e} for time string: '{appointment_time_str}'")
                        messages.error(request, "❌ Invalid appointment time format. Please select a valid time.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor,
                            'bloodgroup_verified': donor.bloodgroup_verified,
                            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        })

                    appointment_datetime = timezone.make_aware(
                        datetime.combine(appointment_date, appointment_time)
                    )
                    logger.info(f"Appointment datetime: {appointment_datetime}")

                    # Get nurse from form
                    nurse = donate_form.cleaned_data.get('nurse')
                    if not nurse:
                        logger.error("❌ No nurse selected")
                        messages.error(request, "❌ Please select a nurse.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor,
                            'bloodgroup_verified': donor.bloodgroup_verified,
                            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        })

                    logger.info(f"🔍 Selected nurse: {nurse.user.get_full_name()} (ID: {nurse.id})")

                    # Check for scheduling conflicts
                    appointment_duration = timedelta(minutes=30)
                    conflict_exists = Appointment.objects.filter(
                        nurse=nurse,
                        date__lt=appointment_datetime + appointment_duration,
                        date__gte=appointment_datetime,
                        status__in=['pending', 'approved']
                    ).exists()

                    if conflict_exists:
                        logger.warning(f"❌ Conflict found for nurse {nurse.id} at {appointment_datetime}")
                        messages.error(
                            request,
                            f"❌ Nurse {nurse.user.get_full_name()} is already booked during this slot. "
                            f"Please select a different time."
                        )
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor,
                            'bloodgroup_verified': donor.bloodgroup_verified,
                            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
                        })

                    # ==========================================
                    # CRITICAL: Create appointment with CORRECT ContentType
                    # ==========================================
                    appointment = Appointment.objects.create(
                        donor=donor,
                        patient=None,  # MUST be None for donations
                        nurse=nurse,
                        date=appointment_datetime,
                        status='pending',
                        donation_center=donation.donation_center,  # Link to donation center
                        request_content_type=donation_ct,  # ← Use BloodDonate ContentType
                        request_object_id=donation.id,     # ← Link to BloodDonate instance
                    )
                    
                    # Comprehensive verification logging
                    logger.info(f"✅ Created Appointment ID: {appointment.id}")
                    logger.info(f"   ├─ Donor: {appointment.donor_id} ({appointment.donor})")
                    logger.info(f"   ├─ Patient: {appointment.patient_id} (should be None)")
                    logger.info(f"   ├─ Nurse: {appointment.nurse_id} ({appointment.nurse})")
                    logger.info(f"   ├─ Donation Center: {appointment.donation_center_id}")
                    logger.info(f"   ├─ ContentType: {appointment.request_content_type}")
                    logger.info(f"   ├─ ContentType ID: {appointment.request_content_type_id}")
                    logger.info(f"   ├─ Object ID: {appointment.request_object_id}")
                    logger.info(f"   └─ Status: {appointment.status}")
                    
                    # Double-check ContentType is correct
                    if appointment.request_content_type != donation_ct:
                        error_msg = (
                            f"❌ CRITICAL ERROR: ContentType mismatch detected!\n"
                            f"   Expected: {donation_ct.app_label}.{donation_ct.model} (ID: {donation_ct.id})\n"
                            f"   Got: {appointment.request_content_type}"
                        )
                        logger.error(error_msg)
                        raise ValueError("ContentType mismatch - appointment creation failed!")
                    else:
                        logger.info(f"✅ ContentType verification PASSED: {donation_ct.app_label}.{donation_ct.model}")
                    
                    # Verify appointment can be found by nurse view query
                    test_query = Appointment.objects.filter(
                        nurse=nurse,
                        request_content_type=donation_ct,
                        donor__isnull=False,
                    )
                    logger.info(f"✅ Nurse query test: Found {test_query.count()} donation appointment(s)")

                # After transaction success, send notification
                try:
                    Notification.objects.create(
                        title="🩸 New Blood Donation Appointment",
                        message=(
                            f"Donor {donor.user.get_full_name()} scheduled a donation on "
                            f"{appointment_datetime.strftime('%b %d, %Y %I:%M %p')}. "
                            f"{'Blood group verified: ' + donor.bloodgroup if donor.bloodgroup_verified else 'First donation - blood group to be verified.'}"
                        ),
                        recipient=nurse,
                        sender=donor,
                    )
                    logger.info(f"✅ Notification sent to nurse {nurse.id}")
                except Exception as e:
                    logger.error(f"❌ Failed to send notification: {e}")

                # Success message with blood group verification status
                success_msg = "✅ Your donation request and appointment were submitted successfully!"
                if donor.bloodgroup_verified:
                    success_msg += f" (Blood group: {donor.bloodgroup})"
                else:
                    success_msg += " Your blood group will be verified by the nurse during donation."
                
                messages.success(request, success_msg)
                return redirect('donation-history')

            except ValidationError as ve:
                logger.error(f"❌ Validation Error: {ve}")
                messages.error(request, f"❌ Validation Error: {str(ve)}")
            except ValueError as ve:
                logger.error(f"❌ ValueError: {ve}")
                messages.error(request, f"❌ System Error: {str(ve)}")
            except Exception as e:
                logger.exception("❌ Exception during donate_blood_view POST")
                messages.error(request, f"❌ An unexpected error occurred: {str(e)}")
        else:
            logger.warning(f"❌ Form is invalid. Errors: {donate_form.errors}")
            messages.error(request, "⚠️ Please correct the errors in the form below.")
            
            # Debug form errors
            for field, errors in donate_form.errors.items():
                logger.debug(f"Field '{field}' errors: {errors}")
    else:
        # GET request - initialize form with donor data
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
        
        logger.info(f"Form initialized for donor {donor.id}")

    # Add blood group verification info to context
    context = {
        'donation_form': donate_form,
        'donor': donor,
        'active_donation': None,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
    }

    return render(request, 'donor/donate_blood.html', context)

# -------------------------------
# Donation History
# -------------------------------
@login_required(login_url='donorlogin')
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

        # Notify nurses at the donation center
        try:
            center = getattr(appointment, 'donation_center', None) or getattr(donation, 'donation_center', None)
            nurses = Nurse.objects.filter(donation_center=center) if center else Nurse.objects.all()
            for nurse in nurses:
                Notification.objects.create(
                    title="Donation Appointment Cancelled",
                    message=(
                        f"Donor {user.get_full_name() or user.username} cancelled their donation appointment "
                        f"(ID: {appointment.id}) scheduled for {appointment.date.strftime('%b %d, %Y %I:%M %p')}."
                    ),
                    recipient=nurse,
                    sender=user.donor
                )
            logger.info(f"Nurses at {center} notified about donor cancellation (Appointment ID: {appointment.id}).")
        except Exception as e:
            logger.warning(f"Failed to notify nurses about donor cancellation (Appointment ID: {appointment.id}): {e}")

    messages.success(request, "Your donation request and appointment have been cancelled successfully.")
    return redirect('donation-history')


# -------------------------------
# profile
# -------------------------------
@login_required(login_url='donorlogin')
def donor_profile_view(request):
    """
    Display donor profile with blood group verification status.
    """
    donor = get_object_or_404(Donor, user=request.user)
    user = request.user

    # Calculate next eligible donation date, days until next donation
    next_donation_date = donor.next_eligible_donation_date()
    days_until_next = donor.days_until_next_donation()

    context = {
        'donor': donor,
        'user': user,
        'next_donation_date': next_donation_date,
        'days_until_next': days_until_next,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
    }
    return render(request, 'donor/donor_profile.html', context)

# -------------------------------
# Edit Profile
# -------------------------------
@login_required(login_url='donorlogin')
def donor_edit_profile_view(request):
    """
    Allow a donor to edit their profile.
    Blood group becomes read-only after nurse verification.
    Email is always read-only.
    """
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "Please create a donor profile first.")
        return redirect('create-donor-profile')
    
    user = request.user
    
    # Store original read-only values for integrity check
    original_email = user.email
    original_bloodgroup = donor.bloodgroup if donor.bloodgroup_verified else None
    original_verified_status = donor.bloodgroup_verified
    
    logger.info(f"Editing profile for donor {donor.id}")
    logger.info(f"Blood group verified: {donor.bloodgroup_verified}")
    logger.info(f"Current blood group: {donor.bloodgroup}")
    
    if request.method == 'POST':
        form = DonorProfileForm(request.POST, request.FILES, instance=donor)
        
        # Handle latitude and longitude from POST explicitly
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')
        
        if lat:
            try:
                donor.latitude = float(lat)
            except ValueError:
                messages.warning(request, "Invalid latitude value.")
        
        if lon:
            try:
                donor.longitude = float(lon)
            except ValueError:
                messages.warning(request, "Invalid longitude value.")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Update first and last names on User
                    user.first_name = form.cleaned_data.get('first_name', user.first_name)
                    user.last_name = form.cleaned_data.get('last_name', user.last_name)
                    
                    # SECURITY: Restore original email to prevent tampering
                    user.email = original_email
                    user.save()
                    
                    # Handle base64 cropped image if provided
                    cropped_image_data = request.POST.get('cropped_image')
                    if cropped_image_data:
                        try:
                            format, imgstr = cropped_image_data.split(';base64,')
                            ext = format.split('/')[-1]
                            data = ContentFile(base64.b64decode(imgstr), name='profile.' + ext)
                            donor.profile_pic = data
                        except Exception as e:
                            logger.error(f"Error processing cropped image: {e}")
                            messages.error(request, f"Error processing cropped image: {e}")
                    
                    # Save Donor instance with updated data
                    donor_instance = form.save(commit=False)
                    
                    # SECURITY: Restore original verified blood group and verification status
                    if original_verified_status:
                        donor_instance.bloodgroup = original_bloodgroup
                        donor_instance.bloodgroup_verified = True
                        donor_instance.bloodgroup_verified_by = donor.bloodgroup_verified_by
                        donor_instance.bloodgroup_verified_at = donor.bloodgroup_verified_at
                        
                        logger.info(f"✅ Protected verified blood group: {original_bloodgroup}")
                    
                    # Update latitude/longitude if provided
                    if lat:
                        try:
                            donor_instance.latitude = float(lat)
                        except ValueError:
                            pass
                    if lon:
                        try:
                            donor_instance.longitude = float(lon)
                        except ValueError:
                            pass
                    
                    donor_instance.save()
                    
                    logger.info(f"✅ Profile updated successfully for donor {donor.id}")
                    messages.success(request, "✅ Profile updated successfully!")
                    return redirect('donor-profile')
                    
            except Exception as e:
                logger.error(f"Error saving profile for donor {donor.id}: {e}", exc_info=True)
                messages.error(request, f"An error occurred while saving: {str(e)}")
        else:
            messages.error(request, "Please correct the errors in the form.")
            logger.error(f"Form validation errors: {form.errors}")
    else:
        # Initial data for first_name, last_name, and email come from User model
        form = DonorProfileForm(instance=donor, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })
    
    context = {
        'profile_form': form,
        'donor': donor,
        'user': user,
        'bloodgroup_verified': donor.bloodgroup_verified,
        'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
    }
    return render(request, 'donor/donor_edit_profile.html', context)

# -------------------------------
# Notifications
# -------------------------------
@login_required(login_url='donorlogin')
def donor_notifications_view(request):
    donor = get_object_or_404(Donor, user=request.user)
    donor_ct = ContentType.objects.get_for_model(donor)

    notifications = Notification.objects.filter(
        recipient_content_type=donor_ct,
        recipient_object_id=donor.id
    ).order_by('-created_at')

    unread_count = notifications.filter(read=False).count()

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
    notification = get_object_or_404(Notification, id=pk, recipient_content_type=donor_ct, recipient_object_id=donor.id)
    notification.read = True
    notification.save()
    return redirect('donor-notifications')

# -------------------------------
# Make Request (on behalf of patients)
# -------------------------------
@login_required(login_url='login')
def donor_make_request_view(request):
    """
    View for donors to make blood requests on behalf of patients
    Direct submission to blood bank technicians (NO APPOINTMENTS)
    """
    user = request.user
    
    # Check if user is a donor
    if not hasattr(user, "donor"):
        raise PermissionDenied("Only donors can make donor-side requests.")

    donor = user.donor
    centers = DonationCenter.objects.all()
    form_errors = {}

    # Check for active donor blood requests (pending only)
    active_request = donor.submitted_patient_requests.filter(
        status='pending'  # Only pending, not approved
    ).first()

    # If there's an active request, show pending page
    if active_request:
        return render(request, "donor/donormakerequest.html", {
            "pending_request": active_request,
            "centers": centers,
            "request_form": DonorBloodRequestForm(),
        })

    # No active request → show the form
    if request.method == "POST":
        request_form = DonorBloodRequestForm(request.POST)
        donation_center_id = request.POST.get("donation_center")

        # Validate center
        center_instance = DonationCenter.objects.filter(id=donation_center_id).first()

        if not center_instance:
            messages.error(request, "❌ Invalid blood bank center selected.")
            form_errors['donation_center'] = ['Please select a valid blood bank center.']

        # Validate consent
        consent_confirmed = request.POST.get('consent_confirmed') == 'on'

        # Proceed if form is valid and center exists
        if request_form.is_valid() and center_instance and consent_confirmed:
            try:
                with transaction.atomic():
                    # Save donor blood request directly (NO APPOINTMENT)
                    blood_request = request_form.save(commit=False)
                    blood_request.request_by_donor = donor
                    blood_request.donation_center = center_instance
                    blood_request.status = 'pending'
                    blood_request.consent_confirmed = True
                    blood_request.save()

                    # 🔔 SEND NOTIFICATION TO BLOOD BANK TECHNICIANS
                    from blood_bank_technician.models import BloodBankTechProfile
                    
                    # Notify all blood bank techs at this center
                    blood_bank_techs = BloodBankTechProfile.objects.filter(
                        center=center_instance,
                        is_active=True
                    )
                    
                    donor_name = donor.user.get_full_name() or donor.user.username
                    
                    for tech in blood_bank_techs:
                        create_notification(
                            title="🩸 New Donor Blood Request",
                            message=(
                                f"Donor {donor_name} has submitted a blood request on behalf of a patient.\n"
                                f"Patient: {blood_request.patient_first_name} {blood_request.patient_last_name}\n"
                                f"Blood Group: {blood_request.bloodgroup}\n"
                                f"Units Needed: {blood_request.unit}ml\n"
                                f"Center: {center_instance.name}"
                            ),
                            recipient_obj=tech,
                            sender_obj=donor,
                            action="new_donor_blood_request",
                            bloodgroup=blood_request.bloodgroup,
                            unit=blood_request.unit
                        )

                    # Also send confirmation to donor
                    create_notification(
                        title="Blood Request Submitted",
                        message=(
                            f"Your blood request for {blood_request.patient_first_name} {blood_request.patient_last_name} "
                            f"({blood_request.unit}ml of {blood_request.bloodgroup}) has been submitted to {center_instance.name}. "
                            f"A blood bank technician will review it shortly."
                        ),
                        recipient_obj=donor,
                        sender_obj=None,
                        action="request_submitted"
                    )
                    
                    messages.success(
                        request, 
                        f"✅ Blood request submitted successfully! The blood bank will review it shortly."
                    )
                    return redirect("donor-request-history")

            except ValidationError as ve:
                if hasattr(ve, 'message_dict'):
                    form_errors.update(ve.message_dict)
                else:
                    form_errors['non_field_errors'] = [str(ve)]
                    
            except Exception as e:
                messages.error(request, f"❌ An error occurred while creating your request: {str(e)}")
                form_errors['non_field_errors'] = [str(e)]
                
        else:
            # Form validation failed
            if not request_form.is_valid():
                messages.error(request, "❌ Please correct the errors in the blood request form.")
                form_errors.update(request_form.errors)
            
            if not consent_confirmed:
                messages.error(request, "❌ You must confirm your consent to submit the request.")
                form_errors['consent_confirmed'] = ['Consent is required.']

        # Return with form that contains POST data and errors
        return render(request, "donor/donormakerequest.html", {
            "request_form": request_form,
            "centers": centers,
            "pending_request": None,
            "form_errors": form_errors,
            "no_appointment": True,
        })

    else:
        # GET request - initialize empty form
        request_form = DonorBloodRequestForm()

        return render(request, "donor/donormakerequest.html", {
            "request_form": request_form,
            "centers": centers,
            "pending_request": None,
            "form_errors": form_errors,
            "no_appointment": True,
        })


@login_required(login_url='login')
def donor_request_history_view(request):
    """
    View for donors to see their blood request history
    """
    user = request.user
    
    # Check if user is a donor
    if not hasattr(user, "donor"):
        raise PermissionDenied("Only donors can access this page.")

    donor = user.donor
    
    # Get all blood requests made by this donor
    blood_requests = DonorBloodRequest.objects.filter(
        request_by_donor=donor
    ).select_related(
        'donation_center',
        'approved_by__user',
        'reviewed_by__user',
        'dispatched_by__user'
    ).order_by('-created_at')
    
    return render(request, 'donor/donor_request_history.html', {
        'blood_requests': blood_requests,
        'now': timezone.now(),
    })


@login_required(login_url='login')
def donor_cancel_request_view(request, request_id):
    """
    Cancel a pending blood request made by a donor
    """
    user = request.user
    
    # Check if user is a donor
    if not hasattr(user, "donor"):
        raise PermissionDenied("Only donors can cancel their requests.")

    donor = user.donor

    blood_request = get_object_or_404(
        DonorBloodRequest,
        id=request_id,
        request_by_donor=donor
    )

    now = timezone.now()

    # Only allow cancellation of pending requests
    if blood_request.status == 'pending':
        # Get cancellation reason from POST if provided
        reason = request.POST.get('reason', '').strip()
        
        # Update request status
        blood_request.status = 'cancelled'
        blood_request.save(update_fields=['status'])

        # 🔔 SEND NOTIFICATION TO BLOOD BANK TECHNICIANS
        from blood_bank_technician.models import BloodBankTechProfile
        
        # Notify all blood bank techs at this center
        blood_bank_techs = BloodBankTechProfile.objects.filter(
            center=blood_request.donation_center,
            is_active=True
        )
        
        donor_name = donor.user.get_full_name() or donor.user.username
        
        for tech in blood_bank_techs:
            create_notification(
                title="🚫 Donor Blood Request Cancelled",
                message=(
                    f"Donor {donor_name} has cancelled their blood request for patient "
                    f"{blood_request.patient_first_name} {blood_request.patient_last_name}.\n"
                    f"Blood Group: {blood_request.bloodgroup}\n"
                    f"Units: {blood_request.unit}ml\n"
                    f"Reason: {reason if reason else 'No reason provided'}"
                ),
                recipient_obj=tech,
                sender_obj=donor,
                action="request_cancelled",
                bloodgroup=blood_request.bloodgroup,
                unit=blood_request.unit
            )

        # Also send confirmation to donor
        create_notification(
            title="Request Cancelled",
            message=(
                f"Your blood request for {blood_request.patient_first_name} {blood_request.patient_last_name} "
                f"({blood_request.unit}ml of {blood_request.bloodgroup}) has been cancelled successfully."
            ),
            recipient_obj=donor,
            sender_obj=None,
            action="cancelled"
        )

        messages.success(request, "✅ Your blood request has been cancelled successfully.")
    else:
        # Determine why it can't be cancelled
        if blood_request.status == 'approved':
            messages.warning(request, "⚠️ This request has already been approved and cannot be cancelled. Please contact the blood bank directly.")
        elif blood_request.status == 'dispatched':
            messages.warning(request, "⚠️ This request has already been dispatched and cannot be cancelled.")
        elif blood_request.status == 'completed':
            messages.warning(request, "⚠️ This request has already been completed.")
        elif blood_request.status == 'rejected':
            messages.warning(request, "⚠️ This request has already been rejected.")
        elif blood_request.status == 'cancelled':
            messages.warning(request, "⚠️ This request is already cancelled.")
        else:
            messages.warning(request, "⚠️ This request cannot be cancelled at this stage.")

    return redirect('donor-request-history')

# -------------------------------
# Health tips
# -------------------------------
def health_tips(request):
    return render(request, 'donor/health_tips.html')

# -------------------------------
# FaQs
# -------------------------------
def faqs(request):
    return render(request, 'donor/faqs.html')

# -------------------------------
# Advice
# -------------------------------
def donor_advice(request):
    return render(request, 'donor/donor_advice.html')

# -------------------------------
# Resources
# -------------------------------
def donor_resources(request):
    return render(request, 'donor/donor_resources.html')

