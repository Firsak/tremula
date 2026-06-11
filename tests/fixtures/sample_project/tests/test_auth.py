from samplepkg.auth import login


def test_login():
    assert login("u").startswith("token-")
