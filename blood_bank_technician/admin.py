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
