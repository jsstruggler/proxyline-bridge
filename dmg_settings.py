import os

# The name of the DMG volume
volume_name = 'Proxyline Bridge'

# DMG format
format = 'UDBZ'

# Size of the disk image
size = None

# Symlinks to create
symlinks = {
    'Applications': '/Applications',
}

# The folder containing the app
files = [
    'dist/ProxylineBridge.app'
]

# Window settings
window_rect = ((100, 100), (600, 400))
background = 'builtin-arrow'
default_view = 'icon-view'

# Icon layout
icon_locations = {
    'ProxylineBridge.app': (140, 120),
    'Applications': (500, 120)
}
