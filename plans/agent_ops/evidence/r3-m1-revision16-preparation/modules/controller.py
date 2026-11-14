"""Facade shares the one policy/ancestry origin; no stale copied literals."""
from legacy_controller import POLICY, ANCESTRY, Refused, seal, digest
from independent_controller import Controller
import independent_controller
assert POLICY is independent_controller.POLICY
