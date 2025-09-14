from django.contrib.contenttypes.models import ContentType
from .models import Patient
from blood.models import Notification 
def patient_notification_count(request):
    if request.user.is_authenticated:
        try:
            patient = Patient.objects.get(user=request.user) # To get the Patient instance
            patient_content_type = ContentType.objects.get_for_model(Patient) # Fetches the ContentType for Patient model
            #counts the unread notifications for this patient:
            unread_count = Notification.objects.filter(
                recipient_content_type=patient_content_type,
                recipient_object_id=patient.id,
                read=False
            ).count()
            return {'unread_count': unread_count}
        except Patient.DoesNotExist:
            return {'unread_count': 0}
    return {'unread_count': 0}
