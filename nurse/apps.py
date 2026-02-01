from django.apps import AppConfig

class NurseConfig(AppConfig):
    name = 'nurse'

    def ready(self):
        import nurse.signals
