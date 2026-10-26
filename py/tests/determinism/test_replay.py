"""記録した操作を再生すると、同じ試合になることの検査。

この版のいちばんの土台。ここが崩れると、通信対戦（相手の操作だけを受け取って同じ試合を
作る）も、画面なしで大量の試合を実行するバランスの検証も成り立たない。
"""

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.world import hash_world
from animal_bomber.net.input_log import InputLog

from .scenario import SEED, TICKS, play_and_record, replay


class Testリプレイ:
    def test_同じ種と同じ操作からは_同じ状態になる(self) -> None:
        a, _ = play_and_record()
        b, _ = play_and_record()
        assert hash_world(a) == hash_world(b)

    def test_記録を再生すると_同じ状態に行き着く(self) -> None:
        played, log = play_and_record()
        assert hash_world(replay(log)) == hash_world(played)

    def test_記録は文字列にして戻しても_同じ状態に行き着く(self) -> None:
        played, log = play_and_record()
        restored = InputLog.decode(log.encode())
        assert restored.encode() == log.encode()
        assert hash_world(replay(restored)) == hash_world(played)

    def test_台本どおりに動いて_盤面の時刻が進んでいる(self) -> None:
        """上の3つの検査が素通りしないための前提。

        同じ状態に行き着くことを確認しても、何も動いていなければ同じになって当たり前。
        """
        played, _ = play_and_record()
        fresh, _ = play_and_record(ticks=0)
        assert played.now == TICKS
        moved = [
            a.position != b.position
            for a, b in zip(played.players, fresh.players, strict=True)
        ]
        assert all(moved), moved

    def test_種が違えば_同じ操作でも違う状態になる(self) -> None:
        # 種が要約に反映されることの対照。台本は壊せるブロックを取り除くので、差は乱数の
        # 状態から出る（入力を変えたときの対照は、すぐ下のテスト）。
        _, log = play_and_record()
        assert hash_world(replay(log, seed=SEED + 1)) != hash_world(replay(log))

    def test_記録を一部変えると_違う状態になる(self) -> None:
        """再生が、本当に記録を読んでいることの対照。

        最後の 100 tick だけ、全員を何も押していない入力に替えた記録を作る（途中の数
        tick を替えるだけだと、そのあと壁に押し付けている間に差が消えることがある）。
        """
        played, log = play_and_record()
        changed = InputLog()
        for tick in map(MatchTick, range(TICKS)):
            for player in played.players:
                player_input = log.at(tick, player.id)
                if tick >= TICKS - 100:
                    player_input = PlayerInput.IDLE
                changed.record(tick, player.id, player_input)
        assert changed.encode() != log.encode()
        assert hash_world(replay(changed)) != hash_world(played)
