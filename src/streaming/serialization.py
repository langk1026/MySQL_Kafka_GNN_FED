import json


def json_serializer(obj: dict) -> bytes:
    return json.dumps(obj).encode("utf-8")


def json_deserializer(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))
