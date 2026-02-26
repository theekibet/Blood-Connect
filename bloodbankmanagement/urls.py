from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import (
    LogoutView, 
    PasswordResetView, 
    PasswordResetDoneView,
    PasswordResetConfirmView, 
    PasswordResetCompleteView
)
from django.conf import settings
from django.conf.urls.static import static

from blood import views as blood_views  
from patient.views import get_nurses_by_center
from nurse import views as nurse_views
from blood import views  
from django.views.generic import TemplateView
from blood.views import CustomPasswordChangeView  
urlpatterns = [
    # ===================================
    # CUSTOM ADMIN APPROVAL VIEWS (MUST COME BEFORE Django admin!)
    # ===================================
    path('admin-nurse-management/', views.admin_nurse_view, name='admin-nurse-view'), 
    path('admin-nurse-management/', views.admin_nurse_view, name='admin-nurse'), 
    path('admin-nurse-management/<int:pk>/approve/', blood_views.admin_approve_nurse_view, name='admin-approve-nurse'),
    path('admin-nurse-management/<int:pk>/reject/', blood_views.admin_reject_nurse_view, name='admin-reject-nurse'),
    path('admin-nurse-management/<int:pk>/revoke/', blood_views.admin_revoke_nurse_view, name='admin-revoke-nurse'),
    path('admin-nurse-management/<int:pk>/update/', views.update_nurse_view, name='admin-nurse-update'),
    path('admin-nurse-management/<int:pk>/delete/', views.delete_nurse_view, name='admin-nurse-delete'),
    
    # ===================================
    # DJANGO DEFAULT ADMIN (Keep for model management)
    # ===================================
    path('admin/', admin.site.urls),

    # ===================================
    # CENTRALIZED AUTHENTICATION FOR ALL USERS
    # ===================================
    path('logout/', LogoutView.as_view(template_name='blood/logout.html'), name='logout'),
    


    
    # Legacy admin login (keep for backward compatibility)
    path('adminlogin/', blood_views.adminlogin_view, name='adminlogin'),
    path('afterlogin/', blood_views.afterlogin_view, name='afterlogin'),



    # ===================================
    # PASSWORD RESET (For ALL users)
    # ===================================
    path('password-reset/', 
         PasswordResetView.as_view(
             template_name='shared/password_reset_form.html',
             email_template_name='shared/password_reset_email.html',
             subject_template_name='shared/emails/password_reset_subject.txt',
             success_url='/password-reset/done/',
             html_email_template_name='shared/password_reset_email.html'
         ), 
         name='password_reset'),
    
    path('password-reset/done/', 
         PasswordResetDoneView.as_view(
             template_name='shared/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         PasswordResetConfirmView.as_view(
             template_name='shared/password_reset_confirm.html',
             success_url='/password-reset-complete/'
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/', 
         PasswordResetCompleteView.as_view(
             template_name='shared/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
    
    
    #########RESET EXISTING PASS
        path('password-change/', 
         CustomPasswordChangeView.as_view(), 
         name='password_change'),
    
    # Also add the success URL
    path('password-change/success/', 
         TemplateView.as_view(template_name='shared/password_change_success.html'), 
         name='password-change-success'),

    # ===================================
    # PUBLIC SITE ROUTES
    # ===================================
    path('', blood_views.home_view, name='home'),
    path('learn-more/', blood_views.learn_more_view, name='learn_more'),
    path('about-us/', blood_views.about_us_view, name='about-us'),
    path('contact/', blood_views.contact_view, name='contact'),
    path('contact/success/', blood_views.contact_success, name='contact_success'),
    path('sickle-cell/', blood_views.sickle_cell_view, name='sickle_cell'),

    # ===================================
    # APP-SPECIFIC URLS
    # ===================================
    path('donor/', include('donor.urls')),
    path('patient/', include('patient.urls')),
    path('nurse/', include('nurse.urls')),
    path('chatbot/', include('chatbot.urls')),

    # ===================================
    # ADMIN PANEL ROUTES
    # ===================================
    path('admin-dashboard/', blood_views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-blood/', blood_views.admin_blood_view, name='admin-blood'),
    path('admin-donor/', blood_views.admin_donor_view, name='admin-donor'),
    path('admin-patient/', blood_views.admin_patient_view, name='admin-patient'),
    path('admin-request/', blood_views.admin_request_view, name='admin-request'),
    path('admin-donation/', blood_views.admin_donation_view, name='admin-donation'),
    path('admin-contacts/', blood_views.admin_contacts_view, name='admin_contacts'),
    path('admin-post-notification/', blood_views.admin_post_notification, name='admin-post-notification'),


    # ===================================
    # AJAX ENDPOINTS
    # ===================================
    path('ajax/get-nurses/', get_nurses_by_center, name='ajax_get_nurses'),

    # ===================================
    # NEARBY CENTERS
    # ===================================
    path('nearby-centers/', blood_views.nearby_centers_view, name='nearby-centers'),

    # ===================================
    # CRUD OPERATIONS (Donor & Patient)
    # ===================================
    path('update-donor/<int:pk>/', blood_views.update_donor_view, name='update-donor'),
    path('delete-donor/<int:pk>/', blood_views.delete_donor_view, name='delete-donor'),
    path('update-patient/<int:pk>/', blood_views.update_patient_view, name='update-patient'),
    path('delete-patient/<int:pk>/', blood_views.delete_patient_view, name='delete-patient'),

    # ===================================
    # OTHER FUNCTIONALITY
    # ===================================
    path("save-user-location/", blood_views.save_user_location, name="save-user-location"),
    path('bloodrequest/<int:blood_request_id>/stock-transactions/', views.blood_request_stock_transactions, name='blood_request_stock_transactions'),
    path('admin-donations/report/', views.admin_donation_report, name='admin-donation-report'),
    path("bloodrequests/export/", views.export_bloodrequests_csv, name="export-bloodrequests-csv"),
    
    # ===================================
    # GLOBAL AJAX VALIDATORS (System-wide)
    # ===================================
    path('ajax/check-username/', blood_views.check_username_ajax, name='check_username_ajax'),
    path('ajax/check-email/', blood_views.check_email_ajax, name='check_email_ajax'),
    path('ajax/check-national-id/', blood_views.check_national_id_ajax, name='check_national_id_ajax'),
    path('ajax/check-mobile/', blood_views.check_mobile_ajax, name='check_mobile_ajax'),
    path('ajax/validate-username/', blood_views.validate_username_ajax, name='ajax_validate_username'),
    path('ajax/check-nurse-registration/', blood_views.ajax_check_nurse_registration, name='ajax_check_nurse_registration'),
    path('ajax/check-nurse-phone/', blood_views.ajax_check_nurse_phone, name='ajax_check_nurse_phone'),
    
    # Blood drives
path('blood-drives/', views.blood_drives_list, name='blood-drives-list'),
path('blood-drive/<int:pk>/', views.blood_drive_detail, name='blood-drive-detail'),

# Donation Facts Section
path('did-you-know/', views.did_you_know_home, name='did_you_know_home'),
path('facts/category/<str:category>/', views.fact_category, name='fact_category'),  # Changed
path('facts/detail/<int:fact_id>/', views.fact_detail, name='fact_detail'),  # Added
path('facts/search/', views.search_facts, name='search_facts'),  # Added
path('interactive-quiz/', views.interactive_quiz, name='interactive_quiz'),
path('quiz/submit/', views.submit_quiz, name='submit_quiz'),  # Added

# User progress
path('my-progress/', views.user_progress, name='user_progress'),  # Added

# AJAX endpoints
path('api/random-fact/', views.random_fact_api, name='random_fact_api'),
path('api/check-quiz/', views.check_quiz_answer, name='check_quiz_answer'),
path('api/like-fact/', views.like_fact, name='like_fact'),
path('api/challenge-stats/', views.daily_challenge_progress, name='daily_challenge_progress'),

    path('lab-tech/', include('lab_technologist.urls')),
    path('blood-bank/', include('blood_bank_technician.urls')),
]

# Media files serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)