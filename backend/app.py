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
        from backend.audit import get_audit_logger

        store = get_store()
        audit_logger = get_audit_logger(app.config.get("AUDIT_DB_PATH"))

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
                audit_logger.log(
                    session_id=session_id,
                    actor="buyer_agent",
                    action="cart_add",
                    payload_summary={"sku": sku, "quantity": qty},
                    policy_result="ALLOWED",
                    reason="Product added to cart",
                )
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
                audit_logger.log(
                    session_id=session_id,
                    actor="buyer_agent",
                    action="cart_update",
                    payload_summary={"sku": sku, "quantity": quantity},
                    policy_result="ALLOWED",
                    reason="Cart item updated",
                )
            elif action == "remove":
                if not sku:
                    return jsonify({
                        "status": "error",
                        "code": "MISSING_SKU",
                        "message": "Field 'sku' is required for action 'remove'.",
                    }), 400
                cart_dict = store.remove_item(session_id, sku)
                audit_logger.log(
                    session_id=session_id,
                    actor="buyer_agent",
                    action="cart_remove",
                    payload_summary={"sku": sku},
                    policy_result="ALLOWED",
                    reason="Cart item removed",
                )
            elif action == "clear":
                cart_dict = store.clear_cart(session_id)
                audit_logger.log(
                    session_id=session_id,
                    actor="buyer_agent",
                    action="cart_clear",
                    payload_summary={},
                    policy_result="ALLOWED",
                    reason="Cart cleared",
                )
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
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action=f"cart_{action or 'unknown'}",
                payload_summary=data,
                policy_result="REJECTED",
                reason=exc.message,
            )
            return jsonify({
                "status": "error",
                "code": exc.code,
                "message": exc.message,
            }), exc.status_code

    @app.route("/agent/discount", methods=["POST", "DELETE"])
    def agent_discount():
        """
        Validates and applies policy-bounded discount coupons to the agent's cart.
        Returns structured rejection if expired, invalid, or exceeding policy bounds.
        """
        from flask import request
        from backend.store import get_store
        from backend.policy import get_policy_engine
        from backend.catalog import get_catalog_manager
        from backend.audit import get_audit_logger

        store = get_store()
        policy_engine = get_policy_engine()
        catalog_mgr = get_catalog_manager()
        audit_logger = get_audit_logger(app.config.get("AUDIT_DB_PATH"))

        if request.method == "DELETE":
            session_id = request.args.get("session_id")
            cart_dict = store.remove_discount(session_id)
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="discount_remove",
                payload_summary={},
                policy_result="ALLOWED",
                reason="Discount removed from cart",
            )
            return jsonify({
                "status": "removed",
                "message": "Discount removed from cart.",
                "cart": cart_dict,
            }), 200

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id") or request.args.get("session_id")
        coupon_code = data.get("coupon_code", "").strip()
        action = data.get("action", "").lower()

        if action == "remove" or not coupon_code:
            cart_dict = store.remove_discount(session_id)
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="discount_remove",
                payload_summary={"action": "remove"},
                policy_result="ALLOWED",
                reason="Discount removed from cart",
            )
            return jsonify({
                "status": "removed",
                "message": "Discount removed from cart.",
                "cart": cart_dict,
            }), 200

        # Validate through policy engine
        policy_res = policy_engine.validate_coupon(coupon_code)

        if not policy_res.allowed:
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="discount_request",
                payload_summary={"coupon_code": coupon_code},
                policy_result="REJECTED",
                reason=policy_res.reason,
            )
            return jsonify({
                "status": "rejected",
                "reason": policy_res.reason,
                "code": policy_res.code,
                "cart": store.get_cart_dict(session_id),
            }), 200

        # Retrieve coupon details to calculate discount
        coupon = catalog_mgr.get_coupon(coupon_code)
        discount_pct = coupon.get("discount_pct", 0) if coupon else 0

        # Apply to session cart
        cart_dict = store.apply_discount(session_id, coupon_code, discount_pct)

        audit_logger.log(
            session_id=session_id or "unknown",
            actor="buyer_agent",
            action="discount_request",
            payload_summary={
                "coupon_code": coupon_code.upper(),
                "discount_pct": discount_pct,
                "discount_amount": cart_dict.get("discount_amount", 0),
            },
            policy_result="ALLOWED",
            reason=policy_res.reason,
        )

        return jsonify({
            "status": "applied",
            "coupon_code": coupon_code.upper(),
            "discount_pct": discount_pct,
            "discount_amount": cart_dict.get("discount_amount", 0),
            "cart": cart_dict,
            "policy_result": policy_res.to_dict(),
        }), 200

    @app.route("/agent/upsell", methods=["POST"])
    def agent_upsell():
        """
        Policy-controlled bounded upsell endpoint.
        Validates SKU, restricts upsells to 1 per session,
        and enforces session spend ceiling (₹10,000).
        """
        from flask import request
        from backend.store import get_store, CartError
        from backend.policy import get_policy_engine
        from backend.catalog import get_catalog_manager
        from backend.audit import get_audit_logger

        store = get_store()
        policy_engine = get_policy_engine()
        catalog_mgr = get_catalog_manager()
        audit_logger = get_audit_logger(app.config.get("AUDIT_DB_PATH"))

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id") or request.args.get("session_id")
        upsell_sku = data.get("sku") or data.get("upsell_sku")

        if not upsell_sku:
            return jsonify({
                "status": "rejected",
                "reason": "Field 'sku' or 'upsell_sku' is required for upsell.",
                "code": "MISSING_SKU",
                "cart": store.get_cart_dict(session_id),
            }), 200

        cart = store.get_or_create_cart(session_id)
        product = catalog_mgr.get_product(upsell_sku)
        upsell_price = product["price"] if product else 0

        # Validate through policy engine
        policy_res = policy_engine.validate_upsell(
            current_upsells_count=cart.upsells_count,
            upsell_sku=upsell_sku,
            current_total=cart.total,
            upsell_price=upsell_price,
        )

        if not policy_res.allowed:
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="upsell_request",
                payload_summary={"sku": upsell_sku, "price": upsell_price},
                policy_result="REJECTED",
                reason=policy_res.reason,
            )
            return jsonify({
                "status": "rejected",
                "reason": policy_res.reason,
                "code": policy_res.code,
                "cart": cart.to_dict(),
                "policy_result": policy_res.to_dict(),
            }), 200

        try:
            updated_cart = store.add_upsell_item(session_id, upsell_sku)
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="upsell_request",
                payload_summary={"sku": upsell_sku, "price": upsell_price},
                policy_result="ALLOWED",
                reason=policy_res.reason,
            )
        except CartError as exc:
            audit_logger.log(
                session_id=session_id or "unknown",
                actor="buyer_agent",
                action="upsell_request",
                payload_summary={"sku": upsell_sku},
                policy_result="REJECTED",
                reason=exc.message,
            )
            return jsonify({
                "status": "rejected",
                "reason": exc.message,
                "code": exc.code,
                "cart": cart.to_dict(),
            }), 200

        return jsonify({
            "status": "applied",
            "message": f"Upsell product '{product['name']}' added to cart.",
            "upsell_sku": upsell_sku,
            "cart": updated_cart,
            "policy_result": policy_res.to_dict(),
        }), 200

    @app.route("/audit", methods=["GET"])
    def get_audit_trail():
        """Exposes immutable audit trail records for merchant review."""
        from flask import request
        from backend.audit import get_audit_logger

        audit_logger = get_audit_logger(app.config.get("AUDIT_DB_PATH"))
        session_id = request.args.get("session_id")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        entries = audit_logger.get_entries(session_id=session_id, limit=limit, offset=offset)
        return jsonify({
            "status": "success",
            "count": len(entries),
            "audit_trail": entries,
        }), 200

    @app.route("/agent/checkout", methods=["POST"])
    def agent_checkout():
        """
        Executes policy-gated checkout.
        Validates cart, enforces spend ceilings, checks human approval thresholds,
        records audit entries, and generates order reference.
        """
        import uuid
        from flask import request
        from backend.store import get_store
        from backend.policy import get_policy_engine
        from backend.audit import get_audit_logger

        store = get_store()
        policy_engine = get_policy_engine()
        audit_logger = get_audit_logger(app.config.get("AUDIT_DB_PATH"))

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id") or request.args.get("session_id")
        buyer_info = data.get("buyer_info", {})

        if not session_id:
            return jsonify({
                "status": "rejected",
                "code": "MISSING_SESSION_ID",
                "reason": "Session ID is required for checkout.",
            }), 400

        cart = store.get_cart_dict(session_id)

        # 1. Cart Validation
        if cart.get("item_count", 0) <= 0 or not cart.get("items"):
            audit_logger.log(
                session_id=session_id,
                actor="buyer_agent",
                action="checkout",
                payload_summary={"buyer_info": buyer_info},
                policy_result="REJECTED",
                reason="Cannot checkout with an empty cart.",
            )
            return jsonify({
                "status": "rejected",
                "code": "EMPTY_CART",
                "reason": "Cannot checkout with an empty cart.",
                "cart": cart,
            }), 200

        order_total = cart.get("total", 0)

        # 2. Spend Ceiling Check (<= ₹10,000)
        spend_res = policy_engine.check_spend_ceiling(order_total)
        if not spend_res.allowed:
            audit_logger.log(
                session_id=session_id,
                actor="buyer_agent",
                action="checkout",
                payload_summary={"amount": order_total, "buyer_info": buyer_info},
                policy_result="REJECTED",
                reason=spend_res.reason,
            )
            return jsonify({
                "status": "rejected",
                "code": spend_res.code,
                "reason": spend_res.reason,
                "cart": cart,
                "policy_result": spend_res.to_dict(),
            }), 200

        # 3. Human Approval Threshold Check (> ₹5,000)
        approval_res = policy_engine.check_human_approval(order_total)
        if not approval_res.allowed:
            audit_logger.log(
                session_id=session_id,
                actor="buyer_agent",
                action="checkout",
                payload_summary={"amount": order_total, "buyer_info": buyer_info},
                policy_result="HUMAN_APPROVAL_REQUIRED",
                reason=approval_res.reason,
            )
            return jsonify({
                "status": "approval_required",
                "code": approval_res.code,
                "reason": approval_res.reason,
                "amount": order_total,
                "currency": cart.get("currency", "INR"),
                "cart": cart,
                "policy_result": approval_res.to_dict(),
            }), 200

        # 4. Standard autonomous checkout approved
        order_id = f"order_{uuid.uuid4().hex[:14]}"
        audit_logger.log(
            session_id=session_id,
            actor="buyer_agent",
            action="checkout",
            payload_summary={"amount": order_total, "buyer_info": buyer_info},
            policy_result="ALLOWED",
            reason="Order approved within autonomous policy boundaries.",
            razorpay_ref=order_id,
        )

        return jsonify({
            "status": "success",
            "order_id": order_id,
            "amount": order_total,
            "currency": cart.get("currency", "INR"),
            "cart": cart,
            "policy_result": approval_res.to_dict(),
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
