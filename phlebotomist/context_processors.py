from django.contrib.contenttypes.models import ContentType
from .models import Phlebotomist
from utils.models import Notification 

def phlebotomist_unread_notifications(request):
    unread_count = 0
    if request.user.is_authenticated and hasattr(request.user, 'phlebotomist'):
        try:
            phlebotomist= request.user.phlebotomist
            phlebotomist_ct = ContentType.objects.get_for_model(Phlebotomist)
            unread_count = Notification.objects.filter(
                recipient_content_type=phlebotomist_ct,
                recipient_object_id=phlebotomist.id,
                read=False
            ).count()
        except Exception:
            unread_count = 0
    return {'unread_count': unread_count}
