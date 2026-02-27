#!/bin/bash

echo "🧹 Starting complete cleanup of patient and request references..."

# ============================================
# 1. FIX BLOOD_BANK_TECHNICIAN FILES
# ============================================

echo "📁 Cleaning blood_bank_technician..."

# Fix blood_bank_technician/views.py - Remove all blood_request and patient references
cat > blood_bank_technician/views.py << 'EOF'
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from .models import BloodBankTechProfile, BloodDispatch
from blood.models import StockUnit, StockTransaction
from hospital.models import BloodRequest
from django.db.models import Q

@login_required
def dashboard(request):
    """Blood Bank Technician Dashboard"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    # Get pending hospital requests
    pending_requests = BloodRequest.objects.filter(status='pending')
    
    # Get available stock
    available_stock = StockUnit.objects.filter(is_available=True, is_quarantined=False)
    
    context = {
        'profile': profile,
        'pending_requests': pending_requests,
        'available_stock': available_stock,
        'pending_count': pending_requests.count(),
        'stock_count': available_stock.count(),
    }
    return render(request, 'blood_bank_technician/dashboard.html', context)

@login_required
def pending_requests(request):
    """View all pending blood requests from hospitals"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    requests = BloodRequest.objects.filter(status='pending').order_by('-created_at')
    
    context = {
        'profile': profile,
        'requests': requests,
    }
    return render(request, 'blood_bank_technician/pending_requests.html', context)

@login_required
def approved_requests(request):
    """View approved requests ready for dispatch"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    requests = BloodRequest.objects.filter(
        status='approved'
    ).order_by('-updated_at')
    
    context = {
        'profile': profile,
        'requests': requests,
    }
    return render(request, 'blood_bank_technician/approved_requests.html', context)

@login_required
@transaction.atomic
def approve_request(request, request_id):
    """Approve a blood request and deduct from inventory"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    blood_request = get_object_or_404(BloodRequest, id=request_id, status='pending')
    
    if request.method == 'POST':
        # Find available stock using FIFO (oldest first)
        available_units = StockUnit.objects.filter(
            bloodgroup=blood_request.blood_group,
            is_available=True,
            is_quarantined=False
        ).order_by('created_at')[:blood_request.units_requested]
        
        total_available = available_units.count()
        
        if total_available < blood_request.units_requested:
            messages.error(
                request, 
                f"Insufficient stock. Need {blood_request.units_requested} units of {blood_request.blood_group}, "
                f"but only {total_available} available."
            )
            return redirect('blood_bank_technician:pending_requests')
        
        # Deduct each unit
        for unit in available_units:
            unit.is_available = False
            unit.save()
            
            StockTransaction.objects.create(
                stockunit=unit,
                quantity_deducted=unit.unit,
                transaction_type='deduction',
                user=request.user,
                notes=f"Deducted for hospital request #{blood_request.request_number}"
            )
        
        # Update request status
        blood_request.status = 'approved'
        blood_request.processed_by = profile
        blood_request.save()
        
        messages.success(
            request, 
            f"Request approved. {blood_request.units_requested} units of {blood_request.blood_group} deducted from inventory."
        )
        return redirect('blood_bank_technician:approved_requests')
    
    context = {
        'request': blood_request,
        'profile': profile,
    }
    return render(request, 'blood_bank_technician/approve_request.html', context)

@login_required
def dispatch_request(request, request_id):
    """Mark request as dispatched (picked up by hospital)"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    blood_request = get_object_or_404(
        BloodRequest, 
        id=request_id, 
        status='approved'
    )
    
    if request.method == 'POST':
        # Create dispatch record
        dispatch = BloodDispatch.objects.create(
            hospital_request=blood_request,
            dispatched_by=profile,
            collected_by_name=request.POST.get('collected_by_name'),
            collected_by_id=request.POST.get('collected_by_id'),
            collected_by_phone=request.POST.get('collected_by_phone', ''),
            collection_time=timezone.now(),
            hospital=blood_request.hospital,
            status='dispatched'
        )
        
        # Update request status
        blood_request.status = 'dispatched'
        blood_request.save()
        
        messages.success(request, f"Blood dispatched successfully to {blood_request.hospital.name}")
        return redirect('blood_bank_technician:approved_requests')
    
    context = {
        'request': blood_request,
        'profile': profile,
    }
    return render(request, 'blood_bank_technician/dispatch_request.html', context)

@login_required
def reject_request(request, request_id):
    """Reject a blood request"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    blood_request = get_object_or_404(BloodRequest, id=request_id, status='pending')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        
        blood_request.status = 'rejected'
        blood_request.rejection_reason = reason
        blood_request.processed_by = profile
        blood_request.save()
        
        messages.warning(request, f"Request #{blood_request.request_number} rejected")
        return redirect('blood_bank_technician:pending_requests')
    
    context = {
        'request': blood_request,
        'profile': profile,
    }
    return render(request, 'blood_bank_technician/reject_request.html', context)

@login_required
def inventory(request):
    """View current inventory"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    stock = StockUnit.objects.filter(
        is_quarantined=False
    ).order_by('bloodgroup', 'created_at')
    
    # Group by blood group
    blood_groups = {}
    for unit in stock:
        if unit.bloodgroup not in blood_groups:
            blood_groups[unit.bloodgroup] = {
                'total': 0,
                'available': 0,
                'units': []
            }
        blood_groups[unit.bloodgroup]['units'].append(unit)
        blood_groups[unit.bloodgroup]['total'] += 1
        if unit.is_available:
            blood_groups[unit.bloodgroup]['available'] += 1
    
    context = {
        'profile': profile,
        'blood_groups': blood_groups,
        'total_units': stock.count(),
    }
    return render(request, 'blood_bank_technician/inventory.html', context)

@login_required
def request_history(request):
    """View request history"""
    profile = get_object_or_404(BloodBankTechProfile, user=request.user)
    
    requests = BloodRequest.objects.all().order_by('-created_at')[:50]
    
    context = {
        'profile': profile,
        'requests': requests,
    }
    return render(request, 'blood_bank_technician/request_history.html', context)
EOF

# Fix blood_bank_technician/admin.py
cat > blood_bank_technician/admin.py << 'EOF'
from django.contrib import admin
from .models import BloodBankTechProfile, BloodDispatch, InventoryAlert, HospitalCommunication

@admin.register(BloodBankTechProfile)
class BloodBankTechProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'center', 'phone', 'is_active']
    list_filter = ['center', 'is_active']
    search_fields = ['user__username', 'employee_id', 'phone']

@admin.register(BloodDispatch)
class BloodDispatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'stock_unit', 'hospital', 'dispatch_date', 'collected_by_name', 'status']
    list_filter = ['status', 'hospital']
    search_fields = ['hospital__name', 'collected_by_name']
    readonly_fields = ['dispatch_date']

@admin.register(InventoryAlert)
class InventoryAlertAdmin(admin.ModelAdmin):
    list_display = ['center', 'alert_type', 'blood_group', 'is_resolved', 'created_at']
    list_filter = ['alert_type', 'is_resolved', 'center']

@admin.register(HospitalCommunication)
class HospitalCommunicationAdmin(admin.ModelAdmin):
    list_display = ['hospital', 'comm_type', 'subject', 'sent_at', 'read_at']
    list_filter = ['comm_type', 'hospital']
EOF

# Fix blood_bank_technician/models.py
cat > blood_bank_technician/models.py << 'EOF'
from django.db import models
from django.conf import settings
from blood.models import DonationCenter, StockUnit
from hospital.models import Hospital, BloodRequest

class BloodBankTechProfile(models.Model):
    """Blood Bank Technician profile"""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blood_bank_tech_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True)
    profile_pic = models.ImageField(upload_to='bloodbank_profiles/', null=True, blank=True)
    center = models.ForeignKey(
        DonationCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blood_bank_technicians'
    )
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Blood Bank Tech: {self.user.get_full_name()} - {self.employee_id}"

class BloodDispatch(models.Model):
    """Record of blood dispatched to hospitals"""
    
    stock_unit = models.ForeignKey(
        StockUnit,
        on_delete=models.CASCADE,
        related_name='dispatches',
        help_text="Stock unit that was dispatched"
    )
    
    hospital_request = models.ForeignKey(
        BloodRequest,
        on_delete=models.CASCADE,
        related_name='dispatches',
        help_text="Hospital blood request this dispatch fulfills"
    )
    
    dispatched_by = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='dispatches_made'
    )
    dispatch_date = models.DateTimeField(auto_now_add=True)
    
    collected_by_name = models.CharField(
        max_length=200,
        help_text="Name of hospital staff who collected"
    )
    collected_by_id = models.CharField(
        max_length=50,
        help_text="ID number of hospital staff"
    )
    collected_by_phone = models.CharField(
        max_length=15,
        blank=True,
        help_text="Contact phone of hospital staff"
    )
    collection_time = models.DateTimeField(
        help_text="When the blood was picked up"
    )
    
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='received_dispatches',
        help_text="Hospital receiving the blood"
    )
    hospital_authorization = models.CharField(
        max_length=100,
        blank=True,
        help_text="Authorization number/reference from hospital"
    )
    
    STATUS_CHOICES = [
        ('pending', 'Pending Pickup'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered to Hospital'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    notes = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_to = models.CharField(max_length=200, blank=True)
    delivery_notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Blood Dispatch"
        verbose_name_plural = "Blood Dispatches"
        ordering = ['-dispatch_date']
    
    def __str__(self):
        return f"Dispatch {self.id}: {self.stock_unit.bloodgroup} to {self.hospital.name}"

class InventoryAlert(models.Model):
    """Alerts for low inventory or expiring blood"""
    
    center = models.ForeignKey(
        DonationCenter,
        on_delete=models.CASCADE,
        related_name='inventory_alerts'
    )
    
    ALERT_TYPE_CHOICES = [
        ('low_stock', 'Low Stock'),
        ('expiring', 'Expiring Soon'),
        ('out_of_stock', 'Out of Stock'),
    ]
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    blood_group = models.CharField(
        max_length=5,
        choices=StockUnit.BLOOD_GROUP_CHOICES,
        blank=True,
        null=True
    )
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.center.name}"

class HospitalCommunication(models.Model):
    """Track communication with hospitals"""
    
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='communications'
    )
    blood_bank_tech = models.ForeignKey(
        BloodBankTechProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='hospital_communications'
    )
    
    COMMUNICATION_TYPE_CHOICES = [
        ('request_received', 'Request Received'),
        ('request_approved', 'Request Approved'),
        ('request_rejected', 'Request Rejected'),
        ('ready_for_pickup', 'Ready for Pickup'),
        ('dispatched', 'Dispatched'),
        ('follow_up', 'Follow Up'),
        ('general', 'General')
    ]
    
    comm_type = models.CharField(max_length=20, choices=COMMUNICATION_TYPE_CHOICES)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    
    related_request = models.ForeignKey(
        BloodRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='communications'
    )
    
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.get_comm_type_display()} - {self.hospital.name} - {self.sent_at}"
EOF

# ============================================
# 2. FIX NURSE MODELS
# ============================================
echo "📁 Cleaning nurse/models.py..."

cat > nurse/models.py << 'EOF'
from django.db import models
from django.contrib.auth.models import User
from donor.models import Donor
from blood.models import DonationCenter
from django.core.exceptions import ValidationError

class Nurse(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_pic = models.ImageField(upload_to='nurse_profiles/', null=True, blank=True)
    license_number = models.CharField(max_length=50, unique=True)
    center = models.ForeignKey(DonationCenter, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Nurse: {self.user.get_full_name()}"

class Appointment(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateTimeField()
    center = models.ForeignKey(DonationCenter, on_delete=models.CASCADE)
    nurse = models.ForeignKey(Nurse, on_delete=models.CASCADE)
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"Appointment {self.id} - {self.donor.user.get_full_name()} - {self.date}"
    
    def clean(self):
        if not self.donor:
            raise ValidationError("Appointment must have a donor")
        if self.status not in dict(self.STATUS_CHOICES):
            raise ValidationError("Invalid status")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
EOF

# ============================================
# 3. FIX BLOOD VIEWS
# ============================================
echo "📁 Cleaning blood/views.py..."

cat > blood/views.py << 'EOF'
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from donor.models import Donor
from blood.models import DonationCenter, StockUnit

def home_view(request):
    return render(request, 'blood/index.html')

def about_view(request):
    return render(request, 'blood/about.html')

def contact_view(request):
    return render(request, 'blood/contact.html')

def donors_list(request):
    donors = Donor.objects.filter(is_active=True)
    return render(request, 'blood/donors_list.html', {'donors': donors})

def donation_centers(request):
    centers = DonationCenter.objects.all()
    return render(request, 'blood/donation_centers.html', {'centers': centers})

def blood_inventory(request):
    stock = StockUnit.objects.filter(is_quarantined=False)
    
    # Group by blood group
    blood_groups = {}
    for unit in stock:
        if unit.bloodgroup not in blood_groups:
            blood_groups[unit.bloodgroup] = {
                'total': 0,
                'available': 0,
                'expiring_soon': 0
            }
        blood_groups[unit.bloodgroup]['total'] += 1
        if unit.is_available:
            blood_groups[unit.bloodgroup]['available'] += 1
        if unit.expiry_date and (unit.expiry_date - timezone.now().date()).days <= 7:
            blood_groups[unit.bloodgroup]['expiring_soon'] += 1
    
    context = {
        'blood_groups': blood_groups,
        'total_units': stock.count(),
    }
    return render(request, 'blood/inventory.html', context)

def dashboard_stats(request):
    """API endpoint for dashboard stats"""
    total_donors = Donor.objects.filter(is_active=True).count()
    total_centers = DonationCenter.objects.count()
    available_units = StockUnit.objects.filter(is_available=True, is_quarantined=False).count()
    
    return JsonResponse({
        'total_donors': total_donors,
        'total_centers': total_centers,
        'available_units': available_units,
    })
EOF

# ============================================
# 4. FIX DONOR VIEWS
# ============================================
echo "📁 Cleaning donor/views.py..."

# Remove the 4 DonorBloodRequest lines from donor/views.py
sed -i '' "/{'icon': 'fa-paper-plane', 'label': 'Requests Made', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor).count(), 'color': 'requests-made-icon', 'description': 'Blood requests submitted'},/d" donor/views.py
sed -i '' "/{'icon': 'fa-clock', 'label': 'Pending Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='pending').count(), 'color': 'pending-requests-icon', 'description': 'Awaiting approval'},/d" donor/views.py
sed -i '' "/{'icon': 'fa-check-circle', 'label': 'Approved Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='approved').count(), 'color': 'approved-requests-icon', 'description': 'Successfully approved'},/d" donor/views.py
sed -i '' "/{'icon': 'fa-times-circle', 'label': 'Rejected Requests', 'count': DonorBloodRequest.objects.filter(request_by_donor=donor, status='rejected').count(), 'color': 'rejected-requests-icon', 'description': 'Not approved'},/d" donor/views.py

# ============================================
# 5. FIX SETTINGS AND URLS
# ============================================
echo "📁 Cleaning settings and URLs..."

# Update LOGIN_URL in settings
sed -i '' 's/LOGIN_URL = .\/patient\/patientlogin./LOGIN_URL = .\/donor\/donorlogin./g' bloodbankmanagement/settings.py

# Remove patient from INSTALLED_APPS
sed -i '' "/'patient',/d" bloodbankmanagement/settings.py

# Remove patient URLs from main urls.py
sed -i '' "/path('patient\/', include('patient.urls')),/d" bloodbankmanagement/urls.py
sed -i '' "/path('admin-patient\/', blood_views.admin_patient_view, name='admin-patient'),/d" bloodbankmanagement/urls.py
sed -i '' "/path('update-patient\/<int:pk>\/', blood_views.update_patient_view, name='update-patient'),/d" bloodbankmanagement/urls.py
sed -i '' "/path('delete-patient\/<int:pk>\/', blood_views.delete_patient_view, name='delete-patient'),/d" bloodbankmanagement/urls.py
sed -i '' "/path('bloodrequest\/<int:blood_request_id>\/stock-transactions\/', views.blood_request_stock_transactions, name='blood_request_stock_transactions'),/d" bloodbankmanagement/urls.py

# ============================================
# 6. CREATE EMPTY INIT FILES FOR PATIENT APP (if it still exists)
# ============================================
echo "📁 Disabling patient app..."

# If patient app directory exists, create empty __init__.py to break imports
if [ -d "patient" ]; then
    echo "# Patient app is disabled" > patient/__init__.py
    echo "from django.core.exceptions import ImproperlyConfigured" >> patient/__init__.py
    echo "raise ImproperlyConfigured('Patient app has been removed from the system')" >> patient/__init__.py
    
    # Create empty models.py
    echo "# Patient app is disabled" > patient/models.py
fi

# ============================================
# 7. MAKE MIGRATIONS
# ============================================
echo "📁 Making migrations..."
python manage.py makemigrations blood_bank_technician nurse donor blood

echo "📁 Applying migrations..."
python manage.py migrate

# ============================================
# 8. VERIFY CLEANUP
# ============================================
echo ""
echo "🔍 VERIFYING CLEANUP..."
echo "========================"

echo ""
echo "Checking for blood_request references:"
if grep -r "blood_request" --include="*.py" . | grep -v "migrations" | grep -q .; then
    grep -r "blood_request" --include="*.py" . | grep -v "migrations"
else
    echo "✅ None found"
fi

echo ""
echo "Checking for DonorBloodRequest references:"
if grep -r "DonorBloodRequest" --include="*.py" . | grep -v "migrations" | grep -q .; then
    grep -r "DonorBloodRequest" --include="*.py" . | grep -v "migrations"
else
    echo "✅ None found"
fi

echo ""
echo "Checking for patient references (excluding comments):"
if grep -r "patient" --include="*.py" . | grep -v "migrations" | grep -v "#" | grep -q .; then
    grep -r "patient" --include="*.py" . | grep -v "migrations" | grep -v "#"
else
    echo "✅ None found"
fi

echo ""
echo "✅ CLEANUP COMPLETE!"
echo "Run 'python manage.py runserver' to test"
EOF