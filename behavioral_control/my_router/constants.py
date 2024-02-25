import django.core.cache as cache
from django.utils.translation import gettext_lazy as _

CACHE_VERSION = 1
DEFAULT_CACHE = cache.caches["default"]

ROUTER_DEVICES_CACHE_KEY_PATTERN = "router-instance:{router_id}{cache_version}"

ROUTER_DEVICES_BLOCK_MAC_BY_ACL_L7_CACHE_KEY_PATTERN = (
    "{router_id}:block_mac_by_acl_l7:{cache_version}")

ROUTER_DEVICE_MAC_ADDRESSES_CACHE_KEY_PATTERN = (
    "{router_id}:mac_addresses:{cache_version}")
ROUTER_DEVICE_CACHE_KEY_PATTERN = "{router_id}:device:{mac}{cache_version}"

DEVICE_DB_CACHE_KEY_PATTERN = "db-cache:{mac}:{cache_version}"

ROUTER_DEVICE_MAC_GROUPS_LIST_CACHE_KEY_PATTERN = (
    "{router_id}:mac_groups:{cache_version}")

ROUTER_ACL_L7_LIST_CACHE_KEY_PATTERN = "{router_id}:acl_l7:{cache_version}"

ROUTER_URL_BLACK_LIST_CACHE_KEY_PATTERN = "{router_id}:url_black:{cache_version}"

ROUTER_DOMAIN_BLACKLIST_CACHE_KEY_PATTERN = (
    "{router_id}:domain_black:{cache_version}")


class ReadonlyDict(dict):
    # This is a read only dict, but key can be visit via attribute
    # https://stackoverflow.com/a/31049908/3437454
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __readonly__(self, *args, **kwargs):
        raise RuntimeError("Cannot modify ReadOnlyDict")

    __setattr__ = __readonly__
    __setitem__ = __readonly__
    __delattr__ = __readonly__
    pop = __readonly__
    popitem = __readonly__
    clear = __readonly__
    update = __readonly__
    setdefault = __readonly__
    del __readonly__


class router_status:  # noqa
    active = "active"
    disabled = "disabled"


ROUTER_STATUS_CHOICES = (
    (router_status.active, _("Active")),
    (router_status.disabled, _("Disabled")),
)

days_const = ReadonlyDict(
    mon="mon",
    tue="tue",
    wed="wed",
    thu="thu",
    fri="fri",
    sat="sat",
    sun="sun"
)

DAYS_CHOICES = (
    (days_const.mon, _("Monday")),
    (days_const.tue, _("Tuesday")),
    (days_const.wed, _("Wednesday")),
    (days_const.thu, _("Thursday")),
    (days_const.fri, _("Friday")),
    (days_const.sat, _("Saturday")),
    (days_const.sun, _("Sunday"))
)
