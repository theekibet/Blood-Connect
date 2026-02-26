# blood/utils/barcode_utils.py

import uuid
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from blood.models import BloodBagBarcode

logger = logging.getLogger(__name__)

def generate_barcode(prefix="BB"):
    """
    Generate a unique barcode
    Format: BB-YYYYMMDD-XXXXXX (e.g., BB-20250225-A1B2C3)
    """
    date_part = datetime.now().strftime("%Y%m%d")
    unique_part = uuid.uuid4().hex[:6].upper()
    barcode = f"{prefix}-{date_part}-{unique_part}"
    return barcode

def generate_batch_barcodes(count, bag_type='single', volume=450, 
                           anticoagulant='cpd', created_by=None):
    """
    Generate a batch of barcodes
    
    Args:
        count: Number of barcodes to generate
        bag_type: Type of blood bag
        volume: Volume in ml
        anticoagulant: Type of anticoagulant
        created_by: User creating the barcodes
    
    Returns:
        List of created BloodBagBarcode objects
    """
    created_barcodes = []
    expiry_date = timezone.now().date() + timedelta(days=730)  # 2 years expiry for bags
    
    for i in range(count):
        # Generate unique barcode
        barcode = generate_barcode()
        
        # Ensure uniqueness (though highly unlikely)
        while BloodBagBarcode.objects.filter(barcode=barcode).exists():
            barcode = generate_barcode()
        
        # Create barcode record
        bag = BloodBagBarcode.objects.create(
            barcode=barcode,
            bag_type=bag_type,
            volume_ml=volume,
            anticoagulant=anticoagulant,
            status='available',
            manufacture_date=timezone.now().date(),
            expiry_date=expiry_date,
            created_by=created_by
        )
        created_barcodes.append(bag)
        logger.info(f"✅ Generated barcode: {barcode}")
    
    return created_barcodes

def get_available_barcodes(center=None, bag_type=None, limit=50):
    """
    Get available barcodes for assignment
    """
    queryset = BloodBagBarcode.objects.filter(status='available')
    
    if bag_type:
        queryset = queryset.filter(bag_type=bag_type)
    
    # Order by oldest first (FIFO)
    return queryset.order_by('created_at')[:limit]

def get_assigned_barcodes(donor):
    """
    Get barcodes assigned to a specific donor
    """
    return BloodBagBarcode.objects.filter(
        assigned_to_donor=donor,
        status='assigned'
    ).order_by('-assigned_at')