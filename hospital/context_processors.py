from .models import HospitalUser

def hospital_user_context(request):
    """Add hospital user info to template context"""
    if request.user.is_authenticated:
        try:
            hospital_user = HospitalUser.objects.get(user=request.user, is_active=True)
            return {
                'hospital_user': hospital_user,
                'hospital': hospital_user.hospital,
            }
        except HospitalUser.DoesNotExist:
            pass
    return {}
