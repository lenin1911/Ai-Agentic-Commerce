import os
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()


def create_app(test_config=None):
    """Application factory for Agent Storefront."""
    app = Flask(__name__)

    # Default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod"),
        FLASK_ENV=os.environ.get("FLASK_ENV", "development"),
    )

    if test_config:
        app.config.update(test_config)

    @app.route("/")
    def index():
        return jsonify({
            "service": "Agent Storefront",
            "status": "online",
            "version": "0.1.0",
            "track": "AI Growth & Agentic Commerce",
            "docs": "/.well-known/agent-catalog.json",
        })

    @app.route("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": "agent-storefront",
        }), 200

    @app.route("/.well-known/agent-catalog.json", methods=["GET"])
    def agent_catalog():
        """Exposes structured, machine-readable product catalog for AI buyers."""
        from backend.catalog import get_catalog_manager

        catalog_mgr = get_catalog_manager(app.config.get("CATALOG_PATH"))
        return jsonify(catalog_mgr.get_agent_catalog()), 200

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
