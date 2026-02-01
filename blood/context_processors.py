from patient.models import BloodRequest  
from donor.models import BloodDonate 

def admin_notification_counts(request):
    try:
        new_requests_count = BloodRequest.objects.filter(status='Pending', is_seen=False).count()
    except Exception:
        new_requests_count = 0

    try:
        new_donations_count = BloodDonate.objects.filter(is_seen=False).count()
    except Exception:
        new_donations_count = 0

    return {
        'new_requests_count': new_requests_count,
        'new_donations_count': new_donations_count
    }
