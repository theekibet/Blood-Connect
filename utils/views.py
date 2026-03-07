from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Notification
import logging

logger = logging.getLogger(__name__)

def get_user_base_template(user):
    """
    Helper function to determine which base template to use for a user
    """
    if user.is_superuser or user.is_staff:
        return 'admin/adminbase.html'
    elif hasattr(user, 'donor'):
        return 'donor/donorbase.html'
    elif hasattr(user, 'hospitaluser'):
        # Hospital uses base.html, not hospitalbase.html
        return 'hospital/base.html'
    elif hasattr(user, 'phlebotomist'):
        # Check if phlebotomist has a specific base template
        try:
            # Try to use phlebotomist base if it exists
            from django.template.loader import get_template
            get_template('phlebotomist/phlebotomistbase.html')
            return 'phlebotomist/phlebotomistbase.html'
        except:
            # Fallback to shared base
            return 'shared/base.html'
    elif hasattr(user, 'lab_tech_profile'):
        return 'lab_technologist/base.html'
    elif hasattr(user, 'blood_bank_tech_profile'):
        return 'blood_bank_technician/base.html'
    else:
        return 'shared/base.html'

def get_user_type(user):
    """
    Helper function to get user type as string
    """
    if user.is_superuser:
        return 'admin'
    elif hasattr(user, 'donor'):
        return 'donor'
    elif hasattr(user, 'hospitaluser'):
        return 'hospital'
    elif hasattr(user, 'phlebotomist'):
        return 'phlebotomist'
    elif hasattr(user, 'lab_tech_profile'):
        return 'lab_technologist'
    elif hasattr(user, 'blood_bank_tech_profile'):
        return 'blood_bank_technician'
    else:
        return 'user'

@login_required
def universal_notifications_list(request):
    """
    Universal notifications view that works for any user type
    """
    # Get user's content type and object
    user_content_type = ContentType.objects.get_for_model(request.user)
    
    # Get notifications for this user
    notifications = Notification.objects.filter(
        recipient_content_type=user_content_type,
        recipient_object_id=request.user.id
    ).order_by('-created_at')
    
    # Filter by read status
    status = request.GET.get('status', 'all')
    if status == 'unread':
        notifications = notifications.filter(is_read=False)
    elif status == 'read':
        notifications = notifications.filter(is_read=True)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        notifications = notifications.filter(
            Q(title__icontains=search) | 
            Q(message__icontains=search)
        )
    
    # Get base template for this user
    base_template = get_user_base_template(request.user)
    user_type = get_user_type(request.user)
    
    # Log for debugging
    logger.info(f"User {request.user.username} - Type: {user_type}, Base template: {base_template}")
    
    context = {
        'notifications': notifications,
        'unread_count': notifications.filter(is_read=False).count(),
        'current_status': status,
        'search': search,
        'base_template': base_template,
        'user_type': user_type,
    }
    
    return render(request, 'shared/universal_notifications.html', context)

@login_required
def universal_mark_read(request, notification_id):
    """
    Universal mark as read view
    """
    user_content_type = ContentType.objects.get_for_model(request.user)
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient_content_type=user_content_type,
        recipient_object_id=request.user.id
    )
    
    notification.is_read = True
    notification.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Notification marked as read'})
    
    return redirect(request.META.get('HTTP_REFERER', 'utils:notifications'))

@login_required
def universal_mark_all_read(request):
    """
    Universal mark all as read view
    """
    user_content_type = ContentType.objects.get_for_model(request.user)
    Notification.objects.filter(
        recipient_content_type=user_content_type,
        recipient_object_id=request.user.id,
        is_read=False
    ).update(is_read=True)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'All notifications marked as read'})
    
    messages.success(request, 'All notifications marked as read.')
    return redirect('utils:notifications')

@login_required
def universal_delete_notification(request, notification_id):
    """
    Universal delete notification view
    """
    user_content_type = ContentType.objects.get_for_model(request.user)
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient_content_type=user_content_type,
        recipient_object_id=request.user.id
    )
    
    notification.delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Notification deleted'})
    
    messages.success(request, 'Notification deleted.')
    return redirect('utils:notifications')

@login_required
def universal_unread_count(request):
    """
    Get unread notification count for any user
    """
    user_content_type = ContentType.objects.get_for_model(request.user)
    unread_count = Notification.objects.filter(
        recipient_content_type=user_content_type,
        recipient_object_id=request.user.id,
        is_read=False
    ).count()
    
    return JsonResponse({'unread_count': unread_count})

# ==========================================
# FALLBACK VIEWS FOR APPS WITHOUT NOTIFICATION VIEWS
# ==========================================

@login_required
def fallback_notifications(request):
    """
    Fallback notifications view that redirects to universal notifications
    """
    messages.info(request, 'Redirecting to unified notifications system...')
    return redirect('utils:notifications')

@login_required
def fallback_mark_read(request, pk):
    """
    Fallback mark read view that redirects to universal mark read
    """
    return redirect('utils:mark_read', notification_id=pk)

@login_required
def fallback_mark_all_read(request):
    """
    Fallback mark all read view
    """
    return redirect('utils:mark_all_read')