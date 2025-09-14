from datetime import datetime,timedelta
import json
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.utils.safestring import mark_safe
from django.core.serializers.json import DjangoJSONEncoder
from django.views.decorators.http import require_GET
from nurse.models import Nurse, Appointment
from .models import Donor, DonorEligibility, BloodDonate

from .forms import (
    DonorUserForm, DonorForm, DonorProfileForm, DonorEligibilityForm,
    BloodDonateForm, DonorLoginForm
)
from django.core.exceptions import PermissionDenied
from blood.models import Notification, BloodRequest, DonationCenter,DonorBloodRequest
from nurse.forms import AppointmentForm
from blood.utils.geolocation import find_nearby_compatible_patients
from datetime import date
import logging
from django.db import transaction
from blood.forms import DonorBloodRequestForm
from django.core.exceptions import ValidationError
def donor_signup_view(request):
    """
    Handles donor registration including user info and donor profile.
    Assigns new users to the DONOR group.
    """
    if request.method == 'POST':
        user_form = DonorUserForm(request.POST)
        donor_form = DonorForm(request.POST, request.FILES)

        if user_form.is_valid() and donor_form.is_valid():
            try:
                user = user_form.save()

                donor = donor_form.save(commit=False)
                donor.user = user
                donor.save()

                donor_group, _ = Group.objects.get_or_create(name='DONOR')
                donor_group.user_set.add(user)

                messages.success(request, "Signup successful! You can now log in below...")
                return redirect('donorlogin')
            except Exception as e:
                messages.error(request, f"An error occurred during signup: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        user_form = DonorUserForm()
        donor_form = DonorForm()

    return render(request, 'donor/donorsignup.html', {
        'user_form': user_form,
        'donor_form': donor_form
    })


def donorlogin_view(request):
    """
    Handles donor login.
    Restricts login to users in DONOR group only.
    Redirects to eligibility form if not completed.
    Supports redirecting to 'next' url after successful login.
    """
    next_url = request.GET.get('next') or request.POST.get('next') or None

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                if user.groups.filter(name='DONOR').exists():
                    login(request, user)

                    try:
                        donor = Donor.objects.get(user=user)
                        eligibility_completed = DonorEligibility.objects.filter(donor=donor).exists()
                    except Donor.DoesNotExist:
                        eligibility_completed = False

                    # Redirect in priority order
                    if next_url:
                        return redirect(next_url)
                    if not eligibility_completed:
                        messages.info(request, "Please complete your eligibility form before accessing your dashboard.")
                        return redirect('donor-eligibility')

                    messages.success(request, "You have logged in successfully.")
                    return redirect('donor-dashboard')
                else:
                    messages.error(request, "You are not authorized to log in as a donor.")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "There was an error in your form. Please correct it.")
    else:
        form = AuthenticationForm()

    return render(request, 'donor/donorlogin.html', {
        'form': form,
        'next': next_url,
    })


def needs_eligibility_check(user):
    """
    Returns True if donor exists but has NOT completed eligibility form.
    """
    try:
        donor = Donor.objects.get(user=user)
    except Donor.DoesNotExist:
        return False
    return not DonorEligibility.objects.filter(donor=donor).exists()


logger = logging.getLogger(__name__)

@login_required(login_url='donorlogin')
def donor_dashboard_view(request):
    user = request.user
    logger.debug(f"Accessing donor dashboard for user '{user.username}'")

    # Early eligibility check and redirect if necessary
    if needs_eligibility_check(user):
        messages.info(request, "Please complete your eligibility form before accessing your dashboard.")
        logger.debug(f"User '{user.username}' redirected to eligibility form")
        return redirect('donor-eligibility')

    # Fetch donor object, log if missing
    try:
        donor = get_object_or_404(Donor, user=user)
        logger.debug(f"Donor object id {donor.id} loaded for user '{user.username}'")
    except Exception as e:
        logger.error(f"Donor profile missing or error for user '{user.username}': {e}")
        messages.error(request, "Donor profile not found. Please contact support.")
        return redirect('donorlogin')

    # Last approved donation
    last_approved_donation = BloodDonate.objects.filter(donor=donor, status='Approved').order_by('-date').first()
    if last_approved_donation:
        if not donor.last_donation_date or donor.last_donation_date < last_approved_donation.date:
            donor.last_donation_date = last_approved_donation.date
            donor.save(update_fields=['last_donation_date'])
            logger.debug(f"Updated last_donation_date for donor id {donor.id}")

        next_donation_date = donor.next_eligible_donation_date()
        days_until_next = donor.days_until_next_donation()
        next_donation_date_iso = next_donation_date.isoformat() if next_donation_date else None
    else:
        next_donation_date = None
        days_until_next = None
        next_donation_date_iso = None

    # Points calculation and update if necessary
    total_donations = BloodDonate.objects.filter(donor=donor, status='Approved').count()
    points_per_donation = 10
    computed_points = total_donations * points_per_donation

    if donor.points != computed_points:
        donor.points = computed_points
        donor.save(update_fields=['points'])
        logger.debug(f"Updated points to {computed_points} for donor id {donor.id}")

    # Progress calculation for display
    goal = 10
    progress = min(int((total_donations / goal) * 100), 100) if goal else 0
    circumference = 2 * 3.1416 * 65  # Approx circumference for progress circle
    stroke_dashoffset = circumference * (1 - progress / 100)

    # Blood request stats
    request_made = DonorBloodRequest.objects.filter(request_by_donor=donor).count()
    request_pending = DonorBloodRequest.objects.filter(request_by_donor=donor, status='pending').count()
    request_approved = DonorBloodRequest.objects.filter(request_by_donor=donor, status='approved').count()
    request_rejected = DonorBloodRequest.objects.filter(request_by_donor=donor, status='rejected').count()

    dashboard_stats = [
        {'icon': 'fa-paper-plane', 'label': 'Requests Made', 'count': request_made, 'color': 'requests-made-icon'},
        {'icon': 'fa-clock', 'label': 'Pending Requests', 'count': request_pending, 'color': 'pending-requests-icon'},
        {'icon': 'fa-check-circle', 'label': 'Approved Requests', 'count': request_approved, 'color': 'approved-requests-icon'},
        {'icon': 'fa-times-circle', 'label': 'Rejected Requests', 'count': request_rejected, 'color': 'rejected-requests-icon'},
    ]

    info_cards = [
        {'icon': 'fa-heartbeat', 'title': 'Health Tips', 'desc': 'Stay hydrated and eat healthy foods before donating blood.', 'url': 'health_tips'},
        {'icon': 'fa-question-circle', 'title': 'FAQs', 'desc': 'Find answers to common questions about blood donation.', 'url': 'faqs'},
        {'icon': 'fa-comments', 'title': 'Donor Advice', 'desc': 'How to prepare for your next donation and what to expect.', 'url': 'donor_advice'},
        {'icon': 'fa-book', 'title': 'Donor Resources', 'desc': 'Learn more about blood donation processes and guidelines.', 'url': 'donor_resources'},
    ]

    context = {
        'user': user,
        'donor': donor,
        'points': donor.points,
        'next_donation_date': next_donation_date.strftime("%b %d, %Y") if next_donation_date else None,
        'days_until_next': days_until_next,
        'next_donation_date_iso': next_donation_date_iso,
        'progress': progress,
        'goal': goal,
        'total_donations': total_donations,
        'stroke_dashoffset': stroke_dashoffset,
        'dashboard_stats': dashboard_stats,
        'info_cards': info_cards,
    }
    logger.debug(f"Rendering donor dashboard for user '{user.username}'")
    return render(request, 'donor/donor_dashboard.html', context)
logger = logging.getLogger(__name__)

@login_required(login_url='donorlogin')
def donate_blood_view(request):
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "⚠️ You must complete your donor profile before donating blood.")
        return redirect('donor-profile')

    now = timezone.now()
    blocking_statuses = ['pending', 'approved']

    # Check for active donation
    active_donation = BloodDonate.objects.filter(
        donor=donor,
        status__in=blocking_statuses
    ).first()

    if active_donation:
        messages.warning(
            request,
            "⚠️ You already have an active donation request. "
            "Please complete or cancel it before making a new request."
        )
        return render(request, 'donor/donate_blood.html', {
            'donation_form': BloodDonateForm(donor=donor),
            'donor': donor,
            'active_donation': active_donation
        })

    # Check eligibility
    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        messages.info(request, "ℹ️ Please complete your eligibility form before donating blood.")
        return redirect('donor-eligibility')

    if not eligibility.approved:
        messages.warning(request, "⚠️ Your eligibility has not been approved yet. Please wait for approval.")
        return redirect('donor-eligibility')

    if request.method == 'POST':
        donate_form = BloodDonateForm(request.POST, donor=donor)

        if donate_form.is_valid():
            try:
                with transaction.atomic():
                    # Update user profile
                    user = request.user
                    user.first_name = donate_form.cleaned_data.get('first_name', user.first_name)
                    user.last_name = donate_form.cleaned_data.get('last_name', user.last_name)
                    user.save()

                    # Update donor profile
                    donor.mobile = donate_form.cleaned_data.get('mobile', donor.mobile)
                    donor.save()

                    # Create donation request
                    donation = donate_form.save(commit=False)
                    donation.donor = donor
                    donation.status = 'pending'
                    donation.save()

                    donation_ct = ContentType.objects.get_for_model(BloodDonate)
                    logger.debug(f"BloodDonate ContentType: {donation_ct}")
                    logger.debug(f"Created BloodDonate ID: {donation.id}")

                    # Get appointment datetime from form data
                    appointment_date = donate_form.cleaned_data.get('appointment_date')
                    appointment_time_str = donate_form.cleaned_data.get('appointment_time')

                    if not appointment_date or not appointment_time_str:
                        messages.error(request, "❌ Please select a valid appointment date and time.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor
                        })

                    try:
                        appointment_time = datetime.strptime(appointment_time_str.strip(), '%I:%M %p').time()
                    except (ValueError, TypeError):
                        messages.error(request, "❌ Invalid appointment time format. Please select a valid time.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor
                        })

                    appointment_datetime = timezone.make_aware(datetime.combine(appointment_date, appointment_time))

                    # Get nurse from form
                    nurse = donate_form.cleaned_data.get('nurse')
                    if not nurse:
                        messages.error(request, "❌ Please select a nurse.")
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor
                        })

                    # Check for scheduling conflicts
                    appointment_duration = timedelta(minutes=30)
                    conflict_exists = Appointment.objects.filter(
                        nurse=nurse,
                        date__lt=appointment_datetime + appointment_duration,
                        date__gte=appointment_datetime,
                        status__in=['pending', 'approved']
                    ).exists()

                    if conflict_exists:
                        messages.error(
                            request,
                            f"❌ Nurse {nurse.user.get_full_name()} is already booked during this slot. Please select a different time."
                        )
                        return render(request, 'donor/donate_blood.html', {
                            'donation_form': donate_form,
                            'donor': donor
                        })

                    # Create appointment linked to the saved donation within the atomic block
                    appointment = Appointment.objects.create(
                        donor=donor,
                        patient=None,
                        nurse=nurse,
                        date=appointment_datetime,
                        status='pending',
                        request_content_type=donation_ct,
                        request_object_id=donation.id,
                    )

                    logger.debug(f"Created Appointment ID: {appointment.id}")

                # After transaction success, send notification
                if nurse:
                    Notification.objects.create(
                        title="🩸 New Blood Donation Appointment",
                        message=f"Donor {donor.user.get_full_name()} scheduled a donation on "
                                f"{appointment_datetime.strftime('%b %d, %Y %I:%M %p')}.",
                        recipient=nurse,
                        sender=donor,
                    )

                messages.success(request, "✅ Your donation request and appointment were submitted successfully!")
                return redirect('donation-history')

            except ValidationError as ve:
                messages.error(request, f"❌ Validation Error: {str(ve)}")
                logger.error(f"Validation Error: {ve}")
            except Exception as e:
                messages.error(request, f"❌ An error occurred: {str(e)}")
                logger.exception("Exception during donate_blood_view POST")
        else:
            messages.error(request, "⚠️ Please correct the errors in the form below.")
            logger.debug(f"Form errors: {donate_form.errors}")
    else:
        donate_form = BloodDonateForm(donor=donor)

    return render(request, 'donor/donate_blood.html', {
        'donation_form': donate_form,
        'donor': donor,
        'active_donation': None
    })
@login_required(login_url='donorlogin')
def donation_history_view(request):
    try:
        donor_instance = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "No donor profile found for this user.")
        return redirect('donor-profile')

    donations = BloodDonate.objects.filter(donor=donor_instance).order_by('-date')
    has_donations = donations.exists()

    # Get all related appointments linked to these donations
    content_type = ContentType.objects.get_for_model(BloodDonate)
    appointments = Appointment.objects.filter(
        request_content_type=content_type,
        request_object_id__in=donations.values_list('id', flat=True)
    )
    appointment_map = {appt.request_object_id: appt for appt in appointments}

    for donation in donations:
        donation.appointment = appointment_map.get(donation.id)
        # Prefer appointment status if set for display, fallback to donation status
        if donation.appointment and donation.appointment.status:
            donation.display_status = donation.appointment.status
        else:
            donation.display_status = donation.status

    # Optional chart data for frontend if you use visualization
    labels = [donation.date.strftime("%b %d, %Y") for donation in donations]
    data = [donation.unit for donation in donations]

    return render(request, 'donor/donation_history.html', {
        'donations': donations,
        'has_donations': has_donations,
        'labels': json.dumps(labels),
        'data': json.dumps(data),
    })
@login_required(login_url='donorlogin')
def cancel_donation_request_view(request, donation_id):
    """
    Allow donors to cancel their own donation request & linked appointment,
    only if still in 'pending' or 'approved' status and scheduled for the future.
    """
    user = request.user
    donation = get_object_or_404(BloodDonate, id=donation_id)

    if not hasattr(user, 'donor') or donation.donor.user != user:
        raise PermissionDenied("You do not have permission to cancel this donation.")

    if donation.status.lower() in ['completed', 'rejected', 'cancelled']:
        messages.warning(request, "This donation has already been finalized and cannot be cancelled.")
        return redirect('donation-history')

    content_type = ContentType.objects.get_for_model(BloodDonate)
    appointment = Appointment.objects.filter(
        donor=user.donor,
        request_content_type=content_type,
        request_object_id=donation.id,
    ).first()

    now = timezone.now()

    if not appointment:
        messages.warning(request, "No appointment found to cancel for this donation.")
        return redirect('donation-history')

    if appointment.date <= now:
        messages.warning(request, "This appointment cannot be cancelled because the date/time has passed or is ongoing.")
        return redirect('donation-history')

    if appointment.status.lower() in ['completed', 'rejected', 'cancelled']:
        messages.warning(request, "This appointment has already been finalized and cannot be cancelled.")
        return redirect('donation-history')

    # Cancel donation
    if donation.status.lower() in ['pending', 'approved']:
        donation.status = 'cancelled'
        donation.save(update_fields=['status'])
        logger.info(f"Donation ID {donation.id} cancelled by donor {user.id}.")

    # Cancel appointment
    if appointment.status.lower() in ['pending', 'approved']:
        appointment.status = 'cancelled'
        appointment.cancelled_by = 'donor'
        appointment.cancelled_by_user = user
        appointment.cancelled_at = now
        appointment.status_changed_by = user
        appointment.status_changed_at = now
        appointment.save()
        logger.info(f"Appointment ID {appointment.id} cancelled by donor {user.id}.")

        # Notify nurses at the donation center
        try:
            center = getattr(appointment, 'donation_center', None) or getattr(donation, 'donation_center', None)
            nurses = Nurse.objects.filter(donation_center=center) if center else Nurse.objects.all()
            for nurse in nurses:
                Notification.objects.create(
                    title="Donation Appointment Cancelled",
                    message=(
                        f"Donor {user.get_full_name() or user.username} cancelled their donation appointment "
                        f"(ID: {appointment.id}) scheduled for {appointment.date.strftime('%b %d, %Y %I:%M %p')}."
                    ),
                    recipient=nurse,
                    sender=user.donor
                )
            logger.info(f"Nurses at {center} notified about donor cancellation (Appointment ID: {appointment.id}).")
        except Exception as e:
            logger.warning(f"Failed to notify nurses about donor cancellation (Appointment ID: {appointment.id}): {e}")

    messages.success(request, "Your donation request and appointment have been cancelled successfully.")
    return redirect('donation-history')
@login_required(login_url='donorlogin')
def request_history_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    blood_requests = BloodRequest.objects.filter(request_by_donor=donor).order_by('-created_at')

    status_counts = blood_requests.values('status').annotate(count=Count('status'))

    labels = [entry['status'] for entry in status_counts]
    data = [entry['count'] for entry in status_counts]

    return render(request, 'donor/request_history.html', {
        'blood_requests': blood_requests,
        'labels': json.dumps(labels),
        'data': json.dumps(data),
        'user': request.user,   # pass user explicitly to template
    })


@login_required(login_url='donorlogin')
def donor_profile_view(request):
    donor = get_object_or_404(Donor, user=request.user)
    user = request.user

    # Calculate next eligible donation date, days until next donation
    next_donation_date = donor.next_eligible_donation_date()
    days_until_next = donor.days_until_next_donation()

    context = {
        'donor': donor,
        'user': user,
        'next_donation_date': next_donation_date,
        'days_until_next': days_until_next,
    }
    return render(request, 'donor/donor_profile.html', context)
@login_required(login_url='donorlogin')
def donor_edit_profile_view(request):
    try:
        donor = Donor.objects.get(user=request.user)
    except Donor.DoesNotExist:
        messages.error(request, "Please create a donor profile first.")
        return redirect('create-donor-profile')

    user = request.user

    if request.method == 'POST':
        form = DonorProfileForm(request.POST, request.FILES, instance=donor)
        
        # Handle latitude and longitude from POST explicitly (if using hidden fields or from JS)
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')
        if lat:
            try:
                donor.latitude = float(lat)
            except ValueError:
                messages.warning(request, "Invalid latitude value.")
        if lon:
            try:
                donor.longitude = float(lon)
            except ValueError:
                messages.warning(request, "Invalid longitude value.")

        if form.is_valid():
            # Update first and last names on User
            user.first_name = form.cleaned_data.get('first_name', user.first_name)
            user.last_name = form.cleaned_data.get('last_name', user.last_name)
            user.save()

            # Handle base64 cropped image if provided
            cropped_image_data = request.POST.get('cropped_image')
            if cropped_image_data:
                try:
                    format, imgstr = cropped_image_data.split(';base64,')
                    ext = format.split('/')[-1]
                    data = ContentFile(base64.b64decode(imgstr), name='profile.' + ext)
                    donor.profile_pic = data
                except Exception as e:
                    messages.error(request, f"Error processing cropped image: {e}")

            # Save Donor instance with updated data including lat/lon updated above
            donor = form.save(commit=False)
            # Just ensure lat/lon saved here as well (in case they were set above)
            if lat:
                donor.latitude = float(lat)
            if lon:
                donor.longitude = float(lon)
            donor.save()

            messages.success(request, "Profile updated successfully!")
            return redirect('donor-profile')

        else:
            messages.error(request, "Please correct the errors in the form.")

    else:
        # initial data for first_name and last_name come from User model
        form = DonorProfileForm(instance=donor, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
        })

    context = {
        'profile_form': form,
        'donor': donor,
        'user': user,
    }
    return render(request, 'donor/donor_edit_profile.html', context)

@login_required(login_url='donorlogin')
def donor_eligibility_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        eligibility = None

    age = DonorEligibilityForm.calculate_age(donor.dob) if donor.dob else None

    if request.method == 'POST':
        form = DonorEligibilityForm(request.POST, instance=eligibility, donor=donor)
        if form.is_valid():
            eligibility_instance = form.save(commit=False)
            eligibility_instance.donor = donor

            # Ensure booleans are properly stored
            eligibility_instance.good_health = bool(eligibility_instance.good_health)
            eligibility_instance.travel_history = bool(eligibility_instance.travel_history)
            eligibility_instance.pregnant = bool(eligibility_instance.pregnant)

            # Eligibility check
            is_eligible = (
                age is not None and 18 <= age <= 65 and
                eligibility_instance.weight >= 50 and
                eligibility_instance.good_health and
                not eligibility_instance.travel_history and
                (eligibility_instance.gender != 'Female' or not eligibility_instance.pregnant)
            )

            eligibility_instance.approved = is_eligible
            eligibility_instance.save()

            if is_eligible:
                messages.success(request, "You are eligible to donate blood.")
            else:
                messages.warning(request, "Thank you for your interest! Currently, you are not eligible to donate blood.")

            return redirect('donor-dashboard')
        else:
            messages.error(request, "There were errors in the form. Please correct them.")
    else:
        form = DonorEligibilityForm(instance=eligibility, donor=donor)

    return render(request, 'donor/donor_eligibility_form.html', {
        'eligibility_form': form,
        'donor_age': age,
    })


@login_required(login_url='donorlogin')
def donor_details_view(request, donor_id):
    donor = get_object_or_404(Donor, pk=donor_id)
    eligibility = DonorEligibility.objects.filter(donor=donor).first()
    donations = BloodDonate.objects.filter(donor=donor)

    return render(request, 'blood/donor_details.html', {
        'donor': donor,
        'eligibility': eligibility,
        'donations': donations,
    })


@login_required(login_url='donorlogin')
def donor_notifications_view(request):
    donor = get_object_or_404(Donor, user=request.user)
    donor_ct = ContentType.objects.get_for_model(donor)

    notifications = Notification.objects.filter(
        recipient_content_type=donor_ct,
        recipient_object_id=donor.id
    ).order_by('-created_at')

    unread_count = notifications.filter(read=False).count()

    return render(request, 'donor/donor_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })
@login_required(login_url='donorlogin')
def mark_notification_read(request, pk):
    donor = get_object_or_404(Donor, user=request.user)
    donor_ct = ContentType.objects.get_for_model(donor)
    notification = get_object_or_404(Notification, id=pk, recipient_content_type=donor_ct, recipient_object_id=donor.id)
    notification.read = True
    notification.save()
    return redirect('donor-notifications')


def health_tips(request):
    return render(request, 'donor/health_tips.html')


def faqs(request):
    return render(request, 'donor/faqs.html')


def donor_advice(request):
    return render(request, 'donor/donor_advice.html')


def donor_resources(request):
    return render(request, 'donor/donor_resources.html')

@login_required(login_url='donorlogin')
def nearby_compatible_patients_view(request):
    user = request.user
    if not hasattr(user, 'donor'):
        messages.error(request, "Donor profile not found.")
        return redirect('donor-dashboard')

    donor = user.donor
    if donor.latitude is None or donor.longitude is None or not donor.bloodgroup:
        messages.error(request, "Please update your location and blood group in profile.")
        return redirect('donor-edit-profile')

    patients = find_nearby_compatible_patients(donor.latitude, donor.longitude, donor.bloodgroup)

    return render(request, 'donor/nearby_compatible_patients.html', {
        'nearby_patients': patients,
        'user_blood_type': donor.bloodgroup,
    })


@login_required(login_url='donorlogin')
def donor_eligibility_status_view(request):
    donor = get_object_or_404(Donor, user=request.user)

    try:
        eligibility = DonorEligibility.objects.get(donor=donor)
    except DonorEligibility.DoesNotExist:
        # Not eligible/no record -> redirect elsewhere or show message
        return redirect('donor-dashboard')  

    if not eligibility.approved:
       
        return redirect('donor-dashboard')

    # Eligible donors only reach here
    last_donation_date_display = "No previous donations recorded."

    last_donation = BloodDonate.objects.filter(donor=donor, status='approved').order_by('-id').first()
    if last_donation and last_donation.appointment_date:
        last_donation_date_display = last_donation.appointment_date.strftime("%B %Y")
    elif last_donation and hasattr(last_donation, 'created_at'):
        last_donation_date_display = last_donation.created_at.strftime("%B %Y")

    context = {
        'eligible': True,
        'last_donation_date': last_donation_date_display,
    }
    return render(request, 'donor/donor_eligibility.html', context)

@login_required(login_url='login')
def donor_make_request_view(request):
    user = request.user
    if not hasattr(user, "donor"):
        raise PermissionDenied("Only donors can make donor-side requests.")

    donor = user.donor
    centers = DonationCenter.objects.all()
    form_errors = {}

    active_request = donor.submitted_patient_requests.filter(
        status__in=['pending', 'approved']
    ).first()

    if active_request:
        messages.warning(
            request,
            "⚠️ You already have an active donor blood request. "
            "Please complete or cancel it before making a new one."
        )
        return render(request, "donor/donormakerequest.html", {
            "pending_request": active_request,
            "centers": centers,
        })

    if request.method == "POST":
        request_form = DonorBloodRequestForm(request.POST)
        donation_center_id = request.POST.get("donation_center")
        nurse_id = request.POST.get("nurse")
        appointment_date = request.POST.get("appointment_date")
        appointment_time = request.POST.get("appointment_time")

        center_instance = DonationCenter.objects.filter(id=donation_center_id).first()
        nurse_instance = Nurse.objects.filter(id=nurse_id).first() if nurse_id else None

        if not center_instance:
            messages.error(request, "❌ Invalid donation center selected.")
        if nurse_id and not nurse_instance:
            messages.error(request, "❌ Invalid nurse selected.")

        appointment_form = AppointmentForm(
            request.POST,
            center=center_instance,
            donor_instance=donor
        )
        appointment_form.fields["date"].required = False  # manual validation for combined datetime

        if request_form.is_valid() and appointment_form.is_valid():
            if appointment_date and appointment_time and nurse_instance:
                try:
                    naive_datetime = datetime.strptime(
                        f"{appointment_date} {appointment_time}", "%Y-%m-%d %I:%M %p"
                    )
                    combined_datetime = timezone.make_aware(
                        naive_datetime, timezone.get_current_timezone()
                    )

                    # Save donor blood request first
                    blood_request = request_form.save(commit=False)
                    blood_request.request_by_donor = donor
                    blood_request.donation_center = center_instance
                    blood_request.save()

                    content_type = ContentType.objects.get_for_model(blood_request.__class__)

                    # Create appointment instance with correct FK
                    appointment = Appointment(
                        donor=donor,
                        patient=None,
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
                        status__in=["pending", "approved"],
                    ).exists()

                    if conflict_exists:
                        messages.error(
                            request,
                            f"❌ Nurse {nurse_instance.user.get_full_name()} is already booked at this time."
                        )
                    else:
                        appointment.save()
                        messages.success(
                            request, "✅ Donor blood request and appointment created successfully."
                        )
                        return redirect("donation-history")

                except ValidationError as ve:
                    form_errors['appointment'] = ve.messages
                except ValueError:
                    messages.error(request, "❌ Invalid appointment date/time format.")
            else:
                messages.error(request, "❌ Please select appointment date, time, and nurse.")
        else:
            messages.error(request, "❌ Please correct the errors in the blood request form or appointment form.")
            form_errors = {**request_form.errors, **appointment_form.errors}
    else:
        request_form = DonorBloodRequestForm()
        appointment_form = AppointmentForm()
        appointment_form.fields["date"].required = False

    return render(request, "donor/donormakerequest.html", {
        "request_form": request_form,
        "appointment_form": appointment_form,
        "centers": centers,
        "pending_request": None,
        "form_errors": form_errors,
    })
@login_required(login_url="login")
def donor_request_history_view(request):
    """
    Display the donor's blood request history along with linked appointments.
    """
    donor = get_object_or_404(Donor, user=request.user)

    # Fetch blood requests for donor
    blood_requests = DonorBloodRequest.objects.filter(
        request_by_donor=donor
    ).select_related("donation_center").order_by("-created_at")

    # Fetch linked appointments using GenericRelation
    content_type = ContentType.objects.get_for_model(DonorBloodRequest)
    appointments = Appointment.objects.filter(
        donor=donor,
        request_content_type=content_type,
        request_object_id__in=blood_requests.values_list("id", flat=True),
    ).select_related("nurse__user")

    # Map appointments to requests
    appointment_map = {appt.request_object_id: appt for appt in appointments}
    for req in blood_requests:
        req.appointment = appointment_map.get(req.id)

    return render(request, "donor/request_history.html", {
        "blood_requests": blood_requests,
        "now": timezone.now(),
    })


@login_required(login_url="login")
def donor_cancel_request_view(request, request_id):
    """
    Allow donor to cancel a blood request and its linked appointment if still pending or approved.
    """
    donor = get_object_or_404(Donor, user=request.user)
    blood_request = get_object_or_404(DonorBloodRequest, id=request_id)

    if blood_request.request_by_donor != donor:
        raise PermissionDenied("This is not your request.")

    content_type = ContentType.objects.get_for_model(DonorBloodRequest)
    appointment = Appointment.objects.filter(
        donor=donor,
        request_content_type=content_type,
        request_object_id=blood_request.id,
    ).first()

    now = timezone.now()
    if appointment and appointment.date > now:
        if blood_request.status in ["pending", "approved"]:
            blood_request.status = "cancelled"
            blood_request.save()

        if appointment.status in ["pending", "approved"]:
            appointment.status = "cancelled"
            appointment.cancelled_by_user = request.user
            appointment.cancelled_at = now
            appointment.status_changed_by = request.user
            appointment.status_changed_at = now
            appointment.save()

        messages.success(request, "✅ Donor blood request and appointment cancelled.")
    else:
        messages.warning(request, "⚠️ Cannot cancel past or missing appointments.")

    return redirect("donation-history")
