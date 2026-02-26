from django.contrib import admin
from .models import BloodBankTechProfile, BloodDispatch

@admin.register(BloodBankTechProfile)
class BloodBankTechProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'center', 'phone', 'is_active']
    list_filter = ['center', 'is_active']
    search_fields = ['user__username', 'user__email', 'employee_id']
    raw_id_fields = ['user']

@admin.register(BloodDispatch)
class BloodDispatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'stock_unit', 'blood_request', 'dispatch_date', 'collected_by_name']
    list_filter = ['dispatch_date']
    search_fields = [
        'blood_request__request_by_patient__user__username',
        'stock_unit__barcode',
        'collected_by_name'
    ]
    raw_id_fields = ['stock_unit', 'blood_request']
    readonly_fields = ['dispatch_date']
    
    fieldsets = (
        ('Dispatch Information', {
            'fields': ('stock_unit', 'blood_request', 'dispatched_by')
        }),
        ('Collection Details', {
            'fields': ('collected_by_name', 'collected_by_id', 'collection_time', 'notes')
        }),
        ('Metadata', {
            'fields': ('dispatch_date',)
        }),
    )
