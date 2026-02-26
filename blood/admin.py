# blood/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    Stock, DonationCenter, StockUnit,
    BloodDriveEvent, Banner, Testimonial, HomePageStats,
    DonationFunFact, UserFactInteraction, DailyFactChallenge,
    QuizAttempt, FactContribution
)
from nurse.models import Appointment

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
        'id', 'barcode', 'date', 'nurse', 
        'get_donor', 'get_patient', 'status_colored',
        'current_phase_display', 'safety_status_badge',
        'created_at'
    )
    
    list_filter = (
        'status',
        'safety_status',
        'nurse',
        'donation_center',
        'date',
        'approved_by_role',
        'collected_by_role',
        'lab_tested_by_role',
        'completed_by_role',
        'created_at',
    )
    
    search_fields = (
        'barcode',
        'donor__user__username',
        'donor__user__first_name',
        'donor__user__last_name',
        'patient__user__username',
        'patient__user__first_name',
        'patient__user__last_name',
        'nurse__user__username',
        'nurse__user__first_name',
        'nurse__user__last_name',
        'status',
    )
    
    ordering = ('-date',)
    
    readonly_fields = (
        'barcode', 'created_at', 
        'status_changed_at', 'status_changed_by', 'status_changed_by_role',
        'approved_at', 'approved_by', 'approved_by_role',
        'collected_at', 'collected_by', 'collected_by_role',
        'sent_to_lab_at', 'lab_received_at',
        'lab_tested_at', 'lab_tested_by', 'lab_tested_by_role',
        'safety_verified_at', 'safety_verified_by', 'safety_verified_by_role',
        'completed_at', 'completed_by', 'completed_by_role',
        'rejected_at', 'rejected_by', 'rejected_by_role',
        'cancelled_at', 'cancelled_by_user', 'cancelled_by_role',
        'appointment_type_display', 'workflow_timeline'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'barcode', 'date', 'donation_center', 'nurse',
                ('donor', 'patient'), 'appointment_type_display'
            )
        }),
        ('Current Status', {
            'fields': (
                'status', 'safety_status', 'current_phase_display',
                'rejection_reason'
            )
        }),
        ('Approval Workflow', {
            'fields': (
                ('approved_by', 'approved_by_role', 'approved_at'),
            ),
            'classes': ('collapse',),
            'description': 'Appointment approval details'
        }),
        ('Collection Workflow', {
            'fields': (
                ('collected_by', 'collected_by_role', 'collected_at'),
                ('sent_to_lab_at', 'lab_received_at'),
            ),
            'classes': ('collapse',),
            'description': 'Blood collection and lab transfer details'
        }),
        ('Lab Testing Workflow', {
            'fields': (
                ('lab_tested_by', 'lab_tested_by_role', 'lab_tested_at'),
                ('safety_verified_by', 'safety_verified_by_role', 'safety_verified_at'),
            ),
            'classes': ('collapse',),
            'description': 'Laboratory testing and safety verification'
        }),
        ('Completion Workflow', {
            'fields': (
                ('completed_by', 'completed_by_role', 'completed_at'),
            ),
            'classes': ('collapse',),
            'description': 'Appointment completion details'
        }),
        ('Rejection/Cancellation', {
            'fields': (
                ('rejected_by', 'rejected_by_role', 'rejected_at'),
                ('cancelled_by', 'cancelled_by_user', 'cancelled_by_role', 'cancelled_at'),
            ),
            'classes': ('collapse',),
        }),
        ('System Fields', {
            'fields': (
                'created_at',
                ('status_changed_by', 'status_changed_by_role', 'status_changed_at'),
                'workflow_timeline'
            ),
            'classes': ('collapse',),
        }),
    )
    
    def get_donor(self, obj):
        """Get donor username with link to donor admin"""
        if obj.donor:
            return format_html(
                '<a href="/admin/donor/donor/{}/change/">{}</a>',
                obj.donor.id,
                obj.donor.user.get_full_name() or obj.donor.user.username
            )
        return "—"
    get_donor.short_description = "Donor"
    get_donor.admin_order_field = 'donor__user__username'

    def get_patient(self, obj):
        """Get patient username with link to patient admin"""
        if obj.patient:
            return format_html(
                '<a href="/admin/patient/patient/{}/change/">{}</a>',
                obj.patient.id,
                obj.patient.user.get_full_name() or obj.patient.user.username
            )
        return "—"
    get_patient.short_description = "Patient"
    get_patient.admin_order_field = 'patient__user__username'
    
    def status_colored(self, obj):
        """Display colored status badge"""
        colors = {
            'pending': '#ffc107',    # yellow
            'approved': '#17a2b8',   # teal
            'collected': '#6f42c1',  # purple
            'completed': '#28a745',  # green
            'rejected': '#dc3545',   # red
            'cancelled': '#6c757d',  # gray
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
    
    def safety_status_badge(self, obj):
        """Display safety status badge"""
        if obj.safety_status == 'safe':
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✅ Safe</span>'
            )
        elif obj.safety_status == 'unsafe':
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">⚠️ Unsafe</span>'
            )
        return format_html(
            '<span style="color: #ffc107; font-weight: bold;">⏳ Pending</span>'
        )
    safety_status_badge.short_description = 'Safety'
    safety_status_badge.admin_order_field = 'safety_status'
    
    def current_phase_display(self, obj):
        """Display current workflow phase with icon"""
        phases = {
            'pending_approval': ('⏳ Pending Approval', '#ffc107'),
            'awaiting_collection': ('👤 Awaiting Collection', '#17a2b8'),
            'awaiting_testing': ('🔬 Awaiting Testing', '#6f42c1'),
            'completed_safe': ('✅ Completed - Safe', '#28a745'),
            'completed_unsafe': ('⚠️ Completed - Unsafe', '#dc3545'),
            'terminated': ('❌ Terminated', '#6c757d'),
        }
        phase, color = phases.get(obj.current_phase, (obj.current_phase, '#000000'))
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            phase
        )
    current_phase_display.short_description = 'Current Phase'
    
    def appointment_type_display(self, obj):
        """Display appointment type with icon"""
        if obj.is_donation:
            return format_html('<span style="color: #28a745;">🩸 Blood Donation</span>')
        elif obj.is_blood_request:
            return format_html('<span style="color: #17a2b8;">📋 Blood Request</span>')
        return format_html('<span style="color: #6c757d;">❓ Unknown</span>')
    appointment_type_display.short_description = 'Appointment Type'
    
    def workflow_timeline(self, obj):
        """Display workflow timeline as HTML"""
        timeline_items = []
        
        # Created
        if obj.created_at:
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #6c757d;">📅 Created:</span>
                    <strong>{obj.created_at.strftime('%Y-%m-%d %H:%M')}</strong>
                </div>
            """)
        
        # Approved
        if obj.approved_at:
            by = obj.approved_by.get_full_name() if obj.approved_by else 'Unknown'
            role = obj.approved_by_role or 'nurse'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #17a2b8;">✅ Approved:</span>
                    <strong>{obj.approved_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} ({role})</small>
                </div>
            """)
        
        # Collected
        if obj.collected_at:
            by = obj.collected_by.get_full_name() if obj.collected_by else 'Unknown'
            role = obj.collected_by_role or 'nurse'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #6f42c1;">🩸 Collected:</span>
                    <strong>{obj.collected_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} ({role})</small>
                </div>
            """)
        
        # Lab Tested
        if obj.lab_tested_at:
            by = obj.lab_tested_by.get_full_name() if obj.lab_tested_by else 'Unknown'
            role = obj.lab_tested_by_role or 'lab_tech'
            result = obj.safety_status
            result_icon = '✅' if result == 'safe' else '⚠️' if result == 'unsafe' else '⏳'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #28a745;">🔬 Lab Tested:</span>
                    <strong>{obj.lab_tested_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} ({role}) - {result_icon} {result}</small>
                </div>
            """)
        
        # Completed
        if obj.completed_at:
            by = obj.completed_by.get_full_name() if obj.completed_by else 'Unknown'
            role = obj.completed_by_role or 'Unknown'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #28a745;">🎉 Completed:</span>
                    <strong>{obj.completed_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} ({role})</small>
                </div>
            """)
        
        # Rejected/Cancelled
        if obj.rejected_at:
            by = obj.rejected_by.get_full_name() if obj.rejected_by else 'Unknown'
            reason = obj.rejection_reason or 'No reason provided'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #dc3545;">❌ Rejected:</span>
                    <strong>{obj.rejected_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} - Reason: {reason}</small>
                </div>
            """)
        elif obj.cancelled_at:
            by = obj.cancelled_by_user.get_full_name() if obj.cancelled_by_user else 'Unknown'
            cancelled_by = obj.cancelled_by or 'Unknown'
            timeline_items.append(f"""
                <div style="margin-bottom: 5px;">
                    <span style="color: #6c757d;">❌ Cancelled:</span>
                    <strong>{obj.cancelled_at.strftime('%Y-%m-%d %H:%M')}</strong>
                    <br><small>by {by} ({cancelled_by})</small>
                </div>
            """)
        
        if timeline_items:
            return format_html('<div style="background: #f8f9fa; padding: 10px; border-radius: 4px;">{}</div>', ''.join(timeline_items))
        return "No timeline available"
    workflow_timeline.short_description = 'Workflow Timeline'
    
    actions = ['mark_as_pending', 'mark_as_approved', 'mark_as_collected', 'mark_as_completed']
    
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(status='pending')
        self.message_user(request, f"{updated} appointment(s) marked as pending.")
    mark_as_pending.short_description = "Mark selected as Pending"
    
    def mark_as_approved(self, request, queryset):
        now = timezone.now()
        for appointment in queryset:
            appointment.status = 'approved'
            appointment.approved_at = now
            appointment.approved_by = request.user
            appointment.approved_by_role = 'admin'
            appointment.save()
        self.message_user(request, f"{queryset.count()} appointment(s) marked as approved.")
    mark_as_approved.short_description = "Mark selected as Approved"
    
    def mark_as_collected(self, request, queryset):
        now = timezone.now()
        for appointment in queryset:
            appointment.status = 'collected'
            appointment.collected_at = now
            appointment.collected_by = request.user
            appointment.collected_by_role = 'admin'
            appointment.sent_to_lab_at = now
            appointment.save()
        self.message_user(request, f"{queryset.count()} appointment(s) marked as collected.")
    mark_as_collected.short_description = "Mark selected as Collected"
    
    def mark_as_completed(self, request, queryset):
        now = timezone.now()
        for appointment in queryset:
            appointment.status = 'completed'
            appointment.completed_at = now
            appointment.completed_by = request.user
            appointment.completed_by_role = 'admin'
            appointment.save()
        self.message_user(request, f"{queryset.count()} appointment(s) marked as completed.")
    mark_as_completed.short_description = "Mark selected as Completed"
# Blood Drive & Homepage Content
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


# Donation Fun Facts Section
@admin.register(DonationFunFact)
class DonationFunFactAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'has_quiz', 'likes', 'times_viewed', 'is_verified', 'created_at']
    list_filter = ['category', 'has_quiz', 'is_verified', 'created_at']
    search_fields = ['title', 'fact_text', 'quiz_question']
    list_editable = ['is_verified']
    ordering = ['-created_at']
    readonly_fields = ['likes', 'shares', 'times_viewed', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'title', 'fact_text', 'image_url', 'is_verified')
        }),
        ('Quiz Elements (Optional)', {
            'fields': ('has_quiz', 'quiz_question', 'correct_answer', 'wrong_answer_1', 'wrong_answer_2', 'explanation'),
            'classes': ('collapse',)
        }),
        ('Engagement Metrics', {
            'fields': ('likes', 'shares', 'times_viewed'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(UserFactInteraction)
class UserFactInteractionAdmin(admin.ModelAdmin):
    list_display = ['user_display', 'fact', 'interaction_type', 'timestamp', 'session_id']
    list_filter = ['interaction_type', 'timestamp']
    search_fields = ['user__username', 'fact__title', 'session_id']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def user_display(self, obj):
        return obj.user.username if obj.user else f"Anonymous ({obj.session_id[:8]}...)"
    user_display.short_description = "User"

@admin.register(DailyFactChallenge)
class DailyFactChallengeAdmin(admin.ModelAdmin):
    list_display = ['date', 'fact', 'total_participants', 'correct_answers', 'accuracy_percentage']
    list_filter = ['date']
    readonly_fields = ['total_participants', 'correct_answers']
    ordering = ['-date']
    
    def accuracy_percentage(self, obj):
        if obj.total_participants > 0:
            return f"{(obj.correct_answers / obj.total_participants * 100):.1f}%"
        return "0%"
    accuracy_percentage.short_description = "Accuracy"

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'score', 'correct_answers', 'total_questions', 'percentage', 'created_at']
    list_filter = ['created_at', 'score']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def percentage(self, obj):
        return f"{obj.score}%"
    percentage.short_description = "Score %"

@admin.register(FactContribution)
class FactContributionAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'category', 'is_approved', 'reviewed_by', 'created_at']
    list_filter = ['is_approved', 'category', 'created_at', 'reviewed_at']
    search_fields = ['title', 'fact_text', 'user__username']
    list_editable = ['is_approved']
    readonly_fields = ['created_at', 'reviewed_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Contribution Details', {
            'fields': ('user', 'category', 'title', 'fact_text', 'source')
        }),
        ('Quiz Elements (Optional)', {
            'fields': ('has_quiz', 'quiz_question', 'correct_answer', 'wrong_answer_1', 'wrong_answer_2'),
            'classes': ('collapse',)
        }),
        ('Moderation', {
            'fields': ('is_approved', 'reviewed_by', 'reviewed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_contributions', 'reject_contributions']
    
    def approve_contributions(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            is_approved=True,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} contribution(s) approved successfully.")
    approve_contributions.short_description = "Approve selected contributions"
    
    def reject_contributions(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            is_approved=False,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} contribution(s) rejected.")
    reject_contributions.short_description = "Reject selected contributions"
# blood/admin.py - Add this

from .models import BloodBagBarcode

@admin.register(BloodBagBarcode)
class BloodBagBarcodeAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'bag_type', 'volume_ml', 'status', 
                    'assigned_to_donor', 'assigned_at', 'collected_at']
    list_filter = ['status', 'bag_type', 'anticoagulant']
    search_fields = ['barcode', 'assigned_to_donor__user__username']
    readonly_fields = ['barcode', 'created_at']
    
    fieldsets = (
        ('Barcode Information', {
            'fields': ('barcode', 'bag_type', 'volume_ml', 'anticoagulant')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Assignment', {
            'fields': ('assigned_to_donor', 'assigned_by', 'assigned_at'),
            'classes': ('collapse',)
        }),
        ('Collection', {
            'fields': ('collected_by', 'collected_at', 'blood_donation'),
            'classes': ('collapse',)
        }),
        ('Manufacturing', {
            'fields': ('manufacturer', 'lot_number', 'manufacture_date', 'expiry_date'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['generate_barcodes']
    
    def generate_barcodes(self, request, queryset):
        """Custom action to generate barcodes"""
        from blood.utils.barcode_utils import generate_batch_barcodes
        
        count = 10  # Default to generate 10
        barcodes = generate_batch_barcodes(count=count, created_by=request.user)
        self.message_user(
            request, 
            f"✅ Generated {len(barcodes)} new barcodes: " + 
            ", ".join([b.barcode for b in barcodes[:5]]) + 
            ("..." if len(barcodes) > 5 else "")
        )
    generate_barcodes.short_description = "Generate 10 new barcodes"