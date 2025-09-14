import logging
from datetime import date, timedelta
from itertools import chain
from operator import attrgetter
from django.utils import timezone
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Sum, Min
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.timezone import now, localdate
from django.views.decorators.http import require_POST
from blood.utils.stock_utils import add_stock
from .models import Nurse, Appointment, NurseBloodRequest
from .forms import (
    NurseLoginForm, NurseSignupForm, NurseForm, AppointmentForm, BloodRequestForm,
)
from blood.models import Notification, Stock, DonationCenter, StockUnit,StockTransaction, DonorBloodRequest
from blood.utils.stock_utils import deduct_stock_fifo
from datetime import datetime
from donor.models import BloodDonate
from blood.models import BloodRequest 
from collections import OrderedDict
from django.db.models import Q
from collections import defaultdict
from .forms import NurseUserForm
from donor.models import Donor
from django.db.models import Prefetch
from patient.models import Patient
from donor.models import BLOODGROUP_CHOICES
logger = logging.getLogger(__name__)

# Helper: Check if user is in NURSE group
def is_nurse(user):
    return user.groups.filter(name='NURSE').exists()

# ---------------------------
# Nurse Signup View
# ---------------------------
def nurse_signup_view(request):
    if request.method == "POST":
        form = NurseSignupForm(request.POST, request.FILES)
        if form.is_valid():
            nurse = form.save()

            # Assign to group
            nurse_group, _ = Group.objects.get_or_create(name="NURSE")
            nurse_group.user_set.add(nurse.user)

            messages.success(request, "Signup successful! You can now log in.")
            return redirect("nurselogin")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NurseSignupForm()
    return render(request, "nurse/nursesignup.html", {"form": form})

# ---------------------------
# Nurse Login View
# ---------------------------
def nurselogin_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, "✅ You have logged in successfully.")
                return redirect('nurse-dashboard')
            else:
                messages.error(request, "❌ Invalid username or password.")
        else:
            messages.error(request, "⚠️ There was an error in your form. Please correct it.")
    else:
        form = AuthenticationForm()
    return render(request, 'nurse/nurselogin.html', {'form': form})

# ---------------------------
# Nurse Dashboard View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_dashboard(request):
    nurse = get_object_or_404(Nurse.objects.select_related('donation_center'), user=request.user)

    today = localdate()

    # --- Appointment aggregates ---
    total_appointments = Appointment.objects.filter(nurse=nurse).count()
    today_appointments = Appointment.objects.filter(nurse=nurse, date__date=today).count()

    upcoming_appointments = Appointment.objects.filter(
        nurse=nurse,
        date__gte=now()
    ).order_by('date')[:5]

    next_appointment = upcoming_appointments.first() if upcoming_appointments else None

    # Weekly appointments chart data — ensure full week coverage with zeros for missing days
    week_start = today - timedelta(days=6)
    dates = [week_start + timedelta(days=i) for i in range(7)]
    date_counts = OrderedDict((d, 0) for d in dates)

    qs = (
        Appointment.objects.filter(nurse=nurse, date__date__gte=week_start)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(count=Count('id'))
    )

    for entry in qs:
        if entry['day'] in date_counts:
            date_counts[entry['day']] = entry['count']

    chart_labels = [d.strftime('%b %d') for d in date_counts.keys()]
    chart_data = list(date_counts.values())

    # --- Blood stock section for nurse's own center ---
    blood_stock_summary = None
    blood_stock_totals = []

    if nurse.donation_center:
        blood_stock_summary = StockUnit.objects.filter(center=nurse.donation_center)

        bloodgroup_qs = (
            StockUnit.objects.filter(center=nurse.donation_center)
            .values('bloodgroup')
            .annotate(
                total_units=Sum('unit'),
                earliest_expiry=Min('expiry_date'),
                batches_count=Count('id')
            )
            .order_by('bloodgroup')
        )

        for group in bloodgroup_qs:
            blood_stock_totals.append(group)

    # --- Other centers stock (summary with earliest expiry) ---
    all_centers = DonationCenter.objects.all().order_by('name')
    selected_center_id = request.GET.get('centre')
    other_centers_stock = None
    selected_center = None

    if selected_center_id:
        try:
            selected_center = DonationCenter.objects.get(id=selected_center_id)
            # Aggregate total units and earliest expiry per blood group at selected center
            other_centers_stock = (
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
            other_centers_stock = None

    context = {
        'nurse': nurse,
        'total_appointments': total_appointments,
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_appointments,
        'next_appointment': next_appointment,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'current_time': today,
        'blood_stock_summary': blood_stock_summary,
        'blood_stock_totals': blood_stock_totals,
        'all_centers': all_centers,
        'selected_center': selected_center,
        'other_centers_stock': other_centers_stock,
        'today_date': today,
    }
    return render(request, 'nurse/dashboard.html', context)
# ---------------------------
# Nurse Appointments View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def blood_request_bookings(request):
    """View for nurse to see blood request appointments"""
    nurse = get_object_or_404(Nurse, user=request.user)
    
    # Get content types for both request models
    blood_request_ct = ContentType.objects.get_for_model(BloodRequest)
    donor_blood_request_ct = ContentType.objects.get_for_model(DonorBloodRequest)
    
    # Get appointments assigned to this nurse for blood requests
    appointments = Appointment.objects.filter(
        nurse=nurse,
        request_content_type__in=[blood_request_ct, donor_blood_request_ct]
    ).select_related(
        'donor__user',
        'patient__user',
        'nurse__user',
        'request_content_type'
    ).order_by('-date')
    
    context = {
        'appointments': appointments,
        'now': timezone.now(),
    }
    return render(request, 'nurse/blood_request_bookings.html', context)



# ---------------------------
# update_donation_appointmentView (AJAX)
# ---------------------------

logger = logging.getLogger(__name__)


def create_appointment_notification(appointment, nurse_user, action):
    donor = getattr(appointment.request, 'donor', None)  # Safe attribute access
    if not donor:
        logger.warning(f"Appointment {appointment.id} has no donor linked for notification")
        return

    title = "Donation Appointment Update"
    message = (
        f"Your donation appointment on {appointment.date.strftime('%b %d, %Y')} "
        f"has been {action.upper()} by Nurse {nurse_user.get_full_name()}."
    )

    Notification.objects.create(
        title=title,
        message=message,
        recipient_content_type=ContentType.objects.get_for_model(donor),
        recipient_object_id=donor.id,
        sender_content_type=ContentType.objects.get_for_model(nurse_user),
        sender_object_id=nurse_user.id,
    )
logger = logging.getLogger(__name__)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
@require_POST
def nurse_update_donation_appointment_status(request, appointment_id):
    """
    Nurse handler for donation appointment actions (approve, reject, cancel, complete).
    Returns JSON for AJAX requests.
    Nurses are the sole actors for these actions.
    """
    try:
        appointment = get_object_or_404(Appointment, id=appointment_id)
        nurse = request.user.nurse
        now = timezone.now()

        # Auto-assign nurse if not already set
        if not appointment.nurse:
            appointment.nurse = nurse
            appointment.save(update_fields=['nurse'])
        elif appointment.nurse != nurse:
            return JsonResponse({
                'success': False,
                'error': 'This appointment is already assigned to another nurse.'
            }, status=403)

        donation = getattr(appointment, 'request', None)
        if not donation or not isinstance(donation, BloodDonate):
            return JsonResponse({
                'success': False,
                'error': 'This appointment is not linked to a valid blood donation.'
            }, status=400)

        action = (request.POST.get('action') or '').strip().lower()
        valid_actions = ['approve', 'reject', 'completed', 'cancelled']
        if action not in valid_actions:
            return JsonResponse({'success': False, 'error': f'Invalid action "{action}".'}, status=400)

        if donation.status in ['completed', 'cancelled', 'rejected']:
            return JsonResponse({
                'success': False,
                'error': f'This donation was already {donation.status}. No changes allowed.'
            }, status=403)

        validation_errors = []
        new_bg = request.POST.get('bloodgroup')
        new_units = request.POST.get('unit')

        if new_bg and new_bg not in [bg[0] for bg in BLOODGROUP_CHOICES]:
            validation_errors.append("Invalid blood group specified")

        unit_val = None
        if new_units:
            try:
                unit_val = int(new_units)
                if unit_val < 450 or unit_val > 2700 or unit_val % 50 != 0:
                    raise ValueError()
            except ValueError:
                validation_errors.append("Units must be 450–2700 ml in multiples of 50")

        if validation_errors:
            return JsonResponse({'success': False, 'error': '; '.join(validation_errors)}, status=400)

        with transaction.atomic():
            original_status = donation.status
            success_message = ""
            generated_barcode = None

            if action == 'approve':
                if donation.approved_by_nurse:
                    return JsonResponse({'success': False, 'error': "Already approved."}, status=403)
                appointment.set_status('approved', request.user, role='nurse')
                donation.status = 'approved'
                donation.approved_by_nurse = request.user
                donation.approved_at_nurse = now
                donation.save()
                create_appointment_notification(appointment, nurse.user, 'approved')
                success_message = "Donation approved successfully. Ready for completion."

            elif action == 'reject':
                appointment.set_status('rejected', request.user, role='nurse')
                donation.status = 'rejected'
                donation.rejected_by = 'nurse'
                donation.rejected_at = now
                donation.save()
                create_appointment_notification(appointment, nurse.user, 'rejected')
                success_message = "Donation rejected. Donor will be notified."

            elif action == 'cancelled':
                if appointment.date <= now:
                    return JsonResponse({'success': False, 'error': "Cannot cancel a past/ongoing appointment."}, status=400)
                appointment.set_status('cancelled', request.user, role='nurse')
                donation.status = 'cancelled'
                donation.cancelled_by = 'nurse'
                donation.cancelled_at = now
                donation.save()
                create_appointment_notification(appointment, nurse.user, 'cancelled')
                success_message = "Donation appointment cancelled successfully."

            elif action == 'completed':
                if not donation.approved_by_nurse:
                    return JsonResponse({'success': False, 'error': "Donation must be approved before completion."}, status=403)
                
                update_details = []
                if new_bg and new_bg != donation.bloodgroup:
                    donation.bloodgroup = new_bg
                    update_details.append(f"blood group updated to {new_bg}")
                if unit_val and unit_val != donation.unit:
                    donation.unit = unit_val
                    update_details.append(f"units updated to {unit_val}ml")
                
                expiry_date = (donation.date or now.date()) + timedelta(days=46)
                center = donation.donation_center or nurse.center
                
                appointment.set_status('completed', request.user, role='nurse')
                donation.status = 'completed'
                donation.completed_by_nurse = request.user
                donation.completed_at_nurse = now

                # Add stock and create transaction record
                if center and not donation.stock_added_by_nurse:
                    try:
                        stock_unit = add_stock(center, donation.bloodgroup, donation.unit, expiry_date)
                        if stock_unit:
                            generated_barcode = stock_unit.barcode
                            donation.stock_added_by_nurse = True
                            
                            # Create StockTransaction record for the addition
                            from blood.models import StockTransaction
                            StockTransaction.objects.create(
                                stockunit=stock_unit,
                                appointment=appointment,
                                quantity_added=donation.unit,
                                transaction_type='addition',
                                user=request.user,
                                notes=f"Blood donation completion - {donation.unit}ml {donation.bloodgroup} from donor {donation.patient.get_full_name()}"
                            )
                            
                    except Exception as e:
                        logger.error(f"Error adding stock for donation {donation.id}: {e}")
                        # Consider whether to fail the entire operation or continue
                        return JsonResponse({
                            'success': False,
                            'error': f"Failed to add stock: {str(e)}"
                        }, status=500)

                donation.save()
                create_appointment_notification(appointment, nurse.user, 'completed')

                success_message = "Donation completed successfully"
                if update_details:
                    success_message += f" ({', '.join(update_details)})"
                if generated_barcode:
                    success_message += f". Stock unit added with barcode {generated_barcode}."
                else:
                    success_message += " and stock updated."

            logger.info(f"👩‍⚕️ Nurse {request.user.username} changed donation {donation.id} from '{original_status}' to '{donation.status}'")

            return JsonResponse({
                'success': True,
                'status': donation.status,
                'message': success_message,
                'appointment_id': appointment.id,
                'barcode': generated_barcode
            })

    except Exception as e:
        logger.error(f"❌ Nurse error updating donation {appointment_id}: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': "An unexpected error occurred. Please try again or contact support."
        }, status=500)

logger = logging.getLogger(__name__)

def serialize_deductions(deductions):
    serialized = []
    for d in deductions:
        serialized.append({
            'barcode': d['barcode'],
            'quantity': d['quantity'],
            'expiry_date': d['expiry_date'].isoformat() if d['expiry_date'] else None,
        })
    return serialized
logger = logging.getLogger(__name__)

def get_patient_profile(user):
    """
    Return patient profile if user has one, else None.
    Ignores donors entirely.
    """
    if not user:
        return None
    try:
        if hasattr(user, "patient"):
            return user.patient
    except Exception:
        pass
    return None


def create_bloodrequest_notification(appointment, nurse_user, action, reason=None):
    """
    Create notifications for patient linked to a blood request appointment.
    Donors are ignored completely.
    """
    linked_request = getattr(appointment, "request", None)
    if not linked_request:
        logger.warning(
            f"Appointment {appointment.id} has no linked blood request for notification"
        )
        return

    recipients = []

    # Resolve patient profile only
    patient_user = getattr(linked_request, "patient", None)
    patient = get_patient_profile(patient_user)
    if patient:
        recipients.append(("patient", patient))
    else:
        if patient_user:
            logger.info(
                f"Patient profile missing for user {patient_user.username} (ID: {patient_user.id})"
            )
        else:
            logger.warning(f"No patient assigned to blood request {linked_request.id}")

    if not recipients:
        logger.warning(f"No valid recipients found for appointment {appointment.id}")
        return

    # Titles + message templates
    titles = {
        "approved": "Appointment Approved",
        "rejected": "Appointment Rejected",
        "cancelled": "Appointment Cancelled",
        "completed": "Appointment Completed",
    }
    templates = {
        "approved": "Your blood request appointment on {date} at {center} was approved by {actor} {name}.",
        "rejected": "Your blood request appointment on {date} at {center} was rejected by {actor} {name}.",
        "cancelled": "Your blood request appointment on {date} at {center} was cancelled by {actor} {name}.",
        "completed": "Your blood request appointment on {date} at {center} was marked completed by {actor} {name}.",
    }

    date_str = appointment.date.strftime("%b %d, %Y %I:%M %p")
    center = getattr(linked_request.donation_center, "name", "Unknown center")
    sender_name = nurse_user.get_full_name() or nurse_user.username
    actor = "Admin" if nurse_user.is_staff and not hasattr(nurse_user, "nurse") else "Nurse"

    message = templates[action].format(
        date=date_str, center=center, actor=actor, name=sender_name
    )

    for role, recipient in recipients:
        try:
            Notification.objects.create(
                title=titles[action],
                message=message,
                action=action,
                reason=reason if action in ["rejected", "cancelled"] else None,
                appointment_date=appointment.date,
                bloodgroup=linked_request.bloodgroup,
                unit=linked_request.unit,
                recipient_content_type=ContentType.objects.get_for_model(
                    recipient.__class__
                ),
                recipient_object_id=recipient.id,
                sender_content_type=ContentType.objects.get_for_model(
                    nurse_user.__class__
                ),
                sender_object_id=nurse_user.id,
                read=False,
            )
            logger.info(
                f"Notification sent to {role} (ID: {recipient.id}) for appointment {appointment.id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to create notification for {role} (ID: {recipient.id}) "
                f"appointment {appointment.id}: {e}"
            )

logger = logging.getLogger(__name__)
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
@require_POST
def nurse_update_bloodrequest_appointment_status(request, appointment_id):
    """Handle nurse actions on blood request appointments"""
    try:
        nurse = request.user.nurse
        now = timezone.now()

        with transaction.atomic():
            appointment = get_object_or_404(
                Appointment.objects.select_for_update(),
                id=appointment_id
            )

            # Auto-assign nurse if not assigned
            if not appointment.nurse:
                appointment.nurse = nurse
                appointment.save(update_fields=['nurse'])
            elif appointment.nurse != nurse:
                return JsonResponse({
                    'success': False, 
                    'error': 'This appointment is assigned to another nurse.'
                }, status=403)

            # Get the linked request (BloodRequest or DonorBloodRequest)
            linked_request = getattr(appointment, 'request', None)
            if not linked_request or not isinstance(linked_request, (BloodRequest, DonorBloodRequest)):
                return JsonResponse({
                    'success': False, 
                    'error': 'Appointment not linked to a valid blood request.'
                }, status=400)

            # Validate action
            action = (request.POST.get('action') or '').strip().lower()
            valid_actions = ['approve', 'reject', 'completed', 'cancelled']
            if action not in valid_actions:
                return JsonResponse({
                    'success': False, 
                    'error': f"Invalid action '{action}'. Valid actions: {', '.join(valid_actions)}"
                }, status=400)

            # Check if already finalized
            finalized_statuses = ['completed', 'cancelled', 'rejected']
            if appointment.status in finalized_statuses or linked_request.status in finalized_statuses:
                return JsonResponse({
                    'success': False, 
                    'error': f'This request has already been {appointment.status}. No further changes allowed.'
                }, status=400)

            # Get reason for reject/cancel actions
            reason = (request.POST.get('reason') or '').strip()

            # Helper function to update statuses
            def update_status(app_status, req_status, **kwargs):
                appointment.status = app_status
                appointment.save()

                old_status = linked_request.status
                linked_request.status = req_status
                
                # Update specific fields based on action
                for field, value in kwargs.items():
                    setattr(linked_request, field, value)
                
                linked_request.save()
                
                logger.info(f"Nurse {nurse.user.username} changed blood request {linked_request.id} from '{old_status}' to '{req_status}'")
                
                return f'Blood request {req_status} successfully by nurse {nurse.user.get_full_name()}.'

            # Handle different actions
            if action == 'approve':
                if linked_request.approved_by_nurse:
                    return JsonResponse({
                        'success': False, 
                        'error': 'This request has already been approved.'
                    }, status=400)
                
                message = update_status('approved', 'approved', 
                                      approved_by_nurse=nurse, 
                                      approved_at_nurse=now)
                
                return JsonResponse({
                    'success': True,
                    'status': 'approved',
                    'message': message,
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p")
                })

            elif action == 'reject':
                message = update_status('rejected', 'rejected',
                                      rejected_by='nurse',
                                      rejected_at=now,
                                      rejection_reason=reason)
                
                return JsonResponse({
                    'success': True,
                    'status': 'rejected',
                    'message': f'{message}' + (f' Reason: {reason}' if reason else ''),
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p")
                })

            elif action == 'cancelled':
                message = update_status('cancelled', 'cancelled',
                                      cancelled_by='nurse',
                                      cancelled_at=now,
                                      cancellation_reason=reason)
                
                return JsonResponse({
                    'success': True,
                    'status': 'cancelled',
                    'message': f'{message}' + (f' Reason: {reason}' if reason else ''),
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p")
                })

            elif action == 'completed':
                # Validate that request is approved first
                if appointment.status != 'approved':
                    return JsonResponse({
                        'success': False, 
                        'error': 'Request must be approved before completion.'
                    }, status=400)

                # Get and validate blood group and units
                new_bg = request.POST.get('bloodgroup', '').strip()
                new_unit = request.POST.get('unit', '').strip()

                if new_bg:
                    valid_bgs = [bg[0] for bg in BloodRequest.BLOOD_GROUP_CHOICES]
                    if new_bg not in valid_bgs:
                        return JsonResponse({
                            'success': False, 
                            'error': f'Invalid blood group: {new_bg}'
                        }, status=400)

                units_value = None
                if new_unit:
                    try:
                        units_value = int(new_unit)
                        if units_value < 450 or units_value > 2700 or units_value % 50 != 0:
                            raise ValueError()
                    except ValueError:
                        return JsonResponse({
                            'success': False, 
                            'error': 'Units must be between 450-2700 ml in multiples of 50.'
                        }, status=400)

                # Update request details if provided
                if new_bg and new_bg != linked_request.bloodgroup:
                    linked_request.bloodgroup = new_bg
                if units_value is not None and units_value != linked_request.unit:
                    linked_request.unit = units_value
                
                # Get donation center
                center = linked_request.donation_center
                if not center:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Donation center not specified for this request.'
                    }, status=400)

                # Check stock availability
                stock = Stock.objects.filter(center=center, bloodgroup=linked_request.bloodgroup).first()
                available_units = stock.unit if stock else 0
                
                if available_units < linked_request.unit:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Insufficient stock: Only {available_units} ml of {linked_request.bloodgroup} blood available at {center.name}. Required: {linked_request.unit} ml.'
                    }, status=400)

                # Prevent duplicate stock deduction
                if linked_request.stock_deducted:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Stock has already been deducted for this request.'
                    }, status=400)

                # Perform FIFO stock deduction
                success, deduction_result = deduct_stock_fifo(center, linked_request.bloodgroup, linked_request.unit)
                
                if not success:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Stock deduction failed: {deduction_result}'
                    }, status=400)

                # Create stock transactions for audit trail
                for deduction in deduction_result:
                    try:
                        stock_unit = StockUnit.objects.get(barcode=deduction['barcode'])
                        
                        # Create transaction with appropriate request link
                        transaction_data = {
                            'stockunit': stock_unit,
                            'appointment': appointment,
                            'quantity_deducted': deduction['quantity'],
                            'transaction_type': 'deduction',
                            'user': nurse.user,
                            'notes': f"Blood request completion - {linked_request.unit}ml {linked_request.bloodgroup}"
                        }
                        
                        # Link to the appropriate request type
                        if isinstance(linked_request, BloodRequest):
                            transaction_data['blood_request'] = linked_request
                        elif isinstance(linked_request, DonorBloodRequest):
                            transaction_data['donor_blood_request'] = linked_request
                            
                        StockTransaction.objects.create(**transaction_data)
                        
                    except StockUnit.DoesNotExist:
                        logger.warning(f"StockUnit {deduction['barcode']} not found during transaction logging.")

                # Update stock totals
                stock.unit -= linked_request.unit
                stock.save()

                # Mark request as completed and stock deducted
                message = update_status('completed', 'completed',
                                      completed_by_nurse=nurse,
                                      completed_at_nurse=now,
                                      stock_deducted=True)

                # Store deduction details in session for potential display
                request.session['last_stock_deductions'] = serialize_deductions(deduction_result)

                return JsonResponse({
                    'success': True,
                    'status': 'completed',
                    'message': f'{message} Successfully deducted {linked_request.unit}ml of {linked_request.bloodgroup} blood from stock.',
                    'action_by': nurse.user.get_full_name(),
                    'when': now.strftime("%b %d, %Y %I:%M %p"),
                    'deductions': len(deduction_result)
                })

            else:
                return JsonResponse({
                    'success': False, 
                    'error': f'Unhandled action: {action}'
                }, status=400)

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'error': 'Appointment not found. It may have been deleted.'
        }, status=404)
    except Exception as e:
        logger.error(f"Error updating blood request appointment {appointment_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False, 
            'error': 'An unexpected error occurred. Please refresh and try again, or contact support if the problem persists.'
        }, status=500)
# ---------------------------
# Nurse Profile View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_profile_view(request, pk):
    """
    View nurse's profile page and allow profile update via POST if desired.
    """
    nurse = get_object_or_404(Nurse, pk=pk)

    if request.method == 'POST':
        form = NurseForm(request.POST, request.FILES, instance=nurse)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('nurse-profile', pk=nurse.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NurseForm(instance=nurse)

    context = {
        'nurse': nurse,
        'form': form,
    }
    return render(request, 'nurse/nurse_profile.html', context)


@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_profile_edit_view(request, pk):
    """
    Allow a nurse to edit their own profile (User + Nurse models).
    """
    nurse = get_object_or_404(Nurse, pk=pk)

    # Ensure only profile owner can edit
    if request.user != nurse.user:
        messages.error(request, "You are not authorized to edit this profile.")
        return redirect('nurse-profile', pk=nurse.pk)

    if request.method == "POST":
        user_form = NurseUserForm(request.POST, instance=nurse.user)
        nurse_form = NurseForm(request.POST, request.FILES, instance=nurse)

        # Handle profile picture removal
        if 'clear_profile_pic' in request.POST:
            if nurse.profile_pic:
                nurse.profile_pic.delete(save=False)
            nurse.profile_pic = None

        if user_form.is_valid() and nurse_form.is_valid():
            try:
                with transaction.atomic():
                    user_form.save()
                    nurse_form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect('nurse-profile', pk=nurse.pk)
            except Exception as e:
                messages.error(request, f"An error occurred while saving: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        user_form = NurseUserForm(instance=nurse.user)
        nurse_form = NurseForm(instance=nurse)

    context = {
        "user_form": user_form,
        "nurse_form": nurse_form,
        "nurse": nurse,
    }
    return render(request, "nurse/nurse_profile_edit.html", context)
# ---------------------------
# Notifications View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def nurse_notifications_view(request):
    nurse = get_object_or_404(Nurse, user=request.user)
    nurse_ct = ContentType.objects.get_for_model(Nurse)

    notifications = Notification.objects.filter(
        recipient_content_type=nurse_ct,
        recipient_object_id=nurse.id
    ).order_by('-created_at')

    unread_count = notifications.filter(read=False).count()

    return render(request, 'nurse/nurse_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def mark_nurse_notification_read(request, pk):
    nurse = get_object_or_404(Nurse, user=request.user)
    nurse_ct = ContentType.objects.get_for_model(Nurse)

    notification = get_object_or_404(
        Notification,
        id=pk,
        recipient_content_type=nurse_ct,
        recipient_object_id=nurse.id
    )
    notification.read = True
    notification.save()

    return redirect('nurse-notifications')
# ---------------------------
# Nurse Donation Bookings View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_donation_bookings(request):
    nurse = request.user.nurse
    donation_content_type = ContentType.objects.get_for_model(BloodDonate)
    
    # Debug: total appointments
    all_appointments = Appointment.objects.filter(nurse=nurse)
    print(f"Total appointments for nurse {nurse}: {all_appointments.count()}")
    
    # Debug: appointments of donation type
    donation_appointments = Appointment.objects.filter(
        nurse=nurse,
        request_content_type=donation_content_type,
    )
    print(f"Donation appointments for nurse {nurse}: {donation_appointments.count()}")
    
    # Fetch donor donation appointments with select_related for efficiency
    donor_donations = donation_appointments.filter(
        donor__isnull=False,
    ).select_related(
        'donor',
        'donor__user',
        'nurse',
        'nurse__user'
    ).order_by('-date')
    
    # Note: Prefetching the reverse GenericRelation here causes issues, so we avoid it.
    # Instead, we will access appointment.request (the BloodDonate instance) in template lazily.
    
    # Debug: Print appointment details safely after querying
    for appointment in donor_donations:
        print(f"Appointment ID: {appointment.id}")
        print(f"Donor: {appointment.donor}")
        print(f"Date: {appointment.date}")
        print(f"Request Content Type: {appointment.request_content_type}")
        print(f"Request Object ID: {appointment.request_object_id}")
        
        # Attempt to access related BloodDonate safely
        related_blood_donate = getattr(appointment, 'request', None)
        if related_blood_donate:
            print(f"Related BloodDonate: {related_blood_donate}")
            print(f"Blood Group: {related_blood_donate.bloodgroup}")
            print(f"Unit: {related_blood_donate.unit}")
        else:
            print(f"No related BloodDonate found for appointment {appointment.id}")
        print("---")
    
    context = {
        'donor_donations': donor_donations,
        'blood_group_choices': BLOODGROUP_CHOICES,
    }
    return render(request, 'nurse/nurse_donation_bookings.html', context)
# ---------------------------
# Nurse Blood Stock View
# ---------------------------

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse)
def nurse_blood_stock(request):
    nurse = get_object_or_404(Nurse, user=request.user)

    blood_stock_totals = []

    if nurse.donation_center:
        # --- SEARCH FILTER ---
        query = request.GET.get("q", "").strip()

        stockunits_qs = StockUnit.objects.filter(center=nurse.donation_center, unit__gt=0)

        if query:
            stockunits_qs = stockunits_qs.filter(
                Q(bloodgroup__icontains=query) |  # Search by blood group
                Q(unit__iexact=query) |           # Search by stock units
                Q(barcode__icontains=query)       # Search by barcode
            )

        # Aggregate stock details
        bloodgroup_qs = (
            stockunits_qs.values('bloodgroup')
            .annotate(
                total_units=Sum('unit'),
                earliest_expiry=Min('expiry_date'),
                batches_count=Count('id')
            )
            .order_by('bloodgroup')
        )

        for group in bloodgroup_qs:
            # List all batches for this blood group, sorted by expiry
            group_batches = stockunits_qs.filter(
                bloodgroup=group['bloodgroup']
            ).order_by('expiry_date')
            group['detailed_batches'] = group_batches
            blood_stock_totals.append(group)

    all_centres = DonationCenter.objects.all().order_by('name')

    selected_centre_id = request.GET.get('centre')
    other_centers_stock = None
    selected_centre = None

    if selected_centre_id:
        try:
            selected_centre = DonationCenter.objects.get(id=selected_centre_id)
            other_centers_stock = Stock.objects.filter(center=selected_centre)
        except DonationCenter.DoesNotExist:
            selected_centre = None
            other_centers_stock = None

    context = {
        'nurse': nurse,
        'blood_stock_totals': blood_stock_totals,
        'all_centres': all_centres,
        'selected_centre': selected_centre,
        'other_centers_stock': other_centers_stock,
        'today_date': localdate(),
        'query': query,  # keep search term in template
    }
    return render(request, 'nurse/blood_stock.html', context)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_stockunit_list(request, highlight_id=None):
    nurse = get_object_or_404(Nurse, user=request.user)
    center = nurse.donation_center

    search_query = request.GET.get('q', '').strip()  # get search query parameter 'q'

    stockunits = StockUnit.objects.filter(center=center)
    if search_query:
        stockunits = stockunits.filter(
            Q(barcode__icontains=search_query) | Q(bloodgroup__icontains=search_query)
        )

    stockunits = stockunits.order_by('-added_on')

    # Aggregate deductions per stockunit
    deductions = StockTransaction.objects.filter(
        transaction_type='deduction',
        stockunit__center=center
    ).values('stockunit').annotate(total_deducted=Sum('quantity_deducted'))

    deducted_map = {item['stockunit']: item['total_deducted'] for item in deductions}

    stockunits_info = []
    for unit in stockunits:
        deducted = deducted_map.get(unit.id, 0) or 0
        remaining = unit.unit - deducted
        stockunits_info.append({
            'unit': unit,
            'deducted': deducted,
            'remaining': remaining,
        })

    context = {
        'stockunits_info': stockunits_info,
        'highlight_id': highlight_id,
        'search_query': search_query,
    }
    return render(request, 'nurse/stockunit_list.html', context)

@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def nurse_stock_deductions(request, appointment_id):
    """
    Display the stock units deducted for a finalized blood request appointment.
    """
    deductions = request.session.pop('last_stock_deductions', None)
    if not deductions:
        messages.warning(request, "No recent stock deductions found.")
        return redirect('nurse-dashboard')

    context = {
        'deductions': deductions,
        'appointment_id': appointment_id
    }
    return render(request, 'nurse/stock_deductions.html', context)
# ---------------------------
# Create Blood Request View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def create_blood_request(request):
    nurse = get_object_or_404(Nurse, user=request.user)

    blood_group_prefill = request.GET.get('blood_group', '').upper()

    low_stock_threshold = 500
    sufficient_centres = []
    if blood_group_prefill:
        stocks = Stock.objects.filter(
            bloodgroup=blood_group_prefill,
            unit__gt=low_stock_threshold
        )
        sufficient_centres = stocks.values_list('center__id', 'center__name').distinct().order_by('center__name')

    if request.method == 'POST':
        form = BloodRequestForm(request.POST)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.requester = nurse
            blood_request.status = 'pending'
            blood_request.save()
            return redirect('nurse-dashboard')  # Adjust redirect as appropriate
    else:
        initial = {}
        if blood_group_prefill:
            initial['blood_group'] = blood_group_prefill
        form = BloodRequestForm(initial=initial)

    context = {
        'form': form,
        'blood_group_prefill': blood_group_prefill,
        'nurse': nurse,
        'sufficient_centres': sufficient_centres,
    }
    return render(request, 'nurse/create_blood_request.html', context)


# ---------------------------
# List Blood Requests View
# ---------------------------
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(is_nurse, login_url='/nurse/nurselogin/')
def list_blood_requests(request):
    nurse = get_object_or_404(Nurse, user=request.user)
    requests = NurseBloodRequest.objects.filter(requester=nurse).order_by('-created_at')
    context = {
        'requests': requests
    }
    return render(request, 'nurse/blood_requests_list.html', context)

@login_required(login_url='/nurse/nurselogin/')
def ajax_booked_timeslots(request):
    nurse_id = request.GET.get('nurse_id')
    date_str = request.GET.get('date')  # Expected format 'dd-mm-YYYY'

    if not nurse_id or not date_str:
        return JsonResponse({'booked_times': []})

    try:
        nurse = Nurse.objects.filter(id=nurse_id).first()
        if not nurse:
            return JsonResponse({'booked_times': []})

        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()



        appointments = Appointment.objects.filter(
            nurse=nurse,
            date__date=date_obj,
            status__in=['pending', 'approved']
        )

        booked_times = [appt.date.strftime('%I:%M %p') for appt in appointments]

        return JsonResponse({'booked_times': booked_times})

    except Exception as e:
        print("Error in ajax_booked_timeslots:", e)
        return JsonResponse({'booked_times': []})
@login_required(login_url='/nurse/nurselogin/')
@user_passes_test(lambda u: hasattr(u, 'nurse'), login_url='/nurse/nurselogin/')
def debug_donation_bookings(request):
    nurse = request.user.nurse
    
    print(f"=== DEBUG: Starting debug for nurse: {nurse} ===")
    
    # 1. Check all appointments for this nurse
    all_appointments = Appointment.objects.filter(nurse=nurse)
    print(f"Total appointments for this nurse: {all_appointments.count()}")
    
    for apt in all_appointments:
        print(f"  - Appointment {apt.id}: donor={apt.donor}, patient={apt.patient}, content_type={apt.request_content_type}")
    
    # 2. Check BloodDonate content type
    try:
        donation_content_type = ContentType.objects.get_for_model(BloodDonate)
        print(f"BloodDonate ContentType: {donation_content_type}")
    except Exception as e:
        print(f"ERROR getting BloodDonate ContentType: {e}")
        donation_content_type = None
    
    # 3. Check appointments with donation content type
    if donation_content_type:
        donation_appointments = Appointment.objects.filter(
            nurse=nurse,
            request_content_type=donation_content_type
        )
        print(f"Appointments with BloodDonate content type: {donation_appointments.count()}")
        
        for apt in donation_appointments:
            print(f"  - Appointment {apt.id}: object_id={apt.request_object_id}")
            
            # Try to get the related BloodDonate
            try:
                blood_donate = BloodDonate.objects.get(id=apt.request_object_id)
                print(f"    Related BloodDonate: {blood_donate}")
            except BloodDonate.DoesNotExist:
                print(f"    ERROR: No BloodDonate with ID {apt.request_object_id}")
    
    # 4. Check all BloodDonate objects for this nurse
    blood_donates = BloodDonate.objects.filter(nurse=nurse)
    print(f"BloodDonate objects assigned to this nurse: {blood_donates.count()}")
    
    for bd in blood_donates:
        print(f"  - BloodDonate {bd.id}: donor={bd.donor}, status={bd.status}")
    
    # Get the actual query for the template
    donor_donations = Appointment.objects.filter(
        nurse=nurse,
        request_content_type=donation_content_type,
        donor__isnull=False,
    ).select_related('donor', 'donor__user', 'nurse', 'nurse__user')
    
    print(f"Final query result: {donor_donations.count()} appointments")
    
    context = {
        'donor_donations': donor_donations,
        'blood_group_choices': BLOODGROUP_CHOICES,
        'debug_info': {
            'total_appointments': all_appointments.count(),
            'donation_appointments': donation_appointments.count() if donation_content_type else 0,
            'nurse_blood_donates': blood_donates.count(),
        }
    }
    return render(request, 'nurse/debug_donation_bookings.html', context)
