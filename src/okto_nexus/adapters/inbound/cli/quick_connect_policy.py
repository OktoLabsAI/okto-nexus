"""Presentation rollback only; public metadata and canonical connections survive."""
import os


def entry_enabled(environment=None):
    environment = os.environ if environment is None else environment
    return environment.get('OKTO_NEXUS_QUICK_CONNECT', 'on').strip().lower() not in ('0', 'false', 'off', 'disabled')
