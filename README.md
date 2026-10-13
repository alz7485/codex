# FormDesigner 利用用パッケージ

AVEVA E3D向けのPMLフォームを設計する日本語のデスクトップアプリです。
更新版 `e63284f` を基に、アプリ・マニュアル・サンプル・Windows EXE作成手順をまとめています。

このZIPはPython版です。起動にはPython 3.12と依存パッケージが必要です。
ビルド済みWindows EXEは含みません。E3D 4.0実機での互換性は未検証です。

## Windowsで起動

Python 3.12をインストールし、ZIPを展開します。
`requirements.txt` のあるフォルダーをPowerShellで開き、次を実行します。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m e3d_designer
```

初回の依存パッケージ導入にはネット接続が必要です。
次回からは最後の起動コマンドだけで開けます。

## Linuxで起動

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m e3d_designer
```

画面操作にはデスクトップ環境が必要です。

## マニュアルとサンプル

「新規・開く」などがある操作列の右端の❔、またはF1で同梱マニュアルを開きます。

- [詳しい操作マニュアル](MANUAL.md)
- [ブラウザー版](docs/manual/index.html)（展開後に開きます）
- [PDF版](docs/manual/FormDesigner-Manual.pdf)
- [基本操作](USER_GUIDE.txt)
- [最初のフォームのサンプル](examples/manual/README.md)

「開く」で `examples/equipmenttool.json` を選ぶと基本フォームを試せます。
DBセレクタ・NET部品・ツールバーの例も `examples` に収録しています。
継続編集はJSONに保存し、E3Dへ渡すコードはMACへ出力します。
画像や外部マクロ・DLLを使う場合は、使用先で読めるように配置してください。

## Windows用EXEを作る

Windowsで次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_onedir.ps1
```

生成先は `dist/FormDesigner` です。配布するときは、そのフォルダー全体をZIPにします。
詳しくは [EXE_BUILD_ONEDIR.txt](EXE_BUILD_ONEDIR.txt) を参照してください。
Windows EXEのビルドはこのクラウド環境では未検証です。

配布フォルダーの構成を保って使用してください。
使用者ごとの `settings.json` や復元データは、起動後にアプリが作成します。

元のソース版: https://github.com/alz7485/codex/tree/e63284fc5b64f76f589b8c2e7201f39995de3ff4
