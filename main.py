import dataclasses
import json
import os.path
import sys
import time

import grequests
import requests
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QThread, QUrl, QTimer, pyqtSignal, QObject, pyqtProperty, QLibraryInfo, QTranslator
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import QApplication, QMainWindow, QProgressBar, QTextBrowser, QLabel, QToolButton, QLineEdit, \
    QComboBox, QCheckBox, QDialogButtonBox, QPushButton, QMessageBox
from PyQt5.QtGui import QIcon, QDesktopServices, QCursor

import utils
from settings import Settings
from windows.main_window import Ui_MainWindow
from windows.view import Ui_Dialog as ViewDialog
from windows.download import Ui_Dialog as DownloadDialog
from windows.progress import Ui_Dialog as ProgressDialog
from windows.settings import Ui_Dialog as SettingsDialog
from windows.create_pack import Ui_Dialog as CreatePackDialog
from windows.pack_view import Ui_Dialog as PackViewDialog
from pack import load_packs, save_packs, packs, create_pack, delete_pack, rename_pack, PackMod


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


translate = QtCore.QCoreApplication.translate


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


class DownloadFile(QThread):
    progress = pyqtSignal(int, int)
    end = pyqtSignal()

    def __init__(self, url, path):
        super().__init__()
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
            print('Downloaded:', self.path)
        except Exception as e:
            print(e)
        self.end.emit()


class ModrinthBrowser(QMainWindow):

    def get_menu(self, is_view, item):
        main_menu = QtWidgets.QMenu(self)
        if not is_view:
            main_menu.addAction(self.tr('Открыть'), lambda: self.open_mod(item))
        main_menu.addAction(self.tr('Загрузить'), lambda: self.open_mod_download(item))
        a = main_menu.addMenu(self.tr('Добавить в сборку'))
        for pack in packs:
            a.addAction(pack.name, lambda: self.add_mod_to_pack(item, pack))
        return main_menu

    def __init__(self):
        super(ModrinthBrowser, self).__init__()  # Call the inherited classes __init__ method
        Ui_MainWindow().setupUi(self)

        self.categories = {
            "adventure": translate('categories', "Приключения"),
            "cursed": translate('categories', "Cursed"),
            "decoration": translate('categories', "Декоративные"),
            "equipment": translate('categories', "Экипировка"),
            "food": translate('categories', "Еда"),
            "library": translate('categories', "Библиотеки"),
            "magic": translate('categories', "Магия"),
            "misc": translate('categories', "Разное"),
            "optimization": translate('categories', "Оптимизация"),
            "storage": translate('categories', "Хранилища"),
            "technology": translate('categories', "Технологии"),
            "utility": translate('categories', "Утилиты"),
            "worldgen": translate('categories', "Генерация мира"),
        }

        self.statusBar().showMessage(self.tr('Загрузка версий Minecraft...'))
        r = requests.get('https://launchermeta.mojang.com/mc/game/version_manifest.json')
        self.mc_versions = r.json()
        self.mc_versions = list(filter(lambda v: v['type'] == 'release', self.mc_versions['versions']))

        self.list: QtWidgets.QTableWidget = self.findChild(QtWidgets.QTableWidget, 'list')
        self.searchBar: QtWidgets.QLineEdit = self.findChild(QtWidgets.QLineEdit, 'searchBar')
        self.settings_button: QtWidgets.QAction = self.findChild(QtWidgets.QAction, 'settings')
        self.create_pack: QtWidgets.QAction = self.findChild(QtWidgets.QAction, 'createPack')
        self.create_pack.triggered.connect(self.open_create_pack)
        self.packs_menu = self.findChild(QtWidgets.QMenu, 'packsMenu')
        self.packs_actions = []

        self.version: QComboBox = self.findChild(QComboBox, 'version')
        self.version.addItems(list(map(lambda v: v['id'], self.mc_versions.copy())))
        self.version.currentTextChanged.connect(
            lambda text: (self.page.setValue(0), self.searchTime.stop(), self.searchTime.start(350)))
        self.category: QComboBox = self.findChild(QComboBox, 'category')
        self.category.addItems(list(self.categories.values()))

        self.category.currentTextChanged.connect(
            lambda text: (self.page.setValue(0), self.searchTime.stop(), self.searchTime.start(350)))

        self.settings_button.triggered.connect(self.open_settings)

        self.page: QtWidgets.QSpinBox = self.findChild(QtWidgets.QSpinBox, 'page')
        self.minusPage: QToolButton = self.findChild(QToolButton, 'minusPage')
        self.plusPage: QToolButton = self.findChild(QToolButton, 'plusPage')
        self.minusPage.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        self.plusPage.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))

        self.searchTime = QTimer(self)
        self.searchTime.timeout.connect(lambda: self.search(self.page.value()))
        self.searchTime.setSingleShot(True)
        self.searchBar.textEdited.connect(
            lambda: (self.page.setValue(0), self.searchTime.stop(), self.searchTime.start(800)))
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
        if not os.path.exists('packs.json'):
            save_packs()
        else:
            load_packs()
        os.mkdir('cache') if not os.path.exists('cache') else None

        self.update_packs()
        self.search(self.page.value())

    def open_mod(self, item):
        if type(item) == QtWidgets.QTableWidgetItem:
            mod = self.projects[item.row()]
            project_id = mod.project_id
        elif type(item) == str:
            project_id = item
        else:
            return
        info = requests.get('https://api.modrinth.com/v2/project/' + project_id)
        info = info.json()
        dialog = QtWidgets.QDialog()
        ViewDialog().setupUi(dialog)

        document = Document()
        channel = QWebChannel()
        channel.registerObject("content", document)

        view: QWebEngineView = QWebEngineView()
        dialog.findChild(QtWidgets.QGridLayout, 'gridLayout_2').addWidget(view)
        view.page().setWebChannel(channel)
        view.setUrl(QUrl.fromLocalFile(os.path.join(os.getcwd(), 'web', 'index.html')))

        def check_url(url: QUrl):
            if url.host() == 'modrinth.com':
                if url.path().split('/')[1] == 'mod':
                    # i dont know better way to cancel loading
                    view.stop()
                    view.back()
                    self.open_mod(url.path().split('/')[2])

        view.page().urlChanged.connect(check_url)
        view.page().setZoomFactor(0.85)
        document.set_text(info['body'])

        button: QToolButton = dialog.findChild(QToolButton, 'menuButton')
        button.clicked.connect(lambda: self.get_menu(True, item).popup(QCursor.pos()))
        label: QLabel = dialog.findChild(QLabel, 'label')
        label.setText(info['title'])

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
            minecraft_path_variants.addItems([''] + paths)
            minecraft_path_variants.setCurrentText(minecraft_path.text())
            minecraft_path_variants.currentTextChanged.connect(lambda text: (minecraft_path.setText(text),
                                                                             check_settings()))
        else:
            minecraft_path_variants.setVisible(False)

        icons_in_table: QCheckBox = dialog.findChild(QCheckBox, 'iconsInTable')
        icons_in_table.setChecked(self.settings.icons_in_table)

        rows_count: QComboBox = dialog.findChild(QComboBox, 'rowsCount')
        rows_count.setCurrentText(str(self.settings.rows_count))

        loader_type: QComboBox = dialog.findChild(QComboBox, 'loaderType')
        if self.settings.loader_type is not None:
            loader_type.setCurrentText(self.settings.loader_type.capitalize())

        languages = {
            'en': 'English',
            'ru': 'Русский',
        }

        language: QComboBox = dialog.findChild(QComboBox, 'language')
        language.addItems(languages.values())
        if self.settings.language is not None:
            language.setCurrentText(languages[self.settings.language])
        else:
            language.setCurrentText(languages.get(locale.name().split('_')[0], 'English'))

        def save_settings():
            if not os.path.exists(os.path.join(minecraft_path.text(), 'mods')):
                os.mkdir(os.path.join(minecraft_path.text(), 'mods'))

            self.settings.minecraft_path = minecraft_path.text()
            self.settings.icons_in_table = icons_in_table.isChecked()
            self.settings.rows_count = int(rows_count.currentText())
            self.settings.loader_type = loader_type.currentText().lower() if loader_type.currentIndex() != 0 else None
            lang = list(languages.keys())[list(languages.values()).index(language.currentText())]
            prev_lang = self.settings.language
            self.settings.language = lang
            self.settings.save()
            if prev_lang != lang:
                install_translation(QApplication.instance(), lang)
                self.close()
                ModrinthBrowser()

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
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, self.tr('Выберите папку'))
        if directory:
            line_edit.setText(directory)
            if callback is not None:
                callback()

    def open_mod_download(self, item):
        if type(item) == QtWidgets.QTableWidgetItem:
            mod = self.projects[item.row()]
            project_id = mod.project_id
        elif type(item) == str:
            project_id = item
        else:
            return
        info = requests.get('https://api.modrinth.com/v2/project/' + project_id + '/version',
                            params={'loaders': json.dumps([self.settings.loader_type])})
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
            versions.setItem(row, 3, QtWidgets.QTableWidgetItem(', '.join(version['loaders'])))
            versions.setItem(row, 4, QtWidgets.QTableWidgetItem(format_int(version['downloads'])))
            versions.setItem(row, 5, QtWidgets.QTableWidgetItem(sizeof_fmt(version['files'][0]['size'])))

        if versions.rowCount() == 0:
            QMessageBox.information(self, self.tr('Ничего не найдено :('),
                                    self.tr('Не удалось найти версии.') + self.tr(
                                        '\nПроверьте настройку \"Загрузчик\", возможно, данная модификация не поддерживает данный загрузчик.') if self.settings.loader_type is not None else '')
        else:
            dialog.exec()

    def open_create_pack(self):
        dialog = QtWidgets.QDialog()
        CreatePackDialog().setupUi(dialog)
        dialog_box: QDialogButtonBox = dialog.findChild(QDialogButtonBox, 'buttonBox')
        name: QLineEdit = dialog.findChild(QLineEdit, 'name')
        ok = dialog_box.button(QDialogButtonBox.Ok)
        ok.setEnabled(False)
        name.textChanged.connect(lambda: ok.setEnabled(name.text() != ''))
        dialog_box.accepted.connect(lambda: (create_pack(name.text()), self.update_packs()))
        dialog.exec()

    def open_pack(self, name):
        pack = list(filter(lambda x: x.name == name, packs))[0]
        dialog = QtWidgets.QDialog()
        PackViewDialog().setupUi(dialog)
        dialog.setWindowTitle(self.tr('Сборка: {0} ({1} модов)').format(name, len(pack.mods)))
        mods: QtWidgets.QListWidget = dialog.findChild(QtWidgets.QListWidget, 'mods')

        def delete():
            if QtWidgets.QMessageBox.question(self, self.tr('Удаление сборки'),
                                              self.tr('Вы действительно хотите удалить сборку {0}?').format(name),
                                              QtWidgets.QMessageBox.Yes,
                                              QtWidgets.QMessageBox.No) == QtWidgets.QMessageBox.Yes:
                delete_pack(name)
                self.update_packs()
                dialog.close()

        def rename():
            rename_dialog = QtWidgets.QDialog()
            CreatePackDialog().setupUi(rename_dialog)
            rename_dialog.setWindowTitle(self.tr('Переименовать сборку'))
            new_name: QLineEdit = rename_dialog.findChild(QLineEdit, 'name')
            new_name.setText(pack.name)
            dialog_box: QDialogButtonBox = rename_dialog.findChild(QDialogButtonBox, 'buttonBox')
            new_name.textChanged.connect(lambda: dialog_box.button(QDialogButtonBox.Ok)
                                         .setEnabled(new_name.text() != ''))
            dialog_box.accepted.connect(lambda: (
                rename_pack(pack.name, new_name.text()), self.update_packs(), rename_dialog.close(), dialog.close(),
                self.open_pack(new_name.text())))
            rename_dialog.exec()

        def delete_mod():
            pack.delete_mod(mods.currentItem().data(QtCore.Qt.UserRole))
            mods.takeItem(mods.currentRow())
            save_packs()

        def download_mods(version_name, loader_name):
            dialog.setCursor(QtCore.Qt.WaitCursor)
            if QtWidgets.QMessageBox.question(self, self.tr('Скачивание модов'),
                                              self.tr(
                                                  'Сейчас будут загружены моды для версии {0} Minecraft {1}\nПродолжить?').format(
                                                  loader_name, version_name),
                                              QtWidgets.QMessageBox.Yes,
                                              QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
                dialog.setCursor(QtCore.Qt.ArrowCursor)
                dialog.setDisabled(False)
                return

            urls = []
            for mod in pack.mods:
                info = requests.get('https://api.modrinth.com/v2/project/' + mod['project_id'] + '/version')
                info = info.json()
                found = False
                for version_info in info:
                    if version_name in version_info['game_versions'] and loader_name.lower() in version_info['loaders']:
                        urls.append((version_info['files'][0]['url'], version_info['files'][0]['filename']))
                        found = True
                        break
                if not found:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Critical)
                    msg.setText(
                        self.tr('Модификация {0} не содержит версии, которые поддерживают версию {1} Minecraft {2}')
                        .format(mod['name'], loader_name, version_name))
                    msg.setWindowTitle(self.tr('Ошибка'))
                    msg.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ignore)
                    if msg.exec() == QMessageBox.Cancel:
                        dialog.setDisabled(False)
                        dialog.setCursor(QtCore.Qt.ArrowCursor)
                        self.statusBar().showMessage('')
                        return
            for url, filename in urls:
                self.download(url, os.path.join(self.settings.minecraft_path, 'mods', filename))
            QMessageBox.information(self, self.tr('Успешно'), self.tr('Модификации успешно скачаны'))
            dialog.setDisabled(False)
            dialog.setCursor(QtCore.Qt.ArrowCursor)

        menu = QtWidgets.QMenu()
        menu.addAction('Удалить', delete_mod)
        versions_menu = QtWidgets.QMenu()
        for version in list(map(lambda v: v['id'], self.mc_versions)):
            sub_menu = versions_menu.addMenu(version)
            for loader_type in ['Fabric', 'Forge', 'Quilt']:
                sub_menu.addAction(loader_type, lambda v=version, l=loader_type: download_mods(v, l))

        delete_pack_button: QPushButton = dialog.findChild(QPushButton, 'deletePack')
        delete_pack_button.clicked.connect(delete)
        rename_pack_button: QPushButton = dialog.findChild(QPushButton, 'renamePack')
        rename_pack_button.clicked.connect(rename)
        download_mods_button: QPushButton = dialog.findChild(QPushButton, 'downloadMods')
        download_mods_button.clicked.connect(lambda: versions_menu.popup(QCursor.pos()))
        download_mods_button.setEnabled(len(pack.mods) > 0)

        mods.itemDoubleClicked.connect(lambda item: self.open_mod(mods.currentItem().data(QtCore.Qt.UserRole)))
        mods.customContextMenuRequested.connect(lambda: menu.popup(QCursor.pos()) if mods.currentItem() else None)

        for mod in pack.mods:
            a = QtWidgets.QListWidgetItem(mod['name'])
            a.setData(QtCore.Qt.UserRole, mod['project_id'])
            mods.addItem(a)
        dialog.exec()

    def add_mod_to_pack(self, item, pack):
        mod = self.projects[item.row()]
        pack.add_mod(PackMod(mod.project_id, mod.title))
        save_packs()

    def update_packs(self):
        for a in self.packs_actions:
            a.deleteLater()
        self.packs_actions.clear()
        for pack in packs:
            a = self.packs_menu.addAction(pack.name)
            a.triggered.connect(lambda b, p=pack: self.open_pack(p.name))
            self.packs_actions.append(a)

    def search(self, page):
        self.statusBar().show()
        self.list.clearContents()
        self.list.setRowCount(0)
        self.projects = []
        self.searchBar.setDisabled(True)
        self.page.setDisabled(True)
        self.version.setDisabled(True)
        self.category.setDisabled(True)

        text = self.searchBar.text()
        self.t = self.Search(self.settings, page, text, utils.create_facets(
            None if self.version.currentIndex() == 0 else [self.version.currentText()],
            None if self.category.currentIndex() == 0 else [
                list(self.categories.keys())[self.category.currentIndex() - 1]]))
        self.t.text.connect(self.statusBar().showMessage)
        self.t.result.connect(self.add_to_list)
        self.t.end.connect(self.search_end)
        self.t.start()

    def download(self, url, path, callback=None):
        self.progress_dialog = QtWidgets.QDialog()
        ProgressDialog().setupUi(self.progress_dialog)
        self.progress_dialog.setWindowFlag(QtCore.Qt.CustomizeWindowHint, True)
        self.progress_dialog.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.t = DownloadFile(url, path)
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
        self.version.setDisabled(False)
        self.category.setDisabled(False)
        self.page.setDisabled(False)
        self.page.setMaximum(total // self.settings.rows_count + 1)
        self.page.setSuffix(
            self.tr(' страница / {1} страниц').format(self.page.value(), total // self.settings.rows_count + 1))

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
            self.text.emit(self.tr('Получение списка модов...'))
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
                self.text.emit(self.tr('Ошибка: {0}').format(data['description']))
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
            self.text.emit(self.tr('Скачивание иконок...'))

            threads = []
            for i in icons:
                thread = DownloadFile(i, 'cache/' + i.split('/')[-2])
                threads.append(thread)
                thread.start()
                time.sleep(0.1)

            for thread in threads:
                thread.wait()

            self.text.emit('')

            for mod in mods:
                self.result.emit(mod, r, len(data['hits']))
                r += 1

            self.end.emit(data['total_hits'])


translators = []


def install_translation(application, lang: str):
    for translator in translators:
        application.removeTranslator(translator)
    translators.clear()
    if lang == 'ru':
        return
    if lang not in ['en']:
        lang = 'en'
    path = 'translations/' + lang
    print('Installing translation: ' + path)
    if os.path.exists(path):
        for i in os.listdir(path):
            if i.endswith('.qm'):
                name = os.path.splitext(i)[0]
                translator = QTranslator(application)
                translators.append(translator)
                if translator.load(os.path.join(path, name)):
                    application.installTranslator(translator)
                    print('Loaded translation: ' + name)
                else:
                    print('Failed to load translation: ' + name)


locale = QtCore.QLocale()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    if os.path.exists('settings.json'):
        with open('settings.json', 'r') as f:
            settings = json.load(f)
        install_translation(app, settings.get('language', 'en'))
    else:
        print('Using system language:', locale.name().split('_')[0])
        install_translation(app, locale.name().split('_')[0])
    ex = ModrinthBrowser()
    sys.exit(app.exec())
