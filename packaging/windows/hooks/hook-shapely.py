# PyInstaller hook for shapely on Windows.
#
# Shapely wheels bundle GEOS binaries; this hook ensures those binaries and data
# files are collected into the frozen app.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("shapely")

