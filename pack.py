import json


class Pack:
    def __init__(self, name):
        self.name = name
        self.mods = []

    def add_mod(self, mod):
        self.mods.append(mod.__dict__)


class PackMod:
    def __init__(self, project_id, name):
        self.project_id = project_id
        self.name = name

packs = []


def load_packs():
    global packs
    with open('packs.json', 'r') as f:
        packs_ = json.load(f)
    for pack in packs_:
        p = Pack(pack['name'])
        for mod in pack['mods']:
            p.add_mod(PackMod(mod['project_id'], mod['name']))
        packs.append(p)


def save_packs():
    with open('packs.json', 'w') as f:
        p = []
        for pack in packs:
            p.append(pack.__dict__)
        json.dump(p, f)


def create_pack(name):
    p = Pack(name)
    packs.append(p)
    save_packs()
    return p
