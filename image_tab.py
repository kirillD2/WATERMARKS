# --- Импорты необходимых библиотек ---
# Стандартные модули Python
import os  # Для работы с путями к файлам (например, чтобы получить имя файла)
import logging  # Для вывода информации о работе программы (не используется активно, но полезно иметь)

# Модули из библиотеки PyQt6 для создания интерфейса
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QSize
from PyQt6.QtGui import QPixmap, QFontDatabase, QImage, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QHBoxLayout, QComboBox, QSlider, QProgressBar, QListWidget, QListWidgetItem, QMenu,
    QSpinBox, QFrame, QStackedWidget, QRadioButton, QGridLayout
)

# Модули из библиотеки Pillow (PIL) для работы с изображениями
from PIL import Image
from PIL.ImageQt import ImageQt

# Импортируем наши собственные функции и классы из файла utils.py
from utils import WatermarkParams, apply_watermark_to_pillow_image


# --- Поток для обработки изображений ---
# Чтобы интерфейс не "зависал" во время обработки множества файлов,
# мы выносим эту задачу в отдельный поток (QThread).
class ImageProcessingThread(QThread):
    # Сигналы - это способ, которым поток сообщает главному окну о событиях.
    finished_one = pyqtSignal(str)  # Сигнал об успешном завершении одного файла
    error = pyqtSignal(str)         # Сигнал в случае ошибки

    def __init__(self, image_file: str, result_file: str, params: WatermarkParams):
        super().__init__()
        # Сохраняем переданные параметры в переменных класса
        self.image_file, self.result_file, self.params = image_file, result_file, params
        self._is_running = True  # Флаг, который показывает, должен ли поток продолжать работать

    
    def run(self):
        if not self._is_running:
            return  # Если пришел сигнал остановиться, выходим

        # Пытаемся обработать изображение
        try:
            base_image = Image.open(self.image_file)
            watermarked_image = apply_watermark_to_pillow_image(base_image, self.params)
            watermarked_image.convert("RGB").save(self.result_file, "JPEG" if self.result_file.lower().endswith((".jpg", ".jpeg")) else "PNG")

            if self._is_running:
                # Если все прошло хорошо и нас не остановили, отправляем сигнал "готово"
                self.finished_one.emit(self.result_file)
        except Exception as e:
            # Если произошла ошибка
            if self._is_running:
                # Отправляем сигнал "ошибка" с текстом исключения
                self.error.emit(f"Ошибка с файлом {os.path.basename(self.image_file)}: {e}")

    # Метод для остановки потока извне
    def stop(self):
        self._is_running = False


# --- Основной виджет вкладки "Изображения" ---
class ImageTab(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings  # Сохраняем настройки
        self.image_threads = []  # Список для хранения потоков обработки
        self.processed_count = 0  # Счетчик обработанных файлов
        self.current_preview_path = None  # Путь к файлу, который сейчас в предпросмотре
        self.current_base_pillow_image = None  # PIL-объект этого файла
        self.banner_path = "" # Добавляем для сохранения пути к баннеру
        
        self.init_ui()
        self.connect_signals()
        self.load_settings()

    # --- Главный метод создания интерфейса ---
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- Left Panel ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(450)

        wm_type_layout = QHBoxLayout()
        self.radio_text_wm = QRadioButton("Текст")
        self.radio_text_wm.setChecked(True)
        self.radio_image_wm = QRadioButton("Баннер")
        wm_type_layout.addWidget(QLabel("Тип водяного знака:"))
        wm_type_layout.addWidget(self.radio_text_wm)
        wm_type_layout.addWidget(self.radio_image_wm)
        wm_type_layout.addStretch()
        left_layout.addLayout(wm_type_layout)

        # -- Text Controls --
        self.text_controls_widget = QWidget()
        text_layout = QVBoxLayout(self.text_controls_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.label_watermark_img = QLabel("Текст водяного знака")
        self.label_watermark_img.setObjectName("label_watermark_img")
        self.input_watermark_img = QLineEdit()
        self.input_watermark_img.setPlaceholderText("Ваш текст...")
        text_grid = QGridLayout()
        self.combo_font_img = QComboBox()
        self.combo_font_img.addItems(QFontDatabase.families())
        self.spin_font_size_img = QSpinBox()
        self.spin_font_size_img.setRange(1, 50)
        self.spin_font_size_img.setValue(10)
        self.spin_font_size_img.setSuffix(" %")
        text_grid.addWidget(QLabel("Шрифт:"), 0, 0)
        text_grid.addWidget(self.combo_font_img, 0, 1)
        text_grid.addWidget(QLabel("Отн. размер:"), 0, 2)
        text_grid.addWidget(self.spin_font_size_img, 0, 3)
        text_layout.addWidget(self.label_watermark_img)
        text_layout.addWidget(self.input_watermark_img)
        text_layout.addLayout(text_grid)
        
        # -- Image Controls --
        self.image_controls_widget = QWidget()
        image_layout = QVBoxLayout(self.image_controls_widget)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_select_banner = QPushButton("Выбрать изображение баннера")
        self.label_banner_path = QLabel("Файл не выбран")
        self.label_banner_path.setStyleSheet("font-style: italic;")
        scale_layout = QHBoxLayout()
        self.spin_banner_scale = QSpinBox()
        self.spin_banner_scale.setRange(1, 100)
        self.spin_banner_scale.setValue(25)
        self.spin_banner_scale.setSuffix(" %")
        scale_layout.addWidget(QLabel("Масштаб (от ширины):"))
        scale_layout.addWidget(self.spin_banner_scale)
        scale_layout.addStretch()
        image_layout.addWidget(self.btn_select_banner)
        image_layout.addWidget(self.label_banner_path)
        image_layout.addLayout(scale_layout)

        self.controls_stack = QStackedWidget()
        self.controls_stack.addWidget(self.text_controls_widget)
        self.controls_stack.addWidget(self.image_controls_widget)
        left_layout.addWidget(self.controls_stack)

        # -- Common Controls --
        common_controls_frame = QFrame()
        common_layout = QGridLayout(common_controls_frame)
        self.combo_position_img = QComboBox()
        self.combo_position_img.addItems(["Центр", "Верхний левый угол", "Верхний правый угол", "Нижний левый угол", "Нижний правый угол"])
        self.spin_offset_x = QSpinBox(); self.spin_offset_x.setRange(-2000, 2000)
        self.spin_offset_y = QSpinBox(); self.spin_offset_y.setRange(-2000, 2000)
        opacity_layout = QHBoxLayout()
        self.slider_opacity_img = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity_img.setRange(0, 255); self.slider_opacity_img.setValue(128)
        opacity_layout.addWidget(QLabel("Непрозрачность:"))
        opacity_layout.addWidget(self.slider_opacity_img)
        common_layout.addWidget(QLabel("Позиция:"), 0, 0)
        common_layout.addWidget(self.combo_position_img, 0, 1, 1, 3)
        common_layout.addWidget(QLabel("Смещение X:"), 1, 0); common_layout.addWidget(self.spin_offset_x, 1, 1)
        common_layout.addWidget(QLabel("Смещение Y:"), 1, 2); common_layout.addWidget(self.spin_offset_y, 1, 3)
        common_layout.addLayout(opacity_layout, 2, 0, 1, 4)
        left_layout.addWidget(common_controls_frame)

        self.image_button_img = QPushButton("📁 Выбрать изображения")
        left_layout.addWidget(self.image_button_img)
        
        self.image_list_widget = QListWidget()
        self.image_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list_widget.setIconSize(QSize(100, 100))
        self.image_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list_widget.setMovement(QListWidget.Movement.Static)
        self.image_list_widget.setSpacing(10)
        self.image_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.image_list_widget)

        self.progress_bar_img = QProgressBar()
        self.progress_bar_img.setVisible(False)
        left_layout.addWidget(self.progress_bar_img)

        action_buttons_layout = QHBoxLayout()
        self.watermark_button_img = QPushButton("🖋️ Применить ко всем")
        self.cancel_button_img = QPushButton("❌ Отмена")
        self.cancel_button_img.setObjectName("cancel_button_img")
        action_buttons_layout.addWidget(self.watermark_button_img)
        action_buttons_layout.addWidget(self.cancel_button_img)
        left_layout.addLayout(action_buttons_layout)
        
        main_layout.addWidget(left_panel)

        # --- Right Panel ---
        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right_panel)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 400)
        self.preview_label_placeholder = QLabel("Перетащите файлы или выберите их,\nчтобы увидеть предпросмотр")
        self.preview_label_placeholder.setObjectName("preview_label_placeholder")
        self.preview_label_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview_label_placeholder)
        self.preview_stack.addWidget(self.preview_label)
        right_layout.addWidget(self.preview_stack)
        main_layout.addWidget(right_panel, 1)
        
        self.reset_processing_state()

    # --- Соединение сигналов и слотов ---
    def connect_signals(self):
        # Update preview on any setting change
        self.radio_text_wm.toggled.connect(self._on_settings_changed)
        self.radio_image_wm.toggled.connect(self._on_settings_changed)
        self.input_watermark_img.textChanged.connect(self._on_settings_changed)
        self.combo_font_img.currentTextChanged.connect(self._on_settings_changed)
        self.spin_font_size_img.valueChanged.connect(self._on_settings_changed)
        self.spin_banner_scale.valueChanged.connect(self._on_settings_changed)
        self.combo_position_img.currentTextChanged.connect(self._on_settings_changed)
        self.spin_offset_x.valueChanged.connect(self._on_settings_changed)
        self.spin_offset_y.valueChanged.connect(self._on_settings_changed)
        self.slider_opacity_img.valueChanged.connect(self._on_settings_changed)
        
        # Buttons
        self.btn_select_banner.clicked.connect(self.select_banner_image)
        self.image_button_img.clicked.connect(self.select_images)
        self.watermark_button_img.clicked.connect(self.apply_watermark_to_all)
        self.cancel_button_img.clicked.connect(self.cancel_image_processing)
        
        # Image list
        self.image_list_widget.itemClicked.connect(self.on_thumbnail_click)
        self.image_list_widget.customContextMenuRequested.connect(self.show_image_context_menu)

    def _on_settings_changed(self, _=None):
        is_text_mode = self.radio_text_wm.isChecked()
        self.controls_stack.setCurrentWidget(self.text_controls_widget if is_text_mode else self.image_controls_widget)
        self.update_preview()

    # --- Слоты (обработчики событий) ---

    def select_banner_image(self):
        """Открывает диалог выбора файла для баннера."""
        file, _ = QFileDialog.getOpenFileName(self, "Выберите баннер", "", "Изображения (*.png *.jpg *.jpeg)")
        if file:
            self.banner_path = file
            self.label_banner_path.setText(os.path.basename(file))
            self.update_preview()

    def select_images(self):
        """Открывает диалог выбора изображений для обработки."""
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.gif)")
        if files: self.add_files_to_list(files)

    def add_files_to_list(self, file_list):
        """Добавляет выбранные файлы в список миниатюр."""
        for file_path in file_list:
            if not any(self.image_list_widget.item(i).data(Qt.ItemDataRole.UserRole) == file_path for i in range(self.image_list_widget.count())):
                item = QListWidgetItem(QIcon(QPixmap(file_path)), os.path.basename(file_path))
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.image_list_widget.addItem(item)
        if self.image_list_widget.count() > 0 and self.current_preview_path is None:
            self.on_thumbnail_click(self.image_list_widget.item(0))
        self._update_apply_button_state()

    def on_thumbnail_click(self, item):
        """Обрабатывает клик по миниатюре в списке."""
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.current_preview_path = path
            self.current_base_pillow_image = Image.open(path)
            self.preview_stack.setCurrentWidget(self.preview_label)
            self.update_preview()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить предпросмотр: {e}")
            self.current_preview_path = None
            self.current_base_pillow_image = None
            self.preview_stack.setCurrentWidget(self.preview_label_placeholder)

    def show_image_context_menu(self, position):
        """Показывает контекстное меню (правый клик) для элемента списка."""
        item = self.image_list_widget.itemAt(position)
        if not item: return
        menu = QMenu()
        delete_action = menu.addAction("🗑️ Удалить")
        action = menu.exec(self.image_list_widget.mapToGlobal(position))
        if action == delete_action: self.delete_selected_image(item)

    def delete_selected_image(self, item_to_delete):
        """Удаляет выбранную картинку из списка."""
        path_to_delete = item_to_delete.data(Qt.ItemDataRole.UserRole)
        self.image_list_widget.takeItem(self.image_list_widget.row(item_to_delete))
        if path_to_delete == self.current_preview_path:
            self.current_preview_path = None
            self.current_base_pillow_image = None
            if self.image_list_widget.count() > 0:
                self.on_thumbnail_click(self.image_list_widget.item(0))
            else:
                self.preview_stack.setCurrentWidget(self.preview_label_placeholder)
        self._update_apply_button_state()

    # --- Основная логика ---

    def update_preview(self):
        """Обновляет изображение в окне предпросмотра."""
        if self.current_base_pillow_image is None: return
        params = self.get_current_params()
        watermarked_pillow_image = apply_watermark_to_pillow_image(self.current_base_pillow_image, params)
        q_image = ImageQt(watermarked_pillow_image.convert('RGBA'))
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled_pixmap)

    def apply_watermark_to_all(self):
        """Запускает процесс наложения водяных знаков на все изображения в списке."""
        if self.image_list_widget.count() == 0: return
        params = self.get_current_params()
        if params.watermark_type == "text" and not params.text:
            QMessageBox.warning(self, "Внимание", "Введите текст водяного знака."); return
        if params.watermark_type == "image" and not params.image_path:
            QMessageBox.warning(self, "Внимание", "Выберите файл изображения для баннера."); return
        output_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if not output_dir: return

        self.processed_count = 0
        self.progress_bar_img.setMaximum(self.image_list_widget.count())
        self.reset_processing_state(is_processing=True)
        self.image_threads = []

        for i in range(self.image_list_widget.count()):
            image_file = self.image_list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            base_name, ext = os.path.splitext(os.path.basename(image_file))
            result_file = os.path.join(output_dir, f"watermarked_{base_name}{ext}")
            thread = ImageProcessingThread(image_file, result_file, params)
            thread.finished_one.connect(self.on_image_finished)
            thread.error.connect(self.on_image_error)
            self.image_threads.append(thread)
            thread.start()

    @pyqtSlot(str)
    def on_image_finished(self, result_file):
        """Слот, который вызывается, когда один поток успешно завершил работу."""
        self.processed_count += 1
        self.progress_bar_img.setValue(self.processed_count)
        if self.processed_count == len(self.image_threads):
            QMessageBox.information(self, "Успех!", "Все изображения успешно обработаны.")
            self.reset_processing_state()
            self.save_settings()

    @pyqtSlot(str)
    def on_image_error(self, error_message):
        """Слот, который вызывается, если в потоке произошла ошибка."""
        QMessageBox.warning(self, "Ошибка обработки", error_message)
        self.processed_count += 1
        self.progress_bar_img.setValue(self.processed_count)
        if self.processed_count == len(self.image_threads):
            QMessageBox.information(self, "Завершено", "Обработка завершена с ошибками.")
            self.reset_processing_state()
    
    def cancel_image_processing(self):
        """Отменяет все запущенные потоки обработки."""
        for thread in self.image_threads: thread.stop()
        self.reset_processing_state()
        QMessageBox.information(self, "Отмена", "Обработка была отменена.")

    # --- Вспомогательные функции ---

    def get_current_params(self) -> WatermarkParams:
        """Собирает все настройки со всех виджетов в один объект WatermarkParams."""
        return WatermarkParams(
            watermark_type="image" if self.radio_image_wm.isChecked() else "text", text=self.input_watermark_img.text(),
            position=self.combo_position_img.currentText(), opacity=self.slider_opacity_img.value(),
            font_name=self.combo_font_img.currentText(), font_size_relative=self.spin_font_size_img.value(),
            offset_x=self.spin_offset_x.value(), offset_y=self.spin_offset_y.value(),
            image_path=self.banner_path, image_scale=self.spin_banner_scale.value()
        )
    
    def reset_processing_state(self, is_processing=False):
        """Переключает состояние интерфейса (в обработке / ожидание)."""
        self.progress_bar_img.setVisible(is_processing)
        self.cancel_button_img.setEnabled(is_processing)
        self.watermark_button_img.setEnabled(not is_processing)
        if not is_processing:
            self.progress_bar_img.setValue(0)
            self.processed_count = 0
            self.image_threads = []
            self._update_apply_button_state()
            
    def _update_apply_button_state(self):
        """Включает или выключает кнопку 'Применить' в зависимости от того, есть ли картинки в списке."""
        self.watermark_button_img.setEnabled(self.image_list_widget.count() > 0)

    def load_settings(self):
        """Загружает настройки при старте приложения."""
        self.input_watermark_img.setText(self.settings.value("text_watermark", "Watermark"))
        self.combo_position_img.setCurrentText(self.settings.value("position", "Центр"))
        self.slider_opacity_img.setValue(self.settings.value("opacity", 128, type=int))
        self.combo_font_img.setCurrentText(self.settings.value("font_name", "Arial"))
        self.spin_font_size_img.setValue(self.settings.value("font_size", 10, type=int))
        self.spin_offset_x.setValue(self.settings.value("offset_x", 0, type=int))
        self.spin_offset_y.setValue(self.settings.value("offset_y", 0, type=int))
        self.banner_path = self.settings.value("banner_path", "")
        if self.banner_path and os.path.exists(self.banner_path):
            self.label_banner_path.setText(os.path.basename(self.banner_path))
        else:
            self.label_banner_path.setText("Файл не выбран")
        self.spin_banner_scale.setValue(self.settings.value("banner_scale", 25, type=int))
        wm_type = self.settings.value("wm_type", "text")
        if wm_type == 'image': self.radio_image_wm.setChecked(True)
        else: self.radio_text_wm.setChecked(True)
        self._on_settings_changed()

    def save_settings(self):
        """Сохраняет текущие настройки."""
        self.settings.setValue("wm_type", "image" if self.radio_image_wm.isChecked() else "text")
        self.settings.setValue("text_watermark", self.input_watermark_img.text())
        self.settings.setValue("position", self.combo_position_img.currentText())
        self.settings.setValue("opacity", self.slider_opacity_img.value())
        self.settings.setValue("font_name", self.combo_font_img.currentText())
        self.settings.setValue("font_size", self.spin_font_size_img.value())
        self.settings.setValue("offset_x", self.spin_offset_x.value())
        self.settings.setValue("offset_y", self.spin_offset_y.value())
        self.settings.setValue("banner_path", self.banner_path)
        self.settings.setValue("banner_scale", self.spin_banner_scale.value())
