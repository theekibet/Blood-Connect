from django.urls import path
from django.contrib.auth.views import LoginView, PasswordChangeView
from . import views
from patient import views as pviews
from django.conf import settings
from django.conf.urls.static import static
from blood.views import save_user_location
from nurse import views as nurse_views
from patient.views import center_stock_ajax

urlpatterns = [
    path('patientlogin', LoginView.as_view(template_name='patient/patientlogin.html'), name='patientlogin'),
    path('patientsignup', views.patient_signup_view, name='patientsignup'),
    path('patient-dashboard/', views.patient_dashboard_view, name='patient-dashboard'),
    path('make-request', views.make_request_view, name='make-request'),
    path('my-request', views.my_request_view, name='my-request'),
    path('patient-profile/<int:patient_id>/', views.patient_profile_view, name='patient-profile'),
    path('edit-profile/<int:patient_id>/', views.edit_patient_profile_view, name='patient-edit-profile'),
    path('notifications/', views.patient_notifications_view, name='patient-notifications'),
    path('mark-notification-read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('resources/', views.resources_view, name='patient-resources'),
    path('faqs/', views.faqs_view, name='patient-faqs'),
    path('donation-centers/', pviews.donation_centers_view, name='donation-centers'),
     path('save-location/', save_user_location, name='save-user-location'),
    path('change-password/', PasswordChangeView.as_view(template_name='patient/change_password.html'), name='patient-change-password'),
    path('ajax/get-nurses/', views.get_nurses_by_center, name='ajax_get_nurses'),
    path('nearby-eligible-donors/', views.nearby_eligible_donors_view, name='nearby-eligible-donors'),
    path('ajax/center-stock/<int:center_id>/', center_stock_ajax, name='center-stock-ajax'),
    path('cancel-request/<int:request_id>/', views.cancel_request_view, name='cancel-request'),
      path('blood-stock-tracker/', views.blood_stock_tracker_view, name='patient-blood-stock-tracker'),
       path(
        'ajax/booked-timeslots/',
        nurse_views.ajax_booked_timeslots,
        name='ajax_booked_timeslots'
        
    ),
    path('ajax/validate-username/', views.ajax_validate_username, name='ajax_validate_username'),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
