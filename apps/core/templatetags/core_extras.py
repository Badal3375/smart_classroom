from django import template

register = template.Library()


@register.filter
def attr(obj, path):
    """Resolve 'a.b.c' attribute paths (callables are called); supports get_<field>_display."""
    for part in str(path).split("."):
        obj = getattr(obj, part, "")
        if callable(obj):
            obj = obj()
    return obj if obj is not None else ""


@register.filter
def pct_class(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "secondary"
    return "success" if v >= 85 else "warning" if v >= 75 else "danger"


@register.filter
def status_badge(code):
    return {"P": "success", "L": "warning", "A": "danger", "E": "info"}.get(code, "secondary")


@register.simple_tag(takes_context=True)
def qs_without_page(context):
    q = context["request"].GET.copy()
    q.pop("page", None)
    return q.urlencode()
