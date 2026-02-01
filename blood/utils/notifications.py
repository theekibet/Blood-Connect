from django.contrib.contenttypes.models import ContentType
from blood.models import Notification   

def create_notification(
    title,
    message,
    recipient_obj,
    sender_obj=None,
    action="",
    reason="",
    appointment_date=None,
    bloodgroup="",
    unit=None
):
    recipient_ct = ContentType.objects.get_for_model(recipient_obj.__class__)
    sender_ct = ContentType.objects.get_for_model(sender_obj.__class__) if sender_obj else None

    Notification.objects.create(
        title=title,
        message=message,
        recipient_content_type=recipient_ct,
        recipient_object_id=recipient_obj.id,

        sender_content_type=sender_ct,
        sender_object_id=sender_obj.id if sender_obj else None,

        action=action,
        reason=reason,
        appointment_date=appointment_date,
        bloodgroup=bloodgroup,
        unit=unit
    )
