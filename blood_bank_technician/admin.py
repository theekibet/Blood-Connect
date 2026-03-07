from django.contrib import admin
from .models import BloodBankTechProfile, BloodDispatch, InventoryAlert, HospitalCommunication
from django.contrib import messages
from django.utils import timezone


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

@admin.register(BloodBankTechProfile)
class BloodBankTechProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'center', 'is_approved', 'is_active', 'created_at']
    list_filter = ['is_approved', 'is_active', 'center']
    search_fields = ['user__username', 'user__email', 'employee_id', 'phone']
    readonly_fields = ['created_at', 'approved_at']
    
    actions = ['approve_technicians']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'employee_id', 'phone')
        }),
        ('Assignment', {
            'fields': ('center',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_approved', 'approved_at', 'approved_by')
        }),
        ('Profile', {
            'fields': ('profile_pic',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def approve_technicians(self, request, queryset):
        """Admin action to approve selected technicians"""
        updated = queryset.update(
            is_approved=True,
            approved_at=timezone.now(),
            approved_by=request.user
        )
        self.message_user(
            request, 
            f"✅ Successfully approved {updated} blood bank technician(s).",
            messages.SUCCESS
        )
    approve_technicians.short_description = "Approve selected technicians"