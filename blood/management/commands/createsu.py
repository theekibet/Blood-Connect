from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

class Command(BaseCommand):
    help = 'Creates a superuser if one does not exist'

    def handle(self, *args, **options):
        User = get_user_model()
        
        # Get credentials from environment variables
        username = os.getenv('ADMIN_USERNAME', 'admin')
        email = os.getenv('ADMIN_EMAIL', 'admin@bloodconnect.com')
        password = os.getenv('ADMIN_PASSWORD')
        
        # Check if password is set
        if not password:
            self.stdout.write(
                self.style.WARNING('ADMIN_PASSWORD not set. Skipping superuser creation.')
            )
            return
        
        # Create superuser if it doesn't exist
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, email, password)
            self.stdout.write(
                self.style.SUCCESS(f'Superuser "{username}" created successfully!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Superuser "{username}" already exists.')
            )
