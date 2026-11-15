"""Point d'entrée des runtimes AgentCore d'AlphaForge AI (``python main.py``).

Le rôle vient de ``AGENT_ROLE`` (``profile``, ``press``, ``data`` ou ``supervisor``). Dans le zip déployé, le paquet
``alphaforge`` est à la racine, à côté de ce fichier; en développement, ``uv run python main.py`` l'importe depuis
``src/`` (installation éditable).
"""

import sys
from pathlib import Path

try:
    import alphaforge  # noqa: F401
except ModuleNotFoundError:  # exécution directe depuis app/agents sans installation
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from alphaforge.server import configure_logging, create_app, serve

configure_logging()
app = create_app()

if __name__ == "__main__":
    serve(app)
