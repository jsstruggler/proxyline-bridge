#!/bin/bash
echo "Building Proxyline Bridge..."
source venv/bin/activate
pyinstaller -y --clean proxyline-bridge.spec

echo "Building DMG installer..."
dmgbuild -s dmg_settings.py "Proxyline Bridge" dist/ProxylineBridge.dmg

echo "Done! Installer is ready at dist/ProxylineBridge.dmg"
