# blood/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    Stock, DonationCenter, StockUnit,
    BloodDriveEvent, Banner, Testimonial, HomePageStats,
    DonationFunFact, UserFactInteraction, DailyFactChallenge,
    QuizAttempt, FactContribution, BloodBagBarcode
)
from phlebotomist.models import Appointment

# Existing admin registrations
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
        'id', 'date', 'donor', 'phlebotomist', 
        'center', 'status_colored', 'created_at'
    )
    
    list_filter = (
        'status',
        'center',
        'phlebotomist',
        'date',
    )
    
    search_fields = (
        'donor__user__username',
        'donor__user__first_name',
        'donor__user__last_name',
        'phlebotomist__user__username',
        'phlebotomist__user__first_name',
        'phlebotomist__user__last_name',
        'status',
    )
    
    ordering = ('-date',)
    
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('date', 'center', 'phlebotomist', 'donor')
        }),
        ('Status', {
            'fields': ('status', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_colored(self, obj):
        """Display colored status badge"""
        colors = {
            'pending': '#ffc107',    # yellow
            'approved': '#17a2b8',   # teal
            'completed': '#28a745',  # green
            'cancelled': '#6c757d',  # gray
            'rejected': '#dc3545',   # red
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold; background: {}20; padding: 3px 8px; border-radius: 4px;">{}</span>',
            color,
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    status_colored.admin_order_field = 'status'
    
    actions = ['mark_as_pending', 'mark_as_approved', 'mark_as_completed']
    
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(status='pending')
        self.message_user(request, f"{updated} appointment(s) marked as pending.")
    mark_as_pending.short_description = "Mark selected as Pending"
    
    def mark_as_approved(self, request, queryset):
        updated = queryset.update(status='approved')
        self.message_user(request, f"{updated} appointment(s) marked as approved.")
    mark_as_approved.short_description = "Mark selected as Approved"
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f"{updated} appointment(s) marked as completed.")
    mark_as_completed.short_description = "Mark selected as Completed"

# Blood Drive & Homepage Content
@admin.register(BloodDriveEvent)
class BloodDriveEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'event_date', 'is_active', 'display_order']
    list_filter = ['is_active', 'event_date']
    search_fields = ['title', 'location']
    list_editable = ['is_active', 'display_order']
    date_hierarchy = 'event_date'

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'start_date', 'end_date', 'display_order']
    list_filter = ['is_active']
    search_fields = ['title']
    list_editable = ['is_active', 'display_order']

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'rating', 'is_featured', 'is_active', 'display_order']
    list_filter = ['is_featured', 'is_active', 'rating']
    search_fields = ['name']
    list_editable = ['is_featured', 'is_active', 'display_order']

@admin.register(HomePageStats)
class HomePageStatsAdmin(admin.ModelAdmin):
    list_display = ['stat_name', 'stat_value', 'icon_class', 'is_active', 'display_order']
    list_editable = ['stat_value', 'is_active', 'display_order']

# Donation Fun Facts Section
@admin.register(DonationFunFact)
class DonationFunFactAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'has_quiz', 'likes', 'is_verified', 'created_at']
    list_filter = ['category', 'has_quiz', 'is_verified']
    search_fields = ['title']
    list_editable = ['is_verified']
    ordering = ['-created_at']

@admin.register(UserFactInteraction)
class UserFactInteractionAdmin(admin.ModelAdmin):
    list_display = ['user', 'fact', 'interaction_type', 'timestamp']
    list_filter = ['interaction_type', 'timestamp']
    search_fields = ['user__username']

@admin.register(DailyFactChallenge)
class DailyFactChallengeAdmin(admin.ModelAdmin):
    list_display = ['date', 'fact']
    list_filter = ['date']

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'score', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']

@admin.register(FactContribution)
class FactContributionAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'category', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'category']
    search_fields = ['title', 'user__username']
    list_editable = ['is_approved']
    
    actions = ['approve_contributions']
    
    def approve_contributions(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            is_approved=True,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} contribution(s) approved successfully.")
    approve_contributions.short_description = "Approve selected contributions"

# Blood Bag Barcodes
@admin.register(BloodBagBarcode)
class BloodBagBarcodeAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'bag_type', 'volume_ml', 'status', 'assigned_to_donor']
    list_filter = ['status', 'bag_type']
    search_fields = ['barcode']
    readonly_fields = ['barcode', 'created_at']
    
    actions = ['generate_barcodes']
    
    def generate_barcodes(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        
        count = 10
        barcodes = generate_batch_barcodes(count=count, created_by=request.user)
        self.message_user(
            request, 
            f"✅ Generated {len(barcodes)} new barcodes"
        )
    generate_barcodes.short_description = "Generate 10 new barcodes"
