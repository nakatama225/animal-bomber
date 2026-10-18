"""試合の状態に無い、見た目だけの値を数える所（粒子・画面の揺れ・歩いた距離など）。

原型はこれらをプレイヤーや盤面の物の項目として持ち、update の中で書き換えていた
（walk・lastMoveAt・hurtFlash・粘膜爆弾の sx と sy・炎の trail・particles・shakeAmt）。
この版のルールの層はそれらを持たない。ここで、1 tick ごとに進めたあとの盤面と、
その tick に起きたこと（`SimEvent`）を受け取って数える
（`tracker.py` の `SceneTracker`）。

数えた値は描く側（`render/renderer.py`）が読む。試合の状態は読むだけで書き換えない。
"""
