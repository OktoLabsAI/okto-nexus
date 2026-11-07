"""Persist the selected supervisor's stop intent before owner containment."""
from .installation import INSTALLATION_NAME, ServerInstallation
from .local import launch_exclusion


def persist_service_stop(lock):
    if lock is None or not (lock.home_dir / INSTALLATION_NAME).exists():
        return
    generation = lock.generation
    with launch_exclusion(lock.home_dir, lock.db_path):
        if not lock.owned or not generation or lock.generation != generation:
            raise ValueError('Service owner changed before persisting its stop intent.')
        ServerInstallation(lock.home_dir, lock.db_path).begin_stop(generation)
