# Agent Storefront

> **Razorpay AI Buildathon 2026** — *AI Growth & Agentic Commerce Track*

A reference implementation demonstrating how a merchant becomes **discoverable, negotiable, and purchasable by AI buyers** with strict server-side policy controls, deterministic guardrails, human approval gating, and full auditability.

---

## 🎯 Project Overview

As autonomous AI agents begin acting as purchasing delegates for consumers and businesses, commerce architectures must evolve beyond human-oriented HTML scraping to structured, machine-first protocols.

**Agent Storefront** provides:
- **Agent-Readable Product Catalog:** Machine-readable catalog exposed via `/.well-known/agent-catalog.json`.
- **Policy Engine & Guardrails:** Server-side bounding of discount requests, spend ceilings, upsell limits, and allowed SKUs.
- **Razorpay Integration:** Payment order creation and capture in Test Mode.
- **Human Approval Gating:** High-value transactions automatically paused for merchant sign-off.
- **Immutable Audit Trail:** Persistent SQLite log capturing all agent decisions, policy evaluations, and payment actions.
- **Deterministic Buyer Agent:** Simulation suite testing discovery, discount negotiation, rejection recovery, upsell, and checkout.

---

## 🏗️ Architecture

```text
                    AI BUYER AGENT
                          │
                          │ HTTP / JSON
                          ▼
              ┌───────────────────────┐
              │      Flask App        │
              │                       │
              │ Agent Catalog         │
              │ Cart                  │
              │ Discount              │
              │ Upsell                │
              │ Checkout              │
              │ Payment               │
              │ Audit                 │
              └──────────┬────────────┘
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
       POLICY ENGINE          RAZORPAY CLIENT
             │                       │
             │                       ▼
             │                Razorpay Test Mode
             │
             ▼
       ALLOW / REJECT /
       HUMAN APPROVAL
             │
             ▼
        AUDIT TRAIL
```

For a deeper dive into data flows and security boundaries, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd agent-storefront
   ```

2. Sync dependencies using `uv`:
   ```bash
   uv sync --extra dev
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

4. Run the development server:
   ```bash
   uv run python -m backend.app
   ```

5. Run test suite:
   ```bash
   uv run pytest
   ```

---

## 📋 Milestone Roadmap

- [x] **Milestone 1:** Project scaffolding & minimal Flask app
- [ ] **Milestone 2:** Agent-readable product catalog (`/.well-known/agent-catalog.json`)
- [ ] **Milestone 3:** Cart system (`/agent/cart`)
- [ ] **Milestone 4:** Policy engine & guardrails (`backend/policy.py`)
- [ ] **Milestone 5:** Discount negotiation & validation (`/agent/discount`)
- [ ] **Milestone 6:** Bounded upsell policy (`/agent/upsell`)
- [ ] **Milestone 7:** Persistent SQLite audit trail (`/audit`)
- [ ] **Milestone 8:** Policy-gated checkout (`/agent/checkout`)
- [ ] **Milestone 9:** Razorpay test-mode integration (`backend/razorpay_client.py`)
- [ ] **Milestone 10:** Human approval gate (orders > ₹5,000)
- [ ] **Milestone 11:** Graceful failure scenario (expired coupon recovery)
- [ ] **Milestone 12:** Buyer agent simulation (`buyer_agent/simulate_buyer.py`)
- [ ] **Milestone 13:** Merchant audit dashboard (`frontend/index.html`)
- [ ] **Milestone 14:** Full integration test suite
- [ ] **Milestone 15:** Documentation & architecture specifications
- [ ] **Milestone 16:** Final buildathon polish & submission
