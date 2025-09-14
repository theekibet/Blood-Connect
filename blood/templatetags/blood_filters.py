from django import template

register = template.Library()

@register.filter(name='multiply_by_0_1')
def multiply_by_0_1(value):
    """
    Multiplies the input value by 0.1 and returns the result as an integer.
    Handles non-numeric values gracefully.
    """
    try:
        return int(float(value) * 0.1)
    except (ValueError, TypeError):
        return 0

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Retrieves a value from a dictionary safely using a key.
    """
    return dictionary.get(key)
