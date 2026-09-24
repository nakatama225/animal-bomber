"""この端末を LAN 上でどう指せばよいかを調べる。

同じ情報に2つの経路がある。片方は Wi-Fi の隔離設定で通らないことがあるため、
両方を用意して両方とも画面に出す（どちらかが必ず通るという想定はしない）。
"""

from __future__ import annotations

import socket
import subprocess


def mdns_hostname() -> str | None:
    """`<ホスト名>.local` の形を返す。

    macOS の Bonjour（mDNS）名で、Mac 同士なら設定ゼロで名前解決できる。
    VPN・Wi-Fi クライアント隔離・VLAN 分割の環境では届かないことがあるため、
    :func:`lan_ip` と両方を候補として提示する。

    Returns:
        `"my-macbook.local"` のような文字列。取得できなければ `None`。
    """
    try:
        result = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None

    name = result.stdout.strip()
    return f"{name}.local" if name else None


def lan_ip() -> str | None:
    """この端末の LAN 内 IPv4 アドレスを返す。

    実際には外部へ接続しない。UDP ソケットで接続先を指定すると、OS が
    「その宛先に届けるならどの network interface を使うか」を決めるので、
    その決定に使われたローカル側のアドレスを読む、という手法。
    8.8.8.8 は届く必要すらない（接続確立もパケット送信もしない）。

    Returns:
        `"192.168.1.42"` のような文字列。取得できなければ `None`。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return None


def candidate_urls(port: int) -> list[str]:
    """ゲストに見せる候補 URL の一覧を作る。

    どちらか一方が必ず通るとは限らないため、両方を表示して
    「繋がらなければもう一方を試す」を利用者に委ねる。
    """
    urls = []
    host = mdns_hostname()
    if host:
        urls.append(f"http://{host}:{port}")
    ip = lan_ip()
    if ip:
        urls.append(f"http://{ip}:{port}")
    return urls
