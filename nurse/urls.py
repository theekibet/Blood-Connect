from django.urls import path
from . import views
from nurse.views import nurse_update_donation_appointment_status, nurse_update_bloodrequest_appointment_status
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('signup/', views.nurse_signup_view, name='nurse_signup'),
    path('nurselogin/', views.nurselogin_view, name='nurselogin'),
    path('dashboard/', views.nurse_dashboard, name='nurse-dashboard'),
    path('blood-requests/bookings/', views.blood_request_bookings, name='nurse-blood-request-bookings'),
    path('blood-requests/list/', views.list_blood_requests, name='blood-requests-list'),
    path('profile/<int:pk>/', views.nurse_profile_view, name='nurse-profile'),
    path('notifications/', views.nurse_notifications_view, name='nurse-notifications'),
    path('notifications/read/<int:pk>/', views.mark_nurse_notification_read, name='mark-nurse-notification-read'),
    path(
        'appointment/<int:appointment_id>/update_status/',
        nurse_update_donation_appointment_status,
        name='nurse-update-donation-appointment-status',
    ),
    path(
        'appointment/<int:appointment_id>/update_bloodrequest_status/',
        nurse_update_bloodrequest_appointment_status,
        name='nurse-update-bloodrequest-appointment-status',
    ),
    path('profile/edit/<int:pk>/', views.nurse_profile_edit_view, name='nurse-profile-edit'),
    path('donation-bookings/', views.nurse_donation_bookings, name='nurse-donation-bookings'),
    path('blood-stock/', views.nurse_blood_stock, name='nurse-blood-stock'),
    path('request-blood/', views.create_blood_request, name='create-blood-request'),
    path('ajax/booked-timeslots/', views.ajax_booked_timeslots, name='ajax_booked_timeslots'),
    path("stockunits/", views.nurse_stockunit_list, name="nurse_stockunit_list"), 
    path('blood-stock/deductions/<int:appointment_id>/', 
     views.nurse_stock_deductions, name='nurse-stock-deductions'),
    #For debugs
path('debug-donations/', views.debug_donation_bookings, name='debug_donation_bookings'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
