# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller のビルド定義。

## --onedir を選ぶ理由（--onefile にしない）

--onefile は実行のたびに `/var/folders` 配下へ全展開してから起動するため、
起動が遅く、macOS の `.app` バンドル構造（Contents/MacOS/ に実行体、
Contents/Resources/ にリソース、という決まった形）とも相性が悪い。
--onedir は「フォルダの中に実行体と付属ファイルがそのまま並ぶ」構造なので、
`.app` バンドルへそのまま素直に収まる。

## --windowed を選ぶ理由

コンソール窓を出すと、ターミナルに詳しくない家族には「黒い画面」が
不安な見た目になる。かわりに `ui.py` の Tk 窓を表示の主役にする。

## ⛔ 内部の実行体ファイル名を ASCII にする理由（実機で踏んだ罠）

`.app` フォルダ名や Finder 表示名（`CFBundleName`）は日本語のままでよいが、
`Contents/MacOS/` の下に置かれる**実行体そのもののファイル名**を日本語にすると、
このマシン（macOS 26.5.2）では `codesign --deep` がクラッシュする
（`-10` エラー・シグナル由来の異常終了）。個別に signing し直しても、
バンドル全体のリソース封印が最後まで一貫しない状態になる。

ASCII 名（`animal-bomber-server`）に変えたところ問題なく署名できた
（`codesign --verify --strict` が通る）ため、実行体名だけ ASCII に固定した。
`EXE(name=...)` は実行体名、`BUNDLE(name=...)` は `.app` フォルダ名で、
両者は独立して指定できる——ここを利用して見た目は変えず内側だけ修正している。
"""

import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None


def _source_html():
    """取り込む animal-bomber.html の在り処を返す。

    リポジトリでは原型の HTML を `legacy/` に隔離しているが、作業用の
    ツリーでは `server/` と並んで置かれている。`main.py` の
    `_default_html_path()` と同じ2通りを同じ順で探し、実在するほうを採る。
    """
    here = SPECPATH  # PyInstaller が spec 実行時に注入する。spec のあるディレクトリ
    candidates = (
        os.path.join(here, os.pardir, 'legacy', 'animal-bomber.html'),
        os.path.join(here, os.pardir, 'animal-bomber.html'),
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError('animal-bomber.html が見つからない: %s' % (candidates,))

a = Analysis(
    ['gui_entry.py'],
    pathex=['src'],
    binaries=[],
    # animal-bomber.html をバンドルのルート（sys._MEIPASS 直下）に置く。
    # main.py の _default_html_path() が Path(sys._MEIPASS) / "animal-bomber.html"
    # を見に行く前提と、この配置先を必ず一致させること。
    # 取り込み元は _default_html_path() と同じ2通りを同じ順で探す
    datas=[(_source_html(), '.')],
    hiddenimports=collect_submodules('websockets'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='animal-bomber-server',  # ⛔ ASCII 固定（理由は上のコメント）
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --windowed 相当。Tk の窓が主役になる
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='animal-bomber-server',
)

app = BUNDLE(
    coll,
    name='どうぶつボンバー LAN対戦サーバ.app',
    icon=None,
    bundle_identifier='dev.nakata.animal-bomber-server',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'どうぶつボンバー LAN対戦サーバ',
        'CFBundleDisplayName': 'どうぶつボンバー LAN対戦サーバ',
        'NSHighResolutionCapable': True,
        # macOS 15+ はローカルネットワーク内の他端末を探す挙動（mDNS 含む）に
        # 許可を要求する。これが無いとゲストが繋げず、症状が「原因不明の
        # 接続失敗」に見える（ダイアログ自体が出ないこともある）
        'NSLocalNetworkUsageDescription':
            'LAN 内の家族の Mac と対戦するために、同じネットワーク上の'
            '機器を検出します。',
        # Bonjour（mDNS）でサービスを名乗るための宣言。
        # 上の使用許諾と対になる（サービスの型を宣言しないと mDNS 応答が届かない
        # 実装がある）
        'NSBonjourServices': ['_http._tcp', '_ws._tcp'],
    },
)
