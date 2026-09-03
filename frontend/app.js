/**
 * Agent Storefront — Merchant Dashboard Logic
 * Connects directly to backend Flask APIs:
 * - /.well-known/agent-catalog.json
 * - /agent/cart
 * - /agent/discount
 * - /agent/upsell
 * - /agent/checkout
 * - /agent/approval
 * - /agent/payment/capture
 * - /audit
 */

// Detect API base URL
const API_BASE = (window.location.protocol === 'file:' || !window.location.port)
  ? 'http://127.0.0.1:5000'
  : window.location.origin;

let currentSessionId = localStorage.getItem('agent_session_id') || 'demo_session';
let autoRefreshTimer = null;
let catalogCache = null;
let currentCart = null;
let pendingOrderId = null;

// DOM Elements
const sessionInput = document.getElementById('session-id-input');
const connectionStatus = document.getElementById('connection-status');
const catalogContainer = document.getElementById('catalog-container');
const cartItemsContainer = document.getElementById('cart-items-container');
const cartSubtotalEl = document.getElementById('cart-subtotal');
const cartDiscountRow = document.getElementById('cart-discount-row');
const cartDiscountEl = document.getElementById('cart-discount');
const cartTotalEl = document.getElementById('cart-total');
const cartTotalBadge = document.getElementById('stat-cart-total');
const cartItemsCountBadge = document.getElementById('stat-cart-items');
const discountStatusBadge = document.getElementById('stat-discount-status');
const upsellStatusBadge = document.getElementById('stat-upsell-status');
const approvalStatusBadge = document.getElementById('stat-approval-status');
const paymentStatusBadge = document.getElementById('stat-payment-status');
const discountAlertEl = document.getElementById('discount-alert');
const checkoutSectionEl = document.getElementById('checkout-section');
const approvalGateSectionEl = document.getElementById('approval-gate-section');
const auditLogContainer = document.getElementById('audit-log-container');
const autoRefreshCheckbox = document.getElementById('auto-refresh-toggle');

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
  sessionInput.value = currentSessionId;
  setupEventListeners();
  checkBackendHealth();
  loadCatalog();
  loadCart();
  loadAuditLogs();
  setupAutoRefresh();
});

function setupEventListeners() {
  document.getElementById('btn-update-session').addEventListener('click', () => {
    const val = sessionInput.value.trim();
    if (val) switchSession(val);
  });

  document.getElementById('btn-new-session').addEventListener('click', () => {
    const newId = 'session_' + Math.random().toString(36).substring(2, 10);
    switchSession(newId);
  });

  document.getElementById('btn-apply-coupon').addEventListener('click', () => {
    const code = document.getElementById('coupon-code-input').value.trim();
    if (code) applyCoupon(code);
  });

  document.getElementById('btn-remove-coupon').addEventListener('click', removeCoupon);
  document.getElementById('btn-clear-cart').addEventListener('click', clearCart);
  document.getElementById('btn-checkout').addEventListener('click', initiateCheckout);
  document.getElementById('btn-refresh-audit').addEventListener('click', loadAuditLogs);

  // Quick coupon chip buttons
  document.querySelectorAll('.chip[data-coupon]').forEach(chip => {
    chip.addEventListener('click', () => {
      const code = chip.getAttribute('data-coupon');
      document.getElementById('coupon-code-input').value = code;
      applyCoupon(code);
    });
  });

  // Auto refresh toggle
  if (autoRefreshCheckbox) {
    autoRefreshCheckbox.addEventListener('change', () => {
      if (autoRefreshCheckbox.checked) {
        setupAutoRefresh();
      } else if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
      }
    });
  }
}

function switchSession(newId) {
  currentSessionId = newId;
  sessionInput.value = newId;
  localStorage.setItem('agent_session_id', newId);
  pendingOrderId = null;
  resetAlerts();
  loadCart();
  loadAuditLogs();
}

function setupAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(() => {
    if (document.hidden) return;
    loadCart(true);
    loadAuditLogs(true);
  }, 3000);
}

// Backend Health Check
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      connectionStatus.innerHTML = '<span class="status-dot"></span> Online (Port 5000)';
      connectionStatus.style.background = 'rgba(16, 185, 129, 0.12)';
      connectionStatus.style.color = '#10b981';
    } else {
      throw new Error(`Status ${res.status}`);
    }
  } catch (err) {
    connectionStatus.innerHTML = '<span class="status-dot" style="background:#ef4444;box-shadow:0 0 8px #ef4444;"></span> Offline / Disconnected';
    connectionStatus.style.background = 'rgba(239, 68, 68, 0.12)';
    connectionStatus.style.color = '#ef4444';
  }
}

// Load Catalog
async function loadCatalog() {
  try {
    const res = await fetch(`${API_BASE}/.well-known/agent-catalog.json`);
    const data = await res.json();
    catalogCache = data;
    renderCatalog(data.products || []);
    renderUpsells(data.products || []);
  } catch (err) {
    catalogContainer.innerHTML = `<div class="empty-state">Failed to load catalog: ${err.message}</div>`;
  }
}

function renderCatalog(products) {
  if (!products.length) {
    catalogContainer.innerHTML = '<div class="empty-state">No products found in catalog.</div>';
    return;
  }

  catalogContainer.innerHTML = products.map(p => {
    const isEligible = p.agent_eligible;
    const inStock = p.in_stock !== false && (p.stock_quantity > 0 || p.stock > 0);
    return `
      <div class="product-card">
        <div>
          <div class="product-header">
            <span class="product-name">${p.name}</span>
            <span class="sku-tag">${p.sku}</span>
          </div>
          <p class="product-desc">${p.description}</p>
          <div style="display:flex;gap:6px;margin-bottom:8px;">
            <span class="panel-badge">${p.category || 'Gear'}</span>
            ${isEligible ? '<span class="panel-badge" style="color:#10b981;border-color:rgba(16,185,129,0.3)">Agent Eligible</span>' : '<span class="panel-badge" style="color:#ef4444;border-color:rgba(239,68,68,0.3)">Restricted</span>'}
          </div>
        </div>
        <div class="product-footer">
          <span class="product-price">₹${p.price.toLocaleString()}</span>
          ${isEligible && inStock ? `
            <button class="btn btn-primary btn-sm" onclick="addToCart('${p.sku}', 1)">
              + Add to Cart
            </button>
          ` : `
            <button class="btn btn-secondary btn-sm" disabled>
              ${!inStock ? 'Out of Stock' : 'Ineligible'}
            </button>
          `}
        </div>
      </div>
    `;
  }).join('');
}

function renderUpsells(products) {
  const upsellContainer = document.getElementById('upsell-container');
  if (!upsellContainer) return;

  // Filter products suitable for upsells (< 1500)
  const upsellCandidates = products.filter(p => p.agent_eligible && p.price < 1500);

  upsellContainer.innerHTML = upsellCandidates.map(p => `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#151d2f;border:1px solid var(--border-color);border-radius:var(--radius-sm);margin-bottom:8px;">
      <div>
        <div style="font-size:13px;font-weight:600;">${p.name}</div>
        <div style="font-size:11px;color:var(--text-muted);">${p.sku} — ₹${p.price}</div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="applyUpsell('${p.sku}')">
        + Upsell (1/session)
      </button>
    </div>
  `).join('');
}

// Load Cart
async function loadCart(silent = false) {
  try {
    const res = await fetch(`${API_BASE}/agent/cart?session_id=${encodeURIComponent(currentSessionId)}`);
    const data = await res.json();
    currentCart = data.cart;
    renderCart(currentCart);
    updateStatHighlights(currentCart);
  } catch (err) {
    if (!silent) console.error('Failed to load cart:', err);
  }
}

function renderCart(cart) {
  const items = cart.items || [];

  if (!items.length) {
    cartItemsContainer.innerHTML = '<div class="empty-state">Cart is currently empty. Click "+ Add to Cart" on any catalog item above.</div>';
    cartSubtotalEl.textContent = '₹0';
    cartDiscountRow.style.display = 'none';
    cartTotalEl.textContent = '₹0';
    return;
  }

  cartItemsContainer.innerHTML = items.map(item => `
    <div class="cart-item-row">
      <div class="cart-item-info">
        <span class="cart-item-name">${item.name}</span>
        <span class="cart-item-sku">${item.sku} @ ₹${item.unit_price.toLocaleString()}</span>
      </div>
      <div class="cart-item-actions">
        <div class="qty-control">
          <button class="qty-btn" onclick="updateItemQty('${item.sku}', ${item.quantity - 1})">-</button>
          <span style="font-size:12px;font-weight:600;min-width:16px;text-align:center;">${item.quantity}</span>
          <button class="qty-btn" onclick="updateItemQty('${item.sku}', ${item.quantity + 1})">+</button>
        </div>
        <span style="font-size:13px;font-weight:600;min-width:60px;text-align:right;">₹${item.total_price.toLocaleString()}</span>
        <button class="btn btn-danger btn-sm" onclick="removeItem('${item.sku}')">✕</button>
      </div>
    </div>
  `).join('');

  cartSubtotalEl.textContent = `₹${cart.subtotal.toLocaleString()}`;

  if (cart.discount_amount > 0 && cart.applied_coupon) {
    cartDiscountRow.style.display = 'flex';
    cartDiscountEl.textContent = `-₹${cart.discount_amount.toLocaleString()} (${cart.applied_coupon.code})`;
  } else {
    cartDiscountRow.style.display = 'none';
  }

  cartTotalEl.textContent = `₹${cart.total.toLocaleString()}`;
}

function updateStatHighlights(cart) {
  cartTotalBadge.textContent = `₹${(cart.total || 0).toLocaleString()}`;
  cartItemsCountBadge.textContent = `${cart.item_count || 0} item${cart.item_count === 1 ? '' : 's'}`;

  // Discount status
  if (cart.applied_coupon) {
    discountStatusBadge.textContent = `${cart.applied_coupon.code} (-${cart.applied_coupon.discount_pct}%)`;
    discountStatusBadge.style.color = '#10b981';
  } else {
    discountStatusBadge.textContent = 'No Discount';
    discountStatusBadge.style.color = '#94a3b8';
  }

  // Upsell status
  const upsells = cart.upsells_count || 0;
  upsellStatusBadge.textContent = `${upsells} / 1 Applied`;
  upsellStatusBadge.style.color = upsells >= 1 ? '#f59e0b' : '#06b6d4';

  // Human approval status
  if (cart.approval_decision === 'approved') {
    approvalStatusBadge.textContent = 'Approved by Human';
    approvalStatusBadge.style.color = '#10b981';
  } else if (cart.approval_decision === 'rejected') {
    approvalStatusBadge.textContent = 'Rejected by Supervisor';
    approvalStatusBadge.style.color = '#ef4444';
  } else if ((cart.total || 0) >= 5000) {
    approvalStatusBadge.textContent = 'Approval Required (≥ ₹5,000)';
    approvalStatusBadge.style.color = '#f59e0b';
  } else {
    approvalStatusBadge.textContent = 'Autonomous (< ₹5,000)';
    approvalStatusBadge.style.color = '#34d399';
  }
}

// Cart Operations
async function addToCart(sku, quantity = 1) {
  try {
    const res = await fetch(`${API_BASE}/agent/cart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, action: 'add', sku, quantity })
    });
    const data = await res.json();
    if (res.ok) {
      loadCart();
      loadAuditLogs();
    } else {
      alert(`Cart Error: ${data.message || data.reason}`);
    }
  } catch (err) {
    alert(`Request failed: ${err.message}`);
  }
}

async function updateItemQty(sku, newQty) {
  if (newQty <= 0) {
    removeItem(sku);
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/agent/cart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, action: 'update', sku, quantity: newQty })
    });
    if (res.ok) {
      loadCart();
      loadAuditLogs();
    }
  } catch (err) {
    console.error(err);
  }
}

async function removeItem(sku) {
  try {
    const res = await fetch(`${API_BASE}/agent/cart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, action: 'remove', sku })
    });
    if (res.ok) {
      loadCart();
      loadAuditLogs();
    }
  } catch (err) {
    console.error(err);
  }
}

async function clearCart() {
  try {
    const res = await fetch(`${API_BASE}/agent/cart`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, action: 'clear' })
    });
    if (res.ok) {
      loadCart();
      loadAuditLogs();
      resetAlerts();
    }
  } catch (err) {
    console.error(err);
  }
}

// Discount Operations (Including Expired Recovery Handling)
async function applyCoupon(couponCode) {
  resetAlerts();
  try {
    const res = await fetch(`${API_BASE}/agent/discount`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, coupon_code: couponCode })
    });
    const data = await res.json();

    if (data.status === 'rejected') {
      discountAlertEl.className = 'alert-banner alert-danger';
      discountAlertEl.style.display = 'flex';
      discountAlertEl.innerHTML = `
        <div>
          <strong>Policy Rejection [${data.code || 'COUPON_REJECTED'}]:</strong> ${data.reason}<br>
          <span style="font-size:12px;opacity:0.9;">
            ${data.code === 'COUPON_EXPIRED' ? 'Recovery Available: You may ignore this rejection or continue directly to checkout at full price.' : ''}
          </span>
        </div>
      `;
    } else if (data.status === 'applied') {
      discountAlertEl.className = 'alert-banner alert-success';
      discountAlertEl.style.display = 'flex';
      discountAlertEl.innerHTML = `
        <div>
          <strong>Coupon Applied!</strong> ${data.coupon_code} gives ${data.discount_pct}% off (saved ₹${data.discount_amount.toLocaleString()}).
        </div>
      `;
    }
    loadCart();
    loadAuditLogs();
  } catch (err) {
    alert(`Failed to apply coupon: ${err.message}`);
  }
}

async function removeCoupon() {
  resetAlerts();
  try {
    const res = await fetch(`${API_BASE}/agent/discount?session_id=${encodeURIComponent(currentSessionId)}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    discountAlertEl.className = 'alert-banner alert-warning';
    discountAlertEl.style.display = 'flex';
    discountAlertEl.textContent = 'Discount removed. Cart restored to full price.';
    loadCart();
    loadAuditLogs();
  } catch (err) {
    console.error(err);
  }
}

// Upsell Operations
async function applyUpsell(sku) {
  try {
    const res = await fetch(`${API_BASE}/agent/upsell`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, sku })
    });
    const data = await res.json();

    if (data.status === 'rejected') {
      alert(`Upsell Policy Rejection: ${data.reason}`);
    } else {
      alert(`Upsell Added: ${data.message || 'Product added to cart.'}`);
      loadCart();
    }
    loadAuditLogs();
  } catch (err) {
    alert(`Upsell failed: ${err.message}`);
  }
}

// Checkout & Human Approval Flow
async function initiateCheckout() {
  resetAlerts();
  try {
    const res = await fetch(`${API_BASE}/agent/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId,
        buyer_info: { agent_id: 'dashboard_buyer_v1', client: 'web_dashboard' }
      })
    });
    const data = await res.json();

    if (data.status === 'approval_required') {
      // Show supervisor approval gate
      approvalGateSectionEl.style.display = 'block';
      approvalGateSectionEl.innerHTML = `
        <div class="approval-gate-card">
          <div class="approval-gate-header">
            <h4>Human Supervisor Sign-Off Required</h4>
            <span class="panel-badge" style="color:#f59e0b;border-color:rgba(245,158,11,0.4)">₹${data.amount.toLocaleString()} ≥ Threshold</span>
          </div>
          <p style="font-size:13px;color:var(--text-secondary);">${data.reason}</p>
          <div class="approval-actions">
            <button class="btn btn-success btn-sm" onclick="submitSupervisorApproval('approved')">
              ✓ Approve Order as Supervisor
            </button>
            <button class="btn btn-danger btn-sm" onclick="submitSupervisorApproval('rejected')">
              ✕ Reject Order
            </button>
          </div>
        </div>
      `;
      paymentStatusBadge.textContent = 'Approval Required';
      paymentStatusBadge.style.color = '#f59e0b';
    } else if (data.status === 'success') {
      pendingOrderId = data.order_id;
      approvalGateSectionEl.style.display = 'none';
      checkoutSectionEl.innerHTML = `
        <div class="alert-banner alert-success" style="display:block;">
          <strong>Checkout Approved!</strong> Razorpay Order Reference: <code>${data.order_id}</code><br>
          <div style="margin-top:10px;">
            <button class="btn btn-success" onclick="capturePayment('${data.order_id}', ${data.amount})">
              💳 Capture Payment (₹${data.amount.toLocaleString()})
            </button>
          </div>
        </div>
      `;
      paymentStatusBadge.textContent = 'Order Created (Ready for Capture)';
      paymentStatusBadge.style.color = '#06b6d4';
    } else {
      alert(`Checkout Blocked: ${data.reason}`);
    }
    loadAuditLogs();
    loadCart();
  } catch (err) {
    alert(`Checkout failed: ${err.message}`);
  }
}

async function submitSupervisorApproval(decision) {
  try {
    const res = await fetch(`${API_BASE}/agent/approval`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId,
        decision: decision,
        approved_by: 'supervisor@merchant-hq.internal',
        reason: decision === 'approved' ? 'Approved by dashboard supervisor' : 'Rejected by merchant policy'
      })
    });
    const data = await res.json();
    approvalGateSectionEl.style.display = 'none';

    if (decision === 'approved') {
      // Re-invoke checkout automatically now that approval is signed
      initiateCheckout();
    } else {
      alert('Order has been rejected by human supervisor.');
      loadCart();
      loadAuditLogs();
    }
  } catch (err) {
    alert(`Approval submission failed: ${err.message}`);
  }
}

async function capturePayment(orderId, amount) {
  try {
    const res = await fetch(`${API_BASE}/agent/payment/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId,
        order_id: orderId,
        payment_id: `pay_mock_${orderId.substring(6)}`,
        amount: amount
      })
    });
    const data = await res.json();

    if (data.status === 'success') {
      checkoutSectionEl.innerHTML = `
        <div class="alert-banner alert-success" style="display:block;">
          <strong>Payment Successfully Captured & Settled!</strong><br>
          Payment ID: <code>${data.payment_id}</code> | Amount: ₹${data.amount.toLocaleString()}<br>
          <span style="font-size:12px;opacity:0.9;">Cart has been cleared and transaction recorded in immutable audit trail.</span>
        </div>
      `;
      paymentStatusBadge.textContent = 'Captured & Settled';
      paymentStatusBadge.style.color = '#10b981';
      loadCart();
      loadAuditLogs();
    } else {
      alert(`Payment Capture Failed: ${data.message}`);
    }
  } catch (err) {
    alert(`Capture failed: ${err.message}`);
  }
}

// Load Audit Trail
async function loadAuditLogs(silent = false) {
  try {
    const res = await fetch(`${API_BASE}/audit?session_id=${encodeURIComponent(currentSessionId)}&limit=50`);
    const data = await res.json();
    renderAuditLogs(data.audit_trail || []);
  } catch (err) {
    if (!silent) console.error('Failed to load audit logs:', err);
  }
}

function renderAuditLogs(logs) {
  if (!logs.length) {
    auditLogContainer.innerHTML = '<div class="empty-state">No audit events recorded for this session yet.</div>';
    return;
  }

  auditLogContainer.innerHTML = logs.map(entry => {
    let resultClass = 'badge-allowed';
    if (entry.policy_result === 'REJECTED') resultClass = 'badge-rejected';
    else if (entry.policy_result === 'HUMAN_APPROVAL_REQUIRED') resultClass = 'badge-approval';

    let timeFormatted = entry.timestamp;
    try {
      const d = new Date(entry.timestamp);
      timeFormatted = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (_) {}

    return `
      <div class="audit-entry">
        <div class="audit-header">
          <span class="action-badge">${entry.action}</span>
          <span class="action-badge ${resultClass}">${entry.policy_result}</span>
          <span class="audit-timestamp">${timeFormatted}</span>
        </div>
        <div class="audit-reason">${entry.reason || 'Operation executed'}</div>
        <div class="audit-meta">
          <span>Actor: <strong>${entry.actor}</strong></span>
          ${entry.razorpay_ref ? `<span class="audit-ref">${entry.razorpay_ref}</span>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function resetAlerts() {
  discountAlertEl.style.display = 'none';
  approvalGateSectionEl.style.display = 'none';
  checkoutSectionEl.innerHTML = '';
}

// Global functions for inline HTML button handlers
window.addToCart = addToCart;
window.updateItemQty = updateItemQty;
window.removeItem = removeItem;
window.applyUpsell = applyUpsell;
window.submitSupervisorApproval = submitSupervisorApproval;
window.capturePayment = capturePayment;
