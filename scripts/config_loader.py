import json
import os
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
ENV_PATH = PROJECT_ROOT / ".env"


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """
    Load application configuration from config.json and override
    sensitive values with environment variables from .env.
    """

    load_dotenv(ENV_PATH)

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}\n"
            "Copy config/config.example.json to config/config.json first."
        )

    with path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    # Email credentials
    config["email"]["email_address"] = os.getenv(
        "EMAIL_ADDRESS",
        config["email"].get("email_address", "")
    )

    config["email"]["password"] = os.getenv(
        "EMAIL_PASSWORD",
        config["email"].get("password", "")
    )

    # Database credentials
    config["database"]["password"] = os.getenv(
        "DB_PASSWORD",
        config["database"].get("password", "")
    )

    # SMTP / notification credentials
    config["notifications"]["smtp_user"] = os.getenv(
        "SMTP_USER",
        config["notifications"].get("smtp_user", "")
    )

    config["notifications"]["smtp_password"] = os.getenv(
        "SMTP_PASSWORD",
        config["notifications"].get("smtp_password", "")
    )

    config["notifications"]["alert_email"] = os.getenv(
        "ALERT_EMAIL",
        config["notifications"].get("alert_email", "")
    )

    return config