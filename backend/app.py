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

    @app.route("/agent/cart", methods=["GET", "POST"])
    def agent_cart():
        """
        Manages agent shopping cart.
        Supports adding, updating, removing items, and fetching current cart state.
        """
        from flask import request
        from backend.store import get_store, CartError

        store = get_store()

        if request.method == "GET":
            session_id = request.args.get("session_id")
            cart = store.get_or_create_cart(session_id)
            return jsonify({
                "status": "success",
                "cart": cart.to_dict(),
            }), 200

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        action = data.get("action")
        sku = data.get("sku")
        quantity = data.get("quantity")

        # Fallback to session from query parameter if omitted in payload
        if not session_id:
            session_id = request.args.get("session_id")

        try:
            # If no action specified, infer from sku / quantity or default to add / get
            if not action:
                if sku:
                    action = "add"
                else:
                    action = "get"

            action = action.lower()

            if action == "get":
                cart_dict = store.get_cart_dict(session_id)
            elif action == "add":
                if not sku:
                    return jsonify({
                        "status": "error",
                        "code": "MISSING_SKU",
                        "message": "Field 'sku' is required for action 'add'.",
                    }), 400
                qty = 1 if quantity is None else quantity
                cart_dict = store.add_item(session_id, sku, qty)
            elif action == "update":
                if not sku:
                    return jsonify({
                        "status": "error",
                        "code": "MISSING_SKU",
                        "message": "Field 'sku' is required for action 'update'.",
                    }), 400
                if quantity is None:
                    return jsonify({
                        "status": "error",
                        "code": "MISSING_QUANTITY",
                        "message": "Field 'quantity' is required for action 'update'.",
                    }), 400
                cart_dict = store.update_item(session_id, sku, quantity)
            elif action == "remove":
                if not sku:
                    return jsonify({
                        "status": "error",
                        "code": "MISSING_SKU",
                        "message": "Field 'sku' is required for action 'remove'.",
                    }), 400
                cart_dict = store.remove_item(session_id, sku)
            elif action == "clear":
                cart_dict = store.clear_cart(session_id)
            else:
                return jsonify({
                    "status": "error",
                    "code": "INVALID_ACTION",
                    "message": f"Unknown action '{action}'. Valid: add, update, remove, clear, get.",
                }), 400

            return jsonify({
                "status": "success",
                "cart": cart_dict,
            }), 200

        except CartError as exc:
            return jsonify({
                "status": "error",
                "code": exc.code,
                "message": exc.message,
            }), exc.status_code

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
