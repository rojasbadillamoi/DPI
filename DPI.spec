# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('species_profiles.json', '.'), ('iconos\\dpi.ico', 'iconos')]
binaries = []
hiddenimports = ['PyQt6.QtPrintSupport', 'pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt6', 'pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt6', 'pyqtgraph.imageview.ImageViewTemplate_pyqt6', 'pandas._libs.tslibs.np_datetime', 'pandas._libs.tslibs.nattype', 'pandas._libs.tslibs.timedeltas', 'scipy.special._cython_special']
# Backends de matplotlib para la descarga de gráficos. Solo `backend_agg`
# aparece en un import del código; los de SVG y PDF los resuelve matplotlib en
# caliente al mirar la extensión del archivo, así que PyInstaller no los ve y
# sin declararlos acá esos dos formatos fallarían únicamente en el .exe.
hiddenimports += ['matplotlib.backends.backend_agg',
                  'matplotlib.backends.backend_svg',
                  'matplotlib.backends.backend_pdf']
tmp_ret = collect_all('pyqtgraph')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main_anillos.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['iconos\\dpi.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DPI',
)
