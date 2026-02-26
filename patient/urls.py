from django.urls import path
from django.contrib.auth.views import LoginView, PasswordChangeDoneView
from django.conf import settings
from django.conf.urls.static import static
from . import views
from blood.views import CustomPasswordChangeView  
from blood.views import save_user_location  # Shared location service
from nurse import views as nurse_views  # For nurse-related AJAX calls
from patient.views import center_stock_ajax  # AJAX endpoint

urlpatterns = [
    # Authentication & Registration
    path('patientlogin/', LoginView.as_view(template_name='patient/patientlogin.html'), name='patientlogin'),
    path('patientsignup/', views.patient_signup_view, name='patientsignup'),
    
    # Dashboard & Profile
    path('patient-dashboard/', views.patient_dashboard_view, name='patient-dashboard'),
    path('patient-profile/<int:patient_id>/', views.patient_profile_view, name='patient-profile'),
    path('edit-profile/<int:patient_id>/', views.edit_patient_profile_view, name='patient-edit-profile'),
    
    # Password Management
    path('change-password/', CustomPasswordChangeView.as_view(), name='patient-change-password'),
    path('change-password/success/', PasswordChangeDoneView.as_view(
        template_name='shared/password_change_success.html'
    ), name='patient-password-change-success'),
    
    # Blood Requests & Management
    path('patient-make-request/', views.patient_make_request_view, name='patient-make-request'),
    path('patient-requests-history/', views.patient_requests_history_view, name='patient-requests-history'),
    path('cancel-request/<int:request_id>/', views.cancel_request_view, name='cancel-request'),
    
    # Location Services
    path('save-location/', save_user_location, name='save-user-location'),
    
 

    
    # Resources & Information
    path('resources/', views.resources_view, name='patient-resources'),
    path('faqs/', views.faqs_view, name='patient-faqs'),
    
    # Notifications
    path('notifications/', views.patient_notifications_view, name='patient-notifications'),
    path('mark-notification-read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    
    # AJAX Endpoints
    path('ajax/get-nurses/', views.get_nurses_by_center, name='ajax_get_nurses'),
    path('ajax/center-stock/<int:center_id>/', center_stock_ajax, name='center-stock-ajax'),
    path('ajax/booked-timeslots/', nurse_views.ajax_booked_timeslots, name='ajax_booked_timeslots'),
    path('ajax/validate-username/', views.ajax_validate_username, name='ajax_validate_username'),
    
    

]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)