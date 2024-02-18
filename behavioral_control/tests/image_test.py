import requests


def test_home():
    url = "http://127.0.0.1:8030/"
    resp = requests.get(url)
    assert resp.history[0].status_code == 302


def test_login():
    url = "http://127.0.0.1:8030/login/"
    session = requests.Session()
    session.get(url)

    csrf_token = session.cookies['csrftoken']

    data = dict(
        username="pc_test",
        password="pc_test",
        csrfmiddlewaretoken=csrf_token,
        login="[]"
    )

    resp = session.post(url, data=data)

    assert resp.status_code == 200, resp.content.decode()

    profile_url = "http://127.0.0.1:8030/profile/"

    resp = session.get(profile_url)

    assert 'name="api_token"' in resp.content.decode()
