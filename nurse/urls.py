from django.urls import path
from . import views
from nurse.views import nurse_update_donation_appointment_status
from django.conf import settings
from django.conf.urls.static import static
app_name = 'nurse'
urlpatterns = [
    
    path('signup/', views.nurse_signup_view, name='nurse_signup'),
    path('nurselogin/', views.nurselogin_view, name='nurselogin'),
    path('dashboard/', views.nurse_dashboard, name='nurse-dashboard'),
    path('profile/<int:pk>/', views.nurse_profile_view, name='nurse-profile'),
    path('notifications/', views.nurse_notifications_view, name='nurse-notifications'),
    path('notifications/read/<int:pk>/', views.mark_nurse_notification_read, name='mark-nurse-notification-read'),
    path(
        'appointment/<int:appointment_id>/update_status/',
        nurse_update_donation_appointment_status,
        name='nurse-update-donation-appointment-status',
    ),
    path('profile/edit/<int:pk>/', views.nurse_profile_edit_view, name='nurse-profile-edit'),
    path('donation-bookings/', views.nurse_donation_bookings, name='nurse-donation-bookings'),
    path('ajax/booked-timeslots/', views.ajax_booked_timeslots, name='ajax_booked_timeslots'),
    path('pending-approval/', views.nurse_pending_approval_view, name='nurse-pending-approval'),

    path('appointment/<int:appointment_id>/select-barcode/', 
     views.select_barcode_for_donation, name='select_barcode'),
path('appointment/<int:appointment_id>/assign-barcode/<int:barcode_id>/', 
     views.assign_barcode_to_donor, name='assign_barcode'),
path('appointment/<int:appointment_id>/collect/<int:barcode_id>/', 
     views.collect_with_barcode, name='collect_with_barcode'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
