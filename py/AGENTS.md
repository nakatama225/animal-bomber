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

`uv run python tools/bench_render.py` で、いちばん重い場面を本物の描画の層（`Renderer`）で描いて、
描画時間を測れます。窓は開きません（SDL の dummy ドライバで描きます。`tests/tools/test_bench_render.py` が
確かめています）。場面は `tools/bench_match_scene.py`、合格基準は `tools/bench_gate.py`、測った結果と
経緯は README の Design Choice 1. にあります。

- 描画の層で毎フレームの描き方（貼る絵の作り方・半透明の掛け方・描く数・場面の揺れ方など）を変えたら、
  測り直して README の数字も直してください。場面が貼る数を数えるテスト
  （`tests/tools/test_bench_match_scene.py`）が失敗したら、その数も直します
- 段階 0 の測定（描画の層を作る前に、代わりの絵で描いた場面）は `tools/bench_scene.py`・
  `bench_sprites.py`・`bench_particles.py` に残してあります。フレームの間の待ち方の測定
  （`tools/bench_pacing.py`）がこの場面を描きます。README の段階 0 の数字はこの場面で測ったものなので、
  場面を変えないでください
- 合否は次の決め方で出してください。ほかの重い処理を止めて 3 回走らせ、3 回とも判定に使う値
  （出力のいちばん下の「判定：」で始まる行に出ます）がしきい値（8.33 ms）以下なら合格。1 回でも
  超えたら、ほかの重い処理を止めて 5 回測り直し、中央値で決めます。回ごとに表の頭の負荷
  （load average）と時刻を残してください（`tools/bench_render.py` の冒頭と同じ）
- ⛔ 画素ごとの透明を持つ薄れる絵（爆風の芯・光の玉など）を、貼るたびに `set_alpha` で
  薄めないでください。重く、しきい値を超えた回がありました。貼るたびに薄めるのと同じ整数の
  不透明度ごとに薄めた写しを作っておき、薄めずに貼ります（`render/sprites.py` の
  `SpriteCache.faded`）。段を粗くして丸めると見た目が変わります。例外は回りながら浮かぶ顔で、
  回した絵を毎フレーム作り直し、薄めた形の絵にしてから重ねます（数が少ないので重さに効きません）
- ⛔ 窓の面へ直接描かないでください。アルファの桁の無い面に描き、窓の面へは 1 フレームに
  1 回だけ貼ります（合否はこの形で測って決めました。窓の面がアルファの桁を持つ形式だと、
  直接描く形は重くなります。`app/main.py` の `run` と `app/shell.py` の描く面）
- 試合の画面の毎フレームの描き方（盤面を盤面の四角で切って描き、盤面の四隅を枠の角丸で切る
  小さい絵の4枚と、横の板の1枚と時計の数字の1枚を貼る）と横の板の中身の組み方は、
  `render/match_frame.py` の `draw_match_frame` と
  `panel_content` にまとめてあり、遊ぶときの窓（`app/match_view.py`）・窓の高さ
  （`app/main.py` の `tallest_panel`）・描画の重さの場面（`tools/bench_match_scene.py`）が
  同じ関数を呼びます。描き方を変えるときはこの関数を変えてください（場面も同じく変わります）。
  呼ぶ側に描く処理を書き足さないでください（場面と遊ぶときの描き方が分かれます）。場面の外の
  物（ポーズの幕・通信対戦の案内の帯）を盤面に重ねるときは、重ねたあとに `BoardFrame.cover` で
  四隅を貼り直します（`app/match_view.py`。原型の canvas の中身と同じく、四隅で切れて見える）。
  ただし幕を重ねたフレームの案内の帯のあとは貼り直しません（幕のぼかした絵は枠もぼかしてあるので、
  ぼけていない四隅が浮いて見える）
- ラウンドの幕と優勝の幕の間は、描画の重さの場面の対象の外です。幕を出した最初のフレームだけ
  盤面と横の板を描いてぼかし（`render/overlay/banner.py`。マス 60 で約 12 ms）、2フレーム目
  からは盤面と横の板を描かずに、ぼかした絵とカードだけを貼ります（`app/match_view.py` の
  `MatchView.draw`）。幕の間にも盤面を描く形に戻すなら、場面に幕を足して測り直してください
- ⛔ 描く面をマス 60px より大きくしないでください（`render/layout.py` の `TILE_MAX`）。上げるなら
  測り直してください（段階 0 の測定で、マス 96 は、3 回測った四角い粒と光の玉の p99 の 6 つのうち
  5 つが、しきい値を超えました）。pygame の SCALED は整数倍でしか広げないので、拡大するのは、画面の
  縦が窓の 2 倍以上あるときだけです。それより小さい画面では、窓は描く面と同じ大きさ（マス 60 で、
  盤面 1454×1094 のまわりに枠 3px を付け、すき間 16px と横の板 238px を足した 1714×1100。窓の高さは
  枠を付けた盤面と横の板の高いほうで、画面の 9 割で頭打ち）です。原型はマス 96 まで広げるので、
  大きい画面では盤面が原型より小さくなります（2560×1440 相当でマス 60 と 69、3840×2160 を等倍で
  使うとき 60 と 96）。整数でない倍率で広げる設定は、実機の窓で見た目と重さを検証してから決めて
  ください（`app/main.py` の `window_layout`）

## 絵と音（`src/animal_bomber/presentation/`）

どこまで原型を逐語に写し、どこを作り直したかは `docs/08-絵と音.md` にあります。

- 試合の状態は読むだけにしてください。書き換えると、画面を出したときだけ試合が変わります
  （`tests/presentation/test_render_match.py` が、描く前と後で状態の要約が変わらないことを見ます）。
  試合の乱数（`world.rng`）も引きません
- 見た目の乱数は `presentation/cosmetic_rng.py` の `CosmeticRng` から引いてください。`random` を
  直に使わないでください。テストは原型が引いた値の列を差して、同じ順・同じ数だけ引くかを見ます
  （画面の揺れ → 爆風 → 被弾の揺れの順。`art/frame.py` の `draw_frame` と `render/renderer.py`）
- 描く関数（`render/art/`）は、原型の canvas の命令の列と同じにします。命令・値・見た目の乱数を
  引く順を変えると `tests/presentation/test_legacy_art.py` が失敗します。毎フレームはそれを
  取っておいた絵（`render/baked/`）を貼って描き、手本の `draw_frame` と画素で比べます
  （`test_renderer.py`）。描く順を変えるときは、`draw_frame` と `Renderer` を同じく変えます
- 薄れる絵は、原型の `globalAlpha` と同じく塗る命令ごとに薄めます。命令が重なる絵をまとめて
  薄めると、重なった所の色が原型と違います（命令1つずつの絵を薄めて重ねるか、canvas の不透明度を
  下げてから描き直して取っておく）。落とし穴にはまったプレイヤーの不透明度の戻し忘れ（原型の
  不具合）も写してあります。`PlayerSprites.draw` が返す不透明度を、次のプレイヤーと炎と葱へ
  渡してください（外周の鍋は不透明度を自分で決めるので渡さない）
- 取っておく絵の段の数（`PULSE_LEVELS` など）を変えるときは、ずれの上限のテスト
  （`tests/presentation/test_quantization_bounds.py`）と、取っておいた絵の検査（`test_baked*.py`）も
  直します。段の数は、先にずれの上限を決めてから出します（定数の docstring に上限を書く）
- 試合の状態に無い見た目だけの値（粒子・画面の揺れ・歩いた距離・被弾の揺れ・粘膜爆弾を投げた
  位置・炎の通った跡・1つ前の tick の値）は、`render/scene/` の `SceneTracker` が 1 tick ごとに
  数えます。1つ前の tick の値は、ゲーム速度が整数でないときに描く値を混ぜるためのもので、盤面に
  いるプレイヤーの位置・外周の位置・歩いた距離・舌先までの長さ（`TrackedMotion`）・飛ぶ葱の位置
  （`leek_before`）・粘膜爆弾の飛んだ tick（`flown_before`）・粒子の位置と寿命（`ParticleLook.previous`）
  です。盤面が進んだ tick にだけ進め、ラウンドが替わったら忘れます。ルールの層に、見た目のためだけの
  値を足さないでください（足すなら、見分けに要るイベントを足します。`domain/events.py` の決まり）
- 描く関数の時刻の引数（`now`）は、盤面の時刻の tick の数を小数で受け取ります。ゲーム速度が整数で
  ないときは、1つ前の tick から割合だけ進んだ時刻（`render/views/player.py` の `drawn_time`）を渡す
  ので、時刻から出す値を tick の整数として扱わないでください（取っておく絵は段に丸めた値ごとにし、
  丸めずに取っておく値は tick の整数に切ってから出す。`art/items.py` の溶けた割合）。状態が期限で
  持つ値（無敵・撃つ間隔）は期限と描く時刻から出し、残りの tick の数で持つ値は `drawn_left` で
  描く時刻の値にします（残りを決めた tick と 0 には足さない。同じファイル）
- 原型の命令の列の固定値（`tests/presentation/legacy_art_ops.json`）・音の表の固定値
  （`legacy_sound_values.json`）・粒子の固定値（`legacy_particles.json`）は、原型を node で
  読み込んで書き出したものです。手で直さず、リポジトリのいちばん上で書き出し直してください。
  どれも何度作っても同じものになります

```sh
node py/tools/legacy_oracle/legacy_art.js py/tests/presentation/legacy_art_ops.json
node py/tools/legacy_oracle/legacy_sound.js py/tests/presentation/legacy_sound_values.json
node py/tools/legacy_oracle/legacy_particles.js py/tests/presentation/legacy_particles.json
```

## フレームの間の待ち方

`uv run python tools/bench_pacing.py` で、フレームを回す輪（`src/animal_bomber/shell/loop.py`）の
待ち方を比べて測れます（窓は開きません。2 分半ほど）。決め方は `tools/bench_pacing_rule.py`、
測った結果と経緯は README の Design Choice の 7. にあります。

- 既定の待ち方（`frames` の `wait`）は眠る（`sleep_until`）です。測る前に書いた決め方では空回りが
  選ばれましたが、遅れの上限 2 ms を外して眠るにしました（理由は README の 7. と `shell/loop.py`）
- 既定を変えるときは、README の数と決めも直してください。`tests/shell/test_loop.py` の
  `test_既定の待ち方は_眠る` は既定の関数だけを見るので失敗します。そのテストの期待と名前も新しい
  既定に直し、ここで名前を指している所も直します
- ⛔ 既定を空回り（`spin_until`）に戻さないでください。待つ間も CPU のコアを1つ使い続け、ほかの
  Python のスレッドも GIL の受け渡しを待たされます。遊べる段階で動きが引っかかって見えたら、
  先に原因（描画の重さか、待ちの遅れか）を測ってから決めます

## 層の依存方向

```text
app → shell → presentation → net → ai → content → domain
```

逆向きの import を追加しないでください。

`pyproject.toml` の `[tool.importlinter]` の層の検査は `exhaustive = true` にしてあり、
ここに並べていないディレクトリを `animal_bomber/` の直下に作ると失敗します
（`net` を `network` と作った、など）。まだ作っていない層は括弧で囲んであります（`"(content)"` など）。
**層のディレクトリを作ったら括弧を外してください。** 括弧のままだと、あとでその層の
ディレクトリを消しても黙って通ります。
ルールと同じく結果を決める層（`content`・`ai`）を作ったときは、「ルールの層は乱数・実時間・
描画・環境で結果が違いうる計算を import しない」の `source_modules` にも足してください。

`domain/` の中の向きは検査していません。次の3つは守ってください。

- `domain/query/` は読むだけです。状態を書き換えず、`domain/systems/` を import しません
  （CPU の判断（`ai/`）も同じ問い合わせを使うため）
- 1 tick の処理は `domain/systems/` に処理ごとのモジュールとして置き、`simulation.py` の
  `step()` に順に並べます。並びは原型の update と同じで、プレイヤーごとに済ませる処理は
  1人ぶんの関数（`move_player`・`place_for` など）として出し、`step()` のプレイヤーごとの
  輪の中で呼びます。並べる順の理由は `simulation.py` のモジュールの説明に、並びと同じ
  番号で書いてください。並びを変えたら `tests/systems/test_tick_order.py`（原型を測った
  答え）が失敗するので、原型の並びと食い違っていないかを確かめてください
- 動物の技（`domain/abilities/`）は、`domain/systems/` の基本の操作（爆発させる・傷つける・
  アイテムを効かせる・爆弾を置く）を呼びます。`domain/systems/` から `domain/abilities/` を
  import してよいのは、技を呼び分ける `actions.py` と盤面の物を進める `actors.py` だけです
  （ほかから import すると、読み込みが循環します）。`domain/state/` は `domain/abilities/` を
  import しません（振る舞いと盤面の物の状態は `state/` に、振る舞いは `abilities/` に置く）

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
  試合通算の時刻を数える `MatchClock`（`domain/core/tick.py`）と、文字列から時刻を読み戻す所
  （記録の `net/input_log.py` の `_decode_entry` と、通信で届いたメッセージの `net/protocol.py` の
  `_Fields.tick`）だけです。ほかで呼んだり、`MatchTick` を値として使ったり
  すると `tests/boundary/test_match_tick.py` が失敗します。試合を進める側は `MatchClock` を持ち、1 tick 進め終えたら `advance()` を呼びます
  （フレームを回す輪は数えません。理由は `shell/loop.py`）。呼んでよい場所を足すときは、そのテストの
  `ALLOWED` に足し、理由を書いてください
- `tests/determinism/test_golden.py` は、台本どおりの試合の状態の要約を固定値と比べます。
  ルールを変えて試合の結果が変わったら失敗します。変わることが意図どおりなら値を出し直して
  書き換え、なぜ変わったかをコミットに書いてください。意図していなければ、値を書き換えずに
  原因を探してください。3.12 と 3.11 で値が違ったら、ルールの層の誤り（版で値が変わる計算）です

## 通信対戦（`src/animal_bomber/net/`）

- メッセージの約束の表（種類と項目の名前）は、中継サーバ（`server/`）の
  `animal_bomber_server.protocol` を import して使います。この版に写さないでください。
  種類や項目を足すときは、中継の表と TypeScript 版の `ts/src/net/protocol.ts` を同じく変え、
  この版の型（`net/protocol.py`）にも足します。食い違いは `tests/net/test_protocol.py`
  （この版と表）と `server/tests/test_protocol_sync.py`（TypeScript 版と表）が見つけます
- 人間のプレイヤーの窓口（`NetworkInputSource`）は `LockstepDriver` が作って試合に繋ぎます
  （試合は `create_session` で作らせる）。⛔ 自分のプレイヤーにキーボードを直に繋がないで
  ください。自分の手元でだけ操作が早く試合に入り、試合がずれます
- 抜けたプレイヤーを CPU に替える tick は、記録の `InputLog.replaced_at` だけで決めます
  （本物の端末と記録の流し直しが、同じ tick で替わるため）。替わる判定をほかに足さないで
  ください
- この層はソケットを持ちません（中継とつなぐ実物は `shell/relay_link.py`）。テストは中継の
  代わり（`tests/net/fake_relay.py`）で何台ぶんでも同じプロセスの中で動かします。本物の中継を
  立てるテストは `tests/relay_server.py` を使い、待つ所には必ず制限時間を置きます
- 画面の流れ（`app/shell.py` の `Shell`）は、1台の試合も通信対戦も `app/runner.py` の
  `MatchRunner` の形で回します。⛔ 入力が揃っていない tick を進めないでください
  （`ready` を見る）。押してすぐ離したキーを忘れる `keyboard.end_tick()` は、進めた tick の
  あとにだけ呼びます（進めなかったフレームで呼ぶと、押したことが読まれないまま消えます）。
  例外は、1台の試合をわざと止めている間（ポーズ・ラウンドの幕・決まった試合。
  `MatchRunner.stopped`）と試合の外の画面で、そのときは原型と同じく毎フレーム忘れます
  （忘れないと、ポーズ中に押した爆弾のキーで、再開した最初の tick に爆弾を置く）。通信対戦の
  `stopped` はいつも False です

## docstring と docs

- docstring は PEP 257 の例と同じ形にします。要約は開きの引用符と同じ行に1行で書き、
  複数行なら要約の下を1行空け、閉じの引用符は単独の行に置きます。関数・クラス・モジュールは
  ruff（D205・D209・D212）が、定数や項目の下の docstring は `tests/boundary/test_docstrings.py` が
  見ます
- `docs/` の Markdown に書いた REPL の例（`>>>` の行）は、pytest が走らせて値を確かめます。
  ルールを変えて値が変わったら、例の値も直してください

## イベント（`domain/events.py`）

- ルールの層から音・画面・通知を呼ばないでください。起きたことは `SimEvent` の種類に足して
  `step()` の戻り値で返し、音と通知に変えるのは `presentation/presenter.py`、粒子と画面の揺れに
  変えるのは `presentation/render/scene/effects.py` です
- 種類を足すと、`presentation/presenter.py` と `presentation/render/scene/effects.py` の
  `match` と、TypeScript 版と比べるテストの `event_row`（`tests/ts_rows.py`）が mypy で
  失敗します。扱いを書いてから完了としてください。`case _:` には `assert_never` だけを置きます
- TypeScript 版と比べる固定値（`tests/systems/test_simulation_ts.py`・
  `test_techniques_ts.py`・`tests/app/test_session_ts.py`）は、同じコミットの TypeScript 版
  （`ts/`）の `domain/` と `app/GameSession.ts` を写し、この版にまだ無いものを止めて、同じ
  台本を流して出したものです。TypeScript 版を直したら、その形を写して出し直します。ルールの
  層で止めているものは、いまはありません（段階 7 まで止めていた葱ボンと延長戦は、段階 8 で
  入れたので、写しも試合の設定の既定どおり入れます）。
  もう1つ、写しでは全員が下を向いて始まる形にします（この版は原型と同じく全員が下を向く。
  TypeScript 版は下の隅のプレイヤーが上を向く）。写しには、振る舞いの中身を文字列にする関数
  （`debugEncode`）も足します（TypeScript 版の振る舞いは中身を外へ見せないため）。
  行の形（`tests/ts_rows.py`）を変えるときは、写しの台本の行の形も同じく変え、変える前の形で
  いまの固定値と1字も違わず出せることを確かめてから出し直します（台本の写し違いと、振る舞いの
  違いを分けるため）。
  段階 4 までは、段階のコミットにあとからの直しを当てて出していましたが、段階 5 で、その
  間に入った名前の置き換え（696e1f9）と葱ボン・延長戦（段階 8）のために直しが当たらなく
  なったので、直しが全部入った HEAD から出す形に替えました。
  段階を進めて出し直すときは、その段階で入る仕組み（葱ボン・延長戦など）を写しで止める
  のをやめ、止めたものと理由をテストの説明に書いてください
- CPU の固定値（`tests/ai/test_cpu_ts.py` が読む `tests/ai/ts_cpu_values.json`）も同じ形で
  出します。写すものに `ai/` を足し、CPU だけの試合を流して、tick ごとの入力と 100 tick ごとの
  盤面を出します。CPU の判断の規則・順・乱数を引く順のどれかを変えると失敗します。写しの
  CPU で止めているものはありません（外周の操縦と、飛んでくる葱をよける規則も写しのまま動かす）。
  4つ目の試合（葱ボンと延長戦）は決定性の台本の `play_cpu_negibon_match` と同じ試合で、
  種と長さは `scenario.py` の定数を両方が読みます
- `tests/boundary/test_closed_kinds.py` は、試合を進める処理（`domain/systems/`）・盤面への
  問い合わせ（`domain/query/`）・イベント（`domain/events.py`）・CPU の共通の判断（`ai/` の
  うち戦い方の `tactics.py` 以外）に、動物の名前と振る舞い・
  盤面の物のクラスの名前が現れないことを見ます。コメントも含みます。名前を書かずに種類を
  見分ける書き方（`action_name`・`actor_name`・`encode_action`・`encode_actor`・
  `isinstance`・`hasattr`・`getattr`）も失敗にします。共通の処理は種類を
  見ず、性質（`state/actions.py` の `traits_of`・`rules/animals.py` の数値）だけを見ます。
  逸話を書くときも、動物の名前を出さず能力で書いてください（「ブロックを通り抜ける動物」）。
  外周の処理（`systems/negibon.py`）も、葱（盤面の物）の種類を書きません。葱を作るのは
  `state/actors.py` の `shot_from_lane`、外周を閉じるときに消すかは同じファイルの
  `ends_with_lanes`（性質）です（`domain/abilities/` を import せずに済ませるため。
  `docs/09-葱ボンと延長戦.md`）。盤面の CPU が飛んでくる葱をよける規則（`ai/behaviors.py`）も、
  葱かどうかを同じファイルの `lane_shot` に聞きます
- `tests/systems/test_match_invariants.py` は、試合を通して崩れない約束（同じマスにアイテムが
  2つ並ばない）を毎 tick 確かめます。約束を崩す仕組みを足すときは、約束のほうから決め直して
  ください

## 動物の能力を追加するとき

動物（`domain/rules/animals.py` の `Animal`）・プレイヤーを乗っ取る振る舞い
（`domain/state/actions.py` の `Action`）・盤面の物（`domain/state/actors.py` の
`Actor`）は、取りうる種類を閉じた列挙と union で定義しています。種類で分ける所は
`match` で書き、最後に `assert_never` を置いています（振り分けは
`domain/abilities/techniques.py` にまとめてあります）。追加すると、対応を書き忘れている
分岐が型検査（mypy の `exhaustive-match`）で失敗します。戻り値を返さない `match` でも
失敗するよう、`pyproject.toml` で有効にしてあります。
**失敗した箇所を潰してから完了としてください。**`match` の分岐に
catch-all（`case _:`）を足して黙らせないでください。

- 数値の違い（速さ・火力・体力・爆弾の数・アイテムの倍率・とくぎの長押し）は
  `rules/animals.py` の `stats_of` に足します。技は `domain/abilities/` に動物ごとの
  モジュールを足し、`techniques.py` の `match` に書きます
- ⛔ 試合を進める処理（`domain/systems/`）に、動物や振る舞いの種類で分ける処理を足さない
  でください。振る舞いが移動・爆弾・拾う・被弾に割り込むときは、`ActionTraits` に性質を
  足し、処理はその性質だけを見ます（突進が特別扱いなしで書けているのが、この形の確かめ
  です）
- CPU の戦い方は `ai/tactics.py` の `tactic_of` の `match` に書きます。動物を足すと、ここも
  mypy が失敗します

## CPU の判断（`ai/`）

- CPU は入力を返すだけです。試合の状態を書き換えず、試合の乱数（`world.rng`）も引きません
  （`tests/ai/test_cpu.py` が、入力を返す前と後で状態の要約が同じことを見ます）。CPU の乱数は
  `CpuInputSource` が持つ `Rng` です
- 判断の規則は `ai/behaviors.py` に関数を1つ書き、`ai/chain.py` の `DEFAULT_CHAIN` に並べます。
  並びの順がそのまま優先順位です。試すのは `for` 文で書きます（`chain.py` の説明）
- ⛔ 「袋小路では爆弾を置かない」を足さないでください。開幕はどこも袋小路なので、
  CPU が永久に爆弾を置かなくなります（原型で実際に起きました）
- 外周にいる CPU は、判断の並びを通らず `ai/pilot.py` の `NegibonPilot` が入力を決めます。
  記憶（`ai/memory.py`）と外周の操縦を作り直すのは、ラウンドの盤面が替わったときだけです。
  延長戦に入ったとき・外周から戻ったときに作り直さないでください（原型も作り直さない。
  作り直すと判断の間隔の揺らぎを引き直して CPU の乱数が1つ進み、`test_cpu_ts.py` が失敗します）
- 規則を変えると、乱数を引く順が変わることがあります。TypeScript 版と比べるテスト
  （`tests/ai/test_cpu_ts.py`）が失敗したら、TypeScript 版も同じく変えたかを確かめてください
