# management/commands/generate_barcodes.py

from django.core.management.base import BaseCommand
from blood.utils.barcode_utils import generate_batch_barcodes

class Command(BaseCommand):
    help = 'Generate pre-printed barcodes for blood bags'
    
    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='Number of barcodes to generate')
        parser.add_argument('--bag-type', type=str, default='single', 
                          choices=['single', 'double', 'triple', 'pediatric'])
    
    def handle(self, *args, **options):
        count = options['count']
        bag_type = options['bag_type']
        
        self.stdout.write(f"Generating {count} barcodes for {bag_type} bags...")
        
        barcodes = generate_batch_barcodes(
            count=count,
            bag_type=bag_type,
            created_by=None  # System generated
        )
        
        self.stdout.write(self.style.SUCCESS(
            f"✅ Successfully generated {len(barcodes)} barcodes"
        ))
        
        # Show first 10 as sample
        self.stdout.write("\nSample barcodes:")
        for barcode in barcodes[:10]:
            self.stdout.write(f"  {barcode.barcode}")
