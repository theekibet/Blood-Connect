from django.contrib.contenttypes.models import ContentType
from .models import Notification

def notification_count(request):
    """
    Context processor to add notification count to all templates
    """
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}
    
    try:
        user_content_type = ContentType.objects.get_for_model(request.user)
        unread_count = Notification.objects.filter(
            recipient_content_type=user_content_type,
            recipient_object_id=request.user.id,
            is_read=False
        ).count()
        
        return {
            'unread_notifications_count': unread_count,
            'has_unread_notifications': unread_count > 0
        }
    except Exception:
        return {'unread_notifications_count': 0, 'has_unread_notifications': False}