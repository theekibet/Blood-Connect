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
from .models import ContactMessage, Contact ,BloodDriveEvent, Banner,  Testimonial,HomePageStats
from django.contrib import messages
from django.contrib.auth import authenticate, login
from patient.models import Patient
from donor.models import DonorEligibility
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from .models import Stock
from patient.models import BloodRequest
from donor.models import DonorEligibility, BloodDonate
from django.db.models import Max
from donor.models import Donor 
from .models import Notification,QuizAttempt
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
from datetime import date as dt_date
from django.utils.timezone import now
from collections import defaultdict
from django.http import JsonResponse
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
from donor.models import DonorBloodRequest
from django.db.models import Prefetch
from .forms import AdminLoginForm
import random
import re

from django.http import HttpResponseServerError
import requests
from .models import DonationFunFact, UserFactInteraction, DailyFactChallenge
from .fact_data import FACT_DATABASE, QUICK_FACTS, DONATION_TIPS, ELIGIBILITY_CRITERIA
from django.db.models import Avg
logger = logging.getLogger(__name__)

def home_view(request):
    try:
        # ==========================================
        # Ensure default donation center exists
        # ==========================================
        center = DonationCenter.objects.first()
        if not center:
            center = DonationCenter.objects.create(
                name="Main Donation Center",
                address="123 Main Street",
                city="Default City",
                contact_number="000-000-0000",
                open_hours="9:00 AM - 5:00 PM"
            )
            logger.info(f"Created default DonationCenter with id {center.id}")
        
        # ==========================================
        # Ensure default stock exists
        # ==========================================
        existing_stock = Stock.objects.filter(center=center)
        if not existing_stock.exists():
            blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
            for group in blood_groups:
                Stock.objects.create(
                    bloodgroup=group,
                    center=center,
                    unit=0
                )
            logger.info(f"Created default stock for center {center.id}")
        
        # ==========================================
        # Redirect authenticated users to dashboard
        # ==========================================
        if request.user.is_authenticated:
            return redirect('afterlogin')
        
        # ==========================================
        # DATABASE STATISTICS
        # ==========================================
        # Check if we have custom stats from admin
        custom_stats = HomePageStats.objects.filter(is_active=True)
        
        if custom_stats.exists():
            # Use admin-defined stats
            stats = custom_stats
        else:
            # Fallback to calculated stats
            # 1. Active donors = donors with approved eligibility OR no eligibility record yet
            active_donors_count = Donor.objects.filter(
                Q(donoreligibility__approved=True) | Q(donoreligibility__isnull=True)
            ).distinct().count()
            
            # 2. Lives saved = completed requests + completed donations
            completed_requests_count = BloodRequest.objects.filter(
                status='completed'
            ).count()
            completed_donations_count = BloodDonate.objects.filter(
                status='completed'
            ).count()
            lives_saved = completed_requests_count + completed_donations_count
            
            # 3. Total donation centers
            donation_centers_count = DonationCenter.objects.count()
            
            # 4. Total blood units available (non-expired)
            total_units_available = StockUnit.objects.filter(
                unit__gt=0,
                expiry_date__gte=dt_date.today()
            ).aggregate(
                total=Sum('unit')
            )['total'] or 0
            
            # Create default stats structure for template
            stats = [
                {
                    'stat_name': 'Active Donors',
                    'stat_value': active_donors_count,
                    'icon_class': 'fas fa-users'
                },
                {
                    'stat_name': 'Lives Saved',
                    'stat_value': lives_saved,
                    'icon_class': 'fas fa-heart'
                },
                {
                    'stat_name': 'Donation Centers',
                    'stat_value': donation_centers_count,
                    'icon_class': 'fas fa-hospital'
                },
                {
                    'stat_name': 'Units Available',
                    'stat_value': total_units_available,
                    'icon_class': 'fas fa-tint'
                },
            ]
        
        # ==========================================
        # DYNAMIC CONTENT FROM ADMIN
        # ==========================================
        now = timezone.now()
        
        # Get active banners (current date within start/end range)
        banners = Banner.objects.filter(
            is_active=True,
            start_date__lte=now
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now)
        )[:5]
        
        # Get upcoming blood drive events
        blood_drives = BloodDriveEvent.objects.filter(
            is_active=True,
            event_date__gte=now
        )[:6]
        
        # Get featured testimonials
        testimonials = Testimonial.objects.filter(
            is_active=True,
            is_featured=True
        )[:6]
        
        # ==========================================
        # RENDER HOME PAGE
        # ==========================================
        context = {
            'user_is_authenticated': request.user.is_authenticated,
            'stats': stats,
            'banners': banners,
            'blood_drives': blood_drives,
            'testimonials': testimonials,
            # Legacy context for backward compatibility
            'active_donors_count': stats[0]['stat_value'] if isinstance(stats, list) else None,
            'lives_saved': stats[1]['stat_value'] if isinstance(stats, list) else None,
            'donation_centers_count': stats[2]['stat_value'] if isinstance(stats, list) else None,
            'total_units_available': stats[3]['stat_value'] if isinstance(stats, list) else None,
        }
        
        return render(request, 'blood/index.html', context)
        
    except Exception as e:
        logger.error(f"Error in home_view: {e}", exc_info=True)
        return HttpResponseServerError("Something went wrong. Please try again later.")


def blood_drive_detail(request, pk):
    """Detail view for individual blood drive events"""
    try:
        drive = BloodDriveEvent.objects.get(pk=pk, is_active=True)
        context = {
            'drive': drive,
        }
        return render(request, 'blood/blood_drive_detail.html', context)
    except BloodDriveEvent.DoesNotExist:
        return redirect('home')


def blood_drives_list(request):
    """List all upcoming blood drive events"""
    try:
        now = timezone.now()
        blood_drives = BloodDriveEvent.objects.filter(
            is_active=True,
            event_date__gte=now
        ).order_by('display_order', 'event_date')
        
        # Get past events too
        past_drives = BloodDriveEvent.objects.filter(
            is_active=True,
            event_date__lt=now
        ).order_by('-event_date')[:10]
        
        context = {
            'upcoming_drives': blood_drives,  # Changed from 'blood_drives'
            'past_drives': past_drives,
        }
        return render(request, 'blood/blood_drives_list.html', context)  # Removed the extra 's'
    except Exception as e:
        logger.error(f"Error in blood_drives_list: {e}", exc_info=True)
        return redirect('home')
def is_donor(user):
    return user.groups.filter(name='DONOR').exists()

def is_patient(user):
    return user.groups.filter(name='PATIENT').exists()

def is_nurse(user):
    return user.groups.filter(name='NURSE').exists()
def adminlogin_view(request):
    """
    Custom admin login view that redirects to afterlogin
    """
    form = AdminLoginForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_staff or user.is_superuser:
                login(request, user)
                return redirect('afterlogin')
            else:
                messages.error(request, "You don't have admin privileges.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'blood/adminlogin.html', {"form": form})

def afterlogin_view(request):
    """
    Redirect users to their respective dashboards based on their SINGLE profile
    """
    user = request.user
    
    try:
        # Admin/staff first
        if user.is_staff or user.is_superuser:
            logger.info(f"Admin user {user.username} redirected to admin-dashboard")
            return redirect('admin-dashboard')
        
        # Check each profile type - ONLY ONE should exist per user
        if hasattr(user, 'patient') and user.patient:
            logger.info(f"User {user.username} redirected to patient-dashboard")
            return redirect('patient-dashboard')
        
        if hasattr(user, 'donor') and user.donor:
            logger.info(f"User {user.username} redirected to donor-dashboard")
            return redirect('donor-dashboard')
        
        if hasattr(user, 'nurse') and user.nurse:
            if user.nurse.is_approved:
                logger.info(f"User {user.username} redirected to nurse-dashboard")
                return redirect('nurse-dashboard')
            else:
                return redirect('nurse-pending-approval')
        
        if hasattr(user, 'lab_tech_profile') and user.lab_tech_profile:
            logger.info(f"User {user.username} redirected to lab_technologist:dashboard")
            return redirect('lab_technologist:dashboard')
        
        if hasattr(user, 'blood_bank_tech_profile') and user.blood_bank_tech_profile:
            logger.info(f"User {user.username} redirected to blood_bank_technician:dashboard")
            return redirect('blood_bank_technician:dashboard')
        
        # No profile found
        logger.warning(f"User {user.username} has no profile")
        messages.error(request, "Your account has no profile. Please complete registration.")
        return redirect('role_selection')
        
    except Exception as e:
        logger.error(f"Error in afterlogin_view: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred during login.")
        return redirect('home')

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
        {"label": "Total Requests", "value": BloodRequest.objects.count(), "icon": "fas fa-clipboard-list", "color": "#ffc107"},
        {"label": "Approved Requests", "value": BloodRequest.objects.filter(status="Approved").count(), "icon": "fas fa-check-circle", "color": "#17a2b8"},

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
@user_passes_test(lambda u: u.is_staff, login_url='adminlogin')
def admin_blood_view(request):
    centers = DonationCenter.objects.all()
    blood_groups = [bg for bg, _ in StockUnit.BLOOD_GROUP_CHOICES]

    stockForm = StockUnitForm()
    donation_center_form = DonationCenterForm()

    if request.method == 'POST':
        try:
            with transaction.atomic():
                if 'submit_stockunit' in request.POST:
                    stockForm = StockUnitForm(request.POST)
                    donation_center_form = DonationCenterForm()
                    
                    if stockForm.is_valid():
                        cd = stockForm.cleaned_data
                        
                        # Create StockUnit directly instead of using add_stock
                        stock_unit = StockUnit.objects.create(
                            center=cd['center'],
                            bloodgroup=cd['bloodgroup'],
                            unit=cd['unit'],
                            expiry_date=cd['expiry_date'],
                            barcode=cd['barcode'],
                        )
                        
                        logger.info(f"✅ Admin added stock unit: {stock_unit.barcode} - {stock_unit.unit}ml {stock_unit.bloodgroup}")
                        messages.success(request, f"Blood stock unit added successfully! Barcode: {stock_unit.barcode}")
                        return redirect('admin-blood')
                    else:
                        for field, errors in stockForm.errors.items():
                            for error in errors:
                                messages.error(request, f"{field}: {error}")
                        
                elif 'submit_donation_center' in request.POST:
                    if not request.user.has_perm('blood.add_donationcenter'):
                        messages.error(request, "You do not have permission to add a donation center.")
                        return redirect('admin-blood')
                    
                    donation_center_form = DonationCenterForm(request.POST)
                    stockForm = StockUnitForm()
                    
                    if donation_center_form.is_valid():
                        center = donation_center_form.save()
                        logger.info(f"✅ Admin added donation center: {center.name}")
                        messages.success(request, f"Donation center '{center.name}' added successfully.")
                        return redirect('admin-blood')
                    else:
                        for field, errors in donation_center_form.errors.items():
                            for error in errors:
                                messages.error(request, f"{field}: {error}")
                        
        except Exception as e:
            logger.error(f"❌ Error adding data: {str(e)}", exc_info=True)
            messages.error(request, f"Error adding data: {str(e)}")
    else:
        stockForm = StockUnitForm()
        donation_center_form = DonationCenterForm()

    # === SEARCH AND FILTER FUNCTIONALITY ===
    search_query = request.GET.get('q', '').strip()
    selected_center_id = request.GET.get('center_id', 'all')
    selected_bloodgroup = request.GET.get('bloodgroup', 'all')

    # Aggregated stock per center
    aggregated_stock = StockUnit.objects.filter(
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).values(
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
        center_stock_map[center_id]['stock'][bloodgroup] = total_units or 0

    chart_data = [{
        'center': data['name'],
        'center_id': center_id,
        'stock': data['stock']
    } for center_id, data in center_stock_map.items()]

    # Detailed stock units with filters
    stock_units = StockUnit.objects.all().select_related('center').order_by('-added_on')
    
    # Apply search filter
    if search_query:
        stock_units = stock_units.filter(
            Q(barcode__icontains=search_query) |
            Q(bloodgroup__icontains=search_query) |
            Q(center__name__icontains=search_query)
        )
    
    # Apply center filter
    if selected_center_id != 'all':
        try:
            stock_units = stock_units.filter(center__id=selected_center_id)
        except (ValueError, TypeError):
            pass
    
    # Apply blood group filter
    if selected_bloodgroup != 'all':
        stock_units = stock_units.filter(bloodgroup=selected_bloodgroup)

    selected_center = None
    if selected_center_id != 'all':
        try:
            selected_center = DonationCenter.objects.get(id=int(selected_center_id))
        except (DonationCenter.DoesNotExist, ValueError, TypeError):
            selected_center = None

    # Calculate statistics
    total_units = stock_units.aggregate(total=Sum('unit'))['total'] or 0
    total_batches = stock_units.count()
    
    # Expiring soon (within 7 days)
    expiring_threshold = timezone.now().date() + timedelta(days=7)
    expiring_soon = stock_units.filter(
        expiry_date__lte=expiring_threshold,
        expiry_date__gte=timezone.now().date()
    ).count()
    
    # Expired
    expired_count = StockUnit.objects.filter(
        expiry_date__lt=timezone.now().date(),
        unit__gt=0
    ).count()

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
        'search_query': search_query,
        'today_date': timezone.now().date(),
        'expiring_threshold': timezone.now().date() + timedelta(days=7),
        'stats': {
            'total_units': total_units,
            'total_batches': total_batches,
            'expiring_soon': expiring_soon,
            'expired': expired_count,
        }
    }
    return render(request, 'blood/admin_blood.html', context)
@login_required(login_url='adminlogin')
def admin_donor_view(request):
    query = request.GET.get('q', '').strip()

    donors = Donor.objects.select_related('user').all()
    eligibilities = DonorEligibility.objects.select_related('donor').all()

    # Optional search filter
    if query:
        donors = donors.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(bloodgroup__icontains=query) |
            Q(user__email__icontains=query) |
            Q(national_id__icontains=query)
        )

    # Build a dictionary of donor_id -> eligibility
    eligibility_dict = {e.donor_id: e for e in eligibilities}

    return render(request, 'blood/admin_donor.html', {
        'donors': donors,
        'eligibility_dict': eligibility_dict,
        'request': request,
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
    Stock,
    StockUnit,
    StockTransaction,
)
from blood.utils.stock_utils import deduct_stock_fifo
from donor.models import DonorBloodRequest
from patient.models import BloodRequest

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
        recipient_ids = request.POST.getlist('recipient_id')  # list of individual user ids
        selected_groups = request.POST.getlist('recipient_group')  # list of groups chosen
         
        # Validate inputs
        if not title or not message_text:
            messages.error(request, "Please provide both title and message.")
            return redirect('admin-post-notification')

        if not selected_groups and not recipient_ids:
            messages.error(request, "Please select at least one group or individual recipient.")
            return redirect('admin-post-notification')

        try:
            notifications = []

            # Map group names to models and content types
            group_model_map = {
                'patient': Patient,
                'donor': Donor,
                'nurse': Nurse
            }

            for group in selected_groups:
                model = group_model_map.get(group)
                if model:
                    content_type = ContentType.objects.get_for_model(model)
                    recipients = model.objects.all()
                    for recipient in recipients:
                        notifications.append(Notification(
                            title=title,
                            message=message_text,
                            recipient_content_type=content_type,
                            recipient_object_id=recipient.id,
                        ))

            # Add notifications for individually selected users if any
            if recipient_ids:
                # Need to identify content type of each user id since could be from any group
                # Assume user IDs are unique across patient, donor, nurse user relations

                # Gather users from all groups' users to map IDs to content types
                user_id_map = {}

                for group, model in group_model_map.items():
                    content_type = ContentType.objects.get_for_model(model)
                    objs = model.objects.filter(user__id__in=recipient_ids).select_related('user')
                    for obj in objs:
                        user_id_map[obj.user.id] = (content_type, obj.id)

                for user_id in recipient_ids:
                    if user_id in user_id_map:
                        content_type, obj_id = user_id_map[user_id]
                        notifications.append(Notification(
                            title=title,
                            message=message_text,
                            recipient_content_type=content_type,
                            recipient_object_id=obj_id,
                        ))

            if not notifications:
                messages.error(request, "No valid recipients found to send notification.")
                return redirect('admin-post-notification')

            Notification.objects.bulk_create(notifications)
            messages.success(request, "Notifications posted successfully!")

        except Exception as e:
            messages.error(request, f"Error posting notifications: {str(e)}")
        return redirect('admin-post-notification')

    patients = Patient.objects.select_related('user').all()
    donors = Donor.objects.select_related('user').all()
    nurses = Nurse.objects.select_related('user').all()

    context = {
        'patients': patients,
        'donors': donors,
        'nurses': nurses,
    }
    return render(request, 'blood/admin_post_notification.html', context)
# ---------------------------
# Admin Nurse Management View
# ---------------------------
@login_required(login_url='adminlogin')
def admin_nurse_view(request):
    """
    Display all nurses with filtering and search
    """
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    query = request.GET.get('q', '').strip()
    
    # Base queryset
    nurses = Nurse.objects.select_related('user', 'donation_center', 'approved_by').all()
    
    # Apply status filter
    if status_filter == 'pending':
        nurses = nurses.filter(is_approved=False, rejection_reason__isnull=True)
    elif status_filter == 'approved':
        nurses = nurses.filter(is_approved=True)
    elif status_filter == 'rejected':
        nurses = nurses.filter(rejection_reason__isnull=False)
    
    # Apply search
    if query:
        nurses = nurses.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(phone__icontains=query) |
            Q(registration_number__icontains=query) |
            Q(user__username__icontains=query)
        )
    
    # Calculate statistics
    total_count = Nurse.objects.count()
    pending_count = Nurse.objects.filter(is_approved=False, rejection_reason__isnull=True).count()
    approved_count = Nurse.objects.filter(is_approved=True).count()
    rejected_count = Nurse.objects.filter(rejection_reason__isnull=False).count()
    
    context = {
        'nurses': nurses,
        'status_filter': status_filter,
        'query': query,
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
    }
    
    return render(request, 'blood/admin_nurse.html', context)
# ---------------------------
# Approve Nurse
# ---------------------------
@login_required(login_url='adminlogin')
def admin_approve_nurse_view(request, pk):
    """
    Approve a pending nurse
    """
    nurse = get_object_or_404(Nurse, pk=pk)
    
    if request.method == 'POST':
        nurse.approve(approved_by_user=request.user)
        messages.success(
            request,
            f"✅ Nurse {nurse.full_name} has been approved successfully!"
        )
        
        # TODO: Send email notification to nurse
        # send_approval_email(nurse)
        
        return redirect('admin-nurse-view')
    
    context = {'nurse': nurse}
    return render(request, 'blood/admin_approve_nurse.html', context)
# ---------------------------
# Reject Nurse
# ---------------------------
@login_required(login_url='adminlogin')
def admin_reject_nurse_view(request, pk):
    """
    Reject a nurse with reason
    """
    nurse = get_object_or_404(Nurse, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('rejection_reason', '').strip()
        
        if not reason:
            messages.error(request, "❌ Please provide a reason for rejection.")
            return render(request, 'blood/admin_reject_nurse.html', {'nurse': nurse})
        
        nurse.reject(reason=reason, rejected_by_user=request.user)
        messages.success(
            request,
            f"✅ Nurse {nurse.full_name} has been rejected."
        )
        
        # TODO: Send rejection email to nurse
        # send_rejection_email(nurse, reason)
        
        return redirect('admin-nurse-view')
    
    context = {'nurse': nurse}
    return render(request, 'blood/admin_reject_nurse.html', context)


# ---------------------------
# Revoke Nurse Approval
# ---------------------------
@login_required(login_url='adminlogin')
def admin_revoke_nurse_view(request, pk):
    """
    Revoke an approved nurse's access
    """
    nurse = get_object_or_404(Nurse, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('revoke_reason', '').strip()
        
        if not reason:
            messages.error(request, "❌ Please provide a reason for revocation.")
            return render(request, 'blood/admin_revoke_nurse.html', {'nurse': nurse})
        
        nurse.reject(reason=reason, rejected_by_user=request.user)
        messages.success(
            request,
            f"✅ Access revoked for {nurse.full_name}."
        )
        
        # TODO: Send revocation email
        # send_revocation_email(nurse, reason)
        
        return redirect('admin-nurse-view')
    
    context = {'nurse': nurse}
    return render(request, 'blood/admin_revoke_nurse.html', context)

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




logger = logging.getLogger(__name__)

def nearby_centers_view(request):
    """
    Unified view for finding nearby donation centers.
    Works for logged-in patients, donors, and guests.
    """

    latitude, longitude = None, None

    # 1️⃣ If logged-in, try pulling location from profile
    if request.user.is_authenticated:
        user = request.user
        if hasattr(user, 'patient') and user.patient.latitude and user.patient.longitude:
            latitude = user.patient.latitude
            longitude = user.patient.longitude
        elif hasattr(user, 'donor') and user.donor.latitude and user.donor.longitude:
            latitude = user.donor.latitude
            longitude = user.donor.longitude

    # 2️⃣ If guest (or missing), check GET params
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

    # 3️⃣ Still missing? -> ask user to update profile or allow location
    if latitude is None or longitude is None:
        if request.user.is_authenticated:
            messages.error(request, "Your location is not set. Please update your profile or allow location detection.")
            if hasattr(request.user, 'donor'):
                return redirect('donor-edit-profile')
            elif hasattr(request.user, 'patient'):
                return redirect('patient-edit-profile')  # adjust this if your patient route differs
            else:
                return redirect('home')
        else:
            messages.error(request, "Location coordinates are required to find nearby centers.")
            return render(request, 'blood/nearby_centers.html', {})

    # 4️⃣ Fetch nearby centers (you already have this helper)
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
def generate_username_suggestions(base_username, count=5):
    """Generate unique username suggestions based on the provided username."""
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
        suffixes = ['_user', '_blood', '_med', str(random.randint(100, 999)), str(random.randint(10, 99))]
        for suffix in suffixes:
            if len(suggestions) >= count:
                break
            suggestion = f"{base_clean}{suffix}"
            if not User.objects.filter(username=suggestion).exists():
                suggestions.append(suggestion)

    # Strategy 3: Add current year
    if len(suggestions) < count:
        from datetime import datetime
        year = datetime.now().year
        suggestion = f"{base_clean}{year}"
        if not User.objects.filter(username=suggestion).exists():
            suggestions.append(suggestion)

    # Strategy 4: Add keyword combinations
    if len(suggestions) < count:
        combo_suffixes = ['blood', 'health', 'care', 'hero', 'saver']
        for suffix in combo_suffixes:
            if len(suggestions) >= count:
                break
            suggestion = f"{base_clean}_{suffix}"
            if not User.objects.filter(username=suggestion).exists():
                suggestions.append(suggestion)

    return suggestions[:count]
def check_username_ajax(request):
    """
    System-wide username validation
    Checks if username exists across all user types
    """
    username = request.GET.get('username', '').strip()
    
    if not username:
        return JsonResponse({
            'exists': False,
            'message': 'Username cannot be empty',
        })
    
    # Check if username exists
    user_exists = User.objects.filter(username__iexact=username).exists()
    
    if user_exists:
        # Generate suggestions based on the username
        suggestions = []
        base_username = username.lower()
        
        # Generate 5 unique suggestions
        attempts = 0
        max_attempts = 20
        
        while len(suggestions) < 5 and attempts < max_attempts:
            attempts += 1
            # Different suggestion strategies
            if attempts % 4 == 0:
                suggestion = f"{base_username}{random.randint(100, 999)}"
            elif attempts % 4 == 1:
                suggestion = f"{base_username}_{random.randint(10, 99)}"
            elif attempts % 4 == 2:
                suggestion = f"{base_username}{random.randint(10, 99)}"
            else:
                suggestion = f"{base_username}{random.choice(['_x', '_pro', '_'])}{random.randint(1, 99)}"
            
            # Check if suggestion is available
            if not User.objects.filter(username__iexact=suggestion).exists():
                suggestions.append(suggestion)
        
        return JsonResponse({
            'exists': True,
            'message': 'This username is already taken',
            'suggestions': suggestions
        })
    
    return JsonResponse({
        'exists': False,
        'message': 'Username is available',
    })


def validate_username_ajax(request):
    """
    Alternative endpoint for username validation (for patient signup compatibility)
    """
    username = request.GET.get('username', '').strip()
    
    if not username:
        return JsonResponse({'is_taken': False})
    
    is_taken = User.objects.filter(username__iexact=username).exists()
    
    return JsonResponse({'is_taken': is_taken})


def check_email_ajax(request):
    """
    System-wide email validation
    Checks if email exists across all user types
    """
    email = request.GET.get('email', '').strip()
    
    if not email:
        return JsonResponse({
            'valid': False,
            'message': 'Email cannot be empty',
        })
    
    # Basic email format validation
    import re
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return JsonResponse({
            'valid': False,
            'message': 'Please enter a valid email address',
        })
    
    # Check if email exists
    email_exists = User.objects.filter(email__iexact=email).exists()
    
    if email_exists:
        return JsonResponse({
            'valid': False,
            'message': 'This email is already registered',
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Email is available',
    })


def check_national_id_ajax(request):
    """
    System-wide national ID validation
    Checks if national ID exists in Donor or Patient records
    """
    national_id = request.GET.get('national_id', '').strip()
    
    if not national_id:
        return JsonResponse({
            'valid': False,
            'message': 'National ID cannot be empty',
        })
    
    # Validate format (8 digits)
    if not national_id.isdigit() or len(national_id) != 8:
        return JsonResponse({
            'valid': False,
            'message': 'National ID must be exactly 8 digits',
        })
    
    # Check if national ID exists in donor or patient records
    donor_exists = Donor.objects.filter(national_id=national_id).exists()
    patient_exists = Patient.objects.filter(national_id=national_id).exists()
    
    if donor_exists or patient_exists:
        return JsonResponse({
            'valid': False,
            'message': 'This National ID is already registered',
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'National ID is available',
    })


def check_mobile_ajax(request):
    """
    System-wide mobile number validation
    Checks if mobile number exists across Donor, Patient, and Nurse records
    """
    mobile = request.GET.get('mobile', '').strip()
    
    if not mobile:
        return JsonResponse({
            'valid': False,
            'message': 'Mobile number cannot be empty',
        })
    
    # Validate Kenyan mobile format (+254...)
    import re
    # Accept formats: +254..., 254..., 07..., 01...
    if mobile.startswith('+254'):
        if len(mobile) != 13:
            return JsonResponse({
                'valid': False,
                'message': 'Invalid mobile format. Should be +254XXXXXXXXX',
            })
    elif mobile.startswith('254'):
        if len(mobile) != 12:
            return JsonResponse({
                'valid': False,
                'message': 'Invalid mobile format. Should be 254XXXXXXXXX',
            })
    elif mobile.startswith('0'):
        if len(mobile) != 10:
            return JsonResponse({
                'valid': False,
                'message': 'Invalid mobile format. Should be 07XXXXXXXX or 01XXXXXXXX',
            })
    else:
        return JsonResponse({
            'valid': False,
            'message': 'Mobile number should start with +254, 254, or 0',
        })
    
    # Normalize to +254 format for comparison
    if mobile.startswith('0'):
        normalized = '+254' + mobile[1:]
    elif mobile.startswith('254'):
        normalized = '+' + mobile
    else:
        normalized = mobile
    
    # Check if mobile exists in any table
    donor_exists = Donor.objects.filter(mobile=normalized).exists()
    patient_exists = Patient.objects.filter(mobile=normalized).exists()
    nurse_exists = Nurse.objects.filter(phone=normalized).exists()
    
    if donor_exists or patient_exists or nurse_exists:
        return JsonResponse({
            'valid': False,
            'message': 'This mobile number is already registered',
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Mobile number is available',
    })

def ajax_check_nurse_registration(request):
    """Check if nurse registration number is available."""
    registration_number = request.GET.get('registration_number', '').strip().upper()
    
    if not registration_number:
        return JsonResponse({
            'valid': False,
            'message': 'Registration number is required'
        })
    
    # Check format (5-30 uppercase alphanumeric)
    if not re.match(r'^[A-Z0-9]{5,30}$', registration_number):
        return JsonResponse({
            'valid': False,
            'message': 'Registration number must be 5-30 uppercase letters and numbers only'
        })
    
    # Check if exists
    exists = Nurse.objects.filter(registration_number=registration_number).exists()
    
    if exists:
        return JsonResponse({
            'valid': False,
            'message': f"Registration number '{registration_number}' is already in use"
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Registration number is available'
    })



def ajax_check_nurse_phone(request):
    """Check if nurse phone number is available."""
    phone = request.GET.get('phone', '').strip()
    
    if not phone:
        return JsonResponse({
            'valid': False,
            'message': 'Phone number is required'
        })
    
    # Remove spaces and dashes
    phone_clean = phone.replace(' ', '').replace('-', '')
    
    # Check format
    if not re.match(r'^\+?1?\d{9,15}$', phone_clean):
        return JsonResponse({
            'valid': False,
            'message': 'Invalid format. Use +999999999 (9-15 digits)'
        })
    
    # Check if exists
    exists = Nurse.objects.filter(phone=phone_clean).exists()
    
    if exists:
        return JsonResponse({
            'valid': False,
            'message': 'This phone number is already registered'
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Phone number is available'
    })


from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'shared/change_password.html'
    success_url = reverse_lazy('password-change-success')
    
    def form_valid(self, form):
        messages.success(
            self.request,
            "Your password has been changed successfully! "
            "Please log in again with your new password."
        )
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add user type for potential customization
        if hasattr(self.request.user, 'patient'):
            context['user_type'] = 'patient'
        elif hasattr(self.request.user, 'donor'):
            context['user_type'] = 'donor'
        elif hasattr(self.request.user, 'nurse'):
            context['user_type'] = 'nurse'
        elif self.request.user.is_staff:
            context['user_type'] = 'admin'
        else:
            context['user_type'] = 'user'
        
        return context





def load_fact_from_database(fact_id=None, category=None):
    """Load fact from database or generate from FACT_DATABASE"""
    # Try database first
    if DonationFunFact.objects.exists():
        facts = DonationFunFact.objects.filter(is_verified=True)
        
        if category:
            facts = facts.filter(category=category)
        
        if fact_id:
            try:
                return facts.get(id=fact_id)
            except DonationFunFact.DoesNotExist:
                pass
        
        if facts.exists():
            return random.choice(facts)
    
    # Fallback to FACT_DATABASE
    available_facts = FACT_DATABASE
    if category:
        available_facts = [f for f in FACT_DATABASE if f.get('category') == category]
    
    if available_facts:
        fact_data = random.choice(available_facts)
        # Create a temporary fact object
        return type('Fact', (), {
            **fact_data,
            'id': None,
            'likes': 0,
            'times_viewed': 0,
            'get_category_display': lambda: dict(DonationFunFact.FACT_CATEGORIES).get(fact_data.get('category', ''), 'Unknown')
        })()
    
    return None


def did_you_know_home(request):
    """Main interactive facts page with enhanced features"""
    today = timezone.now().date()
    
    # Get or create daily challenge
    daily_challenge = None
    try:
        daily_challenge = DailyFactChallenge.objects.select_related('fact').get(date=today)
    except DailyFactChallenge.DoesNotExist:
        if DonationFunFact.objects.filter(has_quiz=True, is_verified=True).exists():
            quiz_facts = DonationFunFact.objects.filter(has_quiz=True, is_verified=True)
            random_fact = random.choice(quiz_facts)
            daily_challenge = DailyFactChallenge.objects.create(
                date=today,
                fact=random_fact
            )
    
    # Get facts by category
    all_facts = DonationFunFact.objects.filter(is_verified=True)
    
    if all_facts.exists():
        random_fact = random.choice(all_facts)
        trending_facts = all_facts.order_by('-likes', '-times_viewed')[:5]
        recent_facts = all_facts.order_by('-created_at')[:5]
        
        # Category breakdown
        category_stats = {}
        for cat_key, cat_name in DonationFunFact.FACT_CATEGORIES:
            count = all_facts.filter(category=cat_key).count()
            if count > 0:
                category_stats[cat_key] = {
                    'name': cat_name,
                    'count': count,
                    'sample': all_facts.filter(category=cat_key).first()
                }
    else:
        # Fallback to sample data
        random_fact = load_fact_from_database()
        trending_facts = []
        recent_facts = []
        
        # Create category stats from FACT_DATABASE
        category_stats = {}
        for cat_key, cat_name in DonationFunFact.FACT_CATEGORIES:
            cat_facts = [f for f in FACT_DATABASE if f.get('category') == cat_key]
            if cat_facts:
                category_stats[cat_key] = {
                    'name': cat_name,
                    'count': len(cat_facts),
                    'sample': None
                }
    
    # User statistics (if authenticated)
    user_stats = None
    if request.user.is_authenticated:
        user_stats = {
            'facts_viewed': UserFactInteraction.objects.filter(
                user=request.user,
                interaction_type='view'
            ).count(),
            'quizzes_taken': QuizAttempt.objects.filter(user=request.user).count(),
            'average_score': QuizAttempt.objects.filter(user=request.user).aggregate(
                avg=Avg('score')
            )['avg'] or 0,
            'liked_facts': UserFactInteraction.objects.filter(
                user=request.user,
                interaction_type='like'
            ).count(),
        }
    
    context = {
        'daily_challenge': daily_challenge,
        'random_fact': random_fact,
        'trending_facts': trending_facts,
        'recent_facts': recent_facts,
        'category_stats': category_stats,
        'quick_facts': random.sample(QUICK_FACTS, min(8, len(QUICK_FACTS))),
        'categories': DonationFunFact.FACT_CATEGORIES,
        'donation_tips': DONATION_TIPS,
        'eligibility_criteria': ELIGIBILITY_CRITERIA,
        'user_stats': user_stats,
        'total_facts': all_facts.count() if all_facts.exists() else len(FACT_DATABASE),
    }
    
    return render(request, 'shared/home.html', context)


def fact_detail(request, fact_id):
    """Detailed view of a single fact"""
    try:
        fact = DonationFunFact.objects.get(id=fact_id, is_verified=True)
        
        # Track view
        fact.times_viewed += 1
        fact.save(update_fields=['times_viewed'])
        
        if request.user.is_authenticated:
            UserFactInteraction.objects.get_or_create(
                user=request.user,
                fact=fact,
                interaction_type='view'
            )
        
        # Get related facts
        related_facts = DonationFunFact.objects.filter(
            category=fact.category,
            is_verified=True
        ).exclude(id=fact.id).order_by('?')[:3]
        
        # Check if user has liked this fact
        user_liked = False
        if request.user.is_authenticated:
            user_liked = UserFactInteraction.objects.filter(
                user=request.user,
                fact=fact,
                interaction_type='like'
            ).exists()
        
        context = {
            'fact': fact,
            'related_facts': related_facts,
            'user_liked': user_liked,
            'categories': DonationFunFact.FACT_CATEGORIES,
        }
        
        return render(request, 'shared/donation_facts/fact_detail.html', context)
        
    except DonationFunFact.DoesNotExist:
        return redirect('did_you_know_home')


def fact_category(request, category=None):
    """Show facts by category with pagination"""
    if category and category not in dict(DonationFunFact.FACT_CATEGORIES):
        return redirect('did_you_know_home')
    
    # Get facts from database
    if category:
        facts = DonationFunFact.objects.filter(category=category, is_verified=True)
        category_name = dict(DonationFunFact.FACT_CATEGORIES).get(category)
    else:
        facts = DonationFunFact.objects.filter(is_verified=True)
        category_name = "All Facts"
    
    # If no facts in database, use FACT_DATABASE
    use_fallback = False
    if not facts.exists():
        use_fallback = True
        if category:
            facts = [f for f in FACT_DATABASE if f.get('category') == category]
        else:
            facts = FACT_DATABASE
    
    # Pagination
    if not use_fallback:
        paginator = Paginator(facts.order_by('-created_at'), 12)  # 12 facts per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    else:
        page_obj = facts  # No pagination for fallback data
    
    context = {
        'facts': page_obj if not use_fallback else facts,
        'selected_category': category,
        'category_name': category_name,
        'categories': DonationFunFact.FACT_CATEGORIES,
        'use_fallback': use_fallback,
        'total_facts': facts.count() if not use_fallback else len(facts),
    }
    
    return render(request, 'shared/fact_list.html', context)


def interactive_quiz(request):
    """Interactive quiz page with scoring"""
    # Get quiz facts from database
    quiz_facts = DonationFunFact.objects.filter(has_quiz=True, is_verified=True)
    
    use_fallback = False
    if not quiz_facts.exists():
        use_fallback = True
        quiz_facts = [f for f in FACT_DATABASE if f.get('has_quiz', False)]
        selected_facts = random.sample(quiz_facts, min(5, len(quiz_facts)))
    else:
        # Select 10 random quiz questions
        selected_facts = random.sample(list(quiz_facts), min(10, quiz_facts.count()))
    
    context = {
        'quiz_facts': selected_facts,
        'use_fallback': use_fallback,
        'total_questions': len(selected_facts),
    }
    
    return render(request, 'shared/quiz.html', context)


@csrf_exempt
def submit_quiz(request):
    """Submit completed quiz and get score"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        
        answers = data.get('answers', {})
        total_questions = len(answers)
        correct_answers = sum(1 for is_correct in answers.values() if is_correct)
        score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # Save quiz attempt if user is authenticated
        if request.user.is_authenticated:
            QuizAttempt.objects.create(
                user=request.user,
                total_questions=total_questions,
                correct_answers=correct_answers,
                score=score_percentage
            )
        
        return JsonResponse({
            'total': total_questions,
            'correct': correct_answers,
            'score': round(score_percentage, 1),
            'passed': score_percentage >= 70
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def check_quiz_answer(request):
    """AJAX endpoint to check individual quiz answers"""
    if request.method == 'POST':
        fact_id = request.POST.get('fact_id')
        user_answer = request.POST.get('answer')
        
        try:
            fact = DonationFunFact.objects.get(id=fact_id)
            is_correct = (user_answer == fact.correct_answer)
            
            # Update daily challenge stats
            today = timezone.now().date()
            try:
                challenge = DailyFactChallenge.objects.get(date=today, fact=fact)
                challenge.total_participants += 1
                if is_correct:
                    challenge.correct_answers += 1
                challenge.save()
            except DailyFactChallenge.DoesNotExist:
                pass
            
            # Track interaction
            if request.user.is_authenticated:
                UserFactInteraction.objects.create(
                    user=request.user,
                    fact=fact,
                    interaction_type='quiz_correct' if is_correct else 'quiz_wrong',
                    user_answer=user_answer
                )
            
            return JsonResponse({
                'correct': is_correct,
                'correct_answer': fact.correct_answer,
                'explanation': fact.explanation
            })
        except DonationFunFact.DoesNotExist:
            # Fallback to sample data
            for fact_data in FACT_DATABASE:
                if str(fact_data.get('id')) == str(fact_id) or fact_data.get('title') == fact_id:
                    is_correct = (user_answer == fact_data.get('correct_answer', ''))
                    return JsonResponse({
                        'correct': is_correct,
                        'correct_answer': fact_data.get('correct_answer', ''),
                        'explanation': fact_data.get('explanation', '')
                    })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def like_fact(request):
    """AJAX endpoint to like a fact"""
    if request.method == 'POST':
        fact_id = request.POST.get('fact_id')
        
        try:
            fact = DonationFunFact.objects.get(id=fact_id)
            
            # Check if user already liked
            if request.user.is_authenticated:
                existing_like = UserFactInteraction.objects.filter(
                    user=request.user,
                    fact=fact,
                    interaction_type='like'
                ).exists()
                
                if existing_like:
                    return JsonResponse({'error': 'Already liked', 'likes': fact.likes}, status=400)
            
            fact.likes += 1
            fact.save(update_fields=['likes'])
            
            if request.user.is_authenticated:
                UserFactInteraction.objects.create(
                    user=request.user,
                    fact=fact,
                    interaction_type='like'
                )
            
            return JsonResponse({'likes': fact.likes, 'success': True})
        except DonationFunFact.DoesNotExist:
            return JsonResponse({'error': 'Fact not found', 'likes': 0}, status=404)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


def random_fact_api(request):
    """API endpoint to get a random fact (for AJAX)"""
    category = request.GET.get('category')
    fact = load_fact_from_database(category=category)
    
    if not fact:
        return JsonResponse({'error': 'No facts available'}, status=404)
    
    # Track view if it's a database fact
    if hasattr(fact, 'id') and fact.id:
        fact.times_viewed += 1
        fact.save(update_fields=['times_viewed'])
    
    fact_data = {
        'id': fact.id if hasattr(fact, 'id') else 0,
        'title': fact.title,
        'fact_text': fact.fact_text,
        'category': fact.category,
        'image_url': fact.image_url if hasattr(fact, 'image_url') else None,
        'has_quiz': fact.has_quiz,
        'likes': fact.likes if hasattr(fact, 'likes') else 0,
    }
    
    return JsonResponse(fact_data)


def daily_challenge_progress(request):
    """Track daily challenge progress"""
    today = timezone.now().date()
    challenge = DailyFactChallenge.objects.filter(date=today).first()
    
    if challenge:
        accuracy = round((challenge.correct_answers / challenge.total_participants * 100), 1) if challenge.total_participants > 0 else 0
        return JsonResponse({
            'total_participants': challenge.total_participants,
            'correct_answers': challenge.correct_answers,
            'accuracy': accuracy,
            'date': str(today)
        })
    
    return JsonResponse({'error': 'No challenge today'}, status=404)


@login_required
def user_progress(request):
    """Show user's learning progress and achievements"""
    interactions = UserFactInteraction.objects.filter(user=request.user)
    quiz_attempts = QuizAttempt.objects.filter(user=request.user).order_by('-created_at')
    
    stats = {
        'total_facts_viewed': interactions.filter(interaction_type='view').count(),
        'facts_liked': interactions.filter(interaction_type='like').count(),
        'quizzes_taken': quiz_attempts.count(),
        'average_score': quiz_attempts.aggregate(avg=Avg('score'))['avg'] or 0,
        'best_score': quiz_attempts.aggregate(max=Max('score'))['max'] or 0,
        'quiz_history': quiz_attempts[:10],  # Last 10 quizzes
    }
    
    context = {
        'stats': stats,
        'categories': DonationFunFact.FACT_CATEGORIES,
    }
    
    return render(request, 'shared/user_progress.html', context)


def search_facts(request):
    """Search facts by keyword"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return redirect('did_you_know_home')
    
    # Search in database
    facts = DonationFunFact.objects.filter(
        Q(title__icontains=query) | 
        Q(fact_text__icontains=query) |
        Q(explanation__icontains=query),
        is_verified=True
    ).order_by('-times_viewed')
    
    # Also search in FACT_DATABASE if needed
    fallback_facts = []
    if not facts.exists():
        fallback_facts = [
            f for f in FACT_DATABASE 
            if query.lower() in f.get('title', '').lower() or 
               query.lower() in f.get('fact_text', '').lower()
        ]
    
    context = {
        'facts': facts if facts.exists() else fallback_facts,
        'query': query,
        'use_fallback': not facts.exists(),
        'categories': DonationFunFact.FACT_CATEGORIES,
    }
    
    return render(request, 'shared/search_results.html', context)
   