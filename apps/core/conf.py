"""Runtime configuration: DB-stored SystemSetting overrides settings.DEFAULT_SYSTEM_SETTINGS."""
from django.conf import settings
from django.core.cache import cache

_CACHE_KEY = "system_settings_v1"


def _load():
    data = cache.get(_CACHE_KEY)
    if data is None:
        from .models import SystemSetting
        data = {s.key: s.value for s in SystemSetting.objects.all()}
        cache.set(_CACHE_KEY, data, 60)
    return data


def get(key, cast=str):
    raw = _load().get(key)
    if raw is None:
        raw = settings.DEFAULT_SYSTEM_SETTINGS.get(key, ("", ""))[0]
    if raw in ("", None):
        return None
    try:
        if cast is bool:
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        return cast(raw)
    except (TypeError, ValueError):
        return cast(settings.DEFAULT_SYSTEM_SETTINGS.get(key, ("0", ""))[0] or 0)


def clear_cache():
    cache.delete(_CACHE_KEY)


def ensure_defaults():
    from .models import SystemSetting
    for k, (v, d) in settings.DEFAULT_SYSTEM_SETTINGS.items():
        SystemSetting.objects.get_or_create(key=k, defaults={"value": v, "description": d})
