from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import BloodTest, LabTechnologistProfile
from donor.models import BloodDonate
from .forms import BloodTestForm,LabTechnologistProfileForm
from blood.utils.stock_utils import add_stock
from django.utils import timezone
from datetime import timedelta
from blood.models import StockUnit, StockTransaction 
from django.db import transaction
import logging
import uuid
import os
from django.conf import settings
from django.core.exceptions import PermissionDenied

from django.db.models import Q 
from .forms import LabTechnologistSignupForm
logger = logging.getLogger(__name__)
def signup_view(request):
    """Lab Technologist signup view"""
    
    if request.method == 'POST':
        form = LabTechnologistSignupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                profile = form.save()
                messages.success(
                    request, 
                    'Registration successful! Your account is pending admin approval. '
                    'You will be notified once your account is activated.'
                )
                return redirect('lab_technologist:login')
            except Exception as e:
                logger.error(f"Signup error: {str(e)}", exc_info=True)
                messages.error(request, f'Registration failed: {str(e)}')
        else:
            # Form errors will be displayed in template
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LabTechnologistSignupForm()
    
    return render(request, 'lab_technologist/signup.html', {'form': form})
# ======================
# LOGIN VIEW
# ======================
def login_view(request):
    """Lab Technologist login view"""
    
    # If user is already logged in and is a lab tech, redirect to dashboard
    if request.user.is_authenticated:
        if hasattr(request.user, 'lab_tech_profile'):
            return redirect('lab_technologist:dashboard')
        else:
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user has lab tech profile
            try:
                lab_tech_profile = LabTechnologistProfile.objects.get(user=user)
                # TEMPORARILY DISABLED: Admin approval not required
                login(request, user)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                return redirect('lab_technologist:dashboard')
            except LabTechnologistProfile.DoesNotExist:
                messages.error(request, "You don't have Lab Technologist access. Please check your credentials.")
        else:
            messages.error(request, "Invalid username or password.")
    
    return render(request, 'lab_technologist/login.html')
@login_required
def lab_tech_profile(request):
    """View logged-in user's lab technologist profile"""
    try:
        profile = request.user.lab_tech_profile
        # Fix: Use the correct URL name from urls.py
        return redirect('lab_technologist:lab_tech_profile_detail', pk=profile.pk)
    except LabTechnologistProfile.DoesNotExist:
        messages.error(request, "Lab Technologist profile not found.")
        return redirect('lab_technologist:dashboard')
@login_required
def lab_tech_profile_detail(request, pk):
    """View lab technologist profile details"""
    profile = get_object_or_404(LabTechnologistProfile, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and profile.user != request.user:
        raise PermissionDenied("You don't have permission to view this profile.")
    
    context = {
        'profile': profile,
        'profile_type': 'Lab Technologist'
    }
    return render(request, 'lab_technologist/profile_detail.html', context)


@login_required
def lab_tech_profile_edit(request, pk):
    """Edit lab technologist profile"""
    profile = get_object_or_404(LabTechnologistProfile, pk=pk)
    
    # Check permission
    if not request.user.is_superuser and profile.user != request.user:
        raise PermissionDenied("You don't have permission to edit this profile.")
    
    if request.method == 'POST':
        # Check if user wants to delete the picture
        if request.POST.get('delete_picture') == 'true' or request.POST.get('remove_picture') == 'on':
            if profile.profile_pic:
                # Delete the file from storage
                if os.path.isfile(profile.profile_pic.path):
                    os.remove(profile.profile_pic.path)
                # Clear the field
                profile.profile_pic = None
                profile.save()
                messages.info(request, 'Profile picture removed.')
                return redirect('lab_technologist:lab_tech_profile_edit', pk=profile.pk)
        
        form = LabTechnologistProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            try:
                saved_profile = form.save()
                if saved_profile.profile_pic:
                    messages.success(request, 'Profile updated successfully with new picture!')
                else:
                    messages.success(request, 'Profile updated successfully!')
                return redirect('lab_technologist:lab_tech_profile_detail', pk=profile.pk)
            except Exception as e:
                messages.error(request, f'Error saving profile: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = LabTechnologistProfileForm(instance=profile)
    
    context = {
        'form': form,
        'profile': profile,
    }
    return render(request, 'lab_technologist/profile_edit.html', context)

# ======================
# DASHBOARD VIEW
# ======================
@login_required
def dashboard(request):
    """Lab Technologist dashboard with barcode information"""
    
    # Ensure user has a profile
    profile, created = LabTechnologistProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'employee_id': f"LAB-{request.user.id}",
            'phone': '',
            'qualification': '',
            'license_number': '',
            'is_active': True
        }
    )
    
    # Get center for filtering
    center = profile.center
    
    # Blood awaiting testing (collected but not tested) - with barcode info
    pending_tests_qs = BloodDonate.objects.filter(
        status='collected',
        lab_test__isnull=True
    )
    
    # Filter by center if lab tech has a center assigned
    if center:
        pending_tests_qs = pending_tests_qs.filter(donation_center=center)
    
    pending_tests = pending_tests_qs.count()
    
    # Get detailed pending tests with barcode information
    pending_tests_details = pending_tests_qs.select_related(
        'donor__user',
        'donation_center'
    ).order_by('-date')[:10]  # Latest 10 pending tests
    
    # Annotate each pending test with its blood bag barcode
    from blood.models import BloodBagBarcode
    
    # Create a list to hold pending tests with barcode info
    pending_tests_with_barcode = []
    for donation in pending_tests_details:
        # Make a copy of the donation object or create a dict with its attributes
        donation_data = {
            'donation': donation,
            'donor_name': donation.donor.user.get_full_name() if donation.donor else 'Unknown',
            'donation_center': donation.donation_center.name if donation.donation_center else 'Unknown',
            'date': donation.date,
            'unit': donation.unit,
            'bloodgroup': donation.bloodgroup,
        }
        
        # Get the blood bag barcode
        blood_bag = BloodBagBarcode.objects.filter(
            assigned_to_donor=donation.donor,
            status='collected',
            blood_donation=donation
        ).first()
        
        donation_data['barcode'] = blood_bag.barcode if blood_bag else 'N/A'
        donation_data['bag_type'] = blood_bag.get_bag_type_display() if blood_bag else 'Standard'
        
        pending_tests_with_barcode.append(donation_data)
    
    # Tests performed by this tech - with barcode info
    my_tests_qs = BloodTest.objects.filter(
        tested_by=profile
    ).select_related(
        'blood_collection__donor__user',
        'blood_collection__donation_center'
    ).order_by('-test_date')[:10]
    
    # Create a list for tests with barcode info
    my_tests_with_barcode = []
    for test in my_tests_qs:
        test_data = {
            'test': test,
            'id': test.id,
            'result': test.result,
            'blood_group': test.blood_group,
            'test_date': test.test_date,
            'donor_name': test.blood_collection.donor.user.get_full_name() if test.blood_collection and test.blood_collection.donor else 'Unknown',
        }
        
        # Add barcode information
        if test.blood_collection:
            from blood.models import BloodBagBarcode
            blood_bag = BloodBagBarcode.objects.filter(
                blood_donation=test.blood_collection
            ).first()
            test_data['barcode'] = blood_bag.barcode if blood_bag else 'N/A'
        else:
            test_data['barcode'] = 'N/A'
        
        my_tests_with_barcode.append(test_data)
    
    # Statistics
    total_tests = BloodTest.objects.count()
    if center:
        total_tests = BloodTest.objects.filter(
            blood_collection__donation_center=center
        ).count()
    
    safe_count = BloodTest.objects.filter(result='safe')
    unsafe_count = BloodTest.objects.filter(result='unsafe')
    
    if center:
        safe_count = safe_count.filter(blood_collection__donation_center=center).count()
        unsafe_count = unsafe_count.filter(blood_collection__donation_center=center).count()
    else:
        safe_count = safe_count.count()
        unsafe_count = unsafe_count.count()
    
    # Tests completed today
    today = timezone.now().date()
    today_tests = BloodTest.objects.filter(
        tested_by=profile,
        test_date__date=today
    ).count()
    
    # ===== GENERATE PERSONALIZED GREETING =====
    try:
        from blood.utils.greetings import get_lab_tech_greeting
        
        greeting_data = get_lab_tech_greeting(
            lab_tech=profile,
            pending_tests=pending_tests,
            completed_today=today_tests,
            safe_count=safe_count,
            unsafe_count=unsafe_count
        )
    except ImportError:
        # Fallback greeting if the utility doesn't exist
        greeting_data = {
            'greeting': f"👋 Good {get_time_of_day()}, {profile.user.get_full_name() or profile.user.username}!",
            'context_message': f"Managing lab at {center.name if center else 'your center'}",
            'user_type': 'lab_tech',
            'icon': '🔬',
            'meta_items': [
                {'icon': 'fas fa-hourglass-half', 'text': f'{pending_tests} pending tests'},
                {'icon': 'fas fa-check-circle', 'text': f'{today_tests} tests today', 'color': 'text-success'},
                {'icon': 'fas fa-flask', 'text': f'{total_tests} total tests'},
            ]
        }
    
    context = {
        'profile': profile,
        'center': center,
        'pending_tests': pending_tests,
        'pending_tests_details': pending_tests_with_barcode,
        'my_tests': my_tests_with_barcode,
        'total_tests': total_tests,
        'safe_count': safe_count,
        'unsafe_count': unsafe_count,
        'today_tests': today_tests,
        'completion_rate': (safe_count / total_tests * 100) if total_tests > 0 else 0,
        'greeting_data': greeting_data,  # Add greeting data to context
    }
    return render(request, 'lab_technologist/dashboard.html', context)

def get_time_of_day():
    """Helper function to get time of day for greeting"""
    hour = timezone.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"
@login_required
def pending_tests(request):
    """List all blood awaiting testing with barcode information"""
    
    profile = request.user.lab_tech_profile
    center = profile.center
    
    pending_blood = BloodDonate.objects.filter(
        status='collected',
        lab_test__isnull=True
    ).select_related(
        'donor__user',
        'donation_center'
    ).order_by('-date')
    
    if center:
        pending_blood = pending_blood.filter(donation_center=center)
    
    # Create a list with barcode information
    pending_blood_with_barcode = []
    from blood.models import BloodBagBarcode
    
    for donation in pending_blood:
        donation_data = {
            'id': donation.id,
            'donor_name': donation.donor.user.get_full_name() if donation.donor else 'Unknown',
            'donor_id': donation.donor.id if donation.donor else None,
            'donation_center': donation.donation_center.name if donation.donation_center else 'Unknown',
            'date': donation.date,
            'unit': donation.unit,
            'bloodgroup': donation.bloodgroup,
            'status': donation.status,
        }
        
        # Get blood bag barcode
        blood_bag = BloodBagBarcode.objects.filter(
            assigned_to_donor=donation.donor,
            status='collected',
            blood_donation=donation
        ).first()
        
        donation_data['barcode'] = blood_bag.barcode if blood_bag else 'N/A'
        donation_data['bag_type'] = blood_bag.get_bag_type_display() if blood_bag and hasattr(blood_bag, 'get_bag_type_display') else 'Standard'
        
        pending_blood_with_barcode.append(donation_data)
    
    context = {
        'pending_blood': pending_blood_with_barcode,  # Now using the list with barcode info
        'count': len(pending_blood_with_barcode),
        'center': center,
    }
    return render(request, 'lab_technologist/pending_tests.html', context)

@login_required
@transaction.atomic
def perform_test(request, collection_id):
    """Perform test on a blood collection with barcode tracking"""
    
    blood = get_object_or_404(BloodDonate, id=collection_id, status='collected')
    
    # Get the blood bag barcode
    from blood.models import BloodBagBarcode
    blood_bag = BloodBagBarcode.objects.filter(
        blood_donation=blood
    ).first()
    
    # Check if already tested
    if hasattr(blood, 'lab_test'):
        messages.warning(request, 'This blood has already been tested.')
        return redirect('lab_technologist:test_result', test_id=blood.lab_test.id)
    
    if request.method == 'POST':
        form = BloodTestForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.blood_collection = blood
            test.tested_by = request.user.lab_tech_profile
            test.save()  # This calls determine_safety() automatically
            
            # Get unsafe reason from form if provided
            unsafe_reason = request.POST.get('unsafe_reason', '').strip()
            
            # ===== PERMANENTLY VERIFY DONOR'S BLOOD GROUP (REGARDLESS OF SAFE/UNSAFE) =====
            # This happens BEFORE stock handling so we know if this was first verification
            donor = blood.donor
            was_first_verification = False
            
            if donor:
                if not donor.bloodgroup_verified:
                    # First time verification - set and lock
                    donor.bloodgroup = test.blood_group
                    donor.bloodgroup_verified = True
                    donor.bloodgroup_verified_by = request.user
                    donor.bloodgroup_verified_at = timezone.now()
                    donor.save()
                    was_first_verification = True
                    
                    logger.info(f"✅ PERMANENTLY VERIFIED donor {donor.id} blood group: {test.blood_group}")
                    
                    # Create notification for donor
                    from utils.models import Notification
                    from django.contrib.contenttypes.models import ContentType
                    
                    Notification.objects.create(
                        title="Blood Group Verified",
                        message=(
                            f"Your blood group has been permanently verified as {test.blood_group} "
                            f"based on laboratory testing. This information is now locked and "
                            f"will be used for all future donations."
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(donor),
                        recipient_object_id=donor.id,
                        sender_content_type=ContentType.objects.get_for_model(request.user),
                        sender_object_id=request.user.id,
                    )
                    
                elif donor.bloodgroup != test.blood_group and donor.bloodgroup_verified:
                    # This should never happen - blood group mismatch with verified donor
                    # Log it as critical error
                    logger.error(f"⚠️ CRITICAL: Donor {donor.id} has verified blood group {donor.bloodgroup} "
                               f"but test shows {test.blood_group}. Manual review required!")
                    
                    # Create alert for admin
                    from utils.models import Notification
                    from django.contrib.contenttypes.models import ContentType
                    
                    Notification.objects.create(
                        title="⚠️ BLOOD GROUP MISMATCH DETECTED",
                        message=(
                            f"Donor {donor.user.get_full_name()} has verified blood group {donor.bloodgroup} "
                            f"but lab test shows {test.blood_group}. Immediate review required!"
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(request.user),
                        recipient_object_id=request.user.id,
                    )
            
            # ===== NOW HANDLE STOCK BASED ON TEST RESULT =====
            if test.result == 'safe':
                # Create stock unit for safe blood - using the pre-generated barcode
                stock_unit = StockUnit.objects.create(
                    bloodgroup=test.blood_group,
                    unit=blood.unit,
                    center=blood.donation_center,
                    expiry_date=timezone.now().date() + timedelta(days=46),
                    blood_donation=blood,
                    blood_bag_barcode=blood_bag,  # Link to the pre-generated barcode
                    barcode=blood_bag.barcode if blood_bag else f"STK-{uuid.uuid4().hex[:10].upper()}",  # Use bag barcode or generate
                    safety_status='safe',
                    safety_verified_by=request.user,
                    safety_verified_by_role='lab_tech',
                    safety_verified_at=timezone.now(),
                    safety_notes=f"Tested by lab: All markers negative. Test ID: {test.id}",
                    is_quarantined=False,
                    added_to_inventory_by=request.user,
                    added_to_inventory_by_role='lab_tech',
                    added_to_inventory_at=timezone.now()
                )
                
                # Create stock transaction record
                StockTransaction.objects.create(
                    stockunit=stock_unit,
                    quantity_added=blood.unit,
                    quantity_deducted=None,
                    transaction_type='addition',
                    user=request.user,
                    notes=f"Added to inventory after lab testing - Test ID: {test.id}, Result: SAFE, Barcode: {stock_unit.barcode}"
                )
                
                # Update blood bag barcode status
                if blood_bag:
                    blood_bag.status = 'tested'
                    blood_bag.save()
                
                # Update blood donation status
                blood.status = 'tested_safe'
                blood.save()
                
                # Update appointment status
                from phlebotomist.models import Appointment
                try:
                    appointment = Appointment.objects.get(
                        request_object_id=blood.id,
                        request_content_type__model='blooddonate'
                    )
                    appointment.status = 'completed'
                    appointment.completed_by = request.user
                    appointment.completed_by_role = 'lab_tech'
                    appointment.completed_at = timezone.now()
                    appointment.safety_status = 'safe'
                    appointment.safety_verified_by = request.user
                    appointment.safety_verified_by_role = 'lab_tech'
                    appointment.safety_verified_at = timezone.now()
                    appointment.save()
                except Appointment.DoesNotExist:
                    logger.warning(f"No appointment found for blood donation {blood.id}")
                
                # Award points to donor
                if blood.donor:
                    blood.donor.points += 10
                    blood.donor.last_donation_date = blood.date
                    blood.donor.save()
                
                messages.success(
                    request, 
                    f'✅ Test completed. Blood marked SAFE and added to inventory. '
                    f'Donor blood group has been {"verified" if was_first_verification else "confirmed"}. '
                    f'Barcode: {stock_unit.barcode}'
                )
                
            else:  # unsafe
                # Use reason from form or default
                if not unsafe_reason:
                    unsafe_reason = 'Tested positive for disease markers'
                
                # Create stock unit for unsafe blood (quarantined)
                stock_unit = StockUnit.objects.create(
                    bloodgroup=test.blood_group,
                    unit=0,  # Zero units for unsafe blood
                    center=blood.donation_center,
                    expiry_date=timezone.now().date() + timedelta(days=46),
                    blood_donation=blood,
                    blood_bag_barcode=blood_bag,
                    barcode=blood_bag.barcode if blood_bag else f"STK-{uuid.uuid4().hex[:10].upper()}",
                    safety_status='unsafe',
                    safety_verified_by=request.user,
                    safety_verified_by_role='lab_tech',
                    safety_verified_at=timezone.now(),
                    unsafe_reason=unsafe_reason,
                    safety_notes=f"Tested by lab: {unsafe_reason}. Test ID: {test.id}",
                    is_quarantined=True
                )
                
                # Create stock transaction record for unsafe blood
                StockTransaction.objects.create(
                    stockunit=stock_unit,
                    quantity_added=None,
                    quantity_deducted=blood.unit,
                    transaction_type='deduction',
                    user=request.user,
                    notes=f"Unsafe blood discarded - Test ID: {test.id}, Result: UNSAFE, Reason: {unsafe_reason}, Barcode: {stock_unit.barcode}"
                )
                
                # Update blood bag barcode status
                if blood_bag:
                    blood_bag.status = 'discarded'
                    blood_bag.save()
                
                # Update blood donation status
                blood.status = 'tested_unsafe'
                blood.save()
                
                # Update appointment status
                from phlebotomist.models import Appointment
                try:
                    appointment = Appointment.objects.get(
                        request_object_id=blood.id,
                        request_content_type__model='blooddonate'
                    )
                    appointment.status = 'completed'
                    appointment.completed_by = request.user
                    appointment.completed_by_role = 'lab_tech'
                    appointment.completed_at = timezone.now()
                    appointment.safety_status = 'unsafe'
                    appointment.safety_verified_by = request.user
                    appointment.safety_verified_by_role = 'lab_tech'
                    appointment.safety_verified_at = timezone.now()
                    appointment.save()
                except Appointment.DoesNotExist:
                    logger.warning(f"No appointment found for blood donation {blood.id}")
                
                # Notify donor about unsafe result (without revealing specific disease)
                if blood.donor:
                    from utils.models import Notification
                    from django.contrib.contenttypes.models import ContentType
                    
                    Notification.objects.create(
                        title="Blood Donation Test Results",
                        message=(
                            f"Thank you for your recent blood donation. Our laboratory testing has been completed. "
                            f"Please contact the blood bank for further information about your results."
                        ),
                        recipient_content_type=ContentType.objects.get_for_model(blood.donor),
                        recipient_object_id=blood.donor.id,
                        sender_content_type=ContentType.objects.get_for_model(request.user),
                        sender_object_id=request.user.id,
                    )
                
                messages.warning(
                    request, 
                    f'⚠️ Test completed. Blood marked UNSAFE and quarantined. '
                    f'Donor blood group has been {"verified" if was_first_verification else "confirmed"}. '
                    f'Reason: {unsafe_reason}'
                )
            
            return redirect('lab_technologist:test_result', test_id=test.id)
    else:
        # Pre-fill with donor's blood group if available
        initial = {}
        if blood.donor and blood.donor.bloodgroup:
            initial['blood_group'] = blood.donor.bloodgroup
        
        # Get barcode info for display
        barcode_info = blood_bag.barcode if blood_bag else 'No barcode assigned'
        bag_type = blood_bag.get_bag_type_display() if blood_bag and hasattr(blood_bag, 'get_bag_type_display') else 'Standard'
        
        form = BloodTestForm(initial=initial)
    
    return render(request, 'lab_technologist/perform_test.html', {
        'form': form,
        'blood': blood,
        'donor': blood.donor,
        'barcode': blood_bag.barcode if blood_bag else None,
        'bag_type': bag_type,
    })

@login_required
def test_result(request, test_id):
    """View test result with barcode information"""
    
    test = get_object_or_404(
        BloodTest.objects.select_related(
            'blood_collection__donor__user',
            'blood_collection__donation_center',
            'tested_by__user'
        ),
        id=test_id
    )
    
    # Get barcode information
    from blood.models import BloodBagBarcode, StockUnit
    blood_bag = None
    stock_unit = None
    
    if test.blood_collection:
        blood_bag = BloodBagBarcode.objects.filter(
            blood_donation=test.blood_collection
        ).first()
        
        stock_unit = StockUnit.objects.filter(
            blood_donation=test.blood_collection
        ).first()
    
    context = {
        'test': test,
        'blood_bag': blood_bag,
        'stock_unit': stock_unit,
        'barcode': blood_bag.barcode if blood_bag else (stock_unit.barcode if stock_unit else 'N/A'),
    }
    return render(request, 'lab_technologist/test_result.html', context)

# ======================
# MARK SAFE VIEW
# ======================
@login_required
@transaction.atomic
def mark_safe(request, test_id):
    """Manually mark blood as safe"""
    test = get_object_or_404(BloodTest, id=test_id)
    blood = test.blood_collection
    
    if request.method == 'POST':
        # Check if stock unit already exists
        existing_stock = StockUnit.objects.filter(blood_donation=blood).first()
        
        if existing_stock:
            # Update existing stock unit
            existing_stock.safety_status = 'safe'
            existing_stock.is_quarantined = False
            existing_stock.unit = blood.unit  # Restore units
            existing_stock.safety_verified_by = request.user
            existing_stock.safety_verified_by_role = 'lab_tech'
            existing_stock.safety_verified_at = timezone.now()
            existing_stock.safety_notes = f"Manually marked safe by lab tech. Test ID: {test.id}"
            existing_stock.save()
            
            # Create stock transaction for re-addition
            StockTransaction.objects.create(
                stockunit=existing_stock,
                quantity_added=blood.unit,
                quantity_deducted=None,
                transaction_type='addition',
                user=request.user,
                notes=f"Manually marked safe - Test ID: {test.id}, Barcode: {existing_stock.barcode}"
            )
        else:
            # Create new stock unit
            from blood.models import BloodBagBarcode
            blood_bag = BloodBagBarcode.objects.filter(blood_donation=blood).first()
            
            stock_unit = StockUnit.objects.create(
                bloodgroup=test.blood_group,
                unit=blood.unit,
                center=blood.donation_center,
                expiry_date=timezone.now().date() + timedelta(days=46),
                blood_donation=blood,
                blood_bag_barcode=blood_bag,
                barcode=blood_bag.barcode if blood_bag else f"STK-{uuid.uuid4().hex[:10].upper()}",
                safety_status='safe',
                safety_verified_by=request.user,
                safety_verified_by_role='lab_tech',
                safety_verified_at=timezone.now(),
                safety_notes=f"Manually marked safe. Test ID: {test.id}",
                is_quarantined=False,
                added_to_inventory_by=request.user,
                added_to_inventory_by_role='lab_tech',
                added_to_inventory_at=timezone.now()
            )
            
            # Create stock transaction
            StockTransaction.objects.create(
                stockunit=stock_unit,
                quantity_added=blood.unit,
                quantity_deducted=None,
                transaction_type='addition',
                user=request.user,
                notes=f"Added to inventory (manual safe mark) - Test ID: {test.id}, Barcode: {stock_unit.barcode}"
            )
            
            # Update blood bag status
            if blood_bag:
                blood_bag.status = 'tested'
                blood_bag.save()
        
        # Update test and blood status
        test.result = 'safe'
        test.save()
        
        blood.status = 'tested_safe'
        blood.save()
        
        # Update appointment
        from phlebotomist.models import Appointment
        try:
            appointment = Appointment.objects.get(
                request_object_id=blood.id,
                request_content_type__model='blooddonate'
            )
            appointment.status = 'completed'
            appointment.completed_by = request.user
            appointment.completed_by_role = 'lab_tech'
            appointment.completed_at = timezone.now()
            appointment.safety_status = 'safe'
            appointment.safety_verified_by = request.user
            appointment.safety_verified_by_role = 'lab_tech'
            appointment.safety_verified_at = timezone.now()
            appointment.save()
        except Appointment.DoesNotExist:
            pass
        
        # Award donor points
        if blood.donor:
            blood.donor.points += 10
            blood.donor.last_donation_date = blood.date
            blood.donor.save()
        
        messages.success(request, '✅ Blood marked as SAFE and added to inventory.')
        return redirect('lab_technologist:test_result', test_id=test.id)


# ======================
# MARK UNSAFE VIEW
# ======================
@login_required
@transaction.atomic
def mark_unsafe(request, test_id):
    """Manually mark blood as unsafe"""
    test = get_object_or_404(BloodTest, id=test_id)
    blood = test.blood_collection
    
    if request.method == 'POST':
        reason = request.POST.get('unsafe_reason', 'Tested positive for disease markers')
        
        # Check if stock unit already exists
        existing_stock = StockUnit.objects.filter(blood_donation=blood).first()
        
        if existing_stock:
            # Update existing stock unit to unsafe
            existing_stock.safety_status = 'unsafe'
            existing_stock.is_quarantined = True
            existing_stock.unit = 0  # Zero out units
            existing_stock.unsafe_reason = reason
            existing_stock.safety_verified_by = request.user
            existing_stock.safety_verified_by_role = 'lab_tech'
            existing_stock.safety_verified_at = timezone.now()
            existing_stock.safety_notes = f"Manually marked unsafe: {reason}. Test ID: {test.id}"
            existing_stock.save()
            
            # Create deduction transaction
            StockTransaction.objects.create(
                stockunit=existing_stock,
                quantity_added=None,
                quantity_deducted=blood.unit,
                transaction_type='deduction',
                user=request.user,
                notes=f"Unsafe blood discarded (manual mark) - Test ID: {test.id}, Reason: {reason}"
            )
        else:
            # Create new unsafe stock unit
            from blood.models import BloodBagBarcode
            blood_bag = BloodBagBarcode.objects.filter(blood_donation=blood).first()
            
            stock_unit = StockUnit.objects.create(
                bloodgroup=test.blood_group,
                unit=0,
                center=blood.donation_center,
                expiry_date=timezone.now().date() + timedelta(days=46),
                blood_donation=blood,
                blood_bag_barcode=blood_bag,
                barcode=blood_bag.barcode if blood_bag else f"STK-{uuid.uuid4().hex[:10].upper()}",
                safety_status='unsafe',
                safety_verified_by=request.user,
                safety_verified_by_role='lab_tech',
                safety_verified_at=timezone.now(),
                unsafe_reason=reason,
                safety_notes=f"Manually marked unsafe: {reason}. Test ID: {test.id}",
                is_quarantined=True
            )
            
            # Create deduction transaction
            StockTransaction.objects.create(
                stockunit=stock_unit,
                quantity_added=None,
                quantity_deducted=blood.unit,
                transaction_type='deduction',
                user=request.user,
                notes=f"Unsafe blood discarded - Test ID: {test.id}, Reason: {reason}"
            )
            
            # Update blood bag status
            if blood_bag:
                blood_bag.status = 'discarded'
                blood_bag.save()
        
        # Update test notes and result
        test.result = 'unsafe'
        test.notes = f"{test.notes}\nUnsafe Reason: {reason}".strip()
        test.save()
        
        # Update blood status
        blood.status = 'tested_unsafe'
        blood.save()
        
        # Update appointment
        from phlebotomist.models import Appointment
        try:
            appointment = Appointment.objects.get(
                request_object_id=blood.id,
                request_content_type__model='blooddonate'
            )
            appointment.status = 'completed'
            appointment.completed_by = request.user
            appointment.completed_by_role = 'lab_tech'
            appointment.completed_at = timezone.now()
            appointment.safety_status = 'unsafe'
            appointment.safety_verified_by = request.user
            appointment.safety_verified_by_role = 'lab_tech'
            appointment.safety_verified_at = timezone.now()
            appointment.save()
        except Appointment.DoesNotExist:
            pass
        
        # Notify donor
        if blood.donor:
            from utils.models import Notification
            from django.contrib.contenttypes.models import ContentType
            
            Notification.objects.create(
                title="Blood Donation Test Results",
                message=(
                    "Thank you for your recent blood donation. Our laboratory testing has been completed. "
                    "Please contact the blood bank for further information about your results."
                ),
                recipient_content_type=ContentType.objects.get_for_model(blood.donor),
                recipient_object_id=blood.donor.id,
                sender_content_type=ContentType.objects.get_for_model(request.user),
                sender_object_id=request.user.id,
            )
        
        messages.warning(request, f'⚠️ Blood marked as UNSAFE and quarantined. Reason: {reason}')
        return redirect('lab_technologist:test_result', test_id=test.id)

# ======================
# TEST HISTORY VIEW
# ======================
@login_required
def test_history(request):
    """View test history with barcode information"""
    
    profile = request.user.lab_tech_profile
    center = profile.center
    
    # Get base queryset
    tests = BloodTest.objects.filter(
        tested_by=profile
    ).select_related(
        'blood_collection__donor__user',
        'blood_collection__donation_center'
    ).order_by('-test_date')
    
    if center:
        tests = tests.filter(blood_collection__donation_center=center)
    
    # Filter by result if provided
    result_filter = request.GET.get('result', '')
    if result_filter:
        tests = tests.filter(result=result_filter)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        tests = tests.filter(
            Q(blood_collection__donor__user__first_name__icontains=search_query) |
            Q(blood_collection__donor__user__last_name__icontains=search_query) |
            Q(blood_collection__donor__user__username__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    # Date filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if date_from:
        tests = tests.filter(test_date__date__gte=date_from)
    if date_to:
        tests = tests.filter(test_date__date__lte=date_to)
    
    # Get total counts for stats
    total_tests = tests.count()
    safe_count = tests.filter(result='safe').count()
    unsafe_count = tests.filter(result='unsafe').count()
    
    # Calculate percentages
    safe_percentage = (safe_count / total_tests * 100) if total_tests > 0 else 0
    unsafe_percentage = (unsafe_count / total_tests * 100) if total_tests > 0 else 0
    
    # Create list with barcode information - ONLY include tests with valid IDs
    tests_with_barcode = []
    from blood.models import BloodBagBarcode
    
    for test in tests:
        # Skip if test has no ID (shouldn't happen, but just in case)
        if not test.id:
            continue
            
        test_data = {
            'test': test,
            'id': test.id,  # Explicitly include ID
            'donor_name': 'Unknown',
            'barcode': 'N/A'
        }
        
        # Get donor name
        if test.blood_collection and test.blood_collection.donor:
            donor = test.blood_collection.donor
            test_data['donor_name'] = donor.user.get_full_name() or donor.user.username
        
        # Get barcode information
        if test.blood_collection:
            blood_bag = BloodBagBarcode.objects.filter(
                blood_donation=test.blood_collection
            ).first()
            test_data['barcode'] = blood_bag.barcode if blood_bag else 'N/A'
        
        tests_with_barcode.append(test_data)
    
    context = {
        'tests': tests_with_barcode,
        'count': len(tests_with_barcode),
        'total_tests': total_tests,
        'safe_count': safe_count,
        'unsafe_count': unsafe_count,
        'safe_percentage': safe_percentage,
        'unsafe_percentage': unsafe_percentage,
        'result_filter': result_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'center': center,
    }
    return render(request, 'lab_technologist/test_history.html', context)
@login_required
def complete_test(request, test_id):
    """Lab tech completes testing and marks blood safe/unsafe"""
    
    test = get_object_or_404(BloodTest, id=test_id, result='pending')
    
    if request.method == 'POST':
        safety_status = request.POST.get('safety_status')
        unsafe_reason = request.POST.get('unsafe_reason', '')
        
        if safety_status == 'safe':
            # Mark as safe and add to inventory
            test.result = 'safe'
            test.save()
            
            # Add to inventory
            donation = test.blood_collection
            stock_unit = add_stock(
                center=donation.donation_center,
                bloodgroup=test.blood_group,
                units=donation.unit,
                expiry_date=timezone.now().date() + timedelta(days=46),
                safety_status='safe',
                safety_notes=f"Tested by lab: All markers negative"
            )
            
            # Update donation status
            donation.status = 'tested_safe'
            donation.save()
            
            # Award points to donor
            if donation.donor:
                donation.donor.points += 10
                donation.donor.last_donation_date = donation.date
                donation.donor.save()
            
            messages.success(request, 'Blood marked SAFE and added to inventory')
            
        elif safety_status == 'unsafe':
            # Mark as unsafe and discard
            test.result = 'unsafe'
            test.notes = f"UNSAFE: {unsafe_reason}"
            test.save()
            
            donation.status = 'tested_unsafe'
            donation.save()
            
            messages.warning(request, f'Blood marked UNSAFE: {unsafe_reason}')
        
        return redirect('lab_technologist:test_result', test_id=test.id)
    
    return render(request, 'lab_technologist/complete_test.html', {'test': test})
