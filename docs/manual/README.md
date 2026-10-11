# 詳細マニュアルの読み方

FormDesigner上部の「新規・開く」などがある操作列の右端の❔、またはF1でブラウザー版を開けます。インターネット接続は不要です。
HTMLが見つからない場合はPDFを開きます。Python版・EXE版とも、アプリと同じフォルダーの `docs/manual` を参照します。

- [ブラウザー版](index.html): ZIPを展開し、index.htmlをブラウザーで開きます。目次・目次検索・Ctrl+F・印刷を使用できます。
- [PDF版](FormDesigner-Manual.pdf): PDFビューアーで開くか印刷します。
- [Markdownの原本](../../MANUAL.md): GitHubまたはMarkdown対応エディターで読めます。

HTML内の画面画像は埋め込んでいます。サンプルへのリンクを使う場合は、ZIPのフォルダー構成を保持してください。
GitHub上のHTML表示はソースです。ブラウザー表示にはダウンロード後に開きます。

原本を変更して再生成する場合は、アプリの依存関係を導入したPythonで実行します。

```powershell
.\.venv\Scripts\python.exe scripts/build_manual.py --pdf
```

Linuxの生成例:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/build_manual.py --pdf
```

PDF生成はPySide6と日本語フォントを使用します。今回のPDFはDejaVu SansとNoto Sans CJK JPで生成しています。
原本を更新した場合はHTMLとPDFも再生成してください。
