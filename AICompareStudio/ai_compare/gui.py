"""PySide6 desktop GUI – black / grey / gold theme."""
from __future__ import annotations

import html
import os
import sys
import tempfile
import traceback

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, QSettings, QSortFilterProxyModel, Qt,
                            QThread, QUrl, Signal)
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QSpinBox, QSplitter, QStatusBar, QTableView, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import __version__
from .ai_agent import DEFAULT_MODEL, MODEL_CHOICES, AgentConfig
from .comparator import compare_files
from .models import CompareResult
from .parsers import FILE_DIALOG_FILTER
from .report import intraline, save_html

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # optional
except Exception:  # pragma: no cover
    QWebEngineView = None

GOLD = "#d4af37"
GOLD2 = "#f3d27a"
IMPACT_COLORS = {"High": "#e0544e", "Medium": "#e3a33b", "Low": "#6fa8dc", "Info": "#8d8d95"}
CHANGE_COLORS = {"Added": "#3fae6a", "Removed": "#d9534f", "Modified": GOLD2, "Renamed": "#5b9bd5"}

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Roboto", sans-serif; font-size: 13px; }}
QMainWindow, QWidget {{ background: #0d0d0f; color: #e6e6e6; }}
QLabel, QCheckBox {{ background: transparent; }}
QLabel#Title {{ color: {GOLD}; font-size: 22px; font-weight: 700; letter-spacing: 2px; }}
QLabel#Subtitle {{ color: #9a9aa2; font-size: 12px; }}
QLabel#Section {{ color: {GOLD}; font-weight: 600; font-size: 12px; letter-spacing: 1px; }}
QFrame#Header {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #18181b, stop:0.7 #111113, stop:1 #241f0f);
                 border-bottom: 1px solid #3a3420; }}
QFrame#Panel, QGroupBox {{ background: #17171a; border: 1px solid #2c2c31; border-radius: 10px; }}
QGroupBox {{ margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {GOLD}; font-weight: 600; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser {{
    background: #1f1f23; border: 1px solid #2f2f35; border-radius: 6px; padding: 6px 8px; color: #e6e6e6;
    selection-background-color: #8a7426; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {GOLD}; }}
QLineEdit#Drop {{ border: 1px dashed #5a4e22; padding: 10px; }}
QComboBox QAbstractItemView {{ background: #1f1f23; selection-background-color: #3a3420; color: #e6e6e6; }}
QPushButton {{ background: #26262b; border: 1px solid #3a3a41; border-radius: 6px; padding: 7px 14px; color: #e6e6e6; }}
QPushButton:hover {{ border-color: {GOLD}; color: {GOLD2}; }}
QPushButton:disabled {{ color: #5d5d63; border-color: #2a2a2e; }}
QPushButton#Primary {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f3d27a, stop:1 #b8932a);
    color: #111; font-weight: 700; font-size: 15px; letter-spacing: 2px; border: 1px solid #f3d27a; padding: 11px; }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffe39a, stop:1 #d4af37); color:#000; }}
QPushButton#Primary:disabled {{ background: #3a3420; color: #777; border-color: #3a3420; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #555; border-radius: 3px; background: #1f1f23; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; }}
QTabWidget::pane {{ border: 1px solid #2c2c31; border-radius: 8px; background: #141417; top: -1px; }}
QTabBar::tab {{ background: #17171a; color: #9a9aa2; padding: 8px 16px; border: 1px solid #2c2c31;
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #141417; color: {GOLD2}; border-color: #5a4e22; }}
QTableView, QTableWidget {{ background: #141417; alternate-background-color: #18181c; gridline-color: #26262b;
    border: none; selection-background-color: #3a3420; selection-color: #fff; }}
QHeaderView::section {{ background: #0f0f11; color: {GOLD}; padding: 7px; border: none;
    border-bottom: 2px solid #8a7426; font-weight: 600; }}
QProgressBar {{ background: #1f1f23; border: 1px solid #2c2c31; border-radius: 6px; text-align: center; color: #ddd; height: 18px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8a7426, stop:1 #f3d27a); border-radius: 5px; }}
QScrollBar:vertical {{ background: #111; width: 11px; }} QScrollBar::handle:vertical {{ background: #3a3a41; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #8a7426; }}
QScrollBar:horizontal {{ background: #111; height: 11px; }} QScrollBar::handle:horizontal {{ background: #3a3a41; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: #0a0a0b; color: #9a9aa2; border-top: 1px solid #2c2c31; }}
QSplitter::handle {{ background: #1a1a1d; }}
QToolTip {{ background: #1f1f23; color: #eee; border: 1px solid {GOLD}; }}
"""


def app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#111"))
    p.setPen(QColor(GOLD))
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor(GOLD2))
    f = QFont("Segoe UI", 22, QFont.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "⇄")
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
class DropLineEdit(QLineEdit):
    def __init__(self, placeholder: str):
        super().__init__()
        self.setObjectName("Drop")
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


class DiffTableModel(QAbstractTableModel):
    COLS = ["#", "Impact", "Change", "Element", "Description", "Reference value", "Target value", "Category", "Location"]

    def __init__(self):
        super().__init__()
        self.items = []

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and o == Qt.Horizontal:
            return self.COLS[s]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        it = self.items[idx.row()]
        c = idx.column()
        vals = [it.id, it.impact, it.change_type, it.element, (("✦ " if it.ai_described else "") + it.description),
                it.ref_value, it.tgt_value, it.category, it.location]
        if role == Qt.DisplayRole:
            v = vals[c]
            if isinstance(v, str) and len(v) > 300:
                v = v[:299] + "…"
            return v
        if role == Qt.UserRole:          # sort key
            if c == 1:
                return {"High": 0, "Medium": 1, "Low": 2, "Info": 3}.get(it.impact, 9)
            return vals[c]
        if role == Qt.ToolTipRole and c >= 3:
            return str(vals[c])[:2000] + "\n\n(double-click for details)"
        if role == Qt.ForegroundRole:
            if c == 1:
                return QBrush(QColor(IMPACT_COLORS.get(it.impact, "#ccc")))
            if c == 2:
                return QBrush(QColor(CHANGE_COLORS.get(it.change_type, "#ccc")))
            if c == 3:
                return QBrush(QColor(GOLD2))
            if c == 5 and it.ref_value:
                return QBrush(QColor("#ffb3b0"))
            if c == 6 and it.tgt_value:
                return QBrush(QColor("#a8f0c4"))
            if c == 8:
                return QBrush(QColor("#9a9aa2"))
        if role == Qt.FontRole and c in (1, 2, 3):
            f = QFont()
            f.setBold(True)
            return f
        return None


class DiffFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.impact = self.change = self.category = "All"
        self.setSortRole(Qt.UserRole)

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        it = self.sourceModel().items[row]
        if self.impact != "All" and it.impact != self.impact:
            return False
        if self.change != "All" and it.change_type != self.change:
            return False
        if self.category != "All" and it.category != self.category:
            return False
        if self.text:
            blob = " ".join([it.location, it.element, it.ref_value, it.tgt_value, it.description]).lower()
            return self.text.lower() in blob
        return True


class DetailDialog(QDialog):
    def __init__(self, it, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Difference #{it.id}")
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        rv, tv = (intraline(it.ref_value, it.tgt_value) if it.ref_value and it.tgt_value
                  else (html.escape(it.ref_value), html.escape(it.tgt_value)))
        hunk = ""
        if it.details:
            lines = []
            for ln in it.details.splitlines():
                color = "#a8f0c4" if ln.startswith("+") else "#ffb3b0" if ln.startswith("-") else \
                        GOLD if ln.startswith("@@") else "#bbb"
                lines.append(f"<span style='color:{color}'>{html.escape(ln)}</span>")
            hunk = ("<h3 style='color:%s'>Code diff</h3><pre style='background:#0a0a0b;padding:8px'>%s</pre>"
                    % (GOLD, "<br>".join(lines)))
        tb.setHtml(f"""<div style='color:#e6e6e6'>
            <h2 style='color:{GOLD}'>{html.escape(it.change_type)} · {html.escape(it.category)}
            <span style='color:{IMPACT_COLORS.get(it.impact)}'> [{html.escape(it.impact)} impact]</span></h2>
            <p><b style='color:{GOLD2}'>Element:</b> {html.escape(it.element)}<br>
            <b style='color:{GOLD2}'>Location:</b> {html.escape(it.location)}</p>
            <h3 style='color:{GOLD}'>Description {'(AI)' if it.ai_described else ''}</h3><p>{html.escape(it.description)}</p>
            <table width='100%' cellspacing='0' cellpadding='8' style='border:1px solid #333'>
            <tr><th style='color:{GOLD};text-align:left'>Reference</th><th style='color:{GOLD};text-align:left'>Target</th></tr>
            <tr><td style='font-family:Consolas,monospace;white-space:pre-wrap;background:#1a1212' valign='top'>{rv.replace('<del>', "<span style='background:#5a2523;color:#ffb3b0'>").replace('</del>', '</span>')}</td>
            <td style='font-family:Consolas,monospace;white-space:pre-wrap;background:#121a14' valign='top'>{tv.replace('<ins>', "<span style='background:#1f4a2f;color:#a8f0c4'>").replace('</ins>', '</span>')}</td></tr></table>
            {hunk}</div>""")
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


# --------------------------------------------------------------------------- #
# Worker thread
# --------------------------------------------------------------------------- #
class Worker(QObject):
    log = Signal(str)
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, ref, tgt, cfg):
        super().__init__()
        self.ref, self.tgt, self.cfg = ref, tgt, cfg

    def run(self):
        try:
            res = compare_files(self.ref, self.tgt, self.cfg, log=self.log.emit,
                                progress=lambda p, m: self.progress.emit(p, m))
            self.finished.emit(res)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AI Compare Studio {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1500, 920)
        self.settings = QSettings("AICompareStudio", "AICompareStudio")
        self.result: CompareResult | None = None
        self.thread: QThread | None = None
        self._preview_file = None

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._header())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._left_panel())
        split.addWidget(self._right_panel())
        split.setStretchFactor(1, 1)
        split.setSizes([380, 1120])
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 12, 12, 8)
        bl.addWidget(split)
        v.addWidget(body, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Select a reference and a target file, then press COMPARE.")
        self.setAcceptDrops(True)
        self._load_settings()

        act = QAction("Compare", self)
        act.setShortcut("Ctrl+Return")
        act.triggered.connect(self.start_compare)
        self.addAction(act)

    # ------------------------------------------------------------------ layout
    def _header(self):
        h = QFrame()
        h.setObjectName("Header")
        h.setFixedHeight(66)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 6, 20, 6)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(40, 40))
        lay.addWidget(icon)
        col = QVBoxLayout()
        t = QLabel("AI COMPARE STUDIO")
        t.setObjectName("Title")
        s = QLabel("Agent-driven comparison · ARXML · C / C++ / H · Excel · Word · PDF · Notes")
        s.setObjectName("Subtitle")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col)
        lay.addStretch(1)
        self.ai_state = QLabel("")
        self.ai_state.setObjectName("Subtitle")
        lay.addWidget(self.ai_state)
        return h

    def _left_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)

        files = QGroupBox("Files")
        g = QGridLayout(files)
        self.ref_edit = DropLineEdit("Drop or browse the REFERENCE file (baseline)…")
        self.tgt_edit = DropLineEdit("Drop or browse the TARGET file (new version)…")
        for row, (label, edit) in enumerate((("Reference", self.ref_edit), ("Target", self.tgt_edit))):
            lab = QLabel(label.upper())
            lab.setObjectName("Section")
            g.addWidget(lab, row * 2, 0, 1, 2)
            g.addWidget(edit, row * 2 + 1, 0)
            b = QPushButton("Browse")
            b.clicked.connect(lambda _=False, e=edit: self.browse(e))
            g.addWidget(b, row * 2 + 1, 1)
        swap = QPushButton("⇅  Swap reference / target")
        swap.clicked.connect(self.swap)
        g.addWidget(swap, 4, 0, 1, 2)
        lay.addWidget(files)

        ai = QGroupBox("AI Agent")
        f = QGridLayout(ai)
        self.ai_enable = QCheckBox("Enable AI agent (Claude)")
        self.ai_enable.setChecked(True)
        f.addWidget(self.ai_enable, 0, 0, 1, 2)
        f.addWidget(QLabel("Model"), 1, 0)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(MODEL_CHOICES)
        f.addWidget(self.model, 1, 1)
        f.addWidget(QLabel("Effort"), 2, 0)
        self.effort = QComboBox()
        self.effort.addItems(["low", "medium", "high", "xhigh", "max"])
        self.effort.setCurrentText("medium")
        f.addWidget(self.effort, 2, 1)
        f.addWidget(QLabel("API key"), 3, 0)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("uses ANTHROPIC_API_KEY if empty")
        f.addWidget(self.api_key, 3, 1)
        self.remember_key = QCheckBox("Remember key on this PC")
        f.addWidget(self.remember_key, 4, 1)
        f.addWidget(QLabel("AI-described items"), 5, 0)
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 5000)
        self.max_items.setValue(400)
        self.max_items.setToolTip("Maximum number of differences the agent rewrites (highest impact first).")
        f.addWidget(self.max_items, 5, 1)
        lay.addWidget(ai)

        self.compare_btn = QPushButton("COMPARE")
        self.compare_btn.setObjectName("Primary")
        self.compare_btn.clicked.connect(self.start_compare)
        lay.addWidget(self.compare_btn)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        lay.addWidget(self.progress)
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("Subtitle")
        lay.addWidget(self.progress_label)

        row = QHBoxLayout()
        self.export_btn = QPushButton("💾  Export HTML")
        self.export_btn.clicked.connect(self.export_html)
        self.open_btn = QPushButton("🌐  Open in browser")
        self.open_btn.clicked.connect(self.open_browser)
        for b in (self.export_btn, self.open_btn):
            b.setEnabled(False)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)
        hint = QLabel("Tip: drag files anywhere onto the window.\nCtrl+Enter starts the comparison.")
        hint.setObjectName("Subtitle")
        lay.addWidget(hint)
        return w

    def _right_panel(self):
        self.tabs = QTabWidget()
        # summary
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(True)
        self.summary.setHtml(self._welcome_html())
        self.tabs.addTab(self.summary, "★  Summary")
        # differences
        dw = QWidget()
        dl = QVBoxLayout(dw)
        fl = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Search differences…")
        self.f_impact = QComboBox()
        self.f_impact.addItems(["All", "High", "Medium", "Low", "Info"])
        self.f_change = QComboBox()
        self.f_change.addItems(["All", "Added", "Removed", "Modified", "Renamed"])
        self.f_cat = QComboBox()
        self.f_cat.addItems(["All"])
        fl.addWidget(self.search, 1)
        for lab, cb in (("Impact", self.f_impact), ("Change", self.f_change), ("Category", self.f_cat)):
            fl.addWidget(QLabel(lab))
            fl.addWidget(cb)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Subtitle")
        fl.addWidget(self.count_label)
        dl.addLayout(fl)
        self.model_diff = DiffTableModel()
        self.proxy = DiffFilter()
        self.proxy.setSourceModel(self.model_diff)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, wdt in enumerate([42, 68, 80, 190, 400, 150, 150, 80]):
            self.table.setColumnWidth(i, wdt)
        self.table.doubleClicked.connect(self.show_detail)
        dl.addWidget(self.table)
        self.search.textChanged.connect(lambda t: self._filter(text=t))
        self.f_impact.currentTextChanged.connect(lambda t: self._filter(impact=t))
        self.f_change.currentTextChanged.connect(lambda t: self._filter(change=t))
        self.f_cat.currentTextChanged.connect(lambda t: self._filter(category=t))
        self.tabs.addTab(dw, "≠  Differences")
        # mapping
        self.map_table = QTableWidget(0, 7)
        self.map_table.setHorizontalHeaderLabels(["Table", "Reference column", "Meaning (understood)",
                                                  "Target column", "Match", "Confidence", "Note"])
        self.map_table.horizontalHeader().setStretchLastSection(True)
        self.map_table.setAlternatingRowColors(True)
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.map_table, "⇆  Column Mapping")
        # side by side
        self.sbs = QTextBrowser()
        self.tabs.addTab(self.sbs, "▤  Line View")
        # report preview
        self.preview = None
        if QWebEngineView is not None and os.environ.get("AICS_NO_WEBENGINE") != "1":
            try:
                self.preview = QWebEngineView()
                self.tabs.addTab(self.preview, "◎  HTML Report")
            except Exception:
                self.preview = None
        # log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.log_view, "🤖  Agent Log")
        return self.tabs

    def _welcome_html(self):
        return f"""<div style='color:#cfcfd4;padding:20px'>
        <h1 style='color:{GOLD}'>Welcome to AI Compare Studio</h1>
        <p style='font-size:14px'>1. Choose the <b style='color:{GOLD2}'>reference</b> file (baseline) and the
        <b style='color:{GOLD2}'>target</b> file (new version).<br>2. Press <b style='color:{GOLD2}'>COMPARE</b>.
        <br>3. Review the summary, the differences table and export the HTML report.</p>
        <h3 style='color:{GOLD}'>What the AI agent does</h3>
        <ul><li>Reads the reference file's column headings and infers what each column <i>means</i>.</li>
        <li>Finds the same column in the target file – even if it was renamed or moved.</li>
        <li>Picks the key column (e.g. signal name) so rows are compared by identity, not by position.</li>
        <li>Explains every difference in plain language with an impact rating.</li>
        <li>Writes an executive summary with key findings.</li></ul>
        <h3 style='color:{GOLD}'>Supported formats</h3>
        <p>AUTOSAR <b>.arxml</b> · <b>.c .h .cpp .hpp</b> · Excel <b>.xlsx .xls .csv</b> · Word <b>.docx</b> ·
        <b>.pdf</b> · notes <b>.txt .md .log .ini .json .xml</b></p>
        <p style='color:#8d8d95'>Without an API key the tool still works using its built-in rule-based engine.</p></div>"""

    # ------------------------------------------------------------------ settings
    def _load_settings(self):
        s = self.settings
        self.model.setCurrentText(s.value("model", DEFAULT_MODEL))
        self.effort.setCurrentText(s.value("effort", "medium"))
        self.ai_enable.setChecked(s.value("ai_enabled", True, type=bool))
        self.max_items.setValue(int(s.value("max_items", 400)))
        key = s.value("api_key", "")
        if key:
            self.api_key.setText(key)
            self.remember_key.setChecked(True)
        self.ref_edit.setText(s.value("last_ref", ""))
        self.tgt_edit.setText(s.value("last_tgt", ""))
        self._update_ai_state()
        self.ai_enable.toggled.connect(self._update_ai_state)
        self.api_key.textChanged.connect(self._update_ai_state)

    def _save_settings(self):
        s = self.settings
        s.setValue("model", self.model.currentText())
        s.setValue("effort", self.effort.currentText())
        s.setValue("ai_enabled", self.ai_enable.isChecked())
        s.setValue("max_items", self.max_items.value())
        s.setValue("api_key", self.api_key.text() if self.remember_key.isChecked() else "")
        s.setValue("last_ref", self.ref_edit.text())
        s.setValue("last_tgt", self.tgt_edit.text())

    def _update_ai_state(self, *_):
        if not self.ai_enable.isChecked():
            self.ai_state.setText("● AI agent off – rule-based mode")
        elif self.api_key.text() or os.environ.get("ANTHROPIC_API_KEY"):
            self.ai_state.setText(f"<span style='color:{GOLD}'>●</span> AI agent ready")
        else:
            self.ai_state.setText("● No API key – rule-based mode")

    # ------------------------------------------------------------------ actions
    def browse(self, edit: QLineEdit):
        start = os.path.dirname(edit.text() or self.ref_edit.text() or os.getcwd())
        path, _ = QFileDialog.getOpenFileName(self, "Select file", start, FILE_DIALOG_FILTER)
        if path:
            edit.setText(path)

    def swap(self):
        a, b = self.ref_edit.text(), self.tgt_edit.text()
        self.ref_edit.setText(b)
        self.tgt_edit.setText(a)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        if len(paths) >= 2:
            self.ref_edit.setText(paths[0])
            self.tgt_edit.setText(paths[1])
        elif paths:
            (self.tgt_edit if self.ref_edit.text() else self.ref_edit).setText(paths[0])

    def start_compare(self):
        ref, tgt = self.ref_edit.text().strip(), self.tgt_edit.text().strip()
        for label, p in (("Reference", ref), ("Target", tgt)):
            if not p or not os.path.isfile(p):
                QMessageBox.warning(self, "Missing file", f"{label} file not found:\n{p or '(empty)'}")
                return
        if self.thread is not None:
            return
        self._save_settings()
        cfg = AgentConfig(enabled=self.ai_enable.isChecked(), api_key=self.api_key.text().strip(),
                          model=self.model.currentText().strip() or DEFAULT_MODEL,
                          effort=self.effort.currentText(), max_ai_items=self.max_items.value())
        self.log_view.clear()
        self.compare_btn.setEnabled(False)
        self.compare_btn.setText("AGENT WORKING…")
        self.progress.setValue(0)
        self.tabs.setCurrentWidget(self.log_view)
        self.thread = QThread()
        self.worker = Worker(ref, tgt, cfg)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_cleanup)
        self.thread.start()

    def _thread_cleanup(self):
        self.thread.deleteLater()
        self.thread = None
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("COMPARE")

    def _on_progress(self, p, msg):
        self.progress.setValue(p)
        self.progress_label.setText(msg)
        self.status.showMessage(msg)

    def _on_fail(self, msg):
        self.progress_label.setText("Failed")
        self.log_view.appendPlainText("❌ " + msg)
        QMessageBox.critical(self, "Comparison failed", msg.split("\n\n")[0])

    def _on_done(self, res: CompareResult):
        self.result = res
        self.export_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self._fill_summary(res)
        self.model_diff.set_items(res.items)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.resizeRowsToContents()
        cats = sorted({i.category for i in res.items})
        self.f_cat.blockSignals(True)
        self.f_cat.clear()
        self.f_cat.addItems(["All"] + cats)
        self.f_cat.blockSignals(False)
        self._filter()
        self._fill_mapping(res)
        self._fill_sbs(res)
        if self.preview is not None:
            fd, path = tempfile.mkstemp(suffix=".html", prefix="aics_")
            os.close(fd)
            save_html(res, path)
            self._preview_file = path
            self.preview.setUrl(QUrl.fromLocalFile(path))
        self.tabs.setCurrentWidget(self.summary)
        self.status.showMessage(f"{len(res.items)} difference(s) · {res.elapsed_s:.1f}s · "
                                + ("AI agent" if res.ai_used else "rule-based"))

    def _filter(self, **kw):
        self.proxy.set(**kw)
        self.count_label.setText(f"{self.proxy.rowCount()} / {self.model_diff.rowCount()}")

    def show_detail(self, idx):
        it = self.model_diff.items[self.proxy.mapToSource(idx).row()]
        DetailDialog(it, self).exec()

    # ------------------------------------------------------------------ result views
    def _fill_summary(self, r: CompareResult):
        c = r.counts()
        high = sum(1 for i in r.items if i.impact == "High")
        risk_col = IMPACT_COLORS.get(r.overall_risk, "#3fae6a")

        def card(n, label, color):
            return (f"<td style='background:#17171a;border:1px solid #2c2c31;padding:10px 16px' align='center'>"
                    f"<span style='font-size:26px;font-weight:700;color:{color}'>{n}</span><br>"
                    f"<span style='color:#9a9aa2;font-size:11px'>{label}</span></td>")
        findings = "".join(f"<li style='margin:4px 0'>{html.escape(k)}</li>" for k in r.key_findings)
        summary = "".join(f"<p>{html.escape(p)}</p>" for p in r.executive_summary.split("\n") if p.strip())
        mode = (f"<span style='color:{GOLD}'>🧠 AI agent ({html.escape(r.model)})</span>" if r.ai_used
                else "<span style='color:#9a9aa2'>Rule-based analysis</span>")
        self.summary.setHtml(f"""<div style='color:#e6e6e6;padding:8px'>
        <h2 style='color:{GOLD};margin-bottom:2px'>Comparison summary</h2>
        <p style='color:#9a9aa2'>Reference: <b style='color:{GOLD2}'>{html.escape(r.reference.name)}</b> ({r.reference.file_type})
        &nbsp;→&nbsp; Target: <b style='color:{GOLD2}'>{html.escape(r.target.name)}</b> ({r.target.file_type})<br>{mode} · {r.elapsed_s:.1f}s</p>
        <table cellspacing='8'><tr>{card(len(r.items), 'TOTAL', GOLD2)}{card(c['Added'], 'ADDED', '#3fae6a')}
        {card(c['Removed'], 'REMOVED', '#d9534f')}{card(c['Modified'], 'MODIFIED', GOLD)}
        {card(c['Renamed'], 'RENAMED', '#5b9bd5')}{card(high, 'HIGH IMPACT', '#e0544e')}</tr></table>
        <h3 style='color:{GOLD}'>Overall risk: <span style='color:{risk_col}'>{html.escape(r.overall_risk or '-')}</span></h3>
        {summary}
        {"<h3 style='color:%s'>Key findings</h3><ul>%s</ul>" % (GOLD, findings) if findings else ""}
        </div>""")

    def _fill_mapping(self, r: CompareResult):
        self.map_table.setRowCount(0)
        labels = {"exact": "Exact", "normalized": "Normalized", "fuzzy": "Fuzzy", "semantic": "Same meaning",
                  "ai": "AI matched", "unmatched": "Missing in target", "new": "New in target"}
        for m in r.mappings:
            row = self.map_table.rowCount()
            self.map_table.insertRow(row)
            key = " 🔑" if m.ref_column in r.key_columns.get(m.table_ref, []) else ""
            vals = [m.table_ref, (m.ref_column or "—") + key, m.meaning, m.tgt_column or "—",
                    labels.get(m.method, m.method), f"{m.confidence:.0%}", m.note]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if col == 4:
                    item.setForeground(QColor("#d9534f" if m.method == "unmatched" else "#3fae6a" if m.method == "new"
                                              else "#5b9bd5" if m.ref_column != m.tgt_column else GOLD2))
                if col in (1, 3):
                    item.setForeground(QColor(GOLD2))
                self.map_table.setItem(row, col, item)
        self.map_table.resizeColumnsToContents()
        if not r.mappings:
            self.map_table.setRowCount(1)
            self.map_table.setItem(0, 0, QTableWidgetItem("No tabular content in these files."))

    def _fill_sbs(self, r: CompareResult):
        rows = []
        for s in r.side_by_side[:3000]:
            if s.tag == "skip":
                rows.append(f"<tr><td colspan='4' style='background:#101012;color:{GOLD}' align='center'>⋯</td></tr>")
                continue
            a, b = (intraline(s.ref_text, s.tgt_text) if s.tag == "replace"
                    else (html.escape(s.ref_text), html.escape(s.tgt_text)))
            a = a.replace("<del>", "<span style='background:#6b2a28;color:#ffd0ce'>").replace("</del>", "</span>")
            b = b.replace("<ins>", "<span style='background:#1f5a35;color:#d0ffe0'>").replace("</ins>", "</span>")
            bga = {"delete": "#2a1615", "replace": "#2a2512"}.get(s.tag, "#141417")
            bgb = {"insert": "#142a1b", "replace": "#2a2512"}.get(s.tag, "#141417")
            rows.append(f"<tr><td style='color:#5d5d63' align='right'>{s.ref_no or ''}</td>"
                        f"<td style='background:{bga};white-space:pre'>{a}</td>"
                        f"<td style='color:#5d5d63' align='right'>{s.tgt_no or ''}</td>"
                        f"<td style='background:{bgb};white-space:pre'>{b}</td></tr>")
        if not rows:
            rows = ["<tr><td>No line-level differences.</td></tr>"]
        self.sbs.setHtml(f"<table width='100%' cellspacing='0' cellpadding='2' "
                         f"style='font-family:Consolas,monospace;font-size:12px;color:#ddd'>"
                         f"<tr><th style='color:{GOLD}'>#</th><th style='color:{GOLD}' align='left'>Reference</th>"
                         f"<th style='color:{GOLD}'>#</th><th style='color:{GOLD}' align='left'>Target</th></tr>"
                         + "".join(rows) + "</table>")

    def export_html(self):
        if not self.result:
            return
        default = os.path.splitext(self.result.target.path)[0] + "_diff_report.html"
        path, _ = QFileDialog.getSaveFileName(self, "Save HTML report", default, "HTML (*.html)")
        if path:
            save_html(self.result, path)
            self.status.showMessage(f"Report saved: {path}")
            if QMessageBox.question(self, "Report saved", f"Saved to\n{path}\n\nOpen it now?") == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_browser(self):
        if not self.result:
            return
        fd, path = tempfile.mkstemp(suffix=".html", prefix="aics_report_")
        os.close(fd)
        save_html(self.result, path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def closeEvent(self, e):
        self._save_settings()
        super().closeEvent(e)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AI Compare Studio")
    app.setStyleSheet(QSS)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
