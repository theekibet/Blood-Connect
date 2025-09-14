from .models import BloodRequest  
from donor.models import BloodDonate 

def admin_notification_counts(request):
    new_requests_count = BloodRequest.objects.filter(status='Pending', is_seen=False).count()
    new_donations_count = BloodDonate.objects.filter(is_seen=False).count()
    return {
        'new_requests_count': new_requests_count,
        'new_donations_count': new_donations_count
    }
