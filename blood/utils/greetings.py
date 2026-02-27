from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User

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


def get_nurse_greeting(nurse, appointment_count, next_appointment=None):
    """Generate personalized greeting for nurses"""
    greeting = get_time_based_greeting(nurse.user.first_name)
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
        next_app_msg = f" Your next appointment is at {time_str} with {participant}."
    
    return {
        'greeting': greeting,
        'context_message': context,
        'next_appointment_msg': next_app_msg,
        'user_type': 'nurse',
        'icon': '👩‍⚕️'
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
        days_since = 0  # Initialize with default value
        
        try:
            # Handle both date and datetime objects safely
            donation_date = last_donation.date
            
            # If it's a datetime, extract date; if already date, use as-is
            if hasattr(donation_date, 'date'):
                donation_date = donation_date.date()
            
            days_since = (timezone.now().date() - donation_date).days
        except (AttributeError, TypeError, ValueError) as e:
            # If date parsing fails, default to 0 (eligible to donate)
            print(f"Date parsing error: {e}")
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
        next_app_msg = f"Your next donation is at {time_str}."
    
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
            status__in=['approved', 'completed']
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
        'profile_pic': donor.profile_pic if hasattr(donor, 'profile_pic') else None
    }

def get_generic_greeting(user, user_type=None):
    """Fallback generic greeting for any user type"""
    greeting = get_time_based_greeting(user.first_name)
    day_message = get_day_specific_message()
    
    return {
        'greeting': greeting,
        'context_message': day_message,
        'user_type': user_type or 'user',
        'icon': '👋'
    }
