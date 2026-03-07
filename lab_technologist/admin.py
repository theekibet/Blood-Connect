# lab_technologist/admin.py
from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from .models import LabTechnologistProfile, BloodTest

@admin.register(LabTechnologistProfile)
class LabTechnologistProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'center', 'phone', 'is_approved', 'is_active', 'created_at']
    list_filter = ['is_approved', 'is_active', 'center']
    search_fields = ['user__username', 'employee_id', 'license_number']
    readonly_fields = ['created_at', 'updated_at', 'approved_at']
    
    actions = ['approve_lab_techs']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'profile_pic', 'employee_id', 'phone')
        }),
        ('Professional Details', {
            'fields': ('qualification', 'license_number', 'specialization', 'years_of_experience')
        }),
        ('Certification', {
            'fields': ('certification_date', 'certification_expiry')
        }),
        ('Assignment', {
            'fields': ('center',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_approved', 'approved_by', 'approved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def approve_lab_techs(self, request, queryset):
        """Admin action to approve selected lab techs"""
        updated = queryset.update(
            is_approved=True,
            approved_at=timezone.now(),
            approved_by=request.user
        )
        self.message_user(
            request, 
            f"✅ Successfully approved {updated} lab technologist(s).",
            messages.SUCCESS
        )
    approve_lab_techs.short_description = "Approve selected lab technologists"

@admin.register(BloodTest)
class BloodTestAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_barcode', 'blood_group', 'result', 'test_date', 'tested_by']
    list_filter = ['result', 'test_date']
    search_fields = ['blood_collection__donor__user__username', 'blood_group']
    readonly_fields = ['test_date']
    
    def get_barcode(self, obj):
        """Get barcode from related blood bag"""
        if not obj.blood_collection:
            return "No donation"
            
        # Try to get from blood bag barcode
        try:
            from blood.models import BloodBagBarcode
            blood_bag = BloodBagBarcode.objects.filter(
                blood_donation=obj.blood_collection
            ).first()
            if blood_bag:
                return blood_bag.barcode
        except ImportError:
            pass
            
        # Try to get from stock unit
        try:
            from blood.models import StockUnit
            stock_unit = StockUnit.objects.filter(
                blood_donation=obj.blood_collection
            ).first()
            if stock_unit:
                return stock_unit.barcode
        except ImportError:
            pass
            
        # Fallback
        return f"Donation #{obj.blood_collection.id}"
    
    get_barcode.short_description = 'Barcode'
    get_barcode.admin_order_field = 'blood_collection__id'