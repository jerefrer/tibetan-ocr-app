import os
import cv2
import sys
import subprocess
import re
from uuid import UUID
from typing import Dict, List
from PySide6.QtCore import Signal, Qt, QThreadPool
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel
from pdf2image import convert_from_path
import platform
from BDRC.Styles import DARK
from BDRC.Inference import OCRPipeline
from BDRC.Data import OpStatus, Platform, OCRData, OCRModel, OCResult
from BDRC.Utils import build_ocr_data, get_filename, create_dir
from BDRC.Widgets.Dialogs import NotificationDialog, SettingsDialog, BatchOCRDialog, ExportDialog, \
    ImportImagesDialog, ImportPDFDialog, ImportFilesProgress
from BDRC.Widgets.Layout import HeaderTools, ImageGallery, Canvas, TextView
from BDRC.MVVM.viewmodel import DataViewModel, SettingsViewModel


class MainView(QWidget):
    s_handle_import = Signal()
    s_handle_pdf_import = Signal()
    s_handle_page_select = Signal(int)
    s_on_file_save = Signal()
    s_run_ocr = Signal(UUID)
    s_run_batch_ocr = Signal()
    s_handle_settings = Signal()

    def __init__(self, data_view: DataViewModel, settings_view: SettingsViewModel, platform: Platform):
        super().__init__()
        self.setObjectName("MainView")
        self.setContentsMargins(0, 0, 0, 0)
        self._data_view = data_view
        self._settings_view = settings_view
        self.platform = platform
        self.resource_dir = self._settings_view.get_execution_dir()
        self.default_font = self._settings_view.get_default_font_path()

        self.header_tools = HeaderTools(self._data_view, self._settings_view)
        self.canvas = Canvas(self.resource_dir )
        self.text_view = TextView(platform=self.platform, dataview=self._data_view, execution_dir=self.resource_dir, font_path=self.default_font)
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(10)
        self.v_splitter.addWidget(self.canvas)
        self.v_splitter.addWidget(self.text_view)

        # build layout
        self.v_layout = QVBoxLayout()
        self.v_layout.addWidget(self.header_tools)
        self.v_layout.addWidget(self.v_splitter)
        self.setLayout(self.v_layout)

        # connect to view model signals
        self._data_view.s_data_selected.connect(self.set_data)
        self._data_view.s_page_data_update.connect(self.set_data)
        self._data_view.s_data_changed.connect(self.update_data)
        self._data_view.s_data_cleared.connect(self.clear_data)


        # connect to tool signals
        self.header_tools.toolbox.s_new.connect(self.handle_new)
        self.header_tools.toolbox.s_import_files.connect(self.handle_import)
        self.header_tools.toolbox.s_import_pdf.connect(self.handle_pdf_import)
        self.header_tools.toolbox.s_save.connect(self.handle_file_save)
        self.header_tools.toolbox.s_on_select_model.connect(self.handle_model_selection)
        self.header_tools.toolbox.s_run.connect(self.handle_run)
        self.header_tools.toolbox.s_run_all.connect(self.handle_batch_run)
        self.header_tools.toolbox.s_settings.connect(self.handle_settings)
        self.header_tools.page_switcher.s_on_page_changed.connect(self.handle_update_page)

        self.current_guid = None

    def handle_new(self):
        self._data_view.clear_data()

    def update_data(self, data: List[OCRData]):
        self.header_tools.update_page_count(len(data))

    def handle_import(self):
        self.s_handle_import.emit()

    def handle_pdf_import(self):
        self.s_handle_pdf_import.emit()

    def handle_file_save(self):
        self.s_on_file_save.emit()

    def handle_model_selection(self, ocr_model: OCRModel):
        self._settings_view.select_ocr_model(ocr_model)

    def handle_run(self):
        if self.current_guid is not None:
            self.s_run_ocr.emit(self.current_guid)
        else:
            dialog = NotificationDialog("No data", "Project contains no data.")
            dialog.exec()

    def handle_batch_run(self):
        self.s_run_batch_ocr.emit()

    def handle_settings(self):
        self.s_handle_settings.emit()

    def handle_update_page(self, index: int):
        self._data_view.select_data_by_index(index)

    def set_data(self, data: OCRData):
        self.canvas.set_preview(data)
        self.current_guid = data.guid

    def clear_data(self):
        self.canvas.clear()


class AppView(QWidget):
    def __init__(self,
                 dataview_model: DataViewModel,
                 settingsview_model: SettingsViewModel,
                 platform: Platform):
        super().__init__()

        self.setObjectName("MainWindow")
        self.setWindowTitle("BDRC OCR [BETA] 0.1")
        self.setContentsMargins(0, 0, 0, 0)
        self.platform = platform
        self.threadpool = QThreadPool()
        self._dataview_model = dataview_model
        self._settingsview_model = settingsview_model

        self.tmp_dir = self._settingsview_model.get_tmp_dir()
        self.resource_dir = self._settingsview_model.get_execution_dir()

        self.image_gallery = ImageGallery(self._dataview_model, self.threadpool, self.resource_dir)
        self.main_container = MainView(self._dataview_model, self._settingsview_model, self.platform)
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setHandleWidth(10)
        self.h_splitter.setContentsMargins(0, 0, 0, 0)
        self.h_splitter.addWidget(self.image_gallery)
        self.h_splitter.addWidget(self.main_container)

        # build layout
        self.main_layout = QHBoxLayout()
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.h_splitter)
        self.setLayout(self.main_layout)

        # connect view model signals
        self._settingsview_model.s_ocr_model_changed.connect(self.update_ocr_model)

        # connect layout signals
        self.main_container.s_handle_import.connect(self.handle_file_import)
        self.main_container.s_handle_pdf_import.connect(self.handle_pdf_import)
        self.main_container.s_handle_page_select.connect(self.select_page)
        self.main_container.s_on_file_save.connect(self.save)
        self.main_container.s_run_ocr.connect(self.run_ocr)
        self.main_container.s_run_batch_ocr.connect(self.run_batch_ocr)
        self.main_container.s_handle_settings.connect(self.handle_settings)

        # ocr inference sessions
        line_config = self._settingsview_model.get_line_model()
        ocr_model = self._settingsview_model.get_current_ocr_model()

        if ocr_model is not None:
            self.ocr_pipeline = OCRPipeline(
                self.platform,
                ocr_model.config,
                line_config)
        else:
            self.ocr_pipeline = None

        self.show()

    def handle_file_import(self):
        dialog = ImportImagesDialog()

        if dialog.exec():
            file_list = dialog.selectedFiles()
            imported_data = {}
            size_hint = self.image_gallery.sizeHint()
            target_width = size_hint.width() - 80

            if len(file_list) > 20:
                progress = ImportFilesProgress("Importing Images...", max_length=len(file_list))
                progress.setWindowModality(Qt.WindowModality.WindowModal)

                for idx, file_path in enumerate(file_list):
                    if os.path.isfile(file_path):

                        ocr_data = build_ocr_data(idx, file_path, target_width)
                        imported_data[ocr_data.guid] = ocr_data
                        progress.setValue(idx)

                        if progress.wasCanceled():
                            progress.close()
                            break

            else:
                for idx, file_path in enumerate(file_list):
                    if os.path.isfile(file_path):
                        ocr_data = build_ocr_data(idx, file_path, target_width)
                        imported_data[ocr_data.guid] = ocr_data

            self.import_files(imported_data)

    def handle_pdf_import(self):
        dialog = ImportPDFDialog()

        if dialog.exec():
            selected_files = dialog.selectedFiles()

            if len(selected_files) > 0:
                file_path = selected_files[0]
                file_n = get_filename(file_path)

                if os.path.isfile(file_path):
                    try:
                        imported_data = {}
                        image_paths = []

                        # Try to find bundled Poppler
                        poppler_path = None
                        try:
                            # Check if we're running from a bundled app
                            if getattr(sys, 'frozen', False):
                                base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
                                
                                # Check for different possible Poppler directory structures
                                possible_paths = [
                                    os.path.join(base_path, 'poppler', 'bin'),  # Standard structure
                                    os.path.join(base_path, 'poppler', 'Library', 'bin'),  # Alternative structure
                                    os.path.join(base_path, 'poppler')  # Direct bin directory
                                ]
                                
                                # Find the first valid path that exists and contains pdfinfo
                                for path in possible_paths:
                                    if os.path.exists(path):
                                        # Check if pdfinfo exists in this path
                                        pdfinfo_path = os.path.join(path, 'pdfinfo')
                                        if platform.system() == 'Windows':
                                            pdfinfo_path += '.exe'
                                        
                                        if os.path.exists(pdfinfo_path):
                                            poppler_path = path
                                            print(f"Found Poppler at: {poppler_path}")
                                            break
                                
                                if not poppler_path:
                                    print("Poppler binaries not found in expected locations")
                        except Exception as e:
                            print(f"Error finding bundled Poppler: {e}")
                            poppler_path = None
                            
                        # Open the PDF file with pdf2image
                        try:
                            # Calculate total pages for progress (we'll need to convert first page to get count)
                            first_page = convert_from_path(file_path, dpi=300, first_page=1, last_page=1, poppler_path=poppler_path)
                            if first_page:
                                # Use pdftoppm to get page count
                                try:
                                    if poppler_path:
                                        pdfinfo_path = os.path.join(poppler_path, 'pdfinfo')
                                        if platform.system() == 'Windows':
                                            pdfinfo_path += '.exe'
                                        if os.path.exists(pdfinfo_path):
                                            result = subprocess.run([pdfinfo_path, file_path], capture_output=True, text=True)
                                            match = re.search(r'Pages:\s+(\d+)', result.stdout)
                                            if match:
                                                total_pages = int(match.group(1))
                                            else:
                                                # Fallback: try to convert all pages and count them
                                                total_pages = 1  # Default to 1 if we can't determine
                                        else:
                                            total_pages = 1
                                    else:
                                        # Try using system pdfinfo
                                        result = subprocess.run(['pdfinfo', file_path], capture_output=True, text=True)
                                        match = re.search(r'Pages:\s+(\d+)', result.stdout)
                                        if match:
                                            total_pages = int(match.group(1))
                                        else:
                                            total_pages = 1
                                except Exception as e:
                                    print(f"Error getting page count: {e}")
                                    total_pages = 1  # Default to 1 if we can't determine
                                
                                progress = ImportFilesProgress("Reading PDF file...", max_length=total_pages)
                                progress.setWindowModality(Qt.WindowModality.WindowModal)

                                tmp_image_dir = os.path.join(self.tmp_dir, "images")
                                create_dir(tmp_image_dir)

                                # Convert first page (already converted)
                                tmp_img_path = f"{tmp_image_dir}/{file_n}_0.jpg"
                                first_page[0].save(tmp_img_path, "JPEG", quality=100)
                                image_paths.append(tmp_img_path)
                                progress.setValue(0)
                                
                                # Convert remaining pages if there are more
                                if total_pages > 1:
                                    # Process in batches to avoid memory issues
                                    batch_size = 5
                                    for batch_start in range(2, total_pages + 1, batch_size):
                                        if progress.wasCanceled():
                                            break
                                            
                                        batch_end = min(batch_start + batch_size - 1, total_pages)
                                        progress.setLabelText(f"Processing pages {batch_start} to {batch_end} of {total_pages}...")
                                        
                                        # Convert batch of pages
                                        pages = convert_from_path(
                                            file_path, 
                                            dpi=300, 
                                            first_page=batch_start, 
                                            last_page=batch_end,
                                            poppler_path=poppler_path
                                        )
                                        
                                        # Save each page
                                        for i, page in enumerate(pages):
                                            page_num = batch_start + i - 1  # Adjust for 0-based indexing
                                            tmp_img_path = f"{tmp_image_dir}/{file_n}_{page_num}.jpg"
                                            page.save(tmp_img_path, "JPEG", quality=100)
                                            image_paths.append(tmp_img_path)
                                            progress.setValue(page_num)
                                
                                size_hint = self.image_gallery.sizeHint()
                                target_width = size_hint.width() - 80

                                for idx, img_path in enumerate(image_paths):
                                    if os.path.isfile(img_path):
                                        ocr_data = build_ocr_data(idx, img_path, target_width)
                                        imported_data[ocr_data.guid] = ocr_data

                                self.import_files(imported_data)
                        except Exception as e:
                            error_dialog = NotificationDialog("Error importing PDF", f"PDF import error: {str(e)}")
                            error_dialog.exec()
                    except Exception as e:
                        error_dialog = NotificationDialog("Error importing PDF", str(e))
                        error_dialog.exec_()
                else:
                    error_dialog = NotificationDialog("Invalid file", "The selected file is not a valid file.")
                    error_dialog.exec_()

    def import_files(self, results: Dict[UUID, OCRData]):
        self._dataview_model.add_data(results)

    def save(self):
        _ocr_data = self._dataview_model.get_data()
        ocred_lines = 0

        for k, data in _ocr_data.items():
            if data.ocr_lines is not None and len(data.ocr_lines) > 0:
                ocred_lines += 1

        if not len(_ocr_data) > 0:
            info_box = NotificationDialog(
                "Saving Annotations",
                "The current project contains no data."
            )
            info_box.exec()

        elif not ocred_lines > 0:
            info_box = NotificationDialog(
                "Saving Annotations",
                "The current contains no OCR data. Please run OCR first."
            )
            info_box.exec()

        else:
            _ocr_settings = self._settingsview_model.get_ocr_settings()
            dialog = ExportDialog(list(_ocr_data.values()), _ocr_settings.output_encoding)
            dialog.setStyleSheet(DARK)
            dialog.exec()

    def select_page(self, index: int):
        self.image_gallery.select_page(index)

    def run_ocr(self, guid: UUID):
        data = self._dataview_model.get_data_by_guid(guid)

        if os.path.isfile(data.image_path):
            img = cv2.imread(data.image_path)
            ocr_settings = self._settingsview_model.get_ocr_settings()
            status, result = self.ocr_pipeline.run_ocr(
                img,
                k_factor=ocr_settings.k_factor,
                bbox_tolerance=ocr_settings.bbox_tolerance,
                merge_lines=ocr_settings.merge_lines,
                use_tps=ocr_settings.dewarping)

            if status == OpStatus.SUCCESS:
                mask, line_data, page_text, angle = result
                self._dataview_model.update_ocr_data(guid, page_text)
                self._dataview_model.update_page_data(guid, line_data, mask, angle)
            else:
                dialog = NotificationDialog("Failed Running OCR", f"Failed to run OCR on selected image.\n\n{result}")
                dialog.exec()
        else:
            dialog = NotificationDialog("Image not found", "The selected image could not be read from disk.")
            dialog.exec()

    def run_batch_ocr(self):
        _data = self._dataview_model.get_data()
        _data = list(_data.values())

        if _data is not None and len(_data) > 0:
            batch_dialog = BatchOCRDialog(
                data=_data,
                ocr_pipeline=self.ocr_pipeline,
                ocr_models=self._settingsview_model.get_ocr_models(),
                ocr_settings=self._settingsview_model.get_ocr_settings(),
                threadpool=self.threadpool
            )
            batch_dialog.sign_ocr_result.connect(self.update_ocr_result)

            batch_dialog.setStyleSheet(DARK)
            batch_dialog.exec()
        else:
            dialog = NotificationDialog("No data", "Project contains no data.")
            dialog.exec()

    def update_ocr_result(self, result: OCResult, silent: bool = False):
        if result is not None:
            self._dataview_model.update_ocr_data(result.guid, result.text, silent)
            self._dataview_model.update_page_data(result.guid, result.lines, result.mask, result.angle, silent)

        else:
            dialog = NotificationDialog("Failed Running OCR", "Failed to run OCR on selected image.")
            dialog.exec()

    def handle_ocr_batch_result(self, batch_result: Dict[UUID, OCResult]):
        if batch_result is not None:
            for _, result in batch_result.values():
                self.update_ocr_result(result, silent=True)
        else:
            dialog = NotificationDialog("Failed Running OCR", "Failed to run OCR on selected image.")
            dialog.exec()

    def handle_settings(self):
        _models = self._settingsview_model.get_ocr_models()
        _app_settings = self._settingsview_model.get_app_settings()
        _ocr_settings = self._settingsview_model.get_ocr_settings()

        dialog = SettingsDialog(_app_settings, _ocr_settings, _models)
        dialog.setStyleSheet(DARK)

        app_settings, ocr_settings, ocr_models = dialog.exec()
        self._settingsview_model.save_app_settings(app_settings)
        self._settingsview_model.save_ocr_settings(ocr_settings)
        self._settingsview_model.update_ocr_models(ocr_models)
        
        current_line_config = self._settingsview_model.get_line_model()

        if self.ocr_pipeline is not None:
            self.ocr_pipeline.update_line_detection(current_line_config)

    def update_ocr_model(self, ocr_model: OCRModel):
        if self.ocr_pipeline is not None:
            self.ocr_pipeline.update_ocr_model(ocr_model.config)
        else:
            line_model_config = self._settingsview_model.get_line_model()
            self.ocr_pipeline = OCRPipeline(self.platform, ocr_model.config, line_model_config)
