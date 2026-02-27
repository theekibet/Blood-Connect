from django.urls import path
from . import views

app_name = 'hospital'

urlpatterns = [
    # Authentication
    path('register/', views.hospital_register, name='register'),
    path('signup/', views.hospital_user_signup, name='signup'),
    path('login/', views.hospital_login_view, name='login'),
    path('logout/', views.hospital_logout_view, name='logout'),
    
    # Dashboards
    path('dashboard/', views.hospital_dashboard, name='dashboard'),
    path('dashboard/admin/', views.hospital_dashboard_admin, name='dashboard_admin'),
    
    # Blood requests
    path('requests/create/', views.create_blood_request, name='create_request'),
    path('requests/', views.request_list, name='request_list'),
    path('requests/<uuid:request_id>/', views.request_detail, name='request_detail'),
    path('requests/<uuid:request_id>/cancel/', views.cancel_request, name='cancel_request'),
    path('requests/<uuid:request_id>/confirm-delivery/', views.confirm_delivery, name='confirm_delivery'),
    
    # Profile management
    path('profile/', views.hospital_profile, name='profile'),
    
    # User management (admin only)
    path('users/', views.user_management, name='user_management'),
    path('users/<uuid:user_id>/deactivate/', views.deactivate_user, name='deactivate_user'),
]