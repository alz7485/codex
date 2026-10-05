# PML フォーム例文の追加調査

調査日: 2026-10-05（日本時間）。GitHub 上の7リポジトリから20件の `.pmlfrm`（内容の重複を除く19件）、解説・スニペットを取得して読みました。第三者ソースは実行していません。以下の例文は資料で確認したパターンを短く構成し直したものです。AVEVA の公式認証や E3D 4.0 実機での検証を受けた例文ではありません。

## 主な情報源

| 情報源 | 読んだ資料・コード | 利用する根拠と限界 |
| --- | --- | --- |
| [shivangKheradiya/AVEVA_PML: Forms](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md) | ライフサイクル、OPTION、LIST、FRAME、TEXT、TEXT PANE、ラジオなど | ガジェット別の具体例が多い。ただし TEXT の例で未定義の t6 を参照するなど誤記もあり、転載してそのまま動作すると扱わない |
| [nhdang117/PML.Learning: Form Concepts](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/forms-concepts-and-callbacks.md) | フォーム構成、PMLLIB、コールバック、show / loadform / hide / kill | 作者はマニュアル・出荷 PMLLIB と照合したと説明。こちらからその照合を独立に確認できていないため、第三者解説として扱う |
| [PML.Learning: Building Forms](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/building-forms.md) | DIALOG、DOCK、サイズ、初期化 | ユーザー提供の DIALOG DOCK RIGHT と整合する DOCK の説明あり |
| [mikhalchankasm: callback 実例](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/hide_examples/forms/traExampleCallback.pmlfrm) | constructor、initCall、firstShownCall、okCall、cancelCall など | 解説だけでなく `.pmlfrm` を確認。ただし末尾に未定義らしい init 呼出し等もあり、完成品・動作保証とは扱わない |
| [mikhalchankasm: TABSET 実例](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/examples/test2form.pmlfrm) | 名前付き TABSET、内側 FRAME、PMLNETCONTROL | 名前付き TABSET の実例。外部 DLL と固定パス依存があり、単体動作する例ではない |
| [ibesedin/AVEVA-1](https://github.com/ibesedin/AVEVA-1/tree/3fd6f30dc1725e97cd11b5893acd1cbab6d6c303) | 6フォーム。CALL、kill、FRAME、RTOG、LIST、Dtext | 古い PDMS / MARINE / E3D 用の実例。4.0 の証明にはならない |
| [me-hungry/Aveva-PDMS](https://github.com/me-hungry/Aveva-PDMS/tree/6cc219d5c109b6004cb438fe1f86847c3ee240d7) | 3フォーム。Grid、PML.NET、コンストラクタ | 外部アセンブリ・名前空間依存があるため、ネイティブ PML の基本部品とは分ける |
| [Donghun1q2w/pml_language_extension](https://github.com/Donghun1q2w/pml_language_extension/tree/4a0fce2da5477464844271c5dcfc23e44e25250f) | フォーム・ボタン・グリッドのスニペット | 編集用テンプレートであり、実機検証結果ではない |
| [PoByBolek/PmlUnit](https://github.com/PoByBolek/PmlUnit/tree/0cbcf6b4e7d0a5ed9e6745ca3f646fe1566a07bc) | テストフレームワーク README | E3D 内でテストする仕組みの参考。記載対象は E3D 1.1 / 2.1 等で、4.0 対応は未確認 |

参照 URL は読取時のブランチ HEAD を指定しています。GitHub ブランチの ZIP 取得と HEAD 確認は別の操作であり、途中でブランチが更新された可能性までは排除していません。

## 1. コンストラクタと表示時初期化を区別する

公開解説と callback フォーム実例の両方で、フォーム名と同じメソッドがコンストラクタとして使われ、`initCall` は別に登録されています。

```pml
setup form !!demoform DIALOG
  !this.initCall = '!this.initialise()'
  TEXT .name AT X 1 Y 1 'Name' WIDTH 20 IS STRING
exit

define method .demoform()
  !this.formTitle = 'Demo'
endmethod

define method .initialise()
  !this.name.val = 'Initial value'
endmethod
```

- `.demoform()` はフォームがロードされたときの初期化。
- `initCall` は表示時の初期化に使用される。
- `firstShownCall` は初回表示の処理を分ける用途。
- `.DEFAULT()` という名前自体を自動初期化の根拠にはできない。今のエディタでは明示呼出しの処理メソッドとして出力している。

**エディタへの示唆:** DEFAULT 編集欄に加え、constructor / initCall / firstShownCall の用途を選べる設計が有用。現実装への機能追加は今回行っていない。

## 2. TEXT は「毎キー入力」と「値の確定」を分けて検証する

公開フォームの最小例では、TEXT の callback を設定し、Enter またはボタン押下で同じメソッドを呼び出しています。

```pml
TEXT .name AT X 1 Y 1 'Name' CALL '!this.applyValue()' WIDTH 20 IS STRING
BUTTON .apply AT X 1 Y 3 'Apply' CALL '!this.applyValue()' WIDTH 12

define method .applyValue()
  !value = !this.name.val
  $p $!value
endmethod
```

参照: [Form Concepts の最小例](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/forms-concepts-and-callbacks.md)。上のガジェットは setup form 内、メソッドはその外に置く。

この例を根拠に「CALL がキーボード1文字ごとに発火する」とは言えません。別の [ガジェット参照表](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/reference/gadget-reference.md) は TEXT に SELECT / MODIFIED / VALIDATE を挙げています。イベント名と発火条件は E3D 4.0 で確認する必要があります。

## 3. イベント名を受け取る open callback

公開資料では、閉じ括弧を付けない callback 文字列と、GADGET / STRING 引数を持つメソッドの組が使われています。

```pml
!this.mode.callback = '!this.onMode('

define method .onMode(!gad is GADGET, !event is STRING)
  if !event eq 'SELECT' then
    !selected = !gad.selection('Rtext')
    $p $!selected
  endif
endmethod
```

参照: [Forms の Option Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#option-gadget)。callback の登録はメソッド内などで行う。

**エディタへの示唆:** 現在のメソッド名欄は引数なし `!this.method()` のみを生成する。open callback は直接 CALL を書くことだけで完結せず、対応する引数付きメソッドの編集・生成が必要。

## 4. OPTION の表示値と返却値

公開実例では `option .mode`、`.dtext`、`.rtext` を使う方式も確認できました。

```pml
OPTION .mode 'Mode' WIDTH 20

-- コンストラクタ内
!display = object ARRAY()
!result = object ARRAY()
!display[1] = 'Pump'
!display[2] = 'Tank'
!result[1] = 'PUMP'
!result[2] = 'TANK'
!this.mode.dtext = !display
!this.mode.rtext = !result
```

参照: [Forms の Option / List](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#option-gadget)。表示名と実値を分け、選択後の処理を callback メソッドで行う方式。ユーザーからも `.dtext` = 表示名、`.rtext` = 実値と確認しました。

ユーザー提供の次の方式は変更していません。

```pml
OPTION _mode AT X 1 Y 1 'Mode' CALL '$$_mode'
VAR LIST _mode PAIRS
'Pump' 'COMMAND A'
'Tank' 'COMMAND B'
EXIT
```

今回取得した資料・フォームでは `VAR LIST … PAIRS` の同一パターンを独立に裏付けられませんでした。それは「無効」という判定ではありません。互換構文・利用環境の違いがあり得るため、ユーザー提供方式として保持し、E3D 4.0 実機検証の対象とします。`.dtext / .rtext` 方式の追加は別の出力形式として検討するのが適切です。

## 5. TABSET、ページ FRAME、タブ切替

ユーザーの説明と同じく、公開フォームでも TABSET の直下に FRAME を置いています。

```pml
FRAME .tabs TABSET AT X 1 Y 1 'TABSET' WIDTH 50
  FRAME .settings 'Settings'
    TEXT .name AT X 1 Y 1 'Name' WIDTH 20 IS STRING
  EXIT
  FRAME .results 'Results'
    PARAGRAPH .message AT X 1 Y 1 TEXT 'Results' WIDTH 30
  EXIT
EXIT
```

参照: [名前付き TABSET のフォーム](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/examples/test2form.pmlfrm) と [Forms の Frame Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#frame-gadget)。上記はユーザー提供構文に合わせた構成例で、公開コードの完全一致転記ではない。

ページをコードで選ぶ例として、別の資料には次の記述がある。

```pml
!this.results.visible = true
```

[Frame Gadgets の説明](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/hide_examples/Frame%20Gadgets/Frame%20Gadgets.md) では、ユーザー操作の切替で HIDDEN / SHOWN イベントが発生し、visible 代入では同じイベントは発生しないとされる。

**資料間の差:** 同じリポジトリのマニュアル風文書には TABSET 自体は「名前を持たない」と書かれる一方、実例には `frame .tabs tabset` がある。特定文書だけでユーザーの名前付き構文を不正と判断しない。対象版・実際の読み込み結果で確認する。

## 6. 型を意識した VAL 代入

ユーザー提供の `!!フォーム.部品.VAL = !!変数` と、公開フォーム内の `!this.部品.val = 値` は同じメンバーを操作する用途で使われています。

```pml
-- STRING
!!demoform.name.val = 'P-101'

-- REAL
!!demoform.amount.val = 12.5

-- BOOLEAN
!!demoform.enabled.val = true
```

参照: [Variables and Expressions](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/variables-and-expressions.md)、[Gadget Reference](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/reference/gadget-reference.md)。name / amount / enabled の部品がロード済みであることが前提。

`VAR !!amount '12.5'` のような変数は資料上 STRING とされる。REAL 欄に渡す場合は `.Real()`、BOOLEAN の場合は `.Boolean()` など、型変換が必要か確認する。

**エディタへの示唆:** 今のグローバル変数欄は VAR と文字列リテラルを生成する。数値・真偽値変数を同じ型の値として扱えると主張できない。型付き変数・変換支援の追加候補。

## 7. フォーム定義と起動用コマンドの分離

複数の `.pmlfrm` 実例と説明では、定義・コンストラクタ・メソッドをフォームファイルに置き、`show` は別に実行する。PML.Learning はフォームファイルの定義・メソッド外の実行文に注意するよう記載している。

フォームファイル: `demoform.pmlfrm`

```pml
setup form !!demoform DIALOG
  TEXT .name AT X 1 Y 1 'Name' WIDTH 20 IS STRING
exit

define method .demoform()
  !this.name.val = 'P-101'
endmethod
```

E3D コマンド欄などで実行:

```pml
pml rehash all
show !!demoform
```

変更時の再読込例:

```pml
pml reload form !!demoform
show !!demoform
```

参照: [Forms](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#basic-understanding-and-syntax)、[Form Concepts](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/forms-concepts-and-callbacks.md)。PMLLIB の探索パス設定とファイル名の一致が前提。

**現エディタの確認事項:** ユーザー指示に合わせ、VAR / kill / フォーム定義 / SHOW / 表示後プログラム / メソッドを1つの `.pmlfrm` に出力している。命令列を実行する用途と PMLLIB のフォームとして自動ロードする用途では条件が異なる可能性がある。一体型を維持しつつ、定義専用 `.pmlfrm` と起動用 `.mac` を別に出す形式を検討する。2026-10-05 のユーザー訂正に合わせ、SHOW は DEFINE METHOD より前に出力する。LIST の AT も表示名より前に出力する。

## 8. 拡張候補

| 機能 | 資料で確認した例 | 現エディタ |
| --- | --- | --- |
| 表示時初期化 | initCall / firstShownCall | 任意コードは記述可能、自動配線欄なし |
| イベントごとの分岐 | open callback | 引数付きメソッド生成なし |
| 表示名・識別値 | OPTION dtext / rtext | PAIRS コマンド方式のみ |
| リスト | SINGLE / MULTI、SetHeadings、SetRows | 単列と複数列 TABLE に対応 |
| 文字入力 | FORMAT、NOECHO、setEditable | STRING / REAL の基本入力のみ |
| 複数行入力 | TEXTPANE と配列 VAL | 未対応 |
| ラジオ | FRAME 内の RTOGGLE、RGROUP | 未対応 |
| フォーム制御 | OK / CANCEL / APPLY / RESET / HELP | 直接 CALL、任意コードのみ |
| レイアウト | PATH、HDIST、VDIST、ANCHOR、DOCK | 絶対座標・基本 TABSET |
| 外部部品 | CONTAINER PMLNETCONTROL、Grid | 未対応、DLL 等が別途必要 |

## 検証範囲とネットワーク制約

今回も help.aveva.com（3.1 / 4.0 の候補 URL）、pdmsmacro.com、資料サイト nhdang117.github.io への HTTPS 接続はプロキシから 403 で拒否された。公式候補ページの存在・内容は確認できていない。GitHub 上の本文と raw / codeload の取得は成功した。許可ドメイン設定は変更していない。

資料には古い製品版、依存 DLL、固定パス、誤記、資料同士の食い違いが含まれる。ネット上の例文が存在することと E3D 4.0 で動作することは別である。背景色番号の対応表、PAIRS の挙動、TEXT の発火時点、名前付き TABSET と寸法、フォームのロード方式・日本語文字コードは実機検証が必要。今回アプリケーションコード・テスト・出力方式は変更していない。

## 9. 追加確認: SLIDER

[Forms の Slider Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#slider-gadget) では、向き・範囲・ステップ・初期値と open callback を組み合わせています。

```pml
-- setup form 内
SLIDER .level HORIZONTAL RANGE 0 100 STEP 5 VAL 50 WIDTH 30

-- コンストラクタ内
!this.level.callback = '!this.sliderEvent('

-- フォームメソッド
define method .sliderEvent(!gad is GADGET, !event is STRING)
  q var !gad.val
  q var !event
endmethod
```

公開参照表は START / MOVE / STOP を挙げています。実際のイベント名・型・通知頻度は実機で確認します。GUI 追加に必要な属性は向き、最小値、最大値、STEP、VAL、幅とイベント処理です。

## 10. 追加確認: LIST の表示名と実値

ユーザー確認: `.dtext` は表示名、`.rtext` は実値です。実値は任意の識別文字列などであり、必ずしも実行コマンドではありません。これは OPTION と LIST の公開例とも一致します。

```pml
-- setup form 内
LIST .equipment 'Equipment' SINGLE WIDTH 25 HEIGHT 5

-- コンストラクタ内
!display = object ARRAY()
!values = object ARRAY()
!display[1] = 'Pump 101'
!display[2] = 'Tank 201'
!values[1] = '/P-101'
!values[2] = '/T-201'
!this.equipment.dtext = !display
!this.equipment.rtext = !values
```

[Forms の List Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#list-gadget) には SINGLE / MULTI、`selection('Dtext')` / `selection('Rtext')`、`SetHeadings` / `SetRows` の例があります。単一・複数選択で戻り値の型がどう変わるかは実機検証が必要です。資料によって MULTI / MULTIPLE と省略・正式表記が異なるため、未確認の表記を統一しません。

## 11. 追加確認: VIEW とコマンドライン

[Forms の View Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#view-gadget) で以下の4種類が説明されています。

| 種類 | 用途 |
| --- | --- |
| ALPHA | テキスト出力・コマンド入力 |
| AREA | 2D Draw |
| PLOT | 2D プロットファイル表示 |
| VOLUME | 3D ビュー |

ALPHA を使うコマンド欄の構成例:

```pml
-- setup form 内
VIEW .commandLine AT X 1 Y 1 ALPHA
  HEIGHT 10 WIDTH 60
  CHANNEL REQUESTS
  CHANNEL COMMANDS
EXIT
```

この EXIT は VIEW を閉じるものです。さらにフォーム本体の EXIT が必要です。CHANNEL COMMANDS はコマンド用、REQUESTS はリクエスト出力用として資料に記載されています。PySide6 上で E3D コマンドを実行する機能とは別物です。

3D ビューの定義例:

```pml
VIEW .model VOLUME WIDTH 46 HEIGHT 15
  LIMITS AUTO
  ISOMETRIC 3
EXIT
```

単に VIEW を置くだけでは対象モデルの表示まで保証できません。同資料では `!!gphDrawlists.createDrawList()`、`!!gphDrawlists.attachView()`、現在要素 `!!CE` の追加、表示範囲の設定、終了時の detach / delete を組み合わせています。例文には quit と close の命名が一致しない箇所もあるため、ライフサイクルまで検証する必要があります。

**エディタへの示唆:** ALPHA、PLOT、VOLUME などの型と子コマンドを保持する必要がある。PySide6 のキャンバスでは概略の枠を描けても、E3D のモデル表示・コマンド応答を再現したとは扱えない。

## 12. 追加確認: RTOGGLE（ラジオボタン）

ユーザーからも RTOGGLE の存在を確認しました。[Forms の Radio Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#radio-gadget) と、[FRAME 用スニペット](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/snippets/pml.json) でも、同じ FRAME に複数の RTOGGLE を入れています。

```pml
FRAME .typeGroup 'Type'
  RTOGGLE .pump 'Pump' AT X 1 Y 1 STATES || 'PUMP'
  RTOGGLE .tank 'Tank' AT X 1 Y 2 STATES || 'TANK'
EXIT
```

公開例で確認した選択情報の取得パターン:

```pml
!index = !this.typeGroup.val
if !index gt 0 then
  !radio = !this.typeGroup.RToggle(!index)
  !value = !radio.onvalue
endif
```

FRAME がグループの選択を管理します。通常の独立した TOGGLE と同じ扱いにはしません。`.onvalue` / `.offvalue` と単純な真偽値の区別、未選択時のインデックス、callback の発火条件は実機で確認します。RGROUP という別方式の例もあります。

## 13. 追加確認: COMBO（コンボボックス）

ユーザー情報と [Forms の Option Gadget](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#option-gadget) を照合しました。

```pml
-- setup form 内
COMBO .freeChoice 'Choice' WIDTH 20

-- コンストラクタ内
!this.freeChoice.dtext = !display
!this.freeChoice.rtext = !values
```

この例の `!display` と `!values` はあらかじめ作った対応する配列です。公開コードの定義キーワードは `combo` ですが、別の参照表は部品名を COMBOBOX と記載しています。「COMBOBOX と表記されるから定義キーワードも必ず COMBOBOX」と推測しません。

通常 OPTION と違い編集可能な表示欄を持つ部品として説明されています。候補の選択と、直接文字入力の確定は別のイベント・戻り値となり得るため、SELECT / UNSELECT / VALIDATE と `.val` / `.selection()` を実機で確認します。

## 14. 追加確認: CONTAINER と PML.NET

ユーザー情報に加え、[uFitlerSelection.pmlfrm](https://github.com/me-hungry/Aveva-PDMS/blob/6cc219d5c109b6004cb438fe1f86847c3ee240d7/uGrid/uFitlerSelection.pmlfrm)、[E3D Grid スニペット](https://github.com/Donghun1q2w/pml_language_extension/blob/4a0fce2da5477464844271c5dcfc23e44e25250f/snippets/pmlformgE3D.json) で CONTAINER を確認しました。

実際の uGrid フォームには次の組があります（依存先の名前は元コードのもの）。

```pml
import 'uGrid'
using namespace 'Aveva.Gadgets.uGrid'
member .memberGrid is userGrid
!this.memberGrid = object userGrid()
container .containerGrid PMLNetControl anchor left+top+bottom width 30 height 10
!this.containerGrid.Control = !this.memberGrid.handle()
```

これは `uGrid` アセンブリとクラスがインストール済みであることを前提とする例であり、標準部品だけのコードではありません。CONTAINER の用途を単なる枠と混同せず、FRAME と区別します。

GUI に CONTAINER を追加するときは、配置だけでなく import、名前空間、型、インスタンス作成、Control の handle 接続、イベントハンドラ、必要 DLL と製品版の互換性を扱う必要があります。特に PDMS 時代の名前空間を E3D 4.0 のものとして固定しません。

## 画像と追加機能の実装

2026-10-05 更新: PARAGRAPH / BUTTON / TOGGLE の単一 PIXMAP、画像 OPTION の DTEXT / RTEXT、TEXTPANE の配列 VAL と FIXCHARS、DATABASE SELECTOR、MAIN の FRAME TOOLBAR、フォーム INITCALL / OKCALL / CANCELCALL、BUTTON の制御属性、POPUP メニューと SetPopup を実装しました。設計 JSON は既存バージョン 1 の未指定項目に既定値を補い、保存・読み込み、Undo / Redo、名前管理、キー操作でも新しい設定を保持します。

今回、次の固定コミットの公開資料をネットから再取得し、構文例を確認しました。

- [AVEVA_PML Forms](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md): PARAGRAPH の PIXMAP / AddPixmap、画像 OPTION の DTEXT ファイル配列と RTEXT、フォームイベント、TEXTPANE、メニューの Add と LIST の SetPopup。
- [Form layout and gadgets](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/form-layout-and-gadgets.md): SELECTOR DATABASE OWNERS、TEXTPANE の配列 VAL と FIXCHARS。
- [Gadget reference](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/reference/gadget-reference.md): DATABASE OWNERS / MEMBERS / AUTO、PIXMAP 対応ガジェットとイベント。
- [Building forms](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/building-forms.md): INITCALL / OKCALL / CANCELCALL、MENU POPUP、メニューの Add('CALLBACK', ...)、SetPopup、MAIN の FRAME TOOLBAR と対応部品。
- [Button methods and control attributes](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/hide_examples/Button%20Gadget/Button%20Gadget%20Methods.md): AddPixmap とボタンの制御属性。AVEVA 文書へのリンクを含む参考資料で、E3D 4.0 の実機検証結果ではありません。

画像 OPTION は従来の文字 PAIRS OPTION と異なり `.名前` を使用します。公開例の画像パスには `/C:\...` の形式がありますが、エディタは入力パスに接頭辞を足さずそのまま出力します。E3D 側の画像探索・利用可能な形式・ピクセル寸法は実機で確認が必要です。サンプル PNG はこのプロジェクトで新規に作成しました。

AUTOCALL、TOGGLE の状態別複数画像、RGROUP、TOOLBAR の既存アプリへの自動登録、外部グリッドの列・イベント設定、既存 PML のインポートは今回も未実装です。SELECTOR のデータ取得とコールバックの実行、VIEW の drawlist 管理、外部 DLL はプレビューで実行しません。

この節より前の「未対応」表記は調査当時の状況です。現状の利用手順は [README](../README.md#画像複数行入力db-選択ツールバー)、サンプルは [extra-features.pmlfrm](../examples/extra-features.pmlfrm) と [toolbar.pmlfrm](../examples/toolbar.pmlfrm) です。

## 更新内容と未実装の区別

2026-10-05 更新: SLIDER、RTOGGLE、VIEW、ALPHA コマンド欄、COMBO、CONTAINER の GUI 編集・概略プレビュー・PML 出力を実装しました。LIST の SINGLE / MULTI と LIST / COMBO の表示名・実値編集にも対応しました。ユーザー提供の !HEAD / !ROWS の例に合わせ、複数列 LIST の表入力と SetHeadings / SetRows 出力にも対応しました。VIEW の drawlist 管理、外部 DLL の配布・イベント接続・終了処理は未対応です。E3D 4.0 実機での構文・動作検証は未実施です。詳細は [README](../README.md#追加ガジェット) と [サンプル](../examples/gadgets.pmlfrm) を参照してください。

## 15. 座標以外の配置: PATH / ALIGN / 相対参照

ユーザー指摘を踏まえ、[Form Layout and Gadgets](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/form-layout-and-gadgets.md)、[Forms の Gadget Positioning Using Paths](https://github.com/shivangKheradiya/AVEVA_PML/blob/2d3a87205cb80fbc68ca6b0518c9cf58dbd14285/10.%20Forms/README.md#gadget-positioning-using-paths)、[実際の BSSPipelineSlopeNET.pmlfrm](https://github.com/ibesedin/AVEVA-1/blob/3fd6f30dc1725e97cd11b5893acd1cbab6d6c303/BSSPipelineSlopeNET.pmlfrm) を照合しました。

| 機能 | コード | 意味 |
| --- | --- | --- |
| 下へ順に配置 | `PATH DOWN` | 後続の部品を下方向へ配置 |
| 右へ順に配置 | `PATH RIGHT` | 後続の部品を右方向へ配置 |
| 縦・横の間隔 | `VDIST 0.5` / `HDIST 1` | 自動配置の部品間隔 |
| 水平方向の整列 | `HALIGN LEFT` / `CENTRE` / `RIGHT` | PATH と組み合わせ、後続部品を前の部品に対して整列 |
| 垂直方向の整列 | `VALIGN TOP` / `CENTRE` / `BOTTOM` | PATH と組み合わせ、後続部品を前の部品に対して整列 |
| 指定部品の左端と下端 | `AT XMIN.name YMAX.name+0.5` | 他部品の端を参照して配置 |
| 指定部品の右隣 | `AT XMAX.name+1 YMIN.name` | X と Y を他部品から取得 |
| 指定部品の右端に揃える | `AT XMAX.name-SIZE YMIN.name` | 自部品の幅を差し引いて右端を一致させる |
| 幅を揃える | `WIDTH.name` | 指定部品の幅を参照 |
| 親のサイズ変更へ追従 | `ANCHOR RIGHT+BOTTOM` | 初期整列とは別に、指定辺への距離を保持 |
| 親の残り領域を埋める | `DOCK FILL` | 親コンテナの領域を埋める |

HALIGN / VALIGN を「無条件にフォーム全体の左・中央・右へ移動する命令」とは説明しません。PATH、前のガジェット、所属コンテナと組み合わせる整列命令です。親の右端に揃える場合は `XMAX FORM-SIZE` などの参照構文、サイズ変更への追従は ANCHOR / DOCK と区別します。

下方向に左端を揃えて並べる例（setup form 内）:

```pml
BUTTON .first AT X 1 Y 1 'First' WIDTH 20
PATH DOWN
VDIST 0.5
HALIGN LEFT
BUTTON .second 'Second' WIDTH 12
BUTTON .third 'Third' WIDTH 16
```

中央合わせ・右端合わせは、同じ位置で `HALIGN CENTRE` / `HALIGN RIGHT` を設定する方式です。具体的な基準となる範囲と最終表示は E3D で確認します。

他部品の右隣と、その下へ配置する例:

```pml
TEXT .name AT X 1 Y 1 'Name' WIDTH 20 IS STRING
BUTTON .apply AT XMAX.name+1 YMIN.name 'Apply' WIDTH 12
PARAGRAPH .hint AT XMIN.name YMAX.name+0.5 TEXT 'Enter a name' WIDTH 30
```

右端を揃える例:

```pml
BUTTON .apply AT XMAX.name-SIZE YMAX.name+0.5 'Apply' WIDTH 12
```

サイズも他部品へ合わせる例:

```pml
FRAME .copy 'Copy' WIDTH.original HEIGHT TO MAX.original
EXIT
```

この例は `.original` が先に定義されていることが前提です。`WIDTH.original` は幅の参照、`HEIGHT TO MAX.original` は下端までの寸法です。

**現エディタの制約:** x / y / width / height は数値のみであり、この相対配置・自動配置はまだ GUI / データモデルに実装していません。対応には「座標」「PATH 自動配置」「参照部品と辺・オフセット」「ANCHOR / DOCK」を別の設定として保持し、参照先が先に定義される出力順と、参照循環の検出が必要です。画面上で一度揃えて固定座標を出力する機能と、PML の相対参照を出力する機能は区別します。

COMBO の追加確認: [Form Layout and Gadgets の本文](https://github.com/nhdang117/PML.Learning/blob/57d55443a63f2cc7ec897c56ba1ae259f4b43bd1/docs/guide/form-layout-and-gadgets.md) には `combobox .colour tagwidth 6 |Colour| scroll 20 width 10` という定義例もありました。公開例に COMBO と COMBOBOX の両方があり、E3D 4.0 での受理範囲は実機確認とします。

ロード方式の追加確認: [公開された Forms の説明](https://github.com/mikhalchankasm/vscode-pml-aveva-e3d/blob/07971b883c53ae665d3c02c7670c1e8cdaa76343/hide_examples/forms/forms.md) は `.pmlfrm` の初回表示時自動ロードと、昔の `$m` によるフォーム定義マクロの互換方式を区別しています。ユーザーの一体型命令列と定義ファイルの違いを検証すべきという先の判断を補強します。

ユーザー追記: 単列リストの複数選択には `LIST .name '表示名' MULTIPLE WIDTH 値 HEIGHT 値` と、表示名の配列を `.DTEXT` へ代入する方式も使える。エディタは単列・複数列とも SINGLE / MULTIPLE と HEIGHT を出力する。旧設計ファイルの MULTI は読み込み時に MULTIPLE に移行する。AT のある定義では先のユーザー指示どおり表示名の前に置く。

ユーザー追記: VIEW は HEIGHT の後に ASPECT 値を指定できる。エディタに任意入力欄を追加し、HEIGHT の直後へ出力する。省略を既定とし、E3D 4.0 実機での表示効果は未検証。

ユーザー追記: LIST の色指定は AT より前に置ける。エディタは BACKGROUND 欄を LIST にも対応させ、`LIST .name BACKGROUND 番号 AT ...` の順で出力する。空欄では省略する。
