from django.contrib.contenttypes.models import ContentType
from .models import Patient
from blood.models import Notification 

def patient_notification_count(request):
    unread_count = 0
    if request.user.is_authenticated:
        try:
            patient = Patient.objects.get(user=request.user)
            patient_ct = ContentType.objects.get_for_model(Patient)
            unread_count = Notification.objects.filter(
                recipient_content_type=patient_ct,
                recipient_object_id=patient.id,
                read=False
            ).count()
        except Exception:
            unread_count = 0
    return {'unread_count': unread_count}
