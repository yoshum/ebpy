# ebpy

[English](README.md) | 日本語

既存の Python コードベースを、**良くなる一方**にする。

[ever-better](https://github.com/isamu/ever-better) の Python 版です。考え方もフェーズも同じで、
ESLint / TypeScript の代わりに Ruff / mypy / pytest を土台にしています。

リポジトリに足りない品質ツールを報告し、導入し、**今日時点の違反をすべて上限（天井）として記録**
します。そのコミット以降、既存コードは既得権として見逃され、新しいコードにはルールセット全体が
適用されます。天井は下がることはあっても、上がることはありません。

## なぜ必要か

古いリポジトリに厳しい linter を入れると 4000 件のエラーが出て、結局 revert されます。よくある
回避策 — 全部を warning にする — では何も強制されず、件数は静かに増えていきます。

ESLint はこれを **bulk suppressions** で本体解決しました。Ruff に同等の機能はないため、ebpy が
ラチェット機構そのものを持ちます。`freeze` が**ファイルごと・ルールごと**の違反数を記録し、
`check` がそれを超えた分で失敗し、`prune` だけがその数字を下げられます。既存の 1 行も変えずに、
初日から全ルールをエラーにできます。

これは linter ではありません。**あなたの** Ruff を、**あなたの**設定で、**あなたの** virtualenv
から実行します。

## インストール

パッケージインデックスには公開していません。次の1コマンドはGit上のebpyをbootstrapとして実行し、
検出したproject managerでebpyを追加して、対応するClaude Codeスキルを `.claude/skills` に
配置します。

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install
```

対象を指定しない場合は、`main` の `ebpy.__version__` から対応するリリースタグを選びます。特定の
リリースは正確なバージョンを渡し、コミットまたはブランチは `--ref` で指定します。

```bash
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install <version>
uvx --from "git+https://github.com/yoshum/ebpy" ebpy install --ref <commit-or-branch>
```

受け付けるリリースバージョンは完全一致だけで、範囲指定にはまだ対応していません。
`skills install` を含まないv0.3.0未満は、projectを変更する前に拒否します。bootstrapの `--from`
URL自体にGit refがあり、CLI側で対象を指定していない場合は、そのrefを引き継ぎます。CLIの
`VERSION` または `--ref` を明示した場合は、常にそちらが優先です。

Python 3.11以降。ワンライナーのbootstrapにはuvが必要です。`ebpy install` はuv / Poetry / PDM /
Pipenvのprojectに対応し、dependency追加と `skills install` の実行の両方に同じmanagerを使います。
pipにはprojectレベルのdev dependencyを永続化する標準的な方法がないため、bare pipへのfallbackは
拒否します。

## 使い方

[`skills/`](skills) にあるスキルがこのツールのもう半分です。CLI は決定的にできること — 検出・導入・
計測・描画・ゲート — を担当し、スキルは判断が要ること — この違反は本物のバグか、修正ではなく issue
にすべきか、どこで手を止めて聞くべきか — を担当します。通常はスキルに運転させ、数字がひとつ欲しい
ときだけ CLI を直接叩きます。

### スキルを Claude Code に渡す

`ebpy install` は、追加したdev dependency側の `ebpy skills install` に処理を移譲します。そのため、
5つのスキルと共有手順はdev dependencyとまったく同じリリースまたはGit refから
`.claude/skills` に配置済みです。

あとは普通の言葉で頼むだけです。スキルはコマンド名ではなく発話内容から選ばれるので、覚えるべき
名前はありません。

| 言い方 | 動くもの | 得られるもの |
| --- | --- | --- |
| 「ebpy を回して」「このリポジトリを綺麗にして」 | [`ebpy-run`](docs/skills.md#ebpy-run) | 全工程を自動で — 積み上がった pull request |
| 「ここで ebpy は何をする?」 | [`ebpy-guide`](docs/skills.md#ebpy-guide) | 診断と、1 フェーズずつの案内 |
| 「lint を入れて」「型チェック入れて」 | [`ebpy-bootstrap`](docs/skills.md#ebpy-bootstrap) | ツールの導入、設定と CI の生成 |
| 「ベースラインを固定して」 | [`ebpy-freeze`](docs/skills.md#ebpy-freeze) | 天井の固定と、それをゲートする CI |
| 「backlog を潰して」「リファクタリングして」 | [`ebpy-drain`](docs/skills.md#ebpy-drain) | 1 ルール 1 PR、テスト付き |

各スキルが何をして、何を譲らず、何をやらないかは **[スキルリファレンス](docs/skills.md)** に
あります。

### 初日: 手つかずのリポジトリ

```
このリポジトリに ebpy を回して
```

これで全工程を渡したことになります。実行前に中身を見たいなら「ここで ebpy は何をする?」と聞いて
ください。フェーズは同じで、1 つずつ進み、承諾するまで何も書きません。

どちらでも初日に生まれるコミットは 4 つ。順番は動かせません。

| | 何が起きるか | 対応コマンド | 見るべきもの |
| --- | --- | --- | --- |
| 1 | 調査 — すべての不足に、解消するフェーズ付きで名前が付く | [`diagnose`](docs/cli/diagnose.md) | 「不足なし」を信じる前に、`select` の中身 |
| 2 | フォーマットだけを単独コミット | `ruff format .` | 何も — レビュー不能だが無害であり、だからこそ分けている |
| 3 | ツールの導入、設定と CI の生成 | [`bootstrap`](docs/cli/bootstrap.md) | `--dry-run` の出力と、`ruff check .` が設定エラーではなく*違反*で落ちること |
| 4 | 今日の違反を天井として固定 | [`freeze`](docs/cli/freeze.md) | 表示される件数と、3 つの成果物が 1 コミットに入っていること |

フォーマットが lint より先なのは、そうしないと最初の drain PR が誰にもレビューできない空白の diff に
なるからです。freeze が最後なのは、フォーマット前に取った天井が後から理由不明のまま下がるからです。

**止めるならタダで止められるのは freeze の地点です。** そのコミット以降は CI が新しい違反を拒否するので、
run は最初の drain PR を出す前にそこで報告します — 件数と、ここから先の消化は任意であること。4 の後は
どの pull request で止めても、リポジトリが元より悪くなることはありません。

bootstrap が書くもの — 選択されるルール階層、固定される Action、各種しきい値 — はすべて
**[デフォルト設定一覧](docs/defaults.md)** にあります。既存の設定は決して上書きしません。

freeze が済めば、そのリポジトリは良くなる一方になります。既存コードは既得権として見逃され、新しい
コードにはルールセット全体が適用され、増えたものは CI が拒否します。

### 2 日目以降: backlog を潰す

```
backlog を潰して
```

**1 ルール 1 pull request** です。1 違反でも、全部まとめてでもありません。スキルは
[`next`](docs/cli/next.md) — 件数の大きさではなく作業コストで並べ替えたもの — からルールを選び、
コードに触れる**前に**現在の挙動を固定するテストを書き、修正し、稼いだ分だけ天井を下げます。

```bash
ebpy next                                          # どの 1 手が一番多くを強制できるか
ebpy prune                                         # 修正と同じコミットに入れる
ebpy log --kind drained --rule ruff:C901 "..."     # 理由。これ以外に記録するものはない
ebpy check                                         # 何も増えていないことの確認
```

既定で自動化し、issue を作るのは本当に所有者の判断が要る 4 つだけです — 挙動が曖昧なもの、公開 API
の変更、単独プロジェクト級のリファクタ、このリポジトリではルール自体が誤りかもしれないもの。
ループの全体は [`ebpy-drain`](docs/skills.md#ebpy-drain) にあります。

### CI では

生成されるワークフローにはすでにゲートが入っています。自分で組む場合、重要なのは 2 行です。

```yaml
      - run: ebpy check              # 天井を超えて増えていたら失敗
      - run: ebpy report             # backlog を ルール × 領域 の表で
        if: always()
```

ベースラインを「メモ」ではなく「ラチェット」にするのが [`check`](docs/cli/check.md) です。
[`report`](docs/cli/report.md) は品質ゲートではなく、findings 自体は終了コードを変えません。ただし、
天井 artifact が不正な場合は誤ったレポートを出さず fail closed します。
[`secrets`](docs/cli/secrets.md) はベースラインを持たない唯一の検査です — コミットされた鍵はすでに
公開済みなので、初回から止めます。

### しばらく空けてから戻るとき

```bash
ebpy status                # 診断が古いコードを指しているときは STALE を先頭に出す
ebpy diagnose --write      # 現在のコミット付きで取り直す
```

ラチェット自体は古くなりません — Ruff が常に現在のツリーに対して維持します。古くなるのは*診断*の方:
ギャップ一覧、ファイルサイズ、そして **Carried over** の deferred メモです。取り直したらその
チェックリストを読み返し、もう何も指していない項目は落としてください。

### CLI を直接使う

すべてのコマンドはスキルの有無に関係なく、どのリポジトリでも単独で動きます。

| コマンド | 用途 |
| --- | --- |
| [`install`](docs/cli/install.md) | uvプロジェクトにebpyと同じrefのClaude Codeスキルを追加 |
| [`skills install`](docs/cli/skills-install.md) | インストール済みebpyのスキルを `.claude/skills` に配置 |
| [`diagnose`](docs/cli/diagnose.md) | 読み取り専用: 何が足りないか、その不足が何を意味するか |
| [`bootstrap`](docs/cli/bootstrap.md) | 導入して設定ファイルを生成 |
| [`freeze`](docs/cli/freeze.md) | 今日の違反を天井として固定 |
| [`check`](docs/cli/check.md) | CI ゲート: 何かが増えていたら失敗 |
| [`next`](docs/cli/next.md) | どこから潰すべきか、その 1 手が何を強制できるようにするか |
| [`prune`](docs/cli/prune.md) | 修正後: 取り戻した天井を回収する |
| [`status`](docs/cli/status.md) | 現在のフェーズ、backlog、そして古びていないか |
| [`report`](docs/cli/report.md) | 違反の分布を markdown で（CI のジョブサマリ向け） |
| [`secrets`](docs/cli/secrets.md) | 履歴全体をスキャンして混入した認証情報を探す |
| [`catalog`](docs/cli/catalog.md) | 既存のヘルパー一覧（6 個目の同じ関数を書かせない） |
| [`log`](docs/cli/log.md) | 何をしたかを、現在のコミット付きで記録 |

フラグ、終了コード、共通オプションは **[CLI リファレンス](docs/cli/README.md)** に。

## 成果物

| ファイル | 所有者 | コミットするか |
| --- | --- | --- |
| `.ebpy/baseline.json` | ebpy | する — これ自体が天井 |
| `.ebpy/state.json` | ebpy | する — 台帳 |
| `QUALITY.md` | 台帳から描画 | する — 人間向けのビュー |

baseline と state は 2 ファイルで 1 つの天井契約です。片方だけが存在する、読めない、形式が不正、
または両者の天井が一致しない場合、artifact を使うコマンドは計測や書き込みの前に失敗します。
片方からもう片方を復元することはしません。対応する 2 ファイルを揃えて復元するか、古い契約を
破棄してよい場合だけ `ebpy freeze --force` で完全な新しい契約を固定します。

`QUALITY.md` は毎回再生成され、台帳から描画された 4 つのセクションを持ちます。フェーズを
チェックボックスにした **Worklist**（残件の少ないルールを子項目に）、意図的に見送った
リファクタの **Carried over**、**Ratchet** テーブル、そして **Work log**。
`<!-- ebpy:notes:start -->` マーカーの間に書いたものは再描画後も残ります。

## フェーズ

| フェーズ | 内容 |
| --- | --- |
| P0 diagnose | 調査し、すべての不足に名前を付ける |
| P1 bootstrap | 導入し、設定を生成する |
| P2 freeze | 天井を固定し、CI をゲートする |
| P3 drain | 1 ルールずつ潰す。見つけたバグにはテストを付ける |
| P4 tighten | 次のルール階層を追加して繰り返す |
| P5 split & DRY | 重複とデッドコードを消す |

価値があるのは P3 と P5 で、ここは**既定で自動化**されます。修正、関数の抽出、テストの追加、孤児
ファイルの削除は、聞かずにやります。所有者の判断が要るリファクタだけが GitHub issue になり、その
issue には選択肢と、エージェントならどれを選ぶかが書かれます。

## ドキュメント

| | |
| --- | --- |
| [スキルリファレンス](docs/skills.md) | 各スキルが何をして、何を譲らず、何をやらないか |
| [CLI リファレンス](docs/cli/README.md) | コマンドごとに 1 ページ、フラグと終了コード付き |
| [デフォルト設定一覧](docs/defaults.md) | `bootstrap` が書く値のすべてと、その理由 |
| [リリース](docs/release.md) | `main` へのマージが何を出荷し、バージョンを何が決めるか |
| [共有ヘルパー](docs/shared-helpers.md) | `ebpy catalog` がこのリポジトリ自身のソースから生成 |

## ever-better との違い

逐語移植ではありません。考え方は同じで、機構は Python エコシステムに従います。

- **ラチェットは ebpy 自身のもの。** ESLint には `--suppress-all` がありますが Ruff にはないため、
  `freeze` / `check` / `prune` がファイル別ルール別の台帳を直接実装しています（ファイル形式は
  ESLint と同じ形）。
- **mypy は Ruff と同じファイル別ルール別のセルモデルでラチェットします。** ルール ID は
  namespace 付き — `ruff:F401`、`mypy:arg-type` — なので Ruff と mypy のセルが衝突せず同じ天井を
  共有します。
- **構文エラーは数えず、名指しする。** Ruff はこれをルール名なしの `invalid-syntax` として報告
  します。既得権化できないので、freeze も check も 0 を記録せずに拒否します。
- **fan-in は Python の import を解決します** — 相対、絶対、`src/` レイアウトの両方。
- `migrate` と `emit-diff` はありません。JavaScript → TypeScript に相当するものが Python には
  なく、「型だけのリファクタが挙動を変えていない」ことを証明できるコンパイル出力もないためです。

## リリース

出荷元は `main` です。`src/ebpy/` か `skills/` を変更した PR がマージされるとバージョンが上がり
(上げ幅は前回タグ以降の Conventional Commits が決めます)、`CHANGELOG.md` を書き、コミットにタグを
打ち、GitHub Release を作ります。どちらも触っていないマージはリリースされず、PyPI への公開は行い
ません。実処理は [python-semantic-release](https://python-semantic-release.readthedocs.io) です。
ルールと「毎マージでリリースする」ことの根拠は [docs/release.md](docs/release.md) に。

## 設計

エージェントが実行のたびに遅く、あるいは違うやり方でやってしまうことは CLI に。markdown の
チェックリストで表現できないことはスキルに。

ランタイム依存はゼロ。

## ライセンス

MIT。オリジナルの著作権は isamu 氏、本移植の著作権はそのコントリビュータに帰属します。
