# TypeScript 版への指示

[リポジトリ共通の指示](../AGENTS.md) を先に読んでください。ここには
TypeScript 版に固有のものだけを書いています。

## 層の依存方向

```text
app → platform → presentation → net → ai → content → domain
```

逆向きの import を追加しないでください。

## `domain/` と `ai/` の中で使ってはいけないもの

- `Math.random` / `Date.now` / `performance.now`
- ブラウザ API（`document` / `window` / `canvas` など）

乱数と時刻は引数として渡します。`domain/` と `ai/` 専用の TypeScript 設定から
DOM の型定義を外してあるので、ブラウザ API を書くと型エラーになります。
**この設定を緩めないでください。**

`ai/`（CPU の思考）も対象なのは、CPU の判断も種から決まる必要があるためです。
通信対戦では各端末が同じ CPU を動かします。CPU は自分専用の乱数（`Rng`）を持ち、
試合の乱数（`world.rng`）には触れません。

## interface の関数の書き方

interface の関数は `next: (world: …) => …` の形で書いてください。`next(world: …): …`（メソッドの形）だと、
TypeScript は引数の型の向きを検査せず、引数を狭めた実装を渡しても型エラーになりません。
lint（`method-signature-style`）が強制し、`tests/boundary/variance.test.ts` が型エラーになることを確認しています。
例外は、ブラウザの Web Audio を写した型の `AudioNodeLike.connect`（`src/presentation/audio/webAudioTypes.ts`）だけです。
実物の connect は引数に DOM の型を取るので、向きを検査すると実物が入りません。その行に理由を書いて lint を外してあります。

## 動物の能力を追加するとき

共通の interface を実装し、登録の1行を足すだけで済む形になっています。
既存の動物のファイルにも、ゲーム本体にも変更を加えないでください。
変更を加えないと追加できない場合は、抽象の引き方が間違っているので報告してください。

CPU の戦い方も同じ形です。`src/ai/tactics/` に戦い方を1つ書き、
`src/ai/tactics/registry.ts` に登録の1行を足します。書かなくても、
省略時の戦い方（足元に爆弾を置く・技は使わない）でその動物は戦えます。

⛔ 共通の処理（`domain/systems/` `domain/mutations/` `domain/query/` `domain/negibon/` `domain/events/` `ai/` 直下 `ai/behaviors/`）に
動物の名前を書かないでください。**コメントも含みます。** 書くと
`tests/boundary/guards.test.ts` が失敗します。

## プレイヤーの状態（`src/domain/state/Life.ts`）

盤面にいる・外周にいる（葱ボン）・退場した、の3つを判別可能ユニオンで持っています。

- ⛔ `player.life` の中身を書き換えないでください。丸ごと差し替えます。`ALIVE` と `OUT` は全員で
  1つを使い回しているので、書き換えると全員の状態が変わります（型も `readonly` にしてあります）
- 盤面の上の処理は、最初に `isAlive(player)` で外周の人と退場した人を外します。
  葱ボンのための分岐を盤面の処理に足さないでください
- 例外は1つだけです。盤面を離れても残す振る舞い（`ActiveAction.staysOffBoard`。いまは舌）は、技の System
  （`ActionSystem`）が外さずに止めておき、爆風に触れたかだけを見続けます。原型が倒れたあとも舌を残し、焼けたかを
  状態を問わず確認するためです。⛔ この分岐を「盤面にいないプレイヤーの処理だから」と消さないでください
- 状態を1つ足すと、状態の要約（`hashWorld` の `hashLife`）がコンパイルエラーで書き足しを求めます

## CPU の判断の規則を足すとき

`src/ai/behaviors/` に `CpuBehavior` を1つ書き、`DefaultChain.ts` の配列に並べます。
配列の順番がそのまま優先順位です。

⛔ 「袋小路では爆弾を置かない」を足さないでください。開幕はどこも袋小路なので、
CPU が永久に爆弾を置かなくなります（原型で実際に起きました）。

## 通信対戦（`src/net/`）

- メッセージの約束（`src/net/protocol.ts`）を変えるときは、中継サーバの
  `server/src/animal_bomber_server/protocol.py` も同じく変えてください。
  片方だけ変えると `server/tests/test_protocol_sync.py` が失敗します
- ⛔ 通信と操作の記録の時刻に `world.now` を使わないでください。ラウンドごとに 0 へ戻り、決着のあとの待ちの間は
  止まります。試合通算の tick（`MatchClock` の形。`GameSession.elapsed` と `LockstepDriver.elapsed`）を使います
- 自分の端末のプレイヤーも `NetworkInputSource` を通します。キーボードを直接繋ぐと、自分の手元でだけ
  操作が早く反映されて試合がずれます

## 数値の調整

CPU の強さや自爆の割合は、画面なしで測れます。

```sh
MEASURE=1 npx vitest run tests/ai/balance.test.ts
```

## 絵と音（`src/presentation/`）

- 試合の状態は読むだけにしてください。書き換えると、画面を出したときだけ試合が変わります
- 見た目の乱数は `CosmeticRng` を使い、`Math.random` を直接呼ばないでください
- ファイルの一番外側（関数の外）で `window` `document` `AudioContext` に触れないでください。
  テストは node で走るので、読み込んだ時点でテストが失敗します
- 描画のテストで使う偽の canvas（`tests/presentation/fakeCanvas.ts`）は、ブラウザが例外を出す
  呼び方（負の半径など）で同じく例外を出します。**この検査を緩めないでください**

## 画面（`src/presentation/hud/`・`src/presentation/menu/`・`src/platform/ui/`）

- 試合の状態から計算して出すもの（名札・時計・幕・通知・秒読み）と、画面の流れ・選んだものは
  `presentation/` に、純粋な関数とクラスで書いてください。試合の状態を読む判断を `platform/ui/` に
  足さないでください
- `platform/ui/` に書いてよいのは、画面の固定の文言（ボタンの名前・注記）と、どの行を並べるか
  （遊び方の人数で行を出し分ける、など）です。メニューの操作の表を使う説明（`platform/keyHelp.ts` の `menuHelp`）も、
  表が `platform/` にあるのでここに置きます。試合のキーの案内（キャラ選び・横の板）は原型と同じ固定の文で、
  `presentation/menu/keyHints.ts`・`presentation/hud/keyHelp.ts` にあります（割り当ての表から作らない。原型の案内は
  割り当てた全部のキーを書かない）
- 画面のボタンは `pointerButton`（`platform/ui/dom.ts`）で作ってください。キーボードで起きたクリックを
  捨てます。マウスで押したボタンにフォーカスが残ると、試合中の Space や Enter（爆弾のキー）でブラウザが
  そのボタンをもう一度押すためです
- キーボードで動かす項目には `data-nav`（グループの名前）を付けてください。縦に並ぶものは1つずつ別の名前に、
  横に並ぶもの（動物の一覧・選択肢の1行）は同じ名前にします。カーソルは `activate` で中身を呼びます。
  ⛔ クリックを偽って発生させないでください（上の、キーボードで起きたクリックを捨てる仕組みをすり抜けます）
- 文は `textContent` で入れてください。`innerHTML` に文字列をつないで入れないでください
- 写す側のテストは、ファイルの先頭に `// @vitest-environment happy-dom` と書くと代わりの DOM の上で
  走ります。ほかのテストは node のままです
- ラウンドの間の幕をボタンで送る形にしないでください。通信対戦で「誰の操作で次へ進むか」を
  揃える必要が出てきます。待ちの長さは試合の側（`ROUND_INTERMISSION`）が tick で数えています
- `main.ts` が探す要素の名前を変えたら、`index.html` も修正してください（`tests/ui/index-html.test.ts` が突き合わせます）
