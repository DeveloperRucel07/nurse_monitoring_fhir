from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REQUIRED_ENVIRONMENT = (
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "OIDC_COOKIE_SECRET",
    "OIDC_REDIRECT_URI",
    "OIDC_SERVER_METADATA_URL",
)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_auth_configuration() -> Path:
    missing = [name for name in REQUIRED_ENVIRONMENT if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Fehlende OIDC-Konfiguration: " + ", ".join(sorted(missing))
        )

    app_dir = Path(__file__).resolve().parent
    secrets_path = app_dir / ".streamlit" / "secrets.runtime.toml"
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    secrets_path.write_text(
        "\n".join(
            [
                "[auth]",
                f"redirect_uri = {_toml_string(os.environ['OIDC_REDIRECT_URI'])}",
                f"cookie_secret = {_toml_string(os.environ['OIDC_COOKIE_SECRET'])}",
                'expose_tokens = ["access"]',
                "",
                "[auth.keycloak]",
                f"client_id = {_toml_string(os.environ['OIDC_CLIENT_ID'])}",
                f"client_secret = {_toml_string(os.environ['OIDC_CLIENT_SECRET'])}",
                "server_metadata_url = "
                + _toml_string(os.environ["OIDC_SERVER_METADATA_URL"]),
                'client_kwargs = { scope = "openid profile email", prompt = "login" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        secrets_path.chmod(0o600)
    except OSError:
        pass
    return secrets_path


def main() -> None:
    app_dir = Path(__file__).resolve().parent
    project_root = app_dir.parent
    write_auth_configuration()

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(project_root)
        if not existing_pythonpath
        else os.pathsep.join((str(project_root), existing_pythonpath))
    )
    os.chdir(app_dir)
    os.execve(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            "8501",
        ],
        environment,
    )


if __name__ == "__main__":
    main()
