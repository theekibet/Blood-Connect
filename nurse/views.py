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
from .models import Nurse, Appointment, NurseBloodRequest
from .forms import (
    NurseLoginForm, NurseSignupForm, NurseForm, AppointmentForm, RequestForm,
)
from blood.models import Notification, Stock, DonationCenter, StockUnit,StockTransaction
from blood.utils.stock_utils import deduct_stock_fifo
from datetime import datetime
from donor.models import BloodDonate,DonorBloodRequest
from patient.models import BloodRequest 
from collections import OrderedDict
from django.views.generic import DetailView
from django.core.exceptions import ValidationError
from django.db.models import Q
from collections import defaultdict
from .forms import NurseUserForm
from donor.models import Donor
from django.db.models import Prefetch
from django.contrib.auth.mixins import LoginRequiredMixin
from patient.models import Patient
from functools import wraps
from django.views.generic import ListView
from blood.utils.notifications import create_notification
from blood.utils.greetings import get_nurse_greeting
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
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
            return redirect('nurselogin')
        
        try:
            nurse = request.user.nurse
            if not nurse.is_approved:
                messages.warning(
                    request, 
                    "⏳ Your account is pending admin approval. You'll receive an email once approved."
                )
                return redirect('nurse-pending-approval')
        except Nurse.DoesNotExist:
            messages.error(request, "❌ Nurse profile not found.")
            return redirect('nurselogin')
        
        return view_func(request, *args, **kwargs)
    return wrapper

# ---------------------------
# Nurse Signup View (UPDATED - NO EMAIL VERIFICATION)
# ---------------------------
def nurse_signup_view(request):
    """
    Handle nurse registration WITHOUT email verification.
    Only admin approval required.
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
                
                # Create user - ACTIVE IMMEDIATELY (no email verification)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True  # CHANGED: Active immediately
                )
                
                # Save nurse profile (pending admin approval)
                nurse = form.save(commit=False)
                nurse.user = user
                nurse.is_approved = False  # Still needs admin approval
                nurse.save()
                
                # Add to NURSE group
                nurse_group, _ = Group.objects.get_or_create(name="NURSE")
                nurse_group.user_set.add(user)
                
                # Send welcome email (optional, not required for login)
                try:
                    from blood.tasks import send_nurse_welcome_email_task  # Rename this task
                    
                    # Send welcome email asynchronously (optional)
                    send_nurse_welcome_email_task.delay(
                        user.id,
                        user.email,
                        request.get_host()
                    )
                    
                    messages.success(
                        request,
                        f"🎉 Registration successful, {user.first_name}! "
                        f"Your account has been created and is pending admin approval. "
                        f"You can login but access will be limited until approved."
                    )
                    
                    email_sent = True
                    
                except Exception as e:
                    # Email is optional, so just log the error
                    logger.error(f"Nurse welcome email task error: {str(e)}", exc_info=True)
                    
                    # Still show success message
                    messages.success(
                        request,
                        f"🎉 Registration successful, {user.first_name}! "
                        f"Your account has been created and is pending admin approval. "
                        f"You can login but access will be limited until approved."
                    )
                    
                    email_sent = False
                
                # Log the registration
                logger.info(f"New nurse registration: {user.username} ({user.email}) - Pending admin approval")
                
                # Notify admin about new nurse registration (optional)
                try:
                    from blood.tasks import notify_admin_new_nurse_task
                    notify_admin_new_nurse_task.delay(nurse.id)
                except Exception as e:
                    logger.error(f"Admin notification task error: {str(e)}")
                
                return redirect("nurselogin")
                
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
        return redirect('nurse-dashboard')
    
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
                            return redirect('nurse-pending-approval')
                    
                    # All checks passed - Login successful
                    login(request, user)
                    logger.info(f"Nurse login successful: {user.username} ({user.email}) - Approved: {nurse.is_approved}")
                    
                    messages.success(request, f"✅ Welcome back, {nurse.full_name or user.username}!")
                    return redirect('nurse-dashboard')
                    
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
        return redirect('nurselogin')
    
    try:
        nurse = request.user.nurse
        
        # If nurse is already approved, redirect to dashboard
        if nurse.is_approved:
            return redirect('nurse-dashboard')
        
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
        return redirect('nurselogin')

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
# ---------------------------
# Blood Requests
# ---------------------------
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def blood_request_bookings(request):
    """
    View for nurse to see BLOOD REQUEST appointments only.
    These are requests FROM:
    - Patients requesting blood for themselves (BloodRequest)
    - Donors requesting blood on behalf of other patients (DonorBloodRequest)
    
    EXCLUDES: BloodDonate (donation appointments - those are in nurse_donation_bookings)
    
    NOW INCLUDES: Patient blood group verification status
    """
    nurse = get_object_or_404(Nurse, user=request.user)

    # Import here to avoid circular import issues
    from donor.models import DonorBloodRequest
    from patient.models import BloodRequest

    # ==========================================
    # ONLY GET BLOOD REQUEST CONTENT TYPES
    # (Exclude BloodDonate - those are donations, not requests)
    # ==========================================
    blood_request_ct = ContentType.objects.get_for_model(BloodRequest)
    donor_blood_request_ct = ContentType.objects.get_for_model(DonorBloodRequest)

    logger.info(f"Blood Request ContentTypes - BloodRequest: {blood_request_ct.id}, "
                f"DonorBloodRequest: {donor_blood_request_ct.id}")

    # Get appointments for BLOOD REQUESTS ONLY (patients + donors requesting blood)
    appointments = Appointment.objects.filter(
        nurse=nurse,
        request_content_type__in=[blood_request_ct, donor_blood_request_ct]
    ).select_related(
        'donor__user',
        'patient__user',
        'nurse__user',
        'donation_center',
        'request_content_type',
        'status_changed_by',
        'cancelled_by_user',
        'approved_by_nurse',
        'completed_by_nurse'
    ).order_by('-date')

    logger.info(f"Found {appointments.count()} blood request appointments for nurse {nurse.id}")

    enhanced_appointments = []
    for appointment in appointments:
        appointment_data = {
            'appointment': appointment,
            'request': None,
            'requester': None,
            'requester_type': None,
            'blood_details': {},
            'patient': None,  # NEW: Track actual patient object
            'bloodgroup_verified': False,  # NEW: Verification status
            'verified_bloodgroup': None,  # NEW: Verified blood group value
        }

        try:
            # 🩸 Patient BloodRequest (Patient requesting blood for themselves)
            if appointment.request_content_type == blood_request_ct:
                req = BloodRequest.objects.select_related(
                    'request_by_patient__user', 'donation_center'
                ).get(id=appointment.request_object_id)
                
                # Get patient and check verification status
                patient = req.request_by_patient
                bloodgroup_verified = False
                verified_bloodgroup = None
                
                if patient:
                    bloodgroup_verified = getattr(patient, 'bloodgroup_verified', False)
                    if bloodgroup_verified:
                        verified_bloodgroup = getattr(patient, 'bloodgroup', None)
                        logger.info(f"✅ Patient {patient.id} has VERIFIED blood group: {verified_bloodgroup}")
                    else:
                        logger.info(f"⚠️ Patient {patient.id} blood group NOT yet verified")
                
                appointment_data.update({
                    'request': req,
                    'requester': req.request_by_patient,
                    'requester_type': 'patient',
                    'patient': patient,  # Store patient object
                    'bloodgroup_verified': bloodgroup_verified,
                    'verified_bloodgroup': verified_bloodgroup,
                    'blood_details': {
                        'first_name': req.first_name,
                        'last_name': req.last_name,
                        'patient_age': req.patient_age,
                        'contact_number': req.contact_number,
                        'emergency_contact': getattr(req, 'emergency_contact', None),
                        'bloodgroup': verified_bloodgroup if bloodgroup_verified else (req.bloodgroup or 'Not specified'),
                        'unit': req.unit,
                        'urgency_level': getattr(req, 'urgency_level', 'Medium'),
                        'center': req.donation_center,
                        'status': req.status,
                        'created_at': req.created_at,
                        'consent_confirmed': getattr(req, 'consent_confirmed', False),
                    }
                })
                logger.info(f"✅ Loaded Patient BloodRequest {req.id} for appointment {appointment.id}")

            # 🧍 DonorBloodRequest (Donor requesting blood on behalf of another patient)
            elif appointment.request_content_type == donor_blood_request_ct:
                req = DonorBloodRequest.objects.select_related(
                    'request_by_donor__user', 'donation_center'
                ).get(id=appointment.request_object_id)
                
                # For donor requests, check if there's a linked patient in the appointment
                patient = appointment.patient if hasattr(appointment, 'patient') else None
                bloodgroup_verified = False
                verified_bloodgroup = None
                
                if patient:
                    bloodgroup_verified = getattr(patient, 'bloodgroup_verified', False)
                    if bloodgroup_verified:
                        verified_bloodgroup = getattr(patient, 'bloodgroup', None)
                        logger.info(f"✅ Patient {patient.id} (via donor) has VERIFIED blood group: {verified_bloodgroup}")
                
                appointment_data.update({
                    'request': req,
                    'requester': req.request_by_donor,
                    'requester_type': 'donor',
                    'patient': patient,  # Store patient object if exists
                    'bloodgroup_verified': bloodgroup_verified,
                    'verified_bloodgroup': verified_bloodgroup,
                    'blood_details': {
                        'patient_first_name': req.patient_first_name,
                        'patient_last_name': req.patient_last_name,
                        'patient_name': f"{req.patient_first_name} {req.patient_last_name}",
                        'patient_age': getattr(req, 'patient_age', None),
                        'patient_dob': getattr(req, 'patient_dob', None),
                        'contact_number': req.contact_number,
                        'bloodgroup': verified_bloodgroup if bloodgroup_verified else req.bloodgroup,
                        'unit': req.unit,
                        'urgency_level': req.urgency_level,
                        'reason': getattr(req, 'reason', None),
                        'center': req.donation_center,
                        'status': req.status,
                        'created_at': req.created_at,
                        'consent_confirmed': req.consent_confirmed,
                        'donor_name': req.request_by_donor.user.get_full_name() if req.request_by_donor.user else 'N/A',
                    }
                })
                logger.info(f"✅ Loaded DonorBloodRequest {req.id} for appointment {appointment.id}")

        except BloodRequest.DoesNotExist:
            logger.error(f"❌ BloodRequest {appointment.request_object_id} not found for appointment {appointment.id}")
        except DonorBloodRequest.DoesNotExist:
            logger.error(f"❌ DonorBloodRequest {appointment.request_object_id} not found for appointment {appointment.id}")
        except Exception as e:
            logger.error(f"❌ Error loading request for appointment {appointment.id}: {str(e)}", exc_info=True)

        enhanced_appointments.append(appointment_data)

    # Calculate statistics
    total_count = len(enhanced_appointments)
    pending_count = sum(1 for item in enhanced_appointments if item['appointment'].status == 'pending')
    approved_count = sum(1 for item in enhanced_appointments if item['appointment'].status == 'approved')
    completed_count = sum(1 for item in enhanced_appointments if item['appointment'].status == 'completed')
    
    # NEW: Count verified vs unverified patients
    verified_patients = sum(1 for item in enhanced_appointments if item['bloodgroup_verified'])
    unverified_patients = sum(1 for item in enhanced_appointments if item['patient'] and not item['bloodgroup_verified'])

    context = {
        'enhanced_appointments': enhanced_appointments,
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'completed_count': completed_count,
        'verified_patients': verified_patients,
        'unverified_patients': unverified_patients,
        'now': timezone.now(),
        'nurse': nurse,
    }
    
    logger.info(f"Returning {total_count} blood request appointments: "
                f"{pending_count} pending, {approved_count} approved, {completed_count} completed. "
                f"Verified: {verified_patients}, Unverified: {unverified_patients}")
    
    return render(request, 'nurse/blood_request_bookings.html', context)




logger = logging.getLogger(__name__)

def get_patient_profile(user):
    """
    Return patient profile if user has one, else None.
    Ignores donors entirely.
    """
    if not user:
        return None
    try:
        if hasattr(user, "patient"):
            return user.patient
    except Exception:
        pass
    return None

# ----------------------------------------------------------------------------------------------------
# UPDATE BLOODREQUEST BOOKINGS STATUS(from either patients or donors requesting on behalf of patients)
# -----------------------------------------------------------------------------------------------------
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def nurse_update_bloodrequest_appointment_status(request, appointment_id):
    """
    Nurse handler for BLOOD REQUEST appointments.
    Uses centralized notification system.
    Sends notifications to both patients and donors as appropriate.
    """
    logger.info(f"🚀 VIEW CALLED: nurse_update_bloodrequest_appointment_status for appointment_id={appointment_id}")
    
    try:
        nurse = request.user.nurse
        logger.info(f"🚀 Nurse: {nurse.user.get_full_name()} (ID: {nurse.id})")
        now = timezone.now()

        # Normalize action
        raw_action = (request.POST.get('action') or '').strip().lower()
        action_map = {
            'approve': 'approved', 'approved': 'approved',
            'reject': 'rejected', 'rejected': 'rejected',
            'complete': 'completed', 'completed': 'completed',
            'cancel': 'cancelled', 'cancelled': 'cancelled',
        }
        action = action_map.get(raw_action)

        if not action:
            logger.error(f"Invalid action received: '{raw_action}'")
            return JsonResponse({
                'success': False,
                'error': f"Invalid or missing action '{raw_action}'."
            }, status=400)

        with transaction.atomic():
            appointment = get_object_or_404(
                Appointment.objects.select_for_update(),
                id=appointment_id
            )

            # Assign nurse if not set
            if not appointment.nurse:
                appointment.nurse = nurse
                appointment.save(update_fields=['nurse'])
            elif appointment.nurse != nurse:
                return JsonResponse({
                    'success': False,
                    'error': 'This appointment is already assigned to another nurse.'
                }, status=403)

            # Resolve linked request
            linked_request = None
            if appointment.request_content_type and appointment.request_object_id:
                model_class = appointment.request_content_type.model_class()
                model_name = model_class.__name__
                
                if model_name == 'BloodDonate':
                    return JsonResponse({
                        'success': False,
                        'error': 'This is a blood donation appointment. Use the donation endpoint.'
                    }, status=400)
                
                elif model_name in ['BloodRequest', 'DonorBloodRequest']:
                    try:
                        linked_request = model_class.objects.select_for_update().get(
                            id=appointment.request_object_id
                        )
                    except model_class.DoesNotExist:
                        return JsonResponse({
                            'success': False,
                            'error': f'{model_name} not found.'
                        }, status=404)
            
            if not linked_request:
                return JsonResponse({
                    'success': False,
                    'error': 'Could not find the associated blood request.'
                }, status=400)

            # Block finalized appointments
            if appointment.status in ['completed', 'cancelled', 'rejected']:
                return JsonResponse({
                    'success': False,
                    'error': f"This appointment is already {appointment.status}."
                }, status=400)

            # Determine if this is a donor or patient request
            donor = None
            if hasattr(linked_request, 'request_by_donor') and linked_request.request_by_donor:
                donor = linked_request.request_by_donor
            elif appointment.donor:
                donor = appointment.donor

            # Get patient for notifications
            patient = None
            if hasattr(linked_request, 'request_by_patient') and linked_request.request_by_patient:
                patient = linked_request.request_by_patient
            elif appointment.patient:
                patient = appointment.patient

            reason = (request.POST.get('reason') or '').strip()
            
            # Get appointment details for notification message
            date_str = appointment.date.strftime("%b %d, %Y %I:%M %p")
            center_name = getattr(linked_request.donation_center, "name", "Unknown center") if hasattr(linked_request, 'donation_center') else "Unknown center"
            nurse_name = nurse.user.get_full_name() or nurse.user.username
            
            # === ACTION HANDLERS ===
            if action == 'approved':
                if appointment.approved_by_nurse:
                    return JsonResponse({'success': False, 'error': 'Already approved.'}, status=400)

                appointment.set_status('approved', nurse.user)
                linked_request.status = 'approved'
                if hasattr(linked_request, 'approved_by_nurse'):
                    linked_request.approved_by_nurse = nurse
                if hasattr(linked_request, 'approved_at_nurse'):
                    linked_request.approved_at_nurse = now
                linked_request.save()

                # 🔔 Send notification to patient (if exists)
                if patient:
                    create_notification(
                        title="Appointment Approved",
                        message=f"Your blood request appointment on {date_str} at {center_name} was approved by Nurse {nurse_name}.",
                        recipient_obj=patient,
                        sender_obj=nurse,
                        action='approved',
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                # 🔔 Send notification to donor (if this is a donor request)
                if donor:
                    create_notification(
                        title="Appointment Approved",
                        message=f"Your blood request appointment on {date_str} at {center_name} was approved by Nurse {nurse_name}.",
                        recipient_obj=donor,
                        sender_obj=nurse,
                        action='approved',
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                logger.info(f"✅ Appointment {appointment.id} approved")
                return JsonResponse({
                    'success': True,
                    'status': 'approved',
                    'message': f"Request approved by {nurse_name}",
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                })

            elif action == 'rejected':
                appointment.set_status('rejected', nurse.user)
                linked_request.status = 'rejected'
                if hasattr(linked_request, 'rejected_by'):
                    linked_request.rejected_by = 'nurse'
                if hasattr(linked_request, 'rejected_at'):
                    linked_request.rejected_at = now
                if hasattr(linked_request, 'rejection_reason'):
                    linked_request.rejection_reason = reason
                linked_request.save()

                # 🔔 Send notification to patient (if exists)
                if patient:
                    create_notification(
                        title="Appointment Rejected",
                        message=f"Your blood request appointment on {date_str} at {center_name} was rejected by Nurse {nurse_name}.",
                        recipient_obj=patient,
                        sender_obj=nurse,
                        action='rejected',
                        reason=reason,
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                # 🔔 Send notification to donor (if this is a donor request)
                if donor:
                    create_notification(
                        title="Appointment Rejected",
                        message=f"Your blood request appointment on {date_str} at {center_name} was rejected by Nurse {nurse_name}.",
                        recipient_obj=donor,
                        sender_obj=nurse,
                        action='rejected',
                        reason=reason,
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                logger.info(f"✅ Appointment {appointment.id} rejected")
                return JsonResponse({
                    'success': True,
                    'status': 'rejected',
                    'message': f"Request rejected by {nurse_name}",
                    'reason': reason,
                })

            elif action == 'cancelled':
                appointment.set_status('cancelled', nurse.user)
                linked_request.status = 'cancelled'
                if hasattr(linked_request, 'cancelled_by'):
                    linked_request.cancelled_by = 'nurse'
                if hasattr(linked_request, 'cancelled_at'):
                    linked_request.cancelled_at = now
                if hasattr(linked_request, 'cancellation_reason'):
                    linked_request.cancellation_reason = reason
                linked_request.save()

                # 🔔 Send notification to patient (if exists)
                if patient:
                    create_notification(
                        title="Appointment Cancelled",
                        message=f"Your blood request appointment on {date_str} at {center_name} was cancelled by Nurse {nurse_name}.",
                        recipient_obj=patient,
                        sender_obj=nurse,
                        action='cancelled',
                        reason=reason,
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                # 🔔 Send notification to donor (if this is a donor request)
                if donor:
                    create_notification(
                        title="Appointment Cancelled",
                        message=f"Your blood request appointment on {date_str} at {center_name} was cancelled by Nurse {nurse_name}.",
                        recipient_obj=donor,
                        sender_obj=nurse,
                        action='cancelled',
                        reason=reason,
                        appointment_date=appointment.date,
                        bloodgroup=linked_request.bloodgroup,
                        unit=linked_request.unit
                    )
                
                logger.info(f"✅ Appointment {appointment.id} cancelled")
                return JsonResponse({
                    'success': True,
                    'status': 'cancelled',
                    'message': f"Request cancelled by {nurse_name}",
                    'reason': reason,
                })

            elif action == 'completed':
                if appointment.status != 'approved':
                    return JsonResponse({
                        'success': False, 
                        'error': 'Request must be approved before completion.'
                    }, status=400)
                    
                if appointment.completed_by_nurse:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Already completed.'
                    }, status=400)

                # Validate blood group and units
                new_bg = (request.POST.get('bloodgroup') or '').strip()
                new_unit = (request.POST.get('unit') or '').strip()

                final_unit = getattr(linked_request, 'unit', None)
                if new_unit:
                    try:
                        final_unit = int(new_unit)
                        if final_unit < 450 or final_unit > 2700 or final_unit % 50 != 0:
                            return JsonResponse({
                                'success': False, 
                                'error': 'Unit must be 450–2700 ml in multiples of 50.'
                            }, status=400)
                    except ValueError:
                        return JsonResponse({
                            'success': False, 
                            'error': 'Invalid unit value.'
                        }, status=400)

                final_bg = new_bg or getattr(linked_request, 'bloodgroup', None)
                
                if not final_bg or not final_unit:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Blood group and units are required for completion.'
                    }, status=400)

                valid_blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
                if final_bg not in valid_blood_groups:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Invalid blood group: {final_bg}'
                    }, status=400)

                center = getattr(linked_request, 'donation_center', None)
                if not center:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Donation center is missing.'
                    }, status=400)

                # Verify patient blood group on first request
                blood_group_was_verified = False
                if patient:
                    if not patient.bloodgroup_verified:
                        patient.bloodgroup = final_bg
                        patient.bloodgroup_verified = True
                        patient.bloodgroup_verified_by = nurse.user
                        patient.bloodgroup_verified_at = now
                        patient.save(update_fields=[
                            'bloodgroup', 
                            'bloodgroup_verified', 
                            'bloodgroup_verified_by', 
                            'bloodgroup_verified_at'
                        ])
                        blood_group_was_verified = True
                        logger.info(f"✅ Blood group verified: {final_bg} for patient {patient.id}")
                    else:
                        if patient.bloodgroup != final_bg:
                            return JsonResponse({
                                'success': False,
                                'error': f'Patient has verified blood group {patient.bloodgroup}. Cannot use {final_bg}.'
                            }, status=400)

                # Check stock availability
                available_units = StockUnit.objects.filter(
                    center=center,
                    bloodgroup=final_bg,
                    unit__gt=0,
                    expiry_date__gte=timezone.now().date()
                )
                total_available = sum([su.unit for su in available_units])
                
                if total_available < final_unit:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Insufficient stock: Only {total_available}ml available. Required: {final_unit}ml.'
                    }, status=400)

                # Deduct stock
                from blood.utils.stock_utils import deduct_stock_fifo
                success, result = deduct_stock_fifo(center, final_bg, final_unit)
                
                if not success:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Stock deduction failed: {result}'
                    }, status=400)

                deductions = result

                # Log transactions
                for d in deductions:
                    try:
                        stock_unit = StockUnit.objects.get(barcode=d['barcode'])
                        
                        # Determine recipient name for transaction notes
                        recipient_name = "Unknown"
                        if patient:
                            recipient_name = patient.user.get_full_name()
                        elif donor:
                            recipient_name = f"via Donor {donor.user.get_full_name()}"
                        
                        tx_data = {
                            'stockunit': stock_unit,
                            'appointment': appointment,
                            'quantity_deducted': d['quantity'],
                            'transaction_type': 'deduction',
                            'user': nurse.user,
                            'notes': f"Blood request completion - {final_unit}ml {final_bg} for {recipient_name}"
                        }
                        
                        model_name = linked_request.__class__.__name__
                        if model_name == 'BloodRequest':
                            tx_data['blood_request'] = linked_request
                        elif model_name == 'DonorBloodRequest':
                            tx_data['donor_blood_request'] = linked_request
                        
                        StockTransaction.objects.create(**tx_data)
                    except Exception as e:
                        logger.error(f"Transaction logging failed: {e}")

                # Mark as completed
                appointment.set_status('completed', nurse.user)
                linked_request.status = 'completed'
                
                if hasattr(linked_request, 'completed_by_nurse'):
                    linked_request.completed_by_nurse = nurse
                if hasattr(linked_request, 'completed_at_nurse'):
                    linked_request.completed_at_nurse = now
                if hasattr(linked_request, 'stock_deducted'):
                    linked_request.stock_deducted = True
                if hasattr(linked_request, 'bloodgroup'):
                    linked_request.bloodgroup = final_bg
                    
                linked_request.save()

                # 🔔 Send notification to patient (if exists)
                if patient:
                    completion_message = f"Your blood request appointment on {date_str} at {center_name} was completed by Nurse {nurse_name}. {final_unit}ml of {final_bg} was provided."
                    
                    if blood_group_was_verified:
                        completion_message += f" Your blood group has been verified as {final_bg}."
                    
                    create_notification(
                        title="Appointment Completed",
                        message=completion_message,
                        recipient_obj=patient,
                        sender_obj=nurse,
                        action='completed',
                        appointment_date=appointment.date,
                        bloodgroup=final_bg,
                        unit=final_unit
                    )
                
                # 🔔 Send notification to donor (if this is a donor request)
                if donor:
                    completion_message = f"Your blood request appointment on {date_str} at {center_name} was completed by Nurse {nurse_name}. {final_unit}ml of {final_bg} was provided."
                    
                    create_notification(
                        title="Appointment Completed",
                        message=completion_message,
                        recipient_obj=donor,
                        sender_obj=nurse,
                        action='completed',
                        appointment_date=appointment.date,
                        bloodgroup=final_bg,
                        unit=final_unit
                    )
                
                logger.info(f"✅ COMPLETED: Appointment {appointment.id}")

                response_data = {
                    'success': True,
                    'status': 'completed',
                    'message': f"Request completed. Deducted {final_unit}ml of {final_bg} from stock.",
                    'action_by': nurse_name,
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                }
                
                if blood_group_was_verified:
                    response_data['bloodgroup_verified'] = True
                    response_data['verified_bloodgroup'] = final_bg
                
                return JsonResponse(response_data)

    except Appointment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Appointment not found.'}, status=404)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'Unexpected error: {str(e)}'}, status=500)

def serialize_deductions(deduction_result):
    """Helper function to serialize deduction results for session storage"""
    return [
        {
            'barcode': d['barcode'],
            'quantity': d['quantity'],
            'expiry_date': d['expiry_date'].isoformat() if d['expiry_date'] else None
        }
        for d in deduction_result
    ]


# ----------------------------------
#Donation Related Appointments
# ------------------------------------
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_donation_bookings(request):
    """
    Modern healthcare view for nurse to manage DONATION appointments.
    Real-time safety tracking with visual status indicators.
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
            'approved_by_nurse',
            'completed_by_nurse'
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
                'approved_by_nurse': getattr(blood_donate, 'approved_by_nurse', None),
                'completed_by_nurse': getattr(blood_donate, 'completed_by_nurse', None),
                'safety_flags': safety_flags,
                'is_quarantined': is_quarantined,
            }
        
        # Appointment status analysis
        appointment_status = appointment.status
        status_analysis = {
            'can_approve': appointment_status == 'pending',
            'can_complete': appointment_status == 'approved',
            'can_cancel': appointment_status in ['pending', 'approved'],
            'is_final': appointment_status in ['completed', 'cancelled', 'rejected'],
            'requires_safety_check': appointment_status == 'approved',
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
                appointment.approved_by_nurse or 
                appointment.completed_by_nurse or 
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
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def nurse_update_donation_appointment_status(request, appointment_id):
    """
    Handler for updating DONATION appointment status (BloodDonate).
    Supports: approve, reject, cancel, complete actions.
    NOW INCLUDES: Safety verification during completion
    """
    logger.info(f"=== Processing donation appointment {appointment_id} ===")
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
            valid_actions = ['approve', 'reject', 'completed', 'cancelled']
            if action not in valid_actions:
                return JsonResponse({
                    'success': False,
                    'error': f"Invalid action '{action}'. Valid: {', '.join(valid_actions)}"
                }, status=400)

            # Prevent double-finalizing
            if appointment.status in ['completed', 'cancelled', 'rejected'] or \
               donation.status in ['completed', 'cancelled', 'rejected']:
                return JsonResponse({
                    'success': False,
                    'error': f'This donation already has a final status: {appointment.status}.'
                }, status=400)

            # Reason for reject/cancel
            reason = (request.POST.get('reason') or '').strip()

            # Helper: update statuses
            def update_status(app_status, don_status, **kwargs):
                appointment.status = app_status
                appointment.save()

                old_status = donation.status
                donation.status = don_status

                for field, value in kwargs.items():
                    setattr(donation, field, value)

                donation.save()

                logger.info(
                    f"Nurse {nurse.user.username} changed donation {donation.id} "
                    f"from '{old_status}' to '{don_status}'"
                )

                return f"Donation {don_status} successfully by nurse {nurse.user.get_full_name()}."

            # =======================
            # ACTION: APPROVE
            # =======================
            if action == 'approve':
                if getattr(donation, 'approved_by_nurse', None):
                    return JsonResponse({
                        'success': False,
                        'error': 'This donation has already been approved.'
                    }, status=400)

                message = update_status(
                    'approved', 'approved',
                    approved_by_nurse=nurse.user,
                    approved_at_nurse=now
                )

                create_appointment_notification(appointment, nurse.user, 'approved')

                return JsonResponse({
                    'success': True,
                    'status': 'approved',
                    'message': message,
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_approval'
                })

            # =======================
            # ACTION: REJECT
            # =======================
            elif action == 'reject':
                message = update_status(
                    'rejected', 'rejected',
                    rejected_by='nurse',
                    rejected_at=now,
                    rejection_reason=reason
                )

                create_appointment_notification(appointment, nurse.user, 'rejected', reason)

                return JsonResponse({
                    'success': True,
                    'status': 'rejected',
                    'message': f'{message}' + (f' Reason: {reason}' if reason else ''),
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_rejection'
                })

            # =======================
            # ACTION: CANCEL
            # =======================
            elif action == 'cancelled':
                message = update_status(
                    'cancelled', 'cancelled',
                    cancelled_by='nurse',
                    cancelled_at=now,
                    cancellation_reason=reason
                )

                create_appointment_notification(appointment, nurse.user, 'cancelled', reason)

                return JsonResponse({
                    'success': True,
                    'status': 'cancelled',
                    'message': f'{message}' + (f' Reason: {reason}' if reason else ''),
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'operation_type': 'donation_cancellation'
                })

            # =======================
            # ACTION: COMPLETED (WITH SAFETY VERIFICATION)
            # =======================
            elif action == 'completed':
                # ----- Validation -----
                if appointment.status != 'approved':
                    return JsonResponse({
                        'success': False,
                        'error': 'Donation must be approved before completion.'
                    }, status=400)

                if getattr(donation, 'stock_added_by_nurse', False):
                    return JsonResponse({
                        'success': False,
                        'error': 'Stock has already been added for this donation.'
                    }, status=400)

                # ----- Get form values -----
                new_bg = request.POST.get('bloodgroup', '').strip()
                new_unit = request.POST.get('unit', '').strip()
                
                # ===== SAFETY VERIFICATION FIELDS =====
                safety_status = request.POST.get('safety_status', '').strip().lower()
                unsafe_reason = request.POST.get('unsafe_reason', '').strip()
                safety_notes = request.POST.get('safety_notes', '').strip()

                # Validate safety status
                if safety_status not in ['safe', 'unsafe']:
                    return JsonResponse({
                        'success': False,
                        'error': 'Safety status must be specified as either "safe" or "unsafe".'
                    }, status=400)

                # If unsafe, require reason
                if safety_status == 'unsafe' and not unsafe_reason:
                    return JsonResponse({
                        'success': False,
                        'error': 'Unsafe reason is required when marking blood as unsafe.'
                    }, status=400)

                # Validate blood group
                if new_bg:
                    valid_bgs = [choice[0] for choice in BLOODGROUP_CHOICES]
                    if new_bg not in valid_bgs:
                        return JsonResponse({
                            'success': False,
                            'error': f'Invalid blood group: {new_bg}. Valid: {", ".join(valid_bgs)}'
                        }, status=400)

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

                # ----- Apply updates -----
                if new_bg and new_bg != donation.bloodgroup:
                    donation.bloodgroup = new_bg

                if units_value is not None and units_value != donation.unit:
                    donation.unit = units_value

                donor = donation.donor

                # ==========================================
                # FIRST DONATION — VERIFY BLOOD GROUP
                # ==========================================
                if donor and not donor.bloodgroup_verified:
                    verified_bg = donation.bloodgroup
                    if not verified_bg:
                        return JsonResponse({
                            'success': False,
                            'error': 'Blood group is required for first-time verification.'
                        }, status=400)

                    donor.bloodgroup = verified_bg
                    donor.bloodgroup_verified = True
                    donor.bloodgroup_verified_by = nurse.user
                    donor.bloodgroup_verified_at = now
                    donor.save(update_fields=[
                        'bloodgroup',
                        'bloodgroup_verified',
                        'bloodgroup_verified_by',
                        'bloodgroup_verified_at'
                    ])

                    logger.info(
                        f"✅ Verified donor BG: {donor.id} -> {verified_bg} "
                        f"by nurse {nurse.user.get_full_name()}"
                    )

                # ----- Donation center -----
                center = donation.donation_center or nurse.donation_center
                if not center:
                    return JsonResponse({
                        'success': False,
                        'error': 'No donation center assigned.'
                    }, status=400)

                expiry_date = (donation.date or now.date()) + timedelta(days=46)

                # ==========================================
                # ADD STOCK WITH SAFETY STATUS (MODIFIED)
                # ==========================================
                try:
                    # Pass all necessary parameters including unsafe_reason and safety_notes
                    stock_unit = add_stock(
                        center=center, 
                        bloodgroup=donation.bloodgroup, 
                        units=donation.unit, 
                        expiry_date=expiry_date,
                        safety_status=safety_status,
                        unsafe_reason=unsafe_reason if safety_status == 'unsafe' else None,
                        safety_notes=safety_notes if safety_notes else None
                    )
                    generated_barcode = stock_unit.barcode if stock_unit else None

                    logger.info(
                        f"✅ STOCK: Added {donation.unit}ml {donation.bloodgroup} "
                        f"to {center.name} (Barcode {generated_barcode}, Status: {safety_status})"
                    )

                    # ===== VERIFY SAFETY IMMEDIATELY =====
                    # Note: Stock unit was already created with the safety status,
                    # but we call mark_safe/mark_unsafe to set the verified_by and timestamp
                    if safety_status == 'safe':
                        stock_unit.mark_safe(
                            verified_by_user=nurse.user,
                            notes=safety_notes if safety_notes else "Verified safe during donation completion"
                        )
                        logger.info(
                            f"✅ SAFE STOCK: {donation.unit}ml {donation.bloodgroup} "
                            f"verified safe by {nurse.user.get_full_name()} (Barcode {generated_barcode})"
                        )
                    
                    elif safety_status == 'unsafe':
                        # Already created as unsafe, but update verification details
                        stock_unit.safety_verified_by = nurse.user
                        stock_unit.safety_verified_at = now
                        stock_unit.save(update_fields=['safety_verified_by', 'safety_verified_at'])
                        
                        logger.warning(
                            f"⚠️ UNSAFE STOCK: {donation.unit}ml {donation.bloodgroup} "
                            f"marked unsafe ({unsafe_reason}) by {nurse.user.get_full_name()} "
                            f"(Barcode {generated_barcode})"
                        )

                except ValueError as ve:
                    logger.error(f"❌ Validation error: {ve}")
                    return JsonResponse({
                        'success': False,
                        'error': str(ve)
                    }, status=400)
                except Exception as e:
                    logger.error(f"❌ Stock add error: {e}", exc_info=True)
                    return JsonResponse({
                        'success': False,
                        'error': f"Stock addition failed: {str(e)}"
                    }, status=500)

                # ==========================================
                # STOCK TRANSACTION LOG (UPDATED)
                # ==========================================
                if stock_unit:
                    try:
                        StockTransaction.objects.create(
                            stockunit=stock_unit,
                            appointment=appointment,
                            blood_donation=donation,
                            quantity_added=donation.unit,
                            transaction_type='addition',
                            user=nurse.user,
                            notes=(
                                f"Completed donation: {donation.unit}ml {donation.bloodgroup} "
                                f"from donor {donation.donor.user.get_full_name()} - "
                                f"Safety Status: {safety_status.upper()}"
                                + (f" - Reason: {unsafe_reason}" if safety_status == 'unsafe' else "")
                                + (f" - Notes: {safety_notes}" if safety_notes else "")
                            )
                        )

                    except Exception as e:
                        logger.error(f"Transaction log error: {e}")

                # ==========================================
                # UPDATE DONATION STATUS FIRST
                # ==========================================
                donation.status = 'completed'
                donation.completed_by_nurse = nurse.user
                donation.completed_at_nurse = now
                donation.stock_added = True
                donation.save()

                appointment.status = 'completed'
                appointment.completed_by_nurse = nurse.user
                appointment.completed_at_nurse = now
                appointment.save()

                logger.info(
                    f"Nurse {nurse.user.username} completed donation {donation.id}"
                )

                # ==========================================
                # UPDATE DONOR PROFILE (FIXED & MODIFIED FOR SAFETY)
                # ==========================================
                try:
                    if donor:
                        # Only award points if blood is SAFE
                        if safety_status == 'safe':
                            donation_date = donation.date or timezone.now().date()
                            donor.last_donation_date = donation_date
                            
                            # Count BOTH approved AND completed SAFE donations
                            total_successful_donations = BloodDonate.objects.filter(
                                donor=donor, 
                                status__in=['approved', 'completed']
                            ).count()
                            
                            donor.points = total_successful_donations * 10 
                            donor.save(update_fields=['last_donation_date', 'points'])

                            logger.info(
                                f"✅ Donor {donor.user.username} updated: "
                                f"points={donor.points}, "
                                f"last_donation_date={donor.last_donation_date}, "
                                f"total_successful_donations={total_successful_donations}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Donor {donor.user.username} donated UNSAFE blood - "
                                f"points NOT awarded"
                            )
                except Exception as e:
                    logger.error(f"❌ ERROR updating donor profile: {e}", exc_info=True)

                create_appointment_notification(appointment, nurse.user, 'completed')

                # ==========================================
                # BUILD RESPONSE WITH SAFETY INFO
                # ==========================================
                response = {
                    'success': True,
                    'status': 'completed',
                    'barcode': generated_barcode,
                    'safety_status': safety_status,
                    'action_by': nurse.user.get_full_name(),
                    'operation_type': 'donation_addition',
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                }

                if safety_status == 'safe':
                    response['message'] = (
                        f"Donation completed successfully. "
                        f"Added {donation.unit}ml of {donation.bloodgroup} "
                        f"to SAFE stock (available for issuance)."
                    )
                elif safety_status == 'unsafe':
                    response['message'] = (
                        f"Donation completed but blood marked as UNSAFE. "
                        f"Unit quarantined and NOT available for issuance. "
                        f"Reason: {unsafe_reason}"
                    )
                    response['unsafe_reason'] = unsafe_reason

                # Include verification report if first donation
                if donor and donor.bloodgroup_verified and donor.bloodgroup_verified_at == now:
                    response['bloodgroup_verified'] = True
                    response['verified_bloodgroup'] = donor.bloodgroup

                # Include updated donor stats (only if safe)
                if donor and safety_status == 'safe':
                    response['donor_stats'] = {
                        'points': donor.points,
                        'total_donations': total_successful_donations,
                        'last_donation_date': donor.last_donation_date.strftime("%b %d, %Y") if donor.last_donation_date else None,
                    }

                return JsonResponse(response)

            # Should never reach here
            return JsonResponse({'success': False, 'error': f'Unhandled action: {action}'})

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

# ---------------------------
# Nurse Blood Stock View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse)
def nurse_blood_stock(request):
    nurse = get_object_or_404(Nurse, user=request.user)

    blood_stock_totals = []

    if nurse.donation_center:
        # --- SEARCH FILTER ---
        query = request.GET.get("q", "").strip()

        stockunits_qs = StockUnit.objects.filter(center=nurse.donation_center, unit__gt=0)

        if query:
            stockunits_qs = stockunits_qs.filter(
                Q(bloodgroup__icontains=query) |  # Search by blood group
                Q(unit__iexact=query) |           # Search by stock units
                Q(barcode__icontains=query)       # Search by barcode
            )

        # Aggregate stock details
        bloodgroup_qs = (
            stockunits_qs.values('bloodgroup')
            .annotate(
                total_units=Sum('unit'),
                earliest_expiry=Min('expiry_date'),
                batches_count=Count('id')
            )
            .order_by('bloodgroup')
        )

        for group in bloodgroup_qs:
            # List all batches for this blood group, sorted by expiry
            group_batches = stockunits_qs.filter(
                bloodgroup=group['bloodgroup']
            ).order_by('expiry_date')
            group['detailed_batches'] = group_batches
            blood_stock_totals.append(group)

    all_centres = DonationCenter.objects.all().order_by('name')

    selected_centre_id = request.GET.get('centre')
    other_centers_stock = None
    selected_centre = None

    if selected_centre_id:
        try:
            selected_centre = DonationCenter.objects.get(id=selected_centre_id)
            other_centers_stock = Stock.objects.filter(center=selected_centre)
        except DonationCenter.DoesNotExist:
            selected_centre = None
            other_centers_stock = None

    context = {
        'nurse': nurse,
        'blood_stock_totals': blood_stock_totals,
        'all_centres': all_centres,
        'selected_centre': selected_centre,
        'other_centers_stock': other_centers_stock,
        'today_date': localdate(),
        'query': query,  # keep search term in template
    }
    return render(request, 'nurse/blood_stock.html', context)

# ----------------------------------
#STOCKUNIT LIST(individual)
# ------------------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_stockunit_list(request, highlight_id=None):
    nurse = get_object_or_404(Nurse, user=request.user)
    center = nurse.donation_center

    if not center:
        messages.warning(request, "You are not assigned to any donation center.")
        return redirect('nurse-dashboard')

    search_query = request.GET.get('q', '').strip()
    blood_group_filter = request.GET.get('blood_group', '').strip()
    safety_status_filter = request.GET.get('safety_status', '').strip()
    stock_status_filter = request.GET.get('stock_status', '').strip()
    
    today = timezone.now().date()
    expiring_threshold = today + timedelta(days=7)

    # Base queryset - EXCLUDE UNSAFE STOCK FROM MAIN VIEW
    stockunits = StockUnit.objects.filter(center=center).exclude(safety_status='unsafe')

    # Apply search filter
    if search_query:
        stockunits = stockunits.filter(
            Q(barcode__icontains=search_query) | 
            Q(bloodgroup__icontains=search_query) |
            Q(safety_notes__icontains=search_query)
        )

    # Apply blood group filter
    if blood_group_filter:
        stockunits = stockunits.filter(bloodgroup=blood_group_filter)

    # Apply safety status filter
    if safety_status_filter:
        stockunits = stockunits.filter(safety_status=safety_status_filter)

    # Apply stock status filter
    if stock_status_filter:
        if stock_status_filter == 'expiring_soon':
            stockunits = stockunits.filter(
                expiry_date__lte=expiring_threshold,
                expiry_date__gte=today
            )
        elif stock_status_filter == 'expired':
            stockunits = stockunits.filter(expiry_date__lt=today)
        elif stock_status_filter == 'depleted':
            # We'll handle this in the processing loop
            pass
        elif stock_status_filter == 'quarantined':
            stockunits = stockunits.filter(is_quarantined=True)
        elif stock_status_filter == 'safe':
            stockunits = stockunits.filter(safety_status='safe')
        elif stock_status_filter == 'pending':
            stockunits = stockunits.filter(safety_status='pending')

    stockunits = stockunits.order_by('-added_on')

    # Aggregate deductions per stockunit from StockTransaction
    deductions = StockTransaction.objects.filter(
        transaction_type='deduction',
        stockunit__center=center
    ).values('stockunit').annotate(total_deducted=Sum('quantity_deducted'))

    deducted_map = {item['stockunit']: item['total_deducted'] for item in deductions}

    # Calculate statistics - FOR SAFE STOCK ONLY
    safe_stockunits = StockUnit.objects.filter(
        center=center,
        safety_status='safe'
    )
    
    total_stock_count = safe_stockunits.count()
    total_units = safe_stockunits.aggregate(total=Sum('unit'))['total'] or 0
    total_deducted = sum(deducted_map.values())
    total_remaining = total_units - total_deducted
    
    # Safety statistics
    safe_count = StockUnit.objects.filter(center=center, safety_status='safe').count()
    unsafe_count = StockUnit.objects.filter(center=center, safety_status='unsafe').count()
    pending_count = StockUnit.objects.filter(center=center, safety_status='pending').count()
    quarantined_count = StockUnit.objects.filter(center=center, is_quarantined=True).count()
    
    expiring_soon = safe_stockunits.filter(
        expiry_date__lte=expiring_threshold,
        expiry_date__gte=today
    ).count()
    
    expired = safe_stockunits.filter(expiry_date__lt=today).count()

    # Prepare stockunit information with status
    stockunits_info = []
    depleted_ids = []
    
    for unit in stockunits:
        deducted = deducted_map.get(unit.id, 0) or 0
        remaining = unit.unit - deducted
        percentage_remaining = (remaining / unit.unit * 100) if unit.unit > 0 else 0
        
        # Determine status based on multiple factors
        if unit.is_quarantined:
            status = 'quarantined'
            status_class = 'status-quarantined'
        elif unit.safety_status == 'unsafe':
            status = 'unsafe'
            status_class = 'status-unsafe'
        elif unit.safety_status == 'pending':
            status = 'pending_verification'
            status_class = 'status-pending'
        elif unit.expiry_date < today:
            status = 'expired'
            status_class = 'status-expired'
        elif unit.expiry_date <= expiring_threshold:
            status = 'expiring_soon'
            status_class = 'status-expiring'
        elif remaining == 0:
            status = 'depleted'
            status_class = 'status-depleted'
            depleted_ids.append(unit.id)
        elif percentage_remaining < 25:
            status = 'low_stock'
            status_class = 'status-low'
        else:
            status = 'available'
            status_class = 'status-available'
        
        # Calculate days until expiry
        days_until_expiry = (unit.expiry_date - today).days
        
        # Safety verification info
        safety_info = {
            'status': unit.safety_status,
            'verified_by': unit.safety_verified_by.get_full_name() if unit.safety_verified_by else None,
            'verified_at': unit.safety_verified_at,
            'notes': unit.safety_notes,
            'unsafe_reason': unit.unsafe_reason,
        }
        
        stockunits_info.append({
            'unit': unit,
            'deducted': deducted,
            'remaining': remaining,
            'percentage_remaining': percentage_remaining,
            'status': status,
            'status_class': status_class,
            'status_display': status.replace('_', ' ').title(),
            'days_until_expiry': days_until_expiry,
            'is_expiring_soon': 0 < days_until_expiry <= 7,
            'safety_info': safety_info,
        })

    # Apply depleted filter if selected
    if stock_status_filter == 'depleted':
        stockunits_info = [info for info in stockunits_info if info['unit'].id in depleted_ids]

    # Get distinct blood groups for dropdown
    blood_groups = list(
        StockUnit.objects.filter(center=center)
        .values_list('bloodgroup', flat=True)
        .distinct()
        .order_by('bloodgroup')
    )

    # Get next distribution barcode (for safe, non-depleted, non-expired stock)
    next_barcode = None
    if blood_group_filter:
        next_stock = StockUnit.objects.filter(
            center=center,
            bloodgroup=blood_group_filter,
            safety_status='safe',
            expiry_date__gte=today,
            is_quarantined=False
        ).exclude(
            id__in=depleted_ids
        ).order_by(
            'expiry_date',
            '-added_on'
        ).first()
        
        if next_stock:
            next_barcode = next_stock.barcode

    context = {
        'stockunits_info': stockunits_info,
        'highlight_id': highlight_id,
        'search_query': search_query,
        'blood_group_filter': blood_group_filter,
        'safety_status_filter': safety_status_filter,
        'stock_status_filter': stock_status_filter,
        'stats': {
            'total_stock_count': total_stock_count,
            'total_units': total_units,
            'total_deducted': total_deducted,
            'total_remaining': total_remaining,
            'expiring_soon': expiring_soon,
            'expired': expired,
            'safe_count': safe_count,
            'unsafe_count': unsafe_count,
            'pending_count': pending_count,
            'quarantined_count': quarantined_count,
        },
        'blood_groups': blood_groups,
        'safety_statuses': ['safe', 'pending', 'unsafe'],
        'stock_statuses': [
            ('available', 'Available'),
            ('expiring_soon', 'Expiring Soon'),
            ('expired', 'Expired'),
            ('depleted', 'Depleted'),
            ('low_stock', 'Low Stock'),
            ('quarantined', 'Quarantined'),
            ('pending_verification', 'Pending Verification'),
        ],
        'next_barcode': next_barcode,
        'today': today,
        'expiring_threshold': expiring_threshold,
    }
    
    # AJAX request for next barcode
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        blood_group = request.GET.get('blood_group', '')
        if blood_group:
            next_stock = StockUnit.objects.filter(
                center=center,
                bloodgroup=blood_group,
                safety_status='safe',
                expiry_date__gte=today,
                is_quarantined=False
            ).exclude(
                id__in=depleted_ids
            ).order_by(
                'expiry_date',
                '-added_on'
            ).first()
            
            return JsonResponse({
                'barcode': next_stock.barcode if next_stock else None,
                'expiry_date': next_stock.expiry_date.strftime("%b %d, %Y") if next_stock else None,
                'remaining_ml': next_stock.unit - deducted_map.get(next_stock.id, 0) if next_stock else None,
            })
    
    return render(request, 'nurse/stockunit_list.html', context)
# ---------------------------------------------------------------------------------
# Create Blood Request View(nurse requesting from other centres with enough stock)
# ---------------------------------------------------------------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def create_blood_request(request):
    nurse = get_object_or_404(Nurse, user=request.user)

    blood_group_prefill = request.GET.get('blood_group', '').upper()

    low_stock_threshold = 500
    sufficient_centres = []
    if blood_group_prefill:
        stocks = Stock.objects.filter(
            bloodgroup=blood_group_prefill,
            unit__gt=low_stock_threshold
        )
        sufficient_centres = stocks.values_list('center__id', 'center__name').distinct().order_by('center__name')

    if request.method == 'POST':
        form = RequestForm(request.POST)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.requester = nurse
            blood_request.status = 'pending'
            blood_request.save()
            return redirect('nurse-dashboard')  # Adjust redirect as appropriate
    else:
        initial = {}
        if blood_group_prefill:
            initial['blood_group'] = blood_group_prefill
        form = RequestForm(initial=initial)

    context = {
        'form': form,
        'blood_group_prefill': blood_group_prefill,
        'nurse': nurse,
        'sufficient_centres': sufficient_centres,
    }
    return render(request, 'nurse/create_blood_request.html', context)

# -----------------------------------
# List Nurse Related Blood Requests 
# ----------------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def list_blood_requests(request):
    nurse = get_object_or_404(Nurse, user=request.user)
    requests = NurseBloodRequest.objects.filter(requester=nurse).order_by('-created_at')
    context = {
        'requests': requests
    }
    return render(request, 'nurse/blood_requests_list.html', context)

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


class UnifiedAppointmentDetailView(LoginRequiredMixin, DetailView):
    """
    Unified detailed view for ALL appointments (pending, approved, completed, etc.)
    Works for both Blood Requests and Donations
    """
    model = Appointment
    template_name = 'nurse/appointment_detail.html'
    context_object_name = 'appointment'
    
    def get_queryset(self):
        """Optimize queries with select_related and prefetch_related"""
        return Appointment.objects.filter(
            nurse__user=self.request.user
        ).select_related(
            'nurse',
            'nurse__user',
            'nurse__donation_center',
            'patient',
            'patient__user',
            'donor',
            'donor__user',
            'donation_center',
            'completed_by_nurse',
            'approved_by_nurse',
            'status_changed_by',
            'cancelled_by_user',
            'request_content_type'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appointment = self.object
        
        # Determine appointment type
        context['appointment_type'] = self._get_appointment_type(appointment)
        context['is_blood_request'] = appointment.request_content_type is not None
        context['is_pure_donation'] = appointment.is_donation
        
        # Add request details based on type
        request_details = self._get_request_details(appointment)
        context.update(request_details)
        
        # Add participant details
        participant_details = self._get_participant_details(appointment)
        context.update(participant_details)
        
        # Add stock-related information
        stock_info = self._get_stock_information(appointment)
        context.update(stock_info)
        
        # Add time metrics
        time_metrics = self._calculate_time_metrics(appointment)
        context.update(time_metrics)
        
        # Add appointment timeline
        context['timeline'] = self._build_timeline(appointment)
        
        # Add action permissions
        context['can_approve'] = appointment.status == 'pending'
        context['can_complete'] = appointment.status == 'approved'
        context['can_reject'] = appointment.status == 'pending'
        context['can_cancel'] = appointment.status in ['pending', 'approved']
        
        # Add available blood groups for completion modal
        context['blood_group_choices'] = BLOODGROUP_CHOICES
        
        return context
    
    def _get_appointment_type(self, appointment):
        """Determine if this is a donation, patient request, or donor request"""
        if appointment.request_content_type:
            model_name = appointment.request_content_type.model
            if model_name == 'bloodrequest':
                return 'patient_request'
            elif model_name == 'donorbloodrequest':
                return 'donor_request'
            elif model_name == 'blooddonate':
                return 'pure_donation'
        elif appointment.donor and not appointment.patient:
            return 'pure_donation'
        return 'unknown'
    
    def _get_request_details(self, appointment):
        """Get details of the linked request object"""
        context = {}
        
        if not appointment.request_content_type or not appointment.request_object_id:
            context['request_object'] = None
            context['request_type'] = None
            return context
        
        model_class = appointment.request_content_type.model_class()
        model_name = model_class.__name__
        
        try:
            request_obj = model_class.objects.select_related(
                'donation_center'
            ).get(id=appointment.request_object_id)
            
            context['request_object'] = request_obj
            context['request_type'] = model_name
            
            # Extract common fields
            context['blood_details'] = {
                'bloodgroup': getattr(request_obj, 'bloodgroup', 'N/A'),
                'unit': getattr(request_obj, 'unit', None),
                'reason': getattr(request_obj, 'reason', None),
                'center': getattr(request_obj, 'donation_center', None),
                'status': getattr(request_obj, 'status', 'pending'),
                'created_at': getattr(request_obj, 'created_at', None),
                'urgency_level': getattr(request_obj, 'urgency_level', None),
            }
            
            # Add type-specific fields
            if model_name == 'BloodRequest':
                context['blood_details'].update({
                    'patient_name': f"{request_obj.first_name} {request_obj.last_name}",
                    'patient_age': getattr(request_obj, 'patient_age', None),
                    'contact_number': getattr(request_obj, 'contact_number', None),
                    'emergency_contact': getattr(request_obj, 'emergency_contact', None),
                    'national_id': getattr(request_obj, 'national_id', None),
                })
            elif model_name == 'DonorBloodRequest':
                context['blood_details'].update({
                    'patient_name': getattr(request_obj, 'patient_name', None),
                    'patient_age': getattr(request_obj, 'patient_age', None),
                })
            elif model_name == 'BloodDonate':
                context['blood_details'].update({
                    'donor_age': getattr(request_obj, 'donor_age', None),
                })
                
        except model_class.DoesNotExist:
            logger.warning(f"Request object {model_name} with ID {appointment.request_object_id} not found")
            context['request_object'] = None
            context['request_type'] = None
            context['blood_details'] = {}
        
        return context
    
    def _get_participant_details(self, appointment):
        """Get detailed information about donor/patient"""
        context = {}
        
        # Donor details
        if appointment.donor:
            donor = appointment.donor
            context['donor_details'] = {
                'name': donor.user.get_full_name() or donor.user.username,
                'username': donor.user.username,
                'email': donor.user.email,
                'blood_group': getattr(donor, 'bloodgroup', getattr(donor, 'blood_group', 'N/A')),
                'age': getattr(donor, 'age', None),
                'gender': getattr(donor, 'gender', 'N/A'),
                'contact': getattr(donor, 'mobile', getattr(donor, 'contact_number', 'N/A')),
                'address': getattr(donor, 'address', 'N/A'),
                'national_id': getattr(donor, 'national_id', 'N/A'),
                'profile_pic': getattr(donor, 'profile_pic', None),
            }
        
        # Patient details
        if appointment.patient:
            patient = appointment.patient
            context['patient_details'] = {
                'name': patient.user.get_full_name() or patient.user.username,
                'username': patient.user.username,
                'email': patient.user.email,
                'blood_group': getattr(patient, 'bloodgroup', 'N/A'),
                'age': getattr(patient, 'age', None),
                'gender': getattr(patient, 'gender', 'N/A'),
                'contact': getattr(patient, 'mobile', 'N/A'),
                'address': getattr(patient, 'location_name', 'N/A'),
                'national_id': getattr(patient, 'national_id', 'N/A'),
                'emergency_contact': getattr(patient, 'emergency_contact', 'N/A'),
            }
        
        return context
    
    def _get_stock_information(self, appointment):
        """Get stock units related to this appointment"""
        context = {}
        
        # For completed donations - show stock added
        if appointment.status == 'completed' and appointment.is_donation:
            if appointment.completed_at_nurse:
                context['related_stock_units'] = StockUnit.objects.filter(
                    center=appointment.donation_center or appointment.nurse.donation_center,
                    added_on__gte=appointment.completed_at_nurse - timedelta(minutes=5),
                    added_on__lte=appointment.completed_at_nurse + timedelta(hours=2)
                ).select_related('center').order_by('-added_on')
        
        # For completed blood requests - show stock deducted
        elif appointment.status == 'completed' and appointment.request_content_type:
            context['stock_transactions'] = StockTransaction.objects.filter(
                appointment=appointment,
                transaction_type='deduction'
            ).select_related('stockunit', 'stockunit__center').order_by('-transaction_at')

        
        return context
    
    def _calculate_time_metrics(self, appointment):
        """Calculate various time-based metrics"""
        context = {}
        
        # Time from creation to completion
        if appointment.created_at and appointment.completed_at_nurse:
            delta = appointment.completed_at_nurse - appointment.created_at
            context['time_to_complete'] = {
                'delta': delta,
                'days': delta.days,
                'hours': delta.seconds // 3600,
                'minutes': (delta.seconds % 3600) // 60,
            }
        
        # Time from approval to completion
        if appointment.approved_at_nurse and appointment.completed_at_nurse:
            delta = appointment.completed_at_nurse - appointment.approved_at_nurse
            context['time_from_approval'] = {
                'delta': delta,
                'days': delta.days,
                'hours': delta.seconds // 3600,
                'minutes': (delta.seconds % 3600) // 60,
            }
        
        # Time until appointment (for pending/approved)
        if appointment.date and appointment.status in ['pending', 'approved']:
            now = timezone.now()
            if appointment.date > now:
                delta = appointment.date - now
                context['time_until_appointment'] = {
                    'delta': delta,
                    'days': delta.days,
                    'hours': delta.seconds // 3600,
                    'minutes': (delta.seconds % 3600) // 60,
                }
            else:
                context['appointment_overdue'] = True
        
        return context
    
    def _build_timeline(self, appointment):
        """Build a chronological timeline of appointment events"""
        timeline = []
        
        if appointment.created_at:
            timeline.append({
                'event': 'Appointment Created',
                'timestamp': appointment.created_at,
                'user': None,
                'icon': 'fa-calendar-plus',
                'color': 'primary'
            })
        
        if appointment.approved_at_nurse:
            timeline.append({
                'event': 'Approved by Nurse',
                'timestamp': appointment.approved_at_nurse,
                'user': appointment.approved_by_nurse,
                'icon': 'fa-check-circle',
                'color': 'success'
            })
        
        if appointment.rejected_at:
            timeline.append({
                'event': 'Rejected',
                'timestamp': appointment.rejected_at,
                'user': appointment.status_changed_by,
                'icon': 'fa-times-circle',
                'color': 'danger'
            })
        
        if appointment.cancelled_at:
            timeline.append({
                'event': f'Cancelled by {appointment.get_cancelled_by_display()}',
                'timestamp': appointment.cancelled_at,
                'user': appointment.cancelled_by_user,
                'icon': 'fa-ban',
                'color': 'warning'
            })
        
        if appointment.completed_at_nurse:
            timeline.append({
                'event': 'Completed by Nurse',
                'timestamp': appointment.completed_at_nurse,
                'user': appointment.completed_by_nurse,
                'icon': 'fa-check-double',
                'color': 'success'
            })
        
        # Sort by timestamp
        timeline.sort(key=lambda x: x['timestamp'])
        
        return timeline
    
#----------------------------------------
# NEXT STOCK UNIT TO BE DEDUCTED
#--------------------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def next_stock_unit(request):
    nurse = get_object_or_404(Nurse, user=request.user)
    center = nurse.donation_center

    blood_group = request.GET.get('blood_group')
    if not blood_group or not center:
        return JsonResponse({'barcode': None})

    # Query for the next stock unit (FIFO - earliest added or earliest expiry)
    next_unit = (
        StockUnit.objects.filter(center=center, bloodgroup=blood_group, expiry_date__gte=timezone.now().date())
        .order_by('added_on')  # FIFO criteria
        .first()
    )

    if next_unit:
        return JsonResponse({'barcode': next_unit.barcode})
    else:
        return JsonResponse({'barcode': None})
    
    
    
    
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def stock_safety_management(request):
    """
    View for nurses to manage stock unit safety verification.
    Shows pending, safe, and unsafe stock units.
    """
    nurse = get_object_or_404(Nurse, user=request.user)
    center = nurse.donation_center
    
    if not center:
        messages.warning(request, "You are not assigned to any donation center.")
        return redirect('nurse-dashboard')
    
    # Get stock summary
    from blood.utils.stock_utils import get_stock_summary, get_pending_verification_stock, get_unsafe_stock
    
    summary = get_stock_summary(center)
    
    # Get pending verification units
    pending_units = get_pending_verification_stock(center).select_related('center')
    
    # Get unsafe/quarantined units
    unsafe_units = get_unsafe_stock(center).select_related('center', 'safety_verified_by')
    
    # Get safe units
    safe_units = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).select_related('center', 'safety_verified_by').order_by('expiry_date')
    
    context = {
        'nurse': nurse,
        'center': center,
        'summary': summary,
        'pending_units': pending_units,
        'safe_units': safe_units,
        'unsafe_units': unsafe_units,
        'pending_count': pending_units.count(),
        'safe_count': safe_units.count(),
        'unsafe_count': unsafe_units.count(),
    }
    
    return render(request, 'nurse/stock_safety_management.html', context)


@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def verify_stock_safety(request, stock_unit_id):
    """
    AJAX endpoint for nurses to verify stock unit safety.
    """
    try:
        nurse = request.user.nurse
        
        with transaction.atomic():
            stock_unit = get_object_or_404(
                StockUnit.objects.select_for_update(),
                id=stock_unit_id,
                center=nurse.donation_center
            )
            
            # Check if already verified
            if stock_unit.safety_status != 'pending':
                return JsonResponse({
                    'success': False,
                    'error': f'This stock unit is already verified as {stock_unit.get_safety_status_display()}'
                }, status=400)
            
            # Get verification data
            safety_status = request.POST.get('safety_status', '').strip().lower()
            unsafe_reason = request.POST.get('unsafe_reason', '').strip()
            safety_notes = request.POST.get('safety_notes', '').strip()
            
            # Validate
            if safety_status not in ['safe', 'unsafe']:
                return JsonResponse({
                    'success': False,
                    'error': 'Safety status must be "safe" or "unsafe"'
                }, status=400)
            
            if safety_status == 'unsafe' and not unsafe_reason:
                return JsonResponse({
                    'success': False,
                    'error': 'Unsafe reason is required'
                }, status=400)
            
            # Apply verification
            if safety_status == 'safe':
                stock_unit.mark_safe(
                    verified_by_user=nurse.user,
                    notes=safety_notes
                )
                message = f"✅ Stock unit {stock_unit.barcode} verified as SAFE and available for use"
                logger.info(f"✅ SAFE: {stock_unit.barcode} verified by {nurse.user.get_full_name()}")
                
            else:  # unsafe
                stock_unit.mark_unsafe(
                    verified_by_user=nurse.user,
                    reason=unsafe_reason,
                    notes=safety_notes
                )
                message = f"⚠️ Stock unit {stock_unit.barcode} marked as UNSAFE and quarantined"
                logger.warning(f"⚠️ UNSAFE: {stock_unit.barcode} ({unsafe_reason}) by {nurse.user.get_full_name()}")
            
            return JsonResponse({
                'success': True,
                'message': message,
                'safety_status': safety_status,
                'barcode': stock_unit.barcode,
                'verified_by': nurse.user.get_full_name(),
                'verified_at': timezone.now().strftime("%b %d, %Y %I:%M %p")
            })
            
    except StockUnit.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Stock unit not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error verifying stock safety: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def stock_unit_detail(request, stock_unit_id):
    """
    Detailed view of a single stock unit including safety verification history.
    """
    nurse = get_object_or_404(Nurse, user=request.user)
    stock_unit = get_object_or_404(
        StockUnit.objects.select_related(
            'center',
            'safety_verified_by'
        ),
        id=stock_unit_id,
        center=nurse.donation_center
    )
    
    # Get related transactions
    transactions = StockTransaction.objects.filter(
        stockunit=stock_unit
    ).select_related(
        'user',
        'appointment',
        'appointment__donor__user',
        'appointment__patient__user'
    ).order_by('-transaction_at')
    
    context = {
        'nurse': nurse,
        'stock_unit': stock_unit,
        'transactions': transactions,
        'can_verify': stock_unit.safety_status == 'pending',
    }
    
    return render(request, 'nurse/stock_unit_detail.html', context)
