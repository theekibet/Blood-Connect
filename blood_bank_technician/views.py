from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import timedelta
from .models import BloodBankTechProfile
from lab_technologist.models import BloodTest
from django.http import JsonResponse
from blood.models import StockUnit, StockTransaction
from django.core.exceptions import PermissionDenied
from .models import BloodBankTechProfile
from .forms import BloodBankTechProfileForm
from django.db import transaction
from hospital.models import HospitalBloodRequest, HospitalUser
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
    pending_requests_count = HospitalBloodRequest.objects.filter(
        status='pending',
        assigned_centre=center
    ).count()
    
    # ===== RECENT TRANSACTIONS =====
    # FIXED: Removed 'blood_request' from select_related
    recent_transactions = StockTransaction.objects.filter(
        stockunit__center=center
    ).select_related(
        'stockunit',
        'user',
        # 'appointment'  # Uncomment if you have appointment field in StockTransaction
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
        'pending_requests': pending_requests_count,
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


# ======================
# PENDING REQUESTS VIEW
# ======================
@login_required
def pending_requests(request):
    """View pending blood requests from hospitals"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get hospital requests
    hospital_requests = HospitalBloodRequest.objects.filter(
        status='pending',
        assigned_centre=center
    ).select_related(
        'hospital',
        'requested_by__user',
        'assigned_centre'
    ).order_by('-created_at')
    
    # Process and annotate requests
    pending_requests_list = []
    
    for req in hospital_requests:
        availability = check_stock_availability(center, req.blood_group, req.units_requested)
        patient_name = f"{req.patient_first_name} {req.patient_last_name}"
        pending_requests_list.append({
            'id': req.id,
            'request_number': req.request_number,
            'patient_name': patient_name,
            'blood_group': req.blood_group,
            'units_requested': req.units_requested,
            'created_at': req.created_at,
            'hospital_name': req.hospital.name,
            'contact_phone': req.hospital.contact_phone,
            'urgency': req.urgency,
            'urgency_display': req.get_urgency_display(),
            'doctor_name': req.doctor_name,
            'has_inventory': availability.get('can_fulfill', False),
            'available_stock': availability.get('safe_stock', 0),
            'available_batches': availability.get('available_batches', 0),
        })
    
    # Sort by urgency and created_at
    pending_requests_list.sort(key=lambda x: (
        0 if x['urgency'] == 'emergency' else 1 if x['urgency'] == 'urgent' else 2,
        -x['created_at'].timestamp()
    ))
    
    context = {
        'pending_requests': pending_requests_list,
        'total_pending': len(pending_requests_list),
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/pending_requests.html', context)


# ======================
# APPROVE REQUEST VIEW
# ======================
@login_required
def approve_request(request, request_id):
    """Approve a hospital blood request and deduct stock using FIFO"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    today = timezone.now().date()
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the hospital request
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        status='pending',
        assigned_centre=center
    )
    patient_name = f"{blood_request.patient_first_name} {blood_request.patient_last_name}"
    
    # Check availability)
    available_units = StockUnit.objects.filter(
        center=center,
        bloodgroup=blood_request.blood_group,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today
    ).order_by('expiry_date', 'added_on')
    
    total_available = available_units.aggregate(total=Sum('unit'))['total'] or 0
    can_fulfill = total_available >= blood_request.units_requested
    
    if request.method == 'POST':
        if not can_fulfill:
            messages.error(
                request, 
                f"Insufficient safe stock. Available: {total_available}ml, "
                f"Required: {blood_request.units_requested}ml"
            )
            return redirect('blood_bank_technician:pending_requests')
        
        try:
            with transaction.atomic():
                # Deduct stock using FIFO
                units_to_deduct = blood_request.units_requested
                deducted_units_list = []
                
                for unit in available_units:
                    if units_to_deduct <= 0:
                        break
                    
                    deduct_amount = min(unit.unit, units_to_deduct)
                    
                    # Create transaction record
                    tx = StockTransaction.objects.create(
                        stockunit=unit,
                        quantity_deducted=deduct_amount,
                        transaction_type='deduction',
                        user=request.user,
                        notes=f"Deducted for hospital request #{blood_request.request_number}"
                    )
                    deducted_units_list.append(tx)
                    
                    # Update stock unit
                    if deduct_amount >= unit.unit:
                        unit.unit = 0
                        unit.is_available = False
                    else:
                        unit.unit -= deduct_amount
                    unit.save()
                    
                    units_to_deduct -= deduct_amount
                
                # Update request status
                blood_request.status = 'approved'
                blood_request.approved_by = profile
                blood_request.approved_at = timezone.now()
                blood_request.save()
                
                # Create notification for hospital
                from utils.models import Notification
                from django.contrib.contenttypes.models import ContentType
                
                hospital_users = HospitalUser.objects.filter(hospital=blood_request.hospital, is_active=True)
                for hospital_user in hospital_users:
                    Notification.objects.create(
                        title="Blood Request Approved",
                        message=(
                            f"Blood request {blood_request.request_number} for patient {patient_name} "
                            f"({blood_request.units_requested}ml of {blood_request.blood_group}) has been approved. "
                            f"Please arrange pickup from {center.name}. Contact: {center.contact_number}"
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(hospital_user.user),
                        recipient_object_id=hospital_user.user.id,
                        sender_content_type=ContentType.objects.get_for_model(profile.user),
                        sender_object_id=profile.user.id,
                    )
                
                messages.success(
                    request, 
                    f"Request #{blood_request.request_number} approved. {blood_request.units_requested}ml of {blood_request.blood_group} deducted from inventory."
                )
                
                return redirect('blood_bank_technician:approved_requests')
            
        except Exception as e:
            messages.error(request, f"Error approving request: {str(e)}")
            logger.error(f"Error approving request {request_id}: {e}", exc_info=True)
            return redirect('blood_bank_technician:pending_requests')
    
    # GET request - show confirmation page
    context = {
        'request': blood_request,
        'patient_name': patient_name,
        'available_units': available_units,
        'total_available': total_available,
        'can_fulfill': can_fulfill,
        'center': center,
        'today': today,
    }
    
    return render(request, 'blood_bank_technician/approve_request.html', context)


# ======================
# REJECT REQUEST VIEW
# ======================
@login_required
def reject_request(request, request_id):
    """Reject a hospital blood request with reason"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the hospital request
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        status='pending',
        assigned_centre=center
    )
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        
        if not reason:
            messages.error(request, 'Please provide a reason for rejection.')
            return render(request, 'blood_bank_technician/reject_request.html', {
                'request': blood_request,
            })
        
        blood_request.status = 'rejected'
        blood_request.rejection_reason = reason
        blood_request.save()
        
        # Create notification for hospital
        from utils.models import Notification
        from django.contrib.contenttypes.models import ContentType
        
        hospital_users = HospitalUser.objects.filter(hospital=blood_request.hospital, is_active=True)
        patient_name = f"{blood_request.patient_first_name} {blood_request.patient_last_name}"
        
        for hospital_user in hospital_users:
            Notification.objects.create(
                title="Blood Request Rejected",
                message=(
                    f"Blood request {blood_request.request_number} for patient {patient_name} "
                    f"({blood_request.units_requested}ml of {blood_request.blood_group}) has been rejected. "
                    f"Reason: {reason}"
                ),
                recipient_content_type=ContentType.objects.get_for_model(hospital_user.user),
                recipient_object_id=hospital_user.user.id,
                sender_content_type=ContentType.objects.get_for_model(profile.user),
                sender_object_id=profile.user.id,
            )
        
        messages.warning(request, f'Request #{blood_request.request_number} rejected. Reason: {reason}')
        return redirect('blood_bank_technician:pending_requests')
    
    return render(request, 'blood_bank_technician/reject_request.html', {
        'request': blood_request,
    })


# ======================
# APPROVED REQUESTS VIEW
# ======================
@login_required
def approved_requests(request):
    """View approved requests ready for dispatch"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get hospital approved requests
    approved_requests_list = HospitalBloodRequest.objects.filter(
        status__in=['approved', 'dispatched'],
        assigned_centre=center
    ).select_related(
        'hospital',
        'approved_by__user',
        'assigned_centre',
    ).order_by('-approved_at')
    
    # Process requests
    processed_requests = []
    for req in approved_requests_list:
        patient_name = f"{req.patient_first_name} {req.patient_last_name}"
        
        # Get dispatch count if any
        dispatch_count = 0
        if hasattr(req, 'dispatches'):
            dispatch_count = req.dispatches.count()
        
        processed_requests.append({
            'id': req.id,
            'request_number': req.request_number,
            'patient_name': patient_name,
            'blood_group': req.blood_group,
            'units_requested': req.units_requested,
            'status': req.status,
            'status_display': req.get_status_display(),
            'approved_at': req.approved_at,
            'approved_by_name': req.approved_by.user.get_full_name() if req.approved_by else 'Unknown',
            'hospital_name': req.hospital.name,
            'hospital_phone': req.hospital.contact_phone,
            'dispatch_count': dispatch_count,
            'urgency': req.urgency,
            'urgency_display': req.get_urgency_display(),
        })
    
    context = {
        'approved_requests': processed_requests,
        'approved_count': len(processed_requests),  # FIXED: Changed from .count() to len()
        'dispatched_count': sum(1 for r in processed_requests if r['status'] == 'dispatched'),
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/approved_requests.html', context)


# ======================
# DISPATCH REQUEST VIEW
# ======================
@login_required
def dispatch_request(request, request_id):
    """Record dispatch of approved blood request to hospital"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    # Get the hospital request
    blood_request = get_object_or_404(
        HospitalBloodRequest, 
        id=request_id, 
        status='approved',
        assigned_centre=center
    )
    
    # Get deducted transactions for this request
    deducted_transactions = StockTransaction.objects.filter(
        notes__icontains=f"#{blood_request.request_number}",
        transaction_type='deduction'
    ).select_related('stockunit')
    
    if request.method == 'POST':
        collected_by = request.POST.get('collected_by_name')
        collected_id = request.POST.get('collected_by_id')
        collected_phone = request.POST.get('collected_by_phone', '')
        collection_notes = request.POST.get('notes', '')
        
        if not collected_by or not collected_id:
            messages.error(request, 'Please provide collector name and ID.')
            return render(request, 'blood_bank_technician/dispatch_request.html', {
                'request': blood_request,
                'deducted_transactions': deducted_transactions,
            })
        
        try:
            with transaction.atomic():
                # Create BloodDispatch records
                from .models import BloodDispatch
                
                for tx in deducted_transactions:
                    BloodDispatch.objects.create(
                        stock_unit=tx.stockunit,
                        hospital_request=blood_request,
                        dispatched_by=profile,
                        collected_by_name=collected_by,
                        collected_by_id=collected_id,
                        collected_by_phone=collected_phone,
                        collection_time=timezone.now(),
                        hospital=blood_request.hospital,
                        notes=collection_notes,
                        status='dispatched'
                    )
                
                # Update request status
                blood_request.status = 'dispatched'
                blood_request.dispatched_by = profile
                blood_request.dispatched_at = timezone.now()
                blood_request.save()
                
                # Notify hospital
                from utils.models import Notification
                from django.contrib.contenttypes.models import ContentType
                
                hospital_users = HospitalUser.objects.filter(hospital=blood_request.hospital, is_active=True)
                patient_name = f"{blood_request.patient_first_name} {blood_request.patient_last_name}"
                
                for hospital_user in hospital_users:
                    Notification.objects.create(
                        title="Blood Dispatched",
                        message=(
                            f"Blood for request {blood_request.request_number} (Patient: {patient_name}) "
                            f"has been dispatched. Collected by: {collected_by} (ID: {collected_id}). "
                            f"Expected arrival at {blood_request.hospital.name} shortly."
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(hospital_user.user),
                        recipient_object_id=hospital_user.user.id,
                        sender_content_type=ContentType.objects.get_for_model(profile.user),
                        sender_object_id=profile.user.id,
                    )
                
                messages.success(
                    request, 
                    f'Blood dispatched successfully to {collected_by} from {blood_request.hospital.name}.'
                )
                return redirect('blood_bank_technician:approved_requests')
            
        except Exception as e:
            messages.error(request, f"Error dispatching blood: {str(e)}")
            logger.error(f"Error dispatching request {request_id}: {e}", exc_info=True)
            return redirect('blood_bank_technician:approved_requests')
    
    context = {
        'request': blood_request,
        'deducted_transactions': deducted_transactions,
        'now': timezone.now(),
        'patient_name': f"{blood_request.patient_first_name} {blood_request.patient_last_name}",
    }
    
    return render(request, 'blood_bank_technician/dispatch_request.html', context)


# ======================
# REQUEST DETAIL VIEW
# ======================
@login_required
def request_detail(request, request_id):
    """View details of a specific blood request"""
    
    profile = request.user.blood_bank_tech_profile
    center = profile.center
    
    if not center:
        messages.error(request, "No donation center assigned.")
        return redirect('blood_bank_technician:dashboard')
    
    blood_request = get_object_or_404(
        HospitalBloodRequest,
        id=request_id,
        assigned_centre=center
    )
    
    # Get related dispatches
    dispatches = []
    if hasattr(blood_request, 'dispatches'):
        dispatches = blood_request.dispatches.all().select_related('dispatched_by__user')
    
    # Get related transactions
    transactions = StockTransaction.objects.filter(
        notes__icontains=f"#{blood_request.request_number}"
    ).select_related('stockunit', 'user')
    
    context = {
        'request': blood_request,
        'patient_name': f"{blood_request.patient_first_name} {blood_request.patient_last_name}",
        'dispatches': dispatches,
        'transactions': transactions,
        'center': center,
    }
    
    return render(request, 'blood_bank_technician/request_detail.html', context)


# ======================
# HELPER FUNCTIONS
# ======================
def check_stock_availability(center, blood_group, required_units):
    """Check if there's enough stock available for a request"""
    today = timezone.now().date()
    
    available_stock = StockUnit.objects.filter(
        center=center,
        bloodgroup=blood_group,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=today
    )
    
    total_available = available_stock.aggregate(total=Sum('unit'))['total'] or 0
    available_batches = available_stock.count()
    
    return {
        'can_fulfill': total_available >= required_units,
        'safe_stock': total_available,
        'available_batches': available_batches,
        'required': required_units,
        'shortage': max(0, required_units - total_available)
    }

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