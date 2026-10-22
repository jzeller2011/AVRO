# -*- coding: utf-8 -*-
"""
Type picker for families that ship a type catalog.

A small modeless window owned by the Family Browser. It shows the catalog's
types and parameter values from the .txt file alone (no Revit API), lets the
user Ctrl/Shift-select several, then hands the chosen names back to the
browser, which loads only those types through its Revit bridge.
"""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Data")

import System
from System.Data import DataTable
from System.Windows import Visibility
from System.Windows.Controls import (
    DataGridLength, DataGridRow, DataGridTextColumn, ItemsControl,
)
from System.Windows.Data import Binding
from System.Windows.Input import Key

import avro_log
import i18n
import type_catalog
import ui_theme
import ui_utils
from revit_utils import as_unicode

_CONTROL_NAMES = (
    "FamilyTitle", "PickerHint", "FilterBox", "FilterHint", "TypeGrid",
    "PickerStatus", "BtnLoadTypes", "BtnPlaceType", "BtnCancelTypes",
)


def escape_like(text):
    """Escape text for a DataView.RowFilter ``LIKE '%...%'`` pattern."""
    out = []
    for ch in as_unicode(text):
        if ch in u"[]*%":
            out.append(u"[" + ch + u"]")
        elif ch == u"'":
            out.append(u"''")
        else:
            out.append(ch)
    return u"".join(out)


class TypePicker(object):
    """One picker window for one family.

    ``on_submit(names, place)`` is called with the selected type names in
    catalog order; ``place`` is True for "Load & place".
    """

    def __init__(self, owner, xaml_dir, fi, catalog, palette, on_submit,
                 keep_open=False):
        self.fi = fi
        self.catalog = catalog
        self.on_submit = on_submit
        self.keep_open = keep_open
        self.win = ui_utils.load_xaml(xaml_dir, "type_picker.xaml")
        self.ui = ui_utils.NamedUiControls(self.win, _CONTROL_NAMES)
        try:
            self.win.Owner = owner
        except Exception:
            pass
        ui_theme.apply_window_theme(self.win, palette)
        self._table = None
        self._closed = False
        self._build_table()
        self._apply_texts()
        self._bind()

    # -- setup -------------------------------------------------------------

    def _apply_texts(self):
        name = as_unicode(getattr(self.fi, "name", u""))
        self.win.Title = i18n.t("picker_title", name=name)
        self.ui.FamilyTitle.Text = name
        self.ui.PickerHint.Text = i18n.t("picker_hint")
        self.ui.FilterHint.Text = i18n.t("picker_filter")
        self.ui.BtnLoadTypes.Content = i18n.t("picker_btn_load")
        self.ui.BtnPlaceType.Content = i18n.t("picker_btn_place")
        self.ui.BtnCancelTypes.Content = i18n.t("picker_btn_cancel")
        self._update_counts()

    def _build_table(self):
        table = DataTable("Types")
        table.Columns.Add("Idx", System.Int32)
        table.Columns.Add("Type", System.String)
        # Catalog headers can contain characters that break binding paths,
        # so data columns get neutral names and the header text is set below.
        for i in range(len(self.catalog.columns)):
            table.Columns.Add("c{}".format(i), System.String)
        for idx, (name, values) in enumerate(self.catalog.rows):
            row = table.NewRow()
            row["Idx"] = idx
            row["Type"] = name
            for i, value in enumerate(values):
                row["c{}".format(i)] = value
            table.Rows.Add(row)
        self._table = table

        grid = self.ui.TypeGrid
        grid.Columns.Clear()
        type_col = DataGridTextColumn()
        type_col.Header = i18n.t("picker_col_type")
        type_col.Binding = Binding("Type")
        type_col.MinWidth = 120
        grid.Columns.Add(type_col)
        for i, column in enumerate(self.catalog.columns):
            col = DataGridTextColumn()
            col.Header = type_catalog.column_header(column)
            col.Binding = Binding("c{}".format(i))
            col.Width = DataGridLength.Auto
            grid.Columns.Add(col)
        grid.ItemsSource = table.DefaultView

    def _bind(self):
        self.ui.FilterBox.TextChanged += self._on_filter
        self.ui.TypeGrid.SelectionChanged += self._on_selection
        self.ui.TypeGrid.MouseDoubleClick += self._on_double_click
        self.ui.BtnLoadTypes.Click += self._on_load
        self.ui.BtnPlaceType.Click += self._on_place
        self.ui.BtnCancelTypes.Click += self._on_cancel
        self.win.PreviewKeyDown += self._on_key
        self.win.Closed += self._on_closed

    # -- public ------------------------------------------------------------

    def show(self):
        self.win.Show()
        if len(self.catalog) == 1:
            self.ui.TypeGrid.SelectAll()
        self.ui.FilterBox.Focus()

    def close(self):
        if not self._closed:
            try:
                self.win.Close()
            except Exception:
                pass

    @property
    def is_open(self):
        return not self._closed

    def set_status(self, text):
        if not self._closed:
            self.ui.PickerStatus.Text = as_unicode(text or u"")

    # -- handlers ----------------------------------------------------------

    def _selected_names(self):
        picked = []
        for item in self.ui.TypeGrid.SelectedItems:
            try:
                picked.append((int(item["Idx"]), as_unicode(item["Type"])))
            except Exception:
                continue
        picked.sort()
        return [name for _idx, name in picked]

    def _visible_count(self):
        try:
            return self._table.DefaultView.Count
        except Exception:
            return len(self.catalog)

    def _update_counts(self):
        selected = len(self._selected_names())
        self.ui.PickerStatus.Text = i18n.t(
            "picker_counts", shown=self._visible_count(),
            total=len(self.catalog), selected=selected)
        enabled = selected > 0
        self.ui.BtnLoadTypes.IsEnabled = enabled
        self.ui.BtnPlaceType.IsEnabled = enabled

    def _on_filter(self, sender, e):
        text = as_unicode(self.ui.FilterBox.Text).strip()
        self.ui.FilterHint.Visibility = (
            Visibility.Collapsed if text else Visibility.Visible)
        view = self._table.DefaultView
        if not text:
            view.RowFilter = u""
        else:
            pattern = escape_like(text)
            names = [u"Type"] + [
                u"c{}".format(i) for i in range(len(self.catalog.columns))]
            view.RowFilter = u" OR ".join(
                u"[{}] LIKE '%{}%'".format(n, pattern) for n in names)
        self._update_counts()

    def _on_selection(self, sender, e):
        self._update_counts()

    def _on_double_click(self, sender, e):
        # Only rows count; ignore double-clicks on headers and scrollbars.
        grid = self.ui.TypeGrid
        try:
            row = ItemsControl.ContainerFromElement(grid, e.OriginalSource)
        except Exception:
            row = None
        if not isinstance(row, DataGridRow) or row.Item is None:
            return
        try:
            name = as_unicode(row.Item["Type"])
        except Exception:
            return
        self._submit([name], place=True)

    def _on_load(self, sender, e):
        self._submit(self._selected_names(), place=False)

    def _on_place(self, sender, e):
        self._submit(self._selected_names(), place=True)

    def _on_cancel(self, sender, e):
        self.close()

    def _on_key(self, sender, e):
        if e.Key == Key.Escape:
            e.Handled = True
            self.close()
        elif e.Key == Key.Return:
            e.Handled = True
            self._submit(self._selected_names(), place=True)
        elif e.Key == Key.Down and self.ui.FilterBox.IsKeyboardFocused:
            # Arrow down from the filter moves into the list.
            grid = self.ui.TypeGrid
            if grid.Items.Count:
                if grid.SelectedIndex < 0:
                    grid.SelectedIndex = 0
                grid.Focus()
                e.Handled = True

    def _submit(self, names, place):
        if not names:
            self.set_status(i18n.t("picker_select_first"))
            return
        try:
            accepted = self.on_submit(names, place)
        except Exception as ex:
            avro_log.exception("type_picker.submit", ex)
            self.set_status(i18n.t("error_generic", err=as_unicode(ex)))
            return
        if accepted and not self.keep_open:
            self.close()

    def _on_closed(self, sender, e):
        self._closed = True
        try:
            self.ui.FilterBox.TextChanged -= self._on_filter
            self.ui.TypeGrid.SelectionChanged -= self._on_selection
            self.ui.TypeGrid.MouseDoubleClick -= self._on_double_click
            self.ui.BtnLoadTypes.Click -= self._on_load
            self.ui.BtnPlaceType.Click -= self._on_place
            self.ui.BtnCancelTypes.Click -= self._on_cancel
            self.win.PreviewKeyDown -= self._on_key
            self.win.Closed -= self._on_closed
        except Exception:
            pass
