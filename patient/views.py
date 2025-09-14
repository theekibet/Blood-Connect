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
from blood import models as bmodels
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
from blood.forms import RequestForm
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
    if request.method == 'POST':
        userForm = forms.PatientUserForm(request.POST)
        patientForm = forms.PatientForm(request.POST, request.FILES)
        if userForm.is_valid() and patientForm.is_valid():
            # Save user
            user = userForm.save(commit=False)
            user.set_password(user.password)
            user.save()
            # Save patient profile
            patient = patientForm.save(commit=False)
            patient.user = user
            patient.save()
            # Add user to PATIENT group
            patient_group, created = Group.objects.get_or_create(name='PATIENT')
            patient_group.user_set.add(user)
            return redirect('patientlogin')
    else:
        userForm = forms.PatientUserForm()
        patientForm = forms.PatientForm()
    return render(request, 'patient/patientsignup.html', {'userForm': userForm, 'patientForm': patientForm})

# -------------------------------
# Dashboard
# -------------------------------
@login_required
def patient_dashboard_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patientlogin")

    # Aggregate blood request stats for this patient
    blood_requests = bmodels.BloodRequest.objects.filter(request_by_patient=patient)
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

    upcoming_appointments = Appointment.objects.filter(
        patient=patient,
        date__gte=timezone.now()
    ).select_related('nurse', 'nurse__donation_center').order_by('date')[:3]

    context = {
        'blood_request_stats': blood_request_stats,
        'centers': centers,
        'patient': patient,
        'upcoming_appointments': upcoming_appointments,
        'now': timezone.now(),
    }
    return render(request, 'patient/patient_dashboard.html', context)

from django.utils import timezone 
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from blood.forms import RequestForm 

from .models import Patient
from nurse.models import Nurse, Appointment
from blood import models as bmodels  
from blood.models import BloodRequest
from blood.utils.geolocation import find_nearby_eligible_donors

# -------------------------------
# Make Blood Request
# -------------------------------
@login_required(login_url='patientlogin')
def make_request_view(request):
    patient = getattr(request.user, "patient", None)
    if not patient:
        return redirect("patient-dashboard")

    centers = DonationCenter.objects.all()
    form_errors = {}
    appointment_datetime_str = ''

    active_request = Appointment.objects.filter(
        patient=patient,
        status__in=['pending', 'approved']
    ).first()

    if active_request:
        messages.warning(
            request,
            "You already have an active blood request appointment. Please complete, reject, or cancel it before making a new request."
        )
        center_data = [
            {"id": c.id, "name": c.name, "latitude": c.latitude, "longitude": c.longitude}
            for c in centers
        ]
        return render(request, 'patient/makerequest.html', {
            'pending_request': active_request,
            'centers': centers,
            'center_data_json': json.dumps(center_data, cls=DjangoJSONEncoder),  # Fixed this line
        })

    if request.method == 'POST':
        request_form = RequestForm(request.POST, request.FILES, user=request.user)

        donation_center_id = request.POST.get('donation_center')
        nurse_id = request.POST.get('nurse')
        appointment_datetime_str = request.POST.get('date')

        center_instance = DonationCenter.objects.filter(id=donation_center_id).first()
        nurse_instance = Nurse.objects.filter(id=nurse_id).first() if nurse_id else None

        request_form_is_valid = request_form.is_valid()

        if request_form_is_valid and appointment_datetime_str and nurse_instance and center_instance:
            try:
                combined_datetime = timezone.make_aware(
                    datetime.fromisoformat(appointment_datetime_str),
                    timezone.get_current_timezone()
                )

                # Save blood request first to get valid ID
                blood_request = request_form.save(commit=False)
                blood_request.request_by_patient = patient
                blood_request.donation_center = center_instance
                blood_request.save()

                content_type = ContentType.objects.get_for_model(blood_request.__class__)
                
                # Create appointment instance with valid FK
                appointment = Appointment(
                    patient=patient,
                    donor=None,
                    nurse=nurse_instance,
                    date=combined_datetime,
                    status='pending',
                    request_content_type=content_type,
                    request_object_id=blood_request.id,
                )

                appointment.full_clean()

                # Check nurse availability conflicts
                appointment_duration = timedelta(minutes=30)
                conflict_exists = Appointment.objects.filter(
                    nurse=nurse_instance,
                    date__lt=combined_datetime + appointment_duration,
                    date__gte=combined_datetime,
                    status__in=['pending', 'approved']
                ).exists()

                if conflict_exists:
                    messages.error(
                        request,
                        f"❌ Nurse {nurse_instance.user.get_full_name()} is already booked during this slot."
                    )
                else:
                    appointment.save()
                    messages.success(request, "✅ Blood request and appointment created successfully.")
                    return redirect('my-request')

            except ValidationError as ve:
                form_errors['appointment'] = ve.messages
            except Exception as e:
                messages.error(request, f"❌ Invalid appointment date/time or other error: {str(e)}")
        else:
            messages.error(
                request,
                "❌ Please correct the errors in the form and make sure all required fields are selected."
            )
            form_errors = {**request_form.errors}

            # Custom errors
            if not nurse_instance:
                form_errors.setdefault('nurse', []).append("Please select a valid nurse.")
            if not appointment_datetime_str:
                form_errors.setdefault('date', []).append("Please select appointment date and time.")
    else:
        request_form = RequestForm(user=request.user)

    center_data = [
        {"id": c.id, "name": c.name, "latitude": c.latitude, "longitude": c.longitude}
        for c in centers
    ]

    return render(request, 'patient/makerequest.html', {
        'request_form': request_form,
        'centers': centers,
        'center_data_json': json.dumps(center_data, cls=DjangoJSONEncoder),  # Fixed this line
        'pending_request': None,
        'form_errors': form_errors,
        'appointment_date': appointment_datetime_str,
        'appointment_time': '',  # legacy, if needed
    })
# -------------------------------
# Requests / Appointments
# -------------------------------
@login_required(login_url='patientlogin')
def my_request_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")

    blood_requests = BloodRequest.objects.filter(request_by_patient=patient)\
                                         .select_related('donation_center')\
                                         .order_by('-created_at')

    content_type = ContentType.objects.get_for_model(BloodRequest)
    appointments = Appointment.objects.filter(
        patient=patient,
        request_content_type=content_type,
        request_object_id__in=blood_requests.values_list('id', flat=True)
    ).select_related('nurse__user')

    appointment_map = {appt.request_object_id: appt for appt in appointments}
    for req in blood_requests:
        req.appointment = appointment_map.get(req.id)

    return render(request, 'patient/my_request.html', {
        'blood_requests': blood_requests,
        'now': timezone.now(),
    })



@login_required(login_url='patientlogin')
def cancel_request_view(request, request_id):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")

    blood_request = get_object_or_404(BloodRequest, id=request_id, request_by_patient=patient)

    appointment = Appointment.objects.filter(
        patient=patient,
        request_content_type=ContentType.objects.get_for_model(BloodRequest),
        request_object_id=blood_request.id
    ).first()

    now = timezone.now()
    if appointment and appointment.date > now:
        if blood_request.status.lower() in ['pending', 'approved']:
            blood_request.status = 'cancelled'
            blood_request.cancelled_by = 'patient'
            blood_request.cancelled_at = now
            blood_request.save()

        if appointment.status.lower() in ['pending', 'approved']:
            appointment.status = 'cancelled'
            appointment.cancelled_by_user = request.user
            appointment.cancelled_at = now
            appointment.status_changed_by = request.user
            appointment.status_changed_at = now
            appointment.save()

        messages.success(request, "Your appointment and request have been cancelled.")
    else:
        messages.warning(request, "This appointment cannot be cancelled (date passed or not found).")

    return redirect('my-request')
# -------------------------------
# Profile
# -------------------------------
@login_required(login_url='patientlogin')
def patient_profile_view(request, patient_id):
    patient = get_object_or_404(models.Patient, id=patient_id)

    if patient.user_id != request.user.id:
        messages.error(request, "Unauthorized access.")
        return redirect('patientlogin')

    return render(request, 'patient/patient_profile.html', {'patient': patient, 'user': request.user})
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

    return render(request, 'patient/patient_notifications.html', {
        'notifications': notifications,
        'patient': patient,
    })




@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, id=pk)
    notification.read = True
    notification.save()
    return redirect('patient-dashboard')

def resources_view(request):
    return render(request, 'patient/resources.html')
def faqs_view(request):
    return render(request, 'patient/faqs.html')
def donation_centers_view(request):
    query = request.GET.get('q')
    centers = DonationCenter.objects.all()
    if query:
        centers = centers.filter(Q(city__icontains=query) | Q(address__icontains=query))
    return render(request, 'patient/donation_centers.html', {'centers': centers})

@login_required(login_url='patientlogin')
def edit_patient_profile_view(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id, user=request.user)

    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('patient-profile', patient_id=patient.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PatientForm(instance=patient)

    return render(request, 'patient/edit_profile.html', {'form': form})
def get_nurses_by_center(request):
    center_id = request.GET.get('center_id')
    if not center_id:
        return JsonResponse({'nurses': []})

    nurses = Nurse.objects.filter(donation_center_id=center_id)

    nurse_data = []
    for nurse in nurses:
        full_name = f"{nurse.user.first_name} {nurse.user.last_name}".strip()
        if not full_name:
            continue  # Skips nurses with empty names

        nurse_data.append({
            'id': nurse.id,
            'name': full_name,
            'specialization': getattr(nurse, 'specialization', 'General Practitioner'),
            'email': getattr(nurse.user, 'email', ''),
            'phone': getattr(nurse, 'phone', ''),
            'bio': getattr(nurse, 'bio', ''),
            'profile_pic_url': nurse.profile_pic.url if getattr(nurse, 'profile_pic', None) else None,
        })

    return JsonResponse({'nurses': nurse_data})

@login_required
def center_stock_ajax(request, center_id):
    try:
        center = DonationCenter.objects.get(id=center_id)
        stock_qs = Stock.objects.filter(center=center).values('bloodgroup', 'unit')
        stock_dict = {item['bloodgroup']: item['unit'] for item in stock_qs}
        return JsonResponse({'center': center.name, 'stock': stock_dict})
    except DonationCenter.DoesNotExist:
        return JsonResponse({'error': 'Center not found'}, status=404)

@login_required(login_url='login')
def nearby_eligible_donors_view(request):
    patient = get_patient_or_redirect(request.user, request)
    if not patient:
        return redirect("patient-dashboard")

    if not patient.latitude or not patient.longitude or not patient.bloodgroup:
        messages.error(request, "Your location and blood group must be set in your profile to find donors.")
        return redirect('patient-edit-profile', patient_id=patient.id)

    donors = find_nearby_eligible_donors(patient.latitude, patient.longitude, patient.bloodgroup)

    return render(request, 'patient/nearby_eligible_donors.html', {
        'nearby_donors': donors,
        'user_blood_type': patient.bloodgroup,
    })
@login_required
def blood_stock_tracker_view(request):
    centers = DonationCenter.objects.all().order_by('name')
    selected_center_id = request.GET.get('center')
    stock_data = None
    selected_center = None

    if selected_center_id:
        try:
            selected_center = DonationCenter.objects.get(id=selected_center_id)
            stock_data = (
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
            stock_data = None

    context = {
        'centers': centers,
        'selected_center': selected_center,
        'stock_data': stock_data,
    }
    return render(request, 'patient/blood_stock_tracker.html', context)
def ajax_validate_username(request):
    username = request.GET.get('username', None)
    data = {
        'is_taken': User.objects.filter(username__iexact=username).exists()
    }
    return JsonResponse(data)