# Agent Storefront — Architecture Specification

> **Razorpay AI Buildathon 2026** — *AI Growth & Agentic Commerce*

---

## 1. System Overview

Agent Storefront is a merchant-side gateway engineered to interface securely with AI Buyer Agents. Autonomous buyers discover inventory, negotiate discounts, manage carts, and execute checkout through programmatic APIs while strictly bounded by server-side policy engines, fraud guardrails, and persistent audit logs.

```text
[ AI Buyer Agent ]
       │
       │  HTTP / REST (JSON)
       ▼
[ Flask Commerce Service ]
   ├── Catalog Provider (/.well-known/agent-catalog.json)
   ├── Cart Manager (/agent/cart)
   ├── Discount Evaluator (/agent/discount)
   ├── Upsell Engine (/agent/upsell)
   ├── Checkout Controller (/agent/checkout)
   └── Payment Controller (/agent/payment/capture)
       │
       ├───► [ Policy Engine ]
       │        ├── Maximum Discount Check (≤ 15%)
       │        ├── Session Spend Ceiling Check (≤ ₹10,000)
       │        ├── Human Approval Gate Check (> ₹5,000)
       │        ├── Upsell Limit (≤ 1 per session)
       │        └── Allowed SKU Validator
       │
       ├───► [ Razorpay Client Interface ]
       │        ├── Orders API (order creation)
       │        └── Payments API (signature verification & capture)
       │
       └───► [ SQLite Audit Trail ]
                └── Tamper-evident ledger of all policy evaluations & transactions
```

---

## 2. Core Components

### 2.1 Backend Application (`backend/`)
- **`app.py`**: Flask application factory, routing, and lifecycle hooks.
- **`catalog.py`**: Serves structured product catalog and merchant metadata.
- **`store.py`**: In-memory/session-backed cart state management.
- **`policy.py`**: Deterministic policy engine returning structured `PolicyResult(allowed, reason, code)`.
- **`audit.py`**: Persistent audit logger recording every incoming request, actor, policy verdict, and payment transaction into SQLite.
- **`razorpay_client.py`**: Adapter providing seamless switching between Razorpay Test Mode and a mock test double.

### 2.2 Buyer Agent Simulation (`buyer_agent/`)
- **`simulate_buyer.py`**: A deterministic end-to-end execution script simulating discovery, shopping, invalid coupon rejection, recovery, upsell, and checkout with approval checks.

### 2.3 Frontend Dashboard (`frontend/`)
- Clean, reactive HTML/CSS/JS dashboard displaying catalog inventory, active carts, and real-time audit ledger entries.

---

## 3. Security & Policy Invariants

1. **Zero-Trust Client Input**: The server never trusts client-supplied prices, totals, or discount calculations. Every calculation is performed server-side against the canonical catalog.
2. **Policy Enforcement Precedence**: Checkout cannot proceed without explicit evaluation from the Policy Engine.
3. **High-Value Gating**: Transactions exceeding ₹5,000 are paused with `HUMAN_APPROVAL_REQUIRED` until signed off by the merchant.
4. **Audit Immutability**: All decisions (approved, rejected, or approval-required) are recorded with timestamps, session tokens, and reason codes.
5. **No Secret Leakage**: Razorpay secrets and private keys are strictly server-side and never exposed to the frontend or API consumers.
