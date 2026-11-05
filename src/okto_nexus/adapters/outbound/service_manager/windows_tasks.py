"""Lazy Windows Task Scheduler I/O; never register a task during inspection.

Task Scheduler has no compare-and-swap API. Each mutation re-reads the native
definition immediately beforehand. Host launch exclusion serializes our own
callers; an external administrator/editor is outside that lock.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexus_connector_core.user_service_definition import windows_definition_digest


class TaskConflict(ValueError):
    pass


@dataclass(frozen=True)
class TaskObservation:
    xml: str
    state: int
    enabled: bool
    last_result: int

    @property
    def digest(self):
        return windows_definition_digest(self.xml)

    @property
    def active(self):
        return self.state in {2, 4}  # QUEUED / RUNNING; never infer app readiness


class WindowsTasks:
    def __init__(self):
        self._service = None

    def _connect(self):
        if self._service is None:
            import win32com.client
            self._service = win32com.client.Dispatch('Schedule.Service')
            self._service.Connect()
        return self._service

    def _task(self, name):
        import pywintypes
        try:
            return self._connect().GetFolder('\\').GetTask(name)
        except pywintypes.com_error as error:
            codes = {error.hresult}
            if error.excepinfo:
                codes.add(error.excepinfo[5])
            if -2147024894 in codes:  # HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)
                return None
            raise OSError('Task Scheduler could not inspect the selected task') from error

    def read(self, name):
        import pywintypes
        task = self._task(name)
        try:
            return None if task is None else TaskObservation(
                task.Xml, int(task.State), bool(task.Enabled), int(task.LastTaskResult))
        except pywintypes.com_error as error:
            raise OSError('The selected task observation was not confirmed') from error

    def create(self, name, xml):
        # TASK_CREATE, never UPDATE, CREATE_OR_UPDATE or schtasks /F.
        import pywintypes
        try:
            task = self._connect().GetFolder('\\').RegisterTask(name, xml, 2, None, None, 3, None)
            return TaskObservation(task.Xml, int(task.State), bool(task.Enabled), int(task.LastTaskResult))
        except pywintypes.com_error as error:
            raise OSError('Task registration was not confirmed; inspect the retained receipt') from error

    def validate(self, name, xml):
        import pywintypes
        try:
            # TASK_VALIDATE_ONLY is deliberately separate from registration.
            self._connect().GetFolder('\\').RegisterTask(name, xml, 1, None, None, 3, None)
        except pywintypes.com_error as error:
            raise OSError('Task Scheduler could not validate the proposed definition') from error

    def _matching(self, name, expected):
        import pywintypes
        task = self._task(name)
        try:
            if task is None or windows_definition_digest(task.Xml) != expected:
                raise TaskConflict('The selected task definition changed; reconcile it before mutation')
        except pywintypes.com_error as error:
            raise OSError('The selected task definition was not confirmed') from error
        return task

    def start(self, name, expected):
        import pywintypes
        task = self._matching(name, expected)
        try:
            task.Run(None)
        except pywintypes.com_error as error:
            raise OSError('Task start was not confirmed; observe the same task') from error

    def delete(self, name, expected):
        import pywintypes
        task = self._matching(name, expected)
        try:
            if int(task.State) in {0, 2, 4}:
                raise TaskConflict('The selected task is still active or unconfirmed')
            self._connect().GetFolder('\\').DeleteTask(name, 0)
        except pywintypes.com_error as error:
            raise OSError('Task removal was not confirmed; inspect the retained receipt') from error
