import io
import json
import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from recommender import calc_client
from recommender.calc_client import CalcClient, CalcClientError
from recommender.calc_service import CalcService, DEFAULT_REPO_ROOT

GARCHOMP = {
    "species": "Garchomp",
    "nature": "Jolly",
    "evs": {"hp": 2, "atk": 32, "spe": 32},
}
KINGAMBIT = {
    "species": "Kingambit",
    "nature": "Adamant",
    "evs": {"hp": 32, "atk": 32, "spd": 2},
}
CALC_SUCCESS = {
    "damageRange": [150, 176],
    "koChance": "100% 2HKO",
    "raw": {
        "damage": [150, 152, 154, 156, 158, 160, 162, 164, 166, 168, 170, 172, 174, 176],
        "range": [150, 176],
        "kochance": {"chance": 1.0, "n": 2, "text": "100% 2HKO"},
        "desc": "short",
        "fullDesc": "full",
        "recovery": None,
        "recoil": None,
        "stats": {
            "attacker": {"atk": 182},
            "defender": {"hp": 170, "def": 120},
        },
    },
}


def _mock_urlopen(responses: dict[tuple[str, str], tuple[int, object]]):
    """Map (method, path) -> (status, body). path is suffix after base URL."""

    def factory(method: str, path: str, body=None):
        key = (method, path)

        def urlopen(req):
            status, payload = responses[key]
            raw = json.dumps(payload).encode()
            if status >= 400:
                err = calc_client.urllib.error.HTTPError(
                    req.full_url, status, "error", None, io.BytesIO(raw)
                )
                raise err
            resp = MagicMock()
            resp.status = status
            resp.read.return_value = raw
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        return urlopen

    return factory


def test_health():
    client = CalcClient("http://127.0.0.1:9")
    with patch.object(
        client,
        "_json_request",
        return_value=(200, {"status": "ok"}),
    ) as req:
        assert client.health() == {"status": "ok"}
    req.assert_called_once_with("GET", "/health")


def test_calculate_success():
    client = CalcClient("http://127.0.0.1:9")
    with patch.object(client, "_json_request", return_value=(200, CALC_SUCCESS)):
        out = client.calculate(GARCHOMP, KINGAMBIT, "Earthquake")
    assert out["damageRange"] == [150, 176]
    assert "2HKO" in out["koChance"]
    assert out["raw"]["range"] == [150, 176]


def test_calculate_with_field():
    client = CalcClient("http://127.0.0.1:9")
    field = {"gameType": "Doubles", "weather": "Rain"}
    with patch.object(client, "_json_request", return_value=(200, CALC_SUCCESS)) as req:
        client.calculate(GARCHOMP, KINGAMBIT, "Earthquake", field=field)
    _, _, body = req.call_args.args
    assert body["field"] == field


def test_calculate_error_raises():
    client = CalcClient("http://127.0.0.1:9")
    with patch.object(
        client, "_json_request", return_value=(400, {"error": "species is required"})
    ):
        with pytest.raises(CalcClientError) as exc:
            client.calculate({}, KINGAMBIT, "Earthquake")
    assert exc.value.status == 400
    assert exc.value.body == {"error": "species is required"}


def test_calculate_batch():
    client = CalcClient("http://127.0.0.1:9")
    batch = {
        "results": [
            CALC_SUCCESS,
            {"error": "move is required"},
        ]
    }
    with patch.object(client, "_json_request", return_value=(200, batch)) as req:
        results = client.calculate_batch(
            [{"attacker": GARCHOMP, "defender": KINGAMBIT, "move": "Earthquake"}]
        )
    req.assert_called_once()
    assert req.call_args.args[:2] == ("POST", "/calculate/batch")
    assert results[0]["damageRange"] == [150, 176]
    assert results[1]["error"] == "move is required"


def test_connection_error_is_normalized():
    client = CalcClient("http://127.0.0.1:9")
    with patch(
        "recommender.calc_client.urllib.request.urlopen",
        side_effect=calc_client.urllib.error.URLError("refused"),
    ):
        with pytest.raises(CalcClientError) as exc:
            client.health()
    assert exc.value.status == 0
    assert "refused" in str(exc.value.body)


def test_invalid_json_response_is_normalized():
    client = CalcClient("http://127.0.0.1:9")
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"{"
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    with patch(
        "recommender.calc_client.urllib.request.urlopen", return_value=response
    ):
        with pytest.raises(CalcClientError) as exc:
            client.health()
    assert exc.value.status == 200


@pytest.mark.parametrize("body", [{}, {"results": None}, []])
def test_malformed_batch_body_is_rejected(body):
    client = CalcClient("http://127.0.0.1:9")
    with patch.object(client, "_json_request", return_value=(200, body)):
        with pytest.raises(CalcClientError):
            client.calculate_batch([])


def test_sets_endpoints():
    client = CalcClient("http://127.0.0.1:9")
    sample_set = {"species": "Garchomp", "moves": ["Earthquake"]}
    with patch.object(
        client,
        "_json_request",
        side_effect=[
            (200, {"packed": "Garchomp|..."}),
            (200, {"set": sample_set}),
            (200, {"set": sample_set}),
            (200, {"text": "Garchomp @\n- Earthquake"}),
        ],
    ) as req:
        assert client.sets_pack(sample_set) == "Garchomp|..."
        assert client.sets_unpack("Garchomp|...") == sample_set
        assert client.sets_import("Garchomp @\n- Earthquake") == sample_set
        assert client.sets_export(sample_set) == "Garchomp @\n- Earthquake"
    paths = [call.args[1] for call in req.call_args_list]
    assert paths == [
        "/sets/pack",
        "/sets/unpack",
        "/sets/import",
        "/sets/export",
    ]


def test_module_wrappers_use_client():
    with patch.object(calc_client, "_client") as get_client:
        stub = MagicMock()
        get_client.return_value = stub
        calc_client.calculate(GARCHOMP, KINGAMBIT, "Earthquake", base_url="http://x")
        calc_client.calculate_batch([], base_url="http://x")
        calc_client.sets_pack({}, base_url="http://x")
        calc_client.sets_unpack("p", base_url="http://x")
        calc_client.sets_import("t", base_url="http://x")
        calc_client.sets_export({}, base_url="http://x")
    assert get_client.call_count == 6
    get_client.assert_called_with("http://x")


def test_calculate_forwards_boosts():
    client = CalcClient("http://127.0.0.1:9")
    with patch.object(
        client,
        "_json_request",
        return_value=(200, CALC_SUCCESS),
    ) as req:
        client.calculate(
            {**GARCHOMP, "boosts": {"atk": 2}},
            KINGAMBIT,
            "Earthquake",
        )
    body = req.call_args.args[2]
    assert body["attacker"]["boosts"] == {"atk": 2}
    proc = MagicMock()
    proc.pid = 4242
    proc.poll.return_value = None
    proc.wait.return_value = 0

    with (
        patch("recommender.calc_service.subprocess.Popen", return_value=proc) as popen,
        patch("recommender.calc_service.CalcClient") as client_cls,
        patch("recommender.calc_service.os.killpg") as killpg,
        patch("recommender.calc_service._pick_free_port", return_value=5555),
    ):
        client = client_cls.return_value
        client.health.side_effect = [
            CalcClientError(503, {"error": "starting"}),
            {"status": "ok"},
        ]
        svc = CalcService(port=5555)
        with svc:
            assert svc.port == 5555
            assert svc.base_url == "http://127.0.0.1:5555"
        popen.assert_called_once()
        kwargs = popen.call_args.kwargs
        assert kwargs["start_new_session"] is True
        assert kwargs["cwd"] == DEFAULT_REPO_ROOT
        assert kwargs["env"]["PORT"] == "5555"
        killpg.assert_any_call(4242, signal.SIGTERM)


def test_calc_service_stop_sigkill_on_timeout():
    proc = MagicMock()
    proc.pid = 9999
    proc.poll.return_value = None
    proc.wait.side_effect = [subprocess.TimeoutExpired("npm", 5), 0]

    with (
        patch("recommender.calc_service.subprocess.Popen", return_value=proc),
        patch("recommender.calc_service.CalcClient") as client_cls,
        patch("recommender.calc_service.os.killpg") as killpg,
    ):
        client_cls.return_value.health.return_value = {"status": "ok"}
        svc = CalcService(port=6000)
        svc.start()
        svc.stop()

    killpg.assert_any_call(9999, signal.SIGTERM)
    killpg.assert_any_call(9999, signal.SIGKILL)


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_live_garchomp_earthquake():
    repo_root = Path(__file__).resolve().parents[2]
    pid: int | None = None
    with CalcService(repo_root=repo_root) as svc:
        client = CalcClient(svc.base_url)
        out = client.calculate(GARCHOMP, KINGAMBIT, "Earthquake")
        assert out["damageRange"] == [150, 176]
        assert "2HKO" in out["koChance"]
        if svc._proc is not None:
            pid = svc._proc.pid
    assert pid is not None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_live_sets_roundtrip():
    repo_root = Path(__file__).resolve().parents[2]
    sample = {
        "species": "Garchomp",
        "item": "Life Orb",
        "ability": "Rough Skin",
        "nature": "Jolly",
        "evs": {"hp": 2, "atk": 32, "spe": 32},
        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
    }
    with CalcService(repo_root=repo_root) as svc:
        client = CalcClient(svc.base_url)
        packed = client.sets_pack(sample)
        assert isinstance(packed, str) and "Garchomp" in packed
        unpacked = client.sets_unpack(packed)
        assert unpacked.get("species") == "Garchomp"
        text = client.sets_export(sample)
        assert "Garchomp" in text
        imported = client.sets_import(text)
        assert imported.get("species") == "Garchomp"

