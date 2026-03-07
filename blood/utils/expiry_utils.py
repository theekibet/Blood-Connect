# blood/utils/expiry_utils.py
from datetime import timedelta
from django.utils import timezone

def calculate_expiry_date(collection_date, component_type='whole_blood'):
    """
    Calculate expiry date based on blood component type.
    
    Medical standards (Kenya NBTS):
    - Whole Blood: 35 days at 1-6°C
    - Packed RBCs: 42 days with additive solution
    - Platelets: 5 days at 20-24°C with agitation  
    - Fresh Frozen Plasma: 365 days at -18°C
    - Cryoprecipitate: 365 days at -18°C
    """
    # Handle both date and datetime objects
    if hasattr(collection_date, 'date'):
        collection_date = collection_date.date()
    
    expiry_rules = {
        'whole_blood': 35,
        'rbc': 42,
        'platelets': 5,
        'ffp': 365,
        'cryo': 365,
    }
    
    days = expiry_rules.get(component_type, 35)
    return collection_date + timedelta(days=days)


def get_expiry_display(days_remaining):
    """Return human-readable expiry status"""
    if days_remaining is None:
        return "⏸️ Not applicable"
    if days_remaining < 0:
        return "⚠️ EXPIRED"
    if days_remaining < 7:
        return f"🔴 Expiring soon ({days_remaining} days)"
    if days_remaining < 14:
        return f"🟡 {days_remaining} days remaining"
    return f"🟢 {days_remaining} days remaining"


def get_component_type_display(component_type):
    """Get display name with shelf life"""
    displays = {
        'whole_blood': 'Whole Blood (35 days)',
        'rbc': 'Packed RBCs (42 days)',
        'platelets': 'Platelets (5 days)',
        'ffp': 'Fresh Frozen Plasma (1 year)',
        'cryo': 'Cryoprecipitate (1 year)',
    }
    return displays.get(component_type, component_type)