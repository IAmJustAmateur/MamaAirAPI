"""Isolated process smoke test settings; not used for deployment or Redis CI."""
from .settings import *  # noqa: F403

test_root = Path(os.environ["EMAIL_E2E_ROOT"])
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": test_root / "test.sqlite3"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = str(test_root / "mail")
CELERY_BROKER_URL = "filesystem://"
CELERY_BROKER_TRANSPORT_OPTIONS = {"data_folder_in": str(test_root / "queue"), "data_folder_out": str(test_root / "queue"), "control_folder": str(test_root / "control")}
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
DEBUG = False
SECRET_KEY = "isolated-email-process-test"
