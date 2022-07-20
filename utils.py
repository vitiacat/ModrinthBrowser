import os


def find_mc_paths():

    # minecraft
    paths = ['~/.minecraft', '~/Library/Application Support/minecraft', '%APPDATA%\.minecraft']
    exists = []
    for path in paths:
        if os.path.exists(os.path.expandvars(os.path.expanduser(path))):
            exists.append(path)

    # multimc
    multimc_paths = ['~/.local/share/multimc/instances', '%APPDATA%\.local\share\multimc\instances']
    for path in multimc_paths:
        a = os.path.expandvars(os.path.expanduser(path))
        if os.path.exists(a):
            for dir in os.listdir(a):
                dir = os.path.join(dir, '.minecraft')
                if os.path.isdir(os.path.join(a, dir)):
                    exists.append(os.path.join(a, dir))

    return exists
