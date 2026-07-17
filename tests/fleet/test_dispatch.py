import sys
from pathlib import Path
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from pd_fleet.dispatch import (  # noqa: E402
    AdapterDeniedError,
    Dispatcher,
    DispatchResult,
    SimulatedAdapter,
    UnknownAdapterError,
    DispatchError,
)


def task(**overrides):
    value = {"id": "T1", "role": "coder", "capabilities": ["python"], "objective": "do it"}
    value.update(overrides)
    return value


def test_selects_capability_then_role_then_simulated():
    dispatcher = Dispatcher(routes={"python": "simulated", "reviewer": "simulated"})
    assert dispatcher.select_adapter(task()) == "simulated"
    assert dispatcher.select_adapter(task(capabilities=[], role="reviewer")) == "simulated"
    assert dispatcher.select_adapter(task(capabilities=["unknown"], role="other")) == "simulated"


def test_unknown_adapter_fails_closed_with_actionable_error():
    dispatcher = Dispatcher(routes={"python": "missing"})
    with pytest.raises(UnknownAdapterError, match="adapter desconhecido.*simulated"):
        dispatcher.dispatch(task())


def test_external_adapter_is_denied_without_execution():
    class Remote:
        name = "remote"
        def dispatch(self, task, context):
            raise AssertionError("must not execute")

    with pytest.raises(AdapterDeniedError, match="default-deny"):
        Dispatcher(adapters={"remote": Remote()}, routes={"python": "remote"}).dispatch(task())


def test_credentials_and_urls_are_denied():
    dispatcher = Dispatcher()
    with pytest.raises(AdapterDeniedError, match="credencial"):
        dispatcher.dispatch(task(), {"api_key": "secret"})
    with pytest.raises(AdapterDeniedError, match="URL externa"):
        dispatcher.dispatch(task(objective="https://example.test/run"))


def test_dry_run_records_without_calling_adapter():
    dispatcher = Dispatcher(dry_run=True)
    result = dispatcher.dispatch(task())
    assert result.status == "dry_run"
    assert result.attempt == 0
    assert result.result == {"would_dispatch": True}
    assert dispatcher.records[0].evidence["dry_run"] is True


def test_simulated_result_is_deterministic_and_serializable():
    first = Dispatcher().dispatch(task(), {"attempt": 2})
    second = Dispatcher().dispatch(task(), {"attempt": 2})
    assert first == second
    assert first.status == "completed"
    assert first.attempt == 2
    assert first.evidence["deterministic"] is True
    assert first.to_dict()["task_id"] == "T1"


def test_duplicate_dispatch_is_idempotent_and_single_attempt():
    dispatcher = Dispatcher()
    first = dispatcher.dispatch(task())
    second = dispatcher.dispatch(task())
    assert second == first
    assert second is not first
    assert len(dispatcher.records) == 1
    assert dispatcher.reports()[0]["status"] == "completed"


def test_protocol_and_adapter_contract():
    adapter = SimulatedAdapter()
    assert isinstance(adapter, object)
    result = adapter.dispatch(task(), {})
    assert isinstance(result, DispatchResult)
    assert {"task_id", "adapter", "status", "attempt", "result", "evidence", "error"} == set(result.to_dict())


def test_simulated_cannot_be_overridden_or_executed():
    class Evil:
        name = "simulated"
        def dispatch(self, *_):
            raise AssertionError("must not execute")
    dispatcher = Dispatcher(adapters={"simulated": Evil()})
    assert isinstance(dispatcher.adapters["simulated"], SimulatedAdapter)
    with pytest.raises(AdapterDeniedError, match="fornecido externamente"):
        dispatcher.dispatch(task())


@pytest.mark.parametrize("value", ["prefix https://example.test/x", "ftp://example.test/x", "ws://example.test/x"])
def test_embedded_urls_and_object_inputs_are_denied(value):
    @dataclass
    class Payload:
        endpoint: str
    with pytest.raises(AdapterDeniedError, match="URL externa"):
        Dispatcher().dispatch(task(objective=Payload(value)))
    with pytest.raises(AdapterDeniedError, match="credencial"):
        Dispatcher().dispatch(task(metadata={"API-Key": "do-not-show"}))


def test_invalid_dry_run_and_capabilities_are_rejected():
    with pytest.raises(Exception, match="booleano"):
        Dispatcher(dry_run=1)
    with pytest.raises(Exception, match="capabilities"):
        Dispatcher().dispatch(task(capabilities="python"))


def test_adapter_exception_is_safe_failed_result_and_payload_changes_do_not_hit_cache():
    dispatcher = Dispatcher()
    with pytest.raises(TypeError):
        dispatcher.adapters["simulated"] = object()
    assert isinstance(dispatcher.adapters["simulated"], SimulatedAdapter)

    safe = Dispatcher()
    first = safe.dispatch(task(objective="one"))
    second = safe.dispatch(task(objective="two"))
    assert first is not second
    assert len(safe.records) == 2


def test_dispatch_outputs_and_history_are_defensive_copies():
    dispatcher = Dispatcher()
    result = dispatcher.dispatch(task())
    result.result["output"] = "tampered"
    result.evidence["fingerprint"] = "tampered"
    result_again = dispatcher.dispatch(task())
    assert result_again.result["output"] != "tampered"
    history = dispatcher.history
    history[0].result.result["output"] = "tampered"
    assert dispatcher.reports()[0]["result"]["result"]["output"] != "tampered"


def test_sensitive_dataclass_fields_are_denied():
    @dataclass
    class Credentials:
        api_key: str

    with pytest.raises(AdapterDeniedError, match="credencial"):
        Dispatcher().dispatch(task(metadata=Credentials("do-not-show")))


def test_throwing_to_dict_is_denied_without_running_dispatch():
    class Broken:
        def to_dict(self):
            raise RuntimeError("secret-value")

    with pytest.raises(AdapterDeniedError, match="conversão") as exc:
        Dispatcher().dispatch(task(metadata=Broken()))
    assert "secret-value" not in str(exc.value)


def test_cyclic_input_is_denied_without_recursion_error():
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(AdapterDeniedError, match="cíclica"):
        Dispatcher().dispatch(task(metadata=cyclic))


def test_unknown_adapter_error_does_not_echo_untrusted_name():
    name = "attacker-secret-value"
    with pytest.raises(UnknownAdapterError) as exc:
        Dispatcher().dispatch(task(adapter=name))
    assert name not in str(exc.value)


def test_simulated_name_is_immutable_and_literal():
    adapter = SimulatedAdapter()
    assert adapter.name == "simulated"
    with pytest.raises(AttributeError):
        adapter.name = "evil"
    assert adapter.name == "simulated"


@pytest.mark.parametrize("value", ["Bearer top-secret", "sk-live_123", "password=secret", "token:secret"])
def test_secret_like_values_are_denied_without_echoing_value(value):
    with pytest.raises(AdapterDeniedError) as exc:
        Dispatcher().dispatch(task(objective=value))
    assert value not in str(exc.value)


def test_sensitive_property_is_detected_static_without_invoking_it():
    class Payload:
        touched = False
        @property
        def api_key(self):
            Payload.touched = True
            raise AssertionError("must not invoke")
    with pytest.raises(AdapterDeniedError, match="propriedade sensível"):
        Dispatcher().dispatch(task(metadata=Payload()))
    assert Payload.touched is False


def test_property_and_field_exceptions_are_sanitized():
    class Broken:
        @property
        def id(self):
            raise RuntimeError("secret-id")
    with pytest.raises(DispatchError) as exc:
        Dispatcher().dispatch(Broken())
    assert "secret-id" not in str(exc.value)

    class BrokenField:
        id = "T1"
        @property
        def role(self):
            raise RuntimeError("secret-field")
    with pytest.raises(DispatchError) as exc:
        Dispatcher().select_adapter(BrokenField())
    assert "secret-field" not in str(exc.value)


@pytest.mark.parametrize("routes", [{"": "simulated"}, {"python": ""}, {1: "simulated"}, {"python": 1}])
def test_routes_require_nonempty_string_keys_and_values(routes):
    with pytest.raises(DispatchError, match="routes"):
        Dispatcher(routes=routes)


def test_opaque_slot_object_is_denied_instead_of_collapsing_to_type_fingerprint():
    class Opaque:
        __slots__ = ("value",)
        def __init__(self, value):
            self.value = value
    with pytest.raises(AdapterDeniedError, match="opaca"):
        Dispatcher().dispatch(task(metadata=Opaque("one")))


@pytest.mark.parametrize("value", ["TOKEN=top-secret", "authorization: top-secret",
                                    "client_secret=top-secret", "password : top-secret"])
def test_general_secret_assignment_and_colon_forms_are_denied(value):
    with pytest.raises(AdapterDeniedError) as exc:
        Dispatcher().dispatch(task(objective=value))
    assert "top-secret" not in str(exc.value)


def test_malicious_mapping_iteration_is_sanitized():
    class BrokenMapping(dict):
        def items(self):
            raise RuntimeError("mapping-secret")
    with pytest.raises((AdapterDeniedError, DispatchError)) as exc:
        Dispatcher().dispatch(task(metadata=BrokenMapping()))
    assert "mapping-secret" not in str(exc.value)


def test_malicious_task_id_strip_is_sanitized():
    class BrokenString(str):
        def strip(self, *args, **kwargs):
            raise RuntimeError("strip-secret")
    with pytest.raises(DispatchError) as exc:
        Dispatcher().dispatch({"id": BrokenString("T1")})
    assert "strip-secret" not in str(exc.value)


def test_malicious_explicit_adapter_conversion_is_sanitized():
    class BrokenName:
        def __str__(self):
            raise RuntimeError("adapter-secret")
    with pytest.raises(DispatchError) as exc:
        Dispatcher().dispatch(task(adapter=BrokenName()))
    assert "adapter-secret" not in str(exc.value)


def test_private_credential_name_is_denied_without_reading_value():
    class Payload:
        def __init__(self):
            self._api_key = "private-secret"
            self._harmless_cache = "safe"
    with pytest.raises(AdapterDeniedError, match="credencial") as exc:
        Dispatcher().dispatch(task(metadata=Payload()))
    assert "private-secret" not in str(exc.value)


@pytest.mark.parametrize("value", ["private_key=top-secret", "refresh-token: top-secret",
                                    "credential_name=top-secret", "client.secret = top-secret"])
def test_compound_secret_assignments_are_denied_without_echoing_value(value):
    with pytest.raises(AdapterDeniedError) as exc:
        Dispatcher().dispatch(task(objective=value))
    assert "top-secret" not in str(exc.value)


class HostileBool:
    def __bool__(self):
        raise AssertionError("untrusted bool must not run")


class HostileHash:
    def __hash__(self):
        raise AssertionError("untrusted hash must not run")


@pytest.mark.parametrize("field", ["adapter", "role"])
def test_untrusted_dispatch_ids_are_rejected_without_bool_or_hash(field):
    with pytest.raises(DispatchError):
        Dispatcher(routes={"coder": "simulated"}).select_adapter(task(**{field: HostileBool()}))


def test_untrusted_capability_and_task_ids_are_rejected_without_hash():
    with pytest.raises(DispatchError):
        Dispatcher(routes={"coder": "simulated"}).select_adapter(task(capabilities=[HostileHash()]))
    with pytest.raises(DispatchError):
        Dispatcher().dispatch({"id": HostileHash()})


def test_untrusted_mapping_truthiness_and_hash_are_not_coerced():
    class HostileMapping(dict):
        def __bool__(self):
            raise AssertionError("mapping bool must not run")

    result = Dispatcher(routes=HostileMapping({"coder": "simulated"})).dispatch(task())
    assert result.status == "completed"
