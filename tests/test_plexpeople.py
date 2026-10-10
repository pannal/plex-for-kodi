# coding=utf-8
"""lib/plexpeople.py - plex.tv/community people lookups for Watch Together."""

from __future__ import absolute_import

import json

from lib import plexpeople


def test_friends_parses_graphql():
    body = json.dumps({"data": {"allFriendsV2": [
        {"user": {"id": "abc", "idRaw": 1000002, "displayName": "P", "avatar": "http://a"}},
    ]}}).encode()
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body))
    assert out == [{"id": 1000002, "title": "P", "thumb": "http://a"}]


def test_friends_degrades_on_error():
    assert plexpeople.friends("tok", http=lambda *a, **k: (500, "text/html", b"")) == []


def test_friends_empty_is_empty():
    body = json.dumps({"data": {"allFriendsV2": []}}).encode()
    assert plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body)) == []


def test_friends_falls_back_to_username_when_displayname_empty():
    # most real friends have an empty displayName but a username (live probe)
    body = json.dumps({"data": {"allFriendsV2": [
        {"user": {"idRaw": 7, "displayName": "", "username": "alice", "avatar": "a"}},
        {"user": {"idRaw": 8, "displayName": "Bob", "username": "bob", "avatar": "b"}},
    ]}}).encode()
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body))
    assert out == [{"id": 7, "title": "alice", "thumb": "a"},
                   {"id": 8, "title": "Bob", "thumb": "b"}]


def test_friends_posts_graphql_with_token_header():
    calls = []

    def http(method, url, headers, body=None):
        calls.append((method, url, headers, body))
        return (200, "application/json", b'{"data": {"allFriendsV2": []}}')

    plexpeople.friends("tok", http=http)
    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url == "https://community.plex.tv/api"
    assert headers["x-plex-token"] == "tok"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body.decode("utf-8"))["operationName"] == "GetAllFriends"


def test_friends_skips_entries_without_idraw():
    body = json.dumps({"data": {"allFriendsV2": [
        {"user": {"displayName": "no id"}},
        {"user": {"idRaw": 7, "displayName": "ok"}},
    ]}}).encode()
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body))
    assert out == [{"id": 7, "title": "ok", "thumb": ""}]


def test_friends_coerces_string_idraw_to_int():
    # a string idRaw would never match the int sharee ids, silently emptying
    # the friends∩sharees intersection
    body = json.dumps({"data": {"allFriendsV2": [
        {"user": {"idRaw": "1000002", "displayName": "P", "avatar": ""}},
    ]}}).encode()
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body))
    assert out == [{"id": 1000002, "title": "P", "thumb": ""}]


def test_friends_skips_non_numeric_idraw():
    body = json.dumps({"data": {"allFriendsV2": [
        {"user": {"idRaw": "abc", "displayName": "bad"}},
        {"user": {"idRaw": 7, "displayName": "ok"}},
    ]}}).encode()
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body))
    assert out == [{"id": 7, "title": "ok", "thumb": ""}]


def test_friends_degrades_on_bad_json():
    assert plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", b"<html>")) == []


def test_friends_non_dict_json_is_empty():
    assert plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", b"[]")) == []


def test_friends_scalar_json_is_empty():
    assert plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", b"123")) == []


def test_friends_non_dict_data_is_empty():
    body = json.dumps({"data": [1]}).encode()
    assert plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", body)) == []


def test_shared_users_parses_xml():
    xml = b'<MediaContainer><SharedServer userID="1000002" username="p"/></MediaContainer>'
    out = plexpeople.shared_users("tok", "mid", http=lambda *a, **k: (200, "application/xml", xml))
    assert out == [{"id": 1000002, "title": "p"}]


def test_shared_users_404_is_empty():
    assert plexpeople.shared_users("tok", "mid", http=lambda *a, **k: (404, "application/xml", b"")) == []


def test_shared_users_gets_server_endpoint_with_token():
    calls = []

    def http(method, url, headers, body=None):
        calls.append((method, url, headers, body))
        return (200, "application/xml", b"<MediaContainer/>")

    plexpeople.shared_users("tok", "mid", http=http)
    method, url, headers, body = calls[0]
    assert method == "GET"
    assert url == "https://plex.tv/api/servers/mid/shared_servers"
    assert headers["x-plex-token"] == "tok"


def test_shared_users_degrades_on_bad_xml():
    assert plexpeople.shared_users("tok", "mid",
                                   http=lambda *a, **k: (200, "application/xml", b"<not xml")) == []


def _pp(friends, sharees):
    def http(method, url, headers, body=None):
        if "community" in url:
            return (200, "application/json", json.dumps({"data": {"allFriendsV2":
                [{"user": {"idRaw": i, "displayName": t, "avatar": ""}} for i, t in friends]}}).encode())
        return (200, "application/xml",
                ("<MediaContainer>" + "".join('<SharedServer userID="%d" username="%s"/>' % (i, t) for i, t in sharees) + "</MediaContainer>").encode())
    return http


def test_own_server_intersects_friends_with_sharees():
    http = _pp([(1, "a"), (2, "b"), (3, "c")], [(2, "b"), (3, "c"), (4, "d")])
    out = plexpeople.eligible_invitees("tok", "mid", True, [{"id": 5, "title": "h", "thumb": ""}], self_id=9, http=http)
    assert sorted(i.id for i in out) == [2, 3, 5]
    assert all(not i.access_unknown for i in out)


def test_shared_server_offers_all_friends_flagged():
    http = _pp([(1, "a"), (2, "b")], [])
    out = plexpeople.eligible_invitees("tok", "mid", False, [{"id": 5, "title": "h", "thumb": ""}], http=http)
    assert sorted(i.id for i in out) == [1, 2, 5]
    assert all(i.access_unknown for i in out)


def test_excludes_self_and_room_members():
    http = _pp([(1, "a"), (2, "b")], [(1, "a"), (2, "b")])
    out = plexpeople.eligible_invitees("tok", "mid", True, [], self_id=1, room_user_ids=[2], http=http)
    assert out == []


def test_friends_failure_falls_back_to_home_users():
    http = lambda *a, **k: (500, "text/html", b"")
    out = plexpeople.eligible_invitees("tok", "mid", False, [{"id": 5, "title": "h", "thumb": ""}], http=http)
    assert [i.id for i in out] == [5]


def test_http_never_raises_on_a_failed_request():
    # the injectable contract: a failed request degrades to an empty result
    status, _ct, body = plexpeople._http("GET", "http://127.0.0.1:1/nope", {})
    assert status == 0
    assert body == b""


def test_friends_str_body_degrades():
    # an injected http returning str (not bytes) must not raise
    out = plexpeople.friends("tok", http=lambda *a, **k: (200, "application/json", "[]"))
    assert out == []
