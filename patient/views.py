from django.shortcuts import render, redirect, reverse
from . import forms, models
from django.db.models import Sum, Q
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from datetime import date, timedelta
from django.core.mail import send_mail
from django.contrib.auth.models import User
from blood import forms as bforms
from patient.models import BloodRequest
from django.contrib.auth import authenticate, login
from .forms import PatientLoginForm
from django.shortcuts import get_object_or_404
from django.contrib import messages
from nurse.models import Appointment
from nurse.forms import AppointmentForm
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from .models import Patient
from datetime import datetime
from blood.models import DonationCenter, Stock,StockUnit 
from .forms import PatientForm
from .forms import RequestForm
from django.http import JsonResponse
from nurse.models import Nurse
from django.core.serializers.json import DjangoJSONEncoder
import json
from django.db.models import Count, Q,Min
from django.views.decorators.csrf import csrf_exempt
from django.http import  HttpResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import localdate
from django.core.exceptions import PermissionDenied
from blood.models import Notification
from django.core.exceptions import ValidationError
import logging
from blood.utils.greetings import get_patient_greeting 
from blood.utils.notifications import create_notification
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
logger = logging.getLogger(__name__)

# -------------------------------
# Helper to safely fetch patient
# -------------------------------
# -------------------------------
# Helper to safely fetch patient
# -------------------------------
def get_patient_or_redirect(user, request, redirect_url="patientlogin"):
    """
    Return patient profile if exists, otherwise redirect with error message.
    """
    if not hasattr(user, "patient"):
        messages.error(request, "Patient profile not found. Please complete signup.")
        return None
    return user.patient

# -------------------------------
# Signup
# -------------------------------

def patient_signup_view(request):
    """
    Handles patient registration.
    Users can login immediately after registration.
    """
    if request.method == 'POST':
        userForm = forms.PatientUserForm(request.POST)
        patientForm = forms.PatientForm(request.POST, request.FILES)
        
        if userForm.is_valid() and patientForm.is_valid():
            try:
                # Save user and activate immediately
                user = userForm.save(commit=False)
                user.is_active = True
                user.set_password(userForm.cleaned_data['password'])
                user.save()
                
                # Save patient profile
                patient = patientForm.save(commit=False)
                patient.user = user
                patient.save()
                
                # Add user to PATIENT group
                patient_group, created = Group.objects.get_or_create(name='PATIENT')
                patient_group.user_set.add(user)
                
                # Log the registration
                logger.info(f"New patient registration: {user.username} - Account active")
                
                # Success message
                messages.success(
                    request, 
                    f"🎉 Registration successful, {user.first_name}! "
                    f"Your account has been created. You can now login."
                )
                
                # Redirect to login page
                return redirect('patientlogin')
                
            except Exception as e:
                # Log the error
                logger.error(f"Patient registration failed: {str(e)}", exc_info=True)
                
                # Clean up: delete the user if patient creation fails
                if 'user' in locals():
                    user.delete()
                
                messages.error(
                    request,
                    "⚠️ Registration failed due to a system error. "
                    "Please try again or contact support if the issue persists."
                )
                
                return render(request, 'patient/patientsignup.html', {
                    'userForm': userForm,
                    'patientForm': patientForm
                })
        else:
            # Forms have validation errors
            messages.error(
                request,
                "⚠️ Please correct the errors below."
            )
    else:
        userForm = forms.PatientUserForm()
        patientForm = forms.PatientForm()
    
    return render(request, 'patient/patientsignup.html', {
        'userForm': userForm, 
        'patientForm': patientForm
    })
# -------------------------------
# Dashboard
# -------------------------------
@login_required
def patient_dashboard_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patientlogin")

    # --- Generate personalized greeting ---
    # Get the greeting function from utils or define it inline
    try:
        from blood.utils.greetings import get_patient_greeting
        upcoming_appointments_for_greeting = Appointment.objects.filter(
            patient=patient,
            date__gte=timezone.now()
        ).order_by('date')[:3]
        
        greeting_data = get_patient_greeting(
            patient=patient,
            upcoming_appointments=upcoming_appointments_for_greeting
        )
    except ImportError:
        # Fallback greeting if utils not available
        greeting_data = {
            'greeting': f"Welcome back, {patient.user.first_name or 'there'}! 👋",
            'context_message': "Managing your health and blood needs.",
            'user_type': 'patient',
            'icon': '👤',
            'profile_pic': patient.profile_pic if hasattr(patient, 'profile_pic') else None
        }

    # Aggregate blood request stats for this patient
    blood_requests = BloodRequest.objects.filter(request_by_patient=patient)

    status_counts = blood_requests.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='Pending')),
        approved=Count('id', filter=Q(status='Approved')),
        rejected=Count('id', filter=Q(status='Rejected'))
    )

    blood_request_stats = [
        {'label': 'Requests Made', 'icon_class': 'fas fa-paper-plane', 'count': status_counts.get('total', 0)},
        {'label': 'Pending Requests', 'icon_class': 'fas fa-clock', 'count': status_counts.get('pending', 0)},
        {'label': 'Approved Requests', 'icon_class': 'fas fa-check-circle', 'count': status_counts.get('approved', 0)},
        {'label': 'Rejected Requests', 'icon_class': 'fas fa-times-circle', 'count': status_counts.get('rejected', 0)},
    ]

    centers = bmodels.DonationCenter.objects.all()

    # Upcoming appointments for display
    upcoming_appointments = Appointment.objects.filter(
        patient=patient,
        date__gte=timezone.now()
    ).select_related('nurse', 'nurse__donation_center').order_by('date')[:5]

    # Get recent appointments (last 3 completed)
    recent_appointments = Appointment.objects.filter(
        patient=patient,
        status='completed'
    ).order_by('-date')[:3]

    # Calculate days since last appointment
    days_since_last = None
    if recent_appointments.exists():
        last_appointment = recent_appointments.first()
        days_since_last = (timezone.now().date() - last_appointment.date.date()).days

    # Get blood groups in stock for nearby centers (FIXED: using bloodgroup not blood_group)
    available_blood_groups = []
    if hasattr(patient, 'bloodgroup') and patient.bloodgroup:
        # Get centers with patient's blood group in stock - FIXED DISTINCT ISSUE
        from blood.models import StockUnit
        
        # Option 1: Remove distinct and use Python to get unique centers
        available_stock = StockUnit.objects.filter(
            bloodgroup=patient.bloodgroup,
            unit__gte=100,  # At least 100ml available
            expiry_date__gt=timezone.now().date() + timedelta(days=7)  # Not expiring soon
        ).select_related('center').order_by('center__id', '-unit')[:10]  # Get more records
        
        # Use Python to get unique centers
        seen_centers = set()
        unique_stock = []
        for stock in available_stock:
            if stock.center.id not in seen_centers:
                seen_centers.add(stock.center.id)
                unique_stock.append(stock)
                if len(unique_stock) >= 3:  # We only want 3 centers
                    break
        
        available_blood_groups = [
            {
                'center': stock.center.name,
                'units': stock.unit,
                'expiry': stock.expiry_date,
                'center_id': stock.center.id
            }
            for stock in unique_stock[:3]
        ]

    # Prepare metadata for greeting card
    meta_items = []
    if hasattr(patient, 'bloodgroup') and patient.bloodgroup:
        meta_items.append({
            'icon': 'fas fa-tint',
            'text': f"Blood Group: {patient.bloodgroup}"
        })
    
    if hasattr(patient, 'phone') and patient.phone:
        meta_items.append({
            'icon': 'fas fa-phone',
            'text': patient.phone
        })
    
    # Add metadata to greeting data if not already present
    if 'meta_items' not in greeting_data and meta_items:
        greeting_data['meta_items'] = meta_items

    context = {
        'blood_request_stats': blood_request_stats,
        'centers': centers,
        'patient': patient,
        'upcoming_appointments': upcoming_appointments,
        'recent_appointments': recent_appointments,
        'days_since_last': days_since_last,
        'available_blood_groups': available_blood_groups,
        'now': timezone.now(),
        'greeting_data': greeting_data,  # Add greeting data
        'current_date': timezone.now().date(),  # For the shared greeting template
        # Additional context for template
        'has_emergency_contact': bool(patient.emergency_contact) if hasattr(patient, 'emergency_contact') else False,
        'is_regular_donor': recent_appointments.count() >= 3 if recent_appointments else False,
    }
    
    return render(request, 'patient/patient_dashboard.html', context)

from django.utils import timezone 
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from patient.forms import RequestForm 

from .models import Patient
from nurse.models import Nurse, Appointment
from blood import models as bmodels  

from blood.utils.geolocation import find_nearby_eligible_donors

# -------------------------------
# Make Blood Request
# -------------------------------
@login_required(login_url='patientlogin')
def patient_make_request_view(request):
    patient = getattr(request.user, "patient", None)
    if not patient:
        return redirect("patient-dashboard")

    centers = DonationCenter.objects.all()
    form_errors = {}

    if request.method == 'POST':
        request_form = RequestForm(request.POST, request.FILES, user=request.user)

        # Attach patient to the request
        request_form.instance.request_by_patient = patient

        # Get donation center
        donation_center_id = request.POST.get('donation_center')
        center_instance = DonationCenter.objects.filter(id=donation_center_id).first()

        if request_form.is_valid() and center_instance:
            try:
                # Save blood request directly
                blood_request = request_form.save(commit=False)
                blood_request.donation_center = center_instance
                blood_request.status = 'pending'
                blood_request.is_seen = False          # <-- ADD THIS
                blood_request.stock_deducted = False   # <-- ADD THIS
                blood_request.save()

                messages.success(
                    request, 
                    "✅ Blood request submitted successfully! The blood bank will review it shortly."
                )
                return redirect('patient-requests-history')

            except Exception as e:
                messages.error(request, f"❌ Error creating request: {str(e)}")
                logger.error(f"Error in patient_make_request_view: {e}", exc_info=True)
        else:
            messages.error(request, "❌ Please correct the errors in the form.")
            form_errors = request_form.errors

    else:
        request_form = RequestForm(user=request.user)

    # Check for any existing pending requests
    pending_request = BloodRequest.objects.filter(
        request_by_patient=patient,
        status='pending'
    ).first()

    center_data = [
        {"id": c.id, "name": c.name, "latitude": c.latitude, "longitude": c.longitude}
        for c in centers
    ]

    context = {
        'request_form': request_form,
        'centers': centers,
        'center_data_json': json.dumps(center_data, cls=DjangoJSONEncoder),
        'pending_request': pending_request,
        'form_errors': form_errors,
        'no_appointment': True,
    }
    
    return render(request, 'patient/makerequest.html', context)
# -------------------------------
# Requests History
# -------------------------------
@login_required(login_url='patientlogin')
def patient_requests_history_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")
    
    # Get all blood requests for this patient
    blood_requests = BloodRequest.objects.filter(
        request_by_patient=patient
    ).select_related(
        'donation_center',
        'approved_by__user',
        'reviewed_by__user',
        'dispatched_by__user'
    ).order_by('-created_at')
    
    return render(request, 'patient/patient_request_history.html', {
        'blood_requests': blood_requests,
        'now': timezone.now(),
    })
# -------------------------------
# Cancel Requests
# -------------------------------
# -------------------------------
# Cancel Requests (Updated for Blood Bank Tech Workflow)
# -------------------------------
@login_required(login_url='patientlogin')
def cancel_request_view(request, request_id):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")

    blood_request = get_object_or_404(
        BloodRequest,
        id=request_id,
        request_by_patient=patient
    )

    now = timezone.now()

    # Only allow cancellation of pending requests
    if blood_request.status == 'pending':
        # Update request status
        blood_request.status = 'cancelled'
        blood_request.cancelled_by = 'patient'
        blood_request.cancelled_at = now
        blood_request.save(update_fields=['status', 'cancelled_by', 'cancelled_at'])

        # Get cancellation reason from POST if provided
        reason = request.POST.get('reason', '').strip()
        if reason:
            blood_request.cancellation_reason = reason
            blood_request.save(update_fields=['cancellation_reason'])

        # 🔔 SEND NOTIFICATION TO BLOOD BANK TECHNICIANS
        from blood_bank_technician.models import BloodBankTechProfile
        
        # Notify all blood bank techs at this center
        blood_bank_techs = BloodBankTechProfile.objects.filter(
            center=blood_request.donation_center,
            is_active=True
        )
        
        for tech in blood_bank_techs:
            create_notification(
                title="🚫 Blood Request Cancelled",
                message=(
                    f"Patient {patient.user.get_full_name()} has cancelled their blood request.\n"
                    f"Blood Group: {blood_request.bloodgroup}\n"
                    f"Units: {blood_request.unit}ml\n"
                    f"Reason: {reason if reason else 'No reason provided'}"
                ),
                recipient_obj=tech,
                sender_obj=patient,
                action="request_cancelled",
                bloodgroup=blood_request.bloodgroup,
                unit=blood_request.unit
            )

        # Also send confirmation to patient
        create_notification(
            title="Request Cancelled",
            message=(
                f"Your blood request for {blood_request.unit}ml of {blood_request.bloodgroup} "
                f"has been cancelled successfully."
            ),
            recipient_obj=patient,
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

    return redirect('patient-requests-history')

# -------------------------------
# Patient  Profile
# -------------------------------
@login_required(login_url='patientlogin')
def patient_profile_view(request, patient_id):
    patient = get_object_or_404(models.Patient, id=patient_id)

    if patient.user_id != request.user.id:
        messages.error(request, "Unauthorized access.")
        return redirect('patientlogin')

    # Add verification context
    context = {
        'patient': patient, 
        'user': request.user,
        'bloodgroup_verified': patient.bloodgroup_verified,
        'verified_bloodgroup': patient.bloodgroup if patient.bloodgroup_verified else None,
    }
    
    return render(request, 'patient/patient_profile.html', context)

# -------------------------------
# Patient Edit Profile
# -------------------------------
@login_required(login_url='patientlogin')
def edit_patient_profile_view(request, patient_id):
    """
    Edit patient profile with blood group verification protection
    """
    patient = get_object_or_404(Patient, id=patient_id, user=request.user)
    
    # Store original verified values for integrity check
    original_bloodgroup = patient.bloodgroup if patient.bloodgroup_verified else None
    original_bloodgroup_verified = patient.bloodgroup_verified
    original_bloodgroup_verified_by = patient.bloodgroup_verified_by
    original_bloodgroup_verified_at = patient.bloodgroup_verified_at

    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES, instance=patient)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save form
                    patient_instance = form.save(commit=False)
                    
                    # ==========================================
                    # CRITICAL: PROTECT VERIFIED BLOOD GROUP
                    # ==========================================
                    if original_bloodgroup_verified:
                        # Restore original verified blood group data
                        patient_instance.bloodgroup = original_bloodgroup
                        patient_instance.bloodgroup_verified = True
                        patient_instance.bloodgroup_verified_by = original_bloodgroup_verified_by
                        patient_instance.bloodgroup_verified_at = original_bloodgroup_verified_at
                        
                        logger.info(
                            f"✅ Protected verified blood group {original_bloodgroup} "
                            f"for patient {patient.id} during profile edit"
                        )
                    
                    patient_instance.save()
                    
                    messages.success(request, "✅ Profile updated successfully!")
                    return redirect('patient-profile', patient_id=patient.id)
                    
            except Exception as e:
                logger.error(f"Error saving patient profile {patient.id}: {e}", exc_info=True)
                messages.error(request, f"❌ An error occurred while saving: {str(e)}")
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = PatientForm(instance=patient)

    context = {
        'form': form,
        'patient': patient,
        'bloodgroup_verified': patient.bloodgroup_verified,
        'verified_bloodgroup': patient.bloodgroup if patient.bloodgroup_verified else None,
    }
    
    return render(request, 'patient/edit_profile.html', context)

# -------------------------------
# Notifications
# -------------------------------
@login_required(login_url='patientlogin')
def patient_notifications_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")

    patient_ct = ContentType.objects.get_for_model(Patient)

    notifications = Notification.objects.filter(
        recipient_content_type=patient_ct,
        recipient_object_id=patient.id
    ).order_by('-created_at')

    unread_count = notifications.filter(read=False).count()

    return render(request, 'patient/patient_notifications.html', {
        'notifications': notifications,
        'patient': patient,
        'unread_count': unread_count,
    })

# -------------------------------
# Mark Notifications Read
# -------------------------------
@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, id=pk)
    notification.read = True
    notification.save()
    return redirect('patient-notifications')

# -------------------------------
# Resources
# -------------------------------
def resources_view(request):
    return render(request, 'patient/resources.html')

# -------------------------------
# FAQs
# -------------------------------
def faqs_view(request):
    return render(request, 'patient/faqs.html')

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
# -------------------------------
# Center stock ajax
# -------------------------------
@login_required
def center_stock_ajax(request, center_id):
    try:
        center = DonationCenter.objects.get(id=center_id)
        stock_qs = Stock.objects.filter(center=center).values('bloodgroup', 'unit')
        stock_dict = {item['bloodgroup']: item['unit'] for item in stock_qs}
        return JsonResponse({'center': center.name, 'stock': stock_dict})
    except DonationCenter.DoesNotExist:
        return JsonResponse({'error': 'Center not found'}, status=404)
    
    


# -------------------------------
# Ajax Validate
# -------------------------------
def ajax_validate_username(request):
    username = request.GET.get('username', None)
    data = {
        'is_taken': User.objects.filter(username__iexact=username).exists()
    }
    return JsonResponse(data)

