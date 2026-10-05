# 作業手順に沿った最新UI

現在の画面は「フォーム設定 → 配置 → 動作 → 確認・出力」の切り替えに対応しています。追加ボタンは全て常時表示し、配置キャンバスとコード出力を別画面にしています。

- [フォーム設定](workflow-form.png)
- [タブと部品の配置](workflow-layout.png)
- [動作設定](workflow-actions.png)
- [生成コードと保存・出力](workflow-output.png)

[初期値のプルダウンとテキスト入力の表示](initial-preview.png)では、TRUE/FALSEの選択欄と、枠外の表示名・枠内の値を確認できます。

以下は過去の画面例です。

---

# 現在のUIと配置サンプル

最新の編集画面は [仕上げ後の画面](finished-editor.png) です。別名保存・コンパクトな部品設定・追加先表示を確認できます。

以下の過去の画面例は、PySide6アプリで `examples/equipmenttool.json` を開いて撮影した画面です。

- [エディタ全体](editor.png)
- [配置したフォームのプレビュー](equipmenttool-preview.png)
- [対応する生成PMLコード](equipmenttool.mac)
- [編集用JSON](../../examples/equipmenttool.json)

プレビューはエディタでの概略表示です。E3D実機の画面ではありません。

![エディタ全体](editor.png)

![配置サンプル](equipmenttool-preview.png)

初期値をプロパティから設定した例です。初期設定コードは DEFAULT メソッドへ自動生成します。

![初期値の設定](initial-defaults.png)

[編集用JSON](../../examples/initial-defaults.json) / [生成PML](../../examples/initial-defaults.mac)

![外部マクロと分岐フラグの設定](macro-actions.png)

[外部マクロを呼び出すサンプル](../../examples/macro-launcher.json) / [分岐マクロのひな形](../../examples/macro-code1.mac)

![MAC出力先フォルダと部品コメント](output-comments.png)
