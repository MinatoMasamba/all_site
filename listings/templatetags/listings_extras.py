from django import template

register = template.Library()


@register.filter
def split_virgule(value):
    """Splits a comma-separated string into a list of stripped items."""
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


@register.filter
def is_maps_url(value):
    """Returns True if the URL is a Google Maps or OpenStreetMap link."""
    if not value:
        return False
    return "google.com/maps" in value or "openstreetmap.org" in value


@register.filter
def widget_type(field):
    """Returns a form field's widget class name (dunder lookups are blocked in templates)."""
    return field.field.widget.__class__.__name__
