from django.contrib import admin
from .models import LabTechnologistProfile, BloodTest

@admin.register(LabTechnologistProfile)
class LabTechnologistProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'center', 'phone']
    search_fields = ['user__username', 'employee_id']

@admin.register(BloodTest)
class BloodTestAdmin(admin.ModelAdmin):
    list_display = ['blood_collection', 'blood_group', 'result', 'test_date']
    list_filter = ['result', 'test_date']
    search_fields = ['blood_collection__barcode']
