# custom_filters.py

from django import template

register = template.Library()

@register.filter(name='multiply_by_0_1')
def multiply_by_0_1(value):
    """
    Multiplies the input value by 0.1 and returns the result as an integer.
    Handles non-numeric values gracefully.
    """
    try:
        return int(float(value) * 0.1)  # Convert to float first to handle decimal values
    except (ValueError, TypeError):
        return 0  # Return 0 for non-numeric values

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Custom filter to get a value from a dictionary by key.
    Returns 0 if dictionary is None or key is missing.
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0
