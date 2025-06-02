from typing import List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QButtonGroup
)

from BDRC.Data import OCRData, Encoding, OCRLine
from BDRC.Widgets.Dialogs.helpers import build_encodings, build_exporter_settings
from BDRC.Widgets.Dialogs.export_dir_dialog import ExportDirDialog
from BDRC.Exporter import PageXMLExporter, JsonExporter, TextExporter

class ExportDialog(QDialog):
    last_export_dir = None  # Remember last export folder for this session

    def __init__(
            self,
            ocr_data: List[OCRData],
            active_encoding: Encoding,
        ):
        super().__init__()
        self.setObjectName("ExportDialog")
        self.ocr_data = ocr_data
        self.encoding = active_encoding
        import os
        from pathlib import Path
        # Use last export dir if set, otherwise default to user's Downloads folder
        if ExportDialog.last_export_dir:
            self.output_dir = ExportDialog.last_export_dir
        else:
            downloads = os.path.join(Path.home(), "Downloads")
            self.output_dir = downloads if os.path.isdir(downloads) else str(Path.home())
        self.main_label = QLabel("Export OCR Data")
        self.main_label.setObjectName("OptionsLabel")
        self.exporter_group, self.exporter_buttons = build_exporter_settings()
        self.encodings_group, self.encoding_buttons = build_encodings(self.encoding)

        # build layout
        self.setWindowTitle("BDRC Export")
        self.setMinimumHeight(220)
        self.setMinimumWidth(600)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.export_dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setObjectName("")
        self.dir_edit.setText(self.output_dir)

        self.dir_select_btn = QPushButton("Select")
        self.dir_select_btn.setObjectName("SmallDialogButton")
        self.export_dir_layout.addWidget(self.dir_edit)
        self.export_dir_layout.addWidget(self.dir_select_btn)

        encoding_layout = QHBoxLayout()
        encoding_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for encoding in self.encoding_buttons:
            encoding_layout.addWidget(encoding)

        export_layout = QHBoxLayout()
        export_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for btn in self.exporter_buttons:
            export_layout.addWidget(btn)

        self.button_h_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Ok")
        self.ok_btn.setObjectName("DialogButton")
        self.cancel_btn = QPushButton("Cancel", parent=self)
        self.cancel_btn.setObjectName("DialogButton")

        self.button_h_layout.addWidget(self.ok_btn)
        self.button_h_layout.addWidget(self.cancel_btn)

        # bind signals
        self.ok_btn.clicked.connect(self.export)
        self.cancel_btn.clicked.connect(self.cancel)
        self.dir_select_btn.clicked.connect(self.select_export_dir)

        self.v_layout = QVBoxLayout()
        self.v_layout.addWidget(self.main_label)
        self.v_layout.addLayout(self.export_dir_layout)
        self.v_layout.addLayout(encoding_layout)
        self.v_layout.addLayout(export_layout)
        self.v_layout.addLayout(self.button_h_layout)
        self.setLayout(self.v_layout)

        self.setStyleSheet(
            """
            background-color: #1d1c1c;
            color: #ffffff;

            QLabel {
                color: #000000;
            }
            """
        )

    def export(self):
        if self.output_dir == "":
            return

        selected_id = self.exporter_group.checkedId()
        selected_encoding_id = self.encodings_group.checkedId()

        # create exporter based on selection
        if selected_id == 0:
            exporter = TextExporter(self.output_dir)
        elif selected_id == 1:
            exporter = PageXMLExporter(self.output_dir)
        elif selected_id == 2:
            exporter = JsonExporter(self.output_dir)
        else:
            exporter = TextExporter(self.output_dir)

        # export all data
        for data in self.ocr_data:
            if isinstance(exporter, TextExporter):
                if data.ocr_lines is not None:
                    # Convert to Wylie if needed
                    if selected_encoding_id == Encoding.Wylie.value:
                        from pyewts import pyewts
                        converter = pyewts()
                        wylie_lines = []
                        for l in data.ocr_lines:
                            # l.text is Unicode, convert to Wylie
                            wylie_text = converter.toWylie(l.text)
                            # Create a new OCRLine with Wylie encoding
                            wylie_lines.append(OCRLine(l.guid, wylie_text, Encoding.Wylie))
                        exporter.export_text(data.image_name, wylie_lines)
                    else:
                        exporter.export_text(data.image_name, data.ocr_lines)
            else:
                exporter.export(data, selected_encoding_id)

        self.accept()

    def cancel(self):
        self.reject()

    def select_export_dir(self):
        _dialog = ExportDirDialog()
        selected_dir = _dialog.exec()

        if selected_dir == 1:
            _selected_dir = _dialog.selectedFiles()[0]
            self.output_dir = _selected_dir
            ExportDialog.last_export_dir = _selected_dir  # Remember for next time
            self.dir_edit.setText(self.output_dir)
