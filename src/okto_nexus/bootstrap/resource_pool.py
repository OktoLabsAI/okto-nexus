"""Composition root for the internal durable pool/queue adapters."""
from ..application.resource_pool import ResourcePool
from ..adapters.outbound.sqlite.resource_pool import SQLitePoolTransaction


def one_shot_pool(connection):
    return ResourcePool(SQLitePoolTransaction(connection), error_prefix='ONE_SHOT')
