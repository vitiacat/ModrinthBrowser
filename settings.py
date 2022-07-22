import json


class Settings:

    def __init__(self):
        self.icons_in_table = True
        self.minecraft_path = ''
        self.rows_count = 20
        self.loader_type = None
        self.language = 'ru'

    def load(self):
        with open('settings.json', 'r') as f:
            data: dict = json.load(f)
            self.minecraft_path = data.get('minecraft_path', '')
            self.icons_in_table = data.get('icons_in_table', True)
            self.rows_count = data.get('rows_count', 20)
            self.loader_type = data.get('loader_type', None)
            self.language = data.get('language', 'ru')

    def save(self):
        with open('settings.json', 'w') as f:
            json.dump({'minecraft_path': self.minecraft_path,
                       'icons_in_table': self.icons_in_table,
                       'rows_count': self.rows_count,
                       'loader_type': self.loader_type,
                       'language': self.language}, f)
