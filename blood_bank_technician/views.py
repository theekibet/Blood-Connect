from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import timedelta
from .models import BloodBankTechProfile
from patient.models import BloodRequest
from lab_technologist.models import BloodTest
from django.http import JsonResponse
from blood.models import StockUnit, StockTransaction
from django.core.exceptions import PermissionDenied
from .models import BloodBankTechProfile
from .forms import BloodBankTechProfileForm
from django.conf import settings
import os
from blood.utils.stock_utils import (
    deduct_stock_fifo, 
    check_stock_availability, 
    get_available_stock,
    get_pending_verification_stock,
    get_unsafe_stock,
    get_stock_summary
)
from .forms import BloodBankTechSignupForm
import logging
logger = logging.getLogger(__name__)
# ======================
# SIGNUP VIEW
# ======================
def signup_view(request):
    """Blood Bank Technician signup view"""
    
    if request.method == 'POST':
        form = BloodBankTechSignupForm(request.POST)
        if form.is_valid():
            try:
                profile = form.save()
                messages.success(
                    request, 
                    'Registration successful! Your account is pending admin approval. '
                    'You will be notified once your account is activated.'
                )
                return redirect('blood_bank_technician:login')
            except Exception as e:
                messages.error(request, f'Registration failed: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BloodBankTechSignupForm()
    
    return render(request, 'blood_bank_technician/signup.html', {'form': form})

# ======================
# LOGIN VIEW
# ======================
def login_view(request):
    """Blood Bank Technician login view"""
    
    # If user is already logged in and is a blood bank tech, redirect to dashboard
    if request.user.is_authenticated:
        if hasattr(request.user, 'blood_bank_tech_profile'):
            return redirect('blood_bank_technician:dashboard')
        else:
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user has blood bank tech profile
            try:
                blood_bank_tech_profile = BloodBankTechProfile.objects.get(user=user)
                # TEMPORARILY DISABLED: Admin approval not required
                login(request, user)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                return redirect('blood_bank_technician:dashboard')
            except BloodBankTechProfile.DoesNotExist:
                messages.error(request, "You don't have Blood Bank Technician access. Please check your credentials.")
        else:
            messages.error(request, "Invalid username or password.")
    
    return render(request, 'blood_bank_technician/login.html')
@login_required
def blood_bank_tech_profile(request):
    """View logged-in user's blood bank technician profile"""
    try:
        profile = request.user.blood_bank_tech_profile
        return redirect('blood_bank_technician:blood_bank_tech_profile_detail', pk=profile.pk)
    except BloodBankTechProfile.DoesNotExist:
        messages.error(request, "Blood Bank Technician profile not found.")
        return redirect('blood_bank_technician:dashboard')

@login_required
def blood_bank_tech_profile_detail(request, pk):
    """View blood bank technician profile details"""
    profile = get_object_or_404(BloodBankTechProfile, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and profile.user != request.user:
        raise PermissionDenied("You don't have permission to view this profile.")
    
    context = {
        'profile': profile,
        'profile_type': 'Blood Bank Technician'
    }
    return render(request, 'blood_bank_technician/profile_detail.html', context)

@login_required
def blood_bank_tech_profile_edit(request, pk):
    """Edit blood bank technician profile"""
    profile = get_object_or_404(BloodBankTechProfile, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and profile.user != request.user:
        raise PermissionDenied("You don't have permission to edit this profile.")
    
    if request.method == 'POST':
        print("\n" + "="*60)
        print("🔍 BLOOD BANK DEBUG: Form submission detected")
        print("="*60)
        print(f"FILES received: {dict(request.FILES)}")
        print(f"POST data: {request.POST}")
        print(f"Delete picture: {request.POST.get('delete_picture')}")
        print(f"Remove picture: {request.POST.get('remove_picture')}")
        print("="*60 + "\n")
        
        # Check if user wants to delete the picture
        if request.POST.get('delete_picture') == 'true' or request.POST.get('remove_picture') == 'on':
            if profile.profile_pic:
                try:
                    # Delete the file from storage
                    if os.path.isfile(profile.profile_pic.path):
                        os.remove(profile.profile_pic.path)
                        print(f"✅ Deleted picture: {profile.profile_pic.path}")
                    
                    # Clear the field
                    profile.profile_pic = None
                    profile.save()
                    messages.success(request, 'Profile picture removed successfully.')
                except Exception as e:
                    print(f"❌ Error deleting picture: {e}")
                    messages.error(request, f'Error removing picture: {str(e)}')
                
                return redirect('blood_bank_technician:blood_bank_tech_profile_edit', pk=profile.pk)
        
        form = BloodBankTechProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            try:
                saved_profile = form.save()
                if saved_profile.profile_pic:
                    messages.success(request, 'Profile updated successfully with new picture!')
                else:
                    messages.success(request, 'Profile updated successfully!')
                return redirect('blood_bank_technician:blood_bank_tech_profile_detail', pk=profile.pk)
            except Exception as e:
                print(f"❌ Error saving profile: {e}")
                messages.error(request, f'Error saving profile: {str(e)}')
        else:
            print("❌ Form errors:", form.errors)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BloodBankTechProfileForm(instance=profile)
    
    context = {
        'form': form,
        'profile': profile,
    }
    return render(request, 'blood_bank_technician/profile_edit.html', context)

# ======================
# LOGOUT VIEW
# ======================
@login_required
def logout_view(request):
    """Blood Bank Technician logout view"""
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('blood_bank_technician:login')

# ======================
# DASHBOARD VIEW - UPDATED WITH REAL STOCK DATA
# ======================
@login_required
def dashboard(request):
    """Blood Bank Technician dashboard - Shows real-time stock stats from StockUnit"""
    
    # Ensure user has a profile
    profile, created = BloodBankTechProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'employee_id': f"BBT-{request.user.id}",
            'phone': '',
            'is_active': True
        }
    )
    
    center = profile.center
    
    if not center:
        messages.warning(request, "You are not assigned to any donation center. Please contact admin.")
        return render(request, 'blood_bank_technician/dashboard.html', {'profile': profile})
    
    today = timezone.now().date()
    
    # ===== SAFE STOCK (Available for issuance) =====
    safe_stock = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today
    )
    
    total_safe_units = safe_stock.count()
    total_safe_volume = safe_stock.aggregate(total=Sum('unit'))['total'] or 0
    
    # ===== PENDING VERIFICATION STOCK (Awaiting lab test) =====
    pending_stock = StockUnit.objects.filter(
        center=center,
        safety_status='pending',
        unit__gt=0,
        expiry_date__gte=today
    )
    
    total_pending_units = pending_stock.count()
    total_pending_volume = pending_stock.aggregate(total=Sum('unit'))['total'] or 0
    
    # ===== UNSAFE STOCK (Quarantined) =====
    unsafe_stock = StockUnit.objects.filter(
        center=center,
        safety_status='unsafe'
    )
    
    total_unsafe_units = unsafe_stock.count()
    total_unsafe_volume = unsafe_stock.aggregate(total=Sum('unit'))['total'] or 0
    
    # ===== EXPIRING SOON (Next 7 days) =====
    expiring_soon = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=7)
    )
    
    total_expiring_units = expiring_soon.count()
    total_expiring_volume = expiring_soon.aggregate(total=Sum('unit'))['total'] or 0
    
    # ===== INVENTORY BY BLOOD TYPE =====
    inventory_by_type = {}
    for blood_type in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
        # Safe stock by blood type
        safe = StockUnit.objects.filter(
            center=center,
            bloodgroup=blood_type,
            safety_status='safe',
            is_quarantined=False,
            unit__gt=0,
            expiry_date__gte=today
        ).aggregate(
            units=Sum('unit'),
            batches=Count('id')
        )
        
        # Pending stock by blood type
        pending = StockUnit.objects.filter(
            center=center,
            bloodgroup=blood_type,
            safety_status='pending',
            unit__gt=0,
            expiry_date__gte=today
        ).aggregate(
            units=Sum('unit'),
            batches=Count('id')
        )
        
        if safe['units'] or pending['units']:
            inventory_by_type[blood_type] = {
                'safe_units': safe['units'] or 0,
                'safe_batches': safe['batches'] or 0,
                'pending_units': pending['units'] or 0,
                'pending_batches': pending['batches'] or 0,
            }
    
    # ===== PENDING BLOOD REQUESTS =====
    pending_requests = BloodRequest.objects.filter(
        status='pending',
        donation_center=center
    ).count()
    
    # ===== RECENT TRANSACTIONS =====
    recent_transactions = StockTransaction.objects.filter(
        stockunit__center=center
    ).select_related(
        'stockunit',
        'user',
        'blood_request__request_by_patient__user'
    ).order_by('-transaction_at')[:10]
    
    context = {
        'profile': profile,
        'center': center,
        'total_safe_units': total_safe_units,
        'total_safe_volume': total_safe_volume,
        'total_pending_units': total_pending_units,
        'total_pending_volume': total_pending_volume,
        'total_unsafe_units': total_unsafe_units,
        'total_unsafe_volume': total_unsafe_volume,
        'total_expiring_units': total_expiring_units,
        'total_expiring_volume': total_expiring_volume,
        'pending_requests': pending_requests,
        'inventory_by_type': inventory_by_type,
        'recent_transactions': recent_transactions,
        'now': timezone.now(),
    }
    
    return render(request, 'blood_bank_technician/dashboard.html', context)

# ======================
# INVENTORY VIEW
# ======================
@login_required
def inventory(request):
    """View safe blood inventory using StockUnit"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get filter parameters
    blood_type = request.GET.get('blood_type', '')
    sort_by = request.GET.get('sort', 'expiry_date')
    today = timezone.now().date()
    
    # Base queryset - only safe, non-quarantined, non-expired stock
    safe_stock = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today
    ).select_related('blood_donation__donor__user')
    
    # Apply blood type filter
    if blood_type:
        safe_stock = safe_stock.filter(bloodgroup=blood_type)
    
    # Apply sorting
    if sort_by == 'expiry_date':
        safe_stock = safe_stock.order_by('expiry_date')
    elif sort_by == 'bloodgroup':
        safe_stock = safe_stock.order_by('bloodgroup', 'expiry_date')
    elif sort_by == 'added_on':
        safe_stock = safe_stock.order_by('-added_on')
    elif sort_by == 'volume':
        safe_stock = safe_stock.order_by('-unit')
    
    # Group by blood type for summary cards
    by_blood_type = {}
    total_volume = 0
    total_batches = 0
    
    for unit in safe_stock:
        bg = unit.bloodgroup
        if bg not in by_blood_type:
            by_blood_type[bg] = {
                'total_units': 0,
                'total_ml': 0,
                'batches': []
            }
        by_blood_type[bg]['total_units'] += 1
        by_blood_type[bg]['total_ml'] += unit.unit
        by_blood_type[bg]['batches'].append(unit)
        total_volume += unit.unit
        total_batches += 1
    
    # Calculate summary statistics
    total_safe_units = safe_stock.count()
    total_safe_volume = safe_stock.aggregate(total=Sum('unit'))['total'] or 0
    
    # Get expiring soon count
    expiring_soon = safe_stock.filter(
        expiry_date__lte=today + timedelta(days=7)
    ).count()
    
    context = {
        'safe_stock': safe_stock,
        'by_blood_type': by_blood_type,
        'blood_type': blood_type,
        'sort_by': sort_by,
        'total_batches': total_batches,
        'total_volume': total_volume,
        'total_safe_units': total_safe_units,
        'total_safe_volume': total_safe_volume,
        'expiring_soon': expiring_soon,
        'today': today,
        'center': center,
        'now': timezone.now(),
    }
    
    return render(request, 'blood_bank_technician/inventory.html', context)
# ======================
# PENDING VERIFICATION VIEW
# ======================
@login_required
def pending_verification(request):
    """View blood units awaiting lab verification"""
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    today = timezone.now().date()  
    
    pending_units = StockUnit.objects.filter(
        center=center,
        safety_status='pending',
        unit__gt=0,
        expiry_date__gte=today  # Use today variable
    ).select_related('blood_donation__donor__user')
    
    context = {
        'pending_units': pending_units,
        'total_pending': pending_units.count(),
        'total_ml': pending_units.aggregate(total=Sum('unit'))['total'] or 0,
        'center': center,
        'today': today,  
    }
    return render(request, 'blood_bank_technician/pending_verification.html', context)
# ======================
# UNSAFE BLOOD VIEW
# ======================
@login_required
def unsafe_blood(request):
    """View quarantined/unsafe blood units"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    blood_type = request.GET.get('blood_type', '')
    
    unsafe_units = get_unsafe_stock(center, blood_type if blood_type else None)
    
    # Group by unsafe reason
    by_reason = {}
    for unit in unsafe_units:
        reason = unit.unsafe_reason or 'other'
        if reason not in by_reason:
            by_reason[reason] = {
                'count': 0,
                'total_ml': 0,
                'units': []
            }
        by_reason[reason]['count'] += 1
        by_reason[reason]['total_ml'] += unit.unit
        by_reason[reason]['units'].append(unit)
    
    context = {
        'unsafe_units': unsafe_units,
        'by_reason': by_reason,
        'blood_type': blood_type,
        'total_unsafe': unsafe_units.count(),
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/unsafe_blood.html', context)

from patient.models import BloodRequest as PatientBloodRequest
from donor.models import DonorBloodRequest
# ======================
# PENDING REQUESTS VIEW (Combined)
# ======================
@login_required
def pending_requests(request):
    """View pending blood requests from both patients and donors"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get patient requests
    patient_requests = PatientBloodRequest.objects.filter(
        status='pending',
        donation_center=center
    ).select_related(
        'request_by_patient__user',
        'donation_center'
    ).order_by('-created_at')
    
    # Get donor requests
    donor_requests = DonorBloodRequest.objects.filter(
        status='pending',
        donation_center=center
    ).select_related(
        'request_by_donor__user',
        'donation_center'
    ).order_by('-created_at')
    
    # Combine and annotate requests
    combined_requests = []
    
    # Process patient requests
    for req in patient_requests:
        availability = check_stock_availability(center, req.bloodgroup, req.unit)
        combined_requests.append({
            'id': req.id,
            'type': 'patient',
            'object': req,
            'patient_name': req.get_full_name(),
            'bloodgroup': req.bloodgroup,
            'unit': req.unit,
            'created_at': req.created_at,
            'donation_center': req.donation_center,
            'has_inventory': availability.get('can_fulfill', False),
            'availability': availability,
            'requester': req.request_by_patient.user.get_full_name() if req.request_by_patient else 'Unknown',
            'contact': req.contact_number,
        })
    
    # Process donor requests
    for req in donor_requests:
        availability = check_stock_availability(center, req.bloodgroup, req.unit)
        patient_name = f"{req.patient_first_name} {req.patient_last_name}"
        combined_requests.append({
            'id': req.id,
            'type': 'donor',
            'object': req,
            'patient_name': patient_name,
            'bloodgroup': req.bloodgroup,
            'unit': req.unit,
            'created_at': req.created_at,
            'donation_center': req.donation_center,
            'has_inventory': availability.get('can_fulfill', False),
            'availability': availability,
            'requester': f"Donor: {req.request_by_donor.user.get_full_name()}",
            'contact': req.contact_number,
        })
    
    # Sort by created_at (newest first)
    combined_requests.sort(key=lambda x: x['created_at'], reverse=True)
    
    context = {
        'combined_requests': combined_requests,
        'total_pending': len(combined_requests),
        'patient_count': len(patient_requests),
        'donor_count': len(donor_requests),
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/pending_requests.html', context)


# ======================
# APPROVE REQUEST VIEW (Handles both types)
# ======================
@login_required
def approve_request(request, request_type, request_id):
    """Approve a blood request (patient or donor) and deduct stock using FIFO"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    today = timezone.now().date()
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the appropriate request object
    if request_type == 'patient':
        blood_request = get_object_or_404(
            PatientBloodRequest, 
            id=request_id, 
            status='pending',
            donation_center=center
        )
        requester_name = blood_request.get_full_name()
    elif request_type == 'donor':
        blood_request = get_object_or_404(
            DonorBloodRequest, 
            id=request_id, 
            status='pending',
            donation_center=center
        )
        requester_name = f"{blood_request.patient_first_name} {blood_request.patient_last_name}"
    else:
        messages.error(request, "Invalid request type.")
        return redirect('blood_bank_technician:pending_requests')
    
    # Check availability again
    availability = check_stock_availability(
        center, 
        blood_request.bloodgroup, 
        blood_request.unit
    )
    
    if not availability['can_fulfill']:
        messages.error(
            request, 
            f"Insufficient safe stock. Available: {availability['safe_stock']}ml, "
            f"Required: {blood_request.unit}ml"
        )
        return redirect('blood_bank_technician:pending_requests')
    
    if request.method == 'POST':
        try:
            # Deduct stock using FIFO
            success, result = deduct_stock_fifo(
                center=center,
                bloodgroup=blood_request.bloodgroup,
                required_units=blood_request.unit,
                deducted_by_user=request.user,
                deducted_by_role='blood_bank_tech',
                blood_request=blood_request  # Pass the blood request to link transactions
            )
            
            if not success:
                messages.error(request, f"Stock deduction failed: {result}")
                return redirect('blood_bank_technician:pending_requests')
            
            # Update request status
            blood_request.status = 'approved'
            blood_request.approved_by = profile
            blood_request.approved_at = timezone.now()
            
            # Mark stock as deducted if field exists
            if hasattr(blood_request, 'stock_deducted'):
                blood_request.stock_deducted = True
            
            blood_request.save()
            
            # Create notification based on request type
            from blood.models import Notification
            from django.contrib.contenttypes.models import ContentType
            
            if request_type == 'patient':
                recipient = blood_request.request_by_patient
                notification_title = "Blood Request Approved"
                notification_message = (
                    f"Your blood request for {blood_request.unit}ml of {blood_request.bloodgroup} "
                    f"has been approved. Please contact {center.name} to arrange pickup."
                )
            else:  # donor
                recipient = blood_request.request_by_donor
                notification_title = "Blood Request Approved"
                notification_message = (
                    f"The blood request for {blood_request.patient_first_name} {blood_request.patient_last_name} "
                    f"({blood_request.unit}ml of {blood_request.bloodgroup}) has been approved. "
                    f"Please contact {center.name} to arrange pickup."
                )
            
            if recipient:
                Notification.objects.create(
                    title=notification_title,
                    message=notification_message,
                    recipient_content_type=ContentType.objects.get_for_model(recipient),
                    recipient_object_id=recipient.id,
                    sender_content_type=ContentType.objects.get_for_model(profile.user),
                    sender_object_id=profile.user.id,
                )
            
            messages.success(
                request, 
                f"Request approved. {blood_request.unit}ml of {blood_request.bloodgroup} deducted from inventory."
            )
            
            return redirect('blood_bank_technician:approved_requests')
            
        except Exception as e:
            messages.error(request, f"Error approving request: {str(e)}")
            logger.error(f"Error approving {request_type} request {request_id}: {e}", exc_info=True)
            return redirect('blood_bank_technician:pending_requests')
    
    # GET request - show confirmation page with available batches
    available_units = StockUnit.objects.filter(
        center=center,
        bloodgroup=blood_request.bloodgroup,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today
    ).order_by('expiry_date')
    
    total_available = available_units.aggregate(total=Sum('unit'))['total'] or 0
    
    context = {
        'request': blood_request,
        'request_type': request_type,
        'requester_name': requester_name,
        'availability': availability,
        'available_units': available_units,
        'total_available': total_available,
        'center': center,
        'today': today,
    }
    
    return render(request, 'blood_bank_technician/approve_request.html', context)
# ======================
# REJECT REQUEST VIEW (Handles both types)
# ======================
@login_required
def reject_request(request, request_type, request_id):
    """Reject a blood request with reason"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the appropriate request object
    if request_type == 'patient':
        blood_request = get_object_or_404(
            PatientBloodRequest, 
            id=request_id, 
            status='pending',
            donation_center=center
        )
    elif request_type == 'donor':
        blood_request = get_object_or_404(
            DonorBloodRequest, 
            id=request_id, 
            status='pending',
            donation_center=center
        )
    else:
        messages.error(request, "Invalid request type.")
        return redirect('blood_bank_technician:pending_requests')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        
        if not reason:
            messages.error(request, 'Please provide a reason for rejection.')
            return render(request, 'blood_bank_technician/reject_request.html', {
                'request': blood_request,
                'request_type': request_type,
            })
        
        blood_request.status = 'rejected'
        blood_request.rejection_reason = reason
        blood_request.reviewed_by = profile
        blood_request.reviewed_at = timezone.now()
        blood_request.save()
        
        # Create notification based on request type
        from blood.models import Notification
        from django.contrib.contenttypes.models import ContentType
        
        if request_type == 'patient':
            recipient = blood_request.request_by_patient
            notification_title = "Blood Request Rejected"
            notification_message = (
                f"Your blood request for {blood_request.unit}ml of {blood_request.bloodgroup} "
                f"has been rejected. Reason: {reason}"
            )
        else:  # donor
            recipient = blood_request.request_by_donor
            notification_title = "Blood Request Rejected"
            notification_message = (
                f"The blood request for {blood_request.patient_first_name} {blood_request.patient_last_name} "
                f"({blood_request.unit}ml of {blood_request.bloodgroup}) has been rejected. "
                f"Reason: {reason}"
            )
        
        if recipient:
            Notification.objects.create(
                title=notification_title,
                message=notification_message,
                recipient_content_type=ContentType.objects.get_for_model(recipient),
                recipient_object_id=recipient.id,
                sender_content_type=ContentType.objects.get_for_model(profile.user),
                sender_object_id=profile.user.id,
            )
        
        messages.warning(request, f'Request rejected. Reason: {reason}')
        return redirect('blood_bank_technician:pending_requests')
    
    return render(request, 'blood_bank_technician/reject_request.html', {
        'request': blood_request,
        'request_type': request_type,
    })


# ======================
# APPROVED REQUESTS VIEW (Combined)
# ======================
@login_required
def approved_requests(request):
    """View approved requests ready for dispatch"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get patient approved requests
    patient_requests = PatientBloodRequest.objects.filter(
        Q(status='approved') | Q(status='dispatched'),
        donation_center=center
    ).select_related(
        'request_by_patient__user',
        'donation_center',
        'approved_by__user',
    ).order_by('-approved_at')
    
    # Get donor approved requests
    donor_requests = DonorBloodRequest.objects.filter(
        Q(status='approved') | Q(status='dispatched'),
        donation_center=center
    ).select_related(
        'request_by_donor__user',
        'donation_center',
        'approved_by__user',
    ).order_by('-approved_at')
    
    # Combine and annotate requests
    combined_requests = []
    
    for req in patient_requests:
        combined_requests.append({
            'id': req.id,
            'type': 'patient',
            'object': req,
            'patient_name': req.get_full_name(),
            'bloodgroup': req.bloodgroup,
            'unit': req.unit,
            'status': req.status,
            'approved_at': req.approved_at,
            'approved_by': req.approved_by,
            'donation_center': req.donation_center,
            'dispatches': getattr(req, 'dispatches_list', []),
        })
    
    for req in donor_requests:
        patient_name = f"{req.patient_first_name} {req.patient_last_name}"
        combined_requests.append({
            'id': req.id,
            'type': 'donor',
            'object': req,
            'patient_name': patient_name,
            'bloodgroup': req.bloodgroup,
            'unit': req.unit,
            'status': req.status,
            'approved_at': req.approved_at,
            'approved_by': req.approved_by,
            'donation_center': req.donation_center,
            'dispatches': getattr(req, 'dispatches_list', []),
        })
    
    # Sort by approved_at (newest first)
    combined_requests.sort(key=lambda x: x['approved_at'] or timezone.datetime.min, reverse=True)
    
    context = {
        'combined_requests': combined_requests,
        'approved_count': sum(1 for r in combined_requests if r['status'] == 'approved'),
        'dispatched_count': sum(1 for r in combined_requests if r['status'] == 'dispatched'),
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/approved_requests.html', context)


# ======================
# DISPATCH REQUEST VIEW (Handles both types)
# ======================
@login_required
def dispatch_request(request, request_type, request_id):
    """Record dispatch of approved blood request"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the appropriate request object and fetch its transactions
    if request_type == 'patient':
        blood_request = get_object_or_404(
            PatientBloodRequest, 
            id=request_id, 
            status='approved',
            donation_center=center
        )
        # For patient requests, filter by blood_request field
        deducted_units = StockTransaction.objects.filter(
            blood_request=blood_request,
            transaction_type='deduction'
        ).select_related('stockunit', 'stockunit__blood_donation__donor__user')
        
    elif request_type == 'donor':
        blood_request = get_object_or_404(
            DonorBloodRequest, 
            id=request_id, 
            status='approved',
            donation_center=center
        )
        # For donor requests, filter by donor_blood_request field
        deducted_units = StockTransaction.objects.filter(
            donor_blood_request=blood_request,
            transaction_type='deduction'
        ).select_related('stockunit', 'stockunit__blood_donation__donor__user')
        
    else:
        messages.error(request, "Invalid request type.")
        return redirect('blood_bank_technician:approved_requests')
    
    if request.method == 'POST':
        collected_by = request.POST.get('collected_by_name')
        collected_id = request.POST.get('collected_by_id')
        collection_notes = request.POST.get('notes', '')
        
        if not collected_by or not collected_id:
            messages.error(request, 'Please provide collector name and ID.')
            return render(request, 'blood_bank_technician/dispatch_request.html', {
                'request': blood_request,
                'request_type': request_type,
                'deducted_units': deducted_units,
            })
        
        try:
            # Update request status
            blood_request.status = 'dispatched'
            blood_request.dispatched_by = profile
            blood_request.dispatched_at = timezone.now()
            blood_request.save()
            
            # Add dispatch note to transactions
            notes_text = f"Dispatched to {collected_by} (ID: {collected_id}) - {collection_notes}"
            
            if request_type == 'patient':
                deducted_units.update(notes=notes_text)
            else:
                deducted_units.update(notes=notes_text)
            
            # Create BloodDispatch records (if you have this model)
            from .models import BloodDispatch
            for tx in deducted_units:
                BloodDispatch.objects.create(
                    stock_unit=tx.stockunit,
                    blood_request=blood_request if request_type == 'patient' else None,
                    donor_blood_request=blood_request if request_type == 'donor' else None,
                    dispatched_by=profile,
                    collected_by_name=collected_by,
                    collected_by_id=collected_id,
                    collection_time=request.POST.get('collection_time') or timezone.now(),
                    notes=collection_notes
                )
            
            messages.success(
                request, 
                f'Blood dispatched successfully to {collected_by}.'
            )
            return redirect('blood_bank_technician:approved_requests')
            
        except Exception as e:
            messages.error(request, f"Error dispatching blood: {str(e)}")
            logger.error(f"Error dispatching {request_type} request {request_id}: {e}", exc_info=True)
            return redirect('blood_bank_technician:approved_requests')
    
    context = {
        'request': blood_request,
        'request_type': request_type,
        'deducted_units': deducted_units,
        'now': timezone.now(),
    }
    
    return render(request, 'blood_bank_technician/dispatch_request.html', context)
# ======================
# EXPIRING BLOOD VIEW
# ======================
@login_required
def expiring_blood(request):
    """View safe blood expiring soon"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    today = timezone.now().date()
    next_week = today + timedelta(days=7)
    
    expiring_soon = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today,
        expiry_date__lte=next_week
    ).select_related('blood_donation__donor__user').order_by('expiry_date')
    
    # Group by blood type
    by_blood_type = {}
    total_ml = 0
    total_batches = 0
    
    for unit in expiring_soon:
        bg = unit.bloodgroup
        if bg not in by_blood_type:
            by_blood_type[bg] = {
                'total_ml': 0,
                'batches': []
            }
        by_blood_type[bg]['total_ml'] += unit.unit
        by_blood_type[bg]['batches'].append(unit)
        total_ml += unit.unit
        total_batches += 1
    
    context = {
        'expiring_soon': expiring_soon,
        'by_blood_type': by_blood_type,
        'total_batches': total_batches,
        'total_ml': total_ml,
        'today': today,
        'next_week': next_week,
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/expiring_blood.html', context)

# ======================
# STOCK TRANSACTION HISTORY
# ======================
@login_required
def transaction_history(request):
    """View stock transaction history"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    transaction_type = request.GET.get('type', '')
    days = request.GET.get('days', 30)
    
    try:
        days = int(days)
    except ValueError:
        days = 30
    
    since = timezone.now() - timedelta(days=days)
    
    transactions = StockTransaction.objects.filter(
        stockunit__center=center,
        transaction_at__gte=since
    ).select_related(
        'stockunit',
        'user',
        'blood_request__request_by_patient__user'
    ).order_by('-transaction_at')
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    # Calculate summary
    summary = {
        'total_additions': transactions.filter(transaction_type='addition').count(),
        'total_deductions': transactions.filter(transaction_type='deduction').count(),
        'total_added_ml': transactions.filter(transaction_type='addition').aggregate(
            total=Sum('quantity_added')
        )['total'] or 0,
        'total_deducted_ml': transactions.filter(transaction_type='deduction').aggregate(
            total=Sum('quantity_deducted')
        )['total'] or 0,
    }
    
    context = {
        'transactions': transactions,
        'summary': summary,
        'transaction_type': transaction_type,
        'days': days,
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/transaction_history.html', context)
