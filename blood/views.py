# blood/views.py - CLEANED VERSION (Only keep public and analytics views)

from django.shortcuts import render, redirect, reverse
from . import forms, models
from django.db.models import Sum, Q
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.conf import settings
from datetime import date, timedelta
from django.core.mail import send_mail
from django.contrib.auth.models import User
from donor import models as dmodels
from donor import forms as dforms
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from .forms import ContactForm
from .models import ContactMessage, Contact ,BloodDriveEvent,  Testimonial,HomePageStats
from django.contrib import messages
from django.contrib.auth import authenticate, login
from donor.models import DonorEligibility
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from .models import Stock
from hospital.models import HospitalBloodRequest
from hospital.models import HospitalUser, Hospital
from donor.models import DonorEligibility, BloodDonate
from django.db.models import Max
from donor.models import Donor
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from utils.models import Notification
from django.contrib.contenttypes.models import ContentType
from blood import models as blood_models
from donor import models as donor_models
from phlebotomist import models as phlebotomist_models
from hospital import models as hospital_models
from django.http import Http404
from django.core.paginator import Paginator
from blood import models
from blood import models as bmodels
from phlebotomist.models import Phlebotomist
from phlebotomist import forms as phlebotomist_forms
from .models import DonationCenter, StockUnit
from .forms import BloodForm
from .forms import StockUnitForm
import json
import os
from datetime import datetime
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
from phlebotomist.models import Appointment
import logging
from donor.models import BLOODGROUP_CHOICES
from django.db.models import F
from blood.models import StockTransaction
import csv
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch
from .forms import AdminLoginForm
import random
import re
from blood.utils.validators import check_for_duplicate_profiles,get_user_profile_type
from django.http import HttpResponseServerError
import requests
from django.contrib.auth.mixins import LoginRequiredMixin
import time
from django_ratelimit.decorators import ratelimit
from .models import HoneypotAttempt
from .models import UserReview, ReviewSurvey
from .forms import UserReviewForm
from .forms import ReviewSurveyForm
from django.db.models import Avg

logger = logging.getLogger(__name__)

# ==========================================
# PUBLIC VIEWS (Keep these)
# ==========================================


def home_view(request):
    try:
        # ==========================================
        # Ensure default donation center exists
        # ==========================================
        from blood.models import DonationCenter, Stock, StockUnit, BloodDriveEvent, Testimonial, HomePageStats
        from donor.models import Donor
        from hospital.models import HospitalBloodRequest
        
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
            
            # 2. Lives saved = completed hospital blood requests (each request represents a patient helped)
            completed_requests_count = HospitalBloodRequest.objects.filter(
                status='delivered'
            ).count()
            
            # 3. Total donation centers
            donation_centers_count = DonationCenter.objects.count()
            
            # 4. Total blood units available (non-expired)
            total_units_available = StockUnit.objects.filter(
                unit__gt=0,
                expiry_date__gte=dt_date.today()
            ).aggregate(
                total=Sum('unit')
            )['total'] or 0
            
            # 5. Hospitals served
            hospitals_served = HospitalBloodRequest.objects.values('hospital').distinct().count()
            
            # Create default stats structure for template
            stats = [
                {
                    'stat_name': 'Active Donors',
                    'stat_value': active_donors_count,
                    'icon_class': 'fas fa-users'
                },
                {
                    'stat_name': 'Hospitals Served',
                    'stat_value': hospitals_served,
                    'icon_class': 'fas fa-hospital'
                },
                {
                    'stat_name': 'Donation Centers',
                    'stat_value': donation_centers_count,
                    'icon_class': 'fas fa-building'
                },
                {
                    'stat_name': 'Units Available',
                    'stat_value': total_units_available,
                    'icon_class': 'fas fa-tint'
                },
                {
                    'stat_name': 'Lives Impacted',
                    'stat_value': completed_requests_count,
                    'icon_class': 'fas fa-heart'
                },
            ]
        
        # ==========================================
        # TESTIMONIALS - DEDUPLICATED WITH AVATAR PRIORITY
        # ==========================================
        
        # Get all active featured testimonials
        all_testimonials = Testimonial.objects.filter(
            is_active=True,
            is_featured=True
        )
        
        # Deduplicate by name (case-insensitive) and prioritize those with avatars
        unique_testimonials = {}
        for testimonial in all_testimonials:
            # Normalize name for comparison (lowercase, strip whitespace)
            name_key = testimonial.name.lower().strip()
            
            # If we haven't seen this name before, add it
            if name_key not in unique_testimonials:
                unique_testimonials[name_key] = testimonial
            else:
                # We've seen this name before - check if current one has avatar
                existing = unique_testimonials[name_key]
                
                # If existing has no avatar but new one does, replace it
                if not existing.avatar and testimonial.avatar:
                    unique_testimonials[name_key] = testimonial
                # If both have avatars, keep the one with higher rating or newer
                elif existing.avatar and testimonial.avatar:
                    # Keep the one with higher rating
                    if testimonial.rating > existing.rating:
                        unique_testimonials[name_key] = testimonial
                    # If ratings are equal, keep the newer one
                    elif testimonial.rating == existing.rating and testimonial.created_at > existing.created_at:
                        unique_testimonials[name_key] = testimonial
        
        # Convert back to list and shuffle for variety
        testimonials = list(unique_testimonials.values())
        
        # Shuffle to mix them up
        import random
        random.shuffle(testimonials)
        
        # Limit to maximum 6 testimonials
        testimonials = testimonials[:6]
        
        # If no testimonials at all, provide empty list
        if not testimonials:
            testimonials = []
        
        # ==========================================
        # RENDER HOME PAGE
        # ==========================================
        context = {
            'user_is_authenticated': request.user.is_authenticated,
            'stats': stats,
            'testimonials': testimonials,
            # Legacy context for backward compatibility
            'active_donors_count': stats[0]['stat_value'] if isinstance(stats, list) else None,
            'hospitals_served': stats[1]['stat_value'] if isinstance(stats, list) else None,
            'donation_centers_count': stats[2]['stat_value'] if isinstance(stats, list) else None,
            'total_units_available': stats[3]['stat_value'] if isinstance(stats, list) else None,
            'lives_impacted': stats[4]['stat_value'] if isinstance(stats, list) else None,
        }
        
        return render(request, 'shared/index.html', context)
        
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
            'upcoming_drives': blood_drives,
            'past_drives': past_drives,
        }
        return render(request, 'blood/blood_drives_list.html', context)
    except Exception as e:
        logger.error(f"Error in blood_drives_list: {e}", exc_info=True)
        return redirect('home')

def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('contact_success')
    else:
        form = ContactForm()
    return render(request, 'shared/contact_us.html', {'form': form})

def contact_success(request):
    return render(request, 'shared/contact_success.html')

def learn_more_view(request):
    return render(request, 'shared/learn_more.html')

def about_us_view(request):
    donor_count = Donor.objects.count()
    lives_saved = BloodDonate.objects.filter(status='completed').count()

    try:
        from hospital.models import Hospital
        hospital_count = Hospital.objects.count()
    except ImportError:
        hospital_count = 125

    last_30_days = timezone.now().date() - timedelta(days=30)
    recent_donations = BloodDonate.objects.filter(date__gte=last_30_days).count()
    pending_donations = BloodDonate.objects.filter(status='pending').count()

    # 🔥 Determine image source
    profile_image = request.session.get('profile_image')
    profile_image_url = request.session.get('profile_image_url')

    if profile_image_url:
        image_url = profile_image_url
        use_static = False
    elif profile_image:
        image_url = profile_image
        use_static = True
    else:
        image_url = "images/allan_kibet.jpg"  # default static image
        use_static = True

    context = {
        'page_title': 'About Us - BloodConnect',
        'current_year': timezone.now().year,
        'creator': {
            'name': 'Allan Kibet',
            'role': 'Founder & Lead Developer',
            'bio': 'Passionate developer on a mission to save lives through technology.',
            'location': 'Nairobi, Kenya',
            'email': 'allankibet1820@gmail.com',
            'phone': '+254 781 024 762',
            'quote': "I built BloodConnect to unite donors, phlebotomists, and hospitals in one life-saving network — with a special dedication to my ever-crashing laptop that somehow survived the journey. ",
            'image_url': image_url,
            'use_static': use_static,
        },
        'impact': [
            {'number': f'{donor_count:,}+', 'label': 'Active Donors'},
            {'number': f'{lives_saved:,}+', 'label': 'Lives Saved'},
            {'number': f'{hospital_count:,}+', 'label': 'Partner Hospitals'},
        ],
        'stats': {
            'donors': donor_count,
            'lives_saved': lives_saved,
            'hospitals': hospital_count,
            'recent_donations': recent_donations,
            'pending_donations': pending_donations,
            'total_donations': BloodDonate.objects.count(),
        }
    }

    return render(request, 'shared/about_us.html', context)

@staff_member_required
def update_profile_image(request):
    if request.method == 'POST':
        # FILE UPLOAD
        if request.FILES.get('profile_image'):
            image = request.FILES['profile_image']
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/jpg']
            if image.content_type not in allowed_types:
                messages.error(request, 'Invalid file type.')
                return redirect('about-us')
            if image.size > 5 * 1024 * 1024:
                messages.error(request, 'File too large (max 5MB).')
                return redirect('about-us')

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ext = os.path.splitext(image.name)[1]
            filename = f'allan_kibet_{timestamp}{ext}'

            static_dir = os.path.join(settings.BASE_DIR, 'static', 'images')
            os.makedirs(static_dir, exist_ok=True)

            filepath = os.path.join(static_dir, filename)
            with open(filepath, 'wb+') as destination:
                for chunk in image.chunks():
                    destination.write(chunk)

            request.session['profile_image'] = f'images/{filename}'
            request.session.pop('profile_image_url', None)
            messages.success(request, 'Profile image updated.')

        # URL UPLOAD
        elif request.POST.get('image_url'):
            url = request.POST['image_url']
            if not url.startswith(('http://', 'https://')):
                messages.error(request, 'Enter a valid URL.')
                return redirect('about-us')
            request.session['profile_image_url'] = url
            request.session.pop('profile_image', None)
            messages.success(request, 'Profile image URL updated.')

        # REMOVE IMAGE
        elif request.POST.get('remove_image'):
            request.session.pop('profile_image', None)
            request.session.pop('profile_image_url', None)
            messages.success(request, 'Profile image removed.')

    return redirect('about-us')

# ==========================================
# AUTHENTICATION VIEWS 
# ==========================================


@ratelimit(key='ip', rate='3/m', method='POST', block=True)
def fake_admin_login_view(request):
    """
    Honeypot login - captures attacker information
    Real admin is at a different, secret URL
    Rate limited to 3 attempts per minute per IP
    """
    # Get the rate limit info to check if they've been blocked
    was_limited = getattr(request, 'limited', False)
    
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        ip = request.META.get('REMOTE_ADDR', 'Unknown')
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        
        # Check if they've been rate limited
        if was_limited:
            logger.warning(f"🔴 RATE LIMITED HONEYPOT ATTEMPT - IP: {ip}, Username: {username}")
            messages.error(request, "Too many attempts. Please try again later.")
            return render(request, 'blood/fake_admin_login.html')
        
        # Log the attack attempt with more details
        logger.warning(f"🔴 HONEYPOT ATTACK DETECTED - IP: {ip}, Username: {username}, Password: {password}, UA: {user_agent}")
        
        # Save to database (if you created the model)
        try:
            HoneypotAttempt.objects.create(
                ip=ip,
                username=username,
                password=password,
                user_agent=user_agent
            )
            logger.info(f"✅ Honeypot attempt saved to database for IP: {ip}")
        except Exception as e:
            logger.error(f"Failed to save honeypot attempt to database: {e}")
        
        # Send email alert for suspicious attempts
        suspicious_keywords = ['admin', 'root', 'administrator', 'super', 'manager', 'sysadmin']
        if any(keyword in username.lower() for keyword in suspicious_keywords):
            try:
                send_mail(
                    '⚠️ Admin Honeypot Triggered',
                    f'🚨 SUSPICIOUS ADMIN LOGIN ATTEMPT DETECTED 🚨\n\n'
                    f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                    f'IP Address: {ip}\n'
                    f'Username tried: {username}\n'
                    f'Password used: {password}\n'
                    f'User Agent: {user_agent}\n\n'
                    f'This attempt has been logged and rate limited.',
                    'noreply@bloodconnect.com',
                    ['allankibet1820@gmail.com'],
                    fail_silently=True,
                )
                logger.info(f"📧 Email alert sent for suspicious attempt from IP: {ip}")
            except Exception as e:
                logger.error(f"Failed to send email alert: {e}")
        
        # Track attempt count for this IP in session
        if 'honeypot_attempts' not in request.session:
            request.session['honeypot_attempts'] = {}
        
        ip_attempts = request.session['honeypot_attempts'].get(ip, 0)
        request.session['honeypot_attempts'][ip] = ip_attempts + 1
        request.session.modified = True
        
        # Progressive delay - gets longer with more attempts
        base_delay = 3
        if ip_attempts > 5:
            delay = base_delay * 3  # 9 seconds after 5 attempts
        elif ip_attempts > 3:
            delay = base_delay * 2  # 6 seconds after 3 attempts
        else:
            delay = base_delay  # 3 seconds normally
        
        time.sleep(delay)
        
        # Always show error message
        messages.error(request, "Invalid username or password.")
        
        # Add a funny message for repeat offenders
        if ip_attempts > 10:
            messages.warning(request, "You really like trying to hack us, don't you? 😉")
        elif ip_attempts > 5:
            messages.warning(request, "Persistent, aren't you? Still not working though. 🤔")
        
    # Add attempt count to context for the template
    attempt_count = request.session.get('honeypot_attempts', {}).get(
        request.META.get('REMOTE_ADDR', 'Unknown'), 0
    )
    
    return render(request, 'blood/fake_admin_login.html', {
        'attempt_count': attempt_count,
        'show_counter': attempt_count > 2,  # Show counter after 2 attempts
    })
@login_required
@user_passes_test(lambda u: u.is_superuser)
def honeypot_monitor_view(request):
    """View to monitor honeypot attempts (superusers only)"""
    from django.db.models import Count
    from datetime import timedelta
    from django.utils import timezone
    
    # Get last 24 hours
    last_24h = timezone.now() - timedelta(hours=24)
    
    # Get statistics
    total_attempts = HoneypotAttempt.objects.count()
    attempts_24h = HoneypotAttempt.objects.filter(timestamp__gte=last_24h).count()
    
    # Top attacking IPs
    top_ips = HoneypotAttempt.objects.values('ip').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Most common usernames tried
    top_usernames = HoneypotAttempt.objects.values('username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Recent attempts
    recent_attempts = HoneypotAttempt.objects.all()[:50]
    
    context = {
        'total_attempts': total_attempts,
        'attempts_24h': attempts_24h,
        'top_ips': top_ips,
        'top_usernames': top_usernames,
        'recent_attempts': recent_attempts,
    }
    return render(request, 'blood/honeypot_monitor.html', context)

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
        # Safety check for duplicate profiles
        duplicate_profiles = check_for_duplicate_profiles(user)
        
        if len(duplicate_profiles) > 1:
            logger.error(f"User {user.username} has MULTIPLE profiles: {duplicate_profiles}")
            messages.error(
                request, 
                "Your account has multiple profiles. Please contact support immediately."
            )
            return redirect('home')
        
        # Admin/staff check
        if user.is_staff or user.is_superuser:
            logger.info(f"Admin user {user.username} redirected to admin-dashboard")
            return redirect('admin-dashboard')
        
        # Get user's profile type and redirect
        profile_type, profile = get_user_profile_type(user)
        
        if profile_type == 'donor':
            return redirect('donor:donor-dashboard')
        elif profile_type == 'phlebotomist':
            # Check if phlebotomist needs approval
            if hasattr(profile, 'is_approved') and not profile.is_approved:
                return redirect('phlebotomist:phlebotomist-pending-approval')
            return redirect('phlebotomist:phlebotomist-dashboard')
        elif profile_type == 'hospital_staff':
            return redirect('hospital:dashboard')
        elif profile_type == 'lab_technologist':
            return redirect('lab_technologist:dashboard')
        elif profile_type == 'blood_bank_technician':
            return redirect('blood_bank_technician:dashboard')
        else:
            # No profile found
            logger.warning(f"User {user.username} has no profile")
            messages.info(request, "Please complete your registration to get started.")
            return redirect('role_selection')
            
    except Exception as e:
        logger.error(f"Error in afterlogin_view: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred during login. Please try again.")
        return redirect('home')

# ==========================================
# ADMIN DASHBOARD (ANALYTICS ONLY - KEEP THIS)
# ==========================================

@login_required(login_url='adminlogin')
@user_passes_test(lambda u: u.is_staff, login_url='adminlogin')
def admin_dashboard_view(request):
    """
    Admin analytics dashboard - ONLY view kept for data visualization
    All CRUD operations are handled by Django Admin
    """
    # Aggregate total units by blood group and center
    all_stocks = blood_models.Stock.objects.select_related('center').values(
        'bloodgroup', 'center__name'
    ).annotate(total_units=models.Sum('unit'))

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
    LOW_STOCK_THRESHOLD_PERCENT = 25
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

    # Stats for cards
    stats = [
        {
            "label": "Total Donors", 
            "value": donor_models.Donor.objects.count(), 
            "icon": "fas fa-user-plus", 
            "color": "#007bff"
        },
        {
            "label": "Total Phlebotomists", 
            "value": phlebotomist_models.Phlebotomist.objects.count(), 
            "icon": "fas fa-user-nurse", 
            "color": "#28a745"
        },
        {
            "label": "Total Hospitals", 
            "value": hospital_models.Hospital.objects.count(), 
            "icon": "fas fa-hospital", 
            "color": "#dc3545"
        },
        {
            "label": "Total Blood Requests", 
            "value": hospital_models.HospitalBloodRequest.objects.count(), 
            "icon": "fas fa-clipboard-list", 
            "color": "#ffc107"
        },
        {
            "label": "Pending Requests", 
            "value": hospital_models.HospitalBloodRequest.objects.filter(status='pending').count(), 
            "icon": "fas fa-clock", 
            "color": "#fd7e14"
        },
        {
            "label": "Approved Requests", 
            "value": hospital_models.HospitalBloodRequest.objects.filter(status='approved').count(), 
            "icon": "fas fa-check-circle", 
            "color": "#17a2b8"
        },
        {
            "label": "Dispatched Requests", 
            "value": hospital_models.HospitalBloodRequest.objects.filter(status='dispatched').count(), 
            "icon": "fas fa-truck", 
            "color": "#6610f2"
        },
    ]

    # Recent activity (last 10 donations)
    recent_donations = BloodDonate.objects.select_related(
        'donor__user', 'donation_center'
    ).order_by('-date')[:10]

    # Recent blood requests
    recent_requests = HospitalBloodRequest.objects.select_related(
        'hospital'
    ).order_by('-created_at')[:10]

    context = {
        "center_stock_map": center_stock_map_norm,
        "blood_data": blood_data,
        "totalbloodunit": totalbloodunit,
        "low_stock_alerts": low_stock_alerts,
        "stats": stats,
        "recent_donations": recent_donations,
        "recent_requests": recent_requests,
        "now": now(),
    }

    return render(request, "blood/admin_dashboard.html", context)

# ==========================================
# REPORT GENERATION (Keep these - Django Admin doesn't do reports)
# ==========================================

@login_required(login_url='adminlogin')
def admin_donation_report(request):
    """Generate CSV report of all donations"""
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
        'Phlebotomist',
        'Appointment Date & Time',
        'Appointment Status',
        'Donation Status',
        'Activity Log'
    ])

    donations = BloodDonate.objects.select_related(
        'donor__user', 'donation_center'
    ).prefetch_related('appointments__phlebotomist__user')

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
        if d.approved_by_phlebotomist:
            activity_log.append(f"App(Phlebotomist) {d.approved_at_phlebotomist.strftime('%b %d, %H:%M')}")
        if d.completed_by_phlebotomist:
            activity_log.append(f"Cmp(Phlebotomist) {d.completed_at_phlebotomist.strftime('%b %d, %H:%M')}")
        if d.status == 'cancelled':
            activity_log.append(f"Cn({d.cancelled_by or '?'}) {d.cancelled_at.strftime('%b %d, %H:%M') if d.cancelled_at else ''}")
        if d.status == 'rejected':
            activity_log.append(f"Rjct({d.rejected_by or '?'}) {d.rejected_at.strftime('%b %d, %H:%M') if d.rejected_at else ''}")
        activity_log_text = " | ".join(activity_log) if activity_log else "No activity yet"

        if not d.appointments.exists():
            writer.writerow([
                f"{donor_name} ({donor_age})" if donor_age else donor_name,
                donor_age,
                contact,
                blood_group,
                unit,
                donation_center,
                "N/A",
                "N/A",
                "N/A",
                main_status,
                activity_log_text
            ])
        else:
            for appt in d.appointments.all():
                phlebotomist_name = appt.phlebotomist.user.get_full_name() if appt.phlebotomist else "N/A"
                appt_date = appt.date.strftime("%Y-%m-%d %H:%M") if appt.date else "N/A"
                appt_status = appt.status
                writer.writerow([
                    f"{donor_name} ({donor_age})" if donor_age else donor_name,
                    donor_age,
                    contact,
                    blood_group,
                    unit,
                    donation_center,
                    phlebotomist_name,
                    appt_date,
                    appt_status,
                    main_status,
                    activity_log_text
                ])

    return response

def blood_request_stock_transactions(request, blood_request_id):
    """View stock transactions for a specific blood request"""
    transactions = StockTransaction.objects.filter(
        blood_request_id=blood_request_id
    ).select_related('stockunit').order_by('-transaction_at')
    
    context = {
        'transactions': transactions,
    }
    return render(request, 'blood/stock_transactions.html', context)

# ==========================================
# AJAX VALIDATION ENDPOINTS (Keep these)
# ==========================================

def check_username_ajax(request):
    """System-wide username validation"""
    username = request.GET.get('username', '').strip()
    
    if not username:
        return JsonResponse({
            'exists': False,
            'message': 'Username cannot be empty',
        })
    
    user_exists = User.objects.filter(username__iexact=username).exists()
    
    if user_exists:
        suggestions = generate_username_suggestions(username)
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
    """Alternative endpoint for username validation"""
    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'is_taken': False})
    is_taken = User.objects.filter(username__iexact=username).exists()
    return JsonResponse({'is_taken': is_taken})

def check_email_ajax(request):
    """System-wide email validation"""
    email = request.GET.get('email', '').strip()
    
    if not email:
        return JsonResponse({
            'valid': False,
            'message': 'Email cannot be empty',
        })
    
    # Basic email format validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return JsonResponse({
            'valid': False,
            'message': 'Please enter a valid email address',
        })
    
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
    """System-wide national ID validation"""
    national_id = request.GET.get('national_id', '').strip()
    
    if not national_id:
        return JsonResponse({
            'valid': False,
            'message': 'National ID cannot be empty',
        })
    
    if not national_id.isdigit() or len(national_id) != 8:
        return JsonResponse({
            'valid': False,
            'message': 'National ID must be exactly 8 digits',
        })
    
    donor_exists = Donor.objects.filter(national_id=national_id).exists()
    
    if donor_exists:
        return JsonResponse({
            'valid': False,
            'message': 'This National ID is already registered',
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'National ID is available',
    })

def check_mobile_ajax(request):
    """System-wide mobile number validation"""
    mobile = request.GET.get('mobile', '').strip()
    
    if not mobile:
        return JsonResponse({
            'valid': False,
            'message': 'Mobile number cannot be empty',
        })
    
    # Validate Kenyan mobile format (+254...)
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
    
    donor_exists = Donor.objects.filter(mobile=normalized).exists()
    phlebotomist_exists = Phlebotomist.objects.filter(phone=normalized).exists()
    
    if donor_exists or phlebotomist_exists:
        return JsonResponse({
            'valid': False,
            'message': 'This mobile number is already registered',
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Mobile number is available',
    })

def ajax_check_phlebotomist_registration(request):
    """Check if phlebotomist registration number is available."""
    registration_number = request.GET.get('registration_number', '').strip().upper()
    
    if not registration_number:
        return JsonResponse({
            'valid': False,
            'message': 'Registration number is required'
        })
    
    if not re.match(r'^[A-Z0-9]{5,30}$', registration_number):
        return JsonResponse({
            'valid': False,
            'message': 'Registration number must be 5-30 uppercase letters and numbers only'
        })
    
    exists = Phlebotomist.objects.filter(license_number=registration_number).exists()
    
    if exists:
        return JsonResponse({
            'valid': False,
            'message': f"Registration number '{registration_number}' is already in use"
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Registration number is available'
    })

def ajax_check_phlebotomist_phone(request):
    """Check if phlebotomist phone number is available."""
    phone = request.GET.get('phone', '').strip()
    
    if not phone:
        return JsonResponse({
            'valid': False,
            'message': 'Phone number is required'
        })
    
    phone_clean = phone.replace(' ', '').replace('-', '')
    
    if not re.match(r'^\+?1?\d{9,15}$', phone_clean):
        return JsonResponse({
            'valid': False,
            'message': 'Invalid format. Use +999999999 (9-15 digits)'
        })
    
    exists = Phlebotomist.objects.filter(phone=phone_clean).exists()
    
    if exists:
        return JsonResponse({
            'valid': False,
            'message': 'This phone number is already registered'
        })
    
    return JsonResponse({
        'valid': True,
        'message': 'Phone number is available'
    })

# ==========================================
# LOCATION & NEARBY CENTERS (Keep these)
# ==========================================

@login_required
def nearby_centers_view(request):
    """View for finding nearby donation centers."""
    latitude, longitude = None, None

    # Try pulling location from user profile
    user = request.user
    if hasattr(user, 'donor') and user.donor.latitude and user.donor.longitude:
        latitude = user.donor.latitude
        longitude = user.donor.longitude
        logger.info(f"[Donor] Using location from donor profile: {latitude}, {longitude}")
    elif hasattr(user, 'patient') and user.patient.latitude and user.patient.longitude:
        latitude = user.patient.latitude
        longitude = user.patient.longitude
        logger.info(f"[Patient] Using location from patient profile: {latitude}, {longitude}")

    # If no location in profile, check for location in session
    if latitude is None or longitude is None:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        if lat and lng:
            try:
                latitude = float(lat)
                longitude = float(lng)
                logger.info(f"[Logged-in User] Using provided coordinates: lat={latitude}, lng={longitude}")
            except ValueError:
                messages.error(request, "Invalid location coordinates provided.")
                return render(request, 'shared/nearby_centers.html', {})

    if latitude is None or longitude is None:
        messages.warning(
            request, 
            "Your location is not set. Please update your profile with your location."
        )
        if hasattr(user, 'donor'):
            return redirect('donor:donor-edit-profile')
        elif hasattr(user, 'patient'):
            return redirect('patient:edit-profile')
        else:
            return redirect('home')

    centers = find_nearby_centers(latitude, longitude)
    logger.info(f"Found {len(centers)} centers near lat={latitude}, lng={longitude}")

    return render(request, 'donor/nearby_centers.html', {
        'nearby_centers': centers,
        'user_latitude': latitude,
        'user_longitude': longitude,
        'user_location_name': getattr(user, 'donor', getattr(user, 'patient', None)).location_name if hasattr(user, 'donor') or hasattr(user, 'patient') else None,
    })

@login_required
def save_user_location(request):
    """Save user location from browser geolocation - ONLY saves precise location details, NOT county"""
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

        # Default values
        location_details = {
            'precise_location': None,
            'town': None,
            'road': None,
            'neighbourhood': None,
            'display_name': None
        }

        # Reverse geocoding to get detailed location info
        try:
            url = f'https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}'
            response = requests.get(url, headers={'User-Agent': 'BloodConnect/1.0'})
            if response.status_code == 200:
                data = response.json()
                address = data.get('address', {})
                
                # Build a comprehensive location string
                parts = []
                
                # Get road/street
                if address.get('road'):
                    parts.append(address['road'])
                    location_details['road'] = address['road']
                
                # Get neighbourhood/suburb
                if address.get('neighbourhood'):
                    parts.append(address['neighbourhood'])
                    location_details['neighbourhood'] = address['neighbourhood']
                elif address.get('suburb'):
                    parts.append(address['suburb'])
                    location_details['neighbourhood'] = address['suburb']
                
                # Get town/city/village
                town = (address.get('city') or 
                       address.get('town') or 
                       address.get('village'))
                if town:
                    parts.append(town)
                    location_details['town'] = town
                
                # Create a user-friendly location string
                location_details['precise_location'] = ', '.join(parts) if parts else None
                location_details['display_name'] = data.get('display_name')
                
        except Exception as e:
            logger.error(f"Geocoding error: {e}")

        user = request.user

        if hasattr(user, 'donor'):
            # Save coordinates
            user.donor.latitude = lat
            user.donor.longitude = lon
            
            # Save location_name with precise details (BUT NOT COUNTY)
            if location_details['precise_location']:
                user.donor.location_name = location_details['precise_location']
            elif location_details['display_name']:
                # Truncate display_name if too long
                user.donor.location_name = location_details['display_name'][:100]
            else:
                user.donor.location_name = f"Location at {lat:.4f}, {lon:.4f}"
            
            user.donor.save()
            
            # Prepare response with ALL location details for the frontend
            response_data = {
                'status': 'success',
                'message': 'Precise location updated',
                'location_name': user.donor.location_name,
                'location_details': {
                    'precise_location': location_details['precise_location'],
                    'town': location_details['town'],
                    'road': location_details['road'],
                    'neighbourhood': location_details['neighbourhood'],
                    'display_name': location_details['display_name']
                }
            }
            
            messages.success(request, f"Your precise location has been updated!")
            return JsonResponse(response_data)
            
        elif hasattr(user, 'patient'):
            # Similar for patient
            user.patient.latitude = lat
            user.patient.longitude = lon
            user.patient.location_name = location_details['precise_location'] or location_details['display_name']
            user.patient.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Precise location updated',
                'location_name': user.patient.location_name
            })
            
        elif hasattr(user, 'phlebotomist') and user.phlebotomist.center:
            # For phlebotomists, store in session
            request.session['temp_latitude'] = lat
            request.session['temp_longitude'] = lon
            request.session['temp_location_name'] = location_details['precise_location'] or location_details['display_name']
            
            return JsonResponse({
                'status': 'success',
                'message': 'Temporary location set',
                'location_name': request.session['temp_location_name']
            })
            
        else:
            return JsonResponse({'status': 'error', 'message': 'Unable to save location for this user type'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """
    Password change view for all authenticated users.
    Used by donors, phlebotomists, hospital staff, etc.
    """
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
        elif hasattr(self.request.user, 'phlebotomist'):
            context['user_type'] = 'phlebotomist'
        elif hasattr(self.request.user, 'hospitaluser'):
            context['user_type'] = 'hospital'
        elif self.request.user.is_staff:
            context['user_type'] = 'admin'
        else:
            context['user_type'] = 'user'
        
        return context

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

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
# blood/views.py - Keep these custom admin views

@login_required(login_url='adminlogin')
def admin_contacts_view(request):
    """
    Custom view to display contact form submissions.
    Django Admin can show contacts but this provides a cleaner interface.
    """
    # Mark unread as read
    Contact.objects.filter(is_read=False).update(is_read=True)
    
    # Get all contacts
    contact_list = Contact.objects.all().order_by('-created_at')
    
    # Paginate
    paginator = Paginator(contact_list, 10)
    page_number = request.GET.get('page')
    contacts = paginator.get_page(page_number)

    return render(request, 'blood/admin_contacts.html', {'contacts': contacts})


@login_required(login_url='adminlogin')
def admin_post_notification(request):
    """
    Custom view to send bulk notifications to users.
    Django Admin cannot send notifications to multiple users at once.
    """
    if request.method == 'POST':
        title = request.POST.get('title')
        message_text = request.POST.get('message')
        recipient_ids = request.POST.getlist('recipient_id')
        selected_groups = request.POST.getlist('recipient_group')
         
        if not title or not message_text:
            messages.error(request, "Please provide both title and message.")
            return redirect('admin-post-notification')

        if not selected_groups and not recipient_ids:
            messages.error(request, "Please select at least one group or individual recipient.")
            return redirect('admin-post-notification')

        try:
            notifications = []

            # Map group names to models
            group_model_map = {
                'hospital': Hospital,
                'hospital_user': HospitalUser,
                'donor': Donor,
                'phlebotomist': Phlebotomist
            }

            for group in selected_groups:
                model = group_model_map.get(group)
                if model:
                    content_type = ContentType.objects.get_for_model(model)
                    recipients = model.objects.all()
                    for recipient in recipients:
                        if group == 'hospital_user':
                            recipient_obj = recipient.user
                            recipient_content_type = ContentType.objects.get_for_model(recipient.user.__class__)
                            recipient_object_id = recipient.user.id
                        else:
                            recipient_obj = recipient
                            recipient_content_type = content_type
                            recipient_object_id = recipient.id
                            
                        notifications.append(Notification(
                            title=title,
                            message=message_text,
                            recipient_content_type=recipient_content_type,
                            recipient_object_id=recipient_object_id,
                            sender_content_type=ContentType.objects.get_for_model(request.user.__class__),
                            sender_object_id=request.user.id,
                        ))

            # Add notifications for individually selected users
            if recipient_ids:
                user_id_map = {}

                # Check all user types
                hospital_users = HospitalUser.objects.filter(user__id__in=recipient_ids).select_related('user')
                for hu in hospital_users:
                    user_id_map[hu.user.id] = (
                        ContentType.objects.get_for_model(hu.user.__class__),
                        hu.user.id
                    )

                donors = Donor.objects.filter(user__id__in=recipient_ids).select_related('user')
                for donor in donors:
                    user_id_map[donor.user.id] = (
                        ContentType.objects.get_for_model(donor.user.__class__),
                        donor.user.id
                    )

                phlebotomists = Phlebotomist.objects.filter(user__id__in=recipient_ids).select_related('user')
                for phlebotomist in phlebotomists:
                    user_id_map[phlebotomist.user.id] = (
                        ContentType.objects.get_for_model(phlebotomist.user.__class__),
                        phlebotomist.user.id
                    )

                for user_id in recipient_ids:
                    if int(user_id) in user_id_map:
                        content_type, obj_id = user_id_map[int(user_id)]
                        notifications.append(Notification(
                            title=title,
                            message=message_text,
                            recipient_content_type=content_type,
                            recipient_object_id=obj_id,
                            sender_content_type=ContentType.objects.get_for_model(request.user.__class__),
                            sender_object_id=request.user.id,
                        ))

            if not notifications:
                messages.error(request, "No valid recipients found to send notification.")
                return redirect('admin-post-notification')

            Notification.objects.bulk_create(notifications)
            messages.success(request, f"{len(notifications)} notifications posted successfully!")

        except Exception as e:
            messages.error(request, f"Error posting notifications: {str(e)}")
        return redirect('admin-post-notification')

    # GET request - show the form
    hospitals = Hospital.objects.all()
    hospital_users = HospitalUser.objects.select_related('user', 'hospital').all()
    donors = Donor.objects.select_related('user').all()
    phlebotomists = Phlebotomist.objects.select_related('user').all()

    context = {
        'hospitals': hospitals,
        'hospital_users': hospital_users,
        'donors': donors,
        'phlebotomists': phlebotomists,
    }
    return render(request, 'blood/admin_post_notification.html', context)



@login_required
def submit_review(request):
    """Multi-step review process with optional survey"""
    user = request.user
    step = int(request.GET.get('step', 1))
    
    # Get or create review
    try:
        review = UserReview.objects.get(user=user)
        is_new = False
    except UserReview.DoesNotExist:
        review = None
        is_new = True
    
    # Handle form submissions
    if request.method == 'POST':
        if step == 1:
            # Save rating
            rating = request.POST.get('rating')
            if rating:
                if review:
                    review.rating = rating
                    review.save()
                else:
                    review = UserReview.objects.create(
                        user=user,
                        rating=rating,
                        comment=''
                    )
            return JsonResponse({'status': 'success', 'next_step': 2})
            
        elif step == 2:
            # Save comment
            comment = request.POST.get('comment')
            if review and comment:
                review.comment = comment
                review.save()
            return JsonResponse({'status': 'success', 'next_step': 3})
            
        elif step == 3:
            # User chose whether to take survey
            take_survey = request.POST.get('take_survey')
            if take_survey == 'yes':
                return JsonResponse({'status': 'success', 'next_step': 4})
            else:
                # No survey - redirect to dashboard
                messages.success(request, "Thank you for your feedback! 🎉")
                return JsonResponse({'status': 'success', 'redirect': '/donor/donor-dashboard'})
            
        elif step == 4:
            # Save survey
            survey_form = ReviewSurveyForm(request.POST)
            if survey_form.is_valid() and review:
                # Check if survey exists
                try:
                    survey = ReviewSurvey.objects.get(review=review)
                    # Update existing survey
                    for field, value in survey_form.cleaned_data.items():
                        setattr(survey, field, value)
                    survey.save()
                except ReviewSurvey.DoesNotExist:
                    # Create new survey
                    survey = survey_form.save(commit=False)
                    survey.review = review
                    survey.save()
                
                messages.success(request, "Thank you for your detailed feedback! 🎉")
                return JsonResponse({'status': 'success', 'redirect': '/donor/donor-dashboard'})
    
    # GET request - show forms
    if step == 1:
        # Create rating form
        from django import forms
        class RatingForm(forms.Form):
            rating = forms.ChoiceField(
                choices=[(i, f"{i} Star{'s' if i > 1 else ''}") for i in range(1, 6)],
                widget=forms.Select(attrs={'class': 'form-control rating-select'}),
                initial=review.rating if review else 3
            )
        form = RatingForm()
        survey_form = None
        show_survey_choice = False
        
    elif step == 2:
        # Create comment form
        from django import forms
        class CommentForm(forms.Form):
            comment = forms.CharField(
                widget=forms.Textarea(attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Share your experience...'
                }),
                initial=review.comment if review else ''
            )
        form = CommentForm()
        survey_form = None
        show_survey_choice = False
        
    elif step == 3:
        # Ask if they want to take survey
        form = None
        survey_form = None
        show_survey_choice = True
        
    elif step == 4:
        # Survey step
        form = None
        show_survey_choice = False
        try:
            survey = ReviewSurvey.objects.get(review=review) if review else None
        except ReviewSurvey.DoesNotExist:
            survey = None
        
        survey_form = ReviewSurveyForm(instance=survey)
    
    context = {
        'step': step,
        'has_review': review is not None,
        'review': review,
        'form': form,
        'survey_form': survey_form,
        'show_survey_choice': show_survey_choice,
        'initial_rating': review.rating if review else 3,
        'initial_comment': review.comment if review else '',
    }
    
    return render(request, 'shared/submit_review.html', context)

@staff_member_required
def admin_reviews_dashboard(request):
    """Admin sees ALL reviews here"""
    # Mark all as read when admin views them
    UserReview.objects.filter(is_read=False).update(is_read=True)
    
    # Get all reviews with stats
    all_reviews = UserReview.objects.all().select_related('user')
    
    # Stats
    total_reviews = all_reviews.count()
    avg_rating = all_reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    five_star_count = all_reviews.filter(rating=5).count()
    
    # Pagination
    paginator = Paginator(all_reviews, 20)
    page = request.GET.get('page')
    reviews = paginator.get_page(page)
    
    # Get featured testimonials
    featured = Testimonial.objects.filter(is_active=True)[:10]
    
    context = {
        'reviews': reviews,
        'total_reviews': total_reviews,
        'avg_rating': round(avg_rating, 1),
        'five_star_count': five_star_count,
        'featured': featured,
    }
    return render(request, 'blood/admin_reviews.html', context)


@staff_member_required
def feature_review_as_testimonial(request, review_id):
    """Admin picks a review to feature as homepage testimonial"""
    review = get_object_or_404(UserReview, id=review_id)
    
    # Check if already featured
    if hasattr(review, 'featured_testimonial'):
        messages.warning(request, "This review is already featured!")
        return redirect('admin_reviews_dashboard')
    
    # Get user's profile picture based on their profile type
    avatar = None
    user = review.user
    
    # Check different profile types for avatar
    if hasattr(user, 'donor') and user.donor.profile_pic:
        avatar = user.donor.profile_pic
    elif hasattr(user, 'phlebotomist') and user.phlebotomist.profile_pic:
        avatar = user.phlebotomist.profile_pic
    elif hasattr(user, 'hospitaluser') and user.hospitaluser.profile_pic:
        avatar = user.hospitaluser.profile_pic
    
    # Create testimonial from review
    testimonial = Testimonial.objects.create(
        # If you have source_review field:
        # source_review=review,
        name=review.user.get_full_name() or review.user.username,
        role="Donor" if hasattr(review.user, 'donor') else "User",
        testimonial=review.comment,
        rating=review.rating,
        avatar=avatar,  # <-- THIS ADDS THE PROFILE PICTURE
        is_active=True,
        is_featured=True
    )
    
    messages.success(request, f"Review by {testimonial.name} is now featured on homepage!")
    return redirect('admin_reviews_dashboard')
@login_required
@require_POST
def save_review_step(request):
    """AJAX endpoint to save review data progressively"""
    user = request.user
    step = request.POST.get('step')
    
    try:
        review = UserReview.objects.get(user=user)
    except UserReview.DoesNotExist:
        review = None
    
    if step == '1':
        # Save rating
        rating = request.POST.get('rating')
        if rating:
            if review:
                review.rating = rating
                review.save()
            else:
                review = UserReview.objects.create(
                    user=user,
                    rating=rating,
                    comment=''
                )
        return JsonResponse({'status': 'success'})
    
    elif step == '2':
        # Save comment
        comment = request.POST.get('comment')
        if review and comment:
            review.comment = comment
            review.save()
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'error'}, status=400)

from blood.utils.barcode_utils import generate_batch_barcodes
from .models import BloodBagBarcode
def generate_initial_barcodes(request):
    """Simple one-time view to generate initial barcodes"""
    # Security: Only allow if no barcodes exist
    if BloodBagBarcode.objects.exists():
        return HttpResponse("Barcodes already exist! No action taken.")
    
    count = 50
    barcodes = []
    
    for i in range(count):
        # Generate unique barcode
        date_part = datetime.now().strftime('%Y%m%d')
        random_part = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        barcode_str = f"BLD-{date_part}-{random_part}"
        
        # Ensure uniqueness
        while BloodBagBarcode.objects.filter(barcode=barcode_str).exists():
            random_part = ''.join([str(random.randint(0, 9)) for _ in range(5)])
            barcode_str = f"BLD-{date_part}-{random_part}"
        
        # Create barcode
        barcode = BloodBagBarcode.objects.create(
            barcode=barcode_str,
            bag_type='single',
            volume_ml=450,
            anticoagulant='cpd',
            status='available',
            created_by=None
        )
        barcodes.append(barcode)
    
    return HttpResponse(f"✅ Generated {len(barcodes)} initial barcodes! You can now use the admin actions.")