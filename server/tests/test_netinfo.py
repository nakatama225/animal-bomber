"""`netinfo` の実測ベースの確認。

実行環境（CI・オフラインの Mac 等）によって取れたり取れなかったりする値なので、
「必ず取れる」ではなく「取れたら形が正しい・取れなければ None」を確認する。
"""

from __future__ import annotations

import ipaddress

from animal_bomber_server.netinfo import candidate_urls, lan_ip, mdns_hostname


def test_mdns_hostnameは取れるかNoneのどちらか():
    result = mdns_hostname()
    if result is not None:
        assert result.endswith(".local")
        assert len(result) > len(".local")


def test_lan_ipは取れたら妥当なIPv4になっている():
    result = lan_ip()
    if result is not None:
        ipaddress.IPv4Address(result)  # 形が違えば例外で落ちる


def test_candidate_urlsはポート番号を含む():
    urls = candidate_urls(8777)
    for url in urls:
        assert url.endswith(":8777")
        assert url.startswith("http://")


def test_取得できるものが1つも無くても例外にしない():
    # 実際に何も取れない環境（オフライン・特殊なネットワーク設定）はありうる。
    # その場合は空リストを返し、呼び出し側がフォールバック文言を出す。
    urls = candidate_urls(8777)
    assert isinstance(urls, list)
