# DBセレクタの処理メソッドの例

各JSONをFormDesignerで開き、必要に応じて配置や処理を変更できます。
同名のMACはUTF-8で保存した生成コードです。E3Dの実行環境に合う文字コードで出力してください。

| ファイル | 内容 |
| --- | --- |
| report-multiple | 複数選択の名前・種類・直属の上位を表示 |
| navigate-single | 単一選択の要素をCEに設定 |
| mydata-multiple | 複数選択の要素をMy Dataに登録 |
| custom-multiple | 1件ごとにDBREFを受け取り、直属の上位を確認 |
| report-on-selection | 選択変更時に情報表示メソッドを実行 |

E3DでCEをSITE等にしてからフォームを開き、一覧から対象を選びます。
処理ボタン方式はボタンを押して実行し、更新ボタンは現在のCEを基準に一覧を更新します。
My Dataには対応するアセンブリが必要です。E3D 4.0実機での動作は未確認です。

[使い方](../../docs/db-selector-methods.md) を参照してください。
