from django.urls import path
from . import views

app_name = 'lab_technologist'

urlpatterns = [
    # Authentication
     path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('profile/', views.lab_tech_profile, name='lab_tech_profile'),
    path('profile/<int:pk>/', views.lab_tech_profile_detail, name='lab_tech_profile_detail'),
    path('profile/<int:pk>/edit/', views.lab_tech_profile_edit, name='lab_tech_profile_edit'),

    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Testing
    path('pending/', views.pending_tests, name='pending_tests'),
    path('perform/<int:collection_id>/', views.perform_test, name='perform_test'),
    path('result/<int:test_id>/', views.test_result, name='test_result'),
    path('mark-safe/<int:test_id>/', views.mark_safe, name='mark_safe'),
    path('mark-unsafe/<int:test_id>/', views.mark_unsafe, name='mark_unsafe'),
    path('history/', views.test_history, name='test_history'),
]