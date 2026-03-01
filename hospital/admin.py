# hospital/admin.py
from django.contrib import admin
from .models import Hospital, HospitalUser, HospitalBloodRequest

@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ['name', 'registration_number', 'county', 'contact_person', 'contact_phone', 'is_active', 'verified']
    list_filter = ['county', 'is_active', 'verified']
    search_fields = ['name', 'registration_number', 'contact_person']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(HospitalUser)
class HospitalUserAdmin(admin.ModelAdmin):
    list_display = ['hospital', 'user', 'role', 'is_primary_contact', 'is_active']
    list_filter = ['role', 'is_active', 'hospital__county']
    search_fields = ['hospital__name', 'user__username']

@admin.register(HospitalBloodRequest)
class HospitalBloodRequestAdmin(admin.ModelAdmin):
    list_display = ['request_number', 'hospital', 'blood_group', 'units_requested', 'urgency', 'status', 'created_at']
    list_filter = ['status', 'urgency', 'blood_group', 'hospital__county']
    search_fields = ['request_number', 'hospital__name', 'patient_first_name', 'patient_last_name']
    readonly_fields = ['request_number', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Request Info', {
            'fields': ('request_number', 'hospital', 'requested_by')
        }),
        ('Blood Details', {
            'fields': ('blood_group', 'units_requested', 'units_dispatched')
        }),
        ('Patient Details', {
            'fields': ('patient_first_name', 'patient_last_name', 'patient_age', 'patient_gender', 'patient_id'),
            'classes': ('wide',)
        }),
        ('Medical Info', {
            'fields': ('doctor_name', 'doctor_license', 'urgency'),
            'classes': ('wide',)
        }),
        ('Status', {
            'fields': ('status', 'rejection_reason', 'assigned_centre')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Dispatch', {
            'fields': ('dispatched_by', 'dispatched_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
