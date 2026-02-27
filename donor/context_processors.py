from django.contrib.contenttypes.models import ContentType
from utils.models import Notification
from donor.models import Donor

def donor_notification_count(request):
    unread_count = 0
    if request.user.is_authenticated:
        try:
            donor = Donor.objects.get(user=request.user)
            donor_ct = ContentType.objects.get_for_model(Donor)
            unread_count = Notification.objects.filter(
                recipient_content_type=donor_ct,
                recipient_object_id=donor.id,
                read=False
            ).count()
        except Exception:
            unread_count = 0
    return {'donor_unread_notification_count': unread_count}
