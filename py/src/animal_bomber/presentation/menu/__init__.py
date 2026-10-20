"""試合の前の画面で選ぶものと、選んだものから試合を作る段取り（純粋。描かない）。

- `choices.py`：画面で選べる値（勝ち数・制限時間・爆風の回数・CPU の強さ）と、
  回数と体力の換算
- `local_setup.py`：1台で遊ぶときに選んだもの（`LocalSetup`）と、そこから作る
  試合の段取り（`plan_local_match`）
- `lan_setup.py`：通信対戦のロビーでホストが選ぶもの（`LanSetup`）と、全員へ配る
  設定（`LanSettings`）との行き来

ルールの層（`MatchConfig`）はどんな値でも受け取れる。選べる値を絞るのは画面の都合なので、
ここに置く（TypeScript 版の `presentation/menu/` と同じ分け方）。
"""
