import json


class Settings:

    def __init__(self):
        self.icons_in_table = True
        self.minecraft_path = ''

    def load(self):
        with open('settings.json', 'r') as f:
            data = json.load(f)
            self.minecraft_path = data['minecraft_path']
            self.icons_in_table = data['icons_in_table']

    def save(self):
        with open('settings.json', 'w') as f:
            json.dump({'minecraft_path': self.minecraft_path,
                       'icons_in_table': self.icons_in_table}, f)