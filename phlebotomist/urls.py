from django.urls import path
from . import views
from phlebotomist.views import phlebotomist_update_donation_appointment_status
from django.conf import settings
from django.conf.urls.static import static

app_name = 'phlebotomist'  

urlpatterns = [
    
    path('signup/', views.phlebotomist_signup_view, name='phlebotomist_signup'),  # Changed
    path('login/', views.phlebotomist_login_view, name='phlebotomistlogin'),  
    path('dashboard/', views.phlebotomist_dashboard, name='phlebotomist-dashboard'),  # Changed
    path('profile/<int:pk>/', views.phlebotomist_profile_view, name='phlebotomist-profile'),  # Changed
    path('notifications/', views.phlebotomist_notifications_view, name='phlebotomist-notifications'),  # Changed
    path('notifications/read/<int:pk>/', views.mark_phlebotomist_notification_read, name='mark-phlebotomist-notification-read'),  # Changed
    path(
        'appointment/<int:appointment_id>/update_status/',
        phlebotomist_update_donation_appointment_status,  # Already updated
        name='phlebotomist-update-donation-appointment-status',  # Changed
    ),
    path('profile/edit/<int:pk>/', views.phlebotomist_profile_edit_view, name='phlebotomist-profile-edit'),  # Changed
    path('donation-bookings/', views.phlebotomist_donation_bookings, name='phlebotomist-donation-bookings'),  # Changed
    path('ajax/booked-timeslots/', views.ajax_booked_timeslots, name='ajax_booked_timeslots'),  # This can stay
    path('pending-approval/', views.phlebotomist_pending_approval_view, name='phlebotomist-pending-approval'),  # Changed

    path('appointment/<int:appointment_id>/select-barcode/', 
     views.select_barcode_for_donation, name='select_barcode'),  # This can stay
    path('appointment/<int:appointment_id>/assign-barcode/<int:barcode_id>/', 
     views.assign_barcode_to_donor, name='assign_barcode'),  # This can stay
    path('appointment/<int:appointment_id>/collect/<int:barcode_id>/', 
     views.collect_with_barcode, name='collect_with_barcode'),  # This can stay
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
