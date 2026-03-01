from django.apps import AppConfig

class PhlebotomistConfig(AppConfig):  # Changed from NurseConfig
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'phlebotomist'  
