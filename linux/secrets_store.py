"""Store API keys in Windows Credential Manager via the keyring package, with .env as the dev fallback."""
import os

from dotenv import load_dotenv

try:
    import keyring
except Exception:  # keyring optional; .env still works
    keyring = None

load_dotenv()  # so a .env works no matter how the app is launched

SERVICE = "com.heyjev.win"
KEY_NAMES = ("TYPESAFE_API_KEY", "FISH_AUDIO_API_KEY", "OPENROUTER_API_KEY")


def credman_value(name):
    if keyring is None:
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def get_secret(name):
    return os.getenv(name) or credman_value(name)  # .env wins, so editing it always takes effect


def save_secret(name, value):
    if name not in KEY_NAMES:
        raise ValueError(f"unknown secret: {name}")
    value = value.strip()
    if not value:
        return
    if keyring is None:
        raise RuntimeError("keyring is not installed; put the key in .env instead")
    try:
        keyring.set_password(SERVICE, name, value)
    except Exception as e:
        raise RuntimeError(f"Could not save to Credential Manager: {e}") from e


def missing_secrets():
    return [name for name in KEY_NAMES if not get_secret(name)]
