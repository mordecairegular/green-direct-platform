from green_direct.cli import build_parser, main
from green_direct.services import LocalPilotAuth, LocalPilotRegistry, LocalResultStore


def _store_arg(tmp_path):
    return ["--store-dir", str(tmp_path)]


def test_cli_pilot_admin_bootstrap_create_reset_disable_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("ANALYST_PASSWORD", "analyst-password")
    monkeypatch.setenv("RESET_PASSWORD", "reset-password")

    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    assert "Bootstrapped platform admin: admin" in capsys.readouterr().out

    assert main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
            "--login-name",
            "analyst@example.local",
            "--display-name",
            "Analyst",
            "--password-env",
            "ANALYST_PASSWORD",
        ]
    ) == 0

    assert main(
        [
            "pilot-admin",
            "reset-password",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
            "--password-env",
            "RESET_PASSWORD",
        ]
    ) == 0

    auth = LocalPilotAuth(
        tmp_path,
        registry=LocalPilotRegistry(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )
    assert auth.login(login_name="analyst@example.local", password="reset-password").user_id == "analyst"

    assert main(
        [
            "pilot-admin",
            "list-users",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "admin@example.local" in output
    assert "analyst@example.local" in output
    assert "reset-password" not in output

    assert main(
        [
            "pilot-admin",
            "disable-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("analyst").is_active is False


def test_cli_pilot_admin_grant_revoke_and_list_sessions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("OPS_PASSWORD", "ops-password")
    main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    )
    main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
            "--login-name",
            "ops@example.local",
            "--display-name",
            "Ops",
            "--password-env",
            "OPS_PASSWORD",
        ]
    )

    assert main(
        [
            "pilot-admin",
            "grant-platform-admin",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("ops").is_platform_admin is True

    auth = LocalPilotAuth(
        tmp_path,
        registry=LocalPilotRegistry(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )
    auth.login(login_name="ops@example.local", password="ops-password")
    assert main(
        [
            "pilot-admin",
            "list-sessions",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert "ops" in capsys.readouterr().out

    assert main(
        [
            "pilot-admin",
            "revoke-platform-admin",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("ops").is_platform_admin is False


def test_cli_errors_return_nonzero_and_do_not_create_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    )

    code = main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "missing-admin",
            "--user-id",
            "viewer",
            "--login-name",
            "viewer@example.local",
            "--display-name",
            "Viewer",
        ]
    )

    assert code == 1
    assert "Error:" in capsys.readouterr().err
    assert LocalPilotRegistry(tmp_path).list_users()[0].user_id == "admin"


def test_cli_exposes_green_direct_console_script():
    parser = build_parser()
    parsed = parser.parse_args(["pilot-admin", "list-users", "--actor-user-id", "admin"])

    assert parsed.command == "pilot-admin"
    assert parsed.pilot_admin_command == "list-users"
