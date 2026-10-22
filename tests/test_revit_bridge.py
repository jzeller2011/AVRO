# -*- coding: utf-8 -*-
"""Queue semantics of lib/revit_bridge.py, with the Revit API stubbed out."""
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)


class _FakeEvent(object):
    def __init__(self, handler):
        self.handler = handler
        self.raised = 0
        self.disposed = False

    def Raise(self):
        self.raised += 1

    def Dispose(self):
        self.disposed = True


def _install_stubs():
    clr = types.ModuleType("clr")
    clr.AddReference = lambda name: None
    ui = types.ModuleType("Autodesk.Revit.UI")
    ui.IExternalEventHandler = object
    ui.ExternalEvent = types.SimpleNamespace(Create=_FakeEvent)
    sys.modules.setdefault("clr", clr)
    sys.modules["Autodesk"] = types.ModuleType("Autodesk")
    sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
    sys.modules["Autodesk.Revit.UI"] = ui


_install_stubs()
import revit_bridge  # noqa: E402


class RevitBridgeTests(unittest.TestCase):
    def _bridge(self):
        bridge = revit_bridge.RevitBridge(u"test")
        return bridge, bridge._event

    def test_queued_work_runs_in_order_with_uiapp(self):
        bridge, event = self._bridge()
        seen = []
        bridge.run(lambda app: seen.append(("a", app)) or 1,
                   lambda result, error: seen.append(("done", result, error)))
        bridge.run(lambda app: seen.append(("b", app)))
        self.assertTrue(bridge.busy)
        event.handler.Execute("uiapp")
        self.assertEqual(seen, [("a", "uiapp"), ("done", 1, None), ("b", "uiapp")])
        self.assertFalse(bridge.busy)

    def test_errors_reach_on_done_and_do_not_stop_the_queue(self):
        bridge, event = self._bridge()
        results = []

        def boom(app):
            raise ValueError("nope")

        bridge.run(boom, lambda result, error: results.append(error))
        bridge.run(lambda app: "ok", lambda result, error: results.append(result))
        event.handler.Execute(None)
        self.assertIsInstance(results[0], ValueError)
        self.assertEqual(results[1], "ok")

    def test_dispose_while_idle_releases_event_and_rejects_work(self):
        bridge, event = self._bridge()
        bridge.dispose()
        self.assertTrue(event.disposed)
        self.assertFalse(bridge.run(lambda app: None))

    def test_dispose_during_work_defers_release_and_drops_queue(self):
        bridge, event = self._bridge()
        ran = []

        def first(app):
            bridge.dispose()          # e.g. window closed mid-placement
            self.assertFalse(event.disposed)
            ran.append("first")

        bridge.run(first)
        bridge.run(lambda app: ran.append("second"))
        event.handler.Execute(None)
        self.assertEqual(ran, ["first"])
        self.assertTrue(event.disposed)


if __name__ == "__main__":
    unittest.main()
