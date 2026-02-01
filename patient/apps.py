from django.apps import AppConfig

class PatientConfig(AppConfig):
    name = 'patient'

    def ready(self):
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.fields import GenericRelation
        from blood.models import Notification

        User.add_to_class(
            'notifications',
            GenericRelation(
                Notification,
                content_type_field='recipient_content_type',
                object_id_field='recipient_object_id'
            )
        )
