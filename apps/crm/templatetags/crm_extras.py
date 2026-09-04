from django import template

register = template.Library()


@register.filter
def get(mapping, key):
    """{{ some_dict|get:key }} — безопасный доступ по ключу."""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def get_item(mapping, key):
    return get(mapping, key)
