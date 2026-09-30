"""盤面に置かれるものの識別子の検査。"""

from animal_bomber.domain.core.entity_id import IdSource


class TestIdSource:
    def test_1から順に発番し_数を覚えている(self) -> None:
        ids = IdSource()
        assert ids.issued == 0
        assert [ids.take() for _ in range(3)] == [1, 2, 3]
        assert ids.issued == 3

    def test_試合ごとに1から数え直す(self) -> None:
        first = IdSource()
        first.take()
        assert IdSource().take() == 1
