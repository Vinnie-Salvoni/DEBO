from desk_robot.core.capabilities import Capability, CapabilityRegistry, CapabilityStatus

def test_capabilities_are_independent() -> None:
    registry = CapabilityRegistry()
    assert registry.get(Capability.INTERNET).status is CapabilityStatus.UNKNOWN
    registry.set_status(Capability.OLLAMA, CapabilityStatus.UNAVAILABLE)
    assert registry.get(Capability.OLLAMA).status is CapabilityStatus.UNAVAILABLE
    assert registry.get(Capability.INTERNET).status is CapabilityStatus.UNKNOWN

def test_capability_snapshot_is_immutable_and_includes_all_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.set_status(Capability.INTERNET, CapabilityStatus.AVAILABLE, detail="direct device", checked_at=123.0)
    snapshot = registry.snapshot()
    internet = next(item for item in snapshot if item.capability is Capability.INTERNET)
    assert internet.status is CapabilityStatus.AVAILABLE
    assert internet.detail == "direct device"
    assert internet.checked_at == 123.0
    assert len(snapshot) == len(Capability)

def test_blank_detail_normalises_to_none() -> None:
    item = CapabilityRegistry().set_status(Capability.NEWS, CapabilityStatus.UNAVAILABLE, detail="   ")
    assert item.detail is None
