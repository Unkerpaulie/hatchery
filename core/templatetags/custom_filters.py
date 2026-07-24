from django import template
from django.template.defaultfilters import floatformat

register = template.Library()

@register.filter(name='currency_comma')
def currency_comma(value):
    """Format a number as currency with comma separation and 2 decimal places.
    
    Example: 1234567.89 -> 1,234,567.89
    """
    try:
        # First format to 2 decimal places using Django's floatformat
        formatted = floatformat(value, 2)
        if formatted is None or formatted == '':
            return value
        
        # Split on decimal point
        parts = formatted.split('.')
        integer_part = parts[0]
        decimal_part = parts[1] if len(parts) > 1 else '00'
        
        # Add commas to the integer part
        has_negative = integer_part.startswith('-')
        if has_negative:
            integer_part = integer_part[1:]
        
        # Add commas every 3 digits from the right
        comma_groups = []
        while len(integer_part) > 3:
            comma_groups.insert(0, integer_part[-3:])
            integer_part = integer_part[:-3]
        comma_groups.insert(0, integer_part)
        integer_with_commas = ','.join(comma_groups)
        
        if has_negative:
            integer_with_commas = '-' + integer_with_commas
        
        return f'{integer_with_commas}.{decimal_part}'
    except (ValueError, TypeError, AttributeError):
        return value