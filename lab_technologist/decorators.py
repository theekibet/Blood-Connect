# lab_technologist/decorators.py
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from .models import LabTechnologistProfile

def lab_tech_approved_required(view_func):
    """
    Decorator to check if lab technologist is approved by admin.
    Redirects to pending approval page if not approved.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('lab_technologist:login')
        
        try:
            profile = request.user.lab_tech_profile
            
            # Check if approved
            if not profile.is_approved:
                messages.warning(
                    request,
                    "Your account is pending admin approval. "
                    "You will be notified once your account is activated."
                )
                return redirect('lab_technologist:pending_approval')
                
        except LabTechnologistProfile.DoesNotExist:
            messages.error(request, "Lab Technologist profile not found.")
            return redirect('lab_technologist:login')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view