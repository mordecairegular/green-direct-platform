from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_defaults_to_internal_pilot_safety():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["green-direct"]
    environment = service["environment"]

    assert environment["GREEN_DIRECT_ENABLE_PILOT_AUTH"] == "1"
    assert environment["GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT"] == "0"
    assert environment["GREEN_DIRECT_PILOT_STORE_DIR"] == "/data/pilot_store"
    assert environment["GREEN_DIRECT_MAX_SCENARIOS_PER_RUN"] == "${GREEN_DIRECT_MAX_SCENARIOS_PER_RUN:-20000}"
    assert "green_direct_pilot_store:/data/pilot_store" in service["volumes"]
    assert compose["volumes"]["green_direct_pilot_store"]["name"] == "green_direct_pilot_store"
    assert service["ports"] == ["8503:8503"]


def test_dockerfile_defaults_to_safe_server_mode():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "GREEN_DIRECT_ENABLE_PILOT_AUTH=1" in dockerfile
    assert "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0" in dockerfile
    assert "GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store" in dockerfile
    assert "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000" in dockerfile
    assert "streamlit" in dockerfile
    assert "_stcore/health" in dockerfile
    assert "USER appuser" in dockerfile


def test_dockerignore_excludes_local_state_and_secrets():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for pattern in [".env", ".env.*", ".runtime/", ".venv/", "outputs/", "*.log"]:
        assert pattern in ignored
    assert "!.env.example" in ignored
