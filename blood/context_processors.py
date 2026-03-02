# yourapp/context_processors.py
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
        'default_profile_pic': settings.STATIC_URL + 'images/default-profile.png',  # Add default
    }
    
    if not request.user.is_authenticated:
        return context
    
    user = request.user
    context['user_initial'] = user.first_name[0] if user.first_name else user.username[0].upper()
    
    # ===== DONOR =====
    if hasattr(user, 'donor'):
        context['user_role'] = 'donor'
        context['profile'] = user.donor
        
        # Handle profile picture - use default if none exists
        if user.donor.profile_pic and hasattr(user.donor.profile_pic, 'url') and user.donor.profile_pic.name:
            context['profile_pic_url'] = user.donor.profile_pic.url
            print(f"✅ Donor profile pic found: {user.donor.profile_pic.url}")  # Debug
        else:
            # Use default profile picture
            context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'
            print(f"🖼️ Using default profile pic for donor {user.username}")  # Debug
        
        # Navbar icons (empty as per your preference)
        context['navbar_icons'] = []
        
        # Profile menu items (keep your existing code)
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
                'url': reverse('donor:volunteer'),
                'icon': 'fas fa-hands-helping',
                'text': 'Volunteer Opportunities'
            })
        except NoReverseMatch:
            pass
        
        context['profile_menu_items'] = profile_items
        
        # Notification count
        if hasattr(user.donor, 'notifications'):
            context['notification_count'] = user.donor.notifications.filter(is_read=False).count()
    
    # ===== PHLEBOTOMIST =====
    elif hasattr(user, 'phlebotomist'):
        context['user_role'] = 'phlebotomist'
        context['profile'] = user.phlebotomist
        
        # Handle profile picture - use default if none exists
        if user.phlebotomist.profile_pic and hasattr(user.phlebotomist.profile_pic, 'url') and user.phlebotomist.profile_pic.name:
            context['profile_pic_url'] = user.phlebotomist.profile_pic.url
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
        
        # Handle profile picture - use default if none exists
        if user.lab_tech_profile.profile_pic and hasattr(user.lab_tech_profile.profile_pic, 'url') and user.lab_tech_profile.profile_pic.name:
            context['profile_pic_url'] = user.lab_tech_profile.profile_pic.url
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
        
        # Handle profile picture - use default if none exists
        if user.blood_bank_tech_profile.profile_pic and hasattr(user.blood_bank_tech_profile.profile_pic, 'url') and user.blood_bank_tech_profile.profile_pic.name:
            context['profile_pic_url'] = user.blood_bank_tech_profile.profile_pic.url
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
        
        # Handle profile picture - hospital users might have different structure
        if hasattr(user.hospitaluser, 'profile_pic') and user.hospitaluser.profile_pic and hasattr(user.hospitaluser.profile_pic, 'url'):
            context['profile_pic_url'] = user.hospitaluser.profile_pic.url
        elif hasattr(user, 'profile_pic') and user.profile_pic and hasattr(user.profile_pic, 'url'):
            context['profile_pic_url'] = user.profile_pic.url
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
        context['profile_pic_url'] = settings.STATIC_URL + 'images/default-profile.png'  # Default for admin too
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