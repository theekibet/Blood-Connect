# blood/notification_utils.py
"""
Centralized notification utilities for blood request appointments
Ensures consistent notifications for all appointment actions
"""

from django.contrib.contenttypes.models import ContentType
from blood.models import Notification
from patient.models import Patient
from nurse.models import Nurse
import logging

logger = logging.getLogger(__name__)


def create_bloodrequest_appointment_notification(
    appointment,
    action,
    actor_user,
    reason=None,
    send_to='both'  # 'both', 'patient', 'nurse'
):
    """
    Create notifications for blood request appointment actions.
    
    Args:
        appointment: Appointment instance
        action: str - 'created', 'approved', 'rejected', 'cancelled', 'completed'
        actor_user: User who performed the action
        reason: Optional reason text for rejection/cancellation
        send_to: Who should receive notification - 'both', 'patient', or 'nurse'
    """
    
    linked_request = getattr(appointment, "request", None)
    if not linked_request:
        logger.warning(f"No linked request for appointment {appointment.id}")
        return
    
    # Determine actor type
    actor_type = None
    actor_name = actor_user.get_full_name() or actor_user.username
    
    if hasattr(actor_user, 'nurse'):
        actor_type = 'Nurse'
    elif hasattr(actor_user, 'patient'):
        actor_type = 'Patient'
    else:
        actor_type = 'Admin'
    
    # Get appointment details
    date_str = appointment.date.strftime("%b %d, %Y at %I:%M %p")
    center_name = getattr(linked_request.donation_center, 'name', 'Unknown Center')
    bloodgroup = getattr(linked_request, 'bloodgroup', 'N/A')
    unit = getattr(linked_request, 'unit', 0)
    
    # Define notification templates
    templates = {
        'created': {
            'title': 'New Blood Request Appointment',
            'patient_msg': f"Your blood request appointment has been scheduled for {date_str} at {center_name}. Please wait for nurse approval.",
            'nurse_msg': f"New blood request appointment scheduled for {date_str}. Patient needs {unit}ml of {bloodgroup} blood. Please review and approve.",
        },
        'approved': {
            'title': 'Appointment Approved',
            'patient_msg': f"Great news! Your blood request appointment on {date_str} at {center_name} has been APPROVED by {actor_type} {actor_name}. Please arrive 15 minutes early.",
            'nurse_msg': f"You approved the blood request appointment for {date_str}. Patient needs {unit}ml of {bloodgroup} blood.",
        },
        'rejected': {
            'title': 'Appointment Rejected',
            'patient_msg': f"Your blood request appointment on {date_str} at {center_name} was REJECTED by {actor_type} {actor_name}.{' Reason: ' + reason if reason else ' Please contact the center for details.'}",
            'nurse_msg': f"You rejected the blood request appointment for {date_str}.{' Reason: ' + reason if reason else ''}",
        },
        'cancelled': {
            'title': 'Appointment Cancelled',
            'patient_msg': f"Your blood request appointment on {date_str} at {center_name} has been CANCELLED.{' Reason: ' + reason if reason else ''}",
            'nurse_msg': f"Blood request appointment on {date_str} was CANCELLED by {actor_type} {actor_name}.{' Reason: ' + reason if reason else ''} Patient needed {unit}ml of {bloodgroup} blood.",
        },
        'completed': {
            'title': 'Appointment Completed',
            'patient_msg': f"Your blood request appointment on {date_str} at {center_name} has been COMPLETED. {unit}ml of {bloodgroup} blood was successfully provided. Thank you!",
            'nurse_msg': f"You completed the blood request appointment for {date_str}. Successfully provided {unit}ml of {bloodgroup} blood to patient.",
        },
    }
    
    if action not in templates:
        logger.error(f"Unknown action: {action}")
        return
    
    template = templates[action]
    
    # Send to patient
    if send_to in ['both', 'patient'] and appointment.patient:
        try:
            patient = appointment.patient
            Notification.objects.create(
                title=template['title'],
                message=template['patient_msg'],
                action=action,
                reason=reason if action in ['rejected', 'cancelled'] else None,
                appointment_date=appointment.date,
                bloodgroup=bloodgroup,
                unit=unit,
                recipient_content_type=ContentType.objects.get_for_model(Patient),
                recipient_object_id=patient.id,
                sender_content_type=ContentType.objects.get_for_model(actor_user.__class__),
                sender_object_id=actor_user.id,
                read=False,
            )
            logger.info(f"✅ Notification sent to patient {patient.id} for appointment {appointment.id} ({action})")
        except Exception as e:
            logger.error(f"❌ Failed to send notification to patient: {e}")
    
    # Send to nurse
    if send_to in ['both', 'nurse'] and appointment.nurse:
        try:
            nurse = appointment.nurse
            Notification.objects.create(
                title=template['title'],
                message=template['nurse_msg'],
                action=action,
                reason=reason if action in ['rejected', 'cancelled'] else None,
                appointment_date=appointment.date,
                bloodgroup=bloodgroup,
                unit=unit,
                recipient_content_type=ContentType.objects.get_for_model(Nurse),
                recipient_object_id=nurse.id,
                sender_content_type=ContentType.objects.get_for_model(actor_user.__class__),
                sender_object_id=actor_user.id,
                read=False,
            )
            logger.info(f"✅ Notification sent to nurse {nurse.id} for appointment {appointment.id} ({action})")
        except Exception as e:
            logger.error(f"❌ Failed to send notification to nurse: {e}")
