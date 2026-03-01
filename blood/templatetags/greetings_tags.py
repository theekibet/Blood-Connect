from django import template
from blood.utils.greetings import (
    get_phlebotomist_greeting,  
    get_donor_greeting, 
    get_generic_greeting
)

register = template.Library()

@register.inclusion_tag('shared/greeting_card.html')
def show_greeting_card(user, user_type, context_data=None):
    """
    Template tag to show greeting card for any user type
    Usage: {% show_greeting_card request.user 'phlebotomist' phlebotomist_context %}
    """
    greeting_data = get_generic_greeting(user, user_type)
    
    # You can extend this based on user_type and context_data
    # For now, return basic greeting
    return {'greeting_data': greeting_data}