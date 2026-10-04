# 調査メモ

調査日: 2026-10-04。公開 GitHub ページと raw ファイルを取得し、下記を確認しました。

| 情報源 | 確認した内容 | 制約 |
| --- | --- | --- |
| [Gabriel-Olive/PMLFormDesigner](https://github.com/Gabriel-Olive/PMLFormDesigner) | ブラウザで配置・プロパティ編集・PML 生成。script.js に button / paragraph / text / toggle / option / list の生成処理 | E3D 4.0 動作保証は確認していない。単純なピクセル換算や文字列生成をそのまま流用しない |
| [nlbyrl/AwePml](https://github.com/nlbyrl/AwePml) | V1.0 の説明文に視覚的フォーム設計・プロパティ編集・PML 生成・PDMS デバッグの説明 | 作者の説明では PDMS 12.1 でのみテスト。Windows exe はダウンロード・実行していない |
| [Donghun1q2w/pml_language_extension](https://github.com/Donghun1q2w/pml_language_extension) | README、snippets/pmlform.json、snippets/pmlbut.json。setup form、コンストラクタ、callback の実例 | GUI デザイナではなく VS Code 拡張。Marine 専用 import は取り込まない |
| [ibesedin/AVEVA-1](https://github.com/ibesedin/AVEVA-1) | BSSClashesDebugNET.pmlfrm / BSSPipelineSlopeNET.pmlfrm の実例。kill、frame、rtog、CANCEL、list の lines、option の dtext | 古い PDMS / Marine / E3D 用コード。E3D 4.0 での互換性は別途必要 |
| [MahabubRony16/PML](https://github.com/MahabubRony16/PML) | E3D / PDMS 開発用スクリプトの公開リポジトリを発見 | 今回フォーム構文の根拠には使っていない |

AVEVA 公式 help.aveva.com、一般検索サイト、pdmsmacro.com へのアクセスは、このクラウドのプロキシから 403 で拒否されました。公式資料を閲覧したとは主張しません。公式との照合を続ける場合は環境の許可ドメインに help.aveva.com を追加する必要があります。ネットワーク設定は変更していません。

ユーザー提供情報: `VAR !!変数名 '初期値'` によるグローバル変数初期化、および `kill !!フォーム名` による既存同名フォーム破棄。両方を生成コードに反映しました。さらに `setup form !!フォーム名 DIALOG DOCK RIGHT` による右ドッキング指定をユーザー情報に基づいて既定の出力にしました。

E3D 実機で確認すべき項目:

- 正確な製品バージョン、フォームの探索パス／再読み込み手順
- 生成した setup form とコンストラクタの実行
- 各ガジェットの表示・座標・サイズ、テキスト型、選択肢
- callback メソッドの呼び出し、グローバル変数初期化
- 未ロードのフォームに対する kill と、既存フォームの再読み込み
- 日本語の UTF-8 / CP932 読み込み

サンプルの位置付けは構文の参考です。第三者コードのライセンスを確認せずに転載・組み込みを行っていません。

追加ユーザー情報: `TOGGLE .オブジェクト名 AT X 座標値 Y 座標値 '表示名' CALL 'コマンド'`。TOGGLE の出力順序と CALL 指定をこの構文に変更しました。

追加ユーザー情報: `PARAGRAPH .オブジェクト名 AT X 座標値 Y 座標値 BACKGROUND カラー番号 TEXT '表示名'`。生成順序と BACKGROUND 欄を反映しました。色番号の対応表は未確認です。

ユーザー確認: BACKGROUND を省略した PARAGRAPH は背景色を使用します。空欄で省略する仕様と UI の説明に反映しました。

追加ユーザー情報: `LINE .オブジェクト名 AT X 座標値 Y 座標値 '' HORIZ WIDTH 値 HEIGHT 値` と `VERT` 版。両方向の出力、GUI 選択、プレビューを追加しました。

ユーザー追記: PARAGRAPH の TEXT の後に `WIDTH 値` を指定。BACKGROUND の有無にかかわらず GUI の幅を出力するよう更新しました。

追加ユーザー情報: `TEXT .オブジェクト名 AT X 座標値 Y 座標値 '表示名' CALL '入力したときに実行されるコマンド' WIDTH 値 IS STRINGまたはREAL`。順序と CALL コマンド編集を反映しました。

追加ユーザー情報: `BUTTON .オブジェクト名 AT X 座標値 Y 座標値 BACKGROUND カラー番号 '表示名' CALL 'ボタン押したときのコマンド' WIDTH 値`。出力順序、背景番号、直接 CALL コマンド編集を反映しました。

追加ユーザー情報: `FRAME .オブジェクト名 '表示名'`。空の枠と対応する EXIT を生成する初期対応を追加しました。子部品の配置は未対応です。

追加ユーザー情報: `FRAME .オブジェクト名 TABSET AT X 座標値 Y 座標値 'TABSET' WIDTH 値`。ユーザー確認により、通常の枠ではなくタブ用コンテナとして扱います。空の TABSET の定義と GUI 形式選択を追加しました。ページ追加・切替は未対応です。

追加ユーザー情報: TABSET の中に FRAME を作成する構造。親コンテナ、入れ子の EXIT、子部品の所属、GUI ページ表示切替を実装しました。

追加ユーザー情報: OPTION _name と CALL '$$_name'、VAR LIST _name PAIRS による選択肢・実行コマンドの組。従来の OPTION dtext 生成をこの方式に変更しました。

追加ユーザー情報: SHOW !!フォーム名、表示後のプログラム、DEFINE METHOD .DEFAULT()、!!フォーム名.オブジェクト名.VAL = !!変数1。編集欄・テンプレート・代入サンプルを追加しました。DEFAULT 呼び出しはユーザーが指定します。
