from django.contrib.contenttypes.models import ContentType
from .models import Notification
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Unified notification service that works across all apps
    """
    
    @staticmethod
    def send_to_user(recipient_user, sender_user, title, message):
        """
        Send notification to a specific user
        """
        try:
            recipient_content_type = ContentType.objects.get_for_model(recipient_user)
            sender_content_type = ContentType.objects.get_for_model(sender_user)
            
            notification = Notification.objects.create(
                title=title,
                message=message,
                recipient_content_type=recipient_content_type,
                recipient_object_id=recipient_user.id,
                sender_content_type=sender_content_type,
                sender_object_id=sender_user.id,
                is_read=False
            )
            
            logger.info(f"Notification sent to {recipient_user.username}: {title}")
            return notification
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return None
    
    @staticmethod
    def send_to_multiple_users(recipient_users, sender_user, title, message):
        """
        Send notification to multiple users
        """
        notifications = []
        for user in recipient_users:
            notif = NotificationService.send_to_user(user, sender_user, title, message)
            if notif:
                notifications.append(notif)
        return notifications
    
    @staticmethod
    def send_to_donor(donor, sender_user, title, message):
        """
        Send notification to a donor
        """
        return NotificationService.send_to_user(donor.user, sender_user, title, message)
    
    @staticmethod
    def send_to_phlebotomist(phlebotomist, sender_user, title, message):
        """
        Send notification to a phlebotomist
        """
        return NotificationService.send_to_user(phlebotomist.user, sender_user, title, message)
    
    @staticmethod
    def send_to_hospital_user(hospital_user, sender_user, title, message):
        """
        Send notification to a hospital user
        """
        return NotificationService.send_to_user(hospital_user.user, sender_user, title, message)
    
    @staticmethod
    def send_to_lab_tech(lab_tech, sender_user, title, message):
        """
        Send notification to a lab technologist
        """
        return NotificationService.send_to_user(lab_tech.user, sender_user, title, message)
    
    @staticmethod
    def send_to_blood_bank_tech(bb_tech, sender_user, title, message):
        """
        Send notification to a blood bank technician
        """
        return NotificationService.send_to_user(bb_tech.user, sender_user, title, message)
    
    @staticmethod
    def send_to_all_admins(title, message, exclude_user=None):
        """
        Send notification to all admin users
        """
        from django.contrib.auth.models import User
        admins = User.objects.filter(is_superuser=True)
        if exclude_user:
            admins = admins.exclude(id=exclude_user.id)
        
        notifications = []
        for admin in admins:
            notif = NotificationService.send_to_user(admin, admin, title, message)
            if notif:
                notifications.append(notif)
        return notifications