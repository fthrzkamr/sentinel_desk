from .base import *  # noqa: F401,F403

DEBUG = True

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

import socket  # noqa: E402

# Requests arriving through Docker's port mapping show up with the Docker
# bridge gateway IP instead of 127.0.0.1, so the toolbar needs that IP too.
_, _, _ips = socket.gethostbyname_ex(socket.gethostname())
INTERNAL_IPS = ["127.0.0.1"] + [ip[: ip.rfind(".")] + ".1" for ip in _ips]
