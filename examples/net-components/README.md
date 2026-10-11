# .NET部品の例

FormDesignerでJSONを開き、MACを出力してE3D側で確認します。
MACはUTF-8です。環境が別の文字コードを使う場合はFormDesignerの出力設定を合わせてください。

| ファイル | 内容 |
| --- | --- |
| grid.json / grid.mac | 手入力した2列の表 |
| grid-members.json / grid-members.mac | 現在要素の直属の配下のName／Typeを表へ表示 |
| file-open.json / file-open.mac | ファイルを開くダイアログでパスを取得 |
| file-save.json / file-save.mac | 保存先を選ぶダイアログでパスを取得 |
| mydata.json / mydata.mac | ボタンを押した時点の現在要素をMy Dataへ登録 |

対応する.NETアセンブリがE3D側に必要です。ファイル選択の例はファイルを読込・書込しません。
公開公式資料の構成を基にした例で、E3D 4.0実機では未実行です。
DLL名と名前空間を使用環境に合わせて確認してください。

詳しくは [作成ガイド](../../docs/net-components.md) を参照してください。
