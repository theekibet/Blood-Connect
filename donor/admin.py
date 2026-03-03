# donor/admin.py
from django.contrib import admin
from .models import Donor, DonorEligibility, BloodDonate

@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'bloodgroup', 'mobile', 'national_id', 'total_donations']
    list_filter = ['bloodgroup', 'county']
    search_fields = ['user__username', 'user__email', 'mobile', 'national_id']
    readonly_fields = ['points', 'total_donations', 'last_donation_date']

@admin.register(DonorEligibility)
class DonorEligibilityAdmin(admin.ModelAdmin):
    list_display = ['donor', 'approved', 'age', 'weight']
    list_filter = ['approved', 'gender']
    search_fields = ['donor__user__username']

@admin.register(BloodDonate)
class BloodDonateAdmin(admin.ModelAdmin):
    list_display = ['id', 'donor', 'bloodgroup', 'unit', 'status', 'date']
    list_filter = ['status', 'bloodgroup', 'donation_center']
    search_fields = ['donor__user__username', 'donor__user__email']
    date_hierarchy = 'date'