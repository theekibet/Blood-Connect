# management/commands/migrate_donation_history.py
from django.core.management.base import BaseCommand
from django.db import transaction
from nurse.models import Appointment
from blood.models import StockUnit

class Command(BaseCommand):
    help = 'Migrate existing donation history to track roles'
    
    @transaction.atomic
    def handle(self, *args, **options):
        # Update all completed appointments to show nurse did everything
        # (since that was the case historically)
        completed_appointments = Appointment.objects.filter(
            status='completed',
            completed_by_nurse__isnull=False
        )
        
        for apt in completed_appointments:
            apt.completed_by_role = 'nurse'
            apt.save()
        
        # Update stock units
        stock_units = StockUnit.objects.filter(safety_verified_by__isnull=False)
        for su in stock_units:
            su.added_to_inventory_by_role = 'nurse'
            su.save()
        
        self.stdout.write(self.style.SUCCESS(
            f'Migrated {completed_appointments.count()} appointments and '
            f'{stock_units.count()} stock units'
        ))