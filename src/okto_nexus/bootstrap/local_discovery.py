"""Local serve arguments for passive Core discovery; never wire configuration."""
from dataclasses import dataclass
from pathlib import Path

from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True)
class LocalDiscoveryConfiguration:
    trusted_roots: tuple[Path, ...] = ()
    pi_install_root: Path | None = None
    pi_node: Path | None = None

    def arguments(self):
        return dict(trusted_roots=self.trusted_roots, pi_install_root=self.pi_install_root,
                    pi_node=self.pi_node)


def split_discovery_args(args):
    """Keep discovery approval on the local owner CLI, before serve starts."""
    roots, values, rest = [], {}, []
    flags = {'--harness-root', '--pi-install-root', '--pi-node'}
    index = 0
    while index < len(args):
        token = args[index]
        flag, separator, inline = token.partition('=')
        index += 1
        if flag not in flags:
            rest.append(token)
            continue
        if separator:
            raw = inline
        elif index < len(args) and not args[index].startswith('--'):
            raw = args[index]
            index += 1
        else:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'A discovery path is required.', {'flag':flag})
        try:
            path = Path(raw)
            if not raw or not path.is_absolute():
                raise ValueError()
            path = path.resolve(strict=True)
            if not (path.is_file() if flag == '--pi-node' else path.is_dir()):
                raise ValueError()
        except (OSError, ValueError):
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                'Discovery paths must be existing absolute local paths.', {'flag':flag}) from None
        if flag == '--harness-root':
            if path not in roots:
                roots.append(path)
            if len(roots) > 32:
                raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'At most 32 discovery roots are allowed.')
        elif flag in values:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'A discovery option was repeated.', {'flag':flag})
        else:
            values[flag] = path
    if ('--pi-install-root' in values) != ('--pi-node' in values):
        raise OktoNexusError(ErrorCode.CONFIG_ERROR, 'Pi discovery requires both --pi-install-root and --pi-node.')
    return LocalDiscoveryConfiguration(tuple(roots), values.get('--pi-install-root'), values.get('--pi-node')), rest
