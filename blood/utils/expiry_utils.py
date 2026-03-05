# blood/utils/expiry_utils.py

from datetime import timedelta
from django.utils import timezone

def calculate_expiry_date(collection_date, component_type='whole_blood'):
    """
    Calculate expiry date based on blood component type and collection date.
    
    Medical standards:
    - Whole Blood: 35 days (stored at 1-6°C)
    - Packed RBCs: 42 days (stored at 1-6°C with additive solution)
    - Platelets: 5 days (stored at 20-24°C with agitation)
    - Fresh Frozen Plasma: 365 days (stored at -18°C or colder)
    - Cryoprecipitate: 365 days (stored at -18°C or colder)
    """
    
    expiry_rules = {
        'whole_blood': 35,      # days
        'rbc': 42,              # packed red blood cells
        'platelets': 5,         # platelets (short shelf life!)
        'ffp': 365,             # fresh frozen plasma
        'cryo': 365,            # cryoprecipitate
    }
    
    days = expiry_rules.get(component_type, 35) 
    return collection_date + timedelta(days=days)


def get_expiry_display(days_remaining):
    """Return human-readable expiry status"""
    if days_remaining < 0:
        return "⚠️ EXPIRED"
    elif days_remaining < 7:
        return f"🔴 Expiring soon ({days_remaining} days)"
    elif days_remaining < 14:
        return f"🟡 {days_remaining} days remaining"
    else:
        return f"🟢 {days_remaining} days remaining"