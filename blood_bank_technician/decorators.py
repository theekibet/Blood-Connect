# blood_bank_technician/decorators.py
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from .models import BloodBankTechProfile  # Make sure this import is correct

def blood_bank_tech_approved_required(view_func):
    """
    Decorator to check if blood bank technician is approved by admin.
    Redirects to pending approval page if not approved.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('blood_bank_technician:login')
        
        try:
            profile = request.user.blood_bank_tech_profile
            
            # Check if approved
            if not profile.is_approved:
                messages.warning(
                    request,
                    "Your account is pending admin approval. "
                    "You will be notified once your account is activated."
                )
                return redirect('blood_bank_technician:pending_approval')
                
        except BloodBankTechProfile.DoesNotExist:
            messages.error(request, "Blood Bank Technician profile not found.")
            return redirect('blood_bank_technician:login')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view