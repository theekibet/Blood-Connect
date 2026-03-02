from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User

def get_time_of_day():
    """Helper function to get current time of day"""
    hour = timezone.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"

def get_time_based_greeting(user_first_name=None):
    """
    Get time-based greeting for any user
    """
    current_hour = datetime.now().hour
    name = user_first_name or "there"
    
    if 5 <= current_hour < 12:
        return f"Good morning, {name}! ☀️"
    elif 12 <= current_hour < 17:
        return f"Good afternoon, {name}! 🌤️"
    elif 17 <= current_hour < 22:
        return f"Good evening, {name}! 🌙"
    else:
        return f"Welcome back, {name}! 🌟"


def get_day_specific_message():
    """Get message based on day of week"""
    current_day = datetime.now().strftime("%A")
    
    day_messages = {
        "Monday": "A fresh week begins! 📅",
        "Tuesday": "Have a productive Tuesday! 💪",
        "Wednesday": "Midweek momentum! 🚀",
        "Thursday": "Almost there! Keep going! 🌟",
        "Friday": "Happy Friday! Great work this week! 🎉",
        "Saturday": "Enjoy your weekend! 🌞",
        "Sunday": "Relax and recharge! 🧘"
    }
    
    return day_messages.get(current_day, "Have a wonderful day!")


def get_phlebotomist_greeting(phlebotomist, appointment_count=0, next_appointment=None):
    """Generate personalized greeting for phlebotomists"""
    greeting = get_time_based_greeting(phlebotomist.user.first_name)
    day_message = get_day_specific_message()
    
    if appointment_count == 0:
        context = f"{day_message} You have a clear schedule today. Perfect time for inventory checks!"
    elif appointment_count == 1:
        context = f"{day_message} You have 1 appointment today. Ready to make a difference!"
    elif appointment_count <= 3:
        context = f"{day_message} You have {appointment_count} appointments today. Stay productive!"
    elif appointment_count <= 6:
        context = f"{day_message} You have {appointment_count} appointments today. It's a busy day!"
    else:
        context = f"{day_message} Wow! {appointment_count} appointments today. You're making a huge impact!"
    
    next_app_msg = ""
    if next_appointment:
        time_str = next_appointment.date.strftime("%I:%M %p")
        donor_name = next_appointment.donor.user.get_full_name() if next_appointment.donor else "a donor"
        next_app_msg = f" Your next appointment is at {time_str} with {donor_name}."
    
    # Meta items
    meta_items = [
        {'icon': 'fas fa-calendar-check', 'text': f'{appointment_count} appointments'},
    ]
    
    if phlebotomist.center:
        meta_items.append({'icon': 'fas fa-building', 'text': phlebotomist.center.name})
    
    return {
        'greeting': greeting,
        'context_message': context,
        'next_appointment_msg': next_app_msg,
        'user_type': 'phlebotomist',
        'icon': '👩‍⚕️',
        'profile_pic': phlebotomist.profile_pic if hasattr(phlebotomist, 'profile_pic') else None,
        'is_hero': appointment_count > 3,
        'meta_items': meta_items,
        'show_quick_actions': True
    }


def get_donor_greeting(donor, last_donation=None, upcoming_appointments=None):
    """Generate personalized greeting for donors"""
    greeting = get_time_based_greeting(donor.user.first_name)
    day_message = get_day_specific_message()
    
    messages = []
    messages.append(day_message)
    
    is_hero = False
    
    # Check last donation
    if last_donation:
        days_since = 0
        
        try:
            # Handle both date and datetime objects safely
            donation_date = last_donation.date
            
            # If it's a datetime, extract date; if already date, use as-is
            if hasattr(donation_date, 'date'):
                donation_date = donation_date.date()
            
            days_since = (timezone.now().date() - donation_date).days
        except (AttributeError, TypeError, ValueError):
            days_since = 0
        
        if days_since > 90:  # Eligible to donate again
            messages.append("You're eligible to donate again! 🩸")
            is_hero = True
        elif days_since > 0:
            days_left = 90 - days_since
            messages.append(f"Thank you for your recent donation! Eligible in {days_left} days. 🙏")
        else:
            messages.append("Thank you for your recent donation! 🙏")
    else:
        messages.append("Ready to save a life today?")
        is_hero = True
    
    # Check upcoming appointments
    next_app_msg = ""
    if upcoming_appointments and upcoming_appointments.exists():
        next_app = upcoming_appointments.first()
        time_str = next_app.date.strftime("%I:%M %p")
        center_name = next_app.center.name if next_app.center else "donation center"
        next_app_msg = f"Your next donation is at {time_str} at {center_name}."
    
    # Prepare metadata
    meta_items = []
    if hasattr(donor, 'bloodgroup') and donor.bloodgroup:
        meta_items.append({
            'icon': 'fas fa-tint',
            'text': f"Blood Group: {donor.bloodgroup}"
        })
    
    # Get total donations count
    try:
        from donor.models import BloodDonate
        total_donations = BloodDonate.objects.filter(
            donor=donor,
            status='tested_safe'
        ).count()
        meta_items.append({
            'icon': 'fas fa-heart',
            'text': f"{total_donations} donation{'s' if total_donations != 1 else ''}"
        })
        
        # Update hero status based on donations
        if total_donations >= 1:
            is_hero = True
            
    except ImportError:
        total_donations = 0
    
    return {
        'greeting': greeting,
        'context_message': " ".join(messages),
        'next_appointment_msg': next_app_msg,
        'user_type': 'donor',
        'icon': '🦸',
        'is_hero': is_hero,
        'meta_items': meta_items,
        'profile_pic': donor.profile_pic if hasattr(donor, 'profile_pic') else None,
        'show_quick_actions': True
    }


def get_blood_bank_tech_greeting(bb_tech, safe_units=0, pending_requests=0, expiring_soon=0):
    """Generate personalized greeting for blood bank technicians"""
    # Use the time-based greeting properly
    time_based_greeting = get_time_based_greeting(bb_tech.user.first_name)
    
    name = bb_tech.user.get_full_name().split()[0] if bb_tech.user.get_full_name() else bb_tech.user.username
    time_of_day = get_time_of_day()
    
    # Context message based on inventory status
    if safe_units == 0:
        context_message = "Your inventory is empty. New blood units are needed."
        icon = "📦"
    elif pending_requests > 0:
        context_message = f"You have {pending_requests} pending blood request{'s' if pending_requests > 1 else ''} to review."
        icon = "🏥"
    elif expiring_soon > 0:
        context_message = f"{expiring_soon} blood unit{'s' if expiring_soon > 1 else ''} expiring soon. Prioritize dispatch."
        icon = "⏳"
    else:
        context_message = f"Managing inventory at {bb_tech.center.name if bb_tech.center else 'your center'}"
        icon = "📊"
    
    # Meta items
    meta_items = [
        {'icon': 'fas fa-building', 'text': bb_tech.center.name if bb_tech.center else 'No center assigned'},
        {'icon': 'fas fa-boxes', 'text': f'{safe_units} safe units'},
    ]
    
    if pending_requests > 0:
        meta_items.append({
            'icon': 'fas fa-clock', 
            'text': f'{pending_requests} pending request{"s" if pending_requests > 1 else ""}',
            'color': 'text-warning'
        })
    
    if expiring_soon > 0:
        meta_items.append({
            'icon': 'fas fa-exclamation-triangle', 
            'text': f'{expiring_soon} expiring soon',
            'color': 'text-danger'
        })
    
    return {
        'greeting': time_based_greeting,  # Use the time-based greeting
        'context_message': context_message,
        'user_type': 'blood_bank_tech',
        'icon': icon,
        'meta_items': meta_items,
        'show_quick_actions': True,
        'profile_pic': bb_tech.profile_pic if hasattr(bb_tech, 'profile_pic') else None
    }

def get_lab_tech_greeting(lab_tech, pending_tests=0, completed_today=0, safe_count=0, unsafe_count=0):
    """Generate personalized greeting for lab technologists"""
    # Use the time-based greeting properly
    time_based_greeting = get_time_based_greeting(lab_tech.user.first_name)
    
    name = lab_tech.user.get_full_name().split()[0] if lab_tech.user.get_full_name() else lab_tech.user.username
    time_of_day = get_time_of_day()
    
    # Context message based on workload
    if pending_tests > 5:
        context_message = f"You have {pending_tests} samples waiting for testing. Time to get to work!"
        icon = "🔬"
    elif pending_tests > 0:
        context_message = f"You have {pending_tests} sample{'s' if pending_tests > 1 else ''} to test."
        icon = "🧪"
    elif completed_today > 0:
        context_message = f"Great job! You've completed {completed_today} test{'s' if completed_today > 1 else ''} today."
        icon = "✅"
    else:
        context_message = f"All caught up! No pending tests at {lab_tech.center.name if lab_tech.center else 'your center'}."
        icon = "✨"
    
    # Meta items
    meta_items = [
        {'icon': 'fas fa-building', 'text': lab_tech.center.name if lab_tech.center else 'No center assigned'},
    ]
    
    if pending_tests > 0:
        meta_items.append({
            'icon': 'fas fa-hourglass-half', 
            'text': f'{pending_tests} pending',
            'color': 'text-warning'
        })
    
    if completed_today > 0:
        meta_items.append({
            'icon': 'fas fa-check-circle', 
            'text': f'{completed_today} today',
            'color': 'text-success'
        })
    
    meta_items.append({
        'icon': 'fas fa-chart-pie',
        'text': f'{safe_count} safe / {unsafe_count} unsafe'
    })
    
    return {
        'greeting': time_based_greeting,  # Use the time-based greeting
        'context_message': context_message,
        'user_type': 'lab_tech',
        'icon': icon,
        'meta_items': meta_items,
        'show_quick_actions': True,
        'profile_pic': lab_tech.profile_pic if hasattr(lab_tech, 'profile_pic') else None
    }

def get_hospital_greeting(hospital_user, pending_requests=0, approved_requests=0, dispatched_requests=0, total_requests=0):
    """Generate personalized greeting for hospital staff"""
    # Get the time-based greeting once
    time_based_greeting = get_time_based_greeting(hospital_user.user.first_name)
    time_of_day = get_time_of_day()
    
    name = hospital_user.user.get_full_name().split()[0] if hospital_user.user.get_full_name() else hospital_user.user.username
    hospital = hospital_user.hospital
    
    # Context message based on request status
    if pending_requests > 3:
        context_message = f"You have {pending_requests} pending blood requests that need attention."
        icon = "⚠️"
    elif pending_requests > 0:
        context_message = f"You have {pending_requests} pending blood request{'s' if pending_requests > 1 else ''}."
        icon = "📋"
    elif dispatched_requests > 0:
        context_message = f"{dispatched_requests} request{'s' if dispatched_requests > 1 else ''} in transit."
        icon = "🚚"
    elif approved_requests > 0:
        context_message = f"{approved_requests} approved request{'s' if approved_requests > 1 else ''} ready for pickup."
        icon = "✅"
    else:
        context_message = f"No active requests at {hospital.name}. Ready for new requests!"
        icon = "✨"
    
    # Meta items
    meta_items = [
        {'icon': 'fas fa-building', 'text': hospital.name},
        {'icon': 'fas fa-user-md', 'text': f'Role: {hospital_user.get_role_display()}'},
    ]
    
    if pending_requests > 0:
        meta_items.append({
            'icon': 'fas fa-clock', 
            'text': f'{pending_requests} pending',
            'color': 'text-warning'
        })
    
    if approved_requests > 0:
        meta_items.append({
            'icon': 'fas fa-check-circle', 
            'text': f'{approved_requests} approved',
            'color': 'text-success'
        })
    
    if dispatched_requests > 0:
        meta_items.append({
            'icon': 'fas fa-truck', 
            'text': f'{dispatched_requests} dispatched',
            'color': 'text-info'
        })
    
    return {
        'greeting': time_based_greeting,  # Use the variable, not the function name
        'context_message': context_message,
        'user_type': 'hospital',
        'icon': icon,
        'meta_items': meta_items,
        'show_quick_actions': True,
        'profile_pic': hospital_user.user.profile_pic if hasattr(hospital_user.user, 'profile_pic') else None
    }

def get_hospital_admin_greeting(hospital_user, stats=None, user_count=0):
    """Generate personalized greeting for hospital administrators"""
    greeting = get_time_based_greeting(hospital_user.user.first_name)
    time_of_day = get_time_of_day()
    
    name = hospital_user.user.get_full_name().split()[0] if hospital_user.user.get_full_name() else hospital_user.user.username
    hospital = hospital_user.hospital
    
    if stats is None:
        stats = {}
    
    # Context message for admin
    pending = stats.get('pending_requests', 0)
    total = stats.get('total_requests', 0)
    
    if pending > 5:
        context_message = f"Administrative oversight: {pending} pending requests require attention."
        icon = "📊"
    elif user_count > 10:
        context_message = f"Managing {user_count} hospital users and {total} total requests."
        icon = "👥"
    else:
        context_message = f"Administrator dashboard for {hospital.name}"
        icon = "👨‍💼"
    
    # Meta items for admin
    meta_items = [
        {'icon': 'fas fa-building', 'text': hospital.name},
        {'icon': 'fas fa-users', 'text': f'{user_count} users'},
        {'icon': 'fas fa-file-alt', 'text': f'{total} total requests'},
    ]
    
    if pending > 0:
        meta_items.append({
            'icon': 'fas fa-clock', 
            'text': f'{pending} pending',
            'color': 'text-warning'
        })
    
    return {
        'greeting': greeting,
        'context_message': context_message,
        'user_type': 'hospital_admin',
        'icon': icon,
        'meta_items': meta_items,
        'show_quick_actions': True,
        'profile_pic': hospital_user.user.profile_pic if hasattr(hospital_user.user, 'profile_pic') else None
    }


def get_generic_greeting(user, user_type=None):
    """Fallback generic greeting for any user type"""
    greeting = get_time_based_greeting(user.first_name)
    day_message = get_day_specific_message()
    
    # If specific user type functions exist, call them
    if user_type == 'phlebotomist' and hasattr(user, 'phlebotomist'):
        try:
            from phlebotomist.models import Phlebotomist
            phlebotomist = Phlebotomist.objects.get(user=user)
            return get_phlebotomist_greeting(phlebotomist)
        except:
            pass
    elif user_type == 'donor' and hasattr(user, 'donor'):
        try:
            from donor.models import Donor
            donor = Donor.objects.get(user=user)
            return get_donor_greeting(donor)
        except:
            pass
    elif user_type == 'lab_tech' and hasattr(user, 'lab_tech_profile'):
        try:
            from lab_technologist.models import LabTechnologistProfile
            lab_tech = LabTechnologistProfile.objects.get(user=user)
            return get_lab_tech_greeting(lab_tech)
        except:
            pass
    elif user_type == 'bb_tech' and hasattr(user, 'blood_bank_tech_profile'):
        try:
            from blood_bank_technician.models import BloodBankTechProfile
            bb_tech = BloodBankTechProfile.objects.get(user=user)
            return get_blood_bank_tech_greeting(bb_tech)
        except:
            pass
    elif user_type == 'hospital' and hasattr(user, 'hospitaluser'):
        try:
            from hospital.models import HospitalUser
            hospital_user = HospitalUser.objects.get(user=user)
            return get_hospital_greeting(hospital_user)
        except:
            pass
    
    # Fallback to generic greeting
    return {
        'greeting': greeting,
        'context_message': day_message,
        'user_type': user_type or 'user',
        'icon': '👋',
        'meta_items': [],
        'is_hero': False,
        'profile_pic': None,
        'show_quick_actions': True
    }