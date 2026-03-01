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
from phlebotomist.models import Phlebotomist, Appointment
from .models import Donor, DonorEligibility, BloodDonate
from blood.models import BloodDriveEvent
from .forms import (
    DonorUserForm, DonorForm, DonorProfileForm, DonorEligibilityForm,
    BloodDonateForm, DonorLoginForm
)
from django.core.exceptions import PermissionDenied
from utils.models import Notification
from phlebotomist.forms import AppointmentForm
from datetime import date
import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.html import strip_tags
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from blood.models import DonationCenter
from datetime import time
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
                return redirect('donor:donorlogin')
                
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
        return redirect('donor:donor-dashboard')
    
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
                        return redirect('donor:donor-eligibility')
                    
                    messages.success(
                        request, 
                        f"👋 Welcome back, {user.first_name or user.username}! "
                        f"Ready to save lives today?"
                    )
                    return redirect('donor:donor-dashboard')
                    
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
                            f'Click here to login as a patient</a>'
                        )
                    elif user.groups.filter(name='NURSE').exists():
                        messages.info(
                            request,
                            f'It looks like you have a phlebotomist account. '
                            f'<a href="{reverse("central_login")}?user_type=phlebotomist" class="alert-link">'
                            f'Click here to login as a phlebotomist</a>'
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

# Remove the decorator - this function is called internally
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
        
        # Check if eligibility exists (use try/except or hasattr)
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

def check_dashboard_access(user):
    """
    Main function to determine dashboard access and display options.
    Used in donor_dashboard_view to set up the context.
    """
    context = {
        'can_access_full_dashboard': True,  # Always true now
        'show_eligibility_modal': False,
        'show_support_options': False,
        'eligibility_status': None,
        'volunteer_suggestions': [],
        'motivational_message': '',
    }
    
    if not user.is_authenticated:
        return context
    
    # Get eligibility status
    status = get_donor_eligibility_status(user)
    context['eligibility_status'] = status
    
    # Check if we should show eligibility modal (new donors)
    context['show_eligibility_modal'] = should_show_eligibility_modal(user)
    
    # Show support options for non-eligible or new donors
    if status['show_support_options'] or status['needs_eligibility_form']:
        context['show_support_options'] = True
        context['volunteer_suggestions'] = get_volunteer_suggestions(user)
    
    # Set motivational message based on status
    if status['is_eligible']:
        if status['can_donate']:
            context['motivational_message'] = "You're eligible to donate! Schedule your appointment today and save lives."
        else:
            context['motivational_message'] = "You're eligible! Your next donation date is coming up soon."
    elif status['has_eligibility']:
        context['motivational_message'] = "Everyone has a role in saving lives. Explore volunteer opportunities!"
    else:
        context['motivational_message'] = "Welcome! Whether you donate or support, you can make a difference."
    
    return context

# -------------------------------
# Eligibility
# -------------------------------
@login_required(login_url='donor:donorlogin')
def donor_eligibility_view(request):
    """
    Enhanced donor eligibility view with REAL-WORLD blood donation criteria.
    Based on Kenyan and international blood donation standards.
    """
    donor = get_object_or_404(Donor, user=request.user)

    # Check if eligibility already exists
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
        messages.info(request, "You've already completed the eligibility form. View your status below.")
        return redirect('donor:donor-eligibility-status')
    except DonorEligibility.DoesNotExist:
        eligibility = None

    age = DonorEligibilityForm.calculate_age(donor.dob) if donor.dob else None

    if request.method == 'POST':
        form = DonorEligibilityForm(request.POST, instance=eligibility, donor=donor)
        if form.is_valid():
            eligibility_instance = form.save(commit=False)
            eligibility_instance.donor = donor

            # Get all form data
            weight = eligibility_instance.weight
            good_health = bool(eligibility_instance.good_health)
            travel_history = bool(eligibility_instance.travel_history)
            pregnant = bool(eligibility_instance.pregnant) if eligibility_instance.pregnant is not None else False
            
            # Get additional fields from form
            recent_surgery = form.cleaned_data.get('recent_surgery', False)
            recent_tattoo = form.cleaned_data.get('recent_tattoo', False)
            tattoo_date = form.cleaned_data.get('tattoo_date')
            recent_childbirth = form.cleaned_data.get('recent_childbirth', False)
            breastfeeding = form.cleaned_data.get('breastfeeding', False)
            medications = form.cleaned_data.get('medications', '')
            medical_conditions = form.cleaned_data.get('medical_conditions', '')
            
            # ==========================================
            # REAL-WORLD ELIGIBILITY CRITERIA
            # ==========================================
            
            reasons = []
            recommendations = []
            is_eligible = True  # Start as True, then check each criterion
            
            # 1. AGE CHECK (Kenya: 16-65 years)
            if age is None:
                reasons.append("• Age could not be determined from your date of birth")
                is_eligible = False
            elif age < 16:
                reasons.append(f"• Minimum age requirement: 16 years (you are {age} years old)")
                recommendations.append("You can register to donate when you turn 16.")
                is_eligible = False
            elif age > 65:
                if age > 75:
                    reasons.append(f"• Maximum age for blood donation: 65 years (you are {age} years old)")
                    recommendations.append("Donors over 65 need physician approval and must be regular donors.")
                    is_eligible = False
                else:
                    # 66-75: Requires physician approval
                    recommendations.append("Donors over 65 need a physician's approval. Please consult your doctor.")
                    # Still can be eligible with doctor's note
            
            # 2. WEIGHT CHECK (Kenya: Minimum 50kg)
            if weight < 50:
                reasons.append(f"• Minimum weight requirement: 50kg (you entered {weight}kg)")
                recommendations.append("Focus on healthy weight gain through balanced nutrition before donating.")
                is_eligible = False
            elif weight < 55 and age < 18:
                # Additional safety for young donors
                recommendations.append("Young donors under 18 with lower weight should consult with our phlebotomist.")
            
            # 3. HEALTH STATUS
            if not good_health:
                reasons.append("• You must be in good health on the day of donation")
                recommendations.append("Common cold, flu, or any infection requires waiting until fully recovered.")
                is_eligible = False
            
            # 4. TATTOO/PERCING RULE (6-12 month wait in most countries)
            if recent_tattoo:
                if tattoo_date:
                    from datetime import date
                    today = date.today()
                    months_since_tattoo = (today.year - tattoo_date.year) * 12 + (today.month - tattoo_date.month)
                    
                    if months_since_tattoo < 6:
                        reasons.append(f"• Tattoo/piercing requires 6-month waiting period (only {months_since_tattoo} months ago)")
                        recommendations.append("You can donate 6 months after getting a tattoo or piercing in a regulated facility.")
                        is_eligible = False
                    elif months_since_tattoo < 12 and tattoo_date.year < 2020:
                        # Tattoos in unregulated facilities may need 12 months
                        recommendations.append("If your tattoo was done in an unregulated facility, please wait 12 months.")
                else:
                    reasons.append("• Recent tattoo/piercing requires waiting period")
                    recommendations.append("Please specify when you got the tattoo/piercing.")
                    is_eligible = False
            
            # 5. SURGERY RULE (Varies by procedure)
            if recent_surgery:
                reasons.append("• Recent surgery requires waiting period (usually 3-12 months)")
                recommendations.append("Please consult with our phlebotomist about your specific surgery.")
                is_eligible = False
            
            # 6. TRAVEL HISTORY (Malaria risk areas)
            if travel_history:
                travel_destination = form.cleaned_data.get('travel_destination', '')
                travel_duration = form.cleaned_data.get('travel_duration', 0)
                
                malaria_risk_countries = ['Nigeria', 'DRC', 'Mozambique', 'Uganda', 'Tanzania', 
                                         'Malawi', 'Zambia', 'Zimbabwe', 'Kenya (coastal)']
                
                # Check if travel was to malaria-endemic area
                if any(country.lower() in travel_destination.lower() for country in malaria_risk_countries):
                    reasons.append("• Travel to malaria-endemic area requires 6-month waiting period")
                    recommendations.append("You can donate 6 months after returning from a malaria-risk area.")
                    is_eligible = False
                else:
                    # Non-malaria travel - 28 days wait for other risks
                    recommendations.append("Please wait 28 days after international travel to ensure no illness develops.")
            
            # 7. PREGNANCY & CHILDBIRTH
            if pregnant:
                reasons.append("• Pregnancy temporarily prevents blood donation")
                recommendations.append("You can donate 6 weeks after pregnancy ends.")
                is_eligible = False
            elif recent_childbirth:
                reasons.append("• Recent childbirth requires 6-week waiting period")
                recommendations.append("You can donate 6 weeks after delivery if you're feeling well.")
                is_eligible = False
            elif breastfeeding:
                recommendations.append("Breastfeeding mothers should wait 6 weeks after delivery and ensure adequate nutrition.")
                # Usually allowed but with caution
            
            # 8. MEDICAL CONDITIONS (Common deferrals)
            serious_conditions = [
                'hepatitis', 'hiv', 'aids', 'cancer', 'leukemia', 'lymphoma',
                'heart disease', 'stroke', 'bleeding disorder', 'sickle cell',
                'diabetes with complications', 'epilepsy', 'tuberculosis'
            ]
            
            if medical_conditions:
                medical_lower = medical_conditions.lower()
                for condition in serious_conditions:
                    if condition in medical_lower:
                        reasons.append(f"• {condition.title()} may affect eligibility")
                        recommendations.append("Please discuss your condition with our medical staff.")
                        is_eligible = False
                        break
            
            # 9. MEDICATIONS (Some require waiting)
            deferral_medications = [
                'accutane', 'isotretinoin', 'finasteride', 'propecia',
                'blood thinners', 'warfarin', 'aspirin', 'heparin',
                'antibiotics', 'steroids'
            ]
            
            if medications:
                med_lower = medications.lower()
                for med in deferral_medications:
                    if med in med_lower:
                        if med in ['accutane', 'isotretinoin']:
                            reasons.append(f"• {med} requires 1-month waiting period after stopping")
                        elif med in ['blood thinners', 'warfarin']:
                            reasons.append(f"• {med} requires waiting period (consult doctor)")
                        else:
                            reasons.append(f"• {med} may require temporary deferral")
                        recommendations.append("Please inform our phlebotomist about your medications.")
                        is_eligible = False
                        break
            
            # 10. BLOOD PRESSURE & OTHER VITALS (from form)
            high_bp = form.cleaned_data.get('high_blood_pressure', False)
            if high_bp:
                reasons.append("• Uncontrolled high blood pressure may affect eligibility")
                recommendations.append("Blood pressure should be below 180/100 on donation day.")
                # Not automatically disqualified if controlled
            
            # 11. ANEMIA / LOW IRON (from form)
            anemia = form.cleaned_data.get('anemia', False)
            if anemia:
                reasons.append("• Anemia or low iron requires treatment before donating")
                recommendations.append("Please treat anemia and have hemoglobin checked before donating.")
                is_eligible = False
            
            # Set eligibility based on all criteria
            eligibility_instance.approved = is_eligible
            eligibility_instance.save()

            # Build detailed feedback message
            if is_eligible:
                messages.success(
                    request, 
                    "✅ Great news! Based on your responses, you appear eligible to donate blood. "
                    "Our phlebotomist will do a final health screening on donation day."
                )
                
                # Create notification
                try:
                    from utils.models import Notification
                    Notification.objects.create(
                        title="🩸 You're Likely Eligible!",
                        message="You appear eligible to donate! Schedule your appointment today. Final screening will be done by our phlebotomist.",
                        recipient=donor.user,
                        notification_type='success'
                    )
                except:
                    pass
                    
            else:
                # Main message with encouraging tone
                messages.info(
                    request,
                    "🌟 You can still be a hero! While you may have temporary deferrals, "
                    "there are many other ways to support our mission."
                )
                
                # Show specific reasons
                if reasons:
                    messages.warning(
                        request,
                        "📋 Based on your responses, here's why you may not be eligible right now:\n" + 
                        "\n".join(reasons[:5])
                    )
                
                # Offer recommendations
                if recommendations:
                    messages.info(
                        request,
                        "💡 Recommendations:\n" + 
                        "\n".join(recommendations[:3])
                    )
                
                # Create notification for non-eligible
                try:
                    from utils.models import Notification
                    Notification.objects.create(
                        title="🌟 Alternative Ways to Help",
                        message="While you may have temporary deferrals, we'd love your support in other ways! Check out volunteer opportunities.",
                        recipient=donor.user,
                        notification_type='info'
                    )
                except:
                    pass

            return redirect('donor:donor-eligibility-status')
        else:
            error_count = len(form.errors)
            messages.error(
                request, 
                f"⚠️ Please correct the {error_count} error(s) highlighted below."
            )
    else:
        form = DonorEligibilityForm(instance=eligibility, donor=donor)
        
        # Add initial data from donor profile
        if donor:
            form.fields['weight'].initial = getattr(donor, 'weight', None)
            form.fields['gender'].initial = getattr(donor, 'gender', None)

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
    
    # Prepare eligibility details for display - FIX: Use updated_at instead of created_at
    eligibility_details = {
        'age': age,
        'weight': eligibility.weight,
        'gender': eligibility.get_gender_display() if hasattr(eligibility, 'get_gender_display') else eligibility.gender,
        'good_health': 'Yes' if eligibility.good_health else 'No',
        'travel_history': 'Yes' if eligibility.travel_history else 'No',
        'medical_conditions': eligibility.medical_conditions or 'None reported',
        # FIX: Use updated_at instead of created_at
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
            'show_verification_option': not donor.bloodgroup_verified,  # Show if blood group not verified
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
            'show_verification_option': not donor.bloodgroup_verified and age >= 16,  # Show if blood group not verified
            'show_contact_option': True,
        }
    
    # Add common context - FIX: Use hasattr checks
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
def donor_dashboard_view(request):
    """
    Donor dashboard with updated stats, points, eligibility, milestones, and recent donations.
    Includes donation status tracking (safe/unsafe) and countdown timers.
    Now integrates with enhanced context processors for notifications and support options.
    """
    user = request.user
    logger.debug(f"Accessing donor dashboard for user '{user.username}'")

    # Get dashboard access context from our helper functions
    access_context = check_dashboard_access(user)
    
    donor = get_object_or_404(Donor, user=user)

    # ==========================================
    # DETERMINE DONOR SAFETY STATUS
    # ==========================================
    # Check for unsafe donations
    unsafe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_unsafe'
    ).first()
    
    # Check for safe donations
    safe_donation = BloodDonate.objects.filter(
        donor=donor,
        status='tested_safe'
    ).first()
    
    # Get pending tests (collected but not tested)
    pending_tests = BloodDonate.objects.filter(
        donor=donor,
        status='collected'
    ).count()
    
    # Count safe and unsafe donations
    safe_count = BloodDonate.objects.filter(donor=donor, status='tested_safe').count()
    unsafe_count = BloodDonate.objects.filter(donor=donor, status='tested_unsafe').count()
    
    # Determine donor status
    is_unsafe_donor = unsafe_donation is not None
    is_safe_donor = safe_donation is not None
    is_first_time_donor = not BloodDonate.objects.filter(donor=donor).exists()
    
    logger.info(f"Donor {donor.id} dashboard: unsafe={is_unsafe_donor}, safe={is_safe_donor}, first_time={is_first_time_donor}")

    # ==========================================
    # ENHANCED GREETING SYSTEM
    # ==========================================
    try:
        from blood.utils.greetings import get_donor_greeting
        # Get last donation for greeting
        last_donation_for_greeting = BloodDonate.objects.filter(
            donor=donor, 
            status__in=['approved', 'completed', 'tested_safe', 'tested_unsafe']
        ).order_by('-date').first()
        
        # Get upcoming appointments for greeting
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
    except ImportError:
        # Fallback greeting with safety status and inclusive messaging
        if is_unsafe_donor:
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
            'profile_pic': donor.profile_pic if hasattr(donor, 'profile_pic') else None
        }

    # ==========================================
    # LAST DONATION & NEXT ELIGIBILITY (FIXED DATE COMPARISON)
    # ==========================================
    last_donation = BloodDonate.objects.filter(
        donor=donor, 
        status__in=['approved', 'completed', 'tested_safe']
    ).order_by('-date').first()

    if last_donation:
        # Convert datetime to date for comparison if needed
        last_donation_date = last_donation.date.date() if hasattr(last_donation.date, 'date') else last_donation.date
        
        # Update donor.last_donation_date if outdated
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
    # TOTAL POINTS & DONATIONS (only safe donations count)
    # ==========================================
    total_safe_donations = BloodDonate.objects.filter(
        donor=donor,
        status='tested_safe'
    ).count()
    
    points_per_donation = 10
    computed_points = total_safe_donations * points_per_donation

    # Sync points with database
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
    # INFO CARDS (Enhanced with volunteer options)
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
    
    # Annotate each donation with display status
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
    # MILESTONES (only count safe donations)
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
    # HERO STATUS & BADGES (based on safe donations only)
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
    
    # Add hero info to greeting data
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
    
    # Add metadata to greeting data if not already present
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

    # ==========================================
    # NOTIFICATION COUNT
    # ==========================================
    from django.contrib.contenttypes.models import ContentType
    from utils.models import Notification
    
    notification_count = 0
    if hasattr(donor, 'id'):
        donor_content_type = ContentType.objects.get_for_model(Donor)
        notification_count = Notification.objects.filter(
            recipient_content_type=donor_content_type,
            recipient_object_id=donor.id,
            is_read=False
        ).count()

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
        'unsafe_reason': unsafe_donation.unsafe_reason if unsafe_donation else None,
        
        # ==========================================
        # INCLUSIVE MESSAGING FEATURES
        # ==========================================
        'eligibility_completed': eligibility_completed,
        'show_eligibility_modal': access_context.get('show_eligibility_modal', False),
        'show_support_options': access_context.get('show_support_options', False),
        'support_options_heading': "Everyone Has a Role in Saving Lives",
        'support_options_message': "Whether you're eligible to donate or not, you can still make a meaningful impact.",
        'volunteer_suggestions': access_context.get('volunteer_suggestions', []),
        'motivational_message': access_context.get('motivational_message', ''),
        'quick_actions': quick_actions,
        'donor_unread_notification_count': notification_count,
    }

    logger.debug(f"Rendering donor dashboard for user '{user.username}' with {total_safe_donations} safe donations and {donor.points} points")
    return render(request, 'donor/donor_dashboard.html', context)

# -------------------------------
# DonateBloodView
# -------------------------------


@login_required(login_url='donor:donorlogin')
def donate_blood_view(request):
    """
    View for donors to schedule blood donation appointments.
    FIXED: Now properly creates Appointment objects that phlebotomists can see.
    """
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "⚠️ You must complete your donor profile before donating blood.")
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
    # HANDLE UNSAFE DONOR
    # ==========================================
    if is_unsafe_donor:
        latest_unsafe = BloodDonate.objects.filter(
            donor=donor,
            status='tested_unsafe'
        ).order_by('-date').first()
        
        donate_form = BloodDonateForm(donor=donor)
        
        context = {
            'donation_form': donate_form,
            'donor': donor,
            'active_donation': None,
            'bloodgroup_verified': donor.bloodgroup_verified,
            'verified_bloodgroup': donor.bloodgroup if donor.bloodgroup_verified else None,
            'unsafe_reason': latest_unsafe.unsafe_reason if latest_unsafe else 'Medical reasons',
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
    # CALCULATE NEXT ELIGIBLE DATE
    # ==========================================
    days_until_next = None
    next_donation_date = None
    
    if is_safe_donor and donor.last_donation_date:
        next_donation_date = donor.last_donation_date + timedelta(days=56)
        today = timezone.now().date()
        days_until_next = (next_donation_date - today).days if next_donation_date > today else 0

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
                    
                    messages.success(request, "✅ Your blood donation appointment has been scheduled successfully!")
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
        'next_donation_date': next_donation_date,
        'is_unsafe': False,
        'has_unsafe_donation': False,
        'has_safe_donation': is_safe_donor,
        'is_first_time_donor': is_first_time_donor
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
    Blood group becomes read-only after phlebotomist verification.
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
def faqs_view(request):
    """Frequently asked questions"""
    context = {
        'page_title': 'Frequently Asked Questions',
        'page_icon': 'fa-question-circle',
        'faq_categories': [
            {
                'name': 'Eligibility',
                'icon': 'fa-check-circle',
                'questions': [
                    {'q': 'Who can donate blood?', 'a': 'Generally, healthy adults aged 18-65 weighing at least 50kg can donate.'},
                    {'q': 'How often can I donate?', 'a': 'Every 56 days (8 weeks) for whole blood donation.'},
                    {'q': 'Can I donate if I have a cold?', 'a': 'No, you should be feeling healthy on the day of donation.'},
                    {'q': 'What medications disqualify me?', 'a': 'Some medications may require waiting periods. Check with our staff.'},
                ]
            },
            {
                'name': 'The Donation Process',
                'icon': 'fa-syringe',
                'questions': [
                    {'q': 'How long does donation take?', 'a': 'The entire process takes about 1 hour, with actual donation 8-10 minutes.'},
                    {'q': 'Is donating blood safe?', 'a': 'Yes, sterile equipment is used once and discarded.'},
                    {'q': 'Will it hurt?', 'a': 'You may feel a quick pinch, but most donors feel fine.'},
                    {'q': 'How much blood is taken?', 'a': 'About 1 pint (450-500ml), which your body quickly replaces.'},
                ]
            },
            {
                'name': 'After Donation',
                'icon': 'fa-heart',
                'questions': [
                    {'q': 'What should I eat after donating?', 'a': 'Iron-rich foods and plenty of fluids.'},
                    {'q': 'Can I exercise after donating?', 'a': 'Avoid strenuous exercise for 24 hours.'},
                    {'q': 'When will I know my blood type?', 'a': 'You\'ll receive notification after your donation is tested.'},
                    {'q': 'How soon can I donate again?', 'a': '56 days for whole blood, sooner for platelets.'},
                ]
            },
        ]
    }
    return render(request, 'donor/resources/faqs.html', context)


@login_required(login_url='donorlogin')
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

@login_required(login_url='donorlogin')
def success_stories_view(request):
    """Success stories from donors and recipients"""
    stories = [
        {
            'id': 1,
            'type': 'donor',
            'name': 'Michael Chen',
            'age': 34,
            'donations': 25,
            'story': 'I started donating in college and haven\'t stopped. Knowing I\'ve helped over 70 patients keeps me going.',
            'image': 'images/stories/michael.jpg',
            'quote': 'Every donation is a chance to be someone\'s hero.'
        },
        {
            'id': 2,
            'type': 'recipient',
            'name': 'Sarah Johnson',
            'age': 28,
            'condition': 'Leukemia survivor',
            'story': 'Blood donors gave me a second chance at life. During my treatment, I received over 50 transfusions.',
            'image': 'images/stories/sarah.jpg',
            'quote': 'To every donor: you are my heroes.'
        },
        {
            'id': 3,
            'type': 'donor',
            'name': 'Robert Smith',
            'age': 62,
            'donations': 100,
            'story': 'Just reached my 100th donation! It\'s been a wonderful journey helping others.',
            'image': 'images/stories/robert.jpg',
            'quote': 'Donating blood is the easiest way to be a hero.'
        },
        {
            'id': 4,
            'type': 'family',
            'name': 'The Williams Family',
            'story': 'When our son needed emergency surgery, blood donors were there for us. Now our whole family donates.',
            'image': 'images/stories/williams.jpg',
            'quote': 'We turned our gratitude into action.'
        },
    ]
    context = {
        'page_title': 'Success Stories',
        'page_icon': 'fa-star',
        'stories': stories
    }
    return render(request, 'donor/community/success_stories.html', context)


# ==========================================
# IMPACT TRACKING VIEWS
# ==========================================

@login_required(login_url='donorlogin')
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
