"""Public, read-only Connector reachability contract."""
from importlib import metadata

# Minimum Connector release supported by this Server's management contract.
MINIMUM_CLI_VERSION = '0.0.1'


def reach_info():
    def installed(name, fallback):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return fallback
    return {
        'service': 'okto-nexus',
        'server_version': installed('okto-nexus', 'dev'),
        'server_core_version': installed('okto-nexus-connector-core', None),
        'minimum_cli_version': MINIMUM_CLI_VERSION,
    }
