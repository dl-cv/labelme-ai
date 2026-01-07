# -*- mode: python -*-
# vim: ft=python

import os.path as osp
import sys

import osam._models.yoloworld.clip


sys.setrecursionlimit(5000)  # required on Windows


spec_dir = SPECPATH
repo_root = osp.abspath(osp.join(spec_dir, "..", ".."))

entrypoint = osp.join(spec_dir, "entrypoint.py")
hooks_dir = osp.join(spec_dir, "hooks")
models_glob = osp.join(spec_dir, "_assets", "models", "*.onnx")
icons_glob = osp.join(repo_root, "labelme", "icons", "*")
icon_ico = osp.join(repo_root, "labelme", "icons", "icon.ico")
translate_glob = osp.join(repo_root, "labelme", "translate", "*.qm")

a = Analysis(
    [entrypoint],
    pathex=[repo_root],
    binaries=[],
    datas=[
        (icons_glob, "labelme/icons"),
        (translate_glob, "translate"),
        # Offline AI models (prepared by packaging/windows/build.ps1)
        (models_glob, "models"),
        (
            osp.join(
                osp.dirname(osam._models.yoloworld.clip.__file__),
                "bpe_simple_vocab_16e6.txt.gz",
            ),
            "osam/_models/yoloworld/clip",
        ),
    ],
    hiddenimports=[
        # PyInstaller rthook `pyi_rth_pkgres` imports pkg_resources -> jaraco.*
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
        "jaraco.collections",
    ],
    hookspath=[hooks_dir],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="labelme",
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon=icon_ico,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="labelme",
)

