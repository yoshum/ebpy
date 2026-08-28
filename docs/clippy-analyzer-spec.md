# Clippy analyzer 導入仕様

Rust/Clippy を ebpy の analyzer として導入するための仕様。

ebpy は「今日の違反を天井として記録し、天井は下がるだけで上がらない」という ratchet を核に持つ。
この核（計測 → 天井 → ゲート）は既にツール非依存であり、Rust 対応とはこの核を Rust に開くことを指す。
一方 `diagnose` / `bootstrap` 系は Python の語彙に強く結び付いており、本仕様では**開かない**。
どこまで開くかを §2 でサブコマンド単位に確定させる。

各決定には **根拠** を付す。根拠は次の3種のいずれかで、種別によって将来の扱いが変わる。

| 種別 | 意味 | 変更時の扱い |
| --- | --- | --- |
| 契約 | 公式ドキュメントまたはツールチェイン同梱の man に明記されている | 破られたら上流のバグとして報告できる |
| 観測 | 実測のみ。ドキュメントに記載を見つけられなかった | 回帰テストで固定する。前提にしてはいけない |
| 実装読解 | ebpy 自身のコードから確認した | テストで固定する |

引用したコードと行番号は `ad738b2` のもの。

---

## 1. 目的

Rust リポジトリ、および Rust と Python が同居するリポジトリに対して、clippy の違反を
ratchet の対象にできるようにする。具体的には `ebpy freeze` が clippy の違反を天井として
固定でき、`ebpy check` がその天井を守れるようにする。

---

## 2. 対応範囲

### 2.1 サブコマンド別の対応可否

本仕様の完了時点で、Rust のみのリポジトリにおける各サブコマンドの状態を次のように確定させる。
「対応」は Rust リポジトリで正しい結果を返すこと、「拒否」は誤った結果を返さずに明示的に
断ることを指す。**黙って空の結果を返すことはどちらでもない**（§2.3）。

| サブコマンド | Rust リポジトリでの扱い | 根拠 |
| --- | --- | --- |
| `ebpy freeze` | **対応** | 天井の固定。ratchet の核のみを使う |
| `ebpy check` | **対応** | ゲート。ratchet の核のみを使う |
| `ebpy prune` | **対応** | 天井の引き下げ。ratchet の核のみを使う |
| `ebpy report` | **対応** | 計測結果と天井のみを読む（`commands/report.py` の依存に facts は無い） |
| `ebpy status` | **対応** | 台帳と git を読む（`freshness_of`）。analyzer の計測は行わない |
| `ebpy log` | **対応** | 台帳と git のみを読む |
| `ebpy secrets` | **対応** | gitleaks と git のみを使う。元から言語非依存 |
| `ebpy next` | **対応** | 天井のセルのみから順序を決める（`commands/next_command.py:31-38`） |
| `ebpy next --fan-in` | **拒否**（新規） | `repo/fan_in.py` が Python の import を解決する（`next_command.py:37`） |
| `ebpy diagnose` | **拒否**（新規） | §2.2 |
| `ebpy bootstrap` | **拒否**（新規） | Python の dev dependency と `setup-python` 前提の CI を生成する |
| `ebpy catalog` | **拒否**（新規） | Python の ast を解析する（`catalog.py:111-118`） |
| `ebpy install` | **拒否**（実装済み） | `pyproject.toml` が無ければ既に断る（`commands/install.py:165`） |
| `ebpy skills install` | **拒否**（実装済み） | `pyproject.toml` が無ければ既に断る（`commands/skills_install.py:292`） |

### 2.2 拒否が必要な理由

`diagnose` / `bootstrap` / `catalog` / `next --fan-in` は現在**ガードを持たない**。Rust のみの
リポジトリで実行すると例外を出さず、「誰も見ていない」を「ゼロ」として描画する。

| 箇所 | Rust のみのリポジトリでの出力 |
| --- | --- |
| `repo/facts.py:84,131`（`.py` 固定） | `SizeDistribution(total=0)` → 「600行超のファイルは0件」と読める |
| `repo/detect/package_manager.py:33` | 既定値 `"pip"` → cargo プロジェクトを pip と表示する |
| `catalog.py:111-118`（`.py` 固定） | "No public functions found."（`catalog.py:87`） |
| `repo/fan_in.py` | `--fan-in` の importers が静かに空になる |
| `repo/detect/ci.py` | clippy を回す CI を「lint していない」と判定する |

いずれも CLAUDE.md の *Absence and zero are different* に正面から抵触する。

### 2.3 対応でも拒否でもないもの

本仕様は「黙って空の結果を返す」を許容しない。上表のいずれのサブコマンドも、Rust のみの
リポジトリに対して**正しい結果を返すか、断るかのどちらか**でなければならない。

### 2.4 Python と Rust が同居するリポジトリ

拒否対象のサブコマンドは従来どおり Python 部分について動作する。拒否は「Python が検出されない
リポジトリ」に対してのみ発生する（D-11）。

混在リポジトリは本仕様が最も価値を持つ場面でもある。clippy 対応版に上げて初めて `diagnose` を
走らせたとき、次の順で「clippy で ratchet できます」という gap が発火する。

1. Python が検出されるので D-11 のガードを通る
2. Rust も検出される（`Cargo.toml` の存在から。workspace のトポロジだけを `cargo metadata` が
   確定する。D-3）
3. `state.frozen_analyzers` に clippy はまだ無い
4. 言語由来の unratcheted gap が clippy を提案する（D-16）

### 2.5 どこまで守り、どこから守らないか

**この仕様が守る失敗は3つに限る。**

| # | 守る失敗 | なぜ |
| --- | --- | --- |
| 1 | 天井が**黙って**下がる / 空になる | ratchet の存在意義そのもの。検出できない後退が最悪 |
| 2 | 存在しない位置のセルが天井に**載る** | 再現しない天井は天井ではない |
| 3 | 主流の Rust リポジトリが**計測不能になる** | 使えないゲートは無いゲートと同じ |

**守らないもの: ebpy が測る構成の外にあるコード。** ebpy は**ただ1つのビルド構成**
（default feature、実行中のプラットフォーム、cfg フラグなし）を測る。その外にあるコードは
天井に載らず、**ゲートもされない**。`#[cfg(feature = "x")]`、`#[cfg(target_os = "windows")]`、
`#[cfg(fuzzing)]` の下はすべてこれに当たる。**元々測れていない範囲については、
天井が下がらないことは守るが、上がらないことは守れない。**

**ただし「package が丸ごと測れなくなる」は守る。** 天井に載っていた package が計測から
落ちたら——workspace がビルドできなくなった、manifest が解決できなくなった——それは
1番目の失敗そのものである。D-6 と D-17 が fail-closed し、契約を狭めるには `freeze --force`
を要求する。

**守れる粒度は package までである。ここは正確に書く。** 前版はここを「天井に載っている
セルが構成の変更で測れなくなったら守る」と書いていたが、**果たせない約束だった**。

```toml
# freeze 時
[features]
default = ["extra"]     →  #[cfg(feature = "extra")] の中の警告が天井に載る

# あとで
default = []            →  その item はコンパイル対象から消える
```

実測（1.96）: **ビルドは両方とも成功し**、警告だけが 1 件から 0 件になる。エラーが出ないので
D-6 の分類は動かず、package も workspace も消えないので D-17 の集合も変わらない。
`prune` は素直に天井を下げる。

**これは検出できない、という以前に区別できない。** セルが消えた理由は2つあり、

```
(a) 誰かが警告を直した          →  天井が下がるべき。ratchet の目的そのもの
(b) その item が構成から外れた  →  天井が下がってはいけない
```

**同じ1回の計測からは、この2つが同じに見える。** 区別するには2つ目の構成をビルドするか
ソースを解析するしかなく、どちらも計測の seam の外にある。

**これは clippy 固有の限界ではない。** ruff の `exclude` にディレクトリを足せば、同じ形で
セルが消えて天井が下がる。**既存の設計が既に受け入れている限界**であり、clippy でだけ
塞ぐと、同じリポジトリの中で analyzer ごとに保証の強さが違うことになる。

**測っていない範囲が package 単位で増えることは、黙って起きてはならない。**

**守らないもの: 敵対的な入力。** clippy と cargo は信頼する。ebpy が防ぐのは**事故**であって、
**攻撃**ではない。リポジトリに書き込める者は既に `.ebpy/` にも書き込めるので、
clippy の出力を偽装する脅威モデルは成立しない。

この線引きが具体的に意味すること:

- パスの検査は**天井の座標に置けるか**だけを見る。置けなければ `UnattributedFinding` に
  なり、`incomplete` として fail-closed する。**置けない理由ごとに分岐を増やさない** —
  UNC も drive-relative も NUL も symlink ループも、同じ1つの結論に落ちる。
- `cargo clippy` の名乗り検査（D-5）は、**alias の事故を検出する**ためのものであって、
  意図的な偽装を防ぐものではない。
- 型検査は **ebpy が読むフィールド**に限る。読まない値の破損で計測を落とさない。

> **この節は、この仕様書がこれ以上場合分けで膨らまないための歯止めである。** 「rustc が
> 理論上そう出力しうる」は、それ自体では決定を増やす理由にならない。**上の3つのどれかを
> 侵すか**を先に問うこと。侵さないなら、既存の一般規則が既に受け止めている。

### 2.6 本仕様の範囲外

| 項目 | 前提となる作業 |
| --- | --- |
| clippy の自動インストール（`ebpy bootstrap` での provisioner） | `InstallAction` を「1つの dev-install コマンド」から「コマンド列」へ一般化する（D-12） |
| Rust リポジトリの `ebpy diagnose` | `repo/facts.py` の多言語化（サイズ分布、ソース列挙） |
| Rust リポジトリの `ebpy catalog` / `next --fan-in` | Rust の公開 API 抽出と依存解決 |
| Rust リポジトリへの `ebpy install` / `ebpy skills install` | `pyproject.toml` 以外への ebpy 自身のピン留め |
| `cfg(test)` のコード / integration test / example / bench を天井に載せるか | D-5 の `--all-targets` の判断 |
| non-default feature 配下のコード | feature 組合せの選択規則の設計 |

#### `detect_ci` の近似は本仕様では直さない

`detect_ci`（`repo/detect/ci.py:41`）は `ebpy check` を見つけると `runs_lint` と `runs_typecheck`
を**両方** true にする。「`check` は必ず ruff と mypy を走らせる」という現行の前提に基づく近似で
ある。D-1 の後、config が ruff だけを宣言していれば mypy は走らないので、この近似は
やや広めの主張になる。また `cargo clippy` を書いた CI は `runs_lint` に数えられない。

**本仕様ではこれを直さない。** `detect_ci` の唯一の利用者は `diagnose`（`decide/diagnose.py:149`）
であり、`diagnose` は §2.1 で Rust 非対応と決めたサブコマンドである。ここに `scope` を通すと、
断ると決めたコマンドの中身を作り込むことになり、宣言したスコープを越える。

近似が広めに出る向きも書いておく: `runs_typecheck=True` は「CI で型検査が走っている」という
**過大な主張**になりうるが、gap を出さない側に倒れるだけで、天井にも gate にも影響しない。
`ebpy check` 自身は D-4 の照合で scope 不一致を断つので、**gate が緩むことは無い**。

**v1 が測る target を明記しておく。** `--all-targets` を付けないので、cargo の既定である
**lib と bin だけ**が対象になる。`tests/` の integration test、`examples/`、`benches/`、
および `cfg(test)` のコードは**天井に載らない**。天井は「default feature の lib と bin に
見える違反」を意味する、と読むこと。

**non-default feature のコードは測らない。** D-5 のコマンドは default features だけを有効にする
（Cargo の既定）。`--all-features` を既定にはしない — 相互排他的な feature を持つクレートでは
ビルド自体が壊れ、`build-finished.success=false` で計測不能になるためである。天井は
「default features で見える違反」を意味する、と読むこと。

---

## 3. 決定事項

### D-1. 計測スコープを引数にする

`measure_repository(cwd)` を次のシグネチャに変更する。

```python
def measure_repository(cwd: Path, scope: tuple[str, ...]) -> Measurement: ...
```

`scope` を `tuple[str, ...]` に固定するのは、渡す側がすべてソート済み tuple だからである
（`ScopeDecision.to_measure` と `global_freeze_scope` の戻り値型）。集合を受け取る形にすると、
出力の順序が呼び出しごとに変わりうる。登録済み analyzer を
全走査する現在の実装をやめ、スコープは呼び出し側が渡す。

> **根拠: 実装読解。** 現在の実装は「登録済み = このリポジトリに該当する」を暗黙に同一視している。
> clippy を `ANALYZERS` に足すとこの同一視が破れ、Python リポジトリで次の2つが壊れる。
>
> - **新規リポジトリの初回 `ebpy freeze` が全損する。** 既定スコープが
>   `set(ANALYZER_NAMES) | frozen_analyzers`（`commands/freeze.py:337`）なので clippy が入り、
>   `build_global_freeze` は fail-closed（`commands/freeze.py:207`）なので `Unavailable` が
>   1つでもあれば拒否する。導入経路そのものが使えなくなる。
> - **すべての `ebpy check` に恒久的なノイズが乗る。** `_non_contract_notes`
>   （`commands/check.py:135`）が毎回 `clippy was not measured and has no ceiling here.` を出す。
>
> これは clippy 導入のための代償ではなく、独立した設計の是正でもある。現状、Rust のみの
> リポジトリが `.ebpy/config.json` で clippy だけを宣言しても、`check` は ruff と mypy を実行して
> 両方についてノートを出す。スコープ化はこれも解消する。

**変更対象は `tools/registry.py:76`。** `measurement/` ではない。

```python
# tools/registry.py:76
def measure_repository(cwd: Path) -> Measurement:
    """Measure every registered analyzer, retaining partial success as data."""
    return Measurement(analyzers={a.name: a.measure(cwd) for a in ANALYZERS})
```

制約は **「registry は方針を持たない。スコープは値として受け取る」**である。

> **根拠: 実装読解。** `docs/measurement-seam.md` は *The seam owns measured facts. It does not
> own ceilings, gate policy or persistence.* と定めており、スコープ選択は policy である。
> なお `measurement/` は元から `ANALYZERS` を知らない（`measurement/__init__.py` の docstring が
> *an abstract leaf … imports nothing from the concrete `tools` runners*）ので、`measurement/` に
> 制約を課す文は何も制約していない。
>
> また `tools/` が `repo/` を import することは**既存の作法**であり、循環は生まれない
> （`tools/ruff/detector.py:9`、`tools/mypy/detector.py:10`、`tools/pytest.py:10` ほか。
> 逆向きの import は存在しない）。D-3 の検出関数を runner から import してよい。

### D-2. Analyzer は自分が測る言語を自己申告する

`src/ebpy/models.py` に追加する。

```python
Language = Literal["python", "rust"]
```

`Analyzer` プロトコルに property を追加する。

```python
class Analyzer(Protocol):
    @property
    def language(self) -> Language:
        """The language this analyzer measures — intrinsic to the tool, not to any repository."""
```

`RuffAnalyzer` と `MypyAnalyzer` は `"python"`、`ClippyAnalyzer` は `"rust"` を返す。
`ToolDetector` は同じ `Language` 型を**集合で**持つ（D-13。理由もそこに書いてある）。

**`Enum` は使わない。** `Literal` 型エイリアスがこのリポジトリの唯一の作法であり
（`src/` 全体で9件、うち `models.py` に5件。`Enum` は `src/` に0件）、既存の直列化は生の文字列を
そのまま読み書きしている（`models.py:158` の書き込みに `.value` は無く、`models.py:190` の
読み込みに再構築は無い）。Enum はこの対称性に変換層を持ち込む。

**`LANGUAGES` タプルも `typing.get_args` も足さない。** `PHASE_ORDER` / `LOG_KINDS` が存在するのは
実行時に全値を列挙する消費者がいるためだが（`render/quality.py:68`、`commands/log.py:29`）、
言語にはその消費者がいない。スコープ関数は `ANALYZERS` と検出結果を回り、detector は自分の
マーカー表を回るだけで、言語の全体集合を列挙しない。`get_args` は `src/` に0件である。

**単数形で始める。** 現在の3つはすべて単一言語であり、単数から `tuple[Language, ...]`
（空タプル = 言語非依存 = 常にスコープ内）への変更は型検査が全箇所を教える機械的な作業になる。
`docs/measurement-seam.md` の「2つ目の実装が現れるまで抽象化しない」がそのまま適用できる。

> **禁止事項。** 言語非依存の analyzer が必要になったとき、`Literal[..., "any"]` のような
> メンバー追加で解決してはいけない。`Framework` の `"none"` は「フレームワークが無い」という
> **不在**を意味するが、言語における `"any"` は「すべてに当てはまる」という**普遍**であり、
> 意味が逆になる。CLAUDE.md の *Absence and zero are different* が禁じている混同である。
> そのときは複数形に広げる。

### D-3. 言語検出はリポジトリルートの関数として一箇所に置く

`src/ebpy/repo/detect/language.py` を新設する。検出は「ルートに設定ファイルがあるか」ではなく
**リポジトリルートパスの関数**として言語ごとに実装し、根拠を値として返す。

```python
# repo/detect/language.py — ファイルシステムだけを読む。失敗しない。

# 純粋関数。既に列挙済みの呼び出し側はこちらを使う。
def languages_from_files(all_files: Iterable[str]) -> RepoLanguages: ...


# cwd ラッパー。列挙していない呼び出し側はこちら。
def detect_languages(cwd: Path) -> RepoLanguages:
    return languages_from_files(list_all_files(cwd))


def has_python(cwd: Path) -> bool: ...
def has_rust(cwd: Path) -> bool: ...


@dataclass(frozen=True)
class RepoLanguages:
    languages: frozenset[Language]


# tools/clippy/_runner.py — cargo に訊く。失敗しうる。
@dataclass(frozen=True)
class RustWorkspace:
    """A Cargo workspace inside this repository, as cargo itself reports it."""

    root: PurePosixPath  # repository root からの相対。必ず repo 内に収まる
    target_directory: Path  # cargo metadata が返した絶対パス
    packages: tuple[str, ...]  # member の package ディレクトリ（リポジトリ相対、昇順）


@dataclass(frozen=True)
class RustTopology:
    """What cargo could and could not resolve in this repository."""

    workspaces: tuple[RustWorkspace, ...]
    unmeasured: tuple[UnmeasuredScope, ...]  # 解決できなかった候補（D-6）


def rust_topology(cwd: Path) -> RustTopology:
    """Resolve this repository into the Cargo workspaces ebpy can measure.

    Candidates cargo cannot resolve are reported in `unmeasured` rather than
    raising, so one vendored manifest cannot make the whole repository unmeasurable.

    Raises:
        ClippyNotFoundError: cargo cannot be executed.
        ClippyFailedError: **no** candidate resolved.
        ClippyInvalidOutputError: metadata output cannot be interpreted safely.
    """
```

**戻り値を tuple から `RustTopology` に変えたのは、部分的な失敗を表す型が無かったからである。**
前版は `tuple[RustWorkspace, ...]` を返し、metadata の失敗はすべて例外にしていた。D-6 が
「一部の候補だけ落ちたら外して続行」と決めた時点で、この型では**成功した workspace と
外した候補を同時に返せない**。実装者は「外した候補を D-17 に渡せない」か「正常な root まで
`Failed` にする」かを選ばざるを得ず、どちらも仕様に反する。**決定を変えたなら、境界の型も
変える。**

**`ClippyInvalidOutputError` は例外のままである。** metadata が非成功終了する（候補が解決
できない）のと、成功したのに出力が読めないのは別である。前者はリポジトリの形についての
事実だが、後者は **ebpy が cargo を読めていない**という事実であり、そこから「この候補は
測れない」と結論してはいけない。D-6 の判定順で「読めない出力からは何も結論できない」と
決めているのと同じ理由である。

**2つのパスの意味が型に出ている。** `root` は必ずリポジトリ相対で repo 内、`target_directory` は
cargo が返した絶対パス。D-9 がパスの意味論に強く依存しているので、両方を裸の `str` にはしない。

**`packages` を持たせるのは、後段で復元できないからである。** D-6 は workspace を外すとき
その全 member のディレクトリを `UnmeasuredScope.packages` に入れる（root では範囲の変化を
検出できない）。member が分かるのは metadata を読んだこの瞬間だけで、parser が受け取るのは
`RustWorkspace` と `repo_root` だけである。**ここで捨てると、後から取り戻す方法が無い。**
D-3 は既に `workspace_members` を metadata から読んで検証しているので、追加の実行は要らない。

#### 検出は失敗しない。トポロジの確定だけが失敗しうる

**言語検出はファイルシステムだけを読む。**

> **「失敗しない」の範囲を書いておく。** 検出そのものに失敗の分岐は無いが、下敷きの
> `_walk_files`（`repo/facts.py:48`）は `iterdir()` の `OSError` は捕まえる一方、
> その後の `entry.is_dir()` / `entry.is_file()` は捕まえていない。読めないディレクトリを
> 含むリポジトリで例外が出る余地が残る。**本仕様はこの walker を強化しない** — git 経路が
> 既定であり、walk はフォールバックである。ここを直すのは検出の問題ではなく
> `RepoFacts` の堅牢性の問題であり、clippy とは独立に扱う。

| 言語 | 判定 |
| --- | --- |
| `"python"` | 下表のいずれかが任意の深さに存在する |
| `"rust"` | `Cargo.toml` が任意の深さに存在する（`target/` 配下を除く） |

**workspace のトポロジを確定するのは clippy runner の仕事**であり、`repo/detect/` の仕事ではない。
`rust_topology()` は `tools/clippy/_runner.py` に置き、失敗は既存の3層の例外で表す
（`tools/ruff/_runner.py:27-35` と同じ形）。**新しい例外型は要らない。**

| 状況 | 送出 | `ClippyAnalyzer.measure()` が作る observation |
| --- | --- | --- |
| `cargo` 実行ファイルが無い（`OSError`） | `ClippyNotFoundError` | **`Unavailable`** |
| cargo は動いたが metadata が非成功終了 | `ClippyFailedError` | `Failed("execution-failed")` |
| metadata の出力が JSON として読めない / 必須フィールドを欠く（`packages` を含む） | `ClippyInvalidOutputError` | `Failed("invalid-output")` |
| metadata は読めたが `workspace_root` が repo 外 | `ClippyInvalidOutputError` | `Failed("invalid-output")` |

必須フィールドは `workspace_root` / `workspace_members` / `packages`（各要素の `id` と
`manifest_path`）/ `target_directory`。出力が
壊れている場合を `invalid-output` にするのは D-6 と同じ立場である — 「ツールが走って失敗した」
のではなく「ツールの出力を ebpy が読み切れなかった」。`measure()` の except 節は ruff と同じ順序で書ける — 実際の ruff は
**`NotFound` → `InvalidOutput` → `(Failed, OSError)`** の順である
（`tools/ruff/analyzer.py:30-37`）。

> **なぜ検出を cargo から切り離すか。** 検出が cargo を起動して失敗しうると、
> **`cargo` が入っていないマシンでは混在リポジトリの scope を作れず、ruff と mypy まで
> 測れなくなる**。
>
> ```
> repo/pyproject.toml, repo/src/foo.py, repo/rust/Cargo.toml   かつ cargo 未インストール
>   検出が失敗する設計 → scope を作れず ebpy check 全体が停止
>   本仕様            → ruff: Measured / mypy: Measured / clippy: Unavailable
> ```
>
> 後者が measurement seam の設計そのものである。`Measurement` は analyzer ごとの observation を
> 持ち、部分的な成功を値として保持する。cargo の不在は **clippy という analyzer の可用性**で
> あって、リポジトリの言語検出の失敗ではない。

> **検出と runner がずれないという保証は、リポジトリ universe の中で成り立つ。** 検出は
> runner が測れる範囲より**広い側にしかずれない** — universe の中に `Cargo.toml` があれば
> clippy は必ず scope に入り、runner が測れなければ `Unavailable` か `Failed` として現れる。
> **黙って scope から消えることが無い**のが要点であり、差は必ず observation として表面化する。
>
> **ebpy の repository universe を定義しておく。**
>
> ```
> universe = git ls-files --cached --others --exclude-standard
>          = tracked ∪ (untracked ∧ 非 ignore)
> （git 管理外では filesystem walk）
> ```
>
> **gitignore された `Cargo.toml` は universe の外であり、本仕様は非対応とする。** そこに
> workspace があると、Python があるので scope 自体は空でない混在リポジトリで、
> **clippy が gap にも `Unavailable` にも現れず静かに抜ける**。これは「逆向きは起こらない」の
> 例外であり、**既知の穴として明示的に受け入れる**。
>
> 塞がない理由は、塞ぐ費用が釣り合わないことである。ignored ファイルまで含む別の列挙規則を
> 作ると、除外ディレクトリ、fixture / vendor の混入、symlink、複数 workspace の扱いを
> すべて設計し直すことになり、**しかも universe が2つに割れる** — 検出・`RepoFacts` ・runner が
> 別々のものを見る状態は、この仕様が D-3 で消したはずの状態そのものである。
>
> ratchet に載せたいコードを gitignore するのは、そもそも普通の構成ではない。

#### Python 専用コマンドのガードが cargo に触れないこと

| 用途 | 呼ぶもの | cargo を起動するか |
| --- | --- | --- |
| Python 専用サブコマンドのガード（D-11） | `has_python()` | **しない** |
| analyzer スコープの決定（D-4） | `detect_languages()` | **しない** |
| clippy runner の計測対象（D-5） | `rust_topology()` | する |

#### Rust の判定規則 — `cargo metadata` に訊く

ファイル配置から推測せず、cargo 自身に workspace の境界を答えさせる。

```
候補 = facts.all_files のうち basename が Cargo.toml のもの（target 除外後、決定的な順序）

未処理の候補 c について:
  manifest = repo_root / c        ← c はリポジトリ相対。必ず絶対に直す
  [1] cwd = manifest.parent
      cargo metadata --no-deps --format-version 1 --manifest-path <manifest>
      workspace_root が repo 外                   → ClippyInvalidOutputError
  [2] cwd = workspace_root
      cargo metadata --no-deps --format-version 1
      workspace_root が [1] と一致しない          → ClippyInvalidOutputError
      採用するのは [2] の target_directory / workspace_members / packages
  workspace_members の各 Package ID を packages[].id と突き合わせる
      ちょうど1件に対応しない ID がある           → ClippyInvalidOutputError
      対応する packages[].manifest_path が repo 外 → ClippyInvalidOutputError
  「処理済み」にするのは次の3つ（resolve 後の絶対パスで照合）:
      - 候補 c 自身
      - workspace_root / "Cargo.toml"
      - 対応した packages[].manifest_path すべて
  workspace_root で重複排除して RustWorkspace を1つ得る

残った未処理の候補を続けて調べる  ← excluded / 独立 package がここで拾われる
```

**候補の母集合は `facts.all_files`**（`repo/facts.py:67` の `list_all_files`）とする。
**`has_python()` / `has_rust()` / `rust_topology()` の3つとも、この同じ**列挙規則**を使う。**
disk を別途 walk する経路を新設しない — 規則が2つあると「どちらが scope を決めたのか」が
再現できなくなる。

**ただし3つが同じ *snapshot* を見るわけではない。** 検出は `RepoFacts` を通るが、計測経路には
`RepoFacts` が存在しない — `Analyzer.measure(cwd)`（`measurement/analyzer.py:32`）も
`measure_repository(cwd, scope)` も `cwd` しか受け取らないからである。

| 関数 | 入手経路 |
| --- | --- |
| `languages_from_files(facts.all_files)` | 既に手元にある `RepoFacts` から（再列挙しない） |
| `detect_languages(cwd)` / `has_python(cwd)` / `has_rust(cwd)` | その場で `list_all_files(cwd)` |
| `rust_topology(cwd)` | 計測時に `repo.facts.list_all_files(cwd)` を**再列挙する** |
| `ClippyDetector.detect(facts)` | `facts.all_files` |

呼び出し側の割り当ては次のとおり。

| 呼び出し側 | 使うもの | 理由 |
| --- | --- | --- |
| `diagnose` / `bootstrap` | `languages_from_files(facts.all_files)` | 既に `gather_facts()` 済み（`commands/diagnose.py:30`）。二重列挙にしない |
| `ClippyDetector.detect(facts)` | `facts.all_files` | detector の契約が `RepoFacts` を受け取る |
| `check` / `freeze` / `prune` / `report` | `detect_languages(cwd)` | `RepoFacts` を持たない |
| D-11 のガード | `has_python(cwd)` | 同上 |

**純粋関数と cwd ラッパーを分ける理由。** `cwd` しか受け取らない形にすると、`RepoFacts` を
既に読んだ `diagnose` と `bootstrap` が**同じディスクを2回歩く**ことになる。`RepoFacts` の
契約は *Everything read from disk once, so decisions stay pure* であり、その1回を無駄にする。

**v1 は計測経路での再列挙を選ぶ。** 同じ snapshot を渡すには `Analyzer` Protocol か registry の API を
`RepoFacts` まで広げることになり、measurement seam が「ツールを走らせて値にする」以上のものを
知ることになる。検出と計測の間にファイルが増減すれば結果は変わりうるが、**その差は
observation として表面化する**（D-3 の「広い側にしかずれない」と同じ性質）。

**この集合の正確な意味を書いておく。** git リポジトリでは
`git ls-files --cached --others --exclude-standard`（`repo/git.py:63`）であり、
**tracked なファイルと、untracked かつ非 ignore のファイルの和**である。「git 管理下のファイル」
ではない。git 管理外では filesystem walk にフォールバックする。したがって
**gitignore されたファイルは言語検出にも workspace 候補にも現れない**。

#### Python のマーカー

| 種別 | マーカー |
| --- | --- |
| ソース | `.py` / `.pyi` / `.pyw` / **`.ipynb`** |
| プロジェクト定義 | `pyproject.toml` / `setup.py` / `setup.cfg` / `requirements*.txt` / `Pipfile` |
| ツール設定 | `ruff.toml` / `.ruff.toml` / `mypy.ini` / `.mypy.ini` |
| ロックファイル | `uv.lock` / `poetry.lock` / `pdm.lock` / `Pipfile.lock` |

**`.ipynb` を入れるのは、ruff が既定で notebook を探索するためである。** 現行の
`ruff check .` は `.py` を1つも持たない notebook 専用リポジトリでも動く。`.py` だけを
マーカーにすると、そこが空 scope になって**今日動いているものが動かなくなる**。

**ツール設定とロックファイルも同じ理由で入れる。** 判定の理由節が `uv.lock` を例に挙げて
いたのに判定表に無い、という食い違いもここで消える。

**マーカーを広く取るのは、狭い側に外れたときの害が大きいためである。** 広すぎれば
ruff と mypy が「何も無い」と報告するだけだが、狭すぎれば**今日ゲートされている
リポジトリが黙って scope から落ちる**。

**`.pyi` / `.pyw` を入れるのも、現行の挙動を狭めないためである。** 今日の `measure_repository` は
registry の全 analyzer を無条件で走らせるので、`.py` も config も持たない stub 専用
リポジトリでも ruff と mypy が動く。`.py` だけを検出マーカーにすると、そこが空 scope になり
**D-1 が「既存の Python リポジトリの挙動は変わらない」と言えなくなる**。

`repo/facts.py` の `list_source_paths` は `.py` だけを返すが、あれは**サイズ分布のための
ソース列挙**であって言語検出ではない。名前が測っているものが違うので、揃える必要はない。

**`target` の除外は path segment 単位で行う。** リポジトリ相対パスを `/` で割り、いずれかの
segment が正確に `target` である候補を落とす。`target/` を gitignore しているリポジトリでは
git 経路で既に落ちているので、この規則が効くのは walk フォールバックと、`target/` を意図的に
コミットしているリポジトリである。

> **この規則が拾えないものを明記しておく。** `target-dir` の設定で target ディレクトリの名前を
> 変えているリポジトリでは、その配下の `Cargo.toml`（`cargo package` が置くものなど）が候補に
> 残る。metadata の `target_directory` は当該 workspace の分しか分からないので、候補を作る時点
> では使えない。残った候補は [1] の metadata に掛かり、同じ `workspace_root` を指すなら重複排除
> で畳まれ、repo 外を指すなら拒否される。**この規則は「target という名前の segment」を落とす
> だけであって、target ディレクトリ一般を落とすとは主張しない**（CLAUDE.md *Names measure
> claims*）。

**候補 `c` 自身と workspace root の manifest を、明示的に処理済みにする。** virtual workspace の
root manifest は `[package]` を持たないので、**`workspace_members` にも `packages` にも現れない**。
member の manifest だけを処理済みにする規則では、

- root から始めた場合、`c` 自身が未処理のまま残る
- member から離れた位置の virtual root を発見した場合、その root が後でもう一度 probe される
- 「未処理の先頭を繰り返す」実装では**無限ループになりうる**

という3つの分岐が生まれる。3つとも、上の3行を処理済みにすれば消える。

**候補は必ずリポジトリルートで絶対化してから渡す。** `facts.all_files` の要素は
リポジトリ相対の文字列である（`repo/facts.py:67`）。相対のまま
`cwd = c.parent` と `--manifest-path c` を組み合わせると、cargo は
`crates/a/crates/a/Cargo.toml` を探すことになる。**cwd を移す以上、パスは絶対でなければ
ならない。**

#### metadata に対する型検査と比較の方法

| 位置 | 要求 |
| --- | --- |
| 出力全体 | JSON object |
| `workspace_root` | `str` かつ絶対パス |
| `target_directory` | `str` かつ絶対パス。**repo 内であることは要求しない**（下記） |
| `workspace_members` | `list[str]` |
| `packages` | `list[dict]` |
| `packages[].id` | `str` |
| `packages[].manifest_path` | `str` かつ絶対パス |

**`target_directory` に containment 検査を掛けない。** cargo は環境変数 / config / CLI で
target ディレクトリをリポジトリの外に置ける。**そこを禁じる理由が無い** — 天井に載るのは
診断のパスであって成果物の置き場ではない。したがって `<target_directory>/ebpy-clippy` は
リポジトリ外に作られうる。D-5 の「`.gitignore` が効くので追跡されない」は
**target がリポジトリ内にある場合の話**であり、外にあるなら追跡の心配自体が無い。

**パスの比較と containment は `Path.resolve()` した結果どうしで行う。** repo 側も
`cwd.resolve()` を使う。字句比較にすると、symlink を挟んだチェックアウトや macOS の
`/tmp` → `/private/tmp` で、実際には repo 内なのに repo 外と判定される。**`repo_root` からの
相対パスに直す段（D-9 の前置）は resolve 後の絶対パスから計算する。**

**Package ID は不透明な文字列として完全一致でのみ扱う。** 分解も解析もしない。

> **根拠は「互換性対象外だから」ではない。** Cargo 1.77 以降、`package_id` は Package ID
> Specification として公式に定義されており、本仕様のサポート下限（1.79、§5.3）はそれより
> 新しい。したがって「内部表現は互換性の対象外」という前版の説明は、現在の契約より強すぎた。
> **解析しない理由は、必要が無いからである** — 対応づけは同じ metadata document の中で閉じて
> おり、完全一致だけで足りる。仕様が要求していない構文解析を書かない、というだけのことである。

**`workspace_members` は manifest path ではなく Package ID である。** 実測:

```
workspace_members : path+file:///…/crates/a#0.1.0     ← ID であってパスではない
packages[].id     : path+file:///…/crates/a#0.1.0
       manifest_path => /…/crates/a/Cargo.toml
```

したがって必須フィールドに **`packages`** が加わり、`id` → `manifest_path` の対応づけが要る。

> **member ごとの containment 検査は必要である（前版の主張を撤回する）。** 本仕様の前版は
> 「`workspace_root` が repo 内なら全 member も repo 内」と書いていた。**これは誤りだった。**
>
> 前版の根拠は、workspace 側だけに `members = ["../sibling"]` と書いた実測である。この形は確かに
> 拒否される。
>
> ```
> error: workspace member `…/sibling/Cargo.toml` is not hierarchically below
>        the workspace root `…/ws`
> ```
>
> しかし **member 側の manifest に `package.workspace` を書き添えると、cargo は root の外の
> member を受理する**。cargo 1.96.0 で実測:
>
> ```
> ws/Cargo.toml        [workspace] members = ["../sibling"]
> sibling/Cargo.toml   [package] … workspace = "../ws"     ← この行が要る
>
> cargo metadata (cwd=ws)  → exit 0
>   workspace_root    : …/ws
>   workspace_members : path+file:///…/sibling#0.1.0        ← root の外
> ```
>
> **しかもこの member は実際に lint され、報告パスは相対ではなく絶対で返る。** 同じ fixture に
> `return 1;` を置いて計測した:
>
> ```
> MSG warning clippy::needless_return ['/…/extmem/sibling/src/lib.rs']   ← 絶対パス
> BUILD-FINISHED success = True
> ```
>
> D-9 は絶対パスを拒否するので天井が壊れることは無いが、診断は
> 「clippy の出力が読めなかった」になり、原因（外部 member）を指さない。**metadata の段階で
> 断ち、原因を名指しする**ほうが正しい。
>
> したがって `workspace_root` の検査に加えて、**全 member の `manifest_path` を repo に対して
> containment 検査する**。ID から manifest への対応づけは同じ metadata document 内での一致比較
> だけに使い、**Package ID の内部表現は解析しない** — 完全一致だけで足り、構文解析を
> 必要としないためである（根拠の詳細は上の型検査の節を参照）。

> **metadata を2回叩く根拠: 契約。** `--manifest-path` は**探索の基準ディレクトリを移さない**。
> rustup は現在ディレクトリから toolchain override を探索し、cargo も現在ディレクトリから
> `.cargo/config.toml` を階層的に探索する。リポジトリルートから1回だけ叩くと、nested workspace
> が固定した toolchain や `target-dir` の設定を見落とし、D-5 のプローブに到達する前に失敗しうる。
>
> **rustup の優先順位には上位がある。** cwd に近い設定が勝つのは、CLI の `+toolchain` や
> `RUSTUP_TOOLCHAIN` が無い場合である。それらがあれば cwd に関わらずそちらが勝つが、
> **probe と計測を同じ cwd で行う**という設計はどちらの場合でも成立する — 上位 override が
> あるなら両方に同じものが掛かる。
>
> **[1] が失敗したら fallback しない。** 非階層 member では、member 側の toolchain 設定や
> `.cargo/config.toml` のせいで [1] が失敗し、workspace root からなら成功する、という
> ことが起こりうる。**それでも workspace root から測り直さない** — [1] の失敗は
> 「この manifest の属する workspace を確定できなかった」であって、確定できないまま別の
> cwd で測れば、**どの workspace を測ったのか誰も言えない計測**になる。fail-closed が一貫する。
>
> [1] は「この manifest はどの workspace に属するか」を訊くだけなので `c.parent` でよい。
> 採用する `target_directory` は、実際に `cargo clippy` を走らせる cwd（= `workspace_root`）から
> 見た値でなければならないので、[2] で取り直す。D-5 がツールチェインのために cwd を厳密に
> 定めているのと同じ理由である。

**「最も外側の `Cargo.toml`」という近似は使えない。** cargo は親ディレクトリの `[workspace]` を
探索し、`package.workspace` キーで別の root を明示することもできる。実測:

```
extws/Cargo.toml           [workspace] members=["myrepo/pkg","other"]   ← リポジトリの外
extws/myrepo/              ← ここがリポジトリルート
extws/myrepo/pkg/Cargo.toml   ← リポジトリ内で「最も外側」の Cargo.toml

myrepo/pkg を cwd にして cargo clippy --workspace:
   LINTED: myrepo/pkg/src/lib.rs
   LINTED: other/src/lib.rs        ← リポジトリ外のパッケージが lint される
```

しかもパスは**外部の** workspace root 相対で返るため、D-9 の前置を素直に当てると
`pkg/other/src/lib.rs` という**リポジトリ内に見える実在しないパス**になり、D-7 の containment
検査も通り抜ける。天井が黙って壊れる。

`cargo metadata` はこの状況を正しく報告する。同じ位置で実行すると
`workspace_root` はリポジトリ外の `extws` を指すので、**明示的に拒否できる**。

> **速度より完全性を採る根拠。** cargo の起動回数は増えるが、`--no-deps` の metadata は依存を
> 取得せずコンパイルもしないので、`cargo clippy` 1回に比べれば桁が違う。一方ここで近似を採ると、
> 落ちたクレートが「ゼロ」として天井に載り `prune` が天井を削る — ratchet の核が黙って壊れる
> 種類の誤りである。*Absence and zero are different* は、安いほうではなく正しいほうを選べと
> 言っている。

`target_directory` も同時に得られるので、D-5 の `--target-dir` に使う。

#### 判定を広く取る理由

存在の判定は Python も Rust も**意図的に広く**取る。D-1 が守ると約束したのは「既存の Python
リポジトリの挙動が変わらないこと」であり、そのためには Python がほぼ確実に検出される必要が
ある。Rust 側を広く取るのは、上の不変条件 — 検出は runner より広い側にしかずれない — を
成り立たせるためである。精密さが要るのは「どこで cargo を起動するか」のほうで、そこは
`rust_topology()` が cargo に訊いて決める。

> **根拠: 設計判断。** マーカーを analyzer ごとに分散させると、Python のマーカー集合
> （`setup.py` → `setup.cfg` → `pyproject.toml` → `uv.lock` …）が動くたびに ruff と mypy の
> 両方を直すことになり、しかも両者がずれても誰も気付かない。CLAUDE.md の *Names measure claims*
> にも反する — analyzer が持つマーカーは「この analyzer が測る種類のリポジトリか」を主張する
> 名前になるが、中身はただの言語検出である。
>
> 一方 `language` を Analyzer / ToolDetector に置くこと自体は妥当である。「ruff は Python の
> ツールである」はツールの定義そのものであり、リポジトリの状態に依存せず、長期に安定する。

### D-4. スコープと契約を1つの値にまとめ、計測前に照合する

`src/ebpy/decide/analyzer_scope.py` を新設する。「どの analyzer を測るか」には3つの権威が
関わるので、**3つを別々の引数として持ち回らず、1つの値にまとめる**。

```python
@dataclass(frozen=True)
class ScopeDecision:
    """どの analyzer を測るかについて、3つの権威が言っていることと、この build の能力。

    `declared` / `detected_analyzers` / `frozen` が方針を述べる3つの権威で、
    `registered_analyzers` は方針ではなく **この build が何を測れるか**の写しである。
    4つとも **analyzer 名の集合**であって、言語の集合ではない。
    """

    declared: frozenset[str] | None  # .ebpy/config.json。None は「未表明」
    detected_analyzers: frozenset[str]  # 言語検出から射影した analyzer 名（下記）
    frozen: frozenset[str]  # state.frozen_analyzers
    registered_analyzers: frozenset[str]  # この build の ANALYZERS。下記

    @property
    def to_measure(self) -> tuple[str, ...]:
        """実際に計測する集合。宣言があればそれ、無ければ検出由来の集合。

        照合はすべて集合演算で行い、外に出すときだけソート済み tuple にする。
        """
        source = self.declared if self.declared is not None else self.detected_analyzers
        return tuple(sorted(source))

    @property
    def global_freeze_scope(self) -> tuple[str, ...]:
        """新しい契約になる集合。宣言が無いときは既存の契約を必ず含む。"""
        if self.declared is not None:
            return tuple(sorted(self.declared))
        return tuple(sorted(self.detected_analyzers | self.frozen))

    def mismatch(self) -> str | None:
        """契約とスコープが食い違うときの説明。一致していれば None。"""


def scope_decision(config, languages: RepoLanguages, state) -> ScopeDecision: ...
```

**3つのフィールドは `frozenset` であって `tuple` ではない。** 照合規則（下記）は完全一致と
部分集合であり、どちらも集合の性質である。tuple のまま比較すると順序が意味を持ってしまう:
検出由来の射影は registry 順で `("ruff", "mypy")` になり、`state.frozen_analyzers` は
ソート済みで `("mypy", "ruff")` になるので、**同じ集合が不一致と判定される**。
`tuple` に戻すのは `to_measure` の1箇所だけで、そこでは必ずソートする。

#### 言語から analyzer への射影

`scope_decision()` の内部で、`RepoLanguages` を `Analyzer.language`（D-2）と突き合わせて
analyzer 名の集合に変換する。

```
RepoLanguages.languages
    ↓ [a.name for a in ANALYZERS if a.language in languages]
detected_analyzers
```

```
python 検出  →  ruff, mypy
rust   検出  →  clippy
```

`ToolDetector.languages`（D-13）の正本は次のとおり。

| detector | `languages` |
| --- | --- |
| `ruff` / `ruff-format` / `mypy` / `pytest` / `vulture` | `{"python"}` |
| `secret-scan` | `frozenset()`（言語非依存。全リポジトリで動く） |
| `clippy` | `{"rust"}` |

**射影を明記するのは、`frozen ⊆ detected_analyzers` の右辺の型を確定させるためである。**
フィールド名を `detected` のままにすると、D-4 だけを読んだ実装者が `detected = languages.languages`
と解釈する余地が残る。名前と型の両方で「これは analyzer 名である」と言い切る。
射影を1箇所に閉じ込めれば、analyzer を足したときに直す場所も1つのままになる。

`store/ceiling_artifacts.reconcile_scope` の役割はこの `mismatch()` に移す。現在の実装は
config だけを見ており（`store/ceiling_artifacts.py:30`）、`ScopeDecision` に吸収される。

> **なぜ1つの値か。** スコープを裸の `tuple[str, ...]` にすると、照合に必要な `frozen` と、
> 「その集合がどこから来たか」が呼び出し側に散る。散った結果が P1-5 の後退である（下記）。
> 3つを1つの frozen dataclass に入れれば、照合規則は値のメソッドになり、**呼び出し側が
> `frozen` を渡し忘れることも、出所を取り違えることもできなくなる**。
> `Decision` の接尾辞は `FreezeDecision` / `CheckDecision` と同じく `decide/` の関数の
> 戻り値であることを表す。
>
> 副次的に `scope=None` という曖昧な状態が消える。`None` は `declared` にしか現れず、
> 意味はただ1つ「config.json が無い」である。config が空リストなのは既にエラーであり
> （`store/config.py:57`）、*Absence and zero are different* が保たれる。

#### 照合を行う条件

**照合は有効な frozen contract が存在するときだけ行う。** fresh な（まだ freeze していない）
リポジトリでは `frozen` が空なので、照合すればどんな `declared` とも食い違う。

これは既存の不変条件でもある。`reconcile_scope` を呼ぶ唯一の場所である `check` は、その手前で
fresh を早期 return しており（`commands/check.py:179`）、照合は frozen のときしか走らない。

したがって **config を置いた新規リポジトリの初回 `ebpy freeze` は照合せず、`declared` を
そのまま新しい契約にする**。ここを照合すると導入経路が塞がる — D-1 が塞がらないようにした
のと同じ場所である。

#### 照合規則

有効な contract があるとき、出所によって規則が変わる。
**これを1つの値に閉じ込めるのが `ScopeDecision` の主目的である。**

| `declared` | 規則 | 不一致のとき |
| --- | --- | --- |
| あり（config 由来） | `declared == frozen`（**完全一致**） | 両方向を名指しする |
| 無し（検出由来） | `frozen ∩ registered ⊆ detected_analyzers`（**片方向のみ**） | `(frozen ∩ registered) - detected_analyzers` を名指しする |

**config 由来で完全一致を要求するのは、現行の挙動を保つためである。** `reconcile_scope` は
今日すでに完全一致を要求しており、`declared - frozen`（宣言されたが未 freeze）も
`frozen - declared` も不一致として扱う。片方向に緩めると、config が `{ruff, mypy, clippy}` で
frozen が `{ruff, mypy}` のとき照合を通り、**`check` が clippy を gate しないまま成功する**。
config が「このリポジトリが ratchet する集合」だという定義そのものからの後退になる。

**`registered_analyzers` で先に絞るのは、`no-runner` を守るためである。** `detected_analyzers` は
この build の `ANALYZERS` から射影されるので、**新しい ebpy が凍結した未知の analyzer 名は
決してそこに入らない**。絞らずに `frozen - detected_analyzers` を取ると、その名前が
scope 不一致として報告される。

これは既存の契約を壊す。`classify(None)` の `"no-runner"` は
*a ledger contract naming an analyzer this ebpy build has no runner for at all*
（`measurement/observation.py:92`）と定義され、**2つの回帰テストが固定している** —
`tests/test_check.py:373`（`pylint` を含む契約は fail-closed）と
`tests/test_freeze.py:350`（global freeze が測れない roster 要素を落とさない）。
`scope-mismatch` に化けると「この build には runner が無い」という**唯一直しようのある案内**が
消える。

**この保護が要るのは `declared is None` の経路である。** config 由来では `read_config` が
`ANALYZER_NAMES` に対して検証するので（`store/config.py:62`）、未知の名前は config には
書けない。したがって未知の frozen analyzer が現れるのは検出由来の経路だけであり、
`registered_analyzers` の絞りもそこに効く。

D-14 の `scope_mismatches` も同じ式を使う。

**`measure_repository` は scope の未知名を `KeyError` にしない。** 登録済みの analyzer だけを
走らせ、未知名は measurement のキーに現れない。**その欠落が `no-runner` の表現そのもの**で
あって、エラーで落とすべき状態ではない。

**検出由来で片方向にするのは、検出が既定でしかないためである。** 検出されたが凍結されていない
analyzer は「まだ ratchet していない」というだけで、エラーではない。これは `diagnose` の gap に
なる（§2.4）。逆向き（凍結されているのに検出されない）は、`Cargo.toml` を消したのに clippy が
契約に残っているような状態なので、計測前に断る。

#### 前提条件の順序

複数の前提が同時に崩れているとき、どれを先に見せるかを決めておく。**新しい順序を作らず、
コマンドごとの現行の順序を保つ。**

```
1. config が読めない / 版が違う /
   analyzers が list[str] でない     → CommandError（read_config が送出する）
2. ceiling artifacts が invalid      → 下表
3. fresh か frozen かで分岐（fresh は照合しない）
4. scope 照合（mismatch）            → 下表
5. to_measure が空                   → 下表
6. 計測
```

**1 と 2 の順序はコマンドで違う。現行のまま変えない。**

| | 1 と 2 の順序 |
| --- | --- |
| `freeze` | **config が先**（`commands/freeze.py:307` が冒頭で `read_config` を呼ぶ） |
| `check` | **artifacts が先**（`read_config` は `reconcile_scope` の引数なので後）（`commands/check.py:175-186`） |
| `prune` / `report` | `check` に揃える。どちらも `read_config` を新たに呼ぶ側である |

**手順2 の invalid には例外がある。global `freeze --force` だけは進む。**

| 経路 | invalid artifacts のとき |
| --- | --- |
| `freeze`（global、`--force`） | **進む。** `previous = empty_state()` から作り直す（`commands/freeze.py:93`） |
| `freeze --analyzer`（`--force` 付きでも） | 断る（`commands/freeze.py:172-179`） |
| `check` / `prune` / `report` | 断る |

これは仕様が新しく決めることではなく、**既存の復旧経路そのもの**である。invalid のときに出る
案内文が *run `ebpy freeze --force` to discard the old contract and pin today's measurements*
と `--force` を指しており（`store/ceiling_artifacts.py:78`）、その出口を塞ぐと**復旧手段が
無くなる**。

**手順4・5 に対する `report` の扱い。**

| 手順 | `report` |
| --- | --- |
| 4（scope 照合の不一致） | **断らない。** D-14 の `scope-mismatch` で表示する |
| 5（空 scope、frozen contract 有り） | **断らない。** 同上 |
| 5（空 scope、fresh） | **断る** |

fresh で空 scope の `report` が断るのは、**表示する契約が存在しないから**である。
`scope-mismatch` は「契約と現実がずれている」という表示であり、契約が無ければ表示するものが
無い。手順1・2 も同じ理由で断る — 壊れた台帳や壊れた config からは、`report` が見せるべき
現状そのものが読めない。**`report` が開いていなければならないのは「契約と現実がずれていると
き」であって、「入力が壊れているとき」ではない。**

`read_config` が既に `OSError` / `UnicodeError` / `json.JSONDecodeError` を
`CommandError` に変換している（`store/config.py:47`）。**D-15 の `InvalidToml` が
`UnicodeError` を捕まえるのは、この既存の作法に揃えるためでもある。**

#### コマンド別の扱い

| コマンド | 照合 | 不一致のとき |
| --- | --- | --- |
| `check` | する | 計測前に fail-closed（既存の挙動が広がるだけ） |
| `prune` | する | 同上。天井を触るので `check` と同じ扱い |
| `report` | する | **断らない。** `AnalyzerSummary` で名指しする |
| `freeze`（global、fresh） | **しない** | `declared` がそのまま新契約になる |
| `freeze`（global、frozen、非 `--force`） | **到達しない** | `_already_frozen` が先に断る（下記） |
| `freeze --force`（global） | **しない** | 意図的な縮小。唯一の抜け道 |
| `freeze --analyzer X` | `X ∈ to_measure` **だけ**を見る | 断る |

`report` が断らないのは、`report_from_measurement` の docstring が
*tool failure changes its detail, never its exit status*（`decide/analysis_report.py:206`）と
宣言しているためである。加えて、契約と現実のずれを調べるために叩いたコマンド自身が断ると、
必要なときに使えなくなる。

**`freeze --analyzer X` の規則は1つだけである。** 前版はこれに「X が検出されない言語なら断る」を
重ねていたが、2つは両立しない。config が clippy を宣言していて `Cargo.toml` が無いとき、
`to_measure` は clippy を含むので前者は通し、後者は断る。config が検出を上書きできるという
D-4 の設計（`to_measure` の定義そのもの）を採る以上、**残すのは `X ∈ to_measure` の側**である。
config が無ければ `to_measure` は検出由来なので、検出されない analyzer は同じ規則で自然に落ちる。

**`freeze`（global、frozen、非 `--force`）の行が「到達しない」なのは、現行コードの順序による。**
`commands/freeze.py:326-327` は計測より前に `artifacts.kind == "frozen"` を無条件で断る。したがって
このマスに入る実行は存在せず、ここに照合を足しても死んだコードになる。**既存の
`already frozen` の優先を変えない** — こちらのほうが打った人にとって行動可能な指示であり、
scope 不一致は `check` / `prune` / `report` が先に見せる。

#### global freeze の scope は `to_measure` ではない

**`freeze`（global）が新しい契約にする集合は `global_freeze_scope` であって `to_measure` ではない。**
`--force` は照合を飛ばすので、`to_measure` をそのまま契約にすると **config が無いだけで契約が
黙って縮む**。

```
frozen = {clippy}   config 無し   Cargo.toml を削除 → detected = {}
  to_measure          = {}          ← clippy が契約から消える
  global_freeze_scope = {clippy}    ← 既存の契約を保つ
```

これは現行コードの不変条件でもある。`commands/freeze.py:337` は config が無いとき
`sorted(set(ANALYZER_NAMES) | set(previous.frozen_analyzers))` を渡しており、**既存の
frozen roster を必ず含める**。D-1 は `ANALYZER_NAMES` を検出由来の集合に置き換えるだけであり、
和を取る側は変えない。

`--force` の carve-out は必須である。契約から analyzer を外す唯一の手段が「config を狭めて
`--force`」であることを、コード自身が明記している。**縮小できるのは `declared is not None` の
ときだけ**、というのが上の式の意味である。

**計測する集合と契約にする集合は同じでなければならない。**

```
global freeze:
    previous = _previous_state(artifacts, force and analyzer is None)
    decision = scope_decision(config, detect_languages(cwd), previous)
    measurement = measure_repository(cwd, decision.global_freeze_scope)
    build_global_freeze(..., scope=list(decision.global_freeze_scope))
```

**`scope_decision` に渡す state は `_previous_state()` の戻り値であって、
`artifacts.ledger.state` ではない。** invalid artifacts からの global `--force` は
`empty_state()` を返すので（`commands/freeze.py:93`）、**捨てるはずの古い roster が
`global_freeze_scope` に入らない**。`artifacts.ledger.state` を渡すと、壊れた台帳に載っていた
analyzer が新しい契約へ蘇り、`no-runner` などで**復旧経路をもう一度塞ぐ**。

`to_measure` で測って `global_freeze_scope` で凍らせると、**測らなかった analyzer が
`no-runner` に化ける**。`build_global_freeze`（`commands/freeze.py:210`）は
`measurement.get(name) is None` を `classify` に渡し、`classify(None)` は `"no-runner"` を返す
（`measurement/observation.py:92`）。runner は在るのに「この build には runner が無い」と
断ることになり、**D-4 が `report` から追い出したのと同じ嘘が `freeze` に生まれる**。
上の形にすれば clippy は実際に走り、`Cargo.toml` が無ければ D-6 の規則どおり `Unavailable` に
なる。断る理由が正しくなる。

```
# commands/freeze.py:204-208（build_global_freeze の docstring）
`frozen_analyzers` is set to exactly `scope`, so dropping an analyzer from the
contract requires the caller to narrow the scope — which means declaring fewer
analyzers in `.ebpy/config.json` and running with `--force`.
```

`freeze --analyzer X` は **X だけを測る**。`build_scoped_freeze` は X 以外を見ないので、
他を測る理由がない。

#### `to_measure` が空のとき

`declared` が無く、どの言語も検出されなかった場合、`to_measure` は空になる。空の計測を
`Measured` として扱うと天井がゼロで固定され、`prune` が既存の天井を削るため、計測は行わない。

**contract の有無で扱いが分かれる。**

| 状態 | `freeze` / `check` / `prune` | `report` |
| --- | --- | --- |
| fresh（contract 無し）+ 空 scope | 断る（「該当する analyzer が無い」） | 断る |
| frozen（contract 有り）+ 空 scope | 断る（`frozen ⊄ ∅` の不一致） | **断らない。** D-14 の表示 |

frozen が `{clippy}` で `Cargo.toml` が消えた場合はこの表の2行目にあたる。`report` は断らず、
契約に載っている analyzer を D-14 の `scope-mismatch` として表示し、天井の数字は出す。
**「断らない」が「空 scope でも断る」に優先する** — `report` は現状を見るための窓であり、
現状が壊れているときこそ開いていなければならない。

`config.json` は `ANALYZER_NAMES` で検証しているため、clippy を registry に登録した時点で
`"clippy"` は自動的に合法な config 値になる（`store/config.py:62`）。ここは無変更でよい。

> **照合を入れないと何が起きるか（根拠: 実装読解）。** `classify()` は observation が `None` の
> とき `"no-runner"` を返し、呼び出し側はその値に**とても具体的な意味**を与えている。
>
> ```python
> # measurement/observation.py:96
> # "no-runner" stands for a ledger contract naming an analyzer
> # this ebpy build has no runner for at all.
>
> # commands/check.py:75
> detail = observation.detail if observation is not None else f"{analyzer} has no runner in this ebpy build"
>
> # commands/freeze.py:120-127
> if status == "no-runner":
>     return f"{analyzer} is in the contract but this ebpy build has no runner for it."
> ```
>
> スコープ化すると「analyzer が `measurement.analyzers` から欠ける」状態が初めて生まれる。
> 契約に mypy があるのにスコープが `{ruff}` だと、上の文面が出る — **runner はあり、走らせな
> かっただけなのに**である。*Absence and zero are different* の違反そのもの。照合を計測前に
> 置けば、この状態に到達しない。

### D-5. 可用性の判定と計測コマンド

**可用性プローブ:** **workspace ごとに1回**、その `workspace_root` を cwd として
`cargo clippy --version` を実行する。失敗したら `Unavailable`。
**`OSError` は probe の中で `ClippyNotFoundError` に変換して送出する。**

> **workspace ごとに行う根拠: 契約。** rustup は cwd から最も近い toolchain 設定を選ぶ
> （rustup overrides）。nested workspace が `rust-toolchain.toml` で別のツールチェインを
> 固定していると、リポジトリルートで1回だけ probe しても、実際に計測するツールチェインの
> 可用性を測ったことにならない。

> **根拠: 実装読解 + 契約 + 観測。** `util.run` は shell を通さず `subprocess.run` を直接呼ぶので、
> 実行ファイルが無ければ `FileNotFoundError`（`OSError`）を**送出する**（`util.py:22-33`）。
> mypy の analyzer は `except (MypyFailedError, OSError)` を `Failed("execution-failed")` に
> 落としているが（`tools/mypy/analyzer.py:38`）、これは `find_mypy`（`tools/mypy/_runner.py:70-77`）
> が先に実行ファイルの存在を確認していて、`OSError` に到達するのが「見つけたのに実行できな
> かった」という本物の異常だけだからである。clippy はこの前段を持たないので、mypy の except 節を
> 書き写すと **cargo が入っていないマシンで `Failed` になる**。
> `docs/measurement-seam.md` の Failure boundary は *executable not found → `Unavailable`* と
> 定めており、cargo 不在は install の問題であって故障ではない。
>
> probe の中で変換すれば、probe が `find_ruff` / `find_mypy` と同じ役割を果たし、
> `ClippyAnalyzer.measure` の except 節が mypy と完全に同じ形になる。
>
> clippy component が入っていないツールチェインでは exit 1 / stdout 0 バイト / stderr 1行になる
> （Rust 1.70 で再現）。
>
> ```
> error: the 'cargo-clippy' binary, normally provided by the 'clippy' component,
> is not applicable to the '1.70-aarch64-apple-darwin' toolchain
> ```
>
> このメッセージは **rustup 由来**であり、非 rustup 環境では別の失敗になる。stderr の文言を
> 解釈してはいけない。プローブの成否だけを見る。
>
> `shutil.which("cargo-clippy")` は使わない。rustup の shim は PATH と独立にツールチェインを
> 解決するため、PATH 探索は偽陰性を生む。

**計測コマンド:** workspace ごとに1回、その `workspace_root` を cwd として次を実行する。
フラグは runner 内で固定する。

```
cargo clippy --workspace --message-format=json \
    --target-dir <target_directory>/ebpy-clippy -- --cap-lints warn
```

`<target_directory>` は D-3 の `cargo metadata` が報告した値。

> **専用 target ディレクトリを使う根拠: 観測。** `-- --cap-lints warn` は rustc の追加引数として
> fingerprint に入るため、ebpy の計測と開発者自身の `cargo clippy` が**互いのキャッシュを
> 無効化する**。実測:
>
> ```
> plain（cold）→ fresh=False    plain 再実行     → fresh=True
> cap-lints    → fresh=False    cap-lints 再実行 → fresh=True
> plain に戻す → fresh=False    ← 相互に打ち消し合う
> ```
>
> 分離しないと、ローカルで `ebpy check` と手動の `cargo clippy` を交互に叩くたびにフル再
> コンパイルになる。cargo が報告した `target_directory` の**配下**に置くのは、`cargo clean` と
> 既存の `.gitignore` がそのまま効くようにするためである。

**`--workspace` が必須である理由。**

> **根拠: 契約 + 観測。** Cargo の package selection は、非 virtual workspace
> （root の `Cargo.toml` が `[package]` と `[workspace]` の両方を持つ）で package 指定が無い場合、
> **root package または `default-members` だけ**を対象にする。member は黙って落ちる。
>
> ```
> 非 virtual workspace（root + crates/a + crates/b、各2違反）
>   cargo clippy               →  2 件（src/lib.rs のみ）      ← member が消える
>   cargo clippy --workspace   →  6 件（3クレートすべて）
> ```
>
> 落ちた member は「ゼロ」として天井に載り、`prune` が天井を不当に下げる。ratchet が黙って
> 見落とす典型例であり、*Absence and zero are different* に抵触する。

**`-- --cap-lints warn` が必須である理由。**

> **根拠: 契約 + 観測。** `[lints.clippy] all = "deny"`、`#![deny(...)]`、`RUSTFLAGS=-Dwarnings`
> のいずれでも lint は error に昇格し、`build-finished.success` が `false` になる。D-6 の規則に
> よりこれは `Failed` なので、**deny を使っているリポジトリは既存違反を freeze できない**。
> `-Dwarnings` は Clippy の公式ドキュメントが CI 構成として案内している一般的な形である。
>
> ```
> [lints.clippy] all = "deny"
>   cap-lints なし  →  error ×2、build-finished success=False   ← freeze 不能
>   -- --cap-lints warn  →  warning ×2、success=True             ← 計測できる
>
> RUSTFLAGS=-Dwarnings
>   cap-lints なし  →  error ×2、success=False
>   -- --cap-lints warn  →  warning ×2、success=True
> ```
>
> **本物のコンパイルエラーは隠れない。** `--cap-lints` は lint の**レベルの上限**を定めるだけで、
> ハードエラーには効かない。実測でも E0308 は `error` のまま残り `success=false` になった。
> D-6 の完全性判定はそのまま機能する。
>
> 意味としても正しい。リポジトリが lint を deny にしているかどうかはそのリポジトリのゲートの
> 設定であって、ebpy が測るべき「今日の違反の数」ではない。ebpy は違反を数え、deny するか
> どうかは天井が決める。

**`--all-targets` は使わない。**

> **根拠: 観測（Rust 1.79 / 1.85 / 1.93 / 1.96 の4版で一致）。** `--all-targets` は lib を lib と
> test harness の2回コンパイルするため、全診断がちょうど2倍になる。両コピーの `target` は
> 完全に同一（`kind` はどちらも `["lib"]`）で識別できない。
>
> ```
> 3 diagnostics  →  --all-targets  →  6 diagnostics + cfg(test) 内の rustc lint 1件
> ```
>
> 将来 `--all-targets` を採用する場合は `(file, line, column, code, message)` による重複除去が
> 必須になる。ただし「cfg(test) のコードを天井に載せるか」は重複問題とは独立の方針判断であり、
> 本仕様では混ぜない（§2.6）。

### D-6. 完全性の判定は `build-finished` に一本化する

**「ちょうど1つ」は1回の cargo 実行の stdout に対する不変条件である。** パーサは
1 invocation = 1 call とし、複数 workspace の stdout を連結してから渡してはいけない。

```python
def parse_clippy_output(
    stdout: str, stderr: str, returncode: int, *, workspace: RustWorkspace, repo_root: Path
) -> AnalysisMeasurement: ...
```

**`stderr` も引数に取る。** 失敗の detail は `message.rendered` を優先するが、それが1つも
無いときは stderr の末尾にフォールバックすると決めた（下記）。stdout だけを受け取る
シグネチャではその規則が実装できない。

**parser は observation を返さない。** 戻り値は `AnalysisMeasurement` だけであり、失敗は例外で
表す。

| 下の判定 | parser が送出するもの |
| --- | --- |
| `invalid-output` | `ClippyInvalidOutputError` |
| `execution-failed` | `ClippyFailedError` |

observation に変換するのは `ClippyAnalyzer.measure()` である。**これは runner が例外を投げ
analyzer が observation を組み立てる、という既存の分担そのものである**（`tools/ruff/analyzer.py`）。
以下の表が `Failed(...)` と書いているのは、**その例外が最終的にどの observation になるか**で
あって、parser の戻り値ではない。

このシグネチャに固定しておくと、「全 workspace 分を concat して parse したら `build-finished`
が複数あった」という誤実装が型の段階で起きなくなる。

workspace ごとの実行それぞれについて、**解釈できる `build-finished` がちょうど1つあり、
その `success` が `true` であること**を要求する。

**判定は次の順で行う。順序そのものが仕様である。**

```
1. `{` で始まる行が JSON object として読めない
   / 下表のフィールドの型が不正                →  Failed("invalid-output")
2. 解釈対象の JSON object が1つも無い          →  Failed("execution-failed")
                                                  （壊れた Cargo.toml、component 不在など）
3. build-finished が0個 または 2個以上         →  Failed("invalid-output")
4. build-finished.success == false
   **または returncode != 0**                  →  Failed("execution-failed")
                                                  detail は下記
5. build-finished.success == true              →  Measured
```

**順序を書き下すのは、複数の規則が同時に当てはまるからである。** stdout が `plain text\n`
だけのとき、「JSON object が0件」と「build-finished が無い」の両方が真になる。前版は前者を
§4 に、後者を D-6 本文に書いていて、どちらが勝つか決まっていなかった。

**2 が 3 より先なのは、区別に意味があるからである。** cargo が何も言わずに死んだ（出力ゼロ）のと、
喋ったが完了マーカーを出さなかった（部分出力）のは違う。前者は「ツールが走って失敗した」、
後者は「ツールの出力を ebpy が読み切れなかった」である。

**1 が最優先なのは、読めない出力からは何も結論できないからである。** 型が壊れた行が1つでも
あれば、`success=true` を見つけていても計測として採用しない。

`success == false` **または `returncode != 0`** の detail は下記の規則で選び、
`observation.py` の `_describe` が 20行 / 4000字に丸める。

> **成功マーカーを必須にする根拠: 契約。** Cargo は `build-finished` を**ビルドの最後**に出すと
> 定めている。したがって cargo が途中で終了した場合、warning の JSON は出ているのに
> `build-finished` が無い、という**部分的な出力**があり得る。「`success == false` でなければ成功」
> と読むと、この部分出力が完全な計測として天井に載る。
>
> 欠落を `invalid-output` に分類するのは、`execution-failed`（ツールが走って失敗した）ではなく
> 「ツールの出力を ebpy が読み切れなかった」ためである。cargo が kill されたのか出力が壊れたのかを
> ebpy から区別する手段は無く、区別できないものを区別したふりをしないほうがよい。

#### 行の切り分け

stdout は JSON だけとは限らない。

```
先頭の1文字が `{` でない行     →  無視する（空白の除去はしない）
`{` で始まるが JSON object と
して解釈できない               →  Failed("invalid-output")
JSON object だが ebpy が読む
フィールドの型が不正           →  Failed("invalid-output")   ← 対象は下表に限る
未知の reason / level /
知らない追加フィールド         →  前方互換に無視する（D-7）
```

**空白を許さない。** 判定は `line.startswith("{")` であって `line.lstrip().startswith("{")` では
ない。寛容にする理由が無く、literal に固定したほうが「任意の出力を JSON と誤認しない」という
境界がはっきりする。

#### 型を検査するフィールドの一覧

「型が不正なら `invalid-output`」の対象は**次の表に挙げたものだけ**である。表に無いフィールドは
読まないので、型がどうであれ計測に影響しない。

| 位置 | 要求する型 | 欠落・型違反のとき |
| --- | --- | --- |
| 各 JSON object の `reason` | `str`（必須） | `invalid-output` |
| `build-finished` の `success` | **厳密に `bool`**（`0` / `1` / `"true"` を受けない） | `invalid-output` |
| `build-script-executed` の `out_dir` | `str` かつ絶対パス | `invalid-output` |
| `compiler-message` の `message` | `dict` | `invalid-output` |
| `message.level` | `str` | `invalid-output` |
| `message.code` | `None` または `dict` | `invalid-output` |
| `message.message` | `str`（**`unattributed` にする message でのみ**。D-9） | `invalid-output` |
| `message.code.code` | 非空 `str` かつ `\r` / `\n` を含まない（セル化する message でのみ） | `invalid-output` |
| `message.spans` | `list` | `invalid-output` |
| `spans[]` の各要素 | `dict` | `invalid-output` |
| `spans[].is_primary` | `bool`（欠落は `False` 扱い） | `invalid-output` |
| primary span の `file_name` | 非空 `str` | `invalid-output` |
| primary span の `line_start` / `column_start` | 正の `int`（`bool` を除く） | `invalid-output` |
| `message.children` | **検査しない**（D-6 の分類でのみ寛容に読む。下記） | — |
| error の `message.spans` | **検査しない**（同上。「空でないか」だけを見る） | — |

**改行を含む code を弾くのは、`qualify_rule` の入力契約に合わせるためである。**
`cell_key.py:24` は `"\n"` または `"\r"` を含む local code を `ValueError` で拒否する。
型検査を「非空 `str`」だけにすると、`code = "\n"` が検査を通ったあとで**生の `ValueError` が
parser の外へ漏れる** — parser は `ClippyInvalidOutputError` か `ClippyFailedError` しか
送出しないと決めた契約（上記）が破れる。**保険として `qualify_rule` の `ValueError` も
`ClippyInvalidOutputError` に包む。**

**rule ID は `message.code.code` である。** rustc の `code` は文字列ではなく nullable な object
であり、`code` キーの下に綴りが入る。D-7 の「`code` が非 null」はこの object の有無を指す。

**`bool` を `int` から除くのは Python の都合である。** `isinstance(True, int)` は真なので、
`line_start` の検査を `isinstance(x, int)` だけで書くと `true` が行番号1として通る。

**検査は段階的で、読まないものは検査しない。** 上の表は「その段に到達したときに要求される型」で
あって、全 message に全項目が掛かるわけではない。

```
1. reason を検査
2. compiler-message なら message と level を検査
3. message.rendered が str なら、失敗用 detail の候補として level ごとに保持する
   （str でない / 欠けている → 無視。ここでは捨てない）
4. level == "error" なら、D-6 の分類に要る事実だけを**寛容に**拾ってから
   セル化候補から外す（下記）。level がそれ以外で warning でもないなら、
   以後のフィールドを読まずにセル化候補から外す
5. warning なら code を検査。None ならセル化候補から外す
6. code が object なら spans を検査
7. 各 span について dict と is_primary だけを検査
8. primary span が1つ以上あることを確かめる。無ければセル化候補から外す
9. primary span についてのみ file_name / line_start / column_start を検査
10. ここまで来た message についてのみ message.code.code を非空 str として検査
```

**段3 を段4 より前に置くのは、失敗の detail が `level == "error"` の `rendered` を必要とする
からである。** 前版は非 warning を段3で捨てていたので、`success=false` のときに引用すべき
コンパイルエラーが手元に残らなかった。**「セル化しない」と「読まない」は別である** —
`rendered` は全 message から拾い、**D-6 の分類に要る事実は error から拾い**、`code` と
`spans` を**セル化のために**読むのは warning だけである。

##### 段4 が error から拾うもの

D-6 の失敗分類は error の `spans` と子ノートを入力にする。段4 でそれを拾わなければ、
**分類が必要とする値を parser がそもそも持っていない**。前版はここが噛み合っておらず、
D-6 の規則は実装できなかった。

```
error について、次の2つだけを記録する:
  has_span        = spans が list であり、空でない
  configured_out  = children が list で、そのいずれかの message（str）が
                    "found an item that was configured out" を含む
```

**この2つは型検査の対象にしない。** 欠けていても、型が違っても `invalid-output` にはせず、
`False` として扱う。理由は2つある。

1. **これらを読むのは、失敗が既に確定した後だけである。** 分類は `execution-failed` の
   内訳を決めるだけで、成功した計測には一切関与しない。ここで厳しくすると、壊れた error
   出力が `execution-failed`（ツールが走って失敗した）を `invalid-output`（読み切れなかった）
   に**格下げ**する。
2. **倒れる向きが安全側になる。** 除外という結論には `configured_out` が**全 error で真**で
   あることが要る。読めなければ偽になり、本物の失敗として扱われる。**疑わしいものを
   天井から外さない**、という向きに自動的に倒れる。

これは「読まないものは検査しない」の系である — ここでは**読むが、検査はしない**。

**`message.code.code` の検査が段10 なのは、primary span を確かめた後だからである。** primary
span を持たない message は `code` object が壊れていても捨てるだけで、`invalid-output` にしない。
セル化しないものを検査すると、**読まない値のせいで計測が失敗する**。

**未知の `level` を持つ message は段4 でセル化候補から外れるので、その `code` や `spans` は
検査しない。**
rustc が enum 的フィールドに値を足しうると書いている以上、未知の level の中身に型を要求すると、
**将来の rustc が計測を `invalid-output` にできてしまう**。

**非 primary span は、`dict` であることと `is_primary` の型以外を検査しない**（段6まで）。
ebpy は読まないので、壊れていても黙って飛ばす。
セル化に使うのは primary span だけであり、読まないものを検査するのは
「ツールが走って失敗した」でも「出力を読み切れなかった」でもない第三の状態を作ることになる。

**`build-finished.success == false` の detail の選び方を確定させる。**

```
1. level == "error" の message の rendered を、stdout に現れた順に連結する
2. 1件も無ければ、level を問わず rendered を stdout の順に連結する
3. それも無ければ、stderr の末尾20行
```

`rendered` は rustc が人間向けに組み立てた文字列であり、`observation.py` の `_describe` が
丸める先もそれである。**error を先に置くのは `_describe` が先頭20行しか残さないからである** —
順不同で連結すると、warning が本物のコンパイルエラーを枠外へ押し出す。`rendered` が無いか
`str` でない診断は飛ばす。

**構造化フィールドから detail を組み立て直さない** — rustc の整形を再実装することになり、
版差で表示が揺れる。

**「読めない」と「知らない」は別である。** `{"reason": "future-cargo-message", ...}` は JSON
object として解釈でき、reason が未知なだけなので**無視する**（`invalid-output` にしない）。
`invalid-output` にするのは、ebpy が実際に読むフィールドが読めないときだけ。これは D-7 が
根拠にしている rustc の前方互換の契約 — *New fields may be added. Enumerated fields … may add
new values.* — と同じ立場である。

> **根拠: 契約。** Cargo は明示している — *"`--message-format=json` only controls Cargo and
> Rustc's output. This cannot control the output of other tools, e.g. `cargo run
> --message-format=json`, or arbitrary output from procedural macros. A possible workaround in
> these situations is to only interpret a line as JSON if it starts with `{`."*
> 手続きマクロが stdout に書けば、その行が JSON ストリームに混ざる。
>
> 同じ節が `build-finished` の役割も定めている — *"This message lets a tool know that Cargo will
> not produce additional JSON messages"*。上の完全性判定はこの用法どおりである。

> **`--target-dir` の隔離は完全ではない。** Cargo は中間生成物の置き場を `build.build-dir` で
> target directory と別に設定できる。**明示的な `build-dir` があるリポジトリでは
> `--target-dir` を分けても中間キャッシュは共有される**ので、D-10 が避けようとしている
> 再コンパイルのコストは残る。これは**正しさの問題ではなく性能の問題**である —
> 計測結果は変わらない。§6 の見積りはこの構成では悲観側に外れる。

**`returncode` も見る。** 前版は exit code に依存しないと決めていたが、それは**強すぎた**。
契約が保証しているのは `build-finished.success` が**ビルド**の成功を表すことまでであり、
`build-finished` の後にもコマンド固有の処理と出力がありうるとされている。一方、通常の cargo
コマンドが成功を exit 0 で表すことは別に契約化されている。**「`success=true` なら非ゼロ終了を
無視してよい」は、どちらの契約からも導けない。**

2つを **and** で結ぶのが安全側である。片方でも失敗を言えば `execution-failed` にする。

**実測では `success=true` かつ `returncode != 0` は現れなかった。** 1.79 / 1.85 / 1.96 で、
警告あり・警告なし・`[lints.clippy] all = "deny"` に `--cap-lints warn`・build script の生成
コードに警告あり、の4条件すべてが exit 0 である。**それでも `returncode` を見る** —
契約が「`build-finished` の後にもコマンド固有の処理がありうる」と言っている以上、
観測が一致していることは「そうでない場合が無い」の証明にならない。判定を1つ足す費用は
ほぼゼロで、見落としたときの費用は壊れた天井である。

**「警告が0件だったこと」には依然として依存しない。**

> **根拠: 契約 + 観測。** `{"reason":"build-finished","success":true}` は Cargo Book の
> JSON messages にスキーマとして明記されている（契約）。一方「コンパイルエラー時に clippy 警告が
> 消える」は観測にすぎない（4版で一致）。`success` を読めば後者の観測に依存せずに
> 「この計測は使えない」と言える。確信度の低い観測を設計から追い出すのが狙いである。
>
> **プローブは「clippy が動いた」ことまで確かめる。** `cargo clippy` は cargo の組み込み
> サブコマンドではなく **external subcommand** であり、**cargo の alias はそれを覆える**。
> 実測（cargo 1.96.0）:
>
> ```
> .cargo/config.toml に  [alias] clippy = ["--version"]
>   $ cargo clippy --version
>   warning: user-defined alias `clippy` is shadowing an external subcommand
>            found at `/…/.cargo/bin/cargo-clippy`
>     = note: this was previously accepted but will become a hard error in the future
>   exit = 0                      ← プローブは「通った」ことになる
> ```
>
> `CARGO_ALIAS_CLIPPY` でも同じである。**cargo は警告するだけで実行を止めない**ので、
> 「終了コードが 0 なら clippy がある」という判定は成立しない。
>
> **stdout の先頭を見る。** 本物は自分の名前を名乗る。**これは実測契約であって、Clippy の
> 公式な出力安定性契約ではない** — `cargo clippy --version` の stdout が `clippy ` で始まる
> という保証は公式文書に無い。したがって §5.3 のサポート範囲の両端で integration test を
> 回し、崩れたら気付くようにする。
>
> ```
> 本物              : "clippy 0.1.96 (ac68faa20c 2026-05-25)"
> alias で覆った場合 : 別物の出力（上の例では空）
> ```
>
> 判定は `stdout.startswith("clippy ")` とする。**警告の文面には依存しない** — 言い回しは
> 変わりうるし、将来 hard error になると予告されている（そうなれば非ゼロ終了として先に
> 落ちる）。名乗りを見るほうが、どちらの時代でも壊れない。
>
> **これは alias が `clippy ` を騙るケースまでは排除しない。** 敵対的な設定を防ぐ機構では
> なく、**事故を検出する機構**である。
>
> **`cargo-clippy` を直接起動する道は採らない。** external subcommand protocol
> （`cargo-clippy clippy …`）で alias を迂回できるが、cargo の PATH 解決と `CARGO` 環境変数を
> ebpy が肩代わりすることになる。**プローブ1つで検出できるものに、起動経路の複製で答えない。**

> exit code だけでは切り分けられない。壊れた Cargo.toml は exit 101 / stdout 0 バイト、
> component 未導入は exit 1 / stdout 0 バイトで、どちらも stdout が空になる。D-5 のプローブで
> 先に `Unavailable` を切り分けてあることが前提になる。

**`incomplete` ではなく `Failed` に倒す理由。** ruff の syntax error は1ファイルだけが欠ける
部分的な穴なので `incomplete` が正しいが、clippy はクレートが通らなければ**何も計測されていない**。
「穴のある計測」ではなく「計測が成立しなかった」である。

**これは D-9 の `UnattributedFinding` と矛盾しない。** 2つは別の状況を指している。

| 状況 | observation |
| --- | --- |
| ビルドが通らなかった（`success=false` / `returncode != 0`） | `Failed`。**何も測れていない** |
| ビルドは通り、診断も読めたが、天井の座標系に置けないパスがあった | `incomplete`。**測れたが一部を置けない** |

前者で `incomplete` を使えば「穴のある計測」という嘘になり、後者で `Failed` を使えば
「何も測れなかった」という嘘になる。`UnattributedFinding` を使うのは後者だけであり、
そこでは**合成した file/line ではなく、clippy が実際に報告したパスと行**を詰める。

**複数 workspace のうち1つでも失敗したら、clippy 全体を `Failed` にする。** 部分成功を
`Measured` にすると、失敗した workspace のセルが「ゼロ」として天井に載り、`prune` が天井を
不当に下げる。

集約は**3段**で、段の間に優先順位は無い。**先に走った段が決着すれば、後の段は走らない。**

| 段 | 条件 | 全体の observation |
| --- | --- | --- |
| 1. 発見 | cargo が無い | `Unavailable` |
| 1. 発見 | ある候補で metadata が失敗 | **その候補を外す**（`unmeasured` に入れる。下記） |
| 1. 発見 | **どの候補でも** metadata が失敗 | その失敗の分類をそのまま返す |
| 1. 発見 | workspace が0件 | `Unavailable` |
| 2. probe | いずれかの workspace で `cargo clippy --version` が通らない | `Unavailable` |
| 3. 計測 | いずれかの workspace が**本物の失敗**（下記） | `Failed` |
| 3. 計測 | 残りが成功 | 合算して `Measured`（下記） |

#### vendored なソースは候補にしない

`cargo vendor` は依存のソースをリポジトリに書き出す。ルートがその dir を `exclude` すると
（cargo が nested package について出す警告への標準的な対処である）、**vendored な依存の
metadata は成功する**——つまり D-3 はそれを独立 workspace として拾い、**feature 指定なしの
素の `cargo clippy` を掛ける**。

実測（1.96。`stm32l4xx-hal` と同じ形——feature 未指定の単独ビルドを `compile_error!` で
拒否する依存を、ルートが `features = ["chip-a"]` 付きで使う）:

| 実行 | 結果 |
| --- | --- |
| exclude された vendored crate の metadata | **exit 0**（独立 workspace として拾われる） |
| ルートの `cargo clippy --workspace` | **exit 0**（リポジトリは健全） |
| vendored crate 単独の clippy | `compile_error!`（span あり、note 無し）→ **本物の失敗** |

D-6 はこれを本物の失敗として全体を `Failed` にする。**ルートが正常にビルドできるリポジトリが
計測不能になる**——失敗類型3である。

**そもそも依存を測ること自体が誤りである。** §5.2 に契約として書いたとおり、
**workspace member でない依存クレートはリントされない**（`RUSTC_WORKSPACE_WRAPPER` は
"for workspace members"）。vendored な依存は依存である。D-3 の独立 package 発見は
`[workspace] exclude` された**自リポジトリの** package を拾うための仕組みであって、
第三者のコードに天井を持つためのものではない。**直せないコードの違反を天井に載せない。**

**判定は `.cargo-checksum.json` が候補 `Cargo.toml` の隣にあるかどうか**とする。
`cargo vendor` を実際に走らせて確認した（1.96）:

```
vendor/cfg-if/Cargo.toml
vendor/cfg-if/.cargo-checksum.json     ← cargo が書く
vendor/cfg-if/.cargo_vcs_info.json
vendor/cfg-if/Cargo.toml.orig
```

**この marker が主張するのは出自であって、ビルド可否ではない。** 「cargo がレジストリの
package を展開した写しである」と言っているだけで、そこから「ビルドできない」を導いてはいない
——§5.1 の3件目（cargo-fuzz の marker をビルド可否の予測に使った誤り）を繰り返さない。

**vendored な候補は `unmeasured` に入れない。** これは「測れなかった範囲」ではなく
**最初から測る対象ではない範囲**である。入れると、`cargo vendor` で依存が1つ増えるたびに
集合が広がり、**D-17 が毎回それを後退と誤認する**。

**判定するのは、どの workspace にも属さなかった候補についてだけである。** 候補は D-3 の
順序で処理され、workspace の member は先に解決済みとして消える。marker を見るのは
**残った独立 package を「自前の workspace」として扱う直前**であり、member がこの判定に
掛かることはない。vendored な依存は member ではないので（member なら `exclude` する理由が
無い）、この順序が両者を分ける。

**限界は誇張せずに書く。** first-party の package にこのファイルが置かれていたら、その候補は
**黙って計測対象から外れる**——`unmeasured` にも入らないので、D-17 も気づかない。
`.cargo-checksum.json` は cargo がレジストリ package の写しにだけ書く自身の帳簿であり、
自前のソースに置く理由は無い、という前提に乗っている。**乗っていることを書いておく。**

#### 解決できない候補で全体を落とさない

前版は「いずれかの候補で metadata が失敗 → 全体を `Failed`」としていた。**vendor を
チェックインした普通のリポジトリが計測不能になる。**

`cargo vendor` は各 crate の `Cargo.toml` ごとソースをコピーし、Cargo の公式文書はそれを
ソース管理に入れる運用を想定している。ルートが workspace で `vendor/` を `exclude` して
いなければ、vendored な manifest は workspace の member でも独立 package でもない。

```
$ cargo metadata --no-deps --manifest-path vendor/somecrate/Cargo.toml
error: current package believes it's in a workspace when it's not:
current:   …/vendor/somecrate/Cargo.toml
workspace: …/Cargo.toml
exit 101      （1.79 / 1.85 / 1.96 で一致）
```

**このリポジトリは壊れていない。** 同じ作業ツリーで `cargo clippy --workspace` は exit 0 で
通る。落ちるのは、ebpy が vendored な manifest を候補として cargo に渡したときだけである。
**ebpy の発見が失敗を作り出していた。**

| 候補 | metadata | 意味 |
| --- | --- | --- |
| `vendor/*`（`exclude` 無し） | **exit 101** | workspace の member でも独立でもない |
| `vendor/*`（`exclude = ["vendor"]`） | exit 0 | 独立 package。D-3 が拾いたいもの |
| ルート | — | `clippy --workspace` exit 0。健全 |

**外すが、黙らない。** 解決できなかった候補は D-6 の構成の不一致と**同じ扱い**にする——
`unmeasured` に入れ、D-17 の包含判定に掛ける。以前測れていた範囲なら fail-closed し、
元から外なら続行する。

> **概念は増えていない。** 「ebpy が測れなかった範囲」の表現も方針も1つのままで、
> 原因が cfg の不一致か manifest の未解決かを問わない。

**ただし1つも計測できなければ `Failed` である。** 全候補が落ちたときに「外して続行」すると、
`Measured(cells={})` が天井に載り、`prune` が天井を丸ごと空にする——失敗類型1そのものである。
**「全部外した」と「測って0件だった」は別**であり、同じ observation にしてはならない。

##### この規則は見た目ほど緩くない

「候補が落ちたら外す」は、本物の破損まで見逃すように読める。**cargo 自身が防いでいる。**
実測（1.96）:

| 構成 | 他候補の metadata | その候補 | 結果 |
| --- | --- | --- | --- |
| vendored な非 member | root は **0** | 101 | 外して続行。**健全なリポジトリ** |
| **member の manifest が壊れている** | root も **101** | 101 | **全候補が落ちる → `Failed`** |
| 非 member ディレクトリの壊れた manifest | root は 0 | 101 | 外して続行（vendor と同じ） |
| 独立 workspace の1つが壊れている | 他は 0 | 101 | 外して続行 |

**2行目が要点である。** member の manifest が壊れていれば cargo は**ルートの metadata も
落とす**ので、workspace の内側の破損は外しようがない。「外す」で消えるのは、**cargo が
ルートから見て無視できると判断した範囲だけ**である。

残るのは4行目——独立 workspace の manifest が壊れている場合で、これは外れる。
**外していいと決める。** 全体を落とせば、独立した補助 workspace を1つ持つだけの
リポジトリが計測不能になる（tokio の形そのもの）。後退の向きは D-17 が押さえており、
外したことは `report` と `check` が名指しする。

> **`[workspace] exclude` の穴は開かない。** 実測のとおり、`exclude` された package の
> metadata は**成功する**（exit 0）ので、これまでどおり独立した workspace として計測される。
> 外れるのは metadata が**落ちた**候補だけである。

#### ビルドの失敗を2種類に分ける

**「ビルドできなかった」には、性質の違う2つが混ざっている。**

| | 意味 | 扱い |
| --- | --- | --- |
| **構成の不一致** | ebpy が使うビルド構成に存在しない項目を、コードが参照している | その workspace を**計測対象から外す**。全体は失敗させない |
| **本物の失敗** | 型が合わない、依存が無い、綴りが違う | 従来どおり **`Failed`** |

**rustc 自身がこの区別を診断に書いている。** 参照先が `#[cfg(...)]` で外された項目だった場合、
rustc は error に子ノートを付ける。

```
error[E0433] cannot find `fuzz` in `mainlib`
  note: found an item that was configured out
      span: src/lib.rs:1   ← #[cfg(fuzzing)] の行
      span: src/lib.rs:2   ← pub mod fuzz; の行（primary）
```

#### 判定規則

`success == false` または `returncode != 0` のとき:

```
errors = level == "error" かつ spans が空でない message

errors が空                                   →  Failed("execution-failed")
errors のすべてが子ノートに
  "found an item that was configured out"
  を含む                                      →  構成の不一致（計測対象から外す）
1つでも含まないものがある                      →  Failed("execution-failed")
```

**span を持つ error だけを見る。** Rust 1.79 は `code: None` の error として
`aborting due to 1 previous error` を余分に出す。**これは失敗した全ケースで出る**ので、
数に入れると 1.79 では「すべてが configured out」が**常に偽**になり、
**この規則が静かに無効化される**。1.79 でだけ tokio 型のリポジトリが計測不能に戻る、という
版依存の穴になっていた。D-7 が既に採っている規律（code と primary span を持つものだけ扱う）と
同じ形にすることで塞がる。

**弁別子は `code` ではなく `spans` である。** 前版はここを「`code` を持つ error」と書いていたが、
それでは `compile_error!` が漏れる。`compile_error!` は `code: None` で出るので、**作者が意図して
置いた硬い失敗が、規則の目に入らなくなる**。

```
#[cfg(not(feature = "backend"))]
compile_error!("select a backend");        ← code: None, spans: 1（primary あり）

aborting due to 2 previous errors          ← code: None, spans: 0
```

`aborting due to …` は**唯一 span を持たない**。区別したい2つを、区別したい軸そのもの
（診断がソース上の位置を指しているか）で切れる。実測（§5.2）:

| fixture | `code` で判定 | `spans` で判定 |
| --- | --- | --- |
| cfg で隠したモジュールを参照 | 除外 | 除外 |
| 綴り間違い / 型エラー / `main` 無し | 失敗 | 失敗 |
| `compile_error!` と cfg 由来が同居 | **1.79/1.85 除外、1.96 失敗** | **3版とも失敗** |

`code` 版は**同じリポジトリを版によって別に分類していた**。`spans` 版は3版で一致し、しかも
`compile_error!` を本物の失敗として扱う——作者が「この構成では建てるな」と書いたのだから、
ebpy がそれを黙って外すのは越権である。

> **サポート範囲の両端で確認済み**（§5.3）。5ケース × 3版:
>
> | fixture | 1.79 | 1.85 | 1.96 |
> | --- | --- | --- | --- |
> | `cfg(feature)` でモジュールを隠す | `E0433` 除外 | 同 | 同 |
> | `cfg(target_os)` でモジュールを隠す | `E0433` 除外 | 同 | 同 |
> | `cfg(fuzzing)` で関数を隠す | **`E0425`** 除外 | 同 | 同 |
> | 綴り間違い | `E0433` **失敗** | 同 | 同 |
> | 型エラー | `E0308` **失敗** | 同 | 同 |

#### この規則が拾えない書き方がある

隠された項目を**裸のパス**で参照した場合、1.79 と 1.85 は note を付けない。1.96 で付くように
なった。実測（§5.2）:

```rust
#[cfg(feature = "extra")]
pub mod extra;

pub fn use_it() { extra::e(); }          // 裸のパス
```

| 参照の書き方 | 1.79 | 1.85 | 1.96 |
| --- | --- | --- | --- |
| `crate::extra::e()` | note **あり** | あり | あり |
| `use crate::extra::e;` | note **あり**（`E0432`） | あり | あり |
| `extra::e()`（裸） | **note 無し** | **note 無し** | あり |

裸のパスは 2018 edition 以降まず extern crate として解決されるので、rustc は
「未宣言のクレートまたはモジュール」と言う。cfg を見に行っていないので、note の付けようがない。

**倒れる向きは安全側である。** note が無い ⇒ 本物の失敗 ⇒ 全体 `Failed`。天井が黙って下がる
ことはない。**失うのは網羅性であって健全性ではない。** 「除外されるはず」と思った workspace が
1.79 では `Failed` になる、という形で現れる。

**それでも仕様として書いておく。** 書かなければ、実装者は「note はいつでも付く」と読む。
サポート下限を上げる判断（§5.3）をするとき、この行が材料になる。

> **判定に error code を使ってはいけない。** 実測で分離を確認した4ケース:
>
> | 与えたもの | code | configured out |
> | --- | --- | --- |
> | 綴り間違い（存在しないモジュール） | **E0433** | なし |
> | 依存の書き忘れ | E0432 | なし |
> | 型エラー | E0308 | なし |
> | cfg で隠された項目の参照 | **E0433** | **あり** |
>
> **綴り間違いも `E0433` を出す。** コードで許すと、本当に壊れたリポジトリを黙って
> 除外することになる。しかもコードは隠し方で変わる — モジュールを隠せば `E0433`、
> 関数を隠せば **`E0425`** である。**分類しているのは note であって code ではない。**

> **これは cfg 一般に効く。** 実測（1.96）:
>
> ```
> cfg(fuzzing)              モジュール  E0433 + configured out
> cfg(feature = "extra")    モジュール  E0433 + configured out
> cfg(target_os="windows")  モジュール  E0433 + configured out
> cfg(fuzzing)              関数        E0425 + configured out
> ```
>
> `cargo fuzz` は最も目につく事例にすぎない。**ebpy はただ1つのビルド構成を測る**ので、
> 構成の外にあるコードは2通りに分かれる — 単に含まれないだけ（害は無い。天井に載らない）か、
> **含まれないのに別のコードが参照している**（コンパイルエラーになる）か。後者がここで扱う
> 状態である。

> **根拠: 観測（1.79 / 1.85 / 1.96 で note の文字列が一致）。契約ではない。**
> error 本文は版で変わる（`cannot find` ↔ `failed to resolve: could not find`）が、
> **note の文字列は3版とも同一**だった。1.85 は `the item is gated here` を追加で出すので、
> **ノート集合の完全一致ではなく、特定の1文字列の存在**で判定する。
>
> **壊れる向きが安全側である。** 将来 rustc が文言を変えれば configured out を認識できなく
> なり、**現在の挙動（`Failed`）に戻るだけ**である。天井が壊れる方向には倒れない。
> それでも §5.3 のサポート範囲の両端で回帰テストを回す。

#### workspace 間の合算に `merge_cells` は使えない

`store/baseline.py:220` の `merge_cells` は、同じ `file × rule` が2つの part に現れると
**`ValueError` を送出する**。docstring がその理由を書いている — *Correct namespacing makes the
same file x rule impossible to produce from two different analyzers, so a collision here means a
caller passed overlapping parts … a bug worth raising loudly*。前提は**analyzer をまたぐ合流**で
あり、同じ analyzer の workspace をまたぐ合流ではない。

**衝突は正当に起こりうる。** Cargo の target は `path` を manifest 相対で指定できるので、
2つの workspace が同じ `.rs` を参照する構成は禁じられていない。

**同じセルの count は加算する。** 1つの invocation の中で同じ `file × rule` を数え上げるのと
同じ扱いであり、**同じリポジトリを2回測れば必ず同じ数になる**ので天井は再現する。

**`unattributed` は連結する。** 順序は `workspace_root` の昇順、各 workspace の中は stdout の
順。**重複除去はしない** — 2つの workspace が同じファイルを別々にコンパイルしたなら、
配置できなかった事実も2回起きている。cells の加算と同じ立場である。

> **加算が何を意味するかを書いておく。** 2つの workspace がコンパイルするファイルの違反は
> **2回数えられる**。セルの数は「そのファイルにある違反の個数」ではなく
> **「計測で観測された件数」**である。天井の性質（再現し、下がることはあっても勝手に上がらない）
> は保たれる。この構成は稀であり、区別のために別の集計軸を導入するほうが失うものが大きい。

**`Unavailable` が `Failed` より先に立つ、という規則は段2と段3の間にしか掛からない。**
前版はこれを全体の優先順位として書いていたが、発見は probe より先に走るので成立しない。

```
候補 A      : 壊れた Cargo.toml → metadata が失敗
候補 B      : 壊れた Cargo.toml → metadata が失敗
  全候補が落ちたので発見の段で決着し、probe には到達しない
```

これは隠された不整合ではなく**段の順序そのもの**である。発見が終わらなければ probe する対象が
定まらない以上、この順序は動かせない。

**段1が決着するのは全候補が落ちたときだけである**（前節）。一部だけが落ちた場合は、残った
workspace で段2・段3へ進む。したがって「metadata が失敗した候補があるのに clippy component
の不在が報告される」ことは起こりうるし、**そのほうが正しい** — 測れる workspace が残って
いる以上、次に利用者が直すべきは component の不在である。

**段1で失敗する候補が複数あるときは、リポジトリ相対パスの昇順で最初のものを返す。** 段2・段3の
順序は D-6 の「失敗したときの detail」と同じく `workspace_root` の昇順である。

**probe は全 workspace 分を先に済ませ、全て通ってから計測に入る。** 1つ目の workspace を
コンパイルし終えてから2つ目の probe が落ちる、という無駄な往復を避けられる。

#### 一度でも天井に載った範囲が測れなくなったら、それは後退である

構成の不一致で外した workspace は**セルを1つも出さない**。では、外した範囲が「元々測れて
いなかった」のか「測れていたのに測れなくなった」のかを、何で判定するか。

**baseline のセルでは判定できない。** `write_cells` は count が 0 のセルを落とすので
（`store/baseline.py:120-136`）、**違反0件で測れていた workspace と、一度も測っていない
workspace は、baseline 上で完全に同じ姿になる**。前版はここを「セルが無い ⇒ 元々測れて
いない」と書いていた。誤りである。しかも 0 件は ebpy がリポジトリを追い込む**行き先**の状態
なので、外れ値ではなく本流で外す。

**これは CLAUDE.md の「Absence and zero are different」そのものである。** 天井を守るために
書いた表で、天井が守る当の規律を破っていた。

##### 同じ問題を、コードは既に一段上の粒度で解いている

```python
# models.py:268-271
# Cells alone cannot distinguish "the analyzer ran and found no violations" from "the analyzer
# never ran". For example, a ceiling of zero is only verifiable if we know which analyzers
# contributed to that measurement.
frozen_analyzers: tuple[str, ...] = ()
```

**analyzer 軸で `frozen_analyzers` が解いていることを、workspace 軸で解けばよい。**
新しい概念は要らない。既にある解を一段細かい粒度に当てるだけである。

##### 契約が覚えるのは「外した package」である

ledger に、clippy が**外した package のディレクトリ**を記録する（D-17）。判定はこうなる。

```
今回外した package の集合  ⊆  契約が覚えている集合   →  通す
                          ⊄                       →  fail-closed
```

| 起きたこと | 今回外す | 契約 | 判定 |
| --- | --- | --- | --- |
| tokio 型（最初から測れない fuzz workspace） | `{fuzz}` | `{fuzz}` | 通す |
| 違反0件だった workspace に cfg ゲートが入った | `{fuzz, core}` | `{fuzz}` | **断る** |
| 外していた workspace が測れるようになった | `{}` | `{fuzz}` | 通す（契約が広がる） |
| crate を削除した | `{fuzz}` | `{fuzz}` | 通す |
| **外れた workspace に member が増えた** | `{fuzz, core}` | `{fuzz}` | **断る** |

**「測った package」ではなく「外した package」を覚えるのは、削除を後退と誤らないためである。**
測ったほうを覚えると、crate を1つ消すたびに `--force` を要求することになる。外したほうなら、
消えた crate はどちらの集合にも現れず静かに通る——そして天井は `prune` が正しく下げる。

##### root ではなく package を数える理由

**前版は workspace root の集合で比べていた。最終行を取りこぼす。**

```toml
# 初回 freeze
[workspace]
members = ["fuzz"]
exclude = ["core", "other"]
    → root "." は fuzz の cfg 不一致で外れる。unmeasured = {"."}
    → core と other は独立 package として測られ、core のセルが天井に載る

# あとで core を member に戻す
[workspace]
members = ["fuzz", "core"]
exclude = ["other"]
    → root は依然 "."。fuzz のせいで外れる。core はもう測られない
    → unmeasured = {"."} なので「後退なし」と誤判定し、core の天井が黙って消える
```

**workspace root は同じでも、その root が覆う範囲が変わる。** root の同一性は
「同じコードが測られている」ことを意味しない。`members` と `exclude` の間で package を
移すのは Cargo の正式な構成変更であり、普通のリファクタリングで起こる。

**package の集合なら、範囲の変化がそのまま集合の変化になる。** 外れた workspace について、
その**全 member のディレクトリ**を入れる。解決できなかった候補については、その候補
manifest のディレクトリを入れる（どちらも「package のディレクトリ」である）。

> **判定に使う値と、表示に使う値は別である。** 判定は package の集合、表示は workspace root
> ——「どの workspace が、どのファイルの天井を失わせたか」を名指しするには root が要る。
> これは §2 で述べた「判定は健全でなければならないが、表示は近似でよい」の適用である。

> **これで以前挙がった2つの取りこぼしも塞がったままである。**
> `[lib] path = "../shared/lib.rs"` のようにソースが package ディレクトリの外にある構成も、
> 同じ `.rs` を2つの workspace が測っている構成も、**パスの前方一致ではなく集合の包含**で
> 比べるので判定に影響しない。後者では、片方が外れた時点で `check` が断る——
> `prune_cells` が 2→1 に下げるより先に。

##### 覚えない範囲があることは、認めて書く

`Cargo.toml` が git から外れて**発見されなくなった**場合は、どちらの集合にも現れないので
断らない。これは clippy 固有の穴ではなく、**ruff の設定から directory を exclude したときと
同じ種類**の、既存の設計が既に受け入れている限界である。ここで塞ぐと §2.5 の制動
（「理論上そうなりうる」だけでは決定を増やさない）に反するので、**塞がない**と決める。

**「発見されない」と「発見できたが解決できない」は別である。** 後者（vendored な manifest、
壊れた `Cargo.toml`）は候補として手元にあるので `unmeasured` に入り、**上の包含判定に
掛かる**。塞がないと決めたのは前者だけである。

**後退を「天井を持ち越す」で処理してはいけない。** 持ち越せば `check` は通り続け、
リポジトリの一部が検証されないまま**無期限に固定される**。これは既存の不変条件を
パス粒度で破ることになる — `build_global_freeze` の docstring が
*any analyzer it cannot completely measure prevents the freeze rather than being silently
omitted*（`commands/freeze.py:204-208`）と書いているのと同じ規律である。

**復帰の手段は意図的な `freeze --force` である。** 契約を狭める唯一の道が `--force` である
ことは、コード自身が既に宣言している（同 docstring）。測れなくなった範囲を天井から
落とすのも契約を狭める操作なので、**同じ扉を通す**。

```
cfg ゲートを足した / feature の既定を変えた
  → 次の check が断る。何が測れなくなったかを名指しする
  → 利用者が選ぶ:
       (a) cfg を直して測れる状態に戻す
       (b) ebpy freeze --force で、狭くなった契約を意図して受け入れる
```

#### 必要な値と、それを使う場所

```python
@dataclass(frozen=True)
class AnalysisMeasurement:
    cells: CellCountsView
    unattributed: tuple[UnattributedFinding, ...] = ()
    unmeasured: tuple[UnmeasuredScope, ...] = ()  # 新規


@dataclass(frozen=True)
class UnmeasuredScope:
    """One range clippy could not measure, as the runner saw it."""

    root: str  # 表示用。workspace root、無ければ候補 manifest のディレクトリ
    packages: tuple[str, ...]  # 判定用。package ディレクトリ（リポジトリ相対、昇順）
```

**`root` は表示に、`packages` は判定に使う。** 2つ持つのは、前節のとおり root の同一性が
範囲の同一性を意味しないからである。

| 外れた原因 | `root` | `packages` |
| --- | --- | --- |
| 構成の不一致（D-6） | `workspace_root` | その workspace の**全 member のディレクトリ** |
| metadata が失敗（D-3） | **候補 manifest のディレクトリ** | 同じ値を1つだけ |

**2行目を見落としてはいけない。** metadata が落ちた候補について cargo は何も返していないので、
その候補がどの workspace に属するはずだったか、member が何かは**分からない**。手元にあるのは
git が返した候補のパスだけである。**分からないものを分かったふりをせず、その1つを入れる。**

> **2種類が同じ範囲に別名を付けることはない。** workspace の内側の manifest が壊れれば
> cargo はルートの metadata も落とすので（前掲の実測）、「ルートは構成不一致、member は
> 解決不能」という食い違いは起こらない。全候補が落ちて `Failed` になる。

**member のディレクトリを入れるとき、workspace root は `packages` に入れない**（virtual
workspace の root は package ではない）。非 virtual な root は自身が member なので、
metadata の `workspace_members` にそのまま現れる。 前版は member を
平坦化した prefix を入れていたが、それでは元の workspace を復元できない——複数 member を持つ
virtual workspace では、prefix の列から root も grouping も workspace 数も戻らない。
`check` は「どの workspace か」を名指しし、`report` は workspace 数を数える。**root を1つずつ
持てば両方そのまま出せる。** D-3 の metadata が既に `workspace_root` を返している。

**後退の判定は決定層が行う。**

```
後退 = clippy ∈ frozen_analyzers
       かつ  unmeasured の packages  ⊄  ledger が覚えている集合
```

**`clippy ∈ frozen_analyzers` を落としてはいけない。** clippy が契約に入っていない
リポジトリでは、clippy は計測されても**天井を持たない**。そこで後退を主張すると、
存在しない天井の後退で gate することになり、既存の不変条件と真正面から衝突する——
`tests/test_check.py:134` の `test_a_non_contract_analyzer_is_named_but_never_gates` が
「契約外の analyzer は名指しするが、決して gate しない」を固定している。

現実に起きる形はこうである。config 無し、契約は `{ruff, mypy}`、Rust と Python が同居、
clippy は未 freeze、`fuzz` だけが cfg 不一致。この条件を落とすと、`{fuzz}`
に対して ledger の既定値 `{}` が比較され、**Python リポジトリの `check` が Rust の
fuzz workspace を理由に落ちる**。

契約外のときは、`unmeasured` は**名指しの材料にだけ使う**（`report` / `check` の1行）。

セルは判定に入らない。入れると 0 件で測れていた workspace を取りこぼす（前節）。
`check` が**名指しする**セル——利用者に見せる、天井を失う範囲——は、新たに外れた root の
member ディレクトリ配下にある baseline のセルから引く。**判定と表示で使う値を分ける**のは、
判定が健全でなければならない一方、表示は近似でよいからである。

| コマンド | 後退したとき |
| --- | --- |
| `check` | **断る。** どの workspace が、どのファイルの天井を失わせたかを名指しする |
| `prune` | **断る。** 天井を触る操作なので `check` と同じ |
| `freeze`（非 `--force`） | **断る**（そもそも `_already_frozen` が先に断る） |
| `freeze --force` | **通す。** 狭くなった契約が新しい契約になり、`unmeasuredPackages` を書き直す |
| `report` | **断らない。** 名指しして表示し、**backlog は baseline を持ち越す**（下記） |

**`store/baseline.py` も `prune_cells` も無変更である。** 後退しているなら `prune` は
そもそも走らない。後退していないなら守るべき天井が無い。**持ち越しの仕組みは要らなかった。**
変わるのは ledger だけである（D-17）。

##### `report` の backlog は、後退時に baseline を持ち越す

`report` は断らないが、**黙って backlog を縮めてもいけない**。`_backlog_cells_for` は
status が `complete` なら baseline を今回の計測へ prune する
（`decide/analysis_report.py:189-199`）。後退しているとき、外した workspace のセルは今回の計測に
現れないので、**prune が backlog の表からそれらを消す**——利用者から見れば「直ったように見える」。

**後退しているときは、失敗・`incomplete` と同じ経路に倒す**：baseline をそのまま backlog として
表示し、なぜ持ち越したかを analyzer の行に添える。天井が実際に下がるわけではない
（`report` は何も書かない）が、**画面上でだけ下がって見えるのは、下がったのと同じくらい悪い**。

> **これは seam の分担どおりである。** parser が報告するのは
> 「この範囲は測っていない」という**事実**だけで、baseline を知らない。
> 「その事実が後退かどうか」は天井を知っている決定層が決める。
> `docs/measurement-seam.md` の *The seam owns measured facts. It does not own ceilings,
> gate policy or persistence.* に一致する。

> **status は `complete` のままである。** `unattributed` は空なので `classify` は `complete` を
> 返す（`measurement/observation.py:107`）。**observation は正しく「測れたものは測れた」と
> 言っており**、断るかどうかは天井と突き合わせた決定層の判断である。`incomplete` に倒すと、
> 元々測れていない workspace を持つリポジトリ（tokio）まで永久に断ることになる。

#### 外したことを黙らせない

構成の不一致で外した workspace は、必ず表に出す。

| 出口 | 何を出すか |
| --- | --- |
| `report` | analyzer の行に「N workspace(s) not measured in this configuration」を添え、root を列挙する |
| `check` / `freeze` | 同じ1行を出力に含める |

文面は、**理由と、それが何を意味するかを両方書く**。

```
{root} does not compile in the configuration ebpy measures.
  It references items hidden behind a `cfg`. ebpy holds no ceiling for it,
  and new violations there are not gated.
```

**`diagnose` には出さない。** 前版は `diagnose` に gap を1つ足していたが、成立しない。
`diagnose` は `RepoFacts` だけを受け取る純粋な経路であり（`decide/diagnose.py:140`）、
本仕様も計測の呼び出し口を `check` / `freeze` / `prune` / `report` の4つに限っている（D-16 も
`diagnose` では probe しないと明記している）。**gap を出すには cargo を起動するしかなく、
それは層の境界を壊す。**

ledger の `unmeasuredPackages` を `diagnose` に渡せば cargo 無しでも出せる——が、それは
**最後の freeze の時点の事実**であって、今この作業ツリーの事実ではない。`diagnose` は
リポジトリを今見て語る P0 の調査なので、そこに古い計測結果を混ぜない。**外したことは
`report` と `check` が、実際に測った直後に言う。**

**最後の1文が要点である。** 元々測れていない範囲は**ゲートされない** — 天井は下がらないが、
上がりもしない。その限界を利用者が読める場所に置く。

**後退したときの文面は別である。** これは gap ではなく、`check` / `prune` が断る理由である。

```
{root} no longer compiles in the configuration ebpy measures.
  <file>:<rule> …（天井を失うセルを名指しする）
Fix the `cfg` so these compile again, or run `ebpy freeze --force`
to accept the narrower contract deliberately.
```

**2つの出口を両方書く。** 直すのか、狭い契約を受け入れるのか、**利用者が選ぶ**。
ebpy が黙って選ばない。

#### 失敗したときの detail

**workspace の順序は `workspace_root` のリポジトリ相対パスの昇順**とする。metadata を叩いた順に
依存させない — 候補の順序は `facts.all_files` に由来し、git の出力順が将来変わっても detail の
文面が変わらないほうがよい。

| | |
| --- | --- |
| probe の失敗 | **最初の失敗で止める。** 残りの probe は叩かない |
| 計測の失敗 | **最初の失敗で止める。** 残りの workspace はコンパイルしない |
| detail | 失敗した workspace の相対パスを冒頭に置き、続けてその workspace の detail |

打ち切るのは、全体が `Failed` になることが最初の失敗の時点で確定するからである
（部分成功を `Measured` にしない、が上の決定である）。**残りを走らせても観測は変わらず、
フルビルド1回分の時間だけが増える。**

### D-7. セル化の条件と、拒否する条件

**セル化する** — 次を**すべて**満たす message だけ。

```
reason == "compiler-message"
level  == "warning"
code   が非 null
spans に is_primary == true のものが1つ以上ある
```

位置は `is_primary == true` の span から取る。複数ある場合は
`(file_name, line_start, column_start)` が最小のものを選ぶ（決定的にするため）。

**黙って捨てる** — 上を満たさない message、および `compiler-artifact` / `build-script-executed` /
`build-finished`。ただし **`build-script-executed` からは `out_dir` を収集する**（D-9）。
セルは作らないが、読まない行ではない。`level` と `reason` を閉じた集合として扱わない。

**`package_id` は読まない。** `compiler-message` は診断がどの package のものかを `package_id` で
持つが、v1 ではこれで絞り込まない。**絞り込みの代わりに D-9 の containment が効く** — 依存
クレートは lint されない（`RUSTC_WORKSPACE_WRAPPER` が workspace member にしか掛からない）ので
そもそも出ず、workspace 外を指す span が出た場合はリポジトリ外のパスとして拒否される。

> **これは v1 の決定であって、`package_id` が不要だという主張ではない。** rustc は span が
> 外部 crate を指しうると書いており、マクロ展開の由来がそこに現れる。`package_id` で
> 「workspace member の診断だけ」に絞れば意味は狭く正確になるが、`RustWorkspace` に member ID を
> 持ち回る必要が生じる。**containment だけで天井は壊れない**ので、必要が実際に現れるまで
> 持ち込まない。

**天井に載せられないパスは、計測ごと失敗させない。** D-9 の判定は3つに分かれる。

| パスの状態 | 扱い |
| --- | --- |
| リポジトリ内の実在ファイル | セル化する |
| `build-script-executed.out_dir` の下（絶対パス） | **黙って捨てる。** 生成物であってソースではない |
| それ以外で天井に載せられない | **`UnattributedFinding` として記録** → status は `incomplete`（下記） |

**`invalid-output` にするのは、JSON の構造・型が読めないとき（D-6）と、metadata の
containment 検査に落ちたとき（D-3）だけ**である。パスが載せられないことは
「出力を読み切れなかった」ではない — **読めたうえで、天井の座標系に置けない**という別の事実で
ある。`UnattributedFinding` はまさにその状態のために seam が持っている語彙であり、
ruff が syntax error のファイルに使っているのと同じものである。

**詰める値を決める。** `UnattributedFinding`（`models.py:65`）は `file` / `line` / `message` の
3つとも必須である。

```python
UnattributedFinding(
    file=報告された file_name（前置も正規化もしない、生の値）,
    line=選択した primary span の line_start,
    message=message.message,
)
```

`file` を生の値にするのは、**読む人が clippy の出力と突き合わせられるようにするため**である。
前置後の値を入れると、リポジトリに存在しないパスを「ebpy が組み立てた形」で見せることになり、
何が起きたのか追えなくなる。

`message.message` を読むのはこの経路だけなので、**型検査もここでだけ行う**（`str` であること。
D-6 の段階的検査に足す）。セル化できた message では読まない。

> **既存の表示文面を広げる必要がある。** `UnattributedFinding` の docstring は
> *typically a syntax error that hides a file from every rule* であり、表示側4箇所も
> syntax / parse の語で書かれている。
>
> | 場所 | 現在の語 |
> | --- | --- |
> | `models.py:65` の docstring | *typically a syntax error* |
> | **`models.py:78` の `AnalysisMeasurement` のコメント** | *Syntax errors cannot be grandfathered* |
> | `commands/check.py:60` `_incomplete_reason` | syntax error のファイル一覧として組み立てる |
> | **`commands/freeze.py:145` `_refusal_reason`** | *"incomplete": syntax errors block attribution* |
> | `commands/freeze.py:53` `_unattributed_report` | *the syntax-error files an analyzer could not lint* |
> | `commands/prune.py:48` `_carry_reason` | 同系の文面 |
> | `render/analysis_report.py:44` `_incomplete_detail` | *the unparsed files* |
> | `docs/cli/report.md` | 同系の文面 |
>
> **`_refusal_reason` を落とさないこと。** ここは `freeze` が実際に断るときに利用者が読む
> 文面であり、clippy の配置不能パスもこの枝を通る。**仕様どおりに実装しても、断る理由が
> 嘘になる**箇所である。
>
> clippy の配置不能パスは syntax error ではない。**「天井の座標に置けなかった finding」という
> 上位の語に置き換える** — `UnattributedFinding` という型名が既にその意味であり、
> docstring と表示だけが1つのツールの事情に寄っていた。ruff の syntax error はその一例に
> なる（*typically* を残せば嘘にならない）。

> **根拠: 契約 + 観測。** rustc のドキュメントは明示的に前方互換を要求している —
> "New fields may be added. Enumerated fields like "level" or "suggestion_applicability" may add
> new values."。また `code` が null になりうること（"Some messages may set this value to null"）、
> `spans` が空になりうること（"This may be empty, for example for some global messages"）も
> どちらも契約として書かれている。
>
> この規則が締め出すのは、**span や code を欠く診断という形のバージョン差**である
（新しい lint が増えることは締め出さない。§5.3 を参照）。Rust 1.79 は成功ビルドでも
> `(code=None, level='warning', spans=0)` を出すが（1.85 で消えた）、1.96 の `failure-note` と
> 同じ規則で落ちるため、どのツールチェインでも同じ件数になる。§5.1 も参照。

> **`is_primary` を使う根拠: 契約。** rustc の JSON schema は `is_primary` を
> *Whether or not this is the "primary" span* と定めており、位置の特定にはこれを使う。
> `spans[0]` が primary である保証はどこにも書かれていない。
>
> **containment を要求する根拠: 実装読解。** 「先頭要素が `..`」という判定では不十分である。
> `normalize_analyzer_path` は**相対パスを畳まない**（`cell_key.py:75-77`）ので、
> nested root `crates/a` に `../shared/src/lib.rs` を前置すると次のようになる。
>
> ```
> normalize_analyzer_path('crates/a/../shared/src/lib.rs')
>   → 'crates/a/../shared/src/lib.rs'      ← 先頭要素は 'crates'。素通りする
> ```
>
> mypy は同じ問題に突き当たっている（`tools/mypy/_runner.py:154-165`）— *the cell key would
> embed this host's directory layout and no other machine could reproduce the ceiling … Refuse
> rather than write a host-dependent baseline.* mypy は絶対パスだけ見れば足りた（mypy は絶対
> パスで報告する）が、clippy は**相対のまま外に出る**ので判定が1つ増える。
>
> **守っている不変条件は同じで、伝え方だけが違う。** どちらも「ホスト依存の天井を書かない」
> ためにセルを作らない。mypy はそこで計測ごと断つが、clippy は `UnattributedFinding` に
> 落として計測は続ける — build script の生成コードのように、**載せられない診断が正常に
> 出るリポジトリが実在する**からである（D-9 の実測）。mypy にはその事情が無い。

#### `ClippyAnalyzer` の `noun`

`Analyzer` Protocol は `noun` を必須にしている（`measurement/analyzer.py:19`）。
**`"Rust lint warnings"`** とする。`"Clippy lints"` では狭い — D-8 のとおり、同じ
ストリームには rustc の lint（`unused_variables` など）も混ざり、それらも天井に載る。ruff の *Lint violations* / mypy の *Type errors* と同じく、
その analyzer が見つけるものを名指しする語である。

`tests/test_tools.py` は registry の要素を厳密一致で検査しているので、`clippy` の追加と
D-2 の `language` プロパティ追加の両方で更新が要る。

### D-8. rule ID の綴り

接頭辞を剥がさない。

```
clippy:clippy::needless_return    ← clippy lint
clippy:unused_variables           ← rustc lint（同じストリームに混在する）
```

> **根拠: 観測 + 実装読解。** `--all-targets` の出力で clippy lint と rustc lint
> （`unused_variables`）が同じストリームに現れることを確認した。`clippy::` を剥がすと両者の
> 名前空間が混ざり、開発者が `#[allow(...)]` に書く綴りとも一致しなくなる。
>
> `cell_key.py` / `models.py` / `measurement/observation.py` は**無変更**で通る。
> `split_rule` が最初のコロンだけで割るため（`cell_key.py:46`）、local code にコロンが残っても
> 往復する。実際に検証した。
>
> ```
> qualify_rule('clippy','clippy::needless_return')
>   → 'clippy:clippy::needless_return' → ('clippy', 'clippy::needless_return')
> Measurement(analyzers={'clippy': Measured(...)})  → 検証通過
> ```
>
> rule ID の入口は freeze 経路だけではない。`ebpy log --rule` も `is_rule_id` を通す
> （`commands/log.py:40`）。`is_rule_id` は `split_rule` と同じ `_partition`（`cell_key.py:33`）を
> 使うので `clippy:clippy::needless_return` は通るが、`RULE_HINT`（`commands/log.py:24`）の例に
> コロンが2つ含まれる形が無いため、打った人が疑う余地が残る。§7 #2 と #5 を参照。

### D-9. パスの前置と正規化

clippy が報告するパスは、観測上 **`workspace_root` 相対**であり、実行時の cwd に依存しない。
**これは契約ではない** — rustc の JSON schema は `file_name` の相対性を保証しておらず、
根拠は §5.2 のとおり観測（複数版で一致）である。しかも root の外の member については
**絶対パスで返る**ことが分かっている（§5.1）。

したがって v1 が受理する形は「workspace-root 相対のパス」だけとし、**絶対パスはリポジトリ内を
指していても拒否する**。リポジトリ内の絶対パスを救う規則を足すことはできるが、それは
「絶対パスが出た＝想定していない構成」というシグナルを消してしまう。**拒否は診断であり、
救済ではない。**

runner は次の順で処理する。

1. `\` を `/` に置き換える
2. **絶対パスを判別する。** `PurePosixPath` と `PureWindowsPath` の**両方**で `is_absolute()`
   を判定し、どちらかが真、または `PureWindowsPath(path).drive` が非空なら絶対とみなす
   - この実行が報告した `build-script-executed.out_dir` のいずれかの下にある絶対パス
     → **黙って捨てる**（生成コード。下記）
   - それ以外の絶対パス → **`UnattributedFinding`**
3. **報告されたパス単体を正規化し、ファイルが残ることを確かめる**（下記）。
   結果が空、**または最後の segment が `..`** なら `UnattributedFinding`。
   **この段では先頭の `..` を保持する**
4. **`workspace_root` のリポジトリ相対パス**（D-3 が返した値）を前置する
5. もう一度正規化する。`..` がリポジトリの外へ出るなら `UnattributedFinding`
6. **正規化後のパスが `cwd` の下に実在するファイルであることを確かめる。**
   実在しなければ `UnattributedFinding`（下記）。
   **`resolve()` / `is_file()` 自体が失敗した場合も `UnattributedFinding`** — 捕まえるのは
   `OSError`（権限、壊れた mount、長すぎるパス）、`ValueError`（NUL 文字）、
   `RuntimeError`（symlink のループ）の3つ
7. `normalize_analyzer_path` に渡す

**正規化を2回に分ける理由。** 前置してから1回だけ畳むと、**nested workspace ではファイルを
指さないパスがディレクトリ名として通る**。

```
workspace_root = crates/a    報告パス = foo/..
  1回だけ畳む : crates/a/foo/..  → crates/a      ← ディレクトリがセルキーになる
  2段階       : foo/..           → ""            ← 手順 3 で拒否される
```

手順 3 で先頭の `..` を保持するのは、`../shared/src/lib.rs` のような正当な報告パスを
ここで落とさないためである。リポジトリ外への脱出は、前置後の手順 5 が判定する。

**空だけを見ても足りない。** `..` と `../foo/..` はどちらも畳んだ結果が `..` になり、空では
ないので素通りする。前置すると `crates/a/..` → `crates` となり、**ディレクトリ名がセルキーに
なる**。末尾が `..` のパスはファイルを指していないので、そこで断つ。

#### 字句正規化の手順

```
def collapse(path, *, keep_leading_parent):
    stack = []
    for part in path.split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif keep_leading_parent:
                stack.append("..")          # 手順 3。前置がまだなので判定を保留する
            else:
                → UNATTRIBUTED              # 手順 5。repo の外へ出る
            continue
        stack.append(part)
    return "/".join(stack)

手順 3: collapse(reported, keep_leading_parent=True)
        空 または 末尾 segment == ".." なら UNATTRIBUTED
手順 5: collapse(workspace_root + "/" + それ, keep_leading_parent=False)
```

**`PurePosixPath` は `..` を畳まない。** `PurePosixPath("crates/a/../shared")` は
`crates/a/../shared` のままである（Python は `..` を意図的に保持する）。畳み込みは
自前で書くしかない。

**両方の flavour で絶対パスを判定する理由。** `C:\outside\file.rs` は `/` へ置換すると
`C:/outside/file.rs` になり、`PurePosixPath.is_absolute()` は **False** を返す。片方しか見ないと
workspace root の下に前置され、リポジトリ内の相対パスとして通ってしまう。

```
'C:/outside/file.rs'  →  posix 絶対? False   windows 絶対? True
```

**drive-relative パスは `is_absolute()` を両方すり抜ける。** `C:foo.rs`（ドライブ指定のある
相対パス）は posix / windows のどちらでも `is_absolute()` が False になる。

```
'C:foo.rs'  →  posix 絶対? False   windows 絶対? False   windows drive? 'C:'
```

したがって手順 2 の判定は「両 flavour の `is_absolute()` のいずれか、**または**
`PureWindowsPath(path).drive` が非空」とする。

**正規化の結果が空になるパスも拒否する。** `.` や `foo/..` は上の stack アルゴリズムで
`""` になる。ファイルを指していないので、セルのキーにできない。

これは `normalize_analyzer_path`（`cell_key.py:76`）が既に両方を試している理由と同じであり、
同じ判定を前置の**前**に置く。

**ホスト非依存に固定する。** `os.path.normpath` は OS によって区切り文字の解釈が変わるので
使わない。

#### 実在検査が要る理由 — `--remap-path-prefix`

**rustc の `--remap-path-prefix` は診断のパスをテキスト置換する。** 相対から相対への置換は、
**リポジトリ内に見えるのに存在しないパス**を作る。実測（cargo 1.96.0）:

```
（remap なし）                          src/lib.rs
RUSTFLAGS=--remap-path-prefix=src=shadow      shadow/lib.rs      ← 手順 2〜5 を素通りする
RUSTFLAGS=--remap-path-prefix=src=/elsewhere  /elsewhere/lib.rs  ← 手順 2 が捕まえる
RUSTFLAGS=--remap-path-prefix=src=../outside  ../outside/lib.rs  ← 手順 5 が捕まえる
```

3件とも `build-finished.success = true`、exit 0 である。**1件目だけが素通りし、
存在しないファイルのセルが天井に載る** — 本仕様が最も避けたい形の誤りである。

**手順6 の実在検査がこれを止める。** 完全な証明ではない（remap 先が偶然別の実在ファイルに
一致する場合は残る）が、穴は桁違いに狭くなる。remap を掛けたリポジトリでは**全診断が
unattributed になる**ので `incomplete` となり、`check` も `freeze` も fail-closed する。
黙って通ることはない。

#### 生成コードを捨てる理由と、その識別方法

**build script が生成したコードの診断は絶対パスで返る。** 実測（1.79 / 1.85 / 1.96 で一致）:

```
include!(concat!(env!("OUT_DIR"), "/gen.rs")) を持つクレート
  MSG clippy::needless_return
      ['/…/gen/t9/debug/build/gendemo-0d659449bd833bfd/out/gen.rs']
  build-finished success = True
```

**これを `invalid-output` にすると、build script で警告の出るコードを生成する
リポジトリが丸ごと計測不能になる。** `unattributed` にしても `incomplete` が固定され、
`freeze` が永久に断る。どちらも受け入れられない。生成物は**ソースではない**ので、天井の
対象外として黙って捨てる。

**識別には `target_directory` を使わない。同じ stdout の
`build-script-executed.out_dir` を使う。** 同じ実行の JSON から拾えるので、config の解釈が
一切要らない。実測:

```
build-script-executed out_dir = /…/gen/t9/debug/build/gendemo-0d659449bd833bfd/out
diag path                     = /…/gen/t9/debug/build/gendemo-0d659449bd833bfd/out/gen.rs
                                → out_dir の下にある
```

> **`target_directory` を基準にすると2方向に壊れる。**
>
> **狭すぎる方向。** Cargo は中間生成物の置き場を `build.build-dir` で target ディレクトリと
> 別に設定でき、`OUT_DIR` はそちらに置かれる。明示的な `build-dir` があるリポジトリでは
> 生成コードのパスが `target_directory` の下に無く、`unattributed` に落ちて `freeze` が
> 断り続ける。
>
> **広すぎる方向。** `CARGO_TARGET_DIR` はリポジトリルートやその祖先を指せる。そのとき
> **リポジトリ内の全絶対パスが「生成物」として黙って捨てられる** — remap で絶対化された
> 実ソースまで消える。天井が黙って空になるのは、この仕様が最も避けている失敗である。
>
> `out_dir` は cargo 自身が「ここに生成した」と言っている値なので、どちらの方向にも外れない。

**`out_dir` は全行を読み終えてから使う。** `build-script-executed` は
`compiler-message` より後に現れうるので、1パスで判定しようとすると取り逃がす。パーサは
行を全部走査して `out_dir` を集めてから、パスの分類を行う2パス構成にする。

**`out_dir` にも診断パスと同じ正規化を掛ける。** 掛けないと Windows で必ず食い違う。

```
out_dir   : C:\repo\target\debug\build\x\out
file_name : C:/repo/target/debug/build/x/out/generated.rs   ← D-9 手順1 で / に直っている
```

| | |
| --- | --- |
| 1 | `\` を `/` に置き換える |
| 2 | 字句正規化を掛ける（`.` と `..` を畳む） |
| 3 | 両 flavour で絶対パスであることを確かめる。そうでなければ `invalid-output` |
| 4 | 末尾の `/` を落とす |

**包含判定は「同値、または `out_dir + "/"` の前方一致」とする。** segment 境界で切るので、
`…/out` が `…/outside.rs` に一致しない。

**`out_dir` の集合は invocation ごとに隔離する。** workspace A の `out_dir` で workspace B の
診断を判定してはいけない。parser は 1 invocation = 1 call なので（D-6）、集合はその呼び出しの
中だけで閉じる。

**セルキーは字句パスのまま、検査だけ resolve する。** 手順6の実在検査と containment は
`repo_root.resolve()` と候補の resolved path で行うが、**天井に書くのは畳んだだけの字句パス**
である。resolve した結果を書くと、symlink を張ったチェックアウトで天井が再現しない。

**ファイルシステム操作の例外を parser の外へ漏らさない。** 手順6 が触るのは
**clippy が報告した外部入力**であり、任意のバイト列が来うる。`Path.resolve()` と
`is_file()` は `OSError` / `ValueError` / `RuntimeError` を送出しうるので、3つとも捕まえて
`UnattributedFinding` にする。parser が送出するのは `ClippyInvalidOutputError` か
`ClippyFailedError` だけ、という契約（D-6）はここでも守られる。

**外向きの symlink は `unattributed` にする。** リポジトリ内に見えるパスが resolve すると外を
指す場合、そのセルは「このホストでの解決結果」に依存するので天井に載せられない。
拒否ではなく `unattributed` なのは、D-9 の他の載せられないパスと同じ理由である。

**字句的に畳むのは、シンボリックリンクを解決しないためである。** 解決結果はホストごとに違い、
天井が再現しなくなる。天井は「このホストで解決したパス」ではなく「リポジトリ内の位置」で引かれる。

前置の基準が `workspace_root` であって「発見した候補 manifest のディレクトリ」ではない点が
重要である。D-3 が `cargo metadata` に訊くのはこのためでもある。

> **根拠: 観測（Rust 1.79 / 1.96 で一致）。** workspace の `crates/a` から実行しても報告パスは
> `src/lib.rs` ではなく `crates/a/src/lib.rs` になる。`normalize_analyzer_path` は絶対パスしか
> 救えないので、相対パスのズレは runner の責任になる。

> **cwd を任せてはいけない根拠: 観測。** `cargo` は `Cargo.toml` を cwd から親方向に探索する。
> ルートに manifest が無いまま実行すると、**リポジトリの外のプロジェクトを lint した結果が
> 正常な計測として返る**。実測:
>
> ```
> myrepo/（Cargo.toml 無し。親ディレクトリに別プロジェクトがある）で実行
>   LINTED: clippy::ptr_arg  src/lib.rs      ← repo 相対に見えるが repo 外のファイル
>   build-finished success = True
>   exit = 0
> ```
>
> D-6 の完全性判定も D-7 の拒否条件もこれを止められない（`src/lib.rs` は相対で `..` を含まない）。
>
> **ただし cwd を固定するだけでは足りない。** リポジトリ内の manifest がリポジトリ外の
> `[workspace]` のメンバーである場合、そこを cwd にしても外部の workspace が lint される
> （D-3 の実測を参照）。止められるのは `cargo metadata` の `workspace_root` を検査したときだけで
> ある。D-3 がその検査を担い、D-9 はその結果を前置に使う。

### D-10. キャッシュされた診断の再出力は回帰テストで固定する

`tests/test_clippy_lifecycle.py` を追加し（`tests/test_mypy_lifecycle.py` に倣う）、実 cargo で
同じフィクスチャを2回計測して件数の一致を assert する。**`cargo clippy --version` が成功しなければ
skip する**（cargo の有無ではない。minimal な rustup プロファイルでは cargo はあっても
clippy component が無い）。

> **根拠: 観測のみ（ドキュメントに記載を見つけられなかった）。** 再コンパイルされなかった
> ユニットについても cargo は保存済みの診断を再出力する。workspace で1クレートだけ touch して
> 再実行しても、全クレートの診断がそろって出ることを確認した。
>
> ```
> ARTIFACT a   fresh=False    crates/a/src/lib.rs   ×2
> ARTIFACT b   fresh=True     crates/b/src/lib.rs   ×2
> ARTIFACT dep fresh=True     vendor/dep/src/lib.rs ×2
> ```
>
> ただしこれは cargo の実装挙動であり、歴史的には「2回目に警告が出ない」という既知の不具合が
> あった領域である。契約でない以上、前提にせず CI が守る不変条件に変える。`--target-dir` を
> 分けても2回目は再コンパイルされないので解決にならず、`cargo clean` は毎回のコストが
> 現実的でない。
>
> 一方 `cargo check` との相互汚染は**起きない**。ただしこれは**条件付きの契約と観測の組**で
> あって、単独の契約ではない。Cargo が保証しているのは
> 「`RUSTC_WORKSPACE_WRAPPER` を使えば artifact のハッシュが分かれる」ことまでである —
> "It affects the filename hash so that artifacts produced by the wrapper are cached separately"。
> **`cargo clippy` がその wrapper を使い続けること自体は、Clippy の利用者向け契約としては
> 見つけられなかった**（観測）。したがってこれも実測テストの対象に残す。

**このテストが失敗したときの意味を、テスト自身に書いておく。**

> 将来の cargo でこのテストが落ちた場合、**期待値を実測値に合わせて通してはいけない。**
> このテストが契約化しているのは「2回目の件数が1回目と同じ」という数字ではなく、
> **「再出力に依存してよい」という前提そのもの**である。落ちたということは前提が崩れたという
> ことなので、計測戦略の側を設計し直す（毎回 cold にする、あるいは再出力に依存しない形にする）。
> 期待値を 4 から 2 に書き換えれば、天井は静かに壊れる。

D-10 の根拠が「観測のみ」であることと、この注意書きは一組である。契約に載っていない挙動に
依存する以上、それが崩れたときに気付く仕掛けと、気付いたときに何をしてはいけないかの両方が要る。

### D-11. Python を検出できないリポジトリでは Python 専用サブコマンドが断る

§2.1 で「拒否（新規）」とした4つ — `diagnose` / `bootstrap` / `catalog` / `next --fan-in` — に
ガードを追加する。判定には **D-3 の `has_python()` を用いる**。Python が検出されない場合に
`CommandError` を返す。

**ただし `diagnose` と `bootstrap` は `has_python(cwd)` を呼ばない。** この2つは既に
`gather_facts()` を済ませている（`commands/diagnose.py:30` / `commands/bootstrap.py:38`）ので、
`languages_from_files(facts.all_files)` の結果をガードと `diagnose(..., languages)` の**両方に
使う**。cwd ラッパーを呼ぶと同じディスクを2回歩くことになり、D-3 の割り当て表と食い違う。

| サブコマンド | ガードの入手経路 |
| --- | --- |
| `diagnose` / `bootstrap` | `languages_from_files(facts.all_files)` から Python の有無を見る |
| `catalog` / `next --fan-in` | `RepoFacts` を作らないので `has_python(cwd)` |

必要なのは「Python があるか」だけなので、`detect_languages()` を通さず `has_python()` を
直接呼ぶ。D-3 の再構成により `detect_languages()` も cargo を起動しないので、どちらでも
Rust 側の異常には影響されないが、ガードが必要としている事実をそのまま名前で呼ぶほうが読める。

`install` と `skills install` は既に `pyproject.toml` の有無で断っているため（`install.py:165`、
`skills_install.py:292`）、本仕様では変更しない。

### D-12 の波及: `freeze` の `Unavailable` 案内

`commands/freeze.py:129` は `Unavailable` な analyzer をすべて同じ文面で断る。

```
{analyzer} is not installed. Install it first: `ebpy bootstrap` is the step.
```

**clippy にこれを出してはいけない。** D-12 は clippy の provisioner を作らないと決めているので、
`ebpy bootstrap` は何も解決しない。**存在しない出口へ案内することになる。**

**新しい API は足さない。** 案内は既存の `Unavailable.detail` に載せる。

```
freeze の unavailable 枝:
    observation.detail を引用する
    固定の「`ebpy bootstrap` is the step」は出さない

ClippyNotFoundError の detail:
    cargo または clippy が使えないこと
    「rustup 管理のツールチェインなら `rustup component add clippy`」という条件つきの案内
```

`Analyzer` Protocol に足すのは D-2 の `language` だけのままである。**「どう直すか」は
observation が既に運んでいる情報**であり、`Failed` の枝が現に `observation.detail` を引用して
いる（`commands/freeze.py:137`）。`Unavailable` だけが固定文言なのは、これまで
provisioner を持たない analyzer が存在しなかったからにすぎない。

これは D-12 の帰結であって clippy 固有の特別扱いではない。**「provisioner を持たない analyzer」
という状態が初めて生まれる**ので、その状態の文面を決める必要がある、というだけである。

### D-12. clippy provisioner は作らない

analyzer と detector のみを追加し、`ebpy bootstrap` の対象外とする（§2.6）。

> **根拠: 実装読解。** `plan_packages` が返すものは単一の dev-install コマンドに流し込まれる
> （`decide/bootstrap_plan.py:59` + `package_manager.py:11`）。clippy は dev dependency ではなく
> `rustup component add clippy` なので、この経路には乗らない。`ProvisionContext` も
> `has_pyproject` / `requires_python` / `run_prefix` と Python の語彙であり、生成される CI も
> `setup-python` + `setup-uv` に固定されている（`generate/workflows.py`）。

### D-13. detector も言語で絞る

`ToolDetector` に `languages` を足し（D-2 と同じ `Language` 型の集合）、`diagnose()` が
検出された言語に関係する detector だけを回す。**空集合はリポジトリ全体に関わることを意味し、
常に回る。**

```python
# repo/detect/detector.py
class ToolDetector(Protocol[S]):
    @property
    def languages(self) -> frozenset[Language]:
        """The languages this detector's tool belongs to; empty means repository-wide."""


# decide/diagnose.py:147 付近
detectors = tuple(d for d in DETECTORS if not d.languages or d.languages & languages)
tool_setups = {d.name: d.detect(facts) for d in detectors}
```

**detector 側だけ最初から複数形にする。** D-2 が Analyzer を単数形で始めるのは、
単一言語でない analyzer が現在1つも無いためである。detector にはもう存在する —
`GitleaksDetector`（`tools/gitleaks.py:81`、name は `secret-scan`）は workflow と
pre-commit の記述と `.gitleaks.toml` だけを見ており、言語に依存しない。これに `"python"` を
返させれば名前が主張する意味が偽になる。「2つ目の実装が現れるまで抽象化しない」という
`docs/measurement-seam.md` の教義を両側に一貫して適用すると、**analyzer は単数、detector は
複数**になる。

> **根拠: 実装読解。** `DETECTORS` は3つのものを同時に駆動している。
>
> ```python
> decide/diagnose.py:147   tool_setups = {detector.name: detector.detect(facts) for detector in DETECTORS}
> decide/diagnose.py:152   *(gap for detector in DETECTORS for gap in detector.gaps(...)),
> render/report.py:21      [detector.render_row(diagnosis.tool_setups[detector.name]) for detector in DETECTORS]
> ```
>
> clippy detector を素で登録すると、`Cargo.toml` の無い全 Python リポジトリで
> 「Clippy is not configured」という bootstrap gap と `clippy  no` の行が毎回出る。しかも D-12 で
> provisioner を作らないので、**解消する手段のない gap** になる。D-1 が消そうとしたノイズと
> 同じ種類のものである。

**波及先:**

- `decide/diagnose.py:152` の gap 生成 — 同じ絞った tuple を使う。
- `render/report.py:21` — `diagnosis.tool_setups[detector.name]` と**添字アクセス**しているので、
  `DETECTORS` 全部を回すと絞られた setup マップで `KeyError` になる。**`DETECTORS` を回したまま
  存在を確かめる形**に直す。

  ```python
  for detector in DETECTORS:
      if detector.name in diagnosis.tool_setups:
          ...
  ```

  **キー側を回す形にはしない。** `diagnosis_from_dict`（`models.py`）は台帳にある setup の
  キーを**そのまま**読み戻すので、将来版の ebpy が書いた未知のキーが混じりうる。キーから
  `DETECTORS_BY_NAME[name]` を引く実装は、そこで `KeyError` になる。registry 順が表示順で
  あることも、`DETECTORS` を回す側でしか保てない。
- `render/quality.py:151` — `if name in setups` の形なので**無変更で通る**。
- `render/quality.py:136` の `_unratcheted_marker` は **D-16 で変更する**。`setups[name].configured`
  だけから marker を作るので、`clippy.toml` を持たない Rust リポジトリでは
  **Outstanding に clippy の gap があるのに見出しに出ない**。`state.diagnosis.gaps` のうち
  `id.startswith("unratcheted:")` のものから marker を作る形に変える。gap は既に台帳にあるので、
  **言語情報を台帳へ新しく保存する必要は無い**。

  **ただし現在の roster で再フィルタする。**

  ```python
  {
      suffix
      for gap in diagnosis.gaps
      if gap.id.startswith("unratcheted:")
      and (suffix := gap.id.removeprefix("unratcheted:"))
      and suffix not in roster
  }
  ```

  `diagnosis` は前回の `diagnose` の写しなので、そのあと `freeze` した analyzer も
  gap として残っている。再フィルタしないと、**次に `diagnose` を回すまで
  「未 ratchet」と表示され続ける**。現在の実装が `name not in roster` を見ているのと同じ
  理由である。
- `diagnose()` が `languages` を引数で受け取る。呼び出し側は `commands/diagnose.py:31` と
  `commands/bootstrap.py:41` の2箇所。
- `_unratcheted_gaps`（`decide/diagnose.py:44`）は **D-16 で変更する**。現在は
  `setup.configured` だけを条件にしており、D-15 で `Cargo.toml` を `configured` の根拠から
  外すと、`clippy.toml` を持たない Rust リポジトリで gap が出なくなる。

### D-14. `report` は scope 不一致を専用の status で表す

`AnalyzerSummary.status`（`decide/analysis_report.py:61`）に、report だけが使う
`"scope-mismatch"` を足す。

```python
# decide/analysis_report.py
ReportAnalyzerStatus = AnalyzerStatus | Literal["scope-mismatch"]
```

| 状況 | status |
| --- | --- |
| 契約にあるが `to_measure` に無い（scope 不一致） | `scope-mismatch` |
| この ebpy build に runner が無い | `no-runner` |

#### 表示する roster

```python
def report_from_measurement(
    baseline: CellCounts,
    frozen_analyzers: tuple[str, ...],
    measurement: Measurement,
    scope_mismatches: frozenset[str],  # 新規。下記の定義
) -> AnalysisReport: ...
```

```
summary を作る対象 = measurement.analyzers.keys() ∪ frozen_analyzers
status = "scope-mismatch" if name in scope_mismatches else classify(...)
```

**`scope-mismatch` の analyzer は計測されていることがある。** config が clippy を宣言し
frozen が持たない場合、clippy は `to_measure` に入るので実際に走る。その計測が `Failed` だった
とき、status は `scope-mismatch` になるが **`failure` detail は残す**。

- **JSON**: `status = "scope-mismatch"` かつ `failure` に detail、`findings` は `Measured` なら
  その値。status が失敗を隠しても、detail は残っているほうが調べられる。
- **Markdown**: `_failure_banners`（`render/analysis_report.py`）は `failure != None` を最初に
  見るので、`Failed` の detail はそのまま出る。**変更が要るのは `incomplete` の枝である。**

`incomplete` の枝は `summary.status == "incomplete"` を条件にしているので、status が
`scope-mismatch` に置き換わると **syntax error で読めなかったファイルの banner が Markdown から
消える**（JSON には `unattributedTotal` が残る）。条件を status ではなく**保持しているデータ**に
変える。

```python
elif summary.unattributed_total > 0:
```

**scope の不一致と計測の状態は別々の事実であり、片方が他方を消す理由が無い。** status は
1つしか持てないので不一致が勝つが、detail は両方残す。

**`scope_mismatches` は D-4 の照合規則と同じ非対称性を持つ。** `ScopeDecision` が算出して渡す。

```python
if not frozen:
    scope_mismatches = frozenset()  # fresh。照合そのものをしない
elif declared is not None:
    scope_mismatches = declared ^ frozen  # config 由来は完全一致 → 対称差
else:
    scope_mismatches = (frozen & registered_analyzers) - detected_analyzers
```

**`registered_analyzers` の絞りを落とすと、未知の frozen analyzer が `no-runner` ではなく
`scope-mismatch` になる**（D-4 参照）。D-14 の表が `no-runner` の行を持っているのは、
この経路が生き続けるという前提である。

**先頭の `not frozen` を落としてはいけない。** fresh なリポジトリでは `frozen` が空なので、
対称差は `declared` そのものになり、**宣言した analyzer が全部 `scope-mismatch` として並ぶ**。
D-4 の「照合は有効な frozen contract があるときだけ」は `report` にも同じく掛かる。

**差集合を `frozen - to_measure` にしてはいけない。** config 由来のときは
`declared ⊆ to_measure` なので「宣言されたが未 freeze」の側が常に空になり、D-4 が不一致と
呼ぶ状態を `report` だけが見落とす。

```
frozen = {ruff}   declared = {ruff, clippy}
  frozen - to_measure = ∅        ← clippy が普通の非契約 analyzer として並ぶ
  declared ^ frozen   = {clippy} ← 正しく scope-mismatch になる
```

**引数で渡す。** 現在の `report_from_measurement`（`decide/analysis_report.py:203`）は
baseline / frozen / measurement しか受け取らず、`declared` も `detected_analyzers` も知らないので
`scope-mismatch` と `no-runner` を区別できない。決定関数が registry を暗黙の第4の権威として
参照するより、D-4 の「関係する値を1つにまとめて渡す」方針に揃える（`ScopeDecision` ごと渡しても
よいが、report が必要とするのは差集合だけである）。

これは現在の実装（`decide/analysis_report.py:208`）のままでよい。`measure_repository` は
`to_measure` のすべてを（`Unavailable` であっても）キーとして持つ dict を作るので
`to_measure ⊆ measurement.analyzers.keys()` が構成上成り立ち、`declared` は
`to_measure` に含まれるため既に覆われている。**`declared` を明示的に union する必要はない。**

明記しておくのは、`measurement` のキーだけを回す実装に縮めてはいけないためである。
frozen が `{clippy}`、`to_measure` が `{ruff, mypy}` のとき、clippy は measurement に現れない。
contract 側を union しないと `scope-mismatch` の行そのものが生成されず、天井の数字も出なくなる。

> **根拠: 実装読解。** `AnalyzerSummary.status` は `AnalyzerStatus` をそのまま使うので、
> 計測に存在しない analyzer は `classify(None)` で `"no-runner"` になる。その値の意味は
> *"a ledger contract naming an analyzer this ebpy build has no runner for at all"*
> （`measurement/observation.py:96`）と定義されている。scope 不一致で測らなかった analyzer に
> これを表示すると、**runner はあるのに「無い」と報告する**ことになる。D-4 が計測前の照合で
> 消したのと同じ嘘が、断らない `report` にだけ残る。
>
> `AnalyzerStatus` そのものを広げないのは、`check` / `freeze` / `prune` が照合で先に断つため
> この状態に到達せず、seam の語彙に到達不能な値を増やすことになるためである。

### D-15. `ClippyDetector` は clippy の設定だけを見る

`Cargo.toml` の存在を `configured=True` の根拠にしない。detector が見るのは次に限る。

- `clippy.toml` および `.clippy.toml`（公式にどちらも有効。ただし下記）
- `Cargo.toml` の `[lints.clippy]` / `[workspace.lints.clippy]`
- CI ワークフローや pre-commit 設定に現れる `cargo clippy`

#### 必要な facts を `RepoFacts` に足す

現在の `RepoFacts`（`repo/facts.py:33`）は `pyproject` を持つが Cargo の manifest を持たない。
detector が自分でファイルを読むと *"Everything read from disk once, so decisions stay pure"* という
`RepoFacts` 自身の契約を破るので、facts の側に足す。

`InvalidToml` は `repo/facts.py` に置く（`RepoFacts` のフィールドの型なので）。

```python
@dataclass(frozen=True)
class InvalidToml:
    """A manifest ebpy could not read, and why — kept apart from a manifest with no clippy config."""

    path: PurePosixPath  # リポジトリ相対
    detail: str  # 絶対パスを含まない（下記）


# RepoFacts に足すフィールド
cargo_manifests: Mapping[PurePosixPath, dict[str, Any] | InvalidToml]
clippy_config_paths: tuple[PurePosixPath, ...]  # clippy.toml / .clippy.toml
```

`InvalidToml` に入るのは **TOML の構文エラー・読み取りエラー・デコードエラーの3つ**である。
どれも「そこに何が書いてあるか ebpy には分からない」という同じ状態であり、`detail` が区別する。

```python
except (OSError, UnicodeError, tomllib.TOMLDecodeError)
```

**`detail` に絶対パスを入れない。** 診断は台帳と `QUALITY.md` に保存されるので、
`str(OSError)` をそのまま入れると**このホストのディレクトリ構成が成果物に焼き付く**。
mypy runner が repo 外のパスを拒否しているのと同じ理由である
（`tools/mypy/_runner.py:154-165`）。

| 例外 | `detail` に載せるもの |
| --- | --- |
| `OSError` | `error.strerror`。`None` のときは例外クラス名 |
| `UnicodeError` | エラー種別と位置（バイトオフセット） |
| `tomllib.TOMLDecodeError` | `str(error)`（行・列を含むがパスは含まない） |

ファイルの名指しは常に `InvalidToml.path`（リポジトリ相対）で行う。gap の形も固定する。

```
id     = f"clippy-manifest:{path}"
title  = f"{path} could not be read as TOML"
detail = f"{detail} — clippy's configuration in this file was not counted."
phase  = "tighten"
```

**`UnicodeError` を落としてはいけない。** `Path.read_text(encoding="utf-8")` は不正な UTF-8 に
対して `UnicodeDecodeError` を送出する。これは `OSError` でも `TOMLDecodeError` でもないので、
2つだけを捕まえると **`gather_facts` 全体が例外で終わる** — 検出どころかリポジトリの
どのコマンドも動かなくなる。

> **同じ穴が既存の `pyproject.toml` の読み取りにもある。** `repo/facts.py` の `gather_facts` は
> `tomllib.loads(pyproject_path.read_text(encoding="utf-8"))` を
> `except (OSError, tomllib.TOMLDecodeError)` で囲っている。不正な UTF-8 の `pyproject.toml` は
> ここを素通りする。**本仕様の作業ではない**（clippy とは無関係の既存の欠陥である）が、
> 同じ書き方を新しいコードに写さないために記録しておく。

**壊れた TOML は `configured=False` にしない。** 読めなかった manifest は `InvalidToml` として
記録し、`configured` の判定からは除外したうえで、**`diagnose` の gap として名指しする**。
`False` に丸めると「clippy の設定が無い」と「設定を読めなかった」が同じ表示になる —
*Absence and zero are different* が禁じている混同である。

#### gap までのデータ経路

detector の契約は `detect(facts) -> S` / `gaps(setup) -> list[Gap]`
（`repo/detect/detector.py:21`）で、`S` は `ToolSetup` に bound された型変数である。したがって
**`ToolSetup` の派生型を返すのが既定の経路**であり、`MypySetup`（`tools/mypy/detector.py:43`）に
前例がある。

```python
@dataclass(frozen=True)
class ClippySetup(ToolSetup):
    invalid_manifests: tuple[InvalidToml, ...]  # path でソート済み
```

- `ClippyDetector.detect()` は `ClippySetup` を返す。
- **`gaps()` が返すのは invalid manifest の gap だけである。** clippy の設定が無いこと自体は
  gap にしない。既存 detector の作法を写すと "Clippy is not configured" という bootstrap 系の
  gap が出るが、**clippy はリポジトリ側の設定なしで動き**（D-16）、**provisioner も無い**
  （D-12）ので、**解消経路の無い gap**になる。しかも D-16 の unratcheted gap と二重になる。
  未 ratchet の提案は D-16 だけが持つ。
- `gaps()` は `invalid_manifests` を**その順序どおりに**名指しする（決定的な出力のため）。
  **gap は manifest 1件につき1つ**とする（形は上記）。集約して1件にすると、直したときに
  どれが残っているのか読み取れない。
- **`configured=True` と invalid manifest は両立する。** 読めた側に clippy の設定があり、
  別の manifest が読めなかった状態は普通に起こる。gap は `configured` と独立に出す。
- `from_dict` は書かない。台帳は**すべての setup を base `ToolSetup` として読み戻す**設計であり
  （`models.py` の `diagnosis_from_dict`: *any extra provenance a tool wrote … is regenerated on
  the next `diagnose` and never read from disk*）、`MypySetup` も同じ扱いを受けている。

検出規則を機械的に書けるところまで落としておく。

| 対象 | 規則 |
| --- | --- |
| `clippy.toml` / `.clippy.toml` | いずれかの Cargo manifest の**祖先ディレクトリ**にあれば `configured=True`。中身は読まない |
| `[lints.clippy]` / `[workspace.lints.clippy]` | そのキーの値が `dict` であるときだけ「在る」とみなす |
| CI / pre-commit | `\bcargo(?:\s+\+\S+)?\s+clippy\b` に一致（大文字小文字を区別する。cargo のサブコマンドは小文字） |
| `clippy_config_paths` の順序 | リポジトリ相対パスの昇順 |

**`+toolchain` を挟む形を拾う。** `cargo +stable clippy` / `cargo +nightly clippy` は
rustup が正式にサポートする書き方であり、CI では普通に現れる。素朴な `cargo\s+clippy` は
これを取り逃がす。

**`render_row()` の文面**は既存 detector に揃える。

```
configured=True   → "clippy      configured"
configured=False  → "clippy      not configured (runs with defaults)"
```

括弧書きを足すのは、他の6ツールと違って**未設定でも動く**（D-16）という事実が、
この行だけ意味を変えるからである。

**コメント行の `cargo clippy` を除外しない。** `detect_ci` の既存の判定（`runs_lint` など）も
同じ regex 方式であり、ここだけ YAML を構文解析すると、同じリポジトリについて2つの規則が
違うことを言う。**近似であることを承知で既存の作法に揃える。**

**detector が読む manifest / config の集合は D-3 の候補と同じ**とする。すなわち `facts.all_files` から
basename が `Cargo.toml` のものを取り、`target` segment を除外したもの。`clippy.toml` /
`.clippy.toml` にも同じ `target` 除外を掛ける。除外規則を揃えないと、
**runner が無視した生成物の manifest を detector だけが「壊れている」と名指しする**という、
2つの決定が同じリポジトリについて違うことを言う状態が作れる。

#### `configured` が主張するのは「設定の存在」だけである

`clippy.toml` / `.clippy.toml` は**存在だけを見る**。中身の構文は検査しない。lint テーブルは
`[lints.clippy]` / `[workspace.lints.clippy]` のキーが在ることだけを見る。

> **detector が主張するのは「リポジトリから見える設定の指標」であって、「Clippy が実際に使う
> 設定」ではない。** 次は検出しない — ignored な `.clippy.toml`、`CLIPPY_CONF_DIR`、
> リポジトリ外の祖先にある config。名前が測っているものをこの範囲に留める。
>
> **これは Clippy 本来の探索規則の近似である。** Clippy は `CLIPPY_CONF_DIR`、
> `CARGO_MANIFEST_DIR`、cwd の優先順で親方向へ探索する。ebpy は環境変数を再現しないので、
> 「manifest の祖先にあるか」までを見る。**リポジトリのどこかに `clippy.toml` があれば
> 全部 `configured`」という素朴な形は採らない** — `tests/fixtures/` の中の1つが
> リポジトリ全体を「設定済み」にしてしまう。
>
> **Clippy の config file 自体は upstream で unstable と明記されている。** 2つのファイル名が
> 有効であることは公式に書かれているが、その仕組み全体に安定性の保証は無い。
> **中身を読まない設計はここでも効いている** — 存在だけを見るなら、内側の書式が変わっても
> detector は壊れない。§5.2 ではこの行を「契約（ただし upstream が unstable と明記）」として
> 扱い、lifecycle テストはサポート範囲の上端でも回す。

> **`[workspace.lints.clippy]` は、それだけでは member に効かない。** member 側に
> `[lints] workspace = true` が要る（Cargo Book, workspace lints）。本仕様は
> **実効性まで検査しない** — `configured` が主張しているのは「このリポジトリは clippy の設定を
> 持っている」という存在の事実であって、「その設定が全 member に効いている」ではない。
> 後者を主張したいなら名前を変えるべきであり、それは本仕様の範囲外である（*Names measure
> claims*）。

「Rust があるのに clippy が凍結されていない」という gap は `configured` からではなく、
**言語検出（D-3）と frozen roster から生成する**。条件は D-16 で定める。

> **根拠: 設計判断。** `Cargo.toml` があるだけで `configured` にすると、D-3 が分離した
> 「Rust が存在するか」と「clippy が設定されているか」が detector の中で再び混ざる。
> `ToolSetup.configured` が主張しているのは後者であり、前者を入れると名前が測っているものが
> ずれる（CLAUDE.md *Names measure claims*）。

### D-16. 未 ratchet の gap は「リポジトリ側の設定なしでも適用可能か」を条件にする

`_unratcheted_gaps`（`decide/diagnose.py:44`）の条件を広げる。

```python
# 現在
setup.configured and name not in roster

# 変更後（手続き全体。setup が無い場合のガードを落とさない）
for name in ANALYZERS_BY_NAME:
    if name in roster:
        continue
    setup = tool_setups.get(name)
    if setup is None:  # D-13 が言語で絞った結果、存在しないことがある
        continue
    detector = DETECTORS_BY_NAME[name]
    if setup.configured or (not detector.requires_repository_setup and detector.languages & languages):
        ...
```

**`setup is None` のガードを落としてはいけない。** D-13 の後、`tool_setups` は言語で絞られる
ので、**Python だけのリポジトリには clippy の setup が存在しない**。現行コードは
`tool_setups.get(name)` と `setup is not None` で明示的に守っている
（`decide/diagnose.py:54-56`）。条件式だけを差し替えると、そのガードが消えて
`AttributeError` になる。

変更後のシグネチャと gap を確定させておく。

```python
def diagnose(
    facts: RepoFacts,
    frozen_analyzers: tuple[str, ...],
    languages: frozenset[Language],
) -> Diagnosis: ...


def _unratcheted_gaps(
    tool_setups: dict[str, ToolSetup],
    frozen_analyzers: tuple[str, ...],
    languages: frozenset[Language],
) -> list[Gap]: ...
```

公開側の `diagnose()`（`decide/diagnose.py:140`）にも同じ `languages` が要る。D-13 の
`tool_setups` の絞り込みと D-16 の gap 条件が、どちらもこの値を使うためである。

- 回すのは `ANALYZERS_BY_NAME` のまま（ratchet できるのは analyzer だけ、という現在の理由は
  変わらない）。**analyzer 名から detector を引くのは `DETECTORS_BY_NAME[name]`** であり、
  registry は両者に同じ名前を使っている（`tools/registry.py:57`）。
- gap の形は既存と同じ — `id=f"unratcheted:{name}"`, `phase="tighten"`。
- `title` / `detail` は2通りに分かれる。

  | 経路 | title |
  | --- | --- |
  | `setup.configured`（既存） | `{name} is configured but not ratcheted` |
  | 言語由来（clippy） | `{name} can ratchet this repository but is not in the contract` |

- `ClippyDetector` は `DETECTORS` の末尾に置く。registry 順が CLI 全体の表示順であり
  （`tools/registry.py:61`）、既存6ツールの並びを動かさないためである。

`ToolDetector` に1つ足す（D-13 の `languages` と同じ場所）。

```python
@property
def requires_repository_setup(self) -> bool:
    """Whether ebpy requires repository-side setup before proposing this tool for ratcheting."""
```

- 既存の6 detector（ruff / ruff-format / mypy / pytest / vulture / secret-scan）→ `True`
- clippy → `False`

**`False` は clippy だけ**である。既存の detector はすべて「リポジトリがそのツールを採用した」
ことを確認してから提案する、という現在の挙動が変わらない。

> **これは ebpy の方針であって、ツールの性質ではない。** ruff も mypy も、設定ファイルが無ければ
> 既定の設定で動く — 「設定が無いと動かないツール」ではない。したがって
> `requires_repository_configuration` という名前に ruff で `True` を返させると、
> *Names measure claims* の観点でその主張自体が偽になる。
>
> この property が述べているのは ebpy 側の方針である — **ruff / mypy については、リポジトリが
> そのツールを採用したという setup を bootstrap / detector の経路で確認してから ratchet を
> 提案する**。clippy にはその確認段階が無い（provisioner を作らないと D-12 で決めており、
> リポジトリ側で採用する対象でもない）ので、言語の存在だけで提案してよい。
>
> **runtime の主張でもない。** clippy が実際に走るかは toolchain に component があるかにも
> 依るが、`diagnose` の時点でそれを probe してはいない（probe は D-5 の計測経路にある）。
> `runs_unconfigured` のような名前を避けたのはこのためである。

> **根拠: 実装読解。** D-15 が `Cargo.toml` を `configured` の根拠から外した結果、
> `clippy.toml` も lint table も持たない Rust リポジトリでは `configured=False` になり、
> 現在の条件では **gap が1つも出ない**。§2.4 が「混在リポジトリで最も価値を持つ」と書いた
> 場面がまさにこれである。
>
> **`configured` の一語で済ませられないのは、ebpy が提案してよい条件が2種類あるからである。**
> ruff / mypy については、リポジトリがそのツールを dev dependency として採用したことを
> bootstrap / detector の経路で確認してから提案する。clippy には採用という段階が無く
> （D-12 で provisioner を作らないと決めている）、Rust があれば直ちに提案してよい。
> `ToolSetup.configured` が主張しているのは「リポジトリがこのツールを設定した」であって
> 「ebpy がこのツールを提案してよい」ではない。両者が一致しないツールが現れたので、
> 条件のほうを分ける。
>
> **条件を単に「言語が一致すれば」に一本化してはいけない。** ruff が設定されていない Python
> リポジトリで「ruff is configured but not ratcheted」が出ることになり、しかも
> `ebpy freeze --analyzer ruff` は ruff が入っていないので失敗する。既存の
> 「Ruff is not configured」という bootstrap gap と重複したうえ、実行できない助言になる。

gap の文面も分ける。`configured` 由来は現在のまま、言語由来は「設定は要らないが天井が無い」と
いう別の事実を述べる。

---

### D-17. 契約が覆っていない範囲を ledger に記録する

D-6 の後退判定には「前回どこまで測れていたか」が要る。baseline のセルからは引けない
（0 件のセルは書かれない）ので、**契約の側に持たせる**。

```python
# models.py の State に1つ足す
unmeasured_packages: tuple[str, ...] = ()
```

```json
// .ebpy/state.json
"unmeasuredPackages": ["fuzz"]
```

**入るのは package のディレクトリであって、workspace root ではない。** 外れた workspace に
ついてはその全 member のディレクトリが、解決できなかった候補についてはその候補 manifest の
ディレクトリが入る（D-6）。**workspace root を入れると、root が覆う範囲が変わったことを
検出できない**（D-6 の「root ではなく package を数える理由」）。

**なぜ ledger であって baseline ではないか。** baseline はセルの入れ物であり、
`store/baseline.py` はそれ以外を知らない。一方 ledger は既に**契約の範囲**を持っている——
`frozen_analyzers` がまさに「どの analyzer がこの天井に寄与したか」である。
`unmeasured_packages` は同じ問いの package 版なので、**同じ場所に、同じ理由で置く**。

| | 覚えているもの | 答えられる問い |
| --- | --- | --- |
| `frozen_analyzers` | 天井に寄与した analyzer | この 0 は「測って 0」か「測っていない」か |
| `unmeasured_packages` | 契約が覆っていない package | この範囲は元から外か、外れたばかりか |

**schema version は上げない。** `_has_valid_v2_shape` は未知のキーを拒まない
（`store/state.py:154-166`。明示的に見ているのは退役した `counters` だけ）ので、キーの追加は
version 2 のまま読める。そもそも clippy は新規なので、このキーを持たない clippy の ledger は
存在しない——**移行は起きない**。

**未知のキーを受理することは、足した既知のキーを検査しない理由にならない。**
`unmeasuredPackages` は ledger の他のキーと同じ厳しさで検査する。

| 状態 | 扱い |
| --- | --- |
| 欠落 | `()`。これが既定であり、**エラーではない** |
| `list[str]` で、各要素が非空・重複なし・リポジトリ相対（先頭 `/` と `..` を含まない） | 受理 |
| それ以外（`list` でない / 要素が `str` でない / 重複 / 絶対パス） | **ledger 全体を不正**として扱う |

最後の行は `_valid_frozen_analyzers` と同じ形である（`store/state.py:125-131`）——
そちらも重複を弾き、要素の妥当性を要求し、外れれば ledger 全体を無効にする。
**契約を表すキーなので、部分的に読めるふりをしない。**

実測（この作業ツリーの `state_from_dict` を直接叩いた）:

| 入力 | 結果 |
| --- | --- |
| `state_to_dict` の往復 | 読める |
| **`unmeasuredPackages` を足したもの** | **読める** |
| `version: 3` | 弾く |
| `counters` を持つもの | 弾く |

**書くのは、計測が成功したうえで後退していないと決まったコマンドである**——
`freeze`、`freeze --force`、`prune`、**そして `check --write`**。後退しているときは書く前に
断る。計測しなかった、あるいは `Failed` だった run は**書かない**——これも「絶対と 0 は違う」
であり、走らなかった run からカウンタを書いてはならないという既存の規律と同じである。

**`check` を落としてはいけない。** `check` は既に state を書いており（`commands/check.py:188`）、
失敗時にも書くことがテストで固定されている
（`tests/test_check.py:449` `test_check_shell_persists_state_and_quality_even_after_a_failure`）。
`check` だけこのキーを書かないと、**契約が広がったことが記録されずに消える**。

```
1. freeze。fuzz が外れており ledger は {fuzz}
2. cfg を直す。check が完全計測する。今回の集合は {}
3. check が書かなければ ledger は {fuzz} のまま
4. cfg 不一致を再び入れる → {fuzz} ⊆ {fuzz} で check が通る
   → 一度測れていた範囲が、2度目は黙って消える
```

**広げる向きの更新は常に安全である。** 書くのは「今回の集合 ⊆ 契約の集合」と確かめた後
だけなので、書き込みで契約が狭まることはない。狭まる側は、その前に断っている。

##### 「state を書く」と「このキーを更新する」は別の話である

`check --write` は**失敗しても `decision.state` を書く**（`tests/test_check.py:449` が固定
している）。一方このキーは、計測が成功したときだけ置き換える。**混同しないよう分けて書く。**

| | いつ |
| --- | --- |
| `decision.state` の永続化 | 従来どおり。**結果が失敗でも書く** |
| `unmeasured_packages` の置換 | clippy が完全に計測でき、包含判定を通ったときだけ |
| 同、それ以外 | **以前の値をそのまま持ち越す**（`Failed` / `Unavailable` / 未計測） |

3行目が「絶対と 0 は違う」の適用である。走らなかった run の空集合で契約を上書きすると、
**測れなかったことが「何も外れていない」と記録される**。

##### scoped freeze はどう扱うか

`freeze --analyzer <name>` は指定した analyzer だけを測る。

| コマンド | `unmeasured_packages` |
| --- | --- |
| `freeze --analyzer ruff` / `mypy` | **触らない。** clippy を測っていない |
| `freeze --analyzer clippy` | 更新する（包含判定を通ったとき） |
| `freeze --force --analyzer clippy` | **書き直す。** 範囲を狭める正式な出口 |

**範囲を狭める出口は `freeze --force --analyzer clippy` でよい。** 契約を狭める操作が
`--force` を通ることは既に決まっており（`commands/freeze.py:204-208`）、clippy だけを
狭めたい利用者に全 analyzer の再 freeze を強いる理由が無い。

`report` は読むだけで書かない。

---

## 4. Clippy runner 仕様

```
workspace の発見 = rust_topology(cwd)（リポジトリにつき1回）          [D-3]
    候補 = repo 内の全 Cargo.toml（target/ 配下を除く、決定的順序）
           ただし .cargo-checksum.json が隣にある候補は最初から除く（vendored）
    未処理の候補 c ごとに（D-3 の2段階。コマンドは D-3 の擬似コードが正本）
        [1] cwd=(repo_root/c).parent
            cargo metadata --no-deps --format-version 1 --manifest-path <repo_root/c>
        [2] cwd=workspace_root  cargo metadata --no-deps --format-version 1
        cargo 実行ファイルが無い          → ClippyNotFoundError     → Unavailable
        metadata が非成功終了             → その候補を外す（unmeasured へ）
        **全候補**が非成功終了            → ClippyFailedError       → Failed("execution-failed")
        出力が JSON として読めない /
        workspace_root / workspace_members /
        packages / target_directory を欠く → ClippyInvalidOutputError → Failed("invalid-output")
        workspace_root が repo 外         → ClippyInvalidOutputError → Failed("invalid-output")
        [2] の workspace_root が [1] と違う → ClippyInvalidOutputError → Failed("invalid-output")
        member ID が packages[].id に
        ちょうど1件対応しない             → ClippyInvalidOutputError → Failed("invalid-output")
        member の manifest_path が repo 外 → ClippyInvalidOutputError → Failed("invalid-output")
        処理済みにするのは 候補 c 自身 / workspace_root/Cargo.toml /
        対応した全 manifest_path の3種（D-3 が正本）
    workspace_root で重複排除 → workspaces
    workspaces が空 → Unavailable("no Cargo workspace in this repository")

各 workspace について（cwd = workspace_root）:

    可用性:
        cargo clippy --version                                        [D-5]
        OSError は ClippyNotFoundError に変換     → Unavailable
        非ゼロ終了                                → Unavailable
        stdout が "clippy " で始まらない          → Unavailable（alias 対策）

    計測:
        cargo clippy --workspace --message-format=json \
            --target-dir <target_directory>/ebpy-clippy -- --cap-lints warn

        parse_clippy_output(result.stdout, result.stderr, result.code,
                            workspace=ws, repo_root=repo_root)             [D-6]
        （1 invocation = 1 call。複数 workspace の stdout を連結しない）

        行の切り分けと失敗の分類は D-6 の 1..5 の手続きに従う。
        **ここには再掲しない** — 順序が仕様なので、2箇所に書けば必ずずれる。

集約: D-6 の3段（発見 / probe / 計測）に従う。
失敗したビルドは D-6 の規則で「構成の不一致」と「本物の失敗」に分ける。
前者はその workspace を外し、UnmeasuredScope(root, 全 member のディレクトリ) を入れる。

**全 workspace を先に probe し、全て成功してから計測に入る。**
途中までコンパイルしてから Unavailable になる無駄を避けられる。

全 workspace の cells を **同じセルの count を加算して** 1 つの AnalysisMeasurement にする
（`merge_cells` は使わない。D-6）

セル化（すべて満たすものだけ）:                                        [D-7]
    reason == "compiler-message"
    level  == "warning"
    code   非 null
    is_primary == true の span が1つ以上ある
    → 位置は primary span のうち (file_name, line_start, column_start) 最小のもの
    → qualify_rule("clippy", code)                                    [D-8]
    → パスの処理は D-9 の 1..6 の手順に従う。**ここには再掲しない**   [D-9]

黙って捨てるもの:                                                      [D-7]
    compiler-artifact / build-script-executed / build-finished
    primary span を持たない message、code が null の message
    未知の level / reason

天井に載せられないパス:                                                [D-7/D-9]
    この invocation の out_dir のいずれかと同一かその子孫（絶対）
                                       → 黙って捨てる（生成物）
    それ以外で載せられないもの         → UnattributedFinding → incomplete
    ※ パスの問題で invalid-output にはしない。D-9 が正本
```

## 5. 根拠と確信度

### 5.1 反証済みの仮説（採用してはいけない設計）

**「span を持たない診断は失敗時にだけ出る」は誤りである。** Rust 1.79 は成功ビルドでも
span なし・code なしの warning を出す（1.85 で消えた）。rustc のドキュメントは
"This may be empty, for example for some global messages" と書いており、この仮説は最初から
成り立たない。

したがって「span が無い診断は失敗の副産物なので、失敗時にだけ気にすればよい」という設計を
採ってはいけない。D-7 は理由を問わず primary span または code を欠く message を捨てることで、
この仮説に依存しない形にしてある。

**「workspace の member は必ず workspace root の下にある」は誤りである。** 本仕様の前版は
`members = ["../sibling"]` だけを書いた fixture が cargo に拒否されるのを見て、この不変条件を
主張していた。**member 側の manifest に `package.workspace = "../ws"` を書き添えると cargo は
受理する**（cargo 1.96.0 で実測。D-3 参照）。Cargo のドキュメントは `package.workspace` について
まさにこの用途を挙げており、契約の側が先に答えを持っていた。

反証の副産物として、**root の外の member について clippy は絶対パスで報告する**ことも分かった。
「報告パスは `workspace_root` 相対」という観測（D-9）は、**member が root の下にある場合に限る**。

したがって `workspace_root` の containment 検査だけで済ませる設計を採ってはいけない。D-3 は
全 member の `manifest_path` を検査することで、この仮説に依存しない形にしてある。

**この2件は同じ失敗の仕方をしている。** どちらも「反例を1つ作って出なかった」ことを不変条件に
昇格させた。§5.3 が求めているのは版をまたぐ実測だが、この2件が示すのは**もう1つの軸**である —
**同じ挙動を引き出す別の書き方を探すこと**。`--all-targets` の有無、`package.workspace` の有無で
結論が変わった。

**「cargo-fuzz の workspace は plain な cargo clippy でビルドできない」は誤りである。**
tokio の `tokio/fuzz` が落ちるのを見て、`package.metadata.cargo-fuzz = true` を
「ビルド契約が別のツールに属する」ことの marker として使おうとした。**1例からの一般化であり、
実測が反証した。**

既定形の cargo-fuzz プロジェクト — 同じ marker、`libfuzzer-sys` 依存、独立 `[workspace]`、
親クレートの公開 API だけを呼ぶハーネス — を作って測ると、**普通にビルドできる**。

```
Compiling libfuzzer-sys v0.4.13
 Checking plainlib-fuzz v0.0.0
build-finished success = True
```

tokio が落ちる原因は `tokio/src/lib.rs` の `#[cfg(fuzzing)] pub mod fuzz;` という
**tokio 自身の設計判断**であって、cargo-fuzz が要求も推奨もしていない。marker は
「これは cargo-fuzz のプロジェクトである」しか申告しておらず、**ビルド可否について
予測力を持たない**。相関ですらなく、1例での同居である。

したがって marker で workspace を計測対象から外す設計を採ってはいけない。**計測できる
コードを理由なく天井から外すことになる。**

**「baseline にセルが無い範囲は、元々測れていない」は誤りである。** 後退を fail-closed に
する規則を、baseline のセルの有無で書いていた。`write_cells` は count が 0 のセルを落とす
（`store/baseline.py:120-136`）ので、**違反0件で測れていた workspace は、一度も測っていない
workspace と区別がつかない**。しかも 0 件は ebpy がリポジトリを追い込む行き先の状態である。

`models.py:268-271` のコメントが analyzer 軸で同じことを既に書いていた。**コードの側が先に
答えを持っていた**——2件目と同じ形の見落としである。D-17 で ledger に記録する形に改めた。

**「configured out の note は cfg 由来の失敗に必ず付く」は誤りである。** 隠された項目を裸の
パスで参照すると、1.79 と 1.85 は note を付けない（D-6 の表）。倒れる向きは安全側なので
規則は健全だが、**網羅的ではない**。「note が付かない ⇒ 本物の失敗」は成り立たず、正しくは
「note が付いた ⇒ 構成の不一致」の一方向だけである。

**この5件は同じ間違い方をしている。** どれも「反例を1つ作って出なかった」あるいは
「1例でそう見えた」ことを一般則に昇格させた。§5.3 が求めているのは版をまたぐ実測だが、
この5件が示すのはもう3つの軸である — **同じ挙動を引き出す別の書き方を探すこと**、
**反対向きの例を1つ作ってみること**、そして **その不変条件を既に扱っているコードが
無いか探すこと**。3件目は「既定形の cargo-fuzz プロジェクト」を1つ作るだけで、4件目は
`models.py` のコメントを1行読むだけで反証できた。

### 5.2 確信度一覧

| 主張 | 根拠の種類 | 確信度 |
| --- | --- | --- |
| JSON は stdout に出る | 契約（同梱の `cargo-check(1)`） | 高 |
| `reason` の値集合 | 契約（Cargo Book） | 高 |
| `build-finished.success` が存在する | 契約（Cargo Book） | 高 |
| `compiler-artifact.fresh` が存在する | 契約（Cargo Book） | 高 |
| `code` は null になりうる | 契約（rustc book） | 高 |
| `spans` は空になりうる | 契約（rustc book） | 高 |
| **workspace member でない**依存クレートはリントされない | 契約（`RUSTC_WORKSPACE_WRAPPER` = "for workspace members"）+ 実測 | 高 |
| clippy の成果物は build/check と別にキャッシュされる | 契約（同上）+ 実測 | 高 |
| repo 内 manifest が repo 外の `[workspace]` の member になりうる | 契約（Cargo manifest: the workspace field）+ 実測 | 高 |
| `cargo metadata --no-deps` が `workspace_root` / `workspace_members` / `target_directory` を返す | 契約（cargo metadata）+ 実測 | 高 |
| stdout に JSON 以外の行が混ざりうる（`{` 判定が回避策） | 契約（Cargo Book: JSON messages の Note） | 高 |
| 非 virtual workspace は `--workspace` 無しで member が落ちる | 契約（Cargo Book: package selection）+ 実測 | 高 |
| `--cap-lints warn` は deny を warning に戻し、コンパイルエラーは隠さない | 契約（rustc lint levels）+ 実測 | 高 |
| `build-finished` はビルドの最後に出る | 契約（Cargo Book） | 高 |
| `is_primary` が span の主従を表す | 契約（rustc JSON schema） | 高 |
| rustup は cwd に最も近い toolchain 設定を選ぶ（**上位の `+toolchain` / `RUSTUP_TOOLCHAIN` が無い場合**） | 契約（rustup overrides） | 高 |
| `cargo` は親方向に `Cargo.toml` を探索し、repo 外を lint しうる | 観測（1.96） | 中〜高 |
| `-- --cap-lints warn` は cargo のキャッシュを分ける | 観測（1.96） | 中 |
| `--all-targets` で lib 診断が2重になる | 観測（1.79 / 1.85 / 1.93 / 1.96） | 中〜高 |
| コンパイルエラーで `success:false` / exit 101 / 警告が消える | 観測（4版） | 中〜高 |
| 壊れた Cargo.toml → stdout 0 バイト / exit 101 | 観測（1.79, 1.96） | 中 |
| パスは workspace root 相対 | 観測（1.79, 1.96） | 中 |
| 再コンパイルされないユニットも診断を再出力する | 観測のみ | 中（D-10 でテスト固定） |
| component 未導入 → exit 1 / stdout 0 バイト | 観測（1.70）。文言は rustup 由来 | 低（文言に依存しない設計） |
| rustc は cfg で外された項目の参照に `found an item that was configured out` の note を付ける | 観測（1.79 / 1.85 / 1.96 で note の文字列が一致。error 本文は変わる） | 中〜高 |
| ただし**裸のパス**で参照した場合、1.79 / 1.85 は note を付けない（1.96 で付く） | 観測（3版。`crate::` 付き・`use` 文とも対照） | 中〜高 |
| `aborting due to N previous errors` は **spans が空**。それ以外の error は primary span を持つ | 観測（1.79 / 1.85 / 1.96 × 12 fixture） | 中〜高 |
| `compile_error!` は `code: None` で、primary span を**持つ** | 観測（3版） | 中〜高 |
| workspace の下にある非 member の manifest（`exclude` されていない `vendor/*`）は metadata が exit 101 | 契約（Cargo: source replacement / workspaces）+ 観測（3版） | 高 |
| 同じ manifest を `exclude` すれば metadata が成功する | 観測（1.79 / 1.96） | 中〜高 |
| `cargo vendor` は各 crate に `.cargo-checksum.json` を書く | 契約（cargo vendor）+ 実測（実際に vendor した） | 高 |
| member の manifest が壊れると**ルートの** metadata も落ちる | 観測（1.96） | 中〜高 |
| default feature を外すと、ビルドは成功したまま cfg 配下の警告だけが消える | 契約（Cargo features / Rust Reference: conditional compilation）+ 観測（1.96） | 高 |
| その note は cfg の種類を問わず出る | 観測（`fuzzing` / `feature` / `target_os` × モジュール / 関数を 1.79 / 1.85 / 1.96 で確認） | 中〜高 |
| error code では構成の不一致を判別できない | 観測（綴り間違いも `E0433`。関数を隠すと `E0425`。3版で一致） | 高 |
| Rust 1.79 は `code: None` の error（`aborting due to …`）を余分に出す | 観測（1.79。**成功・失敗を問わず全ケースで出る**） | 高 |
| span なし診断は失敗時のみ | **反証済み（1.79）** | — |
| `--remap-path-prefix` が診断パスを書き換える | 契約（rustc）+ 実測（1.96 で相対→相対・絶対・親の3形。相対→相対は 1.79 / 1.85 でも一致） | 高 |
| build script の生成コードは `build-script-executed.out_dir` 配下の絶対パスで報告される | 契約（`out_dir` は絶対パス）+ 実測（1.79 / 1.85 / 1.96 で一致） | 高 |
| `rust-toolchain.toml` の固定は計測の失敗原因にならない（rustup が自動導入する） | 実測（未インストールの 1.61.0 を指定して `clippy 0.1.61` が返った） | 中 |
| 通常成功時の cargo-clippy は exit 0 | 契約（cargo の終了ステータス）+ 実測（1.79 / 1.85 / 1.96 で、警告あり・警告なし・`[lints.clippy] all="deny"` + `--cap-lints warn`・生成コード警告ありの4条件とも exit 0） | 高 |
| workspace member は必ず root の下にある | **反証済み（`package.workspace` を書けば受理される）** | — |
| `package.metadata.cargo-fuzz` はビルド不能の marker になる | **反証済み（既定形の cargo-fuzz プロジェクトは plain な clippy で建つ）** | — |
| 報告パスは常に `workspace_root` 相対 | **限定つき**（root の下の member に限る。外の member は絶対パス） | 中 |

### 5.3 実測の扱い

単一バージョンの観測は「反例が出ていない」以上の意味を持たない。複数ツールチェインで同じ実験を
回せば安く反証できる（§5.1 がその例）ため、**実測を根拠にするときは最低でもサポート範囲の
両端で回す**。

#### サポート範囲を定義する

「両端」と言う以上、範囲そのものが決まっていなければならない。

| | |
| --- | --- |
| 下限 | **Rust 1.79** — 本仕様の実測で下端として使った版 |
| 上限 | その時点の stable |
| CI matrix | 上の2点 |

下限を 1.79 に置くのは、`[lints]` テーブル（1.74 で安定）と `build-finished` がどちらもそれより
古く、**実際に end-to-end で確かめた最古の版が 1.79 だから**である。1.70 も使ったが、それは
「clippy component が無い」ケースの再現のためだけで、正常系は通していない。

**この下限は変えてよい決定である。** 変えるときは、§5.2 で「実測」を根拠にしている行を
新しい下限で回し直すこと — それが範囲を宣言する理由である。

#### この範囲は「件数が同じ」の保証ではない

**天井の再現には同じ Rust toolchain が要る。** Clippy は toolchain と一緒に出荷され、
版が上がれば lint が増え、lint group の構成も変わる。Cargo と Clippy の CI ガイド自身が、
toolchain の更新で警告が増えて CI が落ちうるので pin を検討せよと案内している。

| 保証すること | 保証しないこと |
| --- | --- |
| 1.79〜stable で runner と parser が動く（互換性試験） | 版をまたいで件数が同じになること |

**版差は実際に観測できる。** 同じ fixture で `build.rs` 自体の診断が版によって変わった。

```
rust 1.79   clippy::needless_borrows_for_generic_args  ['build.rs']   ← 出る
rust 1.85   （出ない）
rust 1.96   （出ない）
```

lint そのものが消えたわけではなく、この形に対して発火しなくなっている。**天井が
「その toolchain で見えた違反」であることの、最も分かりやすい例**である。

**未 pin の `stable` が上がって新しい lint が出たときは、新規違反として fail-closed する。**
これは誤動作ではなく ratchet の設計どおりの振る舞いである — 天井は「その toolchain で見えた
違反」を意味する。`rust-toolchain.toml` で pin するかどうかは、そのリポジトリの判断に属する。

---

## 6. 実行コスト

- `cargo clippy` は**フルビルドではない**。通常の library / binary target については
  `cargo check` 相当で、**最終的なコード生成を省く**。
  **「コード生成もリンクも一切無い」ではない** — build script と proc-macro は実行するために
  実際にビルドされるので、それらを持つリポジトリでは追加のコストが乗る。
- **workspace member ではない依存クレート**は、コンパイルはされるがリントはされない。
  `RUSTC_WORKSPACE_WRAPPER` が workspace member にしか掛からないという契約と、
  **`cargo clippy` がその wrapper を使うという観測**の組である（D-10 と同じ）。
  **path dependency が workspace member でもある場合、その member はリントされる** —
  D-5 は `--workspace` を渡すので、そもそも計測対象である。天井が自分のコードだけを覆う、
  という性質はこの区別の上に成り立つ。
- 初回のみ依存のメタデータ生成に分単位の時間とネットワークを要する。
- **言語検出は cargo を起動しない**（D-3）。cargo が動くのは clippy が scope に入ったときだけ。
- **cargo の起動回数** = `2P + 2W`。`P` は [1] に入った未処理候補の数（D-3 の2段階 metadata）、
  `W` は workspace の数（可用性プローブと計測が各1回）。全候補数を `C` とすれば上限は `2C + 2W`。
  `metadata --no-deps` と `--version` はコンパイルを伴わないので、**支配的なのは計測の回数**である。
- **専用 `--target-dir` の分ディスクを使う。** `-- --cap-lints warn` がキャッシュを分けるため
  （D-5）、ebpy は `<target_directory>/ebpy-clippy` を使う。開発者の `cargo clippy` との相互
  無効化は消えるが、ebpy 側の初回は必ず cold になり、target ディレクトリの容量が増える。
- **`--locked` も `--offline` も渡さない。** したがって `ebpy check` が
  **`Cargo.lock` を作成・更新し、依存を取得する**ことがある。読み取りだけのつもりの
  コマンドがネットワークとファイルへの副作用を持つ、という点を承知のうえで採る。
  `--locked` を既定にすると、**`Cargo.lock` をコミットしないライブラリクレートでは計測が
  常に失敗する** — 天井を持てないリポジトリを作るほうが害が大きい。lockfile を固定したい
  リポジトリは、CI で `--locked` 付きの `cargo fetch` を先に回せばよい。
- `check` / `report` / `freeze` / `prune` が毎回これを行う。`util.run` にタイムアウトは無い
  （`util.py:23`）。
- **`ebpy check` は常に完全計測する。** 速いパスのために計測を間引くと、間引いた分が「ゼロ」に
  なる。CI では必須ゲートとして cargo のキャッシュ前提で回し、**pre-commit へは自動で追加せず、
  利用者の opt-in にする**。ローカルのコミットごとに workspace 分の cargo を起動するのは、
  ゲートとしての価値に対して代償が大きい。

---

## 7. 実装順序

### #1 スコープ化

`Language` 型 + `Analyzer.language` + `repo/detect/language.py`（`has_python` /
`has_rust` / `detect_languages`。cargo には触れない）+ `decide/analyzer_scope.py`（`ScopeDecision` と
言語→analyzer の射影）+ `measure_repository(cwd, scope)` + **D-14 の `scope-mismatch`**。
`store/ceiling_artifacts.reconcile_scope` は `ScopeDecision.mismatch()` に移す。

`scope-mismatch` をここに置くのは、これが clippy 固有ではなく**スコープ化そのものが新しく
生み出す状態**だからである。clippy を登録する前に、既存の ruff / mypy だけでこの状態を作って
テストできる。
既存挙動が Python リポジトリで不変であることをテストで固定する。
**これが先でないと #3 で既存リポジトリが壊れる。**

`measure_repository` の**製品コードでの**呼び出しは4箇所である。加えて**テストに直接呼び出しと
monkeypatch の stub が多数ある**ので、シグネチャ変更はそれらも更新対象になる。`prune` と `report` は現在 `read_config` を
import すらしていないので、`ScopeDecision` の入手経路を新たに与える必要がある。

| 呼び出し箇所 | 渡すもの | 照合（D-4） |
| --- | --- | --- |
| `commands/check.py:188` | `decision.to_measure` | する（fail-closed） |
| `commands/freeze.py:332` | **global は `decision.global_freeze_scope`**。`--analyzer X` のときは `{X}` | する。`--force` global のみ除外 |
| `commands/prune.py:194` | `decision.to_measure` | する（fail-closed）。**新規** |
| `commands/report.py:51` | `decision.to_measure` | する。**断らず名指し**。**新規** |

**`global_freeze_scope` を渡すのは global `freeze` だけである。** 「同上」と書くと
`prune` と `report` にも広がるが、それは D-4 の設計と逆になる — frozen な clippy の
`Cargo.toml` が消えたリポジトリで、`report` は clippy を**測らずに** `scope-mismatch` として
表示すると決めている。`global_freeze_scope` を渡すと測りに行ってしまう。

テストで固定すること:

- **fresh + config での初回 global freeze が通り、`declared` がそのまま契約になる**
- config 由来のスコープで `declared != frozen` なら計測前に断る（現行の完全一致の維持）
- 検出由来のスコープで `(frozen ∩ registered) ⊆ detected_analyzers` は通り、
  そうでなければ断る
- fresh + 空 scope は4コマンドとも断る
- frozen + 空 scope は `freeze` / `check` / `prune` が断り、`report` は断らず `scope-mismatch`
  を表示する（D-14）
- **config 由来の不一致を `report` が両方向とも `scope-mismatch` にすること**（D-14）
  - `declared = {ruff, mypy}` / `frozen = {ruff}` → mypy が `scope-mismatch`（宣言されたが未 freeze）
  - `declared = {ruff}` / `frozen = {ruff, mypy}` → mypy が `scope-mismatch`（凍結されたが未宣言）
  - 後者だけを通す実装（`frozen - to_measure`）にならないことを、前者のケースが固定する
- `ScopeDecision` の照合が**順序に依存しないこと** — 射影が registry 順、`frozen_analyzers` が
  ソート済みでも一致と判定される（D-4）
- **fresh + config の `report` が `scope-mismatch` を出さないこと**（D-14）
- **config 無しの `freeze --force` が既存の契約を縮めないこと** — `frozen={clippy}` /
  `Cargo.toml` 無し / config 無しで `--force` しても clippy が契約に残る（D-4）
- **その `freeze` で clippy が `no-runner` ではなく `Unavailable` になること** — 契約にする集合を
  実際に計測している、という D-4 の要求の回帰テスト
- **未知の frozen analyzer が `no-runner` のままであること** — `frozen=("pylint",)` で
  `scope-mismatch` にならない。既存の `tests/test_check.py:373` と
  `tests/test_freeze.py:350` を壊さないことの確認でもある
- **`scope-mismatch` かつ `incomplete` な analyzer の unattributed banner が Markdown に
  残ること**（D-14）
- **invalid artifacts + global `freeze --force` が計測へ進むこと**、および
  **invalid artifacts + `freeze --force --analyzer X` が断ること**（D-4 の前提順序。
  既存の復旧経路を塞いでいないことの回帰テスト）
- **fresh + 空 scope の `report` は断り、frozen + 空 scope の `report` は断らないこと**（D-4）
- **invalid ledger の古い `frozen_analyzers` が、global `--force` の scope に継承されないこと**
  （`scope_decision` に渡す state が `_previous_state()` の戻り値であることの回帰テスト）
- **Python だけのリポジトリの `diagnose` が、clippy の setup が無くても例外にならないこと**
  （D-16 の `setup is None` ガードの回帰テスト）
- **`.pyi` だけのリポジトリで ruff と mypy が scope に入ること**（D-1 の互換性の回帰テスト）

### #2 clippy runner + parser + 単体テスト

registry に未登録のまま。テストに含めるもの:

- clippy JSON のパース（セル化 / 黙って捨てる / 拒否 の3分岐）
- `{` で始まらない行の無視、`{` で始まるが読めない行の `invalid-output`
- `build-finished` の欠落・重複 → `invalid-output`
- primary span の選択（複数 primary、primary なし）
- **error の `spans` / `children` が段4で拾われていること** — 拾わない実装では D-6 の
  分類が常に「本物の失敗」に倒れ、tokio 型が救えない
- **error の `spans` / `children` の型が壊れていても `invalid-output` にならないこと**
  — 分類は `False` に倒れ、`execution-failed` のまま（D-6）
- rule ID の往復 — freeze 経路に加えて **`ebpy log --rule clippy:clippy::needless_return`**
- パスの前置と containment:
  判定は「セル化」「黙って捨てる」「unattributed」の3つ。**どれも `invalid-output` にしない。**

  - `crates/a/../shared/src/lib.rs`（実在する）→ **セル化**（`crates/shared/src/lib.rs`）
  - `../shared/src/lib.rs`（先頭の `..`。前置後に repo 内へ収まり実在する）→ **セル化**
  - `<out_dir>/gen.rs`（build script の生成コード）→ **黙って捨てる**（セルにも
    unattributed にもしない）
  - `crates/a/../../../shared/src/lib.rs` → リポジトリ外なので **unattributed**
  - `/etc/passwd.rs`（POSIX 絶対、`out_dir` の外）→ **unattributed**
  - `C:\outside\file.rs`（drive path）→ **unattributed**
  - `C:foo.rs`（drive-relative。両 flavour の `is_absolute()` が False）→ **unattributed**
  - `//server/share/x.rs`（UNC）→ **unattributed**
  - `foo/..`（正規化すると空になる）→ **unattributed**
  - **nested workspace（`workspace_root = crates/a`）で `foo/..` → unattributed**。前置後に
    1回だけ畳む実装だと `crates/a` が通ってしまうので、これが2段階正規化の回帰テストになる
  - `..` および `../foo/..`（畳むと `..` が残り、ファイルを指さない）→ **unattributed**
  - `shadow/lib.rs`（リポジトリ内に見えるが実在しない）→ **unattributed**（手順6）
  - `code` が `"\n"` の message → `invalid-output`（`qualify_rule` の `ValueError` を
    漏らさないことの回帰テスト）

実 cargo を使う統合テスト。**skip 条件は「cargo が無い」ではなく
「`cargo clippy --version` が成功しない」**とする — minimal な rustup プロファイルでは cargo は
あっても clippy component が無い（Rust 1.70 で再現済み）。

- **非 virtual workspace で全 member が測られること**（`--workspace` の回帰テスト）
- **`[lints.clippy] all = "deny"` のリポジトリが freeze できること**（`--cap-lints` の回帰テスト）
- **リポジトリ外の `[workspace]` の member である manifest を拒否すること**（D-3 の回帰テスト）
- **`workspace_root` は repo 内だが member が repo 外にある workspace を拒否すること**
  （D-3 の回帰テスト。member 側に `package.workspace` を書いた fixture。この形は cargo が
  受理し、clippy が絶対パスで報告するため、metadata の member containment 検査でしか止まらない）
- `[workspace] exclude` された独立 package が拾われること
- **`vendor/*/Cargo.toml` を持つリポジトリで、本体 workspace が計測できること**
  — ルート workspace + `exclude` 無しの vendored manifest。前版は全体 `Failed` だった。
  **実 cargo が要る**（metadata が exit 101 になる構成でなければ回帰にならない）
- **`exclude = ["vendor"]` + `.cargo-checksum.json` を持つ vendored 依存が候補に入らないこと**
  — この構成では metadata が**成功する**ので、候補から外さないと独立 workspace として
  素の clippy を掛けてしまう。依存が feature 前提なら全体 `Failed` になる
- **vendored 依存のセルが1つも天井に載らないこと** — 直せないコードに天井を持たない（D-3）
- **vendored 依存が `unmeasuredPackages` に入らないこと** — 入れると `cargo vendor` で
  依存が1つ増えるたびに `check` が後退と誤認する（D-3）
- **workspace member は `.cargo-checksum.json` があっても候補から外れないこと**
  — marker を見るのは、どの workspace にも属さなかった候補についてだけ（D-3）
- **全候補の metadata が失敗したら `Failed` になること** — 「外して続行」が
  `Measured(cells={})` に化けないことの回帰テスト。**ここが最も落としやすい**
- **member の manifest が壊れた workspace が `Failed` になること** — cargo がルートの
  metadata も落とすので全候補が落ちる。「外して続行」が破損を隠さないことの回帰テスト
- **metadata が落ちた候補について、候補 manifest のディレクトリが `root` と `packages` の
  両方に入ること** — `workspace_root` は存在しない（D-6）。`None` を入れる実装だと落ちる
- 複数 workspace を持つリポジトリでの前置
- **`RUSTFLAGS=--remap-path-prefix=src=shadow` を掛けた計測が、セルを作らず
  `incomplete` になること**（D-9 の手順6 の回帰テスト。実 cargo が要る）
- **build script が生成したコードの警告が、報告された `out_dir` の配下として黙って捨てられ、
  計測が成功すること**（D-9 の手順2 の回帰テスト。実 cargo が要る）
- **2つの workspace が同じ `.rs` を参照する構成で、`ValueError` にならず加算されること**
  （`merge_cells` をそのまま使わないことの回帰テスト）
- 候補が相対パスのまま cargo に渡らないこと — nested な `crates/a/Cargo.toml` で
  metadata が成功する（`--manifest-path` の絶対化の回帰テスト）
- **virtual workspace（root に `[package]` が無い）で、root manifest が処理済みになり
  二度 probe されないこと**（D-3。無限ループの回帰テスト）
- 未知の `level` を持つ message が、`code` や `spans` が壊れていても `invalid-output` に
  ならないこと（D-6 の段階的検査の回帰テスト）
- **`success=false` かつ error level の `rendered` があるとき、その detail が引用されること**
  （非 warning を早く捨てると失われる。D-6 の段3の回帰テスト）
- **`success=true` かつ `returncode != 0` が `execution-failed` になること**（D-6 の判定4）
- **`code` object が壊れているが primary span を持たない message が、捨てられるだけで
  `invalid-output` にならないこと**（D-6 の段10 の回帰テスト）

追加の回帰テスト:

- **gitignore された `Cargo.toml` だけを持つ混在リポジトリで clippy が scope に入らないこと**
  — 意図した非対応であることを契約として固定する（D-3 の universe）
- **`compiler-message` が対応する `build-script-executed` より先に現れる stdout で、生成コードが
  正しく捨てられること** — 1パス実装に戻ると落ちる（D-9 の2パス構成）
- **`out_dir` が `\` 区切りでも包含判定が一致すること**、および **`…/out` が `…/outside.rs` を
  巻き込まないこと**（D-9 の `out_dir` 正規化と segment 境界）
- **NUL 文字を含む `file_name` / symlink のループ / 読めないディレクトリで、生の例外が parser の
  外へ出ず `unattributed` になること**（D-9 の手順6）
- **`diagnose` → `freeze` → 再 `diagnose` なしで `QUALITY.md` の marker が消えること**
  （D-16 の roster 再フィルタ）
- **`.ipynb` だけのリポジトリで ruff が scope に入ること**（D-3 のマーカー）
- **`freeze` が断るときの `_refusal_reason` に "syntax" が現れないこと** — 利用者が読む主経路

**構成の不一致と本物の失敗を分ける回帰テスト**（D-6）:

| 与える状況 | 期待 |
| --- | --- |
| cfg で隠されたモジュールを参照（`E0433` + note） | その workspace を外す。全体は `Measured` |
| cfg で隠された関数を参照（**`E0425`** + note） | 同上。code で判定していないことの回帰 |
| 綴り間違い（`E0433`、note 無し） | 全体 `Failed`。**外してはいけない** |
| 型エラー（`E0308`） | 全体 `Failed` |
| cfg 由来と型エラーが同居 | 全体 `Failed`。1つでも note 無しがあれば本物の失敗 |
| Rust 1.79 で cfg 由来の失敗 | 外す。spans が空の `aborting due to …` を数に入れていないこと |
| **cfg 由来と `compile_error!` が同居** | 全体 `Failed`。`code` で絞ると 1.79/1.85 で外れてしまう回帰 |
| **裸のパスで隠された項目を参照（note 無し）** | 全体 `Failed`。網羅的でないことを契約として固定する |

**後退を fail-closed にすることの回帰テスト**（D-6）:

- **元々外していた workspace（ledger の `unmeasuredPackages` に載っている）は外して続行し、
  `check` が通ること** — tokio の形
- **違反0件で測れていた workspace が測れなくなったら `check` が断ること**
  — freeze したあとに `cfg` ゲートを足す2段階のテスト。**ここが最も重要**。
  **baseline にセルを1つも作らない fixture で書く** — セルの有無で判定する実装に戻ると落ちる
- **違反ありの workspace が測れなくなった場合も断ること** — 同じ規則が両方を覆うこと
- **その `check` が、天井を失うセルと2つの出口（cfg を直す / `freeze --force`）を
  名指しすること**
- **`prune` も同じ条件で断ること** — 天井を触るので `check` と同じ
- **`freeze --force` は通り、`unmeasuredPackages` が書き直されること** — 意図的な復帰路
- **crate を削除しても断らないこと** — 「測った root」を覚える実装に戻ると落ちる
- **外していた workspace が測れるようになったら断らず、`unmeasuredPackages` から消えること**
- **その更新を `check --write` も行うこと** — freeze / prune だけが書く実装だと、
  cfg を直して `check` が通ったあと再び壊したときに**2度目が黙って通る**（D-17）
- **`check` が失敗しても `decision.state` は書かれ、かつ `unmeasured_packages` は
  以前の値を持ち越すこと** — 既存の
  `test_check_shell_persists_state_and_quality_even_after_a_failure` を壊さず、
  走らなかった run の空集合で契約を上書きもしないこと（D-17）
- **`freeze --analyzer ruff` が `unmeasured_packages` を触らないこと** — clippy を
  測っていない run が clippy の契約を書き換えない（D-17）
- **`default = ["extra"]` → `default = []` で `check` が断らないこと**
  — 守れる粒度が package までであることを**契約として固定する**（§2.5）。
  「守れるはず」と誤解した実装がここを塞ごうとすると、`prune` の存在意義を壊す
- **外れた workspace に member が増えたら `check` が断ること**
  — `members = ["fuzz"]` / `exclude = ["core"]` で freeze し、`core` を member に移す。
  **workspace root は変わらないので、root の集合で比べる実装は通してしまう**。
  D-17 が package を数える理由の回帰テスト
- **`report` は断らず、後退を表示し、backlog に baseline を持ち越すこと**
  — `complete` のまま prune する実装だと、後退したセルが backlog から消える
- **同じ `.rs` を2つの workspace が測っていて片方が外れたとき、`check` が断ること**
  — セル単位で見る実装だと `prune_cells` が 2→1 に下げて素通りする
- **`Failed` に終わった run が `unmeasuredPackages` を書かないこと** — 走らなかった run から
  契約を書かない
- **clippy が契約に無いリポジトリでは、後退しても `check` が通ること**
  — `frozen=("ruff","mypy")` + Rust 同居 + cfg 不一致。既存の
  `test_a_non_contract_analyzer_is_named_but_never_gates`（`tests/test_check.py:134`）と
  同じ規律。**この条件を落とすと Python リポジトリが Rust を理由に落ちる**
- **`unmeasuredPackages` が `list[str]` でない / 重複する / 絶対パスの ledger を、
  ledger 全体として不正にすること** — 欠落は `()` でエラーにしない（D-17）
- **外した workspace が `report` / `check` / `freeze` の出力に現れること**（`diagnose` には
  出さない — 計測しない層だから）
  — 黙って落ちない

**D-3 の失敗分類を固定する3ケース**（`except Exception` 的な実装に潰されないため）:

| 与える状況 | 送出される例外 | 期待する observation |
| --- | --- | --- |
| `cargo` 実行ファイルが無い | `ClippyNotFoundError` | `Unavailable` |
| cargo はあるが metadata が非成功終了 | `ClippyFailedError` | `Failed("execution-failed")` |
| metadata の出力が構文・構造として不正 | `ClippyInvalidOutputError` | `Failed("invalid-output")` |
| `workspace_root` が repo 外 | `ClippyInvalidOutputError` | `Failed("invalid-output")` |

**混在リポジトリで cargo が無いとき、ruff と mypy が測れること**も固定する（D-3）。

集約の3段（D-6）も固定する:

- 2つの workspace のうち片方だけ probe が通らない → 全体 `Unavailable`（`Failed` ではない）
- 両方 probe は通り、片方の計測が失敗 → 全体 `Failed`
- **発見の段が失敗すれば probe に到達しないこと** — 壊れた `Cargo.toml` の候補と、
  clippy component が無い workspace が同居するリポジトリで、返るのは発見の失敗のほう
- stdout が `plain text\n` だけのとき `execution-failed`（`invalid-output` ではない。
  D-6 の判定順の回帰テスト）
- 不正な型の JSON 行が `success=true` と同居するとき `invalid-output`
- 壊れた `Cargo.toml` を含むリポジトリで、`ClippyDetector.configured` が `False` に丸められず
  gap として名指しされること（D-15）

### #3 registry への登録 + clippy detector

detector は clippy の設定だけを見る（D-15）— `clippy.toml` / `.clippy.toml` / lint table /
CI・pre-commit の `cargo clippy`。`Cargo.toml` の存在は根拠にしない。
「Rust があるのに clippy が未凍結」という gap は言語検出と frozen roster から作る。

あわせて diagnosis 側を整える。

- D-13 の絞り込み — `ToolDetector.languages`（既存6 detector への付与を含む。`GitleaksDetector`
  は空集合）、`diagnose()` の引数追加、`render/report.py:21` の `KeyError` 対応
- D-16 の gap 条件 — `ToolDetector.requires_repository_setup`、`_unratcheted_gaps` の
  書き換え、言語由来 gap の文面
- 回帰テスト: **`clippy.toml` を持たない Rust リポジトリで clippy の unratcheted gap が出ること**、
  および **ruff が未設定の Python リポジトリでは ruff の unratcheted gap が出ないこと**

**後退の fail-closed（D-17）もここに入れる。** `unmeasured` を生むのは clippy だけなので、
登録される前は動かしようがない。

- `State.unmeasured_packages` + `state_from_dict` / `state_to_dict` の `unmeasuredPackages`
  （schema version は据え置き。D-17）
- `check` / `prune` の断り（後退したときだけ）、`freeze --force` の書き直し、
  `report` の backlog 持ち越し
- **`check --write` もこのキーを更新する**（`commands/check.py:188` は既に state を書く）。
  freeze / prune だけが書く実装だと、契約が広がったことが記録されずに消える
- **書くのは計測が成功したコマンドだけ**。`Failed` / `Unavailable` の run は書かない

### #4 Python 専用サブコマンドのガード

§2.1 の「拒否（新規）」4件（D-11）。

### #5 lifecycle テストとドキュメント更新

- `tests/test_clippy_lifecycle.py`（D-10）
- `docs/measurement-seam.md` の該当4箇所 — `measure_repository(cwd)` returns one frozen
  `Measurement` のシグネチャ、構造図の `├── ruff` / `└── mypy`、"Ruff and mypy are the two
  analyzers in the initial implementation."、"## Independent capabilities — Ruff and mypy are
  attempted independently."
- `docs/measurement-seam.md` の「Command shape」節の順序図に**スコープ計算の段が無い**ので追加する。

  ```
  read and classify CeilingArtifacts
    → 前提条件
    → [スコープ決定 + 照合]
    → measure_repository
    → 純粋な決定
    → 永続化
  ```

- `CLAUDE.md` の陳腐化を直す。現在 *the per-tool runners are `measurement/_ruff.py` and
  `measurement/_mypy.py`* と書かれているが、実際には `tools/ruff/_runner.py` と
  `tools/mypy/_runner.py` であり、`measurement/` にこの2ファイルは存在しない。本仕様の作業とは
  独立だが、直さないと次の設計も同じ場所を間違える（D-1 の初稿が実際に誤った）。
- `commands/log.py:24` の `RULE_HINT` に clippy の例を足す（D-8）。
- `tools/registry.py:61` のコメント *Order matches DETECTORS* は、clippy が detector を持ち
  provisioner を持たない（D-12）時点で不正確になる。並びの対応が1対1でなくなることを書き足す。
- `docs/cli/report.md:95` の `report --json` のスキーマ説明。現在は `status` の値に
  `scope-mismatch` と `no-runner` が無く、`unattributedTotal > 0` は `incomplete` のときだけ
  という書き方になっている。D-14 の後は **`scope-mismatch` かつ unattributed** があり得るので、
  各フィールドを status ではなく**背後の observation**に基づいて説明する形に直す。
- `docs/cli/*.md` の残り。
- **`docs/measurement-seam.md` の status 一覧**（`report --json` の説明）に `no-runner` が
  **すでに欠けている**。D-14 の後は `scope-mismatch` も欠ける。両方足す。
- `docs/measurement-seam.md` の「invalid は計測前に必ず断る」も、global `freeze --force` が
  例外であることを書き足す（D-4 の前提順序）。これは本仕様が作る例外ではなく、
  既存の復旧経路が文書に反映されていなかった箇所である。
- **「Python 専用ツール」と読める既存の文面**を、Rust を測れるようになった事実に合わせる。
  スコープを広げすぎないよう、対象は次に限る。

  | 場所 | 現在の文面 |
  | --- | --- |
  | `src/ebpy/cli.py:1` / `:71` | *make a Python codebase that can only get better* |
  | `src/ebpy/__init__.py:1` | 同上 |
  | `pyproject.toml` の `description` | *Make an existing Python codebase one that can only get better* |
  | `README.md:5` | 同上 |

- `src/ebpy/generate/workflows.py` の `gate_workflow` docstring は *There is no raw `ruff check`
  or `mypy` step* と ruff / mypy を名指ししている。**seam の言葉に置き換える** — 生成物そのもの
  は変えない（Rust CI の生成は §2.6 の範囲外）が、docstring が主張しているのは
  「生の lint ステップを置かない理由」であって、その理由は analyzer の名前に依存しない。
  registry に analyzer が増えるたびに docstring が古くなる形を残さない。

---

## 8. 決定済みの運用方針

| 項目 | 決定 | 反映先 |
| --- | --- | --- |
| この文書の扱い | **日本語のまま、コミットせずに設計用の文書として保持する。** `docs/` の正本群（英語）には加えない | — |
| pre-commit に載せるか | `ebpy check` は常に完全計測する。CI では必須ゲート、pre-commit への自動追加はせず利用者の opt-in にする | §6 |
| `--all-targets` | v1 では使わない。重複除去と `cfg(test)` の coverage 契約を設計してから別変更で導入する | D-5 / §2.6 |
| `[workspace] exclude` の穴 | `cargo metadata` を採用して塞ぐ。ratchet の「黙ってゼロにしない」という核に直接関わるため、既知の穴として出荷しない | D-3 |
| 専用 `--target-dir` | 採用する。`cargo metadata` の `target_directory` 配下に `ebpy-clippy/` を作る | D-5 / §6 |
| 構成の不一致と本物のビルド失敗 | **rustc の `found an item that was configured out` note で分ける。** 前者はその workspace を外し、後者は従来どおり全体を `Failed` | D-6 |
| 外した範囲の天井 | **ledger が覚えている「外した root」の集合に収まれば続行、はみ出せば fail-closed。** 復帰は意図的な `freeze --force`。天井を黙って持ち越さない | D-6 / D-17 |
| 契約が覆っていない範囲の記録 | ledger に `unmeasuredPackages` として持つ。**baseline のセルの有無では判定できない**（0件のセルは書かれないため） | D-17 |
| 発見できたが解決できない manifest | **その root を外して続行する。** ルートが正常にビルドできるリポジトリを計測不能にしない。ただし**1つも計測できなければ `Failed`** | D-3 / D-17 |
| vendored な依存のソース | **候補にしない**（`.cargo-checksum.json` が隣にある manifest）。依存はリントしないという契約に従う。直せないコードに天井を持たない | D-3 |
| 守れる粒度 | **package まで。** default feature を変えて item がコンパイル対象から外れる形の縮小は**守らない** — 「直した」と「構成から外れた」が1回の計測では区別できない。ruff の `exclude` と同じ既存の限界 | §2.5 |

未決事項は無い。
