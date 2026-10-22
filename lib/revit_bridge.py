# -*- coding: utf-8 -*-
"""
Run Revit API work requested by a modeless WPF window.

A modeless window's event handlers run outside Revit's API context, so they
must not open transactions, collect elements or prompt for placement
directly. They queue a callable here instead; Revit calls ``Execute`` on its
main thread when it is next idle, and the callable receives the live
``UIApplication``.

Usage::

    bridge = RevitBridge(u"AVRO: Family Browser")   # create in API context
    bridge.run(lambda uiapp: do_work(uiapp),
               on_done=lambda result, error: update_ui(result, error))
    ...
    bridge.dispose()                                  # when the window closes

``on_done`` runs right after the work, still on Revit's main thread, which is
also the WPF window's thread, so it may touch UI controls.
"""
import threading

import clr
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

import avro_log


class _BridgeHandler(IExternalEventHandler):
    def __init__(self, bridge):
        self._bridge = bridge

    def Execute(self, uiapp):
        self._bridge._drain(uiapp)

    def GetName(self):
        return self._bridge.name


class RevitBridge(object):
    """Queue of callables executed by one ExternalEvent."""

    def __init__(self, name):
        self.name = name
        self._lock = threading.Lock()
        self._queue = []
        self._running = False
        self._disposed = False
        self._handler = _BridgeHandler(self)
        # ExternalEvent.Create must be called while Revit is in API context
        # (for example while a pyRevit button script is executing).
        self._event = ExternalEvent.Create(self._handler)

    @property
    def busy(self):
        """True while work is queued or executing."""
        with self._lock:
            return self._running or bool(self._queue)

    def run(self, work, on_done=None):
        """Queue ``work(uiapp)``; return False if the bridge is disposed."""
        with self._lock:
            if self._disposed:
                return False
            self._queue.append((work, on_done))
        event = self._event
        if event is None:
            return False
        try:
            # Raise() on an already-pending event is a no-op; _drain empties
            # the whole queue, so no request is lost.
            event.Raise()
        except Exception as ex:
            avro_log.exception("revit_bridge.raise", ex)
            return False
        return True

    def _drain(self, uiapp):
        while True:
            with self._lock:
                if not self._queue:
                    self._running = False
                    dispose_now = self._disposed
                    break
                work, on_done = self._queue.pop(0)
                self._running = True
            result, error = None, None
            try:
                result = work(uiapp)
            except Exception as ex:
                error = ex
                avro_log.exception("revit_bridge.work", ex)
            if on_done is not None:
                try:
                    on_done(result, error)
                except Exception as ex:
                    avro_log.exception("revit_bridge.on_done", ex)
        if dispose_now:
            # dispose() was called while this handler was executing.
            self._dispose_event()

    def dispose(self):
        """Drop queued work and release the ExternalEvent.

        If work is executing right now (for example the window was closed
        during a placement prompt), the event is released when it returns.
        """
        with self._lock:
            self._disposed = True
            self._queue = []
            running = self._running
        if not running:
            self._dispose_event()

    def _dispose_event(self):
        event = self._event
        self._event = None
        if event is None:
            return
        try:
            event.Dispose()
        except Exception as ex:
            avro_log.exception("revit_bridge.dispose", ex)
