from django.urls import path
from .views import chatbot_api
from . import views
urlpatterns = [
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
   
]
