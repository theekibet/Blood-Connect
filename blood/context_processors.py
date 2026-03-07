from django.conf import settings  # 👈 ADD THIS IMPORT
from blood.models import UserReview
import logging

logger = logging.getLogger(__name__)

def user_role_context(request):
    """Safely provide role-specific context to all templates"""
    context = {
        'user_role': None,
        'user_role_label': None,
        'profile': None,
        'profile_pic_url': None,
        'user_initial': '',
        'notification_count': 0,
        'default_profile_pic': settings.STATIC_URL + 'images/default-profile.png',  # Now works
        'profile_url': None,
        'edit_profile_url': None,
        'has_review': False,
    }
    
    if not request.user.is_authenticated:
        return context
    
    user = request.user
    context['user_initial'] = user.first_name[0] if user.first_name else user.username[0].upper()
    
    # Check if user has a review
    try:
        context['has_review'] = UserReview.objects.filter(user=user).exists()
    except Exception as e:
        logger.error(f"Error checking review: {e}")
    
    # ===== DONOR =====
    if hasattr(user, 'donor'):
        context['user_role'] = 'donor'
        context['user_role_label'] = 'Donor'
        context['profile'] = user.donor
        context['profile_url'] = 'donor:donor-profile'
        context['edit_profile_url'] = 'donor:donor-edit-profile'
        
        if user.donor.profile_pic and hasattr(user.donor.profile_pic, 'url') and user.donor.profile_pic.name:
            context['profile_pic_url'] = user.donor.profile_pic.url
        
        try:
            from utils.models import Notification
            from django.contrib.contenttypes.models import ContentType
            donor_ct = ContentType.objects.get_for_model(user.donor)
            context['notification_count'] = Notification.objects.filter(
                recipient_content_type=donor_ct,
                recipient_object_id=user.donor.id,
                is_read=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting donor notifications: {e}")
            context['notification_count'] = 0
    
    # ===== PHLEBOTOMIST =====
    elif hasattr(user, 'phlebotomist'):
        context['user_role'] = 'phlebotomist'
        context['user_role_label'] = 'Phlebotomist'
        context['profile'] = user.phlebotomist
        context['profile_url'] = 'phlebotomist:phlebotomist-profile'
        context['edit_profile_url'] = 'phlebotomist:phlebotomist-profile-edit'
        
        if user.phlebotomist.profile_pic and hasattr(user.phlebotomist.profile_pic, 'url') and user.phlebotomist.profile_pic.name:
            context['profile_pic_url'] = user.phlebotomist.profile_pic.url
    
    # ===== LAB TECHNOLOGIST =====
    elif hasattr(user, 'lab_tech_profile'):
        context['user_role'] = 'lab_tech'
        context['user_role_label'] = 'Lab Technologist'
        context['profile'] = user.lab_tech_profile
        context['profile_url'] = 'lab_technologist:lab_tech_profile'
        context['edit_profile_url'] = 'lab_technologist:lab_tech_profile_edit'
        
        if user.lab_tech_profile.profile_pic and hasattr(user.lab_tech_profile.profile_pic, 'url') and user.lab_tech_profile.profile_pic.name:
            context['profile_pic_url'] = user.lab_tech_profile.profile_pic.url
    
    # ===== BLOOD BANK TECHNICIAN =====
    elif hasattr(user, 'blood_bank_tech_profile'):
        context['user_role'] = 'bb_tech'
        context['user_role_label'] = 'Blood Bank Technician'
        context['profile'] = user.blood_bank_tech_profile
        context['profile_url'] = 'blood_bank_technician:blood_bank_tech_profile'
        context['edit_profile_url'] = 'blood_bank_technician:blood_bank_tech_profile_edit'
        
        if user.blood_bank_tech_profile.profile_pic and hasattr(user.blood_bank_tech_profile.profile_pic, 'url') and user.blood_bank_tech_profile.profile_pic.name:
            context['profile_pic_url'] = user.blood_bank_tech_profile.profile_pic.url
    
    # ===== HOSPITAL USER =====
    elif hasattr(user, 'hospitaluser'):
        context['user_role'] = 'hospital'
        context['user_role_label'] = 'Hospital Staff'
        context['profile'] = user.hospitaluser
        context['profile_url'] = 'hospital:profile'
        context['edit_profile_url'] = 'hospital:profile'
        
        # Hospital users might have profile pics in different places
        if hasattr(user, 'profile_pic') and user.profile_pic:
            context['profile_pic_url'] = user.profile_pic.url
    
    # ===== ADMIN =====
    elif user.is_staff:
        context['user_role'] = 'admin'
        context['user_role_label'] = 'Administrator'
    
    return context