"""Comunicando Clips — editor y detector local para macOS Apple Silicon."""
from __future__ import annotations

import json

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QVBoxLayout, QWidget
)

from engine import Clip, ClipError, download_youtube, duration_for, find_clips, is_youtube_url, render_clip, save_project

STYLE = """
QWidget { background:#10141c; color:#f4f4f4; font-size:13px; }
QMainWindow { background:#10141c; }
QGroupBox { border:1px solid #343b49; margin-top:12px; border-radius:8px; padding:14px 9px 10px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#ffd33d; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QListWidget { background:#1a202b; border:1px solid #3b4656; border-radius:6px; padding:6px; }
QPushButton { background:#2a3343; border:1px solid #465166; padding:8px 12px; border-radius:6px; font-weight:600; }
QPushButton:hover { background:#3d4a61; }
QPushButton:disabled { color:#6f7988; background:#1b2029; }
QPushButton#primary { background:#f3c82d; color:#141414; border:0; }
QPushButton#primary:hover { background:#ffde5e; }
QPushButton#reject { background:#553132; }
QLabel#heading { font-size:27px; font-weight:800; color:#ffdf4b; }
QLabel#muted { color:#aab1bd; }
QListWidget::item { padding:9px; border-bottom:1px solid #343b49; }
QListWidget::item:selected { background:#46516a; }
QProgressBar { border:1px solid #384354; border-radius:6px; height:12px; }
QProgressBar::chunk { background:#f3c82d; }
"""


class TaskThread(QThread):
    info = Signal(str)
    outcome = Signal(object)
    failure = Signal(str)

    def __init__(self, action, *args):
        super().__init__()
        self.action = action
        self.args = args

    def run(self):
        try:
            result = self.action(*self.args, notify=self.info.emit)
            self.outcome.emit(result)
        except Exception as exc:
            self.failure.emit(f'{exc}\n\n{traceback.format_exc(limit=2)}')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Comunicando Clips — Edición local')
        self.resize(1250, 830)
        self.setMinimumSize(980, 690)
        self.video = ''
        self.clips: list[Clip] = []
        self.segments = []
        self.thread = None
        self.busy = False
        self.current_folder = str(Path.home() / 'Movies' / 'Comunicando Clips')

        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setSpacing(13)
        self.setCentralWidget(body)
        title = QLabel('COMUNICANDO CLIPS')
        title.setObjectName('heading')
        outer.addWidget(title)
        subtitle = QLabel('Del video largo a clips verticales. Detecta → revisa → edita → guarda uno por uno.')
        subtitle.setObjectName('muted')
        outer.addWidget(subtitle)

        sourcebox = QGroupBox('1  IMPORTAR VIDEO')
        sl = QVBoxLayout(sourcebox)
        row = QHBoxLayout()
        self.pathbox = QLineEdit()
        self.pathbox.setPlaceholderText('Archivo local o enlace de YouTube…')
        row.addWidget(self.pathbox, 1)
        self.browse = QPushButton('Elegir archivo')
        self.browse.clicked.connect(self.choose_file)
        row.addWidget(self.browse)
        sl.addLayout(row)
        settings = QHBoxLayout()
        self.count = QSpinBox()
        self.count.setRange(1, 15)
        self.count.setValue(15)
        self.minimum = QSpinBox()
        self.minimum.setRange(10, 90)
        self.minimum.setValue(30)
        self.maximum = QSpinBox()
        self.maximum.setRange(20, 120)
        self.maximum.setValue(90)
        self.model = QComboBox()
        self.model.addItems(['base', 'small', 'tiny'])
        for name, widget in [('Clips máx.', self.count), ('Mín. (s)', self.minimum), ('Máx. (s)', self.maximum), ('Voz IA', self.model)]:
            settings.addWidget(QLabel(name))
            settings.addWidget(widget)
        self.analyze = QPushButton('Detectar mejores momentos')
        self.analyze.setObjectName('primary')
        self.analyze.clicked.connect(self.begin_analyze)
        settings.addWidget(self.analyze)
        sl.addLayout(settings)
        outer.addWidget(sourcebox)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        clips_header = QLabel('2  FRAGMENTOS DETECTADOS')
        clips_header.setStyleSheet('font-weight:bold;color:#ffd33d;')
        ll.addWidget(clips_header)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.select_clip)
        ll.addWidget(self.list)
        self.legend = QLabel('Los clips no se guardan hasta que los apruebes.')
        self.legend.setWordWrap(True)
        self.legend.setObjectName('muted')
        ll.addWidget(self.legend)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(300)
        rl.addWidget(self.video_widget, 1)
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.audio.setVolume(0.75)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self.limit_preview)
        pr = QHBoxLayout()
        self.play = QPushButton('▶ Reproducir fragmento')
        self.play.clicked.connect(self.play_clip)
        pr.addWidget(self.play)
        self.pause = QPushButton('⏸ Pausa')
        self.pause.clicked.connect(self.player.pause)
        pr.addWidget(self.pause)
        rl.addLayout(pr)

        editor = QGroupBox('3  REVISAR Y EDITAR ANTES DE GUARDAR')
        edl = QVBoxLayout(editor)
        clip_time = QFormLayout()
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for w in (self.start, self.end):
            w.setRange(0, 999999)
            w.setDecimals(1)
            w.setSingleStep(0.5)
            w.valueChanged.connect(self.update_trim)
        clip_time.addRow('Inicio (segundos):', self.start)
        clip_time.addRow('Final (segundos):', self.end)
        edl.addLayout(clip_time)
        self.subtitles = QCheckBox('Incluir subtítulos automáticos')
        self.subtitles.setChecked(True)
        edl.addWidget(self.subtitles)
        self.layout = QComboBox()
        self.layout.addItem('Recortar al centro (9:16)', 'recortar')
        self.layout.addItem('Fondo difuminado (9:16)', 'difuminado')
        edl.addWidget(self.layout)
        self.summary = QLabel('Selecciona un fragmento para revisarlo.')
        self.summary.setWordWrap(True)
        edl.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.approve = QPushButton('✓ Aprobar y guardar MP4')
        self.approve.setObjectName('primary')
        self.approve.clicked.connect(self.approve_clip)
        buttons.addWidget(self.approve)
        self.reject = QPushButton('Omitir fragmento')
        self.reject.setObjectName('reject')
        self.reject.clicked.connect(self.reject_clip)
        buttons.addWidget(self.reject)
        edl.addLayout(buttons)
        rl.addWidget(editor)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        outer.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.folderbtn = QPushButton('Carpeta de salida…')
        self.folderbtn.clicked.connect(self.choose_folder)
        footer.addWidget(self.folderbtn)
        self.folderlabel = QLabel(self.current_folder)
        self.folderlabel.setObjectName('muted')
        footer.addWidget(self.folderlabel, 1)
        outer.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        outer.addWidget(self.progress)
        self.status = QLabel('Listo. Selecciona un video para comenzar.')
        self.status.setObjectName('muted')
        outer.addWidget(self.status)
        self.toggle_clip_buttons()

        menu = self.menuBar().addMenu('Archivo')
        action = QAction('Elegir video…', self)
        action.triggered.connect(self.choose_file)
        menu.addAction(action)
        reopen = QAction('Abrir proyecto guardado…', self)
        reopen.triggered.connect(self.open_project)
        menu.addAction(reopen)
        self.restore = QPushButton('Abrir proyecto…')
        self.restore.clicked.connect(self.open_project)
        footer.insertWidget(1, self.restore)

    def open_project(self):
        if self.busy:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Abrir proyecto Comunicando Clips', self.current_folder,
            'Proyecto JSON (*.json)')
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding='utf-8'))
            video = data['video']
            if not Path(video).is_file():
                raise ValueError('El archivo de video original ya no existe en esta ubicación.')
            clips = [Clip(**c) for c in data['clips']]
            from engine import SpeechSegment
            segments = [SpeechSegment(**t) for t in data.get('segments', [])]
            if any(c.end <= c.start or c.start < 0 for c in clips):
                raise ValueError('El proyecto contiene tiempos inválidos.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.critical(self, 'No se pudo abrir el proyecto', str(exc))
            return
        self.player.stop()
        self.video, self.clips, self.segments = video, clips, segments
        self.current_folder = str(Path(filename).parent)
        self.folderlabel.setText(self.current_folder)
        self.pathbox.setText(video)
        self.player.setSource(QUrl.fromLocalFile(video))
        self.refresh_list()
        if clips:
            self.list.setCurrentRow(0)
        self.status.setText(f'Proyecto recuperado: {len(clips)} fragmentos.')

    def choose_file(self):
        file, _ = QFileDialog.getOpenFileName(self, 'Seleccionar video', str(Path.home()),
                                              'Videos (*.mp4 *.mov *.mkv *.m4v *.webm *.avi);;Todos (*)')
        if file:
            self.pathbox.setText(file)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta donde guardar clips', self.current_folder)
        if folder:
            self.current_folder = folder
            self.folderlabel.setText(folder)

    def set_busy(self, value: bool, message: str = ''):
        self.busy = value
        self.analyze.setEnabled(not value)
        self.approve.setEnabled(not value and self.selected() is not None and self.selected().status == 'pendiente')
        self.reject.setEnabled(not value and self.selected() is not None and self.selected().status == 'pendiente')
        self.progress.setRange(0, 0 if value else 1)
        if not value:
            self.progress.setValue(1)
        if message:
            self.status.setText(message)

    def start_task(self, operation, args, done):
        if self.busy:
            return
        self.set_busy(True, 'Procesando…')
        worker = TaskThread(operation, *args)
        self.thread = worker
        worker.info.connect(self.status.setText)
        def complete(value):
            self.set_busy(False)
            done(value)
        def failure(msg):
            self.set_busy(False, 'Ocurrió un error. Revisa el mensaje.')
            QMessageBox.critical(self, 'Error de Comunicando Clips', msg)
        worker.outcome.connect(complete)
        worker.failure.connect(failure)
        worker.start()

    def begin_analyze(self):
        source = self.pathbox.text().strip()
        if not source:
            QMessageBox.warning(self, 'Falta video', 'Elige un archivo o pega una URL de YouTube.')
            return
        if self.minimum.value() > self.maximum.value():
            QMessageBox.warning(self, 'Duración', 'El mínimo no puede superar el máximo.')
            return
        Path(self.current_folder).mkdir(parents=True, exist_ok=True)
        if source.startswith(('http://','https://')):
            if not is_youtube_url(source):
                QMessageBox.warning(self, 'YouTube', 'Solo se admiten enlaces válidos de YouTube.')
                return
            self.start_task(download_youtube, (source, self.current_folder), self.downloaded)
        else:
            if not Path(source).is_file():
                QMessageBox.warning(self, 'No existe el archivo', 'El archivo indicado no existe.')
                return
            self.prepare(source)

    def downloaded(self, video):
        self.pathbox.setText(video)
        self.prepare(video)

    def prepare(self, video):
        self.video = video
        self.clips = []
        self.segments = []
        self.list.clear()
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(video))
        self.start_task(find_clips, (video, self.minimum.value(), self.maximum.value(),
                                     self.count.value(), self.model.currentText()), self.detected)

    def detected(self, result):
        self.clips, self.segments = result
        self.refresh_list()
        self.persist()
        self.status.setText(f'{len(self.clips)} fragmentos detectados. Revisa y aprueba individualmente.')
        if self.clips:
            self.list.setCurrentRow(0)

    def refresh_list(self):
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for i, c in enumerate(self.clips):
            icon = {'pendiente':'○', 'guardado':'✓', 'omitido':'✕'}.get(c.status, '○')
            self.list.addItem(QListWidgetItem(f'{icon}  {i+1:02} · {self.clock(c.start)}–{self.clock(c.end)}\n{c.title}'))
        self.list.blockSignals(False)
        if current >= 0 and current < len(self.clips):
            self.list.setCurrentRow(current)

    @staticmethod
    def clock(t):
        return f'{int(t)//60:02}:{int(t)%60:02}'

    def selected(self):
        i = self.list.currentRow()
        return self.clips[i] if 0 <= i < len(self.clips) else None

    def select_clip(self, index):
        clip = self.selected()
        self.player.pause()
        self.preview_timer.stop()
        if clip is None:
            self.summary.setText('Selecciona un clip.')
            self.toggle_clip_buttons()
            return
        self.start.blockSignals(True)
        self.end.blockSignals(True)
        self.start.setValue(clip.start)
        self.end.setValue(clip.end)
        self.start.blockSignals(False)
        self.end.blockSignals(False)
        self.player.setPosition(int(clip.start * 1000))
        self.summary.setText(f'{clip.reason}. Puntaje orientativo: {clip.score:.1f}. Estado: {clip.status}.')
        self.toggle_clip_buttons()

    def update_trim(self):
        clip = self.selected()
        if clip is None or self.busy or clip.status != 'pendiente':
            return
        start, end = self.start.value(), self.end.value()
        if end <= start:
            self.summary.setText('El final debe ser mayor que el inicio.')
            return
        clip.start = start
        clip.end = end
        self.summary.setText(f'Duración editada: {end-start:.1f} segundos. Reproduce para comprobar.')

    def limit_preview(self):
        clip = self.selected()
        if clip and self.player.position() >= int(clip.end * 1000):
            self.player.pause()
            self.preview_timer.stop()

    def play_clip(self):
        clip = self.selected()
        if not clip:
            return
        self.player.setPosition(int(clip.start*1000))
        self.player.play()
        self.preview_timer.start()

    def toggle_clip_buttons(self):
        c = self.selected()
        enabled = c is not None and c.status == 'pendiente' and not self.busy
        self.approve.setEnabled(enabled)
        self.reject.setEnabled(enabled)
        self.play.setEnabled(c is not None)

    def approve_clip(self):
        c = self.selected()
        if not c or c.status != 'pendiente':
            return
        if c.end-c.start < self.minimum.value() or c.end-c.start > self.maximum.value():
            QMessageBox.warning(self, 'Duración inválida',
                f'Los clips deben durar entre {self.minimum.value()} y {self.maximum.value()} segundos.')
            return
        if c.end-c.start < 1:
            QMessageBox.warning(self, 'Duración inválida', 'El clip debe durar al menos un segundo.')
            return
        try:
            total = duration_for(self.video)
        except Exception as exc:
            QMessageBox.critical(self, 'Error', str(exc))
            return
        if c.start < 0 or c.end > total + .1:
            QMessageBox.warning(self, 'Duración inválida', 'El fragmento supera los límites del video.')
            return
        idx = self.list.currentRow()
        stem = f'comunicando_clip_{idx+1:02d}_{int(c.start)}s'
        destination = Path(self.current_folder) / f'{stem}.mp4'
        suffix = 2
        while destination.exists():
            destination = Path(self.current_folder) / f'{stem}_{suffix}.mp4'
            suffix += 1
        output = str(destination)
        # snapshot para que editar mientras se procesa no cambie la exportación
        copy = Clip(c.start, c.end, c.score, c.title, c.reason)
        self.player.pause()
        self.start_task(render_clip, (self.video, copy, list(self.segments), output,
                                      self.subtitles.isChecked(), self.layout.currentData()),
                        lambda _: self.exported(idx, output))

    def exported(self, idx, path):
        self.clips[idx].status = 'guardado'
        self.clips[idx].output = path
        self.persist()
        self.refresh_list()
        self.status.setText(f'Clip guardado: {path}')
        self.next_pending(idx)

    def reject_clip(self):
        i = self.list.currentRow()
        c = self.selected()
        if c is None or c.status != 'pendiente':
            return
        c.status = 'omitido'
        self.persist()
        self.refresh_list()
        self.next_pending(i)

    def next_pending(self, previous):
        for i in list(range(previous+1, len(self.clips))) + list(range(0, previous+1)):
            if self.clips[i].status == 'pendiente':
                self.list.setCurrentRow(i)
                return
        self.list.setCurrentRow(previous)
        self.toggle_clip_buttons()
        saved = sum(c.status == 'guardado' for c in self.clips)
        self.status.setText(f'Revisión terminada. Clips guardados: {saved}.')

    def persist(self):
        if self.video:
            try:
                save_project(self.current_folder, self.video, self.clips, self.segments)
            except OSError as exc:
                self.status.setText(f'No se pudo guardar el proyecto: {exc}')

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, 'Procesando', 'Termina la operación antes de cerrar la aplicación.')
            event.ignore()
            return
        self.preview_timer.stop()
        self.player.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Comunicando Clips')
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
