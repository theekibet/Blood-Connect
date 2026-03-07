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
# Fixed import - removed incorrect line

urlpatterns = [

    # ===================================
    # REAL ADMIN - SECRET URL (CHANGE THIS!)
    # ===================================
    path(f'{settings.ADMIN_SECRET_URL}/', admin.site.urls),

    # ===================================
    # HONEYPOT / FAKE ADMIN ROUTES
    # ===================================
    # Public button leads here - captures attacker information
    path('admin-login/', blood_views.fake_admin_login_view, name='fake_admin_login'),
    
    # Additional honeypot paths that bots commonly scan for
    path('wp-admin/', blood_views.fake_admin_login_view),        # WordPress honeypot
    path('administrator/', blood_views.fake_admin_login_view),   # Common admin path
    path('admin-area/', blood_views.fake_admin_login_view),      # Another common path
    path('backend/', blood_views.fake_admin_login_view),         # Backend honeypot
    path('cpanel/', blood_views.fake_admin_login_view),          # cPanel honeypot
    path('admin-panel/', blood_views.fake_admin_login_view),     # Admin panel honeypot
    path('admin-console/', blood_views.fake_admin_login_view),   # Admin console honeypot
    path('admin123/', blood_views.fake_admin_login_view),        # Common brute force path
    path('admin2024/', blood_views.fake_admin_login_view),       # Year-based path


    
    # ===================================
    # CENTRALIZED AUTHENTICATION FOR ALL USERS
    # ===================================
    path('logout/', LogoutView.as_view(template_name='blood/logout.html'), name='logout'),
    

    path('afterlogin/', blood_views.afterlogin_view, name='afterlogin'),

    # Password Change URLs
    path('password-change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('password-change/success/', TemplateView.as_view(template_name='shared/password_change_success.html'), name='password-change-success'),

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
    path('lab-tech/', include('lab_technologist.urls')),
    path('blood-bank/', include('blood_bank_technician.urls')),
    
    # ===================================
    # ADMIN PANEL ROUTES (Custom Admin Views)
    # ===================================
    path('admin-dashboard/', blood_views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-contacts/', blood_views.admin_contacts_view, name='admin_contacts'),
    path('admin-post-notification/', blood_views.admin_post_notification, name='admin-post-notification'),

    # ===================================
    # HONEYPOT MONITOR (Optional - for superusers only)
    # ===================================
    # Uncomment this after creating the honeypot monitor view
    path('honeypot-monitor/', blood_views.honeypot_monitor_view, name='honeypot_monitor'),

    # ===================================
    # AJAX ENDPOINTS
    # ===================================
    path('ajax/get-phlebotomists/', get_phlebotomists_by_center, name='ajax_get_phlebotomists'),

    # ===================================
    # NEARBY CENTERS
    # ===================================
    path('nearby-centers/', blood_views.nearby_centers_view, name='nearby-centers'),

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

    # Profile image update
    path('update-profile-image/', blood_views.update_profile_image, name='update_profile_image'),
    
        path('submit-review/', blood_views.submit_review, name='submit_review'),
    
    # Admin review management
    path('admin/reviews/', blood_views.admin_reviews_dashboard, name='admin_reviews_dashboard'),
    path('admin/reviews/<int:review_id>/feature/', blood_views.feature_review_as_testimonial, name='feature_review'),
    path('save-review-step/', blood_views.save_review_step, name='save_review_step'),

    path('testing-guide/', blood_views.testing_guide_view, name='testing_guide'),
    
    path('utils/', include('utils.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)