from django.urls import path
from . import views
from phlebotomist.views import phlebotomist_update_donation_appointment_status, phlebotomist_appointment_details
from django.conf import settings
from django.conf.urls.static import static

app_name = 'phlebotomist'  

urlpatterns = [
    
    path('signup/', views.phlebotomist_signup_view, name='phlebotomist_signup'),
    path('login/', views.phlebotomist_login_view, name='phlebotomistlogin'),  
    path('dashboard/', views.phlebotomist_dashboard, name='phlebotomist-dashboard'),
    path('profile/<int:pk>/', views.phlebotomist_profile_view, name='phlebotomist-profile'),

    
    # Fixed: update-status/ with hyphen (matches your JavaScript)
    path(
        'appointment/<int:appointment_id>/update-status/',
        phlebotomist_update_donation_appointment_status,
        name='phlebotomist-update-donation-appointment-status',
    ),
    
    # Fixed: Import name should match the function name (with 's' at the end)
    path(
        'appointment/<int:appointment_id>/details/',
        phlebotomist_appointment_details,  # Changed from phlebotomist_appointment_detail to phlebotomist_appointment_details
        name='phlebotomist-appointment-details',
    ),
    
    path('profile/edit/<int:pk>/', views.phlebotomist_profile_edit_view, name='phlebotomist-profile-edit'),
    path('donation-bookings/', views.phlebotomist_donation_bookings, name='phlebotomist-donation-bookings'),
    path('ajax/booked-timeslots/', views.ajax_booked_timeslots, name='ajax_booked_timeslots'),
    path('pending-approval/', views.phlebotomist_pending_approval_view, name='phlebotomist-pending-approval'),

    path('appointment/<int:appointment_id>/select-barcode/', 
         views.select_barcode_for_donation, name='select_barcode'),
    path('appointment/<int:appointment_id>/assign-barcode/<int:barcode_id>/', 
         views.assign_barcode_to_donor, name='assign_barcode'),
    path('appointment/<int:appointment_id>/collect/<int:barcode_id>/', 
         views.collect_with_barcode, name='collect_with_barcode'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)