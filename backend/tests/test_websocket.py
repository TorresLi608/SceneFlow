from __future__ import annotations

from app.api.v1.websocket import protocol_token


def test_websocket_token_comes_from_protocol_header() -> None:
    token, protocol = protocol_token("chat, sceneflow-auth.header.payload.signature")

    assert token == "header.payload.signature"
    assert protocol == "sceneflow-auth.header.payload.signature"


if __name__ == "__main__":
    test_websocket_token_comes_from_protocol_header()
