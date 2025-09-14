from django.contrib.contenttypes.models import ContentType
from blood.models import Notification
from donor.models import Donor

def donor_notification_count(request):
    if request.user.is_authenticated:
        try:
            donor = Donor.objects.get(user=request.user)
            donor_content_type = ContentType.objects.get_for_model(Donor)
            unread_count = Notification.objects.filter(
                recipient_content_type=donor_content_type,
                recipient_object_id=donor.id,
                read=False
            ).count()
        except Donor.DoesNotExist:
            unread_count = 0
    else:
        unread_count = 0

    return {'donor_unread_notification_count': unread_count}
