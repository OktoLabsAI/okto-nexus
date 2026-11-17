from foo import fixture as fixture

__all__ = ['fixture']


def test_one(fixture):
    assert fixture
