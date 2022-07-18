import json


class Settings:

    def __init__(self):
        self.icons_in_table = True
        self.minecraft_path = ''
        self.rows_count = 20

    def load(self):
        with open('settings.json', 'r') as f:
            data = json.load(f)
            self.minecraft_path = data['minecraft_path']
            self.icons_in_table = data['icons_in_table']
            self.rows_count = data['rows_count']

    def save(self):
        with open('settings.json', 'w') as f:
            json.dump({'minecraft_path': self.minecraft_path,
                       'icons_in_table': self.icons_in_table,
                       'rows_count': self.rows_count}, f)
