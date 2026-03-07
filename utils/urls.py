from django.urls import path
from . import views

app_name = 'utils'

urlpatterns = [
    # Universal notification URLs (these will work for all user types)
    path('notifications/', views.universal_notifications_list, name='notifications'),
    path('notifications/<int:notification_id>/read/', views.universal_mark_read, name='mark_read'),
    path('notifications/mark-all-read/', views.universal_mark_all_read, name='mark_all_read'),
    path('notifications/<int:notification_id>/delete/', views.universal_delete_notification, name='delete_notification'),
    path('notifications/unread-count/', views.universal_unread_count, name='unread_count'),
    
    # Fallback URLs for apps that don't have notification views
    path('fallback/notifications/', views.fallback_notifications, name='fallback_notifications'),
    path('fallback/mark-read/<int:pk>/', views.fallback_mark_read, name='fallback_mark_read'),
    path('fallback/mark-all-read/', views.fallback_mark_all_read, name='fallback_mark_all_read'),
]