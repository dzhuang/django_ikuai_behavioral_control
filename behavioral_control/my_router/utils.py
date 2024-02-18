from __future__ import annotations

from django import forms

from my_router.constants import (
    CACHE_VERSION, DEVICE_DB_CACHE_KEY_PATTERN,
    ROUTER_ACL_L7_LIST_CACHE_KEY_PATTERN, ROUTER_DEVICE_CACHE_KEY_PATTERN,
    ROUTER_DEVICE_MAC_ADDRESSES_CACHE_KEY_PATTERN,
    ROUTER_DEVICE_MAC_GROUPS_LIST_CACHE_KEY_PATTERN,
    ROUTER_DEVICES_CACHE_KEY_PATTERN,
    ROUTER_DOMAIN_BLACKLIST_CACHE_KEY_PATTERN,
    ROUTER_URL_BLACK_LIST_CACHE_KEY_PATTERN, days_const)
from my_router.fields import mac_re


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        # type: (...) -> None
        from crispy_forms.helper import FormHelper
        self.helper = FormHelper()
        self._configure_helper()

        super().__init__(*args, **kwargs)

    def _configure_helper(self):
        # type: () -> None
        self.helper.form_class = "form-horizontal"
        self.helper.label_class = "col-lg-2"
        self.helper.field_class = "col-lg-8"


class StyledForm(StyledFormMixin, forms.Form):
    pass


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    pass


class CacheDataDoesNotExist(Exception):
    pass


def is_valid_mac_address(mac_address):
    return bool(mac_re.match(mac_address))


def get_router_device_cache_key(router_id, mac_address):
    return ROUTER_DEVICE_CACHE_KEY_PATTERN.format(
        router_id=router_id, mac=mac_address, cache_version=CACHE_VERSION)


def get_router_all_devices_mac_cache_key(router_id):
    return ROUTER_DEVICE_MAC_ADDRESSES_CACHE_KEY_PATTERN.format(
        router_id=router_id, cache_version=CACHE_VERSION)


def get_device_list_cache_key(router_id):
    return ROUTER_DEVICES_CACHE_KEY_PATTERN.format(
        router_id=router_id, cache_version=CACHE_VERSION)


def get_device_db_cache_key(mac):
    return DEVICE_DB_CACHE_KEY_PATTERN.format(mac=mac, cache_version=CACHE_VERSION)


def get_acl_l7_list_cache_key(router_id):
    return ROUTER_ACL_L7_LIST_CACHE_KEY_PATTERN.format(
        router_id=router_id,
        cache_version=CACHE_VERSION)


def get_mac_groups_cache_key(router_id):
    return ROUTER_DEVICE_MAC_GROUPS_LIST_CACHE_KEY_PATTERN.format(
        router_id=router_id,
        cache_version=CACHE_VERSION)


def get_url_black_list_cache_key(router_id):
    return ROUTER_URL_BLACK_LIST_CACHE_KEY_PATTERN.format(
        router_id=router_id,
        cache_version=CACHE_VERSION)


def get_domain_blacklist_cache_key(router_id):
    return ROUTER_DOMAIN_BLACKLIST_CACHE_KEY_PATTERN.format(
        router_id=router_id,
        cache_version=CACHE_VERSION)


def days_string_conversion(input_, reverse_=False):
    """
    This function either converts a string containing digits 1 to 7 to a list of
    abbreviated day names or converts a list of abbreviated day names to a string
    containing digits 1 to 7 based on the reverse_ parameter.

    Args:
    input_ (str or list): A string containing digits 1 to 7 or a list of
    abbreviated day names.
    reverse_ (bool): If False, converts string to list; if True, converts list to
    string.

    Returns:
    str or list: Based on the reverse_ parameter, returns either a list of
    abbreviated day names or a string of digits.
    """
    day_mapping = {
        "1": days_const.mon,
        "2": days_const.tue,
        "3": days_const.wed,
        "4": days_const.thu,
        "5": days_const.fri,
        "6": days_const.sat,
        "7": days_const.sun
    }
    reverse_day_mapping = {v: k for k, v in day_mapping.items()}

    if reverse_:
        # Convert list to string
        output = "".join([reverse_day_mapping[day] for day in input_ if
                          day in reverse_day_mapping])
    else:
        # Convert string to list
        output = [day_mapping[digit] for digit in
                  input_ if digit in day_mapping]

    return output


def find_data_with_id_from_list_of_dict(l_of_d: list, id_to_find):
    for d in l_of_d:
        if "id" not in d:
            continue
        if int(d["id"]) == int(id_to_find):
            return d

    raise ValueError(f"id {id_to_find} not found in give data.")
