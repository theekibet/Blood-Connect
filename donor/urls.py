from django.urls import path, include
from . import views
from blood.views import save_user_location
from phlebotomist import views as phlebotomist_views

app_name = 'donor'  # Add app_name for namespacing

urlpatterns = [
    # ==========================================
    # AUTHENTICATION
    # ==========================================
    path('donorlogin', views.donorlogin_view, name='donorlogin'),
    path('donorsignup', views.donor_signup_view, name='donorsignup'),
    path('choose-username/', views.choose_username_view, name='choose-username'),

    # ==========================================
    # DASHBOARD
    # ==========================================
    path('donor-dashboard', views.donor_dashboard_view, name='donor-dashboard'),

    # ==========================================
    # DONATION MANAGEMENT
    # ==========================================
    path('donate-blood/', views.donate_blood_view, name='donate-blood'),
    path('donation-history/', views.donation_history_view, name='donation-history'),
    path('cancel-donation/<int:donation_id>/', views.cancel_donation_request_view, name='cancel-donation'),
    path('ajax/get-available-times/', views.ajax_get_available_times, name='ajax_get_available_times'),  # <--- FIXED: Added views.
    
    # ==========================================
    # PROFILE MANAGEMENT
    # ==========================================
    path('profile/', views.donor_profile_view, name='donor-profile'),
    path('edit-profile/', views.donor_edit_profile_view, name='donor-edit-profile'),
    path('donor-eligibility/', views.donor_eligibility_view, name='donor-eligibility'),
    path('eligibility-status/', views.donor_eligibility_status_view, name='donor-eligibility-status'),
    path('save-location/', save_user_location, name='save-user-location'),

    # ==========================================
    # NOTIFICATIONS
    # ==========================================
    path('notifications/', views.donor_notifications_view, name='donor-notifications'),
    path('mark-notification-read/<int:pk>/', views.mark_notification_read, name='mark-notification-read'),

    # ==========================================
    # VOLUNTEER OPPORTUNITIES
    # ==========================================
    path('volunteer/', views.volunteer_opportunities_view, name='volunteer'),
    path('volunteer/advocate/', views.social_media_advocate_view, name='social-media-advocate'),
    path('volunteer/transport/', views.transport_volunteer_view, name='transport-volunteer'),

    # ==========================================
    # AWARENESS & EDUCATION
    # ==========================================
    path('awareness/', views.awareness_hub_view, name='awareness-hub'),
    path('awareness/campaigns/', views.awareness_campaigns_view, name='awareness-campaigns'),
    path('awareness/share/', views.share_awareness_view, name='share-awareness'),

    # ==========================================
    # EDUCATIONAL RESOURCES
    # ==========================================
    path('resources/', views.donor_resources_view, name='donor-resources'),
    path('resources/health-tips/', views.health_tips_view, name='health-tips'),
    path('resources/faqs/', views.faqs_view, name='faqs'),
    path('resources/donor-advice/', views.donor_advice_view, name='donor-advice'),

    # ==========================================
    # COMMUNITY & EVENTS
    # ==========================================
    path('events/', views.events_view, name='events'),
    path('events/<int:event_id>/', views.event_detail_view, name='event-detail'),

    # ==========================================
    # IMPACT TRACKING
    # ==========================================
    path('impact/', views.impact_view, name='impact'),
    path('impact/share/', views.share_impact_view, name='share-impact'),

    # ==========================================
    # AJAX ENDPOINTS
    # ==========================================
    path('ajax/booked-timeslots/', phlebotomist_views.ajax_booked_timeslots, name='ajax_booked_timeslots'),
]