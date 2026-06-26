"""Path safety checks for Tor-like 3-hop client circuits.

This module is a guard rail for lab ideas. It does not replace Tor's full path
selection code. It only blocks obvious unsafe paths before we benchmark them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Relay:
    name: str
    fingerprint: str
    flags: frozenset[str] = field(default_factory=frozenset)
    family: frozenset[str] = field(default_factory=frozenset)
    ipv4: str | None = None
    ipv6: str | None = None
    exit_ports: frozenset[int] = field(default_factory=frozenset)

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def supports_port(self, port: int) -> bool:
        return port in self.exit_ports


def relay(
    name: str,
    fingerprint: str,
    *,
    flags: Iterable[str] = (),
    family: Iterable[str] = (),
    ipv4: str | None = None,
    ipv6: str | None = None,
    exit_ports: Iterable[int] = (),
) -> Relay:
    """Create a relay while normalizing set-like fields."""

    return Relay(
        name=name,
        fingerprint=fingerprint,
        flags=frozenset(flags),
        family=frozenset(family),
        ipv4=ipv4,
        ipv6=ipv6,
        exit_ports=frozenset(exit_ports),
    )


def validate_three_hop_path(
    path: Sequence[Relay],
    *,
    target_port: int,
    ipv4_prefix: int = 16,
    ipv6_prefix: int = 32,
) -> list[str]:
    """Return path rule errors. Empty list means the basic checks passed."""

    errors: list[str] = []

    if len(path) != 3:
        errors.append("path_length_must_be_3")
        return errors

    guard, _middle, exit_relay = path

    if not guard.has_flag("Guard"):
        errors.append(f"first_hop_must_be_guard:{guard.name}")

    for item in path:
        if not item.has_flag("Fast"):
            errors.append(f"relay_missing_fast_flag:{item.name}")

    fingerprints = [item.fingerprint for item in path]
    if len(set(fingerprints)) != len(fingerprints):
        errors.append("path_reuses_relay")

    errors.extend(_family_errors(path))
    errors.extend(_subnet_errors(path, ipv4_prefix=ipv4_prefix, ipv6_prefix=ipv6_prefix))

    if not exit_relay.supports_port(target_port):
        errors.append(f"exit_policy_rejects_port:{exit_relay.name}:{target_port}")

    return errors


def assert_three_hop_path(path: Sequence[Relay], *, target_port: int) -> None:
    """Raise ValueError if the path fails the basic quality gate."""

    errors = validate_three_hop_path(path, target_port=target_port)
    if errors:
        raise ValueError(", ".join(errors))


def _family_errors(path: Sequence[Relay]) -> list[str]:
    errors: list[str] = []
    for left_index, left in enumerate(path):
        for right in path[left_index + 1 :]:
            direct_family_link = (
                right.fingerprint in left.family or left.fingerprint in right.family
            )
            shared_family_id = bool(left.family & right.family)
            if direct_family_link or shared_family_id:
                errors.append(f"relays_share_family:{left.name}:{right.name}")
    return errors


def _subnet_errors(
    path: Sequence[Relay], *, ipv4_prefix: int, ipv6_prefix: int
) -> list[str]:
    errors: list[str] = []
    for left_index, left in enumerate(path):
        for right in path[left_index + 1 :]:
            if _same_network(left.ipv4, right.ipv4, ipv4_prefix):
                errors.append(f"relays_share_ipv4_subnet:{left.name}:{right.name}")
            if _same_network(left.ipv6, right.ipv6, ipv6_prefix):
                errors.append(f"relays_share_ipv6_subnet:{left.name}:{right.name}")
    return errors


def _same_network(left: str | None, right: str | None, prefix: int) -> bool:
    if not left or not right:
        return False
    left_ip = ipaddress.ip_address(left)
    right_ip = ipaddress.ip_address(right)
    if left_ip.version != right_ip.version:
        return False
    return (
        ipaddress.ip_network(f"{left_ip}/{prefix}", strict=False)
        == ipaddress.ip_network(f"{right_ip}/{prefix}", strict=False)
    )
