# Modeless Family Browser (fork notes)

This fork keeps the Family Browser window open while you work in Revit, so it
can live on a second monitor.

## Why upstream locks Revit

Upstream opens the browser with `ShowDialog()`, a modal WPF window, which
blocks its owner (Revit) until it closes. Placing a family closed the window,
ran `PromptForFamilyInstancePlacement`, then rebuilt and reopened the window.

## What changed

| Area | Change |
|------|--------|
| `FamilyBrowser.pushbutton/script.py` | `__persistentengine__ = True`; `win.Show()` instead of the `ShowDialog()` reopen loop; teardown moved to a `Closed` handler; settings block at the top of the file |
| `lib/revit_bridge.py` (new) | One `ExternalEvent` plus a work queue. Every Revit API call from the window goes through it |
| Placement | Queued through the bridge; the window stays open. A second click while Revit is still waiting for a placement shows a "busy" status instead of queueing |
| Load selected | The batch `LoadFamily` transaction runs through the bridge |
| Right-click properties | Opening the `.rfa` with `OpenDocumentFile` runs through the bridge (cached metadata still shows instantly) |
| Active project | Each action re-reads `ActiveUIDocument`, so switching projects while the browser is open works |
| Second click on the ribbon button | Brings the open browser forward instead of opening a duplicate |
| `lib/i18n.py` | Four new status strings (EN/RU) |
| Tests | `test_revit_bridge.py` (queue/dispose behaviour with the API stubbed); one structural test updated for the modeless design |

Upstream's reopen helpers (`_restore_ui_after_reopen`, pending-placement
fields) are left in place but unused, to keep merges from upstream easy.

## Settings (top of `script.py`)

- `REUSE_OPEN_WINDOW` — second ribbon click focuses the open browser.
- `FOCUS_BROWSER_AFTER_LOAD` — raise the browser after "Load selected".
- `PLACEMENT_MODE` — `"prompt"` (upstream behaviour, reports placed/cancelled)
  or `"post"` (`PostRequestForElementTypePlacement`: hands off to Revit's own
  placement command and frees the browser immediately).

## Test checklist in Revit

Nothing here could be run inside Revit when the fork was made; unit tests and
the repo's `scripts/check.py` pass on CPython only.

1. Open the browser, move it to the second monitor, and check you can select,
   pan and edit in Revit while it is open.
2. Left-click a family: it should attach to the cursor in the active view.
   If it only does so after you click into the view, try `PLACEMENT_MODE = "post"`.
3. Press Esc to finish placing, then place a different family without
   reopening the browser.
4. Click a second family while still placing the first: expect the "busy"
   status, no error.
5. Load selected (several families), then check Undo shows one AVRO transaction.
6. Right-click a family not yet inspected: the properties panel fills in.
7. Switch to another open project and place/load there.
8. Close the browser in the middle of a placement; finish the placement; reopen.
9. Click the ribbon button while the browser is open: it should come forward.
10. Upstream's ADR 0002 asks for 20+ open/close cycles with previews loading.
    Do that before relying on it day to day.
