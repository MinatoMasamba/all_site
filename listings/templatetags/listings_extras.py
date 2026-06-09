from django import template

register = template.Library()


@register.filter
def split_virgule(value):
    """Splits a comma-separated string into a list of stripped items."""
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]
