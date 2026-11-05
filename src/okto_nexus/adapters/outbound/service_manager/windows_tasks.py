"""Thread-scoped Task Scheduler adapter; no task changes during inspection."""
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
        return self.state in {2, 4}


class WindowsTasks:
    def _call(self, operation):
        import pythoncom
        import pywintypes
        import win32com.client
        # Return only plain data. COM objects and exception frames must be
        # released before balancing initialization on this calling thread.
        pythoncom.CoInitialize()
        service = folder = None
        result = failure = None
        try:
            service = win32com.client.Dispatch('Schedule.Service')
            service.Connect()
            folder = service.GetFolder('\\')
            result = operation(folder)
        except TaskConflict as error:
            failure = TaskConflict(str(error))
        except ValueError:
            failure = TaskConflict('The native definition cannot be safely compared; it was preserved')
        except pywintypes.com_error:
            failure = OSError('Task Scheduler did not confirm the selected operation')
        finally:
            folder = service = None
            pythoncom.CoUninitialize()
        if failure:
            raise failure
        return result

    def _task(self, folder, name):
        import pywintypes
        try:
            return folder.GetTask(name)
        except pywintypes.com_error as error:
            if -2147024894 in {error.hresult, error.excepinfo[5] if error.excepinfo else None}:
                return None
            raise

    def _observation(self, task):
        return None if task is None else TaskObservation(
            task.Xml, int(task.State), bool(task.Enabled), int(task.LastTaskResult))

    def read(self, name):
        return self._call(lambda folder: self._observation(self._task(folder, name)))

    def validate(self, name, xml):
        def operation(folder):
            folder.RegisterTask(name, xml, 1, None, None, 3, None)
        self._call(operation)

    def create(self, name, xml):
        return self._call(lambda folder: self._observation(
            folder.RegisterTask(name, xml, 2, None, None, 3, None)))

    def _matching(self, folder, name, expected):
        task = self._task(folder, name)
        if task is None or windows_definition_digest(task.Xml) != expected:
            raise TaskConflict('The task definition changed; reconcile it before mutation')
        return task

    def start(self, name, expected):
        def operation(folder):
            self._matching(folder, name, expected).Run(None)
        self._call(operation)

    def set_enabled(self, name, expected, enabled):
        if type(enabled) is not bool:
            raise ValueError('Enablement must be boolean')
        def operation(folder):
            task = self._matching(folder, name, expected)
            task.Enabled = enabled
            return self._observation(task)
        return self._call(operation)

    def delete(self, name, expected):
        def operation(folder):
            task = self._matching(folder, name, expected)
            if int(task.State) in {0, 2, 4}:
                raise TaskConflict('The selected task is still active or unconfirmed')
            folder.DeleteTask(name, 0)
        self._call(operation)
