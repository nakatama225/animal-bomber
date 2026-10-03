# Python 版への指示

[リポジトリ共通の指示](../AGENTS.md) を先に読んでください。ここには
Python 版に固有のものだけを書いています。

## パッケージ管理

uv を使います。`uv.lock` を手で編集しないでください。`pyproject.toml` と
`uv.lock` は必ずペアでコミットします。

## 検査

```sh
uv run tools/verify.sh   # ruff → ruff format --check → mypy --strict → lint-imports → pytest（3.12 と 3.11）
```

各段階はこれが通ることを完了の条件にしています。pytest は 3.12 のあと、3.11 でも走らせます
（`uv run --isolated --python 3.11 pytest`。試合の結果が Python の版で変わらないことを見るため）。

## 描画の重さ

`uv run python tools/bench_render.py` で、いちばん重い場面の描画時間を測れます。
窓は開きません（SDL の dummy ドライバで描きます。`tests/tools/test_bench_render.py` が確かめています）。
合格基準は `tools/bench_gate.py`、測った結果と経緯は README の Design Choice にあります。

- 測定は描画の層（`src/animal_bomber/presentation/`）を import せず、自前の場面
  （`tools/bench_scene.py`・`bench_particles.py`・`bench_sprites.py`）を描いています。描画の層で
  毎フレームの描き方（貼る絵の作り方・半透明の掛け方・描く数など）を変えたら、先にそれらを
  同じ描き方に直してから測り直し、README の数字も直してください。描き方を数えるテスト
  （`tests/tools/test_bench_scene.py`）は失敗するので、その数も直します。描画の層ができたら（段階 7）、
  測定をその層を通して描く形に替えます
- 合否は次の決め方で出してください。ほかの重い処理を止めて 3 回走らせ、3 回とも判定に使う値
  （出力のいちばん下の「判定：」で始まる行に出ます）がしきい値（8.33 ms）以下なら合格。1 回でも
  超えたら、ほかの重い処理を止めて 5 回測り直し、中央値で決めます。回ごとに表の頭の負荷
  （load average）と時刻を残してください（`tools/bench_render.py` の冒頭と同じ）
- ⛔ 画素ごとの透明を持つ薄れる絵（爆風の芯・光の玉など）を、貼るたびに `set_alpha` で
  薄めないでください。重く、しきい値を超えた回がありました。貼るたびに薄めるのと同じ整数の
  不透明度ごとに薄めた絵を先に作っておき、薄めずに貼ります（`tools/bench_sprites.py` の `faded`）。
  段を粗くして丸めると見た目が変わります。例外は回りながら浮かぶ顔で、回した絵を毎フレーム
  作り直すので、貼るときに薄めています（測定の場面も同じ。数が少ないので重さに効きません）
- ⛔ 窓の面へ直接描かないでください。アルファの桁の無い面に描き、窓の面へは 1 フレームに
  1 回だけ貼ります（合否はこの形で測って決めました。窓の面がアルファの桁を持つ形式だと、
  直接描く形は重くなります）
- ⛔ 描く面をマス 60px より大きくしないでください。大きい窓では、描いた面を拡大して出します。
  上げるなら測り直してください（マス 96 は、3 回測った四角い粒と光の玉の p99 の 6 つのうち 5 つが、
  しきい値を超えました）

## フレームの間の待ち方

`uv run python tools/bench_pacing.py` で、フレームを回す輪（`src/animal_bomber/shell/loop.py`）の
待ち方を比べて測れます（窓は開きません。2 分半ほど）。決め方は `tools/bench_pacing_rule.py`、
測った結果と経緯は README の Design Choice の 7. にあります。

- 既定の待ち方（`frames` の `wait`）を変えるときは、測り直して README の数と決めも直してください。
  `tests/shell/test_loop.py` の `test_既定の待ち方は_測って決めた空回り` は既定の関数だけを見るので
  失敗します。そのテストの期待と名前も新しい既定に直し、ここで名前を指している所も直します
- いまの決め（空回り。CPU のコアを1つ使い続ける）は仮です。窓を開く段階（段階 4）で、vsync も
  候補に入れ、CPU の使用率の上限を足した決め方を、測る前に書いてから、窓を通して測り直します。
  区切りの並べ方も、隣り合う組がそろう形に替えます（`tools/bench_pacing.py` の「並べ方」）
- 空回りの間、ほかの Python のスレッドは GIL の受け渡しを待たないと動けません（`shell/loop.py`）。
  通信の受信をスレッドで書く段階（9）では、裏のスレッドが目を覚ますまでの遅れも決め方に入れて測ります

## 層の依存方向

```text
app → shell → presentation → net → ai → content → domain
```

逆向きの import を追加しないでください。

`pyproject.toml` の `[tool.importlinter]` の層の検査は `exhaustive = true` にしてあり、
ここに並べていないディレクトリを `animal_bomber/` の直下に作ると失敗します
（`net` を `network` と作った、など）。まだ作っていない層は括弧で囲んであります（`"(ai)"` など）。
**層のディレクトリを作ったら括弧を外してください。** 括弧のままだと、あとでその層の
ディレクトリを消しても黙って通ります。
ルールと同じく結果を決める層（`content`・`ai`）を作ったときは、「ルールの層は乱数・実時間・
描画・環境で結果が違いうる計算を import しない」の `source_modules` にも足してください。

## `domain/` の中で使ってはいけないもの

- **import**：`pygame` / `random` / `secrets` / `uuid` / `time` / `datetime` / `numpy` / `cmath`。
  乱数と時刻は引数として渡す。識別子は `core/entity_id.py` の `IdSource` で連番を取る
- **`os` の一部**：`urandom`・`getrandom`・`times`
- **`math` の一部**：三角関数・双曲線関数・指数と対数の関数・累乗と立方根・誤差関数・
  ガンマ関数（一覧は `tests/boundary/banned_names.py` の `MEMBERS_BANNED`）と、`hypot`・`dist`
  （結果の最後の桁が環境で違いうる）。`math.sqrt`・`math.floor`・`math.ceil` と四則演算は使ってよい
- **set の反復**。文字列の set は取り出し順がプロセスごとに変わるため、
  同じ入力でも結果が変わる。順序が要る場所は list を使う
- **組み込みの `hash()`・`id()`**。`hash()` は同じ理由で、`id()` はオブジェクトの番地を返すので、
  起動ごとに値が変わる。要約は `core/statehash.py` で作る
- **小数の丸め（`round`）**。Python は偶数丸めのため他言語と結果が食い違う。
  体力は整数で持つ
- **`**` と `pow()`**。小数の累乗は `math.pow` と同じ C の `pow` を通る。指数が整数でも同じ
  （`x ** 2` ではなく `x * x` と書く）。整数の定数どうし（`2**32`）だけは使ってよい
- **`sum()`**。小数の合計の出し方が Python 3.12 で変わり、3.11 と値が違う。
  整数か小数かを検査で見分けられないので、どちらも `for` で1つずつ足す

import は `import-linter` と `ruff` で、組み込みの関数と `**` は `tests/boundary/test_builtins.py`
（構文木を走査する）で検査しています。**検査の設定を緩めないでください。**
ruff の禁止（TID251）は全体に掛け、使ってよい層（`presentation`・`shell`・`app`）と
テスト・補助のスクリプトだけを `per-file-ignores` で外しています。外す先を増やすときは、
その層で乱数や実時間が要る理由を設定の横に書き、`test_builtins.py` の `EXEMPT_LAYERS` も揃えてください
（食い違うと `test_外す層は_ruffの禁止を外す層と同じ` が失敗します）。

禁じるものの一覧は `tests/boundary/banned_names.py` の `MODULES_BANNED`（import そのものを
禁じる。ruff と import-linter の両方）と `MEMBERS_BANNED`（中の一部を禁じる。ruff だけ）が
正です。禁止を足す・外すときは、`pyproject.toml` の2か所とこの一覧を同じく変えてください。
食い違うと `test_guards.py` の `test_設定の禁止は_この一覧と等しい` が失敗します。
`test_guards.py` は、違反したファイルを書き出して本物の検査コマンドが失敗することも確かめています。

set の反復は、import でも構文木でも止められません。`tests/determinism/test_hashseed.py` が、
台本どおりの試合（`tests/determinism/scenario.py`）を文字列の hash の種を変えた2つの
プロセスで走らせて突き合わせます。ルールの層に処理を足したら、台本がその処理を通るように
台本も足してください（台本が通らない処理の set の反復は、ここでは見つかりません）。

## 時刻と記録

- ⛔ 操作の記録と通信の時刻に、盤面の時刻（`world.now`。型は `Tick`）を使わないでください。
  試合通算の時刻（`MatchTick`）を使います。型が違うので、盤面の時刻をそのまま渡すと mypy が
  失敗します（理由は `domain/core/tick.py` の `MatchTick`）
- ⛔ `MatchTick(world.now)` と書かないでください（包むと mypy は通ります。段階 1 では2つの時刻が
  いつも同じ値なので、テストの値でも見つかりません）。`src/` の中で `MatchTick(...)` を呼んでよいのは、
  試合通算の時刻を数える `MatchClock`（`domain/core/tick.py`）と、記録を文字列から戻す所
  （`net/input_log.py` の `_decode_entry`）だけです。ほかで呼んだり、`MatchTick` を値として使ったり
  すると `tests/boundary/test_match_tick.py` が失敗します。試合を進める側は `MatchClock` を持ち、1 tick 進め終えたら `advance()` を呼びます
  （フレームを回す輪は数えません。理由は `shell/loop.py`）。呼んでよい場所を足すときは、そのテストの
  `ALLOWED` に足し、理由を書いてください
- `tests/determinism/test_golden.py` は、台本どおりの試合の状態の要約を固定値と比べます。
  ルールを変えて試合の結果が変わったら失敗します。変わることが意図どおりなら値を出し直して
  書き換え、なぜ変わったかをコミットに書いてください。意図していなければ、値を書き換えずに
  原因を探してください。3.12 と 3.11 で値が違ったら、ルールの層の誤り（版で値が変わる計算）です

## docstring と docs

- docstring は PEP 257 の例と同じ形にします。要約は開きの引用符と同じ行に1行で書き、
  複数行なら要約の下を1行空け、閉じの引用符は単独の行に置きます。関数・クラス・モジュールは
  ruff（D205・D209・D212）が、定数や項目の下の docstring は `tests/boundary/test_docstrings.py` が
  見ます
- `docs/` の Markdown に書いた REPL の例（`>>>` の行）は、pytest が走らせて値を確かめます。
  ルールを変えて値が変わったら、例の値も直してください

## 動物の能力を追加するとき

能力と行動中の状態は、取りうる種類を閉じた union で定義します（段階 5 で作ります）。
追加すると、対応を書き忘れている分岐が型検査（mypy の `exhaustive-match`）で失敗します。
戻り値を返さない `match` でも失敗するよう、`pyproject.toml` で有効にしてあります。
**失敗した箇所を潰してから完了としてください。**`match` の分岐に
catch-all（`case _:`）を足して黙らせないでください。
