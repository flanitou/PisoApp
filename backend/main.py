"""WSGI entrypoint for Gunicorn and direct local execution."""

from silence.server import manager
from api import register_routes
from avatars import register_avatar_routes


manager.setup()
app = manager.APP
register_routes(app)
register_avatar_routes(app)


if __name__ == "__main__":
    manager.run()
