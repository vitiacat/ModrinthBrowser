import dataclasses
import json
import os.path
import sys

import grequests
import requests
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QThread, QUrl, QTimer, pyqtSignal, QObject, pyqtProperty
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QMainWindow, QProgressBar, QTextBrowser, QLabel, QToolButton, QLineEdit, \
    QComboBox, QCheckBox
from PyQt5.QtGui import QIcon, QDesktopServices, QCursor

import utils
from settings import Settings
from windows.main_window import Ui_MainWindow
from windows.view import Ui_Dialog as ViewDialog
from windows.download import Ui_Dialog as DownloadDialog
from windows.progress import Ui_Dialog as ProgressDialog
from windows.settings import Ui_Dialog as SettingsDialog


@dataclasses.dataclass
class ModInfo:
    project_id: str
    title: str
    versions: list
    downloads: int
    follows: int
    author: str
    client_side: str
    server_side: str


def format_int(num):
    return "{:,}".format(num)


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def open_link(url):
    QDesktopServices.openUrl(QUrl(url))


categories = {
    "adventure": "Приключения",
    "cursed": "Cursed",
    "decoration": "Декоративные",
    "equipment": "Экипировка",
    "food": "Еда",
    "library": "Библиотеки",
    "magic": "Магия",
    "misc": "Разное",
    "optimization": "Оптимизация",
    "storage": "Хранилища",
    "technology": "Технологии",
    "utility": "Утилиты",
    "worldgen": "Генерация мира",
}


class Document(QObject):
    textChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_text = ""

    def get_text(self):
        return self.m_text

    def set_text(self, text):
        if self.m_text == text:
            return
        self.m_text = text
        self.textChanged.emit(self.m_text)

    text = pyqtProperty(str, fget=get_text, fset=set_text, notify=textChanged)

class ModrinthBrowser(QMainWindow):

    def get_menu(self, is_view, item):
        main_menu = QtWidgets.QMenu(self)
        if not is_view:
            main_menu.addAction('Открыть', lambda: self.open_mod(item))
        main_menu.addAction('Загрузить', lambda: self.open_mod_download(item))
        return main_menu

    def __init__(self):
        super(ModrinthBrowser, self).__init__()  # Call the inherited classes __init__ method
        Ui_MainWindow().setupUi(self)

        self.statusBar().showMessage('Загрузка версий Minecraft...')
        r = requests.get('https://launchermeta.mojang.com/mc/game/version_manifest.json')
        self.mc_versions = r.json()
        self.mc_versions = filter(lambda v: v['type'] == 'release', self.mc_versions['versions'])

        self.list: QtWidgets.QTableWidget = self.findChild(QtWidgets.QTableWidget, 'list')
        self.searchBar: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, 'searchBar')
        self.settings_button: QtWidgets.QAction = self.findChild(QtWidgets.QAction, 'settings')

        self.version: QComboBox = self.findChild(QComboBox, 'version')
        self.version.addItems(list(map(lambda v: v['id'], self.mc_versions)))
        self.version.currentTextChanged.connect(lambda text: (self.searchTime.stop(), self.searchTime.start(350)))

        self.category: QComboBox = self.findChild(QComboBox, 'category')
        self.category.addItems(list(categories.values()))

        self.category.currentTextChanged.connect(lambda text: (self.searchTime.stop(), self.searchTime.start(350)))

        self.settings_button.triggered.connect(self.open_settings)

        self.page: QtWidgets.QSpinBox = self.findChild(QtWidgets.QSpinBox, 'page')

        self.searchTime = QTimer(self)
        self.searchTime.timeout.connect(lambda: self.search(self.page.value()))
        self.searchTime.setSingleShot(True)
        self.searchBar.textEdited.connect(lambda: (self.searchTime.stop(), self.searchTime.start(800)))
        self.page.valueChanged.connect(lambda: (self.searchTime.stop(), self.searchTime.start(500)))

        # strech the columns
        for i in range(self.list.columnCount()):
            self.list.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)
        self.list.setIconSize(QtCore.QSize(32, 32))
        self.list.itemDoubleClicked.connect(self.open_mod)
        self.list.customContextMenuRequested.connect(
            lambda: None if self.list.currentItem() is None else self.get_menu(False, self.list.currentItem()).popup(
                QCursor.pos()))
        self.projects = []

        self.progress_dialog = None
        self.status_progress = QProgressBar(self)
        self.statusBar().addWidget(self.status_progress)
        self.show()
        self.t = None

        self.settings = Settings()

        if not os.path.exists('settings.json'):
            self.open_settings()
        else:
            self.settings.load()
        os.mkdir('cache') if not os.path.exists('cache') else None

        self.search(self.page.value())

    def open_mod(self, item):
        mod = self.projects[item.row()]
        info = requests.get('https://api.modrinth.com/v2/project/' + mod.project_id)
        info = info.json()
        dialog = QtWidgets.QDialog()
        ViewDialog().setupUi(dialog)

        document = Document()
        channel = QWebChannel()
        channel.registerObject("content", document)

        view: QWebEngineView = QWebEngineView()
        dialog.findChild(QtWidgets.QGridLayout, 'gridLayout_2').addWidget(view)
        view.page().setWebChannel(channel)
        view.setUrl(QUrl.fromLocalFile(os.path.join(os.path.dirname(__file__), 'web', 'index.html')))
        document.set_text(info['body'])


        button: QToolButton = dialog.findChild(QToolButton, 'menuButton')
        button.clicked.connect(lambda: self.get_menu(True, item).popup(QCursor.pos()))
        label: QLabel = dialog.findChild(QLabel, 'label')
        label.setText(info['title'])

        #browser: QTextBrowser = dialog.findChild(QTextBrowser, 'textBrowser')
        # browser.anchorClicked.connect(open_link)
        # browser.setMarkdown(info['body'])
        # browser.setOpenLinks(False)
        dialog.exec()

    def open_settings(self):
        dialog = QtWidgets.QDialog()
        SettingsDialog().setupUi(dialog)
        minecraft_path: QLineEdit = dialog.findChild(QLineEdit, 'minecraftPath')
        minecraft_path_variants: QComboBox = dialog.findChild(QComboBox, 'minecraftPathVariants')
        minecraft_path.setText(self.settings.minecraft_path)
        minecraft_path.mousePressEvent = lambda e: self.open_directory_dialog(minecraft_path, check_settings)

        paths = utils.find_mc_paths()
        if len(paths) > 0:
            minecraft_path_variants.addItems(paths)
            minecraft_path_variants.setCurrentText(minecraft_path.text())
            minecraft_path_variants.currentTextChanged.connect(minecraft_path.setText)
        else:
            minecraft_path_variants.setVisible(False)

        icons_in_table: QCheckBox = dialog.findChild(QCheckBox, 'iconsInTable')
        icons_in_table.setChecked(self.settings.icons_in_table)

        rows_count: QComboBox = dialog.findChild(QComboBox, 'rowsCount')
        rows_count.setCurrentText(str(self.settings.rows_count))

        def save_settings():
            self.settings.minecraft_path = minecraft_path.text()
            self.settings.icons_in_table = icons_in_table.isChecked()
            self.settings.rows_count = int(rows_count.currentText())
            self.settings.save()

        def check_settings():
            if minecraft_path.text() == '':
                button_box.button(QtWidgets.QDialogButtonBox.Save).setEnabled(False)
            else:
                button_box.button(QtWidgets.QDialogButtonBox.Save).setEnabled(True)

        button_box: QtWidgets.QDialogButtonBox = dialog.findChild(QtWidgets.QDialogButtonBox, 'buttonBox')
        if not os.path.exists('settings.json'):
            button_box.setStandardButtons(QtWidgets.QDialogButtonBox.Save)
        button_box.accepted.connect(save_settings)
        check_settings()
        dialog.exec()

    def open_directory_dialog(self, line_edit, callback=None):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, 'Выберите папку')
        if directory:
            line_edit.setText(directory)
            if callback is not None:
                callback()

    def open_mod_download(self, item):
        mod = self.projects[item.row()]
        info = requests.get('https://api.modrinth.com/v2/project/' + mod.project_id + '/version')
        info = info.json()
        dialog = QtWidgets.QDialog()
        DownloadDialog().setupUi(dialog)
        versions: QtWidgets.QTableWidget = dialog.findChild(QtWidgets.QTableWidget, 'versions')
        versions.cellDoubleClicked.connect(lambda row, _: self.download(info[row]['files'][0]['url'],
                                                                        os.path.join(self.settings.minecraft_path,
                                                                                     'mods',
                                                                                     info[row]['files'][0]['url'].split(
                                                                                         '/')[-1]),
                                                                        lambda: dialog.close()))
        for i in range(versions.columnCount()):
            versions.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)
        for version in info:
            versions.insertRow(versions.rowCount())
            row = versions.rowCount() - 1
            versions.setItem(row, 0, QtWidgets.QTableWidgetItem(version['name']))
            versions.setItem(row, 1, QtWidgets.QTableWidgetItem(
                version['game_versions'][0] if len(version['game_versions']) == 1 else (
                            version['game_versions'][0] + ' - ' + version['game_versions'][-1])))
            versions.setItem(row, 2, QtWidgets.QTableWidgetItem(version['version_type']))
            versions.setItem(row, 3, QtWidgets.QTableWidgetItem(format_int(version['downloads'])))
            versions.setItem(row, 4, QtWidgets.QTableWidgetItem(sizeof_fmt(version['files'][0]['size'])))
        dialog.exec()

    def search(self, page):
        self.statusBar().show()
        self.list.clearContents()
        self.list.setRowCount(0)
        self.projects = []
        self.searchBar.setDisabled(True)
        self.page.setDisabled(True)
        text = self.searchBar.text()
        self.t = self.Search(self.settings, page, text, utils.create_facets(
            None if self.version.currentIndex() == 0 else [self.version.currentText()],
            None if self.category.currentIndex() == 0 else [list(categories.keys())[self.category.currentIndex() - 1]]))
        self.t.text.connect(self.statusBar().showMessage)
        self.t.result.connect(self.add_to_list)
        self.t.end.connect(self.search_end)
        self.t.start()

    def download(self, url, path, callback=None):
        self.progress_dialog = QtWidgets.QDialog()
        ProgressDialog().setupUi(self.progress_dialog)
        self.progress_dialog.setWindowFlag(QtCore.Qt.CustomizeWindowHint, True)
        self.progress_dialog.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.t = self.DownloadFile(url, path)
        p = self.progress_dialog.findChild(QtWidgets.QProgressBar, 'progressBar')
        label = self.progress_dialog.findChild(QtWidgets.QLabel, 'progressLabel')
        self.t.progress.connect(lambda x, total: (p.setValue(int(x / total * 100)),
                                                  label.setText(f'{sizeof_fmt(x)} / {sizeof_fmt(total)}')))
        self.t.end.connect(lambda: (self.progress_dialog.close(), callback() if callback is not None else None))
        self.t.start()
        self.progress_dialog.exec()

    def search_end(self, total):
        self.statusBar().hide()
        self.searchBar.setDisabled(False)
        self.page.setDisabled(False)
        self.page.setMaximum(total // self.settings.rows_count + 1)
        self.page.setSuffix(f' страница / {self.page.maximum()} стр.')

    def add_to_list(self, mod: ModInfo, i, count):
        self.projects.append(mod)
        icon = QIcon('cache/' + mod.project_id)
        item = QtWidgets.QTableWidgetItem()
        item.setSizeHint(QtCore.QSize(64, 64))
        item.setIcon(icon)
        self.list.insertRow(self.list.rowCount())
        count_ = self.list.rowCount() - 1
        self.list.setItem(count_, 0, item)
        self.list.setItem(count_, 1, QtWidgets.QTableWidgetItem(mod.title))
        self.list.setItem(count_, 2, QtWidgets.QTableWidgetItem(mod.versions[0] + ' - ' + mod.versions[-1]))
        self.list.setItem(count_, 3, QtWidgets.QTableWidgetItem(format_int(mod.downloads)))
        self.list.setItem(count_, 4, QtWidgets.QTableWidgetItem(format_int(mod.follows)))
        self.list.setItem(count_, 5, QtWidgets.QTableWidgetItem(mod.client_side))
        self.list.setItem(count_, 6, QtWidgets.QTableWidgetItem(mod.server_side))
        self.list.setItem(count_, 7, QtWidgets.QTableWidgetItem(mod.author))
        self.list.setItem(count_, 8, QtWidgets.QTableWidgetItem(mod.project_id))
        self.status_progress.setValue(int(i / count * 100))

    class DownloadFile(QThread):

        progress = pyqtSignal(int, int)
        end = pyqtSignal()

        def __init__(self, url, path):
            super(ModrinthBrowser.DownloadFile, self).__init__()
            self.url = url
            self.path = path

        def run(self):
            try:
                r = requests.get(self.url, stream=True)
                total_length = int(r.headers.get('content-length'))
                i = 0
                with open(self.path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=4096):
                        if chunk:
                            f.write(chunk)
                            i += len(chunk)
                            self.progress.emit(i, total_length)
            except Exception as e:
                print(e)
            self.end.emit()

    class Search(QThread):

        result: pyqtSignal = pyqtSignal(ModInfo, int, int)
        text: pyqtSignal = pyqtSignal(str)
        end: pyqtSignal = pyqtSignal(int)
        query = None

        def __init__(self, settings, page=1, query=None, facets=None):
            QThread.__init__(self)
            self.settings = settings
            self.query = query
            self.page = page
            self.facets = facets

        def run(self):
            self.text.emit('Получение списка модов...')
            response = requests.get('https://api.modrinth.com/v2/search?limit=' + str(self.settings.rows_count) +
                                    ('&query=' + self.query if self.query else '') +
                                    '&offset=' + str((self.page - 1) * self.settings.rows_count) +
                                    ('&facets=' + json.dumps(self.facets) if self.facets else ''))
            data = response.json()
            print(response.json())
            icons = []
            mods = []
            r = 1
            if 'error' in data:
                self.text.emit('Ошибка: ' + data['description'])
                return
            for i in data['hits']:
                path = 'cache/' + i['project_id']
                if not os.path.exists(path) and self.settings.icons_in_table:
                    # check if url is valid
                    if i['icon_url'] not in ['', 'null', None]:
                        print('Added icon: ' + i['icon_url'])
                        icons.append(i['icon_url'])
                        # self.parent.download(i['icon_url'], 'cache/' + i['project_id'])
                        # response = requests.get(i['icon_url'])
                        # with open('cache/' + i['project_id'], 'wb') as f:
                        #     f.write(response.content)
                    else:
                        print('Invalid icon url: ' + i['icon_url'] + ' in project ' + i['project_id'])
                mods.append(
                    ModInfo(i['project_id'], i['title'], i['versions'], i['downloads'], i['follows'], i['author'],
                            i['client_side'], i['server_side']))
            self.text.emit('Скачивание иконок...')
            response = (grequests.get(url) for url in icons)
            response = grequests.map(response)
            for resp in response:
                if resp is not None:
                    with open(os.path.join('cache', resp.url.split('/')[-2]), 'wb') as f:
                        f.write(resp.content)
                        print('Downloaded icon: ' + resp.url)
            self.text.emit('')
            for mod in mods:
                self.result.emit(mod, r, len(data['hits']))
                r += 1
            self.end.emit(data['total_hits'])


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ModrinthBrowser()
    sys.exit(app.exec())
