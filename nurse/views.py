import logging
from datetime import date, timedelta
from itertools import chain
from operator import attrgetter
from django.utils import timezone
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Sum, Min
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.timezone import now, localdate
from django.views.decorators.http import require_POST
from blood.utils.stock_utils import add_stock
from .models import Nurse, Appointment
from .forms import (
    NurseLoginForm, NurseSignupForm, NurseForm, AppointmentForm
)
from blood.models import  Stock, DonationCenter, StockUnit,StockTransaction,BloodBagBarcode
from blood.utils.stock_utils import deduct_stock_fifo
from datetime import datetime
from donor.models import BloodDonate
from collections import OrderedDict
from django.views.generic import DetailView
from django.core.exceptions import ValidationError
from django.db.models import Q
from collections import defaultdict
from .forms import NurseUserForm
from donor.models import Donor
from django.db.models import Prefetch
from django.contrib.auth.mixins import LoginRequiredMixin
from functools import wraps
from django.views.generic import ListView
from blood.utils.notifications import create_notification
from blood.utils.greetings import get_nurse_greeting
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from utils.models import Notification
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from donor.models import BLOODGROUP_CHOICES
logger = logging.getLogger(__name__)

# Helper: Check if user is in NURSE group
def is_nurse(user):
    return user.groups.filter(name='NURSE').exists()

# ---------------------------
# Custom Decorator for Approved Nurses
# ---------------------------
def nurse_approved_required(view_func):
    """
    Decorator to ensure nurse is approved before accessing views
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('nurse:nurselogin')
        
        try:
            nurse = request.user.nurse
            if not nurse.is_approved:
                messages.warning(
                    request, 
                    "⏳ Your account is pending admin approval. You'll receive an email once approved."
                )
                return redirect('nurse:nurse-pending-approval')
        except Nurse.DoesNotExist:
            messages.error(request, "❌ Nurse profile not found.")
            return redirect('nurse:nurselogin')
        
        return view_func(request, *args, **kwargs)
    return wrapper

# ---------------------------
# Nurse Signup View (UPDATED - NO EMAIL VERIFICATION)
# ---------------------------

def nurse_signup_view(request):
    """
    Handle nurse registration.
    Account is active immediately but requires admin approval for full access.
    """
    if request.method == "POST":
        form = NurseSignupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Extract data from form
                username = request.POST.get('username') or form.cleaned_data.get('username')
                email = request.POST.get('email') or form.cleaned_data.get('email')
                password = request.POST.get('password1') or request.POST.get('password') or form.cleaned_data.get('password1')
                first_name = request.POST.get('first_name') or form.cleaned_data.get('first_name', '')
                last_name = request.POST.get('last_name') or form.cleaned_data.get('last_name', '')
                
                # Create user - active immediately
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True
                )
                
                # Save nurse profile (pending admin approval)
                nurse = form.save(commit=False)
                nurse.user = user
                nurse.is_approved = False  # Needs admin approval
                nurse.save()
                
                # Add to NURSE group
                nurse_group, _ = Group.objects.get_or_create(name="NURSE")
                nurse_group.user_set.add(user)
                
                # Log the registration
                logger.info(f"New nurse registration: {user.username} - Pending admin approval")
                
                # Success message
                messages.success(
                    request,
                    f"🎉 Registration successful, {user.first_name}! "
                    f"Your account has been created and is pending admin approval. "
                    f"You can login but access will be limited until approved."
                )
                
                return redirect('nurse:nurselogin')
                
            except Exception as e:
                # Log the error for debugging
                logger.error(f"Nurse registration error: {str(e)}", exc_info=True)
                
                # Clean up: delete the user if registration fails
                if 'user' in locals():
                    user.delete()
                
                messages.error(request, f"⚠️ Registration failed: {str(e)}")
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = NurseSignupForm()

    return render(request, "nurse/nursesignup.html", {"form": form})

# ---------------------------
# Nurse Login View (UPDATED - NO EMAIL VERIFICATION)
# ---------------------------
def nurselogin_view(request):
    """
    Handle nurse login WITHOUT email verification requirement.
    Only admin approval required.
    """
    # If user is already authenticated and is a nurse, redirect to dashboard
    if request.user.is_authenticated and request.user.groups.filter(name='NURSE').exists():
        return redirect('nurse:nurse-dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                # CHECK 1: Nurse Profile Exists
                if not hasattr(user, 'nurse'):
                    messages.error(
                        request, 
                        '❌ Nurse profile not found. '
                        'Please contact support to complete your registration.'
                    )
                    return render(request, 'nurse/nurselogin.html', {'form': form})
                
                # CHECK 2: Admin Approval Status
                try:
                    nurse = user.nurse
                    
                    if not nurse.is_approved:
                        if nurse.rejection_reason:
                            # Account was rejected
                            messages.error(
                                request,
                                f"❌ Your account has been rejected. Reason: {nurse.rejection_reason}"
                            )
                            return render(request, 'nurse/nurselogin.html', {'form': form})
                        else:
                            # Account pending approval - can login but limited access
                            login(request, user)
                            logger.info(f"Nurse login (pending approval): {user.username} ({user.email})")
                            
                            messages.warning(
                                request,
                                f"⚠️ Welcome, {nurse.full_name or user.username}! "
                                f"Your account is pending admin approval. "
                                f"Access is limited until approved."
                            )
                            return redirect('nurse:nurse-pending-approval')
                    
                    # All checks passed - Login successful
                    login(request, user)
                    logger.info(f"Nurse login successful: {user.username} ({user.email}) - Approved: {nurse.is_approved}")
                    
                    messages.success(request, f"✅ Welcome back, {nurse.full_name or user.username}!")
                    return redirect('nurse:nurse-dashboard')
                    
                except Nurse.DoesNotExist:
                    messages.error(request, "❌ Nurse profile not found. Please contact support.")
                    
            else:
                # Authentication failed
                messages.error(request, "❌ Invalid username or password.")
                
                # Provide helpful suggestions
                messages.info(
                    request,
                    'Forgot your password? '
                    f'<a href="/password-reset/" class="alert-link">'
                    f'Click here to reset it</a>'
                )
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = AuthenticationForm()
    
    return render(request, 'nurse/nurselogin.html', {'form': form})

# ---------------------------
# Pending Approval View
# ---------------------------
# ---------------------------
# Pending Approval View
# ---------------------------
def nurse_pending_approval_view(request):
    """
    View for nurses waiting for admin approval.
    """
    if not request.user.is_authenticated:
        return redirect('nurse:nurselogin')
    
    try:
        nurse = request.user.nurse
        
        # If nurse is already approved, redirect to dashboard
        if nurse.is_approved:
            return redirect('nurse:nurse-dashboard')
        
        # Use user's date_joined if nurse model doesn't have registration_date
        registration_date = getattr(nurse, 'registration_date', request.user.date_joined)
        
        context = {
            'nurse': nurse,
            'full_name': nurse.full_name or request.user.get_full_name() or request.user.username,
            'registration_date': registration_date,
            'is_rejected': bool(nurse.rejection_reason),
            'rejection_reason': nurse.rejection_reason,
        }
        
        return render(request, 'nurse/nurse_pending_approval.html', context)
        
    except Nurse.DoesNotExist:
        messages.error(request, "❌ Nurse profile not found.")
        return redirect('nurse:nurselogin')

# ---------------------------
# Nurse Dashboard View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_dashboard(request):
    nurse = get_object_or_404(Nurse.objects.select_related('donation_center'), user=request.user)
    today = localdate()

    # --- Appointment aggregates ---
    total_appointments = Appointment.objects.filter(nurse=nurse).count()
    today_appointments = Appointment.objects.filter(nurse=nurse, date__date=today).count()

    upcoming_appointments = Appointment.objects.filter(
        nurse=nurse,
        date__gte=now()
    ).order_by('date')[:5]

    next_appointment = upcoming_appointments.first() if upcoming_appointments else None

    # --- Generate personalized greeting ---
    greeting_data = get_nurse_greeting(
        nurse=nurse,
        appointment_count=today_appointments,
        next_appointment=next_appointment
    )

    # Weekly appointments chart data — ensure full week coverage with zeros for missing days
    week_start = today - timedelta(days=6)
    dates = [week_start + timedelta(days=i) for i in range(7)]
    date_counts = OrderedDict((d, 0) for d in dates)

    qs = (
        Appointment.objects.filter(nurse=nurse, date__date__gte=week_start)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(count=Count('id'))
    )

    for entry in qs:
        if entry['day'] in date_counts:
            date_counts[entry['day']] = entry['count']

    chart_labels = [d.strftime('%b %d') for d in date_counts.keys()]
    chart_data = list(date_counts.values())

    # --- Blood stock section for nurse's own center ---
    blood_stock_summary = None
    blood_stock_totals = []

    if nurse.donation_center:
        blood_stock_summary = StockUnit.objects.filter(center=nurse.donation_center)

        bloodgroup_qs = (
            StockUnit.objects.filter(center=nurse.donation_center)
            .values('bloodgroup')
            .annotate(
                total_units=Sum('unit'),
                earliest_expiry=Min('expiry_date'),
                batches_count=Count('id')
            )
            .order_by('bloodgroup')
        )

        for group in bloodgroup_qs:
            blood_stock_totals.append(group)

    # --- Other centers stock (summary with earliest expiry) ---
    all_centers = DonationCenter.objects.all().order_by('name')
    selected_center_id = request.GET.get('centre')
    other_centers_stock = None
    selected_center = None

    if selected_center_id:
        try:
            selected_center = DonationCenter.objects.get(id=selected_center_id)
            # Aggregate total units and earliest expiry per blood group at selected center
            other_centers_stock = (
                StockUnit.objects.filter(center=selected_center)
                .values('bloodgroup')
                .annotate(
                    total_units=Sum('unit'),
                    earliest_expiry=Min('expiry_date'),
                )
                .order_by('bloodgroup')
            )
        except DonationCenter.DoesNotExist:
            selected_center = None
            other_centers_stock = None

    # --- Calculate additional metrics for context ---
    completed_appointments = Appointment.objects.filter(
        nurse=nurse,
        status='completed',
        date__date=today
    ).count()
    
    pending_appointments = Appointment.objects.filter(
        nurse=nurse,
        status='scheduled',
        date__date=today
    ).count()

    context = {
        'nurse': nurse,
        'total_appointments': total_appointments,
        'today_appointments': today_appointments,
        'completed_today': completed_appointments,
        'pending_today': pending_appointments,
        'upcoming_appointments': upcoming_appointments,
        'next_appointment': next_appointment,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'current_time': today,
        'blood_stock_summary': blood_stock_summary,
        'blood_stock_totals': blood_stock_totals,
        'all_centers': all_centers,
        'selected_center': selected_center,
        'other_centers_stock': other_centers_stock,
        'today_date': today,
        'greeting_data': greeting_data,  # Add the greeting data to context
        'current_date': today,  # For the shared greeting template
    }
    
    return render(request, 'nurse/dashboard.html', context)

# ----------------------------------
#Donation Related Appointments
# ------------------------------------
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_donation_bookings(request):
    """
    Updated view for nurse to manage DONATION appointments.
    Nurses now only: approve, reject, cancel, and collect blood samples.
    Safety verification moved to lab techs.
    """
    nurse = request.user.nurse
    center = nurse.donation_center
    
    logger.info(f"🩺 Nurse {nurse.user.username} accessing donation bookings at {center.name if center else 'No Center'}")
    
    # Import here to avoid circular imports
    from donor.models import BloodDonate
    
    try:
        donation_content_type = ContentType.objects.get_for_model(BloodDonate)
        logger.info(f"📋 BloodDonate ContentType ID: {donation_content_type.id}")
    except Exception as e:
        logger.error(f"❌ Error getting BloodDonate ContentType: {e}")
        donation_content_type = None
    
    # ==========================================
    # FILTERING LOGIC
    # ==========================================
    filters = Q()
    
    # Filter by nurse
    filters &= Q(nurse=nurse)
    
    # Filter by center if nurse is assigned to one
    if center:
        filters &= Q(donation_center=center)
    
    # Get status filter from request
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        filters &= Q(status=status_filter)
        logger.info(f"📊 Applying status filter: {status_filter}")
    
    # Get date filter
    date_filter = request.GET.get('date', '').strip()
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            filters &= Q(date__date=filter_date)
            logger.info(f"📅 Applying date filter: {date_filter}")
        except ValueError:
            logger.warning(f"⚠️ Invalid date format: {date_filter}")
    
    # ==========================================
    # QUERY CONSTRUCTION WITH OPTIMIZATION
    # ==========================================
    if donation_content_type:
        donation_appointments = Appointment.objects.filter(
            filters,
            request_content_type=donation_content_type,
            donor__isnull=False,
        ).select_related(
            'donor',
            'donor__user',
            'nurse',
            'nurse__user',
            'donation_center',
            'status_changed_by',
            'cancelled_by_user',
            'approved_by',        # Changed from approved_by_nurse
            'collected_by',       # Changed from completed_by_nurse
            'rejected_by'         # Added for rejection tracking
        ).order_by('-date', '-created_at')
        
        total_appointments = donation_appointments.count()
        logger.info(f"📈 Found {total_appointments} donation appointments")
    else:
        donation_appointments = Appointment.objects.none()
        total_appointments = 0
    
    # ==========================================
    # ENHANCED DATA PREPARATION
    # ==========================================
    appointments_with_details = []
    
    # Pre-fetch all related BloodDonate objects in one query
    appointment_ids = [app.id for app in donation_appointments]
    
    # Get all related BloodDonate objects for these appointments
    blood_donations_dict = {}
    if appointment_ids:
        try:
            # Get BloodDonate objects related to these appointments
            request_object_ids = [app.request_object_id for app in donation_appointments if app.request_object_id]
            if request_object_ids:
                blood_donations = BloodDonate.objects.filter(
                    id__in=request_object_ids
                ).select_related(
                    'donor',
                    'donor__user',
                    'donation_center'
                )
                
                # Create a dictionary mapping BloodDonate ID to the object
                blood_donations_by_id = {bd.id: bd for bd in blood_donations}
                
                # Map appointment IDs to BloodDonate objects
                for app in donation_appointments:
                    if app.request_object_id and app.request_object_id in blood_donations_by_id:
                        blood_donations_dict[app.id] = blood_donations_by_id[app.request_object_id]
                    
        except Exception as e:
            logger.error(f"❌ Error fetching blood donations: {e}")
    
    # Get StockUnit safety information for these blood donations
    stock_units_dict = {}
    if blood_donations_dict:
        from blood.models import StockUnit
        blood_donate_ids = [bd.id for bd in blood_donations_dict.values()]
        
        try:
            stock_units = StockUnit.objects.filter(
                blood_donation_id__in=blood_donate_ids
            ).select_related('safety_verified_by')
            
            for su in stock_units:
                stock_units_dict[su.blood_donation_id] = su
                
        except Exception as e:
            logger.error(f"❌ Error fetching stock units: {e}")
    
    for appointment in donation_appointments:
        blood_donate = None
        stock_unit = None
        donor_details = {}
        blood_donate_details = {}
        
        # Get BloodDonate object from our pre-fetched dictionary
        blood_donate = blood_donations_dict.get(appointment.id)
        
        # Get associated StockUnit if exists
        if blood_donate:
            stock_unit = stock_units_dict.get(blood_donate.id)
        
        # Get comprehensive donor details
        if appointment.donor:
            donor = appointment.donor
            user = donor.user
            
            donor_details = {
                'id': donor.id,
                'full_name': user.get_full_name() if user else 'Anonymous Donor',
                'username': user.username if user else 'N/A',
                'email': user.email if user else 'N/A',
                'mobile': getattr(donor, 'mobile', 'N/A'),
                'national_id': getattr(donor, 'national_id', 'N/A'),
                'county': getattr(donor, 'county', 'N/A'),
                'profile_pic': getattr(donor, 'profile_pic', None),
                'bloodgroup': getattr(donor, 'bloodgroup', 'Not Tested'),
                'bloodgroup_verified': getattr(donor, 'bloodgroup_verified', False),
                'verified_at': getattr(donor, 'bloodgroup_verified_at', None),
                'verified_by': getattr(donor, 'bloodgroup_verified_by', None),
                'dob': getattr(donor, 'dob', None),
                'age': donor.age if hasattr(donor, 'age') else None,
                'last_donation_date': getattr(donor, 'last_donation_date', None),
                'points': getattr(donor, 'points', 0),
                'total_donations': getattr(donor, 'total_donations', 0),
                'has_unsafe_history': False,
                'safety_rating': 'high',
            }
        
        # Get BloodDonate details
        if blood_donate:
            # Calculate safety metrics from StockUnit if available
            expiry_date = None
            safety_status = 'pending'
            is_quarantined = False
            unsafe_reason = ''
            safety_notes = ''
            safety_verified_by = None
            safety_verified_at = None
            
            if stock_unit:
                safety_status = getattr(stock_unit, 'safety_status', 'pending')
                is_quarantined = getattr(stock_unit, 'is_quarantined', False)
                unsafe_reason = getattr(stock_unit, 'unsafe_reason', '')
                safety_notes = getattr(stock_unit, 'safety_notes', '')
                safety_verified_by = getattr(stock_unit, 'safety_verified_by', None)
                safety_verified_at = getattr(stock_unit, 'safety_verified_at', None)
                
                if stock_unit.expiry_date:
                    expiry_date = stock_unit.expiry_date
            
            # Get donation center details safely
            donation_center_name = 'Not Assigned'
            donation_center_address = 'N/A'
            
            if blood_donate.donation_center:
                donation_center_name = blood_donate.donation_center.name
                
                # Safely get address components
                address_parts = []
                if hasattr(blood_donate.donation_center, 'city'):
                    address_parts.append(blood_donate.donation_center.city)
                if hasattr(blood_donate.donation_center, 'address'):
                    address_parts.append(blood_donate.donation_center.address)
                elif hasattr(blood_donate.donation_center, 'location'):
                    address_parts.append(blood_donate.donation_center.location)
                elif hasattr(blood_donate.donation_center, 'street'):
                    address_parts.append(blood_donate.donation_center.street)
                
                if address_parts:
                    donation_center_address = ', '.join(filter(None, address_parts))
            
            # Determine safety flags
            safety_flags = []
            if safety_status == 'unsafe':
                safety_flags.append('unsafe')
            if is_quarantined:
                safety_flags.append('quarantined')
            if expiry_date and expiry_date <= timezone.now().date() + timedelta(days=7):
                safety_flags.append('expiring_soon')
            
            blood_donate_details = {
                'id': blood_donate.id,
                'bloodgroup': getattr(blood_donate, 'bloodgroup', 'Not specified'),
                'unit': getattr(blood_donate, 'unit', 450),
                'donor_age': getattr(blood_donate, 'donor_age', None),
                'donation_center': getattr(blood_donate, 'donation_center', None),
                'donation_center_name': donation_center_name,
                'donation_center_address': donation_center_address,
                'status': getattr(blood_donate, 'status', 'pending'),
                'safety_status': safety_status,
                'unsafe_reason': unsafe_reason,
                'safety_notes': safety_notes,
                'safety_verified_by': safety_verified_by,
                'safety_verified_at': safety_verified_at,
                'date': getattr(blood_donate, 'date', None),
                'expiry_date': expiry_date,
                'days_until_expiry': (expiry_date - timezone.now().date()).days if expiry_date else None,
                'stock_added': getattr(blood_donate, 'stock_added', False),
                'approved_by': getattr(blood_donate, 'approved_by_nurse', None),  # Updated reference
                'collected_by': getattr(blood_donate, 'collected_by_nurse', None),  # Updated reference
                'safety_flags': safety_flags,
                'is_quarantined': is_quarantined,
            }
        
        # Appointment status analysis
        appointment_status = appointment.status
        status_analysis = {
            'can_approve': appointment_status == 'pending',
            'can_collect': appointment_status == 'approved',  # Changed from can_complete
            'can_cancel': appointment_status in ['pending', 'approved'],
            'is_final': appointment_status in ['completed', 'collected', 'cancelled', 'rejected'],  # Added 'collected'
            'requires_safety_check': False,  # Removed from nurse
        }
        
        # Compile all data
        appointments_with_details.append({
            'appointment': appointment,
            'blood_donate': blood_donate,
            'stock_unit': stock_unit,
            'donor': appointment.donor,
            'donor_details': donor_details,
            'blood_donate_details': blood_donate_details,
            'status_analysis': status_analysis,
            'has_activity': (
                appointment.approved_by or 
                appointment.collected_by or 
                appointment.status in ['cancelled', 'rejected']
            ),
            'time_since_created': (timezone.now() - appointment.created_at).days if appointment.created_at else 0,
        })
    
    # ==========================================
    # APPLY BLOOD GROUP FILTER (if any)
    # ==========================================
    blood_group_filter = request.GET.get('blood_group', '').strip()
    if blood_group_filter and appointments_with_details:
        filtered_appointments = []
        for item in appointments_with_details:
            bg = item.get('blood_donate_details', {}).get('bloodgroup')
            if bg and bg == blood_group_filter:
                filtered_appointments.append(item)
        appointments_with_details = filtered_appointments
    
    # ==========================================
    # STATISTICS & ANALYTICS
    # ==========================================
    status_counts = donation_appointments.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        approved=Count('id', filter=Q(status='approved')),
        collected=Count('id', filter=Q(status='collected')),  # Added collected
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        rejected=Count('id', filter=Q(status='rejected')),
    )
    
    # Safety statistics - get from StockUnit model
    safety_stats = {
        'pending_verification': 0,
        'safe_units': 0,
        'unsafe_units': 0,
        'quarantined': 0,
    }
    
    # Count safety status from stock units
    from blood.models import StockUnit
    for item in appointments_with_details:
        if item.get('stock_unit'):
            su = item['stock_unit']
            safety_status = getattr(su, 'safety_status', 'pending')
            if safety_status == 'safe':
                safety_stats['safe_units'] += 1
            elif safety_status == 'unsafe':
                safety_stats['unsafe_units'] += 1
            else:
                safety_stats['pending_verification'] += 1
            
            if getattr(su, 'is_quarantined', False):
                safety_stats['quarantined'] += 1
    
    # Blood group distribution
    blood_group_stats = {}
    for item in appointments_with_details:
        bg = item.get('blood_donate_details', {}).get('bloodgroup')
        if bg and bg != 'Not specified':
            if bg in blood_group_stats:
                blood_group_stats[bg] += 1
            else:
                blood_group_stats[bg] = 1
    
    # ==========================================
    # TEMPLATE CONTEXT
    # ==========================================
    from donor.models import BLOODGROUP_CHOICES
    
    context = {
        'donor_donations': appointments_with_details,
        'total_count': status_counts.get('total', 0),
        'pending_count': status_counts.get('pending', 0),
        'approved_count': status_counts.get('approved', 0),
        'collected_count': status_counts.get('collected', 0),  # Added collected count
        'completed_count': status_counts.get('completed', 0),
        'cancelled_count': status_counts.get('cancelled', 0),
        'rejected_count': status_counts.get('rejected', 0),
        'safety_stats': safety_stats,
        'blood_group_stats': blood_group_stats,
        'blood_group_choices': BLOODGROUP_CHOICES,
        'nurse': nurse,
        'center': center,
        'now': timezone.now(),
        'current_filters': {
            'status': status_filter,
            'blood_group': blood_group_filter,
            'date': date_filter,
        },
        'status_options': [
            ('', 'All Status'),
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('collected', 'Collected'),  # Added collected
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('rejected', 'Rejected'),
        ],
        'safety_statuses': [
            ('pending', 'Pending Verification'),
            ('safe', 'Safe'),
            ('unsafe', 'Unsafe'),
        ],
        # For dashboard cards
        'metrics': {
            'today_appointments': donation_appointments.filter(date__date=timezone.now().date()).count(),
            'tomorrow_appointments': donation_appointments.filter(
                date__date=timezone.now().date() + timedelta(days=1)
            ).count(),
            'avg_units_per_appointment': sum(
                item.get('blood_donate_details', {}).get('unit', 0) 
                for item in appointments_with_details
            ) / len(appointments_with_details) if appointments_with_details else 0,
            'first_time_donors': sum(
                1 for item in appointments_with_details 
                if not item.get('donor_details', {}).get('bloodgroup_verified', True)
            ),
        }
    }
    
    logger.info(f"""
    📊 DONATION BOOKINGS SUMMARY:
    • Total: {status_counts.get('total', 0)}
    • Pending: {status_counts.get('pending', 0)}
    • Approved: {status_counts.get('approved', 0)}
    • Collected: {status_counts.get('collected', 0)}
    • Completed: {status_counts.get('completed', 0)}
    • Safe Units: {safety_stats.get('safe_units', 0)}
    • Unsafe Units: {safety_stats.get('unsafe_units', 0)}
    • Quarantined: {safety_stats.get('quarantined', 0)}
    """)
    
    return render(request, 'nurse/nurse_donation_bookings.html', context)
# ----------------------------------
# UPDATE DONATION APPOINTMENT STATUS
# ------------------------------------
logger = logging.getLogger(__name__)


def create_appointment_notification(appointment, nurse_user, action, reason=None):
    donor = getattr(appointment.request, 'donor', None)
    if not donor:
        logger.warning(f"Appointment {appointment.id} has no donor linked for notification")
        return

    title = "Donation Appointment Update"
    message = (
        f"Your donation appointment on {appointment.date.strftime('%b %d, %Y')} "
        f"has been {action.upper()} by Nurse {nurse_user.get_full_name()}."
    )
    if reason:
        message += f" Reason: {reason}"

    Notification.objects.create(
        title=title,
        message=message,
        recipient_content_type=ContentType.objects.get_for_model(donor),
        recipient_object_id=donor.id,
        sender_content_type=ContentType.objects.get_for_model(nurse_user),
        sender_object_id=nurse_user.id,
    )
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def nurse_update_donation_appointment_status(request, appointment_id):
    """
    PHASE 1: Nurse collects blood but DOES NOT verify safety
    Safety verification moved to Lab Technologist
    """
    logger.info(f"=== PHASE 1: Processing donation appointment {appointment_id} ===")
    logger.info(f"POST data: {dict(request.POST)}")
    logger.info(f"User: {request.user}")

    try:
        nurse = request.user.nurse
        now = timezone.now()

        with transaction.atomic():
            appointment = get_object_or_404(
                Appointment.objects.select_for_update(),
                id=appointment_id
            )

            # Auto-assign nurse if needed
            if not appointment.nurse:
                appointment.nurse = nurse
                appointment.save(update_fields=['nurse'])
            elif appointment.nurse != nurse:
                return JsonResponse({
                    'success': False,
                    'error': 'This appointment is already assigned to another nurse.'
                }, status=403)

            # Get linked donation request
            donation = getattr(appointment, 'request', None)
            if not donation or not isinstance(donation, BloodDonate):
                return JsonResponse({
                    'success': False,
                    'error': 'This appointment is not linked to a valid blood donation.'
                }, status=400)

            # Validate action
            action = (request.POST.get('action') or '').strip().lower()
            valid_actions = ['approve', 'reject', 'collect', 'cancelled']  # Changed 'completed' to 'collect'
            
            if action not in valid_actions:
                return JsonResponse({
                    'success': False,
                    'error': f"Invalid action '{action}'. Valid: {', '.join(valid_actions)}"
                }, status=400)

            # Prevent double-finalizing
            if appointment.status in ['completed', 'cancelled', 'rejected', 'collected'] or \
               donation.status in ['completed', 'cancelled', 'rejected', 'collected']:
                return JsonResponse({
                    'success': False,
                    'error': f'This donation already has a final status: {appointment.status}.'
                }, status=400)

            # Reason for reject/cancel
            reason = (request.POST.get('reason') or '').strip()

            # =======================
            # ACTION: APPROVE
            # =======================
            if action == 'approve':
                if getattr(donation, 'approved_by', None):
                    return JsonResponse({
                        'success': False,
                        'error': 'This donation has already been approved.'
                    }, status=400)

                # Update appointment
                appointment.status = 'approved'
                appointment.approved_by = nurse.user
                appointment.approved_by_role = 'nurse'
                appointment.approved_at = now
                appointment.status_changed_by = nurse.user
                appointment.status_changed_by_role = 'nurse'
                appointment.status_changed_at = now
                appointment.save()

                # Update donation
                donation.status = 'approved'
                donation.save()

                # Create notification
                create_appointment_notification(appointment, nurse.user, 'approved')

                logger.info(f"✅ Nurse {nurse.user.username} approved donation {donation.id}")

                return JsonResponse({
                    'success': True,
                    'status': 'approved',
                    'message': f"Donation approved successfully by {nurse.user.get_full_name()}.",
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_approval'
                })

            # =======================
            # ACTION: REJECT
            # =======================
            elif action == 'reject':
                if not reason:
                    return JsonResponse({
                        'success': False,
                        'error': 'Reason is required for rejection.'
                    }, status=400)

                # Update appointment
                appointment.status = 'rejected'
                appointment.rejected_by = nurse.user
                appointment.rejected_by_role = 'nurse'
                appointment.rejected_at = now
                appointment.rejection_reason = reason
                appointment.status_changed_by = nurse.user
                appointment.status_changed_by_role = 'nurse'
                appointment.status_changed_at = now
                appointment.save()

                # Update donation
                donation.status = 'rejected'
                donation.rejection_reason = reason
                donation.save()

                # Create notification
                create_appointment_notification(appointment, nurse.user, 'rejected', reason)

                logger.info(f"✅ Nurse {nurse.user.username} rejected donation {donation.id}")

                return JsonResponse({
                    'success': True,
                    'status': 'rejected',
                    'message': f"Donation rejected. Reason: {reason}",
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_rejection'
                })

            # =======================
            # ACTION: COLLECT (formerly completed)
            # =======================
            elif action == 'collect':
                # ----- Validation -----
                if appointment.status != 'approved':
                    return JsonResponse({
                        'success': False,
                        'error': 'Donation must be approved before collection.'
                    }, status=400)

                # ----- Get form values -----
                new_bg = request.POST.get('bloodgroup', '').strip()
                new_unit = request.POST.get('unit', '').strip()
                collection_notes = request.POST.get('collection_notes', '').strip()

                # Validate blood group for first-time donors
                donor = donation.donor
                
                # Validate unit amount
                units_value = None
                if new_unit:
                    try:
                        units_value = int(new_unit)
                        if units_value < 450 or units_value > 2700 or units_value % 50 != 0:
                            return JsonResponse({
                                'success': False,
                                'error': 'Units must be 450–2700 ml in multiples of 50.'
                            }, status=400)
                    except ValueError:
                        return JsonResponse({
                            'success': False,
                            'error': 'Units must be a valid number.'
                        }, status=400)
                else:
                    units_value = 450  # Default

                # ----- Apply updates -----
                if new_bg and new_bg != donation.bloodgroup:
                    donation.bloodgroup = new_bg

                donation.unit = units_value

                # ==========================================
                # FIRST DONATION — RECORD BLOOD GROUP (but don't verify yet)
                # ==========================================
                if donor and not donor.bloodgroup_verified and new_bg:
                    # Store the blood group but don't mark as verified yet
                    # Lab will verify during testing
                    donor.bloodgroup = new_bg
                    donor.save(update_fields=['bloodgroup'])
                    
                    logger.info(
                        f"📝 Recorded blood group for donor {donor.id}: {new_bg} "
                        f"(awaiting lab verification)"
                    )

                # ==========================================
                # UPDATE TO COLLECTED STATUS (not completed)
                # ==========================================
                
                # Update donation status to 'collected'
                donation.status = 'collected'
                donation.collected_by = nurse.user
                donation.collected_at = now
                donation.save()

                # Update appointment
                appointment.status = 'collected'
                appointment.collected_by = nurse.user
                appointment.collected_by_role = 'nurse'
                appointment.collected_at = now
                appointment.sent_to_lab_at = now
                appointment.status_changed_by = nurse.user
                appointment.status_changed_by_role = 'nurse'
                appointment.status_changed_at = now
                appointment.save()

                logger.info(
                    f"✅ Nurse {nurse.user.username} collected donation {donation.id} - "
                    f"awaiting lab testing"
                )

                # ==========================================
                # NOTIFY LAB TECH THAT BLOOD NEEDS TESTING
                # ==========================================
                try:
                    from lab_technologist.models import LabTechnologistProfile
                    center = donation.donation_center or nurse.donation_center
                    
                    if center:
                        lab_techs = LabTechnologistProfile.objects.filter(
                            center=center,
                            is_active=True
                        )
                        
                        for lab_tech in lab_techs:
                            Notification.objects.create(
                                title="New Blood Sample for Testing",
                                message=(
                                    f"Blood sample from donor {donor.user.get_full_name() if donor else 'Unknown'} "
                                    f"({units_value}ml) needs testing. "
                                    f"Collection barcode: {appointment.barcode}"
                                ),
                                recipient_content_type=ContentType.objects.get_for_model(lab_tech.user),
                                recipient_object_id=lab_tech.user.id,
                                sender_content_type=ContentType.objects.get_for_model(nurse.user),
                                sender_object_id=nurse.user.id,
                            )
                except Exception as e:
                    logger.error(f"Failed to notify lab techs: {e}")

                # ==========================================
                # CREATE NOTIFICATION FOR DONOR
                # ==========================================
                create_appointment_notification(appointment, nurse.user, 'collected')

                # ==========================================
                # BUILD RESPONSE
                # ==========================================
                response = {
                    'success': True,
                    'status': 'collected',
                    'barcode': appointment.barcode,
                    'action_by': nurse.user.get_full_name(),
                    'operation_type': 'donation_collection',
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'message': (
                        f"Blood collected successfully. Sample sent to lab for testing. "
                        f"Donor will be notified once test results are available."
                    ),
                }

                # Include blood group info if provided
                if new_bg:
                    response['bloodgroup_recorded'] = True
                    response['recorded_bloodgroup'] = new_bg

                return JsonResponse(response)

            # =======================
            # ACTION: CANCELLED
            # =======================
            elif action == 'cancelled':
                if not reason:
                    return JsonResponse({
                        'success': False,
                        'error': 'Reason is required for cancellation.'
                    }, status=400)

                # Update appointment
                appointment.status = 'cancelled'
                appointment.cancelled_by = 'nurse'
                appointment.cancelled_by_user = nurse.user
                appointment.cancelled_by_role = 'nurse'
                appointment.cancelled_at = now
                appointment.status_changed_by = nurse.user
                appointment.status_changed_by_role = 'nurse'
                appointment.status_changed_at = now
                appointment.save()

                # Update donation
                donation.status = 'cancelled'
                donation.cancellation_reason = reason
                donation.save()

                # Create notification
                create_appointment_notification(appointment, nurse.user, 'cancelled', reason)

                logger.info(f"✅ Nurse {nurse.user.username} cancelled donation {donation.id}")

                return JsonResponse({
                    'success': True,
                    'status': 'cancelled',
                    'message': f"Donation cancelled. Reason: {reason}",
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_cancellation'
                })

            # Should never reach here
            return JsonResponse({'success': False, 'error': f'Unhandled action: {action}'}, status=400)

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Appointment not found (may have been deleted).'
        }, status=404)

    except Exception as e:
        logger.error(
            f"❌ Unexpected error updating appointment {appointment_id}: {str(e)}",
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': f"Unexpected error: {str(e)}"
        }, status=500)
# ---------------------------
# Nurse Profile View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_profile_view(request, pk):
    """
    View nurse's profile page and allow profile update via POST if desired.
    """
    nurse = get_object_or_404(Nurse, pk=pk)

    if request.method == 'POST':
        form = NurseForm(request.POST, request.FILES, instance=nurse)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('nurse-profile', pk=nurse.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NurseForm(instance=nurse)

    context = {
        'nurse': nurse,
        'form': form,
    }
    return render(request, 'nurse/nurse_profile.html', context)

# ---------------------------
# Edit Profile View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_profile_edit_view(request, pk):
    """
    Allow a nurse to edit their own profile (User + Nurse models).
    """
    nurse = get_object_or_404(Nurse, pk=pk)
    
    # Ensure only profile owner can edit
    if request.user != nurse.user:
        messages.error(request, "You are not authorized to edit this profile.")
        return redirect('nurse-profile', pk=nurse.pk)
    
    # Store original read-only values for integrity check
    original_registration_number = nurse.registration_number
    original_donation_center = nurse.donation_center
    
    if request.method == "POST":
        user_form = NurseUserForm(request.POST, instance=nurse.user)
        nurse_form = NurseForm(request.POST, request.FILES, instance=nurse)
        
        # Handle profile picture removal
        if 'clear_profile_pic' in request.POST:
            if nurse.profile_pic:
                nurse.profile_pic.delete(save=False)
                nurse.profile_pic = None
        
        if user_form.is_valid() and nurse_form.is_valid():
            try:
                with transaction.atomic():
                    # Save user form
                    user_form.save()
                    
                    # Save nurse form but restore read-only fields
                    nurse_instance = nurse_form.save(commit=False)
                    
                    # SECURITY: Restore read-only fields to prevent tampering
                    nurse_instance.registration_number = original_registration_number
                    nurse_instance.donation_center = original_donation_center
                    
                    nurse_instance.save()
                    
                    messages.success(request, "Profile updated successfully.")
                    return redirect('nurse-profile', pk=nurse.pk)
            except Exception as e:
                messages.error(request, f"An error occurred while saving: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        user_form = NurseUserForm(instance=nurse.user)
        nurse_form = NurseForm(instance=nurse)
    
    context = {
        "user_form": user_form,
        "nurse_form": nurse_form,
        "nurse": nurse,
    }
    return render(request, "nurse/nurse_profile_edit.html", context)

# ---------------------------
# Notifications View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_notifications_view(request):
    nurse = get_object_or_404(Nurse, user=request.user)
    nurse_ct = ContentType.objects.get_for_model(Nurse)

    notifications = Notification.objects.filter(
        recipient_content_type=nurse_ct,
        recipient_object_id=nurse.id
    ).order_by('-created_at')

    unread_count = notifications.filter(read=False).count()

    return render(request, 'nurse/nurse_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })
    
# ---------------------------
# Mark Notifications Read
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def mark_nurse_notification_read(request, pk):
    nurse = get_object_or_404(Nurse, user=request.user)
    nurse_ct = ContentType.objects.get_for_model(Nurse)

    notification = get_object_or_404(
        Notification,
        id=pk,
        recipient_content_type=nurse_ct,
        recipient_object_id=nurse.id
    )
    notification.read = True
    notification.save()

    return redirect('nurse-notifications')


# ----------------------------------
# Ajax Booked Time Slots
# ------------------------------------
@login_required(login_url='/nurse/nurselogin/')
def ajax_booked_timeslots(request):
    nurse_id = request.GET.get('nurse_id')
    date_str = request.GET.get('date')  # Expected format 'dd-mm-YYYY'

    if not nurse_id or not date_str:
        return JsonResponse({'booked_times': []})

    try:
        nurse = Nurse.objects.filter(id=nurse_id).first()
        if not nurse:
            return JsonResponse({'booked_times': []})

        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()



        appointments = Appointment.objects.filter(
            nurse=nurse,
            date__date=date_obj,
            status__in=['pending', 'approved']
        )

        booked_times = [appt.date.strftime('%I:%M %p') for appt in appointments]

        return JsonResponse({'booked_times': booked_times})

    except Exception as e:
        print("Error in ajax_booked_timeslots:", e)
        return JsonResponse({'booked_times': []})

@login_required
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def select_barcode_for_donation(request, appointment_id):
    """
    View for nurse to select a pre-generated barcode for a donation
    """
    nurse = request.user.nurse
    appointment = get_object_or_404(Appointment, id=appointment_id, nurse=nurse, status='approved')
    
    # Get available barcodes
    from blood.utils.barcode_utils import get_available_barcodes
    available_barcodes = get_available_barcodes(limit=50)
    
    # Get recently used barcodes at this center
    recent_barcodes = BloodBagBarcode.objects.filter(
        collected_by=nurse.user
    ).order_by('-collected_at')[:10]
    
    context = {
        'appointment': appointment,
        'available_barcodes': available_barcodes,
        'recent_barcodes': recent_barcodes,
        'donor': appointment.donor,
    }
    
    return render(request, 'nurse/select_barcode.html', context)

@login_required
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def assign_barcode_to_donor(request, appointment_id, barcode_id):
    """
    Assign a barcode to a donor before collection
    """
    nurse = request.user.nurse
    appointment = get_object_or_404(Appointment, id=appointment_id, nurse=nurse)
    barcode = get_object_or_404(BloodBagBarcode, id=barcode_id, status='available')
    
    # Assign barcode to donor
    barcode.assign_to_donor(appointment.donor, nurse.user)
    
    messages.success(request, f"Barcode {barcode.barcode} assigned to {appointment.donor.user.get_full_name()}")
    
    # Redirect to collection form with pre-selected barcode
    return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
@login_required
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def collect_with_barcode(request, appointment_id, barcode_id):
    """
    Collection form with pre-selected barcode
    """
    nurse = request.user.nurse
    appointment = get_object_or_404(Appointment, id=appointment_id, nurse=nurse, status='approved')
    barcode = get_object_or_404(BloodBagBarcode, id=barcode_id, assigned_to_donor=appointment.donor)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get form data
                bloodgroup = request.POST.get('bloodgroup')
                unit = request.POST.get('unit')
                collection_notes = request.POST.get('collection_notes', '')
                
                # Validate data
                if not bloodgroup and not appointment.donor.bloodgroup_verified:
                    messages.error(request, "Blood group is required for first-time donors.")
                    return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
                
                if not unit:
                    messages.error(request, "Units are required.")
                    return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
                
                try:
                    unit = int(unit)
                    if unit < 100 or unit > 500 or unit % 50 != 0:
                        messages.error(request, "Units must be 100-500ml in multiples of 50.")
                        return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
                except ValueError:
                    messages.error(request, "Invalid unit value.")
                    return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
                
                # ===== CREATE BLOOD DONATION RECORD =====
                blood_donation = BloodDonate.objects.create(
                    donor=appointment.donor,
                    donation_center=appointment.donation_center,
                    nurse=nurse,
                    status='collected',
                    date=timezone.now().date(),
                    bloodgroup=bloodgroup if bloodgroup else appointment.donor.bloodgroup,
                    unit=unit
                )
                
                # ===== UPDATE BARCODE STATUS =====
                barcode.status = 'collected'
                barcode.collected_by = nurse.user
                barcode.collected_at = timezone.now()
                barcode.blood_donation = blood_donation
                if hasattr(barcode, 'notes'):
                    barcode.notes = collection_notes
                barcode.save()
                
                # ===== UPDATE APPOINTMENT STATUS =====
                appointment.status = 'completed'
                appointment.collected_by = nurse.user
                appointment.collected_by_role = 'nurse'
                appointment.collected_at = timezone.now()
                appointment.sent_to_lab_at = timezone.now()
                appointment.request_object_id = blood_donation.id
                from django.contrib.contenttypes.models import ContentType
                blood_donate_ct = ContentType.objects.get_for_model(BloodDonate)
                appointment.request_content_type = blood_donate_ct
                appointment.save()
                
                # ===== UPDATE DONOR'S DONATION HISTORY =====
                donor = appointment.donor
                
                # Update donor's last donation date
                donor.last_donation_date = timezone.now().date()
                
                # REMOVED: donor.total_donations += 1 (field doesn't exist)
                # Your donor dashboard calculates total_donations dynamically
                
                # Save donor changes
                donor.save()
                
                # ===== CREATE NOTIFICATION FOR DONOR =====
                from utils.models import Notification
                from django.contrib.contenttypes.models import ContentType
                
                # Create notification for donor
                Notification.objects.create(
                    title="Blood Donation Completed",
                    message=(
                        f"Thank you for your blood donation on {timezone.now().date()}! "
                        f"Your sample (Barcode: {barcode.barcode}) has been collected and "
                        f"sent to the lab for testing. You will be notified once test results "
                        f"are available. Your selfless act helps save lives!"
                    ),
                    recipient_content_type=ContentType.objects.get_for_model(donor),
                    recipient_object_id=donor.id,
                    sender_content_type=ContentType.objects.get_for_model(nurse.user),
                    sender_object_id=nurse.user.id,
                    action='donation_completed',
                    appointment_date=appointment.date,
                    bloodgroup=bloodgroup if bloodgroup else donor.bloodgroup,
                    unit=unit
                )
                
                # ===== UPDATE DONOR'S BLOOD GROUP (TENTATIVE) =====
                # This is temporary until lab verification
                if bloodgroup and not donor.bloodgroup_verified:
                    donor.bloodgroup = bloodgroup
                    donor.save()
                    logger.info(f"📝 Tentative blood group {bloodgroup} recorded for donor {donor.id}")
                
                # ===== SUCCESS MESSAGE =====
                messages.success(
                    request, 
                    f"✅ Blood collected successfully! Thank you, {donor.user.get_full_name()}, for your donation. "
                    f"Sample sent to lab for testing. A notification has been sent to the donor."
                )
                
                # ===== REDIRECT TO DONATION BOOKINGS =====
                return redirect('nurse:nurse-donation-bookings')
                
        except Exception as e:
            logger.error(f"Error in collect_with_barcode: {str(e)}", exc_info=True)
            messages.error(request, f"Error during collection: {str(e)}")
            return redirect('nurse:collect_with_barcode', appointment_id=appointment.id, barcode_id=barcode.id)
    
    # GET request - show the form
    context = {
        'appointment': appointment,
        'barcode': barcode,
        'donor': appointment.donor,
    }
    return render(request, 'nurse/collect_with_barcode.html', context)
# -------------------------------
# Get Nurses By Centre
# -------------------------------
def get_nurses_by_center(request):
    center_id = request.GET.get('center_id')
    if not center_id:
        return JsonResponse({'nurses': []})

    nurses = Nurse.objects.filter(
        donation_center_id=center_id,
        is_approved=True  # Only approved nurses
    ).select_related('user')

    nurse_data = []
    for nurse in nurses:
        # USE NURSE'S FIELDS, NOT USER'S
        full_name = f"{nurse.first_name} {nurse.last_name}".strip()
        
        # Fallback to user if nurse fields are empty
        if not full_name:
            full_name = f"{nurse.user.first_name} {nurse.user.last_name}".strip()
        
        if not full_name:
            full_name = nurse.user.username  # Last resort
        
        nurse_data.append({
            'id': nurse.id,
            'name': full_name,
            'specialization': nurse.specialization or 'General Practitioner',
            'email': nurse.user.email or '',
            'phone': nurse.phone or '',
            'bio': nurse.bio or '',
            'profile_pic_url': nurse.profile_pic.url if nurse.profile_pic else None,
        })

    print(f"DEBUG: Center {center_id} - Found {len(nurse_data)} nurses")  # Debug line
    return JsonResponse({'nurses': nurse_data})