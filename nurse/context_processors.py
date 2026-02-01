from django.contrib.contenttypes.models import ContentType
from .models import Nurse
from blood.models import Notification 

def nurse_unread_notifications(request):
    unread_count = 0
    if request.user.is_authenticated and hasattr(request.user, 'nurse'):
        try:
            nurse = request.user.nurse
            nurse_ct = ContentType.objects.get_for_model(Nurse)
            unread_count = Notification.objects.filter(
                recipient_content_type=nurse_ct,
                recipient_object_id=nurse.id,
                read=False
            ).count()
        except Exception:
            unread_count = 0
    return {'unread_count': unread_count}
