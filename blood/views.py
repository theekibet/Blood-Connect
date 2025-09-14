from django.shortcuts import render, redirect, reverse
from . import forms, models
from django.db.models import Sum, Q
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required, user_passes_test,permission_required
from django.conf import settings
from datetime import date, timedelta
from django.core.mail import send_mail
from django.contrib.auth.models import User
from donor import models as dmodels
from patient import models as pmodels
from donor import forms as dforms
from patient import forms as pforms
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from .forms import ContactForm
from .models import ContactMessage, Contact  
from django.contrib import messages
from django.contrib.auth import authenticate, login
from patient.models import Patient
from donor.models import DonorEligibility
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from .models import Stock, BloodRequest
from donor.models import DonorEligibility, BloodDonate
from django.db.models import Max
from donor.models import Donor 
from .models import Notification
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from patient.models import Patient
from django.core.paginator import Paginator
from patient import models 
from blood import models
from blood import models as bmodels
from nurse.models import Nurse
from nurse import forms as nurse_forms
from .models import DonationCenter, StockUnit
from .forms import BloodForm
from .forms import StockUnitForm
import json
from django.utils.timezone import now
from collections import defaultdict
from django.http import JsonResponse
from nurse.models import NurseBloodRequest,NurseBloodRequestStockUnit
from django.views.decorators.http import require_http_methods
from .forms import DonationCenterForm
from django.core.exceptions import PermissionDenied,ValidationError
from blood.utils.stock_utils import add_stock
from blood.utils.stock_utils import deduct_stock_fifo
from django.utils import timezone
from django.db import transaction
from blood.utils.geolocation import find_nearby_centers
from django.views.decorators.csrf import csrf_exempt
from nurse.models import Appointment
import logging
from donor.models import BLOODGROUP_CHOICES
from django.db.models import F
from blood.models import StockTransaction
import csv
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from blood.models import DonorBloodRequest
from django.db.models import Prefetch
import requests
def home_view(request):
    # Ensure at least one donation center exists
    center = models.DonationCenter.objects.first()
    if not center:
        center = models.DonationCenter.objects.create(
            name="Main Donation Center",
            address="123 Main Street",
            city="Default City",
            contact_number="000-000-0000",
            open_hours="9:00 AM - 5:00 PM"
        )

    # Ensure stock records exist for this center
    if not models.Stock.objects.filter(center=center).exists():
        blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        for group in blood_groups:
            models.Stock.objects.create(
                bloodgroup=group,
                center=center,
                unit=0
            )

    if request.user.is_authenticated:
        return redirect('afterlogin')

    # Pass user authentication status to the template context
    context = {
        'user_is_authenticated': request.user.is_authenticated,
    }
    return render(request, 'blood/index.html', context)
def is_donor(user):
    return user.groups.filter(name='DONOR').exists()

def is_patient(user):
    return user.groups.filter(name='PATIENT').exists()

def is_nurse(user):
    return user.groups.filter(name='NURSE').exists()

@login_required
def afterlogin_view(request):
    user = request.user

    if hasattr(user, 'patient'):
        return redirect('patient-dashboard')
    elif hasattr(user, 'nurse'):
        return redirect('nurse-dashboard')
    elif hasattr(user, 'donor'):
        return redirect('donor-dashboard')
    else:
        return redirect('admin-dashboard')

@login_required(login_url='adminlogin')
@user_passes_test(lambda u: u.is_staff, login_url='adminlogin')
def admin_dashboard_view(request):
    # Aggregate total units by blood group and center
    all_stocks = models.Stock.objects.select_related('center').values(
        'bloodgroup', 'center__name'
    ).annotate(total_units=Sum('unit'))

    # Organize stocks by center and blood group
    center_stock_map = defaultdict(lambda: defaultdict(int))
    blood_group_totals = defaultdict(int)

    for entry in all_stocks:
        center = entry['center__name']
        bg = entry['bloodgroup']
        units = entry['total_units'] or 0
        center_stock_map[center][bg] = units
        blood_group_totals[bg] += units

    # Deep convert nested defaultdicts to normal dicts
    center_stock_map_norm = {center: dict(bloodgroups) for center, bloodgroups in center_stock_map.items()}

    # Fixed list of blood groups for ordering & display
    blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

    # Calculate max units safely to avoid division by zero
    max_unit = max(blood_group_totals.values()) if blood_group_totals else 1
    if max_unit == 0:
        max_unit = 1

    # Prepare blood_data for cards & chart
    blood_data = []
    totalbloodunit = 0
    for bg in blood_groups:
        total_stock = blood_group_totals.get(bg, 0)
        percentage = min((total_stock / max_unit) * 100, 100)
        blood_data.append({
            "blood_group": bg,
            "total_stock": total_stock,
            "percentage": round(percentage, 2),
        })
        totalbloodunit += total_stock

    # Prepare low stock alerts per center and blood group
    LOW_STOCK_THRESHOLD_PERCENT = 25  # Customize alert threshold
    low_stock_alerts = []
    for center, stocks in center_stock_map_norm.items():
        for bg in blood_groups:
            units = stocks.get(bg, 0)
            percentage = (units / max_unit) * 100 if max_unit else 0
            if percentage < LOW_STOCK_THRESHOLD_PERCENT:
                low_stock_alerts.append({
                    'center': center,
                    'blood_group': bg,
                    'units': units,
                    'percentage': round(percentage, 2),
                })

    # Stats for cards: Adjust icons and colors as you like
    stats = [
        {"label": "Total Donors", "value": dmodels.Donor.objects.count(), "icon": "fas fa-user-plus", "color": "#007bff"},
        {"label": "Total Patients", "value": pmodels.Patient.objects.count(), "icon": "fas fa-procedures", "color": "#28a745"},
        {"label": "Total Requests", "value": models.BloodRequest.objects.count(), "icon": "fas fa-clipboard-list", "color": "#ffc107"},
        {"label": "Approved Requests", "value": models.BloodRequest.objects.filter(status="Approved").count(), "icon": "fas fa-check-circle", "color": "#17a2b8"},
    ]

    context = {
        "center_stock_map": center_stock_map_norm,
        "blood_data": blood_data,
        "totalbloodunit": totalbloodunit,
        "low_stock_alerts": low_stock_alerts,
        "stats": stats,
        "now": now(),
    }

    return render(request, "blood/admin_dashboard.html", context)
def add_stock(center, bloodgroup, units, expiry_date):
    if units <= 0:
        raise ValidationError("Units must be positive.")
    if expiry_date < timezone.now().date():
        raise ValidationError("Expiry date cannot be in the past.")

    stock_unit = StockUnit(
        center=center,
        bloodgroup=bloodgroup,
        unit=units,
        expiry_date=expiry_date,
    )
    stock_unit.save()


@login_required(login_url='adminlogin')
def admin_blood_view(request):
    centers = DonationCenter.objects.all()
    blood_groups = [bg for bg, _ in StockUnit.BLOOD_GROUP_CHOICES]

    stockForm = StockUnitForm()
    donation_center_form = DonationCenterForm()

    if request.method == 'POST':
        try:
            with transaction.atomic():
                if 'submit_stockunit' in request.POST:
                    # Stock unit form is always allowed
                    stockForm = StockUnitForm(request.POST)
                    donation_center_form = DonationCenterForm()
                    if stockForm.is_valid():
                        cd = stockForm.cleaned_data
                        add_stock(
                            center=cd['center'],
                            bloodgroup=cd['bloodgroup'],
                            units=cd['unit'],
                            expiry_date=cd['expiry_date']
                        )
                        messages.success(request, "Blood stock unit added successfully.")
                        return redirect('admin-blood')
                    else:
                        messages.error(request, "Please correct the errors below.")

                elif 'submit_donation_center' in request.POST:
                    # Permission check ONLY here
                    if not request.user.has_perm('blood.add_donationcenter'):
                        raise PermissionDenied("You do not have permission to add a donation center.")

                    donation_center_form = DonationCenterForm(request.POST)
                    stockForm = StockUnitForm()
                    if donation_center_form.is_valid():
                        donation_center_form.save()
                        messages.success(request, "Donation center added successfully.")
                        return redirect('admin-blood')
                    else:
                        messages.error(request, "Please correct the errors in Donation Center form.")
        except Exception as e:
            messages.error(request, f"Error adding data: {e}")
    else:
        stockForm = StockUnitForm()
        donation_center_form = DonationCenterForm()

    # Aggregate stock for tables and chart
    aggregated_stock = StockUnit.objects.values(
        'center__id', 'center__name', 'bloodgroup'
    ).annotate(total_units=Sum('unit'))

    center_stock_map = {}
    for entry in aggregated_stock:
        center_id = entry['center__id']
        center_name = entry['center__name']
        bloodgroup = entry['bloodgroup']
        total_units = entry['total_units']
        if center_id not in center_stock_map:
            center_stock_map[center_id] = {'name': center_name, 'stock': {}}
        center_stock_map[center_id]['stock'][bloodgroup] = total_units

    chart_data = [{
        'center': data['name'],
        'center_id': center_id,
        'stock': data['stock']
    } for center_id, data in center_stock_map.items()]

    selected_center_id = request.GET.get('center_id', 'all')
    selected_bloodgroup = request.GET.get('bloodgroup', 'all')

    stock_units = StockUnit.objects.all().select_related('center')
    if selected_center_id != 'all':
        stock_units = stock_units.filter(center__id=selected_center_id)
    if selected_bloodgroup != 'all':
        stock_units = stock_units.filter(bloodgroup=selected_bloodgroup)

    selected_center = None
    if selected_center_id != 'all':
        try:
            selected_center = DonationCenter.objects.get(id=int(selected_center_id))
        except DonationCenter.DoesNotExist:
            selected_center = None

    context = {
        'stockForm': stockForm,
        'donation_center_form': donation_center_form,
        'centers': centers,
        'blood_groups': blood_groups,
        'center_stock_map': center_stock_map,
        'chart_data_json': json.dumps(chart_data),
        'stock_units': stock_units,
        'selected_center': selected_center,
        'selected_center_id': selected_center_id,
        'selected_bloodgroup': selected_bloodgroup,
    }
    return render(request, 'blood/admin_blood.html', context)
@login_required(login_url='adminlogin')
def admin_donor_view(request):
    query = request.GET.get('q', '').strip()

    donors = Donor.objects.all()
    eligibilities = DonorEligibility.objects.all()

    if query:
        donors = donors.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(bloodgroup__icontains=query) |
            Q(user__email__icontains=query) |
            Q(national_id__icontains=query)
        )
        eligibilities = eligibilities.filter(donor__in=donors)

    return render(request, 'blood/admin_donor.html', {
        'donors': donors,
        'eligibilities': eligibilities,
        'request': request,  # Pass to access GET params in template for search field value
    })
@login_required(login_url='adminlogin')
def update_donor_view(request, pk):
    try:
        donor = dmodels.Donor.objects.get(id=pk)
        user = dmodels.User.objects.get(id=donor.user_id)
    except dmodels.Donor.DoesNotExist:
        raise Http404("Donor not found")
    except dmodels.User.DoesNotExist:
        raise Http404("User not found")

    userForm = dforms.DonorUserForm(instance=user)
    donorForm = dforms.DonorForm(request.FILES, instance=donor)

    mydict = {'userForm': userForm, 'donorForm': donorForm}

    if request.method == 'POST':
        userForm = dforms.DonorUserForm(request.POST, instance=user)
        donorForm = dforms.DonorForm(request.POST, request.FILES, instance=donor)
        if userForm.is_valid() and donorForm.is_valid():
            user = userForm.save()
            user.set_password(user.password)
            user.save()
            donor = donorForm.save(commit=False)
            donor.user = user
            donor.bloodgroup = donorForm.cleaned_data['bloodgroup']
            donor.save()
            return redirect('admin-donor')

    return render(request, 'blood/update_donor.html', context=mydict)

@login_required(login_url='adminlogin')
def delete_donor_view(request, pk):
    try:
       
        donor = Donor.objects.get(id=pk)
    except Donor.DoesNotExist:
        raise Http404("Donor not found")  # Raise 404 if donor doesn't exist

    try:
        # Try to fetch the User object associated with the donor
        user = User.objects.get(id=donor.user_id)
        user.delete()  # Delete the User if found
    except User.DoesNotExist:
        pass 

   
    donor.delete()

  
    messages.success(request, "Donor and associated user (if any) deleted successfully.")
    return redirect('admin-donor')

@login_required(login_url='adminlogin')
def admin_patient_view(request):
    # Annotate each patient with the datetime of their last blood request and last appointment
    patients = pmodels.Patient.objects.all().annotate(
        last_request=Max('blood_requests__created_at'),       
        last_appointment=Max('appointments__date'),           
    )

    # Determine if patient is critical based on blood group or recent blood request (last 7 days)
    for patient in patients:
        is_rare_group = hasattr(patient, 'bloodgroup') and patient.bloodgroup in ['AB-', 'B-']
        recently_requested = patient.last_request and (now().date() - patient.last_request.date()).days < 7
        patient.is_critical = is_rare_group or recently_requested

    context = {
        'patients': patients,
        'message': request.GET.get('message', None),  # Optional message from redirect/query params
    }

    return render(request, 'blood/admin_patient.html', context)
@login_required(login_url='adminlogin')
def update_patient_view(request, pk):
    try:
        patient = pmodels.Patient.objects.get(id=pk)
    except pmodels.Patient.DoesNotExist:
        raise Http404("Patient does not exist")

    try:
        user = pmodels.User.objects.get(id=patient.user_id)
    except pmodels.User.DoesNotExist:
        raise Http404("User associated with this patient does not exist")

    userForm = pforms.PatientUserForm(instance=user)
    patientForm = pforms.PatientForm(request.FILES, instance=patient)
    mydict = {'userForm': userForm, 'patientForm': patientForm}

    if request.method == 'POST':
        userForm = pforms.PatientUserForm(request.POST, instance=user)
        patientForm = pforms.PatientForm(request.POST, request.FILES, instance=patient)
        if userForm.is_valid() and patientForm.is_valid():
            user = userForm.save()
            user.set_password(user.password)
            user.save()
            patient = patientForm.save(commit=False)
            patient.user = user
            patient.bloodgroup = patientForm.cleaned_data['bloodgroup']
            patient.save()
            return redirect('admin-patient')
    return render(request, 'blood/update_patient.html', context=mydict)


@login_required(login_url='adminlogin')
def delete_patient_view(request, pk):
    patient = get_object_or_404(pmodels.Patient, id=pk)

   
    try:
        user = User.objects.get(id=patient.user_id)
        user.delete()
    except User.DoesNotExist:
       
        pass

    
    patient.delete()

    return HttpResponseRedirect('/admin-patient')

@login_required(login_url='adminlogin')
def admin_request_view(request):
    # Get content types for both request models
    blood_request_ct = ContentType.objects.get_for_model(BloodRequest)
    donor_blood_request_ct = ContentType.objects.get_for_model(DonorBloodRequest)

    # Query appointments linked to either blood request type
    appointments = Appointment.objects.filter(
        request_content_type__in=[blood_request_ct, donor_blood_request_ct]
    ).select_related(
        'donor__user',
        'patient__user',
        'request_content_type'
    ).order_by('-date')

    # Mark unseen pending requests (both types) as seen
    BloodRequest.objects.filter(status='pending', is_seen=False).update(is_seen=True)
    DonorBloodRequest.objects.filter(status='pending', is_seen=False).update(is_seen=True)

    # Count unseen pending requests (both types)
    new_requests_count = (
        BloodRequest.objects.filter(status='pending', is_seen=False).count() +
        DonorBloodRequest.objects.filter(status='pending', is_seen=False).count()
    )

    context = {
        'appointments': appointments,
        'new_requests_count': new_requests_count,
    }
    return render(request, 'blood/admin_request.html', context)
logger = logging.getLogger(__name__)


@login_required(login_url='adminlogin')
@user_passes_test(lambda u: u.is_staff, login_url='adminlogin')
def admin_donation_view(request):
    """
    Admin dashboard view for all blood donations with linked appointments.
    Efficiently loads related data using select_related and prefetch_related.
    Marks unseen donations as seen.
    """
    # Mark all unseen donations as seen
    BloodDonate.objects.filter(is_seen=False).update(is_seen=True)

    # Prefetch related appointments with their nurse and user data
    donations = (
        BloodDonate.objects
        .select_related('donor__user', 'donation_center')
        .prefetch_related(
            Prefetch(
                'appointments',
                queryset=Appointment.objects.select_related('nurse', 'nurse__user'),
                to_attr='prefetched_appointments'  # Access via donation.prefetched_appointments
            )
        )
        .order_by('-date')  # recent first, optional
    )

    # Get blood group choices from model field
    blood_group_choices = BloodDonate._meta.get_field('bloodgroup').choices

    context = {
        'donations': donations,
        'blood_group_choices': blood_group_choices,
    }
    return render(request, 'blood/admin_donation.html', context)
from blood.models import (
    Appointment,
    BloodRequest,
    DonorBloodRequest,
    Stock,
    StockUnit,
    StockTransaction,
)
from blood.utils.stock_utils import deduct_stock_fifo

logger = logging.getLogger(__name__)
def serialize_deductions(deductions):
    """
    Convert stock deduction objects into JSON-serializable format.
    """
    serialized = []
    for d in deductions:
        serialized.append({
            'barcode': d['barcode'],
            'quantity': d['quantity'],
            'expiry_date': d['expiry_date'].isoformat() if d['expiry_date'] else None,
        })
    return serialized



def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('contact_success')  # Redirect to contact_success
    else:
        form = ContactForm()
    return render(request, 'blood/contact_us.html', {'form': form})

def contact_success(request):
    return render(request, 'blood/contact_success.html')



def learn_more_view(request):
    return render(request, 'blood/learn_more.html')

def about_us_view(request):
    return render(request, 'blood/about_us.html')



@login_required(login_url='adminlogin')
def admin_contacts_view(request):
    
    Contact.objects.filter(is_read=False).update(is_read=True)

    
    contact_list = Contact.objects.all().order_by('-created_at')

    
    paginator = Paginator(contact_list, 10)  
    page_number = request.GET.get('page')
    contacts = paginator.get_page(page_number)

    return render(request, 'blood/admin_contacts.html', {'contacts': contacts})

def admin_post_notification(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        message_text = request.POST.get('message')
        recipient_id = request.POST.get('recipient_id')
        recipient_type = request.POST.get('recipient_type')  

        # Validate and fetch recipient
        try:
            if recipient_type == 'patient':
                recipient = Patient.objects.get(user__id=recipient_id)
                recipient_content_type = ContentType.objects.get_for_model(Patient)
            elif recipient_type == 'donor':
                recipient = Donor.objects.get(user__id=recipient_id)
                recipient_content_type = ContentType.objects.get_for_model(Donor)
            elif recipient_type == 'doctor':
                recipient = Nurse.objects.get(user__id=recipient_id)
                recipient_content_type = ContentType.objects.get_for_model(Nurse)
            else:
                messages.error(request, "Invalid recipient type.")
                return redirect('admin-post-notification')

            # Create the notification
            Notification.objects.create(
                title=title,
                message=message_text,
                recipient_content_type=recipient_content_type,
                recipient_object_id=recipient.id
            )

            messages.success(request, "Notification posted successfully!")

        except (Patient.DoesNotExist, Donor.DoesNotExist):
            messages.error(request, "Recipient not found.")

        return redirect('admin-post-notification')  # Redirect back to form with message

    # Load recipients
    patients = Patient.objects.select_related('user').all()
    donors = Donor.objects.select_related('user').all()
    nurses = Nurse.objects.select_related('user').all()

    context = {
        'patients': patients,
        'donors': donors,
        'nurses': nurses,
    }
    return render(request, 'blood/admin_post_notification.html', context)
@login_required(login_url='adminlogin')
def admin_nurse_view(request):
    nurses = Nurse.objects.all()  # Query all nurses
    return render(request, 'blood/admin_nurse.html', {'nurses': nurses})
@login_required(login_url='adminlogin')
def update_nurse_view(request, pk):
    # Fetch the nurse instance and related user
    nurse = get_object_or_404(Nurse, id=pk)
    user = nurse.user

    if request.method == 'POST':
        # Bind POST data to forms
        user_form = nurse_forms.NurseUserForm(request.POST, instance=user)
        nurse_form = nurse_forms.NurseForm(request.POST, request.FILES, instance=nurse)

        # Handle profile picture removal if admin checked it
        if 'clear_profile_pic' in request.POST and nurse.profile_pic:
            nurse.profile_pic.delete(save=False)
            nurse.profile_pic = None

        # Validate both forms
        if user_form.is_valid() and nurse_form.is_valid():
            user_form.save()
            nurse_form.save()
            messages.success(request, "Nurse profile updated successfully.")
            return redirect('admin-nurse')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        # Prefill forms with current data
        user_form = nurse_forms.NurseUserForm(instance=user)
        nurse_form = nurse_forms.NurseForm(instance=nurse)

    context = {
        'userForm': user_form,   # match these variable names to template
        'nurseForm': nurse_form,
        'nurse': nurse,
    }
    return render(request, 'blood/update_nurse.html', context)
@login_required(login_url='adminlogin')
def delete_nurse_view(request, pk):
    nurse = get_object_or_404(Nurse, id=pk)

    try:
        user = User.objects.get(id=nurse.user_id)
        user.delete()
    except User.DoesNotExist:
        pass

    nurse.delete()

    return HttpResponseRedirect('/admin-nurse')
def sickle_cell_view(request):
    return render(request, 'blood/sickle_cell.html')

# Admin user = staff who is NOT a nurse
def is_admin(user):
    return user.is_staff and (not is_nurse(user))

@login_required(login_url='adminlogin')
@user_passes_test(is_admin, login_url='adminlogin')
@require_http_methods(["GET", "POST"])
def admin_nurse_blood_requests_view(request):
    if request.method == "POST":
        request_id = request.POST.get("request_id")
        action = request.POST.get("action")  # approve, reject, cancel, complete

        if not (request_id and action in ['approve', 'reject', 'cancel', 'complete']):
            messages.error(request, "Invalid form submission.")
            return redirect('admin-nurse-blood-requests')

        blood_request = get_object_or_404(NurseBloodRequest, id=request_id)

        # Allow cancel any time except if fulfilled
        if blood_request.status != NurseBloodRequest.STATUS_PENDING and action != 'cancel':
            messages.warning(request,
                f"Request ID {request_id} is already '{blood_request.status}'. No changes made.")
            return redirect('admin-nurse-blood-requests')

        if action == 'approve':
            blood_request.status = NurseBloodRequest.STATUS_APPROVED
            blood_request.save()
            messages.success(request, f"Request ID {request_id} approved.")

        elif action == 'reject':
            blood_request.status = NurseBloodRequest.STATUS_REJECTED
            blood_request.save()
            messages.success(request, f"Request ID {request_id} rejected.")

        elif action == 'cancel':
            if blood_request.status == NurseBloodRequest.STATUS_FULFILLED:
                messages.error(request, "Cannot cancel a fulfilled request.")
            else:
                blood_request.status = NurseBloodRequest.STATUS_CANCELLED
                blood_request.save()
                messages.success(request, f"Request ID {request_id} cancelled.")

        elif action == 'complete':
            if blood_request.status != NurseBloodRequest.STATUS_APPROVED:
                messages.error(request, "Only approved requests can be completed.")
                return redirect('admin-nurse-blood-requests')

            try:
                with transaction.atomic():
                    supplying_center = blood_request.supplying_center
                    requesting_center = blood_request.requester.donation_center

                    if not requesting_center:
                        messages.error(request, "Requesting nurse is not assigned to a donation center.")
                        return redirect('admin-nurse-blood-requests')

                    required_units = blood_request.units
                    bloodgroup = blood_request.blood_group

                    # Get FIFO StockUnits with available units in supplying_center
                    fifo_stock_units = StockUnit.objects.select_for_update().filter(
                        center=supplying_center,
                        bloodgroup=bloodgroup,
                        unit__gt=0,
                        expiry_date__gte=timezone.now().date()
                    ).order_by('expiry_date', 'added_on')

                    accumulated = 0
                    used_units_allocation = []

                    for stockunit in fifo_stock_units:
                        if accumulated >= required_units:
                            break

                        available = stockunit.unit
                        needed = required_units - accumulated
                        use_amount = min(available, needed)

                        # Deduct units from supplying StockUnit
                        stockunit.unit = F('unit') - use_amount
                        stockunit.save(update_fields=['unit'])

                        # Add units to requesting center StockUnit (same blood group and expiry)
                        requesting_stockunit, _ = StockUnit.objects.get_or_create(
                            center=requesting_center,
                            bloodgroup=bloodgroup,
                            expiry_date=stockunit.expiry_date,
                            defaults={'unit': 0}
                        )
                        requesting_stockunit.unit = F('unit') + use_amount
                        requesting_stockunit.save(update_fields=['unit'])

                        # Record usage for linking later
                        used_units_allocation.append((stockunit, use_amount))
                        accumulated += use_amount

                    if accumulated < required_units:
                        # Rollback transaction: will happen automatically due to exception
                        raise ValueError("Insufficient blood stock units available to fulfill the request.")

                    # Record which stockunits were used for this request
                    for stockunit, units_used in used_units_allocation:
                        NurseBloodRequestStockUnit.objects.create(
                            blood_request=blood_request,
                            stock_unit=stockunit,
                            units_used=units_used
                        )

                    # Update request status
                    blood_request.status = NurseBloodRequest.STATUS_FULFILLED
                    blood_request.save()

                messages.success(request, f"Request ID {request_id} marked as completed and stock updated.")

            except Stock.DoesNotExist:
                messages.error(request, "Stock data missing for the supplying center.")
            except Exception as e:
                messages.error(request, f"Error completing request: {str(e)}")

        return redirect('admin-nurse-blood-requests')

    # GET request: show all nurse blood requests
    requests = NurseBloodRequest.objects.select_related('requester', 'supplying_center').order_by('-created_at')

    new_nurse_requests_count = NurseBloodRequest.objects.filter(status=NurseBloodRequest.STATUS_PENDING).count()

    context = {
        "requests": requests,
        "new_nurse_requests_count": new_nurse_requests_count,
    }
    return render(request, "blood/admin_nurse_blood_requests.html", context)



logger = logging.getLogger(__name__)

def nearby_centers_view(request):
    """
    Unified view for finding nearby donation centers.
    Works for logged-in patients, donors, and guests.
    """

    latitude, longitude = None, None

    # 1. If logged-in, try pulling location from patient/donor profile
    if request.user.is_authenticated:
        user = request.user
        if hasattr(user, 'patient') and user.patient.latitude and user.patient.longitude:
            latitude = user.patient.latitude
            longitude = user.patient.longitude
        elif hasattr(user, 'donor') and user.donor.latitude and user.donor.longitude:
            latitude = user.donor.latitude
            longitude = user.donor.longitude

    # 2. If guest (or missing profile location), check GET params
    if latitude is None or longitude is None:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        if lat and lng:
            try:
                latitude = float(lat)
                longitude = float(lng)
                logger.info(f"[Guest/Public] Using lat={latitude}, lng={longitude}")
            except ValueError:
                messages.error(request, "Invalid location coordinates provided.")
                return render(request, 'blood/nearby_centers.html', {})

    # 3. Still missing? -> Ask user to update profile or allow location
    if latitude is None or longitude is None:
        if request.user.is_authenticated:
            messages.error(request, "Your location is not set. Please update your profile or allow location detection.")
            return redirect('profile-update')
        else:
            messages.error(request, "Location coordinates are required to find nearby centers.")
            return render(request, 'blood/nearby_centers.html', {})

    # 4. Fetch nearby centers
    centers = find_nearby_centers(latitude, longitude)
    logger.info(f"Found {len(centers)} centers near lat={latitude}, lng={longitude}")

    return render(request, 'blood/nearby_centers.html', {
        'nearby_centers': centers,
        'user_latitude': latitude,
        'user_longitude': longitude,
    })
@login_required
def save_user_location(request):
    if request.method == 'POST':
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')

        if lat is None or lon is None:
            return JsonResponse({'status': 'error', 'message': 'Missing latitude or longitude'}, status=400)

        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid latitude or longitude format'}, status=400)

        location_name = None

        try:
            url = f'https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}'
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                data = response.json()
                location_name = data.get('address', {}).get('city') or \
                                data.get('address', {}).get('town') or \
                                data.get('address', {}).get('village') or \
                                data.get('display_name')
        except Exception as e:
            location_name = None

        user = request.user

        if hasattr(user, 'donor'):
            user.donor.latitude = lat
            user.donor.longitude = lon
            user.donor.location_name = location_name
            user.donor.save()
        elif hasattr(user, 'patient'):
            user.patient.latitude = lat
            user.patient.longitude = lon
            user.patient.location_name = location_name
            user.patient.save()
        else:
            return JsonResponse({'status': 'error', 'message': 'User profile not found'}, status=400)

        return JsonResponse({'status': 'success', 'message': 'Location updated', 'location_name': location_name})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
from blood.models import StockTransaction

def blood_request_stock_transactions(request, blood_request_id):
    transactions = StockTransaction.objects.filter(blood_request_id=blood_request_id).select_related('stockunit').order_by('-transaction_at')
    context = {
        'transactions': transactions,
    }
    return render(request, 'blood/stock_transactions.html', context)

@login_required(login_url='adminlogin')
def admin_donation_report(request):
    # Prepare response for CSV download
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="donations_report_full.csv"'
    response.write(u'\ufeff'.encode('utf8'))  # BOM for Excel compatibility

    writer = csv.writer(response)
    writer.writerow([
        'Donor Name',
        'Age',
        'Contact',
        'Blood Group',
        'Unit',
        'Donation Center',
        'Nurse',
        'Appointment Date & Time',
        'Appointment Status',
        'Donation Status',
        'Activity Log'
    ])

    donations = BloodDonate.objects.select_related(
        'donor__user', 'donation_center'
    ).prefetch_related('appointments__nurse__user')

    for d in donations:
        donor_name = d.donor.user.get_full_name() if d.donor else "N/A"
        donor_age = d.donor_age or ''
        contact = d.donor.mobile if d.donor and d.donor.mobile else 'N/A'
        blood_group = d.bloodgroup or 'N/A'
        unit = d.unit or ''
        donation_center = d.donation_center.name if d.donation_center else 'N/A'
        main_status = d.status

        # Build activity log
        activity_log = []
        if d.approved_by_admin:
            activity_log.append(f"App(Admin) {d.approved_at_admin.strftime('%b %d, %H:%M')}")
        if d.approved_by_nurse:
            activity_log.append(f"App(Nurse) {d.approved_at_nurse.strftime('%b %d, %H:%M')}")
        if d.completed_by_admin:
            activity_log.append(f"Cmp(Admin) {d.completed_at_admin.strftime('%b %d, %H:%M')}")
        if d.completed_by_nurse:
            activity_log.append(f"Cmp(Nurse) {d.completed_at_nurse.strftime('%b %d, %H:%M')}")
        if d.status == 'cancelled':
            activity_log.append(f"Cn({d.cancelled_by or '?'}) {d.cancelled_at.strftime('%b %d, %H:%M') if d.cancelled_at else ''}")
        if d.status == 'rejected':
            activity_log.append(f"Rjct({d.rejected_by or '?'}) {d.rejected_at.strftime('%b %d, %H:%M') if d.rejected_at else ''}")
        activity_log_text = " | ".join(activity_log) if activity_log else "No activity yet"

        # Linked appointments
        if not d.appointments.exists():
            writer.writerow([
                f"{donor_name} ({donor_age})" if donor_age else donor_name,
                donor_age,
                contact,
                blood_group,
                unit,
                donation_center,
                "N/A",  # Nurse
                "N/A",  # Appointment Date
                "N/A",  # Appointment Status
                main_status,
                activity_log_text
            ])
        else:
            for appt in d.appointments.all():
                nurse_name = appt.nurse.user.get_full_name() if appt.nurse else "N/A"
                appt_date = appt.date.strftime("%Y-%m-%d %H:%M") if appt.date else "N/A"
                appt_status = appt.status
                writer.writerow([
                    f"{donor_name} ({donor_age})" if donor_age else donor_name,
                    donor_age,
                    contact,
                    blood_group,
                    unit,
                    donation_center,
                    nurse_name,
                    appt_date,
                    appt_status,
                    main_status,
                    activity_log_text
                ])

    return response

@staff_member_required  # ensures only admins/staff can access
def export_bloodrequests_csv(request):
    # Create the HttpResponse object with CSV header
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="blood_requests.csv"'},
    )

    writer = csv.writer(response)
    
    # Write CSV header
    writer.writerow([
        'ID', 'Patient Name', 'Age', 'Contact Number', 'Blood Group',
        'Unit (ml)', 'Urgency', 'Donation Center', 'Nurse Assigned',
        'Status', 'Created At'
    ])

    # Write data rows
    for req in BloodRequest.objects.select_related(
        'donation_center'
    ).prefetch_related('appointments'):
        appt = req.appointments.first()
        nurse_name = (
            f"{appt.nurse.first_name} {appt.nurse.last_name}"
            if appt and appt.nurse else "N/A"
        )
        writer.writerow([
            req.id,
            req.patient_name,
            req.patient_age,
            req.contact_number,
            req.bloodgroup or "N/A",
            req.unit or "N/A",
            req.urgency_level,
            req.donation_center.name if req.donation_center else "N/A",
            nurse_name,
            req.status,
            req.created_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return response
