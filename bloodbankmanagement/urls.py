from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView, LoginView
from django.conf import settings
from django.conf.urls.static import static


from blood import views as blood_views  
from patient.views import get_nurses_by_center



from blood import views  


urlpatterns = [
    
    

    # --- DJANGO DEFAULT ADMIN URLS --- #
    path('admin/', admin.site.urls),

    # Authentication
    path('logout/', LogoutView.as_view(template_name='blood/logout.html'), name='logout'),
    path('adminlogin/', LoginView.as_view(template_name='blood/adminlogin.html'), name='adminlogin'),
    path('afterlogin/', blood_views.afterlogin_view, name='afterlogin'),

    # Public site routes
    path('', blood_views.home_view, name='home'),
    path('learn-more/', blood_views.learn_more_view, name='learn_more'),
    path('about-us/', blood_views.about_us_view, name='about-us'),
    path('contact/', blood_views.contact_view, name='contact'),
    path('contact/success/', blood_views.contact_success, name='contact_success'),
    path('sickle-cell/', blood_views.sickle_cell_view, name='sickle_cell'),

    # Include app-specific urls
    path('donor/', include('donor.urls')),
    path('patient/', include('patient.urls')),
    path('nurse/', include('nurse.urls')),  # Ensure nurse URLs handle nurse update & CRUD views
    path('', include('chatbot.urls')),

    # Admin panel specific routes for blood app
    path('admin-dashboard/', blood_views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-blood/', blood_views.admin_blood_view, name='admin-blood'),
    path('admin-donor/', blood_views.admin_donor_view, name='admin-donor'),
    path('admin-patient/', blood_views.admin_patient_view, name='admin-patient'),
    path('admin-request/', blood_views.admin_request_view, name='admin-request'),
    path('admin-donation/', blood_views.admin_donation_view, name='admin-donation'),

    path('admin-contacts/', blood_views.admin_contacts_view, name='admin_contacts'),
    path('admin-post-notification/', blood_views.admin_post_notification, name='admin-post-notification'),
    
    # Admin nurse management
    path('admin-nurse/', views.admin_nurse_view, name='admin-nurse'),
    path('admin-nurse/update/<int:pk>/', views.update_nurse_view, name='admin-nurse-update'),
    path('admin-nurse/delete/<int:pk>/', views.delete_nurse_view, name='admin-nurse-delete'),

    path('admin-nurse-blood-requests/', blood_views.admin_nurse_blood_requests_view, name='admin-nurse-blood-requests'),

    

    # AJAX endpoints
    path('ajax/get-nurses/', get_nurses_by_center, name='ajax_get_nurses'),

    # Nearby donation centers
    path('nearby-centers/', blood_views.nearby_centers_view, name='nearby-centers'),
    

    # CRUD operations for donor and patient
    path('update-donor/<int:pk>/', blood_views.update_donor_view, name='update-donor'),
    path('delete-donor/<int:pk>/', blood_views.delete_donor_view, name='delete-donor'),
    path('update-patient/<int:pk>/', blood_views.update_patient_view, name='update-patient'),
    path('delete-patient/<int:pk>/', blood_views.delete_patient_view, name='delete-patient'),
    path("save-user-location/", blood_views.save_user_location, name="save-user-location"),
     path('bloodrequest/<int:blood_request_id>/stock-transactions/', views.blood_request_stock_transactions, name='blood_request_stock_transactions'),
     path('admin-donations/report/', views.admin_donation_report, name='admin-donation-report'),
    path("bloodrequests/export/", views.export_bloodrequests_csv, name="export-bloodrequests-csv"),

]

# Media files serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
