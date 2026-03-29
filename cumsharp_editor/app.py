from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QRegularExpression, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QSyntaxHighlighter,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileSystemModel,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QTreeView,
    QWidget,
)


CUM_TEMPLATE = """use std.io;\n\nfn main() -> Int {\n    let mut message: String = \"hello from Cum#\";\n    print(message);\n    return 0;\n}\n"""


@dataclass
class DocumentState:
    path: Path | None = None
    untitled_index: int = 1
    language: str = "plain"


class CumSharpHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        def fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            if bold:
                text_format.setFontWeight(QFont.Weight.Bold)
            text_format.setFontItalic(italic)
            return text_format

        keyword_format = fmt("#7dd3fc", bold=True)
        type_format = fmt("#f9a8d4", bold=True)
        string_format = fmt("#86efac")
        number_format = fmt("#fdba74")
        comment_format = fmt("#94a3b8", italic=True)
        function_format = fmt("#c4b5fd", bold=True)
        operator_format = fmt("#fca5a5")
        annotation_format = fmt("#fde68a")

        keywords = [
            "use",
            "fn",
            "let",
            "mut",
            "if",
            "else",
            "for",
            "while",
            "loop",
            "return",
            "break",
            "continue",
            "match",
            "case",
            "class",
            "extends",
            "spawn",
            "async",
            "await",
            "true",
            "false",
            "null",
            "import",
            "from",
            "enum",
            "struct",
            "trait",
            "impl",
        ]
        types = [
            "Int",
            "Float",
            "Bool",
            "String",
            "Char",
            "Void",
            "List",
            "Map",
            "Any",
            "Result",
            "Option",
        ]

        for keyword in keywords:
            self.rules.append((QRegularExpression(rf"\\b{keyword}\\b"), keyword_format))
        for type_name in types:
            self.rules.append((QRegularExpression(rf"\\b{type_name}\\b"), type_format))

        self.rules.extend(
            [
                (QRegularExpression(r"//[^\n]*"), comment_format),
                (QRegularExpression(r'"([^"\\]|\\.)*"'), string_format),
                (QRegularExpression(r"'([^'\\]|\\.)*'"), string_format),
                (QRegularExpression(r"\b\d+(?:\.\d+)?\b"), number_format),
                (QRegularExpression(r"\b[A-Z][A-Za-z0-9_]*\b"), type_format),
                (QRegularExpression(r"@[A-Za-z_][A-Za-z0-9_]*"), annotation_format),
                (QRegularExpression(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)"), function_format),
                (QRegularExpression(r"->|=>|==|!=|<=|>=|&&|\|\||[+\-*/%=<>!~^]"), operator_format),
            ]
        )

        self.block_comment_start = QRegularExpression(r"/\*")
        self.block_comment_end = QRegularExpression(r"\*/")
        self.block_comment_format = comment_format

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt naming)
        for pattern, text_format in self.rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                if start < 0:
                    continue
                length = match.capturedLength()
                if pattern.pattern().startswith(r"\bfn") and match.lastCapturedIndex() >= 1:
                    start = match.capturedStart(1)
                    length = match.capturedLength(1)
                self.setFormat(start, length, text_format)

        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            block_start_match = self.block_comment_start.match(text)
            start_index = block_start_match.capturedStart() if block_start_match.hasMatch() else -1
        else:
            start_index = 0

        while start_index >= 0:
            block_end_match = self.block_comment_end.match(text, start_index)
            if block_end_match.hasMatch():
                end_index = block_end_match.capturedStart()
                comment_length = end_index - start_index + block_end_match.capturedLength()
            else:
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            self.setFormat(start_index, comment_length, self.block_comment_format)
            next_start_match = self.block_comment_start.match(text, start_index + comment_length)
            start_index = next_start_match.capturedStart() if next_start_match.hasMatch() else -1


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    cursor_moved = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.line_number_area = LineNumberArea(self)
        self.highlighter = CumSharpHighlighter(self.document())
        self._state = DocumentState()

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            "QPlainTextEdit {"
            "background: #0f172a; color: #e2e8f0; selection-background-color: #1d4ed8;"
            "border: none; }"
        )

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self.emit_cursor_position)
        self.document().modificationChanged.connect(lambda _: self.viewport().update())

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    @property
    def state(self) -> DocumentState:
        return self._state

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(contents_rect.left(), contents_rect.top(), self.line_number_area_width(), contents_rect.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#111827"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#64748b"))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self) -> None:
        if self.isReadOnly():
            return
        selection = QTextEdit.ExtraSelection()  # type: ignore[name-defined]
        selection.format.setBackground(QColor("#172554"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def emit_cursor_position(self) -> None:
        cursor = self.textCursor()
        self.cursor_moved.emit(cursor.blockNumber() + 1, cursor.columnNumber() + 1)

    def is_cum_file(self) -> bool:
        return self.state.language == "cum" or bool(self.state.path and self.state.path.suffix.lower() == ".cum")


class EditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cum# Editor")
        self.resize(1360, 860)
        self.untitled_counter = 1

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(self.on_current_tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab { background: #1f2937; color: #cbd5e1; padding: 10px 16px; }"
            "QTabBar::tab:selected { background: #334155; color: #ffffff; }"
        )

        self.tree_model = QFileSystemModel(self)
        self.tree_model.setRootPath("")
        self.tree = QTreeView()
        self.tree.setModel(self.tree_model)
        self.tree.setHeaderHidden(True)
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.hideColumn(3)
        self.tree.doubleClicked.connect(self.open_from_tree)
        self.tree.setMinimumWidth(260)
        self.tree.setStyleSheet(
            "QTreeView { background: #111827; color: #cbd5e1; border: none; }"
            "QTreeView::item:selected { background: #1d4ed8; }"
        )

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 1100])
        self.setCentralWidget(splitter)

        self.path_label = QLabel("No file")
        self.language_label = QLabel("Plain Text")
        self.cursor_label = QLabel("Ln 1, Col 1")
        status = QStatusBar()
        status.addPermanentWidget(self.language_label)
        status.addPermanentWidget(self.cursor_label)
        status.addWidget(self.path_label, 1)
        self.setStatusBar(status)

        self.build_actions()
        self.build_menus_and_toolbar()
        self.apply_dark_chrome()
        self.new_cum_file()

    def apply_dark_chrome(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background: #0b1120; color: #e2e8f0; }"
            "QMenuBar { background: #0f172a; color: #e2e8f0; }"
            "QMenuBar::item:selected { background: #1e293b; }"
            "QMenu { background: #0f172a; color: #e2e8f0; }"
            "QMenu::item:selected { background: #1e293b; }"
            "QToolBar { background: #0f172a; border: none; spacing: 6px; }"
            "QToolButton { color: #e2e8f0; padding: 6px; }"
            "QToolButton:hover { background: #1e293b; }"
            "QStatusBar { background: #0f172a; color: #cbd5e1; }"
        )

    def build_actions(self) -> None:
        self.new_action = QAction("New Cum# File", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_cum_file)

        self.new_plain_action = QAction("New Empty File", self)
        self.new_plain_action.setShortcut("Ctrl+Shift+N")
        self.new_plain_action.triggered.connect(self.new_empty_file)

        self.open_action = QAction("Open File…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_file_dialog)

        self.open_folder_action = QAction("Open Folder…", self)
        self.open_folder_action.setShortcut("Ctrl+K")
        self.open_folder_action.triggered.connect(self.open_folder_dialog)

        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_current)

        self.save_as_action = QAction("Save As…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_current_as)

        self.close_tab_action = QAction("Close Tab", self)
        self.close_tab_action.setShortcut(QKeySequence.StandardKey.Close)
        self.close_tab_action.triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))

        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.find_action = QAction("Find…", self)
        self.find_action.setShortcut(QKeySequence.StandardKey.Find)
        self.find_action.triggered.connect(self.find_text)

        self.goto_action = QAction("Go to Line…", self)
        self.goto_action.setShortcut("Ctrl+L")
        self.goto_action.triggered.connect(self.goto_line)

        self.about_action = QAction("About Cum# Editor", self)
        self.about_action.triggered.connect(self.show_about)

    def build_menus_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.new_plain_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.close_tab_action)
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.find_action)
        edit_menu.addAction(self.goto_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.about_action)

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.open_folder_action)
        toolbar.addSeparator()
        toolbar.addAction(self.find_action)
        toolbar.addAction(self.goto_action)
        self.addToolBar(toolbar)

    def current_editor(self) -> CodeEditor | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, CodeEditor) else None

    def make_editor(self, text: str = "", path: Path | None = None, language: str | None = None) -> CodeEditor:
        editor = CodeEditor()
        editor.setPlainText(text)
        editor.state.path = path
        if language is None and path is not None and path.suffix.lower() == ".cum":
            language = "cum"
        editor.state.language = language or "plain"
        if path is None:
            editor.state.untitled_index = self.untitled_counter
            self.untitled_counter += 1
        editor.document().setModified(False)
        editor.document().modificationChanged.connect(lambda _: self.refresh_current_tab_title(editor))
        editor.cursor_moved.connect(self.update_cursor_label)
        return editor

    def add_editor_tab(self, editor: CodeEditor) -> None:
        self.tabs.addTab(editor, self.title_for_editor(editor))
        self.tabs.setCurrentWidget(editor)
        self.refresh_current_tab_title(editor)
        self.on_current_tab_changed(self.tabs.currentIndex())

    def title_for_editor(self, editor: CodeEditor) -> str:
        if editor.state.path is not None:
            title = editor.state.path.name
        else:
            title = f"untitled-{editor.state.untitled_index}.cum" if editor.state.language == "cum" else f"untitled-{editor.state.untitled_index}.txt"
        if editor.document().isModified():
            title += " *"
        return title

    def refresh_current_tab_title(self, editor: CodeEditor) -> None:
        index = self.tabs.indexOf(editor)
        if index >= 0:
            self.tabs.setTabText(index, self.title_for_editor(editor))
        if self.current_editor() is editor:
            self.update_status(editor)

    def update_status(self, editor: CodeEditor | None) -> None:
        if editor is None:
            self.path_label.setText("No file")
            self.language_label.setText("Plain Text")
            self.cursor_label.setText("Ln 1, Col 1")
            return

        path_text = str(editor.state.path) if editor.state.path else self.title_for_editor(editor).replace(" *", "")
        self.path_label.setText(path_text)
        self.language_label.setText("Cum# (.cum)" if editor.is_cum_file() else "Plain Text")
        cursor = editor.textCursor()
        self.update_cursor_label(cursor.blockNumber() + 1, cursor.columnNumber() + 1)
        self.setWindowTitle(f"{self.title_for_editor(editor).replace(' *', '')} — Cum# Editor")

    def update_cursor_label(self, line: int, column: int) -> None:
        self.cursor_label.setText(f"Ln {line}, Col {column}")

    def new_cum_file(self) -> None:
        editor = self.make_editor(CUM_TEMPLATE, language="cum")
        self.add_editor_tab(editor)
        self.language_label.setText("Cum# (.cum)")

    def new_empty_file(self) -> None:
        editor = self.make_editor("")
        self.add_editor_tab(editor)

    def open_file_dialog(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Source File",
            str(Path.home()),
            "Cum# Files (*.cum);;Source Files (*.cum *.py *.rs *.c *.cpp *.h *.hpp *.js *.ts *.json *.toml *.md);;All Files (*)",
        )
        if file_name:
            self.open_file(Path(file_name))

    def open_folder_dialog(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Folder", str(Path.home()))
        if directory:
            self.set_project_root(Path(directory))

    def set_project_root(self, path: Path) -> None:
        index = self.tree_model.index(str(path))
        self.tree.setRootIndex(index)
        self.path_label.setText(str(path))

    def open_from_tree(self, index) -> None:
        path = Path(self.tree_model.filePath(index))
        if path.is_file():
            self.open_file(path)

    def open_file(self, path: Path) -> None:
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, CodeEditor) and widget.state.path == path:
                self.tabs.setCurrentIndex(i)
                return
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            QMessageBox.warning(self, "Unsupported Encoding", f"Could not open {path.name} as UTF-8 text.")
            return
        except OSError as exc:
            QMessageBox.critical(self, "Open Failed", f"Could not open file:\n{exc}")
            return

        editor = self.make_editor(text, path, language="cum" if path.suffix.lower() == ".cum" else "plain")
        self.add_editor_tab(editor)
        self.update_status(editor)

    def save_editor_to_path(self, editor: CodeEditor, path: Path) -> bool:
        try:
            path.write_text(editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save file:\n{exc}")
            return False
        editor.state.path = path
        editor.state.language = "cum" if path.suffix.lower() == ".cum" else editor.state.language
        editor.document().setModified(False)
        self.refresh_current_tab_title(editor)
        self.update_status(editor)
        return True

    def save_current(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        if editor.state.path is None:
            self.save_current_as()
            return
        self.save_editor_to_path(editor, editor.state.path)

    def save_current_as(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        start_path = editor.state.path or Path.home() / self.title_for_editor(editor).replace(" *", "")
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            str(start_path),
            "Cum# Files (*.cum);;All Files (*)",
        )
        if file_name:
            chosen = Path(file_name)
            if chosen.suffix == "":
                chosen = chosen.with_suffix(".cum")
            self.save_editor_to_path(editor, chosen)

    def maybe_save(self, editor: CodeEditor) -> bool:
        if not editor.document().isModified():
            return True
        title = self.title_for_editor(editor).replace(" *", "")
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes to {title}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Cancel:
            return False
        if result == QMessageBox.StandardButton.Save:
            if editor.state.path is None:
                current_index = self.tabs.indexOf(editor)
                self.tabs.setCurrentIndex(current_index)
                self.save_current_as()
                return not editor.document().isModified()
            return self.save_editor_to_path(editor, editor.state.path)
        return True

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if not isinstance(widget, CodeEditor):
            return
        if not self.maybe_save(widget):
            return
        self.tabs.removeTab(index)
        widget.deleteLater()
        if self.tabs.count() == 0:
            self.new_cum_file()
        else:
            self.on_current_tab_changed(self.tabs.currentIndex())

    def on_current_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        self.update_status(widget if isinstance(widget, CodeEditor) else None)

    def find_text(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        needle, ok = QInputDialog.getText(self, "Find", "Search text:")
        if not ok or not needle:
            return
        if not editor.find(needle):
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            if not editor.find(needle):
                QMessageBox.information(self, "Find", f"Could not find '{needle}'.")

    def goto_line(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        line, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", 1, 1, max(1, editor.blockCount()))
        if not ok:
            return
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, line - 1)
        editor.setTextCursor(cursor)
        editor.setFocus()

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Cum# Editor",
            "Cum# Editor\n\n"
            "A lightweight desktop editor for .cum files with a custom Cum# syntax highlighter, "
            "project tree, and DebianMOSS-friendly packaging.",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, CodeEditor) and not self.maybe_save(widget):
                event.ignore()
                return
        event.accept()


# Imported late to keep the QtWidgets namespace focused above.
from PySide6.QtWidgets import QTextEdit  # noqa: E402  pylint: disable=wrong-import-position


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cum# Editor")
    app.setOrganizationName("DebianMOSS")
    window = EditorWindow()

    initial_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    if initial_path:
        if initial_path.is_dir():
            window.set_project_root(initial_path)
        elif initial_path.is_file():
            window.open_file(initial_path)
            window.set_project_root(initial_path.parent)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
