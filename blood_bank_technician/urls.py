from django.urls import path
from . import views

app_name = 'blood_bank_technician'

urlpatterns = [
    # Authentication
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),


    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Profile URLs
    path('profile/', views.blood_bank_tech_profile, name='blood_bank_tech_profile'),
    path('profile/<int:pk>/', views.blood_bank_tech_profile_detail, name='blood_bank_tech_profile_detail'),
    path('profile/<int:pk>/edit/', views.blood_bank_tech_profile_edit, name='blood_bank_tech_profile_edit'),
    
    # Inventory
    path('inventory/', views.inventory, name='inventory'),
    path('expiring/', views.expiring_blood, name='expiring_blood'),
    path('unsafe-blood/', views.unsafe_blood, name='unsafe_blood'),
    path('pending-verification/', views.pending_verification, name='pending_verification'),
    
    # Hospital Request management - UPDATED: removed request_type, using uuid
    path('requests/pending/', views.pending_requests, name='pending_requests'),
    path('requests/approved/', views.approved_requests, name='approved_requests'),
    path('requests/approve/<uuid:request_id>/', views.approve_request, name='approve_request'),
    path('requests/reject/<uuid:request_id>/', views.reject_request, name='reject_request'),
    path('requests/dispatch/<uuid:request_id>/', views.dispatch_request, name='dispatch_request'),
    path('requests/<uuid:request_id>/', views.request_detail, name='request_detail'),  # Added detail view
]