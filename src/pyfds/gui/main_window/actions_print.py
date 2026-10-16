"""File > Print and Run > Hardware & Graphics Settings (plan step F1).

Print prints what is in front: the 3D view or the 2D plan as a picture, the Record view as text, the results viewer as a
picture. The same drawing code feeds the preview, a paper printer and "print to PDF"."""
from __future__ import annotations

import datetime
from typing import Any, Optional, Tuple

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QMessageBox

from pyfds.gui.graphics_dialog import HardwareSettingsDialog


class ActionsPrintMixin:
    # -- what to print ------------------------------------------------------------------------------------------------
    def _print_content(self) -> Tuple[str, Any, str]:
        """``(kind, payload, title)``: ``image`` with a QImage, or ``text`` with a string, for the tab in front."""
        current = self.view_tabs.currentWidget()
        title = f"{self.api.project.chid} - {self.view_tabs.tabText(self.view_tabs.currentIndex())}"
        if current is getattr(self, "_record_view", None) and current is not None:
            return "text", current.text(), title
        if current is self.model_split and hasattr(self.viewport_widget, "image"):
            return "image", self.viewport_widget.image(), title
        if current is self.model_split:                              # no 3D view (headless): the input file is the content
            return "text", self.api.fds_text(), title
        return "image", current.grab().toImage(), title

    # -- drawing for a printer ------------------------------------------------------------------------------------------
    def render_for_print(self, printer: QPrinter, content: Optional[Tuple[str, Any, str]] = None) -> None:
        kind, payload, title = content or self._print_content()
        if kind == "text":
            doc = QTextDocument()
            doc.setPlainText(f"{title}\n{datetime.date.today().isoformat()}\n\n{payload}")
            font = doc.defaultFont()
            font.setFamily("Consolas")
            font.setPointSize(9)
            doc.setDefaultFont(font)
            doc.print_(printer)
            return
        image: QImage = payload
        painter = QPainter(printer)
        try:
            page = printer.pageRect(QPrinter.DevicePixel).toRect()
            painter.setFont(painter.font())
            header = painter.fontMetrics().height() * 2
            painter.drawText(QRect(page.left(), page.top(), page.width(), header), Qt.AlignLeft | Qt.AlignVCenter,
                             f"{title}    {datetime.date.today().isoformat()}")
            body = QRect(page.left(), page.top() + header, page.width(), page.height() - header)
            if not image.isNull():
                scaled = image.scaled(body.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawImage(body.left() + (body.width() - scaled.width()) // 2, body.top(), scaled)
        finally:
            painter.end()

    def print_to_pdf(self, path: str, content: Optional[Tuple[str, Any, str]] = None) -> str:
        """Print what is in front into a PDF file (also the quickest way to test printing)."""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageOrientation(QPageLayout.Landscape)
        self.render_for_print(printer, content)
        return path

    # -- the menu entries --------------------------------------------------------------------------------------------------
    def _on_print(self) -> QPrintPreviewDialog:
        """Print preview of the tab in front; the dialog's own toolbar prints or saves it."""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(QPageLayout.Landscape)
        content = self._print_content()
        dialog = QPrintPreviewDialog(printer, self)
        dialog.paintRequested.connect(lambda p: self.render_for_print(p, content))
        self._print_dialog = dialog
        dialog.exec()
        return dialog

    def _on_hardware_settings(self) -> HardwareSettingsDialog:
        dialog = HardwareSettingsDialog(self.api, self.viewport_widget, self)
        self._hardware_dialog = dialog
        dialog.exec()
        return dialog
