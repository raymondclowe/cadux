import os
from dotenv import load_dotenv


# Load .env if present (no error if missing)
load_dotenv()


def load_config(page=None):
    """Load config from env -> .env -> session.store -> None.

    Returns dict with keys 'wss_url' and 'secret_key', or None if not found.
    """
    url = os.environ.get("CADUX_WSS_URL")
    key = os.environ.get("CADUX_SECRET_KEY")

    if not url or not key:
        load_dotenv(override=False)
        url = url or os.environ.get("CADUX_WSS_URL")
        key = key or os.environ.get("CADUX_SECRET_KEY")

    if (not url or not key) and page is not None:
        try:
            url = url or page.session.store.get("wss_url")
            key = key or page.session.store.get("secret_key")
        except AttributeError:
            pass

    if url and key:
        return {"wss_url": url, "secret_key": key}

    return None
