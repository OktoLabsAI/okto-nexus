"""Normalize Connector unlimited limits to the internal configuration contract."""
from nexus_connector_core import CoreError


def normalize_authorization(configuration):
    if not isinstance(configuration, dict):
        return configuration
    limits = configuration.get('authorization')
    if not isinstance(limits, dict):
        return configuration
    if set(limits) - {'minutes', 'actions', 'no_expiry', 'unlimited_actions'}:
        raise CoreError('VALIDATION_ERROR', 'connection_configuration')
    normalized = {}
    for name, flag in [('minutes', 'no_expiry'), ('actions', 'unlimited_actions')]:
        if name not in limits:
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        value = limits[name]
        if value is not None and type(value) is not int:
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        unlimited = value is None or value == 0
        if flag in limits and (type(limits[flag]) is not bool or limits[flag] != unlimited):
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        normalized[name] = None if unlimited else value
    return {**configuration, 'authorization': normalized}
