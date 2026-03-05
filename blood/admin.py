# blood/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    Stock, DonationCenter, StockUnit,
    BloodDriveEvent,  Testimonial, HomePageStats,
    
     BloodBagBarcode
)
from phlebotomist.models import Appointment
from .models import HoneypotAttempt
from .models import UserReview
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



# Blood Bag Barcodes@admin.register(BloodBagBarcode)
@admin.register(BloodBagBarcode)
class BloodBagBarcodeAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'bag_type', 'volume_ml', 'status', 'assigned_to_donor', 'created_at']
    list_filter = ['status', 'bag_type']
    search_fields = ['barcode']
    readonly_fields = ['barcode', 'created_at']
    
    # Disable manual addition
    def has_add_permission(self, request):
        return False  # This removes the "Add" button and prevents manual entry
    
    # Allow editing existing barcodes
    def has_change_permission(self, request, obj=None):
        return True
    
    # Allow deletion if needed
    def has_delete_permission(self, request, obj=None):
        return True
    
    fieldsets = (
        ('Barcode Information', {
            'fields': ('barcode', 'bag_type', 'volume_ml', 'anticoagulant')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Assignment Information', {
            'fields': ('assigned_to_donor', 'assigned_by', 'assigned_at'),
            'classes': ('collapse',),
        }),
        ('Collection Information', {
            'fields': ('collected_by', 'collected_at', 'blood_donation'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',),
        }),
    )
    
    # Actions for generating different bag types
    actions = [
        'generate_single_10', 'generate_single_50', 'generate_single_100',
        'generate_double_10', 'generate_double_50', 'generate_double_100',
        'generate_triple_10', 'generate_triple_50', 'generate_triple_100',
        'generate_pediatric_10', 'generate_pediatric_50', 'generate_pediatric_100'
    ]
    
    # ===== SINGLE BAG GENERATION =====
    def generate_single_10(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=10, bag_type='single', created_by=request.user)
        self.message_user(request, f"✅ Generated 10 Single Blood Bag barcodes")
    generate_single_10.short_description = "Generate 10 Single Blood Bag barcodes"
    
    def generate_single_50(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=50, bag_type='single', created_by=request.user)
        self.message_user(request, f"✅ Generated 50 Single Blood Bag barcodes")
    generate_single_50.short_description = "Generate 50 Single Blood Bag barcodes"
    
    def generate_single_100(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=100, bag_type='single', created_by=request.user)
        self.message_user(request, f"✅ Generated 100 Single Blood Bag barcodes")
    generate_single_100.short_description = "Generate 100 Single Blood Bag barcodes"
    
    # ===== DOUBLE BAG GENERATION =====
    def generate_double_10(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=10, bag_type='double', created_by=request.user)
        self.message_user(request, f"✅ Generated 10 Double Blood Bag barcodes")
    generate_double_10.short_description = "Generate 10 Double Blood Bag barcodes"
    
    def generate_double_50(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=50, bag_type='double', created_by=request.user)
        self.message_user(request, f"✅ Generated 50 Double Blood Bag barcodes")
    generate_double_50.short_description = "Generate 50 Double Blood Bag barcodes"
    
    def generate_double_100(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=100, bag_type='double', created_by=request.user)
        self.message_user(request, f"✅ Generated 100 Double Blood Bag barcodes")
    generate_double_100.short_description = "Generate 100 Double Blood Bag barcodes"
    
    # ===== TRIPLE BAG GENERATION =====
    def generate_triple_10(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=10, bag_type='triple', created_by=request.user)
        self.message_user(request, f"✅ Generated 10 Triple Blood Bag barcodes")
    generate_triple_10.short_description = "Generate 10 Triple Blood Bag barcodes"
    
    def generate_triple_50(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=50, bag_type='triple', created_by=request.user)
        self.message_user(request, f"✅ Generated 50 Triple Blood Bag barcodes")
    generate_triple_50.short_description = "Generate 50 Triple Blood Bag barcodes"
    
    def generate_triple_100(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=100, bag_type='triple', created_by=request.user)
        self.message_user(request, f"✅ Generated 100 Triple Blood Bag barcodes")
    generate_triple_100.short_description = "Generate 100 Triple Blood Bag barcodes"
    
    # ===== PEDIATRIC BAG GENERATION =====
    def generate_pediatric_10(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=10, bag_type='pediatric', created_by=request.user)
        self.message_user(request, f"✅ Generated 10 Pediatric Blood Bag barcodes")
    generate_pediatric_10.short_description = "Generate 10 Pediatric Blood Bag barcodes"
    
    def generate_pediatric_50(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=50, bag_type='pediatric', created_by=request.user)
        self.message_user(request, f"✅ Generated 50 Pediatric Blood Bag barcodes")
    generate_pediatric_50.short_description = "Generate 50 Pediatric Blood Bag barcodes"
    
    def generate_pediatric_100(self, request, queryset):
        from blood.utils.barcode_utils import generate_batch_barcodes
        barcodes = generate_batch_barcodes(count=100, bag_type='pediatric', created_by=request.user)
        self.message_user(request, f"✅ Generated 100 Pediatric Blood Bag barcodes")
    generate_pediatric_100.short_description = "Generate 100 Pediatric Blood Bag barcodes"
@admin.register(HoneypotAttempt)
class HoneypotAttemptAdmin(admin.ModelAdmin):
    list_display = ['ip', 'username', 'timestamp']
    list_filter = ['timestamp']
    search_fields = ['ip', 'username']
    readonly_fields = ['ip', 'username', 'password', 'user_agent', 'timestamp']
    
    def has_add_permission(self, request):
        return False  # Don't allow manual adding
    
    def has_change_permission(self, request, obj=None):
        return False 
    

@admin.register(UserReview)
class UserReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'rating', 'short_comment', 'created_at', 'is_read']
    list_filter = ['rating', 'is_read', 'created_at']
    search_fields = ['user__username', 'user__email', 'comment']
    readonly_fields = ['created_at']
    actions = ['mark_as_read', 'mark_as_unread']
    
    def short_comment(self, obj):
        return obj.comment[:50] + "..." if len(obj.comment) > 50 else obj.comment
    short_comment.short_description = "Comment"
    
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, f"{queryset.count()} reviews marked as read.")
    mark_as_read.short_description = "Mark selected as read"
    
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)
        self.message_user(request, f"{queryset.count()} reviews marked as unread.")
    mark_as_unread.short_description = "Mark selected as unread"