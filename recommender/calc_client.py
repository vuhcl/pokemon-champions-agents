"""Thin HTTP client for the Node calc service (fixed contract)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Literal, NotRequired, TypedDict

DEFAULT_BASE_URL = "http://127.0.0.1:4173"


class CalcClientError(Exception):
    """HTTP failure or calc-service `{error: ...}` response."""

    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self.body = body
        super().__init__(f"calc request failed ({status}): {body}")


# JSON uses "def"; TypedDict cannot name a field `def`.
StatSpreadJson = dict[str, int]

SideWeather = Literal[
    "Sand",
    "Sun",
    "Rain",
    "Snow",
    "Harsh Sunshine",
    "Heavy Rain",
    "Strong Winds",
]
Terrain = Literal["Electric", "Grassy", "Psychic", "Misty"]
GameType = Literal["Singles", "Doubles"]


class SideSpec(TypedDict, total=False):
    isReflect: bool
    isLightScreen: bool
    isAuroraVeil: bool
    isTailwind: bool
    isHelpingHand: bool
    isFriendGuard: bool
    isBattery: bool
    spikes: int
    isSR: bool


class FieldSpec(TypedDict, total=False):
    gameType: GameType
    weather: SideWeather
    terrain: Terrain
    isGravity: bool
    isMagicRoom: bool
    isWonderRoom: bool
    attackerSide: SideSpec
    defenderSide: SideSpec


class PokemonSpec(TypedDict):
    species: str


class PokemonSpecOptional(PokemonSpec, total=False):
    item: str
    ability: str
    moves: list[str]
    nature: str
    evs: StatSpreadJson
    level: int
    boosts: StatSpreadJson


class CalcRequest(TypedDict):
    attacker: PokemonSpecOptional
    defender: PokemonSpecOptional
    move: str
    field: NotRequired[FieldSpec]


class KochanceRaw(TypedDict):
    chance: float | None
    n: int
    text: str


class RecoveryRaw(TypedDict):
    recovery: list[int]
    text: str


class RecoilRaw(TypedDict):
    recoil: int | list[int]
    text: str


class CalcStatsRaw(TypedDict):
    attacker: StatSpreadJson
    defender: StatSpreadJson


class CalcRaw(TypedDict, total=False):
    damage: int | list[int] | list[list[int]]
    range: list[int]
    kochance: KochanceRaw
    desc: str
    fullDesc: str
    recovery: RecoveryRaw
    recoil: RecoilRaw
    stats: CalcStatsRaw


class CalcSuccessResponse(TypedDict):
    damageRange: list[int]
    koChance: str
    raw: CalcRaw


class CalcErrorResponse(TypedDict):
    error: str


CalcResult = CalcSuccessResponse | CalcErrorResponse


class HealthResponse(TypedDict):
    status: str


class BatchRequest(TypedDict):
    requests: list[CalcRequest]


class BatchResponse(TypedDict):
    results: list[CalcResult]


class PackRequest(TypedDict):
    set: dict[str, Any]


class PackResponse(TypedDict):
    packed: str


class UnpackRequest(TypedDict):
    packed: str


class UnpackResponse(TypedDict):
    set: dict[str, Any]


class ImportRequest(TypedDict):
    text: str


class ImportResponse(TypedDict):
    set: dict[str, Any]


class ExportRequest(TypedDict):
    set: dict[str, Any]


class ExportResponse(TypedDict):
    text: str


class CalcClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _json_request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        data: bytes | None = None
        headers: dict[str, str] = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                parsed = json.loads(resp.read().decode())
                return resp.status, parsed
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                parsed = json.loads(raw) if raw else {"error": exc.reason}
            except json.JSONDecodeError:
                parsed = {"error": raw or exc.reason}
            return exc.code, parsed

    def health(self) -> HealthResponse:
        status, body = self._json_request("GET", "/health")
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body

    def calculate(
        self,
        attacker: PokemonSpecOptional,
        defender: PokemonSpecOptional,
        move: str,
        field: FieldSpec | None = None,
    ) -> CalcSuccessResponse:
        payload: CalcRequest = {
            "attacker": attacker,
            "defender": defender,
            "move": move,
        }
        if field is not None:
            payload["field"] = field
        status, body = self._json_request("POST", "/calculate", payload)
        if status < 200 or status >= 300 or (
            isinstance(body, dict) and "error" in body
        ):
            raise CalcClientError(status, body)
        return body

    def calculate_batch(self, requests: list[CalcRequest]) -> list[CalcResult]:
        status, body = self._json_request(
            "POST", "/calculate/batch", {"requests": requests}
        )
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body["results"]

    def sets_pack(self, set_data: dict[str, Any]) -> str:
        status, body = self._json_request("POST", "/sets/pack", {"set": set_data})
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body["packed"]

    def sets_unpack(self, packed: str) -> dict[str, Any]:
        status, body = self._json_request("POST", "/sets/unpack", {"packed": packed})
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body["set"]

    def sets_import(self, text: str) -> dict[str, Any]:
        status, body = self._json_request("POST", "/sets/import", {"text": text})
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body["set"]

    def sets_export(self, set_data: dict[str, Any]) -> str:
        status, body = self._json_request("POST", "/sets/export", {"set": set_data})
        if status < 200 or status >= 300:
            raise CalcClientError(status, body)
        return body["text"]


_default_client: CalcClient | None = None


def _client(base_url: str | None = None) -> CalcClient:
    if base_url is not None:
        return CalcClient(base_url)
    global _default_client
    if _default_client is None:
        _default_client = CalcClient()
    return _default_client


def calculate(
    attacker: PokemonSpecOptional,
    defender: PokemonSpecOptional,
    move: str,
    field: FieldSpec | None = None,
    *,
    base_url: str | None = None,
) -> CalcSuccessResponse:
    return _client(base_url).calculate(attacker, defender, move, field)


def calculate_batch(
    requests: list[CalcRequest],
    *,
    base_url: str | None = None,
) -> list[CalcResult]:
    return _client(base_url).calculate_batch(requests)


def sets_pack(set_data: dict[str, Any], *, base_url: str | None = None) -> str:
    return _client(base_url).sets_pack(set_data)


def sets_unpack(packed: str, *, base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url).sets_unpack(packed)


def sets_import(text: str, *, base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url).sets_import(text)


def sets_export(set_data: dict[str, Any], *, base_url: str | None = None) -> str:
    return _client(base_url).sets_export(set_data)
