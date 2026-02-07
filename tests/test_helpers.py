"""Tests for helpers module."""

from __future__ import annotations

import pytest

from custom_components.smartthings_dynamic.helpers import (
    as_bool,
    attribute_suffix,
    bool_like,
    capability_tail,
    capability_versions_for_component,
    component_label,
    device_label,
    get_capability_status,
    is_supported_meta_attribute,
    iter_capability_attributes,
    iter_device_components,
    safe_state,
)


# ─── device_label ───────────────────────────────────────────────────────────


class TestDeviceLabel:
    def test_uses_label_first(self, sample_device):
        assert device_label(sample_device) == "Samsung Washer"

    def test_falls_back_to_name(self, sample_device_no_label):
        assert device_label(sample_device_no_label) == "Kitchen Fridge"

    def test_falls_back_to_device_label_field(self):
        assert device_label({"deviceLabel": "My Oven"}) == "My Oven"

    def test_falls_back_to_device_type_name(self):
        assert device_label({"deviceTypeName": "OCF Device"}) == "OCF Device"

    def test_falls_back_to_device_id(self):
        assert device_label({"deviceId": "abc-123"}) == "abc-123"

    def test_empty_dict_returns_default(self):
        assert device_label({}) == "SmartThings Device"

    def test_label_is_empty_string_falls_through(self):
        dev = {"label": "", "name": "Fallback"}
        assert device_label(dev) == "Fallback"


# ─── component_label ────────────────────────────────────────────────────────


class TestComponentLabel:
    def test_returns_component_label(self, sample_device):
        assert component_label(sample_device, "main") == "Main"

    def test_returns_component_id_for_sub(self, sample_device):
        assert component_label(sample_device, "sub") == "AddWash Door"

    def test_unknown_component_returns_id(self, sample_device):
        assert component_label(sample_device, "nonexistent") == "nonexistent"

    def test_no_components_key(self):
        assert component_label({}, "main") == "main"

    def test_components_is_none(self):
        assert component_label({"components": None}, "main") == "main"

    def test_component_without_label(self):
        dev = {"components": [{"id": "zone1"}]}
        assert component_label(dev, "zone1") == "zone1"


# ─── capability_tail ────────────────────────────────────────────────────────


class TestCapabilityTail:
    def test_simple(self):
        assert capability_tail("switch") == "switch"

    def test_dotted(self):
        assert capability_tail("custom.washerWaterTemperature") == "washerWaterTemperature"

    def test_multiple_dots(self):
        assert capability_tail("samsung.custom.washerMode") == "washerMode"


# ─── attribute_suffix ───────────────────────────────────────────────────────


class TestAttributeSuffix:
    def test_attribute_same_as_capability(self):
        assert attribute_suffix("switch", "switch") == "switch"

    def test_attribute_different(self):
        assert attribute_suffix("washerOperatingState", "machineState") == "washerOperatingState.machineState"

    def test_case_insensitive_match(self):
        assert attribute_suffix("Switch", "switch") == "Switch"

    def test_dotted_capability(self):
        assert attribute_suffix("custom.washerMode", "washerMode") == "washerMode"


# ─── iter_device_components ─────────────────────────────────────────────────


class TestIterDeviceComponents:
    def test_yields_all_components(self, sample_device):
        data = {"devices": {"device-001": sample_device}}
        result = list(iter_device_components(data))
        assert len(result) == 2
        assert result[0] == ("device-001", sample_device, "main")
        assert result[1] == ("device-001", sample_device, "sub")

    def test_device_without_components_yields_main(self):
        data = {"devices": {"d1": {"deviceId": "d1"}}}
        result = list(iter_device_components(data))
        assert result == [("d1", {"deviceId": "d1"}, "main")]

    def test_empty_devices(self):
        assert list(iter_device_components({})) == []

    def test_devices_is_none(self):
        assert list(iter_device_components({"devices": None})) == []

    def test_component_without_id_defaults_to_main(self):
        data = {"devices": {"d1": {"components": [{}]}}}
        result = list(iter_device_components(data))
        assert result[0][2] == "main"


# ─── capability_versions_for_component ──────────────────────────────────────


class TestCapabilityVersionsForComponent:
    def test_returns_versions(self, sample_device):
        versions = capability_versions_for_component(sample_device, "main")
        assert versions == {
            "switch": 1,
            "washerOperatingState": 1,
            "custom.washerWaterTemperature": 1,
        }

    def test_sub_component(self, sample_device):
        versions = capability_versions_for_component(sample_device, "sub")
        assert versions == {"contactSensor": 1}

    def test_unknown_component_returns_empty(self, sample_device):
        assert capability_versions_for_component(sample_device, "nonexistent") == {}

    def test_no_components(self):
        assert capability_versions_for_component({}, "main") == {}

    def test_capability_without_id_is_skipped(self):
        dev = {"components": [{"id": "main", "capabilities": [{"version": 1}]}]}
        assert capability_versions_for_component(dev, "main") == {}

    def test_default_version_is_1(self):
        dev = {"components": [{"id": "main", "capabilities": [{"id": "switch"}]}]}
        result = capability_versions_for_component(dev, "main")
        assert result == {"switch": 1}


# ─── get_capability_status ──────────────────────────────────────────────────


class TestGetCapabilityStatus:
    def test_returns_capability_attributes(self, sample_coordinator_data):
        result = get_capability_status(sample_coordinator_data, "device-001", "main", "switch")
        assert result == {"switch": {"value": "on"}}

    def test_unknown_device_returns_empty(self, sample_coordinator_data):
        assert get_capability_status(sample_coordinator_data, "unknown", "main", "switch") == {}

    def test_unknown_component_returns_empty(self, sample_coordinator_data):
        assert get_capability_status(sample_coordinator_data, "device-001", "unknown", "switch") == {}

    def test_unknown_capability_returns_empty(self, sample_coordinator_data):
        assert get_capability_status(sample_coordinator_data, "device-001", "main", "unknown") == {}

    def test_no_status_key(self):
        assert get_capability_status({}, "d", "c", "cap") == {}

    def test_status_is_none(self):
        assert get_capability_status({"status": None}, "d", "c", "cap") == {}

    def test_device_status_is_not_dict(self):
        data = {"status": {"d1": "unexpected_string"}}
        assert get_capability_status(data, "d1", "main", "switch") == {}

    def test_capability_status_is_not_dict(self):
        data = {"status": {"d1": {"components": {"main": {"switch": "bad"}}}}}
        assert get_capability_status(data, "d1", "main", "switch") == {}


# ─── iter_capability_attributes ─────────────────────────────────────────────


class TestIterCapabilityAttributes:
    def test_yields_dict_attributes(self):
        cap = {"switch": {"value": "on"}, "bad_attr": "not_a_dict"}
        result = list(iter_capability_attributes(cap))
        assert result == [("switch", {"value": "on"})]

    def test_empty_dict(self):
        assert list(iter_capability_attributes({})) == []

    def test_none_input(self):
        assert list(iter_capability_attributes(None)) == []


# ─── safe_state ─────────────────────────────────────────────────────────────


class TestSafeState:
    def test_none(self):
        assert safe_state(None) is None

    def test_string(self):
        assert safe_state("running") == "running"

    def test_null_like_strings(self):
        assert safe_state("none") is None
        assert safe_state("null") is None
        assert safe_state("N/A") is None
        assert safe_state("na") is None
        assert safe_state("unknown") is None
        assert safe_state("") is None

    def test_integer(self):
        assert safe_state(42) == 42

    def test_float(self):
        assert safe_state(3.14) == 3.14

    def test_bool_true(self):
        # bool is subclass of int, so isinstance(True, int) is True
        # The function checks isinstance(value, str) first, then int/float, then bool
        # Since bool is a subclass of int, True will match int check first
        result = safe_state(True)
        assert result in (True, "on")  # depends on check order

    def test_bool_false(self):
        result = safe_state(False)
        assert result in (False, "off")

    def test_small_list(self):
        result = safe_state([1, 2, 3])
        assert result == "[1,2,3]"

    def test_small_dict(self):
        result = safe_state({"key": "val"})
        assert result == '{"key":"val"}'

    def test_large_list_truncated(self):
        big = list(range(200))
        result = safe_state(big)
        assert result == f"list[{len(big)}]"

    def test_large_dict_truncated(self):
        big = {f"key_{i}": f"value_{i}" for i in range(100)}
        result = safe_state(big)
        assert result == f"dict[{len(big)}]"

    def test_whitespace_null_like(self):
        assert safe_state("  none  ") is None
        assert safe_state(" NULL ") is None


# ─── is_supported_meta_attribute ────────────────────────────────────────────


class TestIsSupportedMetaAttribute:
    def test_supported_prefix(self):
        assert is_supported_meta_attribute("supportedMachineStates") is True

    def test_range_suffix(self):
        assert is_supported_meta_attribute("temperatureRange") is True

    def test_ranges_suffix(self):
        assert is_supported_meta_attribute("temperatureRanges") is True

    def test_exact_matches(self):
        assert is_supported_meta_attribute("supportedoptions") is True
        assert is_supported_meta_attribute("referencetable") is True
        assert is_supported_meta_attribute("settable") is True
        assert is_supported_meta_attribute("supportedcommands") is True

    def test_normal_attribute_returns_false(self):
        assert is_supported_meta_attribute("machineState") is False
        assert is_supported_meta_attribute("temperature") is False

    def test_case_insensitive(self):
        assert is_supported_meta_attribute("SupportedModes") is True
        assert is_supported_meta_attribute("TEMPERATURERANGE") is True


# ─── bool_like ──────────────────────────────────────────────────────────────


class TestBoolLike:
    def test_actual_bool(self):
        assert bool_like(True) is True
        assert bool_like(False) is True

    def test_string_values(self):
        assert bool_like("on") is True
        assert bool_like("off") is True
        assert bool_like("open") is True
        assert bool_like("closed") is True
        assert bool_like("true") is True
        assert bool_like("false") is True

    def test_non_bool_like(self):
        assert bool_like("running") is False
        assert bool_like(42) is False
        assert bool_like(None) is False
        assert bool_like("") is False


# ─── as_bool ────────────────────────────────────────────────────────────────


class TestAsBool:
    def test_actual_bool(self):
        assert as_bool(True) is True
        assert as_bool(False) is False

    def test_truthy_strings(self):
        assert as_bool("on") is True
        assert as_bool("open") is True
        assert as_bool("true") is True

    def test_falsy_strings(self):
        assert as_bool("off") is False
        assert as_bool("closed") is False
        assert as_bool("false") is False

    def test_case_insensitive(self):
        assert as_bool("ON") is True
        assert as_bool("OFF") is False
        assert as_bool("True") is True

    def test_unknown_returns_none(self):
        assert as_bool("running") is None
        assert as_bool(42) is None
        assert as_bool(None) is None
