# blood/admin.py
from django.contrib import admin
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
        'barcode'
    )
    ordering = ('-date',)
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