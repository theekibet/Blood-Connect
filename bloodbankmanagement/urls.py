from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from phlebotomist.views import get_phlebotomists_by_center
from django.views.generic.base import RedirectView
from blood import views as blood_views  
from phlebotomist import views as phlebotomist_views
from django.views.generic import TemplateView
from blood.views import CustomPasswordChangeView  

urlpatterns = [
    # ===================================
    # CUSTOM ADMIN APPROVAL VIEWS (MUST COME BEFORE Django admin!)
    # ===================================
    # Phlebotomist Management URLs - CONSISTENT NAMING
    path('admin-phlebotomist-management/', 
         blood_views.admin_phlebotomist_view,  # Fixed: changed views to blood_views
         name='admin-phlebotomist-view'),
    
    # UNIFIED ACTION VIEW - Replaces approve/reject/revoke
    path('admin-phlebotomist-management/<int:pk>/<str:action>/', 
         blood_views.admin_phlebotomist_action_view, 
         name='admin-phlebotomist-action'),
    
    # Update and Delete views (keep these separate as they're more complex)
    path('admin-phlebotomist-management/<int:pk>/update/', 
         blood_views.update_phlebotomist_view,  # Fixed: changed views to blood_views
         name='admin-phlebotomist-update'),
    
    path('admin-phlebotomist-management/<int:pk>/delete/', 
         blood_views.delete_phlebotomist_view,  # Fixed: changed views to blood_views
         name='admin-phlebotomist-delete'),
    
    # ===================================
    # DJANGO DEFAULT ADMIN
    # ===================================
    path('admin/', admin.site.urls),

    # ===================================
    # CENTRALIZED AUTHENTICATION FOR ALL USERS
    # ===================================
    path('logout/', LogoutView.as_view(template_name='blood/logout.html'), name='logout'),
    
    # Legacy admin login (keep for backward compatibility)
    path('adminlogin/', blood_views.adminlogin_view, name='adminlogin'),
    path('afterlogin/', blood_views.afterlogin_view, name='afterlogin'),

    # Password Change URLs
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
    path('about/', RedirectView.as_view(url='/about-us/', permanent=True)),
    path('about-us/', blood_views.about_us_view, name='about-us'),
    path('contact/', blood_views.contact_view, name='contact'),
    path('contact/success/', blood_views.contact_success, name='contact_success'),


    # ===================================
    # APP-SPECIFIC URLS
    # ===================================
    path('donor/', include('donor.urls')),
    path('phlebotomist/', include('phlebotomist.urls')),  
    path('chatbot/', include('chatbot.urls')),
    path('hospital/', include('hospital.urls')),
    
    # ===================================
    # ADMIN PANEL ROUTES
    # ===================================
    path('admin-dashboard/', blood_views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-blood/', blood_views.admin_blood_view, name='admin-blood'),
    path('admin-donor/', blood_views.admin_donor_view, name='admin-donor'),
    path('admin-request/', blood_views.admin_request_view, name='admin-request'),
    path('admin-donation/', blood_views.admin_donation_view, name='admin-donation'),
    path('admin-contacts/', blood_views.admin_contacts_view, name='admin_contacts'),
    path('admin-post-notification/', blood_views.admin_post_notification, name='admin-post-notification'),

    # ===================================
    # AJAX ENDPOINTS
    # ===================================
    path('ajax/get-phlebotomists/', get_phlebotomists_by_center, name='ajax_get_phlebotomists'),

    # ===================================
    # NEARBY CENTERS
    # ===================================
    path('nearby-centers/', blood_views.nearby_centers_view, name='nearby-centers'),

    # ===================================
    # CRUD OPERATIONS (Donor & Patient)
    # ===================================
    path('update-donor/<int:pk>/', blood_views.update_donor_view, name='update-donor'),
    path('delete-donor/<int:pk>/', blood_views.delete_donor_view, name='delete-donor'),
 
    # ===================================
    # OTHER FUNCTIONALITY
    # ===================================
    path("save-user-location/", blood_views.save_user_location, name="save-user-location"),
    path('admin-donations/report/', blood_views.admin_donation_report, name='admin-donation-report'),
    
    # ===================================
    # GLOBAL AJAX VALIDATORS (System-wide)
    # ===================================
    path('ajax/check-username/', blood_views.check_username_ajax, name='check_username_ajax'),
    path('ajax/check-email/', blood_views.check_email_ajax, name='check_email_ajax'),
    path('ajax/check-national-id/', blood_views.check_national_id_ajax, name='check_national_id_ajax'),
    path('ajax/check-mobile/', blood_views.check_mobile_ajax, name='check_mobile_ajax'),
    path('ajax/validate-username/', blood_views.validate_username_ajax, name='ajax_validate_username'),
    path('ajax/check-phlebotomist-registration/', blood_views.ajax_check_phlebotomist_registration, name='ajax_check_phlebotomist_registration'),
    path('ajax/check-phlebotomist-phone/', blood_views.ajax_check_phlebotomist_phone, name='ajax_check_phlebotomist_phone'),
    
    # Blood drives
    path('blood-drives/', blood_views.blood_drives_list, name='blood-drives-list'),
    path('blood-drive/<int:pk>/', blood_views.blood_drive_detail, name='blood-drive-detail'),

    # Other app includes
    path('lab-tech/', include('lab_technologist.urls')),
    path('blood-bank/', include('blood_bank_technician.urls')),
    path('update-profile-image/', blood_views.update_profile_image, name='update_profile_image'),
]

# Media files serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)