from django.contrib import admin
from .models import Stock, DonationCenter, StockUnit
from nurse.models import Appointment

admin.site.register(Stock)

@admin.register(DonationCenter)
class DonationCenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'contact_number')
@admin.register(StockUnit)
class StockUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'barcode', 'bloodgroup', 'unit', 'expiry_date', 'center', 'added_on')
    list_filter = ('bloodgroup', 'center', 'expiry_date')
    search_fields = ('barcode',)
    ordering = ('expiry_date',)
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'date', 'nurse', 'get_donor', 'get_patient',
        'status', 'created_at', 'status_changed_by', 'status_changed_at'
    )
    list_filter = (
        'status',
        'nurse',
        'date',
        'created_at',
    )
    search_fields = (
        'donor__user__username',
        'patient__user__username',
        'nurse__user__username',
        'status',
        'barcode'  # only if your related request has it
    )
    ordering = ('-date',)

    # readonly audit fields
    readonly_fields = (
        'created_at', 'status_changed_at',
        'approved_at_nurse', 'completed_at_nurse',
        'cancelled_at', 'rejected_at'
    )

    def get_donor(self, obj):
        return obj.donor.user.username if obj.donor else "—"
    get_donor.short_description = "Donor"

    def get_patient(self, obj):
        return obj.patient.user.username if obj.patient else "—"
    get_patient.short_description = "Patient"



from .models import BloodDriveEvent, Banner, Testimonial, HomePageStats

@admin.register(BloodDriveEvent)
class BloodDriveEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'event_date', 'is_active', 'is_upcoming', 'display_order']
    list_filter = ['is_active', 'event_date', 'created_at']
    search_fields = ['title', 'location', 'address', 'description']
    list_editable = ['is_active', 'display_order']
    date_hierarchy = 'event_date'
    fieldsets = (
        ('Event Information', {
            'fields': ('title', 'description', 'image')
        }),
        ('Location Details', {
            'fields': ('location', 'address', 'latitude', 'longitude')
        }),
        ('Date & Time', {
            'fields': ('event_date', 'end_date')
        }),
        ('Contact Information', {
            'fields': ('contact_phone', 'contact_email')
        }),
        ('Display Settings', {
            'fields': ('is_active', 'display_order')
        }),
    )

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['title', 'banner_type', 'is_active', 'is_current', 'start_date', 'end_date', 'display_order']
    list_filter = ['banner_type', 'is_active', 'start_date']
    search_fields = ['title', 'message']
    list_editable = ['is_active', 'display_order']
    date_hierarchy = 'start_date'

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'rating', 'is_featured', 'is_active', 'display_order']
    list_filter = ['is_featured', 'is_active', 'rating']
    search_fields = ['name', 'role', 'testimonial']
    list_editable = ['is_featured', 'is_active', 'display_order']

@admin.register(HomePageStats)
class HomePageStatsAdmin(admin.ModelAdmin):
    list_display = ['stat_name', 'stat_value', 'icon_class', 'is_active', 'display_order']
    list_editable = ['stat_value', 'is_active', 'display_order']