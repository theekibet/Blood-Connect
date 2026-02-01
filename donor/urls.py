from django.urls import path, include
from . import views
from patient import views as patient_views
from blood.views import save_user_location
from nurse import views as nurse_views

urlpatterns = [
    # Auth
    path('donorlogin', views.donorlogin_view, name='donorlogin'),
    path('donorsignup', views.donor_signup_view, name='donorsignup'),

    # Dashboard
    path('donor-dashboard', views.donor_dashboard_view, name='donor-dashboard'),

    # Donations
    path('donate-blood/', views.donate_blood_view, name='donate-blood'),
    path('donation-history/', views.donation_history_view, name='donation-history'),
    path('cancel-donation/<int:donation_id>/', views.cancel_donation_request_view, name='cancel-donation'),

    # Requests
    path("make-request/", views.donor_make_request_view, name="donor-make-request"),
    path('cancel-request/<int:request_id>/', views.cancel_donor_request_view, name='cancel-donor-request'),
    
    
    # Profile
    path('profile/', views.donor_profile_view, name='donor-profile'),
    path('edit-profile/', views.donor_edit_profile_view, name='donor-edit-profile'),
    path('donor-eligibility/', views.donor_eligibility_view, name='donor-eligibility'),
    path('eligibility-status/', views.donor_eligibility_status_view, name='donor-eligibility-status'),
    path('save-location/', save_user_location, name='save-user-location'),

    # Notifications
    path('notifications/', views.donor_notifications_view, name='donor-notifications'),
    path('mark-notification-read/<int:pk>/', views.mark_notification_read, name='mark-notification-read'),

    # Nearby Patients
    path('nearby-compatible-patients/', views.nearby_compatible_patients_view, name='nearby-compatible-patients'),

    # Static / Info Pages
    path('health-tips/', views.health_tips, name='health-tips'),
    path('faqs/', views.faqs, name='faqs'),
    path('donor-advice/', views.donor_advice, name='donor-advice'),
    path('resources/', views.donor_resources, name='donor-resources'),

    # AJAX
    path('ajax/get-nurses/', patient_views.get_nurses_by_center, name='ajax_get_nurses'),
    path('ajax/booked-timeslots/', nurse_views.ajax_booked_timeslots, name='ajax_booked_timeslots'),

    # Django auth (password reset, change, etc.)
    
    path("request-history/", views.donor_request_history_view, name="donor-request-history"),
    


]
