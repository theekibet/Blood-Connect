# yourapp/context_processors.py - UPDATED VERSION
from django.urls import reverse, NoReverseMatch
from django.conf import settings
import os

def user_role_context(request):
    """Safely provide role-specific context to all templates"""
    context = {
        'user_role': None,
        'profile': None,
        'profile_pic_url': None,
        'user_initial': '',
        'navbar_icons': [],
        'profile_menu_items': [],
        'notification_count': 0,
        'show_profile_edit': True,
        'show_change_password': True,
        'default_profile_pic': settings.STATIC_URL + 'images/default-profile.png',
        'is_onboarding': False,  # Flag for onboarding mode
        'onboarding_step': None,  # Current onboarding step
        'onboarding_progress': 0,  # Progress percentage
        'onboarding_next': None,  # Next step description
        'onboarding_greeting': None,  # Personalized greeting
    }
    
    if not request.user.is_authenticated:
        return context
    
    user = request.user
    context['user_initial'] = user.first_name[0] if user.first_name else user.username[0].upper()
    
    # ===== CHECK ONBOARDING STATUS FOR DONORS =====
    if hasattr(user, 'donor'):
        donor = user.donor
        
        # STEP 1: Check if username needs to be set (still using email)
        if user.username == user.email:
            context['is_onboarding'] = True
            context['onboarding_step'] = 'username'
            context['onboarding_progress'] = 0
            context['onboarding_next'] = 'Choose your unique username'
            context['onboarding_greeting'] = f"Welcome, {user.first_name or 'there'}! Let's set up your account."
            
            # Don't load navbar/sidebar during username onboarding
            return context
        
        # STEP 2: Check profile completion - EXCLUDING blood group (optional)
        missing_fields = []
        if not donor.mobile:
            missing_fields.append('Mobile Number')
        if not donor.national_id:
            missing_fields.append('National ID')
        if not donor.county:
            missing_fields.append('County')
        if not donor.dob:
            missing_fields.append('Date of Birth')
        
        # If any required fields are missing, still in onboarding
        if missing_fields:
            context['is_onboarding'] = True
            context['onboarding_step'] = 'profile'
            context['onboarding_progress'] = 50
            context['onboarding_next'] = f"Complete: {', '.join(missing_fields)}"
            context['onboarding_greeting'] = f"Great username, {user.username}! Now complete your profile."
            
            # Don't load navbar/sidebar during profile onboarding
            return context
        
        # STEP 3: If we get here, onboarding is complete
        context['is_onboarding'] = False
        context['onboarding_progress'] = 100
    
    # ===== DONOR (only loaded if onboarding is complete) =====
    if hasattr(user, 'donor') and not context['is_onboarding']:
        context['user_role'] = 'donor'
        context['profile'] = user.donor
        
        # Handle profile picture
        if user.donor.profile_pic and hasattr(user.donor.profile_pic, 'url') and user.donor.profile_pic.name:
            try:
                context['profile_pic_url'] = user.donor.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        else:
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        
        # Navbar icons (customize as needed)
        context['navbar_icons'] = []
        
        # Profile menu items
        profile_items = []
        try:
            profile_items.append({
                'url': reverse('donor:donor-profile'),
                'icon': 'fas fa-user-circle',
                'text': 'View Profile'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({
                'url': reverse('donor:donor-edit-profile'),
                'icon': 'fas fa-edit',
                'text': 'Edit Profile'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({'divider': True})
            profile_items.append({
                'url': reverse('donor:donation-history'),
                'icon': 'fas fa-history',
                'text': 'Donation History'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({
                'url': reverse('donor:volunteer'),
                'icon': 'fas fa-hands-helping',
                'text': 'Volunteer Opportunities'
            })
        except NoReverseMatch:
            pass
        
        context['profile_menu_items'] = profile_items
        
        # Notification count
        try:
            context['notification_count'] = user.donor.notifications.filter(is_read=False).count()
        except:
            context['notification_count'] = 0
    
    # ===== PHLEBOTOMIST =====
    elif hasattr(user, 'phlebotomist'):
        context['user_role'] = 'phlebotomist'
        context['profile'] = user.phlebotomist
        
        # Handle profile picture
        if user.phlebotomist.profile_pic and hasattr(user.phlebotomist.profile_pic, 'url') and user.phlebotomist.profile_pic.name:
            try:
                context['profile_pic_url'] = user.phlebotomist.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        else:
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        
        context['navbar_icons'] = []
        
        profile_items = []
        try:
            profile_items.append({
                'url': reverse('phlebotomist:phlebotomist-profile', args=[user.phlebotomist.id]),
                'icon': 'fas fa-user-circle',
                'text': 'View Profile'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({
                'url': reverse('phlebotomist:phlebotomist-profile-edit', args=[user.phlebotomist.pk]),
                'icon': 'fas fa-edit',
                'text': 'Edit Profile'
            })
        except NoReverseMatch:
            pass
        
        context['profile_menu_items'] = profile_items
        context['notification_count'] = 0
    
    # ===== LAB TECHNOLOGIST =====
    elif hasattr(user, 'lab_tech_profile'):
        context['user_role'] = 'lab_tech'
        context['profile'] = user.lab_tech_profile
        
        # Handle profile picture
        if user.lab_tech_profile.profile_pic and hasattr(user.lab_tech_profile.profile_pic, 'url') and user.lab_tech_profile.profile_pic.name:
            try:
                context['profile_pic_url'] = user.lab_tech_profile.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        else:
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        
        context['navbar_icons'] = []
        
        profile_items = []
        try:
            profile_items.append({
                'url': reverse('lab_technologist:lab_tech_profile'),
                'icon': 'fas fa-user-circle',
                'text': 'View Profile'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({
                'url': reverse('lab_technologist:lab_tech_profile_edit', args=[user.lab_tech_profile.pk]),
                'icon': 'fas fa-edit',
                'text': 'Edit Profile'
            })
        except NoReverseMatch:
            pass
        
        context['profile_menu_items'] = profile_items
        context['notification_count'] = 0
    
    # ===== BLOOD BANK TECHNICIAN =====
    elif hasattr(user, 'blood_bank_tech_profile'):
        context['user_role'] = 'bb_tech'
        context['profile'] = user.blood_bank_tech_profile
        
        # Handle profile picture
        if user.blood_bank_tech_profile.profile_pic and hasattr(user.blood_bank_tech_profile.profile_pic, 'url') and user.blood_bank_tech_profile.profile_pic.name:
            try:
                context['profile_pic_url'] = user.blood_bank_tech_profile.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        else:
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        
        context['navbar_icons'] = []
        
        profile_items = []
        try:
            profile_items.append({
                'url': reverse('blood_bank_technician:blood_bank_tech_profile'),
                'icon': 'fas fa-user-circle',
                'text': 'View Profile'
            })
        except NoReverseMatch:
            pass
        
        try:
            profile_items.append({
                'url': reverse('blood_bank_technician:blood_bank_tech_profile_edit', args=[user.blood_bank_tech_profile.pk]),
                'icon': 'fas fa-edit',
                'text': 'Edit Profile'
            })
        except NoReverseMatch:
            pass
        
        context['profile_menu_items'] = profile_items
        context['notification_count'] = 0
    
    # ===== HOSPITAL USER =====
    elif hasattr(user, 'hospitaluser'):
        context['user_role'] = 'hospital'
        context['profile'] = user.hospitaluser
        
        # Handle profile picture
        if hasattr(user.hospitaluser, 'profile_pic') and user.hospitaluser.profile_pic and hasattr(user.hospitaluser.profile_pic, 'url'):
            try:
                context['profile_pic_url'] = user.hospitaluser.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        elif hasattr(user, 'profile_pic') and user.profile_pic and hasattr(user.profile_pic, 'url'):
            try:
                context['profile_pic_url'] = user.profile_pic.url
            except:
                context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        else:
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        
        context['navbar_icons'] = []
        
        profile_items = []
        try:
            profile_items.append({
                'url': reverse('hospital:profile'),
                'icon': 'fas fa-id-card',
                'text': 'Hospital Profile'
            })
        except NoReverseMatch:
            pass
        
        # Add admin-only items
        if user.hospitaluser.role == 'admin':
            try:
                profile_items.append({'divider': True})
                profile_items.append({
                    'url': reverse('hospital:user_management'),
                    'icon': 'fas fa-users-cog',
                    'text': 'Manage Users'
                })
            except NoReverseMatch:
                pass
        
        context['profile_menu_items'] = profile_items
        context['notification_count'] = 0
    
    # ===== ADMIN STAFF =====
    elif user.is_staff:
        context['user_role'] = 'admin'
        context['profile'] = None
        context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
        context['show_profile_edit'] = False
        context['show_change_password'] = False
        
        context['navbar_icons'] = []
        
        try:
            context['profile_menu_items'] = [
                {
                    'url': reverse('admin:index'),
                    'icon': 'fas fa-cog',
                    'text': 'Admin Panel'
                },
            ]
        except NoReverseMatch:
            context['profile_menu_items'] = []
        
        context['notification_count'] = 0
    
    return context
def admin_secret_url(request):
    """Make the admin secret URL available to templates"""
    return {
        'ADMIN_SECRET_URL': settings.ADMIN_SECRET_URL,
    }