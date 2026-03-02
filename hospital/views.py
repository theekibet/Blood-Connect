from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.http import JsonResponse
from .models import Hospital, HospitalUser, HospitalBloodRequest
from .forms import (
    HospitalRegistrationForm, HospitalUserSignupForm, 
    HospitalLoginForm, HospitalBloodRequestForm, HospitalProfileForm
)
from blood.models import DonationCenter, StockUnit
from utils.models import Notification
from django.contrib.contenttypes.models import ContentType
import logging

logger = logging.getLogger(__name__)


def hospital_register(request):
    """Register a new hospital"""
    if request.method == 'POST':
        form = HospitalRegistrationForm(request.POST)
        if form.is_valid():
            hospital = form.save(commit=False)
            hospital.verified = False  # Requires admin verification
            hospital.save()
            
            messages.success(
                request, 
                "Hospital registered successfully! An administrator will verify your registration."
            )
            return redirect('hospital:login')
    else:
        form = HospitalRegistrationForm()
    
    return render(request, 'hospital/register.html', {'form': form})


def hospital_user_signup(request):
    """Create a hospital user account"""
    if request.method == 'POST':
        form = HospitalUserSignupForm(request.POST)
        if form.is_valid():
            hospital_user = form.save()
            
            messages.success(
                request, 
                f"Account created for {hospital_user.user.get_full_name()}. You can now login."
            )
            return redirect('hospital:login')
    else:
        form = HospitalUserSignupForm()
    
    return render(request, 'hospital/signup.html', {'form': form})


def hospital_login_view(request):
    """Hospital user login"""
    if request.method == 'POST':
        form = HospitalLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                try:
                    hospital_user = HospitalUser.objects.get(user=user, is_active=True)
                    
                    if not hospital_user.hospital.verified:
                        messages.error(request, "Your hospital is not yet verified by admin.")
                        return render(request, 'hospital/login.html', {'form': form})
                    
                    login(request, user)
                    request.session['hospital_id'] = str(hospital_user.hospital.id)
                    request.session['hospital_user_role'] = hospital_user.role
                    
                    messages.success(request, f"Welcome back, {user.get_full_name()}!")
                    
                    # Redirect based on role
                    if hospital_user.role == 'admin':
                        return redirect('hospital:dashboard_admin')
                    else:
                        return redirect('hospital:dashboard')
                    
                except HospitalUser.DoesNotExist:
                    messages.error(request, "You don't have hospital access privileges.")
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = HospitalLoginForm()
    
    return render(request, 'hospital/login.html', {'form': form})


@login_required
def hospital_logout_view(request):
    """Hospital user logout"""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('hospital:login')


@login_required
def hospital_dashboard(request):
    """Main dashboard for hospital users (lab techs)"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    # Get recent requests
    recent_requests = HospitalBloodRequest.objects.filter(
        hospital=hospital
    ).order_by('-created_at')[:10]
    
    # Get request statistics
    total_requests = HospitalBloodRequest.objects.filter(hospital=hospital).count()
    pending_requests = HospitalBloodRequest.objects.filter(
        hospital=hospital, status='pending'
    ).count()
    approved_requests = HospitalBloodRequest.objects.filter(
        hospital=hospital, status='approved'
    ).count()
    dispatched_requests = HospitalBloodRequest.objects.filter(
        hospital=hospital, status='dispatched'
    ).count()
    delivered_requests = HospitalBloodRequest.objects.filter(
        hospital=hospital, status='delivered'
    ).count()
    
    # Blood group breakdown
    blood_group_stats = HospitalBloodRequest.objects.filter(
        hospital=hospital
    ).values('blood_group').annotate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        fulfilled=Count('id', filter=Q(status='delivered'))
    ).order_by('blood_group')
    
    # Get serving centre stock info if available
    centre_stock = None
    if hospital.serving_centre:
        centre_stock = StockUnit.objects.filter(
            center=hospital.serving_centre,
            safety_status='safe',
            is_quarantined=False,
            unit__gt=0,
            expiry_date__gte=timezone.now().date()
        ).values('bloodgroup').annotate(
            total_units=Sum('unit')
        ).order_by('bloodgroup')
    
    # ===== GENERATE PERSONALIZED GREETING =====
    try:
        from blood.utils.greetings import get_hospital_greeting
        
        greeting_data = get_hospital_greeting(
            hospital_user=hospital_user,
            pending_requests=pending_requests,
            approved_requests=approved_requests,
            dispatched_requests=dispatched_requests,
            total_requests=total_requests
        )
    except ImportError:
        # Fallback greeting
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        else:
            time_of_day = "evening"
            
        name = hospital_user.user.get_full_name().split()[0] if hospital_user.user.get_full_name() else hospital_user.user.username
        
        greeting_data = {
            'greeting': f"Good {time_of_day}, {name}! 🏥",
            'context_message': f"Managing blood requests at {hospital.name}",
            'user_type': 'hospital',
            'icon': '🏥',
            'meta_items': [
                {'icon': 'fas fa-building', 'text': hospital.name},
                {'icon': 'fas fa-clock', 'text': f'{pending_requests} pending', 'color': 'text-warning' if pending_requests > 0 else ''},
                {'icon': 'fas fa-check-circle', 'text': f'{approved_requests} approved', 'color': 'text-success'},
            ]
        }
    
    context = {
        'hospital': hospital,
        'hospital_user': hospital_user,
        'recent_requests': recent_requests,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'dispatched_requests': dispatched_requests,
        'delivered_requests': delivered_requests,
        'blood_group_stats': blood_group_stats,
        'centre_stock': centre_stock,
        'greeting_data': greeting_data,  # Add greeting data to context
    }
    
    return render(request, 'hospital/dashboard.html', context)


@login_required
def hospital_dashboard_admin(request):
    """Admin dashboard for hospital administrators"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True, role='admin')
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "You don't have admin access.")
        return redirect('hospital:dashboard')
    
    # Get all hospital users
    hospital_users = HospitalUser.objects.filter(hospital=hospital)
    
    # Get all blood requests
    all_requests = HospitalBloodRequest.objects.filter(hospital=hospital).order_by('-created_at')
    
    # Statistics
    stats = {
        'total_users': hospital_users.count(),
        'total_requests': all_requests.count(),
        'pending_requests': all_requests.filter(status='pending').count(),
        'approved_requests': all_requests.filter(status='approved').count(),
        'dispatched_requests': all_requests.filter(status='dispatched').count(),
        'delivered_requests': all_requests.filter(status='delivered').count(),
        'rejected_requests': all_requests.filter(status='rejected').count(),
    }
    
    # ===== GENERATE PERSONALIZED GREETING FOR ADMIN =====
    try:
        from blood.utils.greetings import get_hospital_admin_greeting
        
        greeting_data = get_hospital_admin_greeting(
            hospital_user=hospital_user,
            stats=stats,
            user_count=hospital_users.count()
        )
    except ImportError:
        # Fallback greeting
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        else:
            time_of_day = "evening"
            
        name = hospital_user.user.get_full_name().split()[0] if hospital_user.user.get_full_name() else hospital_user.user.username
        
        greeting_data = {
            'greeting': f"Good {time_of_day}, {name}! 👨‍💼",
            'context_message': f"Administrator dashboard for {hospital.name}",
            'user_type': 'hospital_admin',
            'icon': '👨‍💼',
            'meta_items': [
                {'icon': 'fas fa-building', 'text': hospital.name},
                {'icon': 'fas fa-users', 'text': f'{hospital_users.count()} users'},
                {'icon': 'fas fa-clock', 'text': f"{stats['pending_requests']} pending", 'color': 'text-warning' if stats['pending_requests'] > 0 else ''},
            ]
        }
    
    context = {
        'hospital': hospital,
        'hospital_user': hospital_user,
        'hospital_users': hospital_users,
        'all_requests': all_requests,
        'stats': stats,
        'greeting_data': greeting_data,  # Add greeting data to context
    }
    
    return render(request, 'hospital/dashboard_admin.html', context)

@login_required
def create_blood_request(request):
    """Create a new blood request"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    if not hospital.verified:
        messages.error(request, "Your hospital is not verified. Cannot create requests.")
        return redirect('hospital:dashboard')
    
    if request.method == 'POST':
        form = HospitalBloodRequestForm(request.POST)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.hospital = hospital
            blood_request.requested_by = hospital_user
            blood_request.status = 'pending'
            
            # ⭐ ADD THIS LINE - This is the fix!
            blood_request.assigned_centre = hospital.serving_centre
            
            blood_request.save()
            
            # Notify blood bank techs
            try:
                from blood_bank_technician.models import BloodBankTechProfile
                blood_bank_techs = BloodBankTechProfile.objects.filter(
                    center=hospital.serving_centre,
                    is_active=True
                )
                
                for tech in blood_bank_techs:
                    Notification.objects.create(
                        title="New Hospital Blood Request",
                        message=(
                            f"New blood request from {hospital.name}: "
                            f"{blood_request.units_requested} units of {blood_request.blood_group} "
                            f"for patient {blood_request.patient_full_name}. Urgency: {blood_request.urgency}"
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(tech.user),
                        recipient_object_id=tech.user.id,
                        sender_content_type=ContentType.objects.get_for_model(request.user),
                        sender_object_id=request.user.id,
                    )
            except Exception as e:
                logger.error(f"Failed to notify blood bank techs: {e}")
            
            messages.success(
                request, 
                f"Blood request #{blood_request.request_number} created successfully!"
            )
            return redirect('hospital:request_detail', request_id=blood_request.id)
    else:
        form = HospitalBloodRequestForm()
    
    context = {
        'form': form,
        'hospital': hospital,
    }
    return render(request, 'hospital/create_request.html', context)



@login_required
def request_list(request):
    """List all blood requests for the hospital"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '')
    
    requests = HospitalBloodRequest.objects.filter(hospital=hospital)
    
    if status_filter != 'all':
        requests = requests.filter(status=status_filter)
    
    if search_query:
        requests = requests.filter(
            Q(request_number__icontains=search_query) |
            Q(patient_first_name__icontains=search_query) |
            Q(patient_last_name__icontains=search_query) |
            Q(doctor_name__icontains=search_query)
        )
    
    requests = requests.order_by('-created_at')
    
    # Statistics for filter tabs
    stats = {
        'all': HospitalBloodRequest.objects.filter(hospital=hospital).count(),
        'pending': HospitalBloodRequest.objects.filter(hospital=hospital, status='pending').count(),
        'approved': HospitalBloodRequest.objects.filter(hospital=hospital, status='approved').count(),
        'dispatched': HospitalBloodRequest.objects.filter(hospital=hospital, status='dispatched').count(),
        'delivered': HospitalBloodRequest.objects.filter(hospital=hospital, status='delivered').count(),
        'rejected': HospitalBloodRequest.objects.filter(hospital=hospital, status='rejected').count(),
    }
    
    context = {
        'requests': requests,
        'stats': stats,
        'current_status': status_filter,
        'search_query': search_query,
    }
    return render(request, 'hospital/request_list.html', context)


@login_required
def request_detail(request, request_id):
    """View details of a specific blood request"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        hospital=hospital
    )
    
    # Get related dispatches if any
    dispatches = blood_request.dispatches.all() if hasattr(blood_request, 'dispatches') else []
    
    context = {
        'request': blood_request,
        'dispatches': dispatches,
    }
    return render(request, 'hospital/request_detail.html', context)


@login_required
def cancel_request(request, request_id):
    """Cancel a pending blood request"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        hospital=hospital,
        status='pending'
    )
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        blood_request.status = 'cancelled'
        blood_request.rejection_reason = reason
        blood_request.save()
        
        messages.success(request, f"Request #{blood_request.request_number} cancelled.")
        return redirect('hospital:request_list')
    
    return render(request, 'hospital/cancel_request.html', {'request': blood_request})


@login_required
def confirm_delivery(request, request_id):
    """Confirm that blood has been delivered to the hospital"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        hospital=hospital,
        status='dispatched'
    )
    
    if request.method == 'POST':
        blood_request.status = 'delivered'
        blood_request.save()
        
        messages.success(request, f"Blood delivered for request #{blood_request.request_number}")
        return redirect('hospital:request_detail', request_id=blood_request.id)
    
    return render(request, 'hospital/confirm_delivery.html', {'request': blood_request})


@login_required
def hospital_profile(request):
    """View and edit hospital profile"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Hospital user not found.")
        return redirect('hospital:login')
    
    if request.method == 'POST':
        form = HospitalProfileForm(request.POST, instance=hospital)
        if form.is_valid():
            form.save()
            messages.success(request, "Hospital profile updated successfully.")
            return redirect('hospital:profile')
    else:
        form = HospitalProfileForm(instance=hospital)
    
    context = {
        'form': form,
        'hospital': hospital,
        'hospital_user': hospital_user,
    }
    return render(request, 'hospital/profile.html', context)


@login_required
def user_management(request):
    """Manage hospital users (admin only)"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True, role='admin')
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Admin access required.")
        return redirect('hospital:dashboard')
    
    users = HospitalUser.objects.filter(hospital=hospital)
    
    context = {
        'users': users,
        'hospital': hospital,
    }
    return render(request, 'hospital/user_management.html', context)


@login_required
def deactivate_user(request, user_id):
    """Deactivate a hospital user (admin only)"""
    try:
        hospital_user = HospitalUser.objects.get(user=request.user, is_active=True, role='admin')
        hospital = hospital_user.hospital
    except HospitalUser.DoesNotExist:
        messages.error(request, "Admin access required.")
        return redirect('hospital:dashboard')
    
    target_user = get_object_or_404(HospitalUser, id=user_id, hospital=hospital)
    
    if target_user == hospital_user:
        messages.error(request, "You cannot deactivate yourself.")
        return redirect('hospital:user_management')
    
    if request.method == 'POST':
        target_user.is_active = False
        target_user.save()
        messages.success(request, f"User {target_user.user.get_full_name()} deactivated.")
        return redirect('hospital:user_management')
    
    return render(request, 'hospital/deactivate_user.html', {'target_user': target_user})
