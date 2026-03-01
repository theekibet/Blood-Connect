# validators.py
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

def validate_single_profile(user, current_profile_type=None, exclude_self=True):
    """
    Validate that a user doesn't have multiple profiles
    """
    
    if not user or not user.pk:
        return True
    
    # Define all possible profile types with their actual related names
    PROFILE_TYPES = {
        # From donor app
        'donor': 'donor',
        
        # From phlebotomist app
        'phlebotomist': 'phlebotomist',
        
        # From hospital app
        'hospital_staff': 'hospitaluser',  # HospitalUser model
        
        # From lab_technologist app
        'lab_technologist': 'lab_tech_profile',
        
        # From blood_bank_technician app
        'blood_bank_technician': 'blood_bank_tech_profile',
    }
    
    existing_profiles = []
    profile_objects = {}
    
    for profile_name, related_name in PROFILE_TYPES.items():
        if exclude_self and current_profile_type and related_name == current_profile_type:
            continue
        
        if hasattr(user, related_name):
            profile = getattr(user, related_name)
            # Check if profile exists (not None) and has a primary key (is saved)
            if profile and profile.pk:
                existing_profiles.append(profile_name)
                profile_objects[profile_name] = profile
    
    # If we found any existing profiles of OTHER types
    if existing_profiles:
        error_msg = (
            f"User {user.username} (ID: {user.pk}) already has a profile as: "
            f"{', '.join(existing_profiles)}. "
            f"Each user can only have one role in the system."
        )
        logger.warning(error_msg)
        raise ValidationError(error_msg)
    
    return True


def get_user_profile_type(user):
    """
    Determine what profile type a user has
    
    Returns:
        tuple: (profile_type_name, profile_object) or (None, None)
    """
    PROFILE_TYPES = {
        'donor': 'donor',
        'phlebotomist': 'phlebotomist',
        'hospital_staff': 'hospitaluser',
        'lab_technologist': 'lab_tech_profile',
        'blood_bank_technician': 'blood_bank_tech_profile',
    }
    
    for profile_name, related_name in PROFILE_TYPES.items():
        if hasattr(user, related_name):
            profile = getattr(user, related_name)
            if profile and profile.pk:
                return profile_name, profile
    
    return None, None


def check_for_duplicate_profiles(user):
    """
    Check if a user has multiple profiles
    
    Returns:
        list: List of profile types found for the user
    """
    PROFILE_TYPES = {
        'donor': 'donor',
        'phlebotomist': 'phlebotomist',
        'hospital_staff': 'hospitaluser',
        'lab_technologist': 'lab_tech_profile',
        'blood_bank_technician': 'blood_bank_tech_profile',
    }
    
    found_profiles = []
    
    for profile_name, related_name in PROFILE_TYPES.items():
        if hasattr(user, related_name):
            profile = getattr(user, related_name)
            if profile and profile.pk:
                found_profiles.append(profile_name)
    
    return found_profiles


def get_profile_dashboard_url(user):
    """
    Get the appropriate dashboard URL for a user based on their profile
    
    Args:
        user: The user instance
    
    Returns:
        str: URL name for the dashboard, or None if no profile
    """
    profile_type, profile = get_user_profile_type(user)
    
    if not profile_type:
        return None
    
    # Map profile types to dashboard URL names
    # Adjust these URL names based on your urls.py
    DASHBOARD_URLS = {
        'donor': 'donor-dashboard',
        'nurse': 'phlebotomist-dashboard',
        'hospital_staff': 'hospital:dashboard',
        'lab_technologist': 'lab_technologist:dashboard',
        'blood_bank_technician': 'blood_bank_technician:dashboard',
    }
    
    return DASHBOARD_URLS.get(profile_type)
