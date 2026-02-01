# blood/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging
import time

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    retry_backoff=True,
    retry_jitter=True,
    rate_limit='30/m'  # 30 tasks per minute per worker (better than 10 for bursts)
)
def send_verification_email_task(self, user_id, user_email, domain, user_type="User"):
    """
    Celery task to send email verification link asynchronously.
    Rate limited to 30 tasks per minute per worker.

    Args:
        user_id (int): Django User ID
        user_email (str): Recipient email
        domain (str): Domain name (e.g., example.com)
        user_type (str): 'Donor', 'Nurse', 'Patient', etc. (for personalized email)
    """
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        logger.info(f"Starting verification email task for user_id={user_id} ({user_email})")

        # Generate verification token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Build verification URL
        verification_link = f"https://{domain}/verify-email/{uid}/{token}/"

        # Render email HTML template
        html_message = render_to_string('shared/verification_email.html', {
            'user': user,
            'verification_url': verification_link,
            'site_name': 'BloodConnect',
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'user_type': user_type,
        })
        plain_message = strip_tags(html_message)
        subject = f"Verify Your Email - BloodConnect {user_type} Account"

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            fail_silently=False,
            html_message=html_message,
        )

        logger.info(f"Verification email successfully sent to {user_email}")
        return f"Verification email sent to {user_email}"

    except User.DoesNotExist:
        logger.error(f"User with id={user_id} not found")
        return f"Failed to send email: User not found"
    except Exception as e:
        logger.error(f"Failed to send verification email to {user_email}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task
def celery_keep_alive_task():
    """
    Keep-alive task to prevent Railway from stopping idle Celery workers.
    This task runs every 5 minutes via Celery Beat to keep the worker active.
    """
    logger.debug("Celery keep-alive heartbeat")
    return {
        "status": "alive",
        "timestamp": time.time(),
        "service": "bloodbankmanagement-celery-worker"
    }


@shared_task
def debug_task():
    """
    Simple debug task for testing Celery setup.
    """
    logger.info("Debug task executed successfully")
    return "Celery is working!"