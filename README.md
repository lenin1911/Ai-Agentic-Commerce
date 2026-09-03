# Agent Storefront

> **Razorpay AI Buildathon 2026** — *AI Growth & Agentic Commerce Track*  
> A reference implementation demonstrating how merchants become **discoverable, negotiable, and purchasable by AI buyers** with strict server-side policy guardrails, human approval gating, and immutable auditability.

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Problem Being Solved](#-problem-being-solved)
- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Setup & Installation](#-setup--installation-using-uv)
- [Environment Variables](#-environment-variables)
- [Running the Backend](#-running-the-backend)
- [Running the Buyer Agent Simulation](#-running-the-buyer-agent-simulation)
- [Using the Merchant Dashboard](#-using-the-merchant-dashboard)
- [API Endpoint Summary](#-api-endpoint-summary)
- [Merchant Policy Rules](#-merchant-policy-rules)
- [Razorpay Test Mode & Mock Fallback](#-razorpay-test-mode--mock-fallback)
- [Example Agent Flow](#-example-agent-flow)
- [Deliberate Failure & Recovery Scenario](#-deliberate-failure--recovery-scenario)
- [Testing Instructions](#-testing-instructions)
- [Architecture & Data Flow](#-architecture--data-flow)
- [Reference Implementation Notice](#-reference-implementation-notice)

---

## 🎯 Overview

As autonomous AI agents evolve from conversational assistants into purchasing delegates for consumers and enterprises, commerce systems must transition from human-centric HTML storefronts to machine-first API protocols.

**Agent Storefront** is a reference architecture showing how a merchant can expose its inventory to AI agents while retaining full sovereignty over pricing, inventory, discount ceilings, and money movement. Every state change and transaction is bounded by server-side policy checks, gated by human supervisor approval when exceeding financial thresholds, and permanently recorded in an immutable audit ledger.

---

## 💡 Problem Being Solved

Traditional e-commerce is fundamentally ill-suited for autonomous AI buyers:
1. **Unstructured Scraping vs. Protocol Discovery:** Agents scraping HTML faces fragile selectors, bot blocks, and hallucinations. Merchants need a machine-readable discovery standard (`/.well-known/agent-catalog.json`).
2. **Unbounded Agent Actions:** Autonomous agents given open payment instruments can overspend, exploit infinite discounts, or flood inventory without guardrails.
3. **Lack of Human Oversight on High-Value Orders:** Merchants cannot risk autonomous agents placing multi-thousand rupee orders without supervisor sign-off.
4. **Opaque Agent Interventions:** Merchants lack forensic visibility into why an agent purchase failed or succeeded, requiring an immutable, tamper-evident audit trail.

---

## 🏗 System Architecture

```text
                               AI BUYER AGENT / SIMULATOR
                                           │
                       HTTP / REST (JSON)  │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AGENT STOREFRONT (Flask Backend)                      │
│                                                                                 │
│   /.well-known/agent-catalog.json    │   /agent/cart         │   /agent/discount │
│   /agent/upsell                      │   /agent/checkout     │   /agent/approval │
│   /agent/payment/capture             │   /audit              │   /dashboard      │
└───────────────┬──────────────────────────┬─────────────────────────────┬────────┘
                │                          │                             │
                ▼                          ▼                             ▼
┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────┐
│       POLICY ENGINE       │ │      IN-MEMORY STORE      │ │    RAZORPAY CLIENT    │
│                           │ │                           │ │                       │
│ • SKU & Stock Eligibility │ │ • Session-scoped Carts    │ │ • Live Razorpay Test  │
│ • Discount Ceiling (≤15%) │ │ • Subtotal Calculation    │ │   Mode (with API keys)│
│ • Expired Coupon Check    │ │ • Discount Computation    │ │ • Deterministic Mock  │
│ • Spend Ceiling (≤₹10,000)│ │ • State Reset & Settlement│ │   Fallback (zero-key) │
│ • Human Approval (≥₹5,000)│ └───────────────────────────┘ └───────────┬───────────┘
│ • Upsell Bounding (≤1)    │                                           │
└───────────────┬───────────┘                                           │
                │                                                       │
                ▼                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      IMMUTABLE SQLITE AUDIT TRAIL (audit.db)                     │
│  Timestamped records of actor, action, payload, policy verdict, & Razorpay ref   │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
                       MERCHANT DASHBOARD (Vanilla HTML/CSS/JS)
```

---

## ✨ Key Features

- **Agent-Readable Catalog:** Standardized JSON catalog at `/.well-known/agent-catalog.json` specifying SKU metadata, pricing, stock levels, and store policies.
- **Server-Side Policy Engine:** Strict guardrails preventing price tampering, unauthorized discounts, and runaway spending.
- **Human Approval Gate:** Automatically halts checkout for orders ≥ ₹5,000, requiring supervisor approval via `/agent/approval` before proceeding.
- **Bounded Upsell Engine:** Permits algorithmic upsells within strict limits (max 1 upsell per session and total within spend ceiling).
- **Deliberate Failure & Recovery:** Demonstrates graceful recovery when an expired coupon (`SUMMER10`) is rejected with `COUPON_EXPIRED`, allowing the agent to proceed to full-price checkout without state corruption.
- **Dual-Mode Razorpay Gateway:** Seamless switching between Razorpay Test Mode and an offline deterministic mock client.
- **Immutable SQLite Audit Trail:** Complete tamper-evident event log capturing every policy evaluation, rejection, approval, and settlement.
- **Deterministic Buyer Agent:** Autonomous agent simulation (`buyer_agent/simulate_buyer.py`) executing a full 10-step purchasing flow.
- **Merchant Web Console:** High-aesthetic, responsive dark-mode dashboard at `/dashboard` built in vanilla HTML/CSS/JS.

---

## 🛠 Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| **Runtime & Backend** | Python 3.11+, Flask 3.0+ | Lightweight, standards-compliant REST architecture |
| **Package Manager** | `uv` (Astral) | Extremely fast, reproducible virtualenv & package management |
| **Audit Ledger** | SQLite3 (Standard Library) | Zero-external-dependency, ACID-compliant immutable event log |
| **Payment Gateway** | Razorpay Python SDK + Mock Client | Official Razorpay API integration with judge-friendly zero-credential mock fallback |
| **Testing** | Pytest 9.x | Comprehensive unit, policy, simulation, and end-to-end integration tests |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript | Zero framework bloat, fast rendering, glassmorphic dark mode |

---

## 📦 Setup & Installation (Using `uv`)

### Prerequisites
- Python 3.11 or higher
- [`uv`](https://github.com/astral-sh/uv) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `pip install uv`)

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/lenin1911/Ai-Agentic-Commerce.git
   cd Ai-Agentic-Commerce
   ```

2. Synchronize dependencies using `uv`:
   ```bash
   uv sync --extra dev
   ```

3. Create your local environment configuration:
   ```bash
   cp .env.example .env
   ```

---

## 🔐 Environment Variables

The project works completely out-of-the-box using safe defaults and deterministic mocks. You can optionally configure real Razorpay Test Mode credentials in `.env`:

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Flask runtime environment |
| `FLASK_PORT` | `5000` | Port for the backend API and dashboard |
| `SECRET_KEY` | `dev-secret-key-change-in-prod` | Session secret key |
| `CATALOG_PATH` | `data/catalog_seed.json` | Path to product catalog seed JSON |
| `AUDIT_DB_PATH` | `audit.db` | Path to SQLite audit ledger database |
| `MAX_DISCOUNT_PCT` | `15` | Maximum allowable discount percentage ceiling |
| `MAX_UPSELLS_PER_SESSION` | `1` | Maximum allowable upsells per buyer session |
| `SESSION_SPEND_CEILING` | `10000` | Maximum allowable spend per session in INR |
| `HUMAN_APPROVAL_THRESHOLD` | `5000` | Order total in INR triggering human supervisor review |
| `RAZORPAY_KEY_ID` | *optional* | Razorpay Test Key ID (`rzp_test_...`) |
| `RAZORPAY_KEY_SECRET` | *optional* | Razorpay Test Key Secret |
| `FORCE_MOCK_RAZORPAY` | `false` | Force deterministic mock client even if keys are set |

---

## 🚀 Running the Backend

Start the Flask server using `uv`:

```bash
uv run python -m backend.app
```

The server will initialize on `http://127.0.0.1:5000`:
- **API Root:** `http://127.0.0.1:5000/`
- **Health Check:** `http://127.0.0.1:5000/health`
- **Agent Catalog:** `http://127.0.0.1:5000/.well-known/agent-catalog.json`
- **Merchant Dashboard:** `http://127.0.0.1:5000/dashboard`

---

## 🤖 Running the Buyer Agent Simulation

The repository includes a deterministic AI buyer simulation that interacts strictly through the backend HTTP APIs.

Run against the running backend server:
```bash
uv run python buyer_agent/simulate_buyer.py
```

### Simulation Command-Line Options

```bash
# Exercise high-value human approval gate (quantity=2, total=₹8,400 ≥ ₹5,000)
uv run python buyer_agent/simulate_buyer.py --require-approval

# Purchase a specific SKU
uv run python buyer_agent/simulate_buyer.py --sku USB-CORAL-TPU-02 --quantity 1

# Execute standalone in-process via Flask test client without a running server
uv run python buyer_agent/simulate_buyer.py --in-process

# Target a custom base URL
uv run python buyer_agent/simulate_buyer.py --base-url http://localhost:5000
```

---

## 🖥 Using the Merchant Dashboard

Open `http://127.0.0.1:5000/dashboard` in any web browser.

### Key Sections:
1. **Header & Session Control:** Switch between buyer sessions (e.g. `demo_session` or simulation sessions), create clean sessions, and monitor API connectivity.
2. **Overview Metric Cards:** Real-time visibility into cart totals, discount status, upsell usage, approval gate status, and payment state.
3. **Product Catalog:** Live product cards from `/.well-known/agent-catalog.json` with direct "+ Add to Cart" action buttons.
4. **Agent Shopping Cart:** Real-time item listing, quantity adjusters, item removal, and subtotal/total calculations.
5. **Coupon Testing Panel:** Test valid discounts (`WELCOME10`), expired discounts (`SUMMER10`), or ceiling-exceeding discounts (`EXCESSIVE50`).
6. **Bounded Upsells:** Add approved companion accessories within policy bounds.
7. **Human Approval Gate:** Interactive banner that automatically triggers when cart total ≥ ₹5,000, allowing the merchant to approve or reject the order.
8. **Live Immutable Audit Ledger:** Real-time stream of all policy verdicts, coupon rejections, supervisor sign-offs, and Razorpay payment references.

---

## 📡 API Endpoint Summary

| Endpoint | Method | Description | Sample Status |
|---|---|---|---|
| `GET /` | `GET` | Service index & metadata | 200 OK |
| `GET /health` | `GET` | Health check probe | 200 OK |
| `GET /.well-known/agent-catalog.json` | `GET` | Machine-readable catalog & policies for AI agents | 200 OK |
| `GET /dashboard` | `GET` | Serves merchant web dashboard | 200 OK |
| `GET /agent/cart` | `GET` | Retrieves active cart for session | 200 OK |
| `POST /agent/cart` | `POST` | Add, update, remove, or clear items in cart | 200 / 400 |
| `POST /agent/discount` | `POST` | Validates & applies policy-gated coupon code | 200 OK (applied / rejected) |
| `DELETE /agent/discount` | `DELETE` | Removes applied discount from cart | 200 OK |
| `POST /agent/upsell` | `POST` | Applies policy-bounded companion upsell item | 200 OK (applied / rejected) |
| `POST /agent/checkout` | `POST` | Policy-gated checkout; triggers Razorpay order | 200 OK (success / approval_required / rejected) |
| `POST /agent/approval` | `POST` | Merchant supervisor sign-off gate | 200 OK |
| `POST /agent/payment/capture` | `POST` | Captures payment & settles order | 200 / 400 |
| `GET /audit` | `GET` | Queries immutable SQLite audit ledger | 200 OK |

---

## 🛡 Merchant Policy Rules

Every transaction is evaluated server-side against strict invariants defined in `backend/policy.py`:

1. **SKU & Stock Eligibility:**
   - Products must exist in the merchant catalog, have `agent_eligible: true`, and have `stock > 0`.
   - Rejection codes: `SKU_NOT_FOUND`, `SKU_NOT_ELIGIBLE`, `OUT_OF_STOCK`.
2. **Discount Ceiling Policy:**
   - Discounts cannot exceed **15%** (`MAX_DISCOUNT_PCT`).
   - Rejection code: `DISCOUNT_EXCEEDS_POLICY_MAX`.
3. **Coupon Expiration Policy:**
   - Expired promotional codes are rejected cleanly with HTTP 200.
   - Rejection code: `COUPON_EXPIRED`.
4. **Bounded Upsell Policy:**
   - Agents are restricted to a maximum of **1 upsell** per session.
   - Rejection code: `UPSELL_LIMIT_EXCEEDED`.
5. **Session Spend Ceiling:**
   - Total cart value cannot exceed **₹10,000** (`SESSION_SPEND_CEILING`).
   - Rejection code: `SPEND_CEILING_EXCEEDED`.
6. **Human Approval Threshold:**
   - Orders with total **≥ ₹5,000** require explicit merchant supervisor sign-off.
   - Status code: `HUMAN_APPROVAL_REQUIRED`.

---

## 💳 Razorpay Test Mode & Mock Fallback

The backend provides a robust dual-mode payment implementation in `backend/razorpay_client.py`:

- **Test Mode (with API Keys):** If `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are provided in `.env`, the client connects to official Razorpay Test Mode APIs to create orders and capture payments.
- **Deterministic Mock Fallback (Zero Credentials):** If credentials are not supplied (or if `FORCE_MOCK_RAZORPAY=true`), the system automatically switches to `MockRazorpayClient`. The mock generates deterministic `order_mock_...` and `pay_mock_...` identifiers, accurately computes paise amounts, and settles payments without external network dependencies.

---

## 🔄 Example Agent Flow

Below is the standard 10-step lifecycle of an AI buyer interacting with the Agent Storefront:

```text
1. Discover Catalog     GET /.well-known/agent-catalog.json  --> Discovers products & policies
2. Select Product       Filters for agent_eligible & in_stock --> Selects EDGE-DEV-KIT-01 (₹4,200)
3. Add to Cart          POST /agent/cart                    --> Cart subtotal: ₹4,200
4. Attempt Coupon       POST /agent/discount (SUMMER10)     --> Expired coupon attempted
5. Receive Rejection    Status 200 OK                       --> code: COUPON_EXPIRED
6. Recover to Full Price Cart remains uncorrupted            --> Total remains ₹4,200
7. Attempt Checkout     POST /agent/checkout                --> Initiates checkout
8. Approval Gate Check  Check amount < ₹5,000               --> Autonomous approval granted
9. Capture Payment      POST /agent/payment/capture         --> Settled via Razorpay mock
10. Verify Audit Log    GET /audit?session_id=...           --> All actions logged immutably
```

---

## ⚡ Deliberate Failure & Recovery Scenario

To prove agentic resilience, Milestone 11 implements a deliberate coupon failure scenario:

1. The buyer agent attempts to apply expired coupon `SUMMER10`.
2. The policy engine rejects it with a **structured HTTP 200 OK** (not an unhandled HTTP 500 error):
   ```json
   {
     "status": "rejected",
     "code": "COUPON_EXPIRED",
     "reason": "Coupon 'SUMMER10' expired on 2024-06-30.",
     "cart": { "subtotal": 4200, "discount_amount": 0, "total": 4200 }
   }
   ```
3. The session cart is **not corrupted** and retains its full-price state.
4. The agent can seamlessly continue to checkout at full price (₹4,200).
5. Both the rejection (`DISCOUNT_REQUEST` / `REJECTED`) and the subsequent settlement (`CHECKOUT` / `ALLOWED`) are recorded in the audit trail.

---

## 🧪 Testing Instructions

Run the complete test suite using `uv`:

```bash
uv run pytest
```

### Test Coverage Summary:
- `tests/test_catalog.py`: Catalog schema, agent-readability, and SKU filtering.
- `tests/test_cart.py`: Cart item addition, updates, removals, subtotal calculations, and stock checks.
- `tests/test_policy.py`: Server-side policy engine invariants, discount ceilings, and approval gates.
- `tests/test_discount.py`: Valid coupon discounts, expired coupon rejection, and recovery flows.
- `tests/test_upsell.py`: Bounded upsell policy (1 max per session) and spend ceiling constraints.
- `tests/test_checkout.py`: Policy-gated checkout validation and order generation.
- `tests/test_approval.py`: Human approval gate trigger (≥ ₹5,000), approval sign-off, and rejection handling.
- `tests/test_razorpay.py`: Razorpay order creation, payment capture, and mock fallback.
- `tests/test_audit.py`: SQLite audit trail persistence, schema, querying, and immutability.
- `tests/test_buyer_simulation.py`: Deterministic buyer agent 10-step simulation flows.
- `tests/test_dashboard.py`: Frontend dashboard serving, static assets, and CORS integration.
- `tests/test_integration.py`: Full end-to-end 11-step integration tests.

---

## 🏛 Architecture & Data Flow

Detailed architectural specifications, request/response models, and data sequence diagrams are maintained in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## ⚠️ Reference Implementation Notice

> **IMPORTANT DISCLAIMER:** This project is an architectural reference implementation created for the **Razorpay AI Buildathon 2026** to explore bounded agentic commerce. It is designed to demonstrate safe patterns for autonomous purchasing, policy evaluation, and auditability. It is not intended as an unsupported, production-ready payment gateway without enterprise security auditing, production secrets management, and distributed state persistence.
