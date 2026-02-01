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
from datetime import date as dt_date
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
from donor.models import DonorBloodRequest
from django.db.models import Prefetch
from .forms import AdminLoginForm
import random
import re

from django.http import HttpResponseServerError
import requests


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
    Enhanced afterlogin view with proper error handling and fallback logic
    """
    user = request.user
    
    try:
        # ========================================
        # CHECK STAFF/ADMIN FIRST (HIGHEST PRIORITY)
        # ========================================
        if user.is_staff or user.is_superuser:
            logger.info(f"Admin user {user.username} redirected to admin-dashboard")
            return redirect('admin-dashboard')
        
        # Check for patient profile
        elif hasattr(user, 'patient') and user.patient:
            logger.info(f"User {user.username} redirected to patient-dashboard")
            return redirect('patient-dashboard')
        
        # Check for nurse profile
        elif hasattr(user, 'nurse') and user.nurse:
            logger.info(f"User {user.username} redirected to nurse-dashboard")
            return redirect('nurse-dashboard')
        
        # Check for donor profile
        elif hasattr(user, 'donor') and user.donor:
            logger.info(f"User {user.username} redirected to donor-dashboard")
            return redirect('donor-dashboard')
        
        # User authenticated but no profile exists
        else:
            logger.warning(f"User {user.username} has no associated profile")
            messages.error(
                request, 
                "Your account exists but no profile was found. Please contact support."
            )
            
            # Try to determine which group they belong to and suggest action
            if user.groups.filter(name='PATIENT').exists():
                messages.info(request, "You are registered as a PATIENT but profile setup is incomplete.")
                return redirect('patientsignup')
            
            elif user.groups.filter(name='NURSE').exists():
                messages.info(request, "You are registered as a NURSE but profile setup is incomplete.")
                return redirect('nursesignup')
            
            elif user.groups.filter(name='DONOR').exists():
                messages.info(request, "You are registered as a DONOR but profile setup is incomplete.")
                return redirect('donorsignup')
            
            # No group assigned either - serious issue
            else:
                messages.error(
                    request,
                    "Your account is not properly configured. Please contact the administrator."
                )
                logger.error(f"User {user.username} (ID: {user.id}) has no group or profile")
                return redirect('home')
    
    except Exception as e:
        logger.error(f"Error in afterlogin_view for user {user.username}: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred during login. Please try again.")
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



from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.views import LoginView

logger = logging.getLogger(__name__)

# -------------------------------
# Central Login View for ALL users
# -------------------------------
class CentralLoginView(LoginView):
    """Central login view that redirects to individual login pages"""
    
    def get(self, request, *args, **kwargs):
        user_type = request.GET.get('user_type')
        
        # Redirect based on user_type to existing login pages
        if user_type == 'donor':
            return redirect('donorlogin')
        elif user_type == 'patient':
            return redirect('patientlogin')
        elif user_type == 'nurse':
            return redirect('nurselogin')
        else:
            # Show a simple role selection page
            return render(request, 'blood/role_selection.html')
# -------------------------------
# Email Verification (Shared)
# -------------------------------
def send_verification_email(user, request):
    """Send email verification link to new user"""
    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        verification_url = request.build_absolute_uri(
            f'/verify-email/{uid}/{token}/'
        )
        
        # Determine user type for personalized message
        user_type = 'User'
        if hasattr(user, 'patient'):
            user_type = 'Patient'
        elif hasattr(user, 'donor'):
            user_type = 'Donor'
        elif hasattr(user, 'nurse'):
            user_type = 'Nurse'
        
        context = {
            'user': user,
            'verification_url': verification_url,
            'site_name': 'BloodConnect',
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'user_type': user_type,
        }
        
        html_message = render_to_string('shared/verification_email.html', context)
        plain_message = strip_tags(html_message)
        subject = f'Verify Your Email - BloodConnect {user_type} Account'
        
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Verification email sent to {user.email} ({user_type})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False

def verify_email_view(request, uidb64, token):
    """Verify user's email address"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        
        # Determine user type for message
        if hasattr(user, 'patient'):
            user_type = 'patient'
            login_url = reverse('central_login') + '?user_type=patient'
        elif hasattr(user, 'donor'):
            user_type = 'donor'
            login_url = reverse('central_login') + '?user_type=donor'
        elif hasattr(user, 'nurse'):
            user_type = 'nurse'
            login_url = reverse('central_login') + '?user_type=nurse'
        else:
            user_type = 'user'
            login_url = reverse('central_login')
        
        messages.success(request, 
            f'✅ Email verified successfully! Your {user_type} account is now active. '
            f'You can now <a href="{login_url}" class="alert-link">login here</a>.'
        )
        return redirect('home')
    else:
        messages.error(request, '❌ Verification link is invalid or has expired.')
        return redirect('home')

def resend_verification_view(request):
    """Resend verification email"""
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            user = User.objects.get(email=email)
            
            if user.is_active:
                messages.info(request, '✅ Account is already verified. You can log in.')
                return redirect('central_login')
            else:
                if send_verification_email(user, request):
                    messages.success(request, '📧 Verification email sent! Check your inbox.')
                else:
                    messages.error(request, '❌ Failed to send email. Try again later.')
                return redirect('central_login')
                
        except User.DoesNotExist:
            messages.error(request, '❌ No account found with this email.')
            return redirect('central_login')
    
    # GET request - show form
    return render(request, 'shared/resend_verification.html')