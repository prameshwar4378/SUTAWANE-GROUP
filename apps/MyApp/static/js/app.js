/**
 * Sutawane Classes Management Software - Core Frontend Client Script
 * Handles Lucide icons, sidebar toggle, quick student search autocomplete, modals, and printing.
 */

// Initialize Lucide icons on document load
document.addEventListener('DOMContentLoaded', function () {
  window.renderIcons();
  initSidebar();
  initHeaderSearch();
  initMonthlyFinancialChart();
});

// Render the dashboard's Monthly Financial Movement Chart via Chart.js
function initMonthlyFinancialChart() {
  const canvas = document.getElementById('monthlyFinancialChart');
  const dataNode = document.getElementById('dashboard-trend-data');
  if (!canvas || !dataNode) return;
  if (typeof Chart === 'undefined') {
    // If Chart.js script is still loading defer-style, wait a tick
    setTimeout(initMonthlyFinancialChart, 50);
    return;
  }

  let trend;
  try {
    trend = JSON.parse(dataNode.textContent);
  } catch (error) {
    console.error('Failed to parse dashboard trend data:', error);
    return;
  }
  if (!Array.isArray(trend) || !trend.length) return;

  // Destroy previous instance if it exists
  if (window.dashboardFinancialChart && typeof window.dashboardFinancialChart.destroy === 'function') {
    window.dashboardFinancialChart.destroy();
  }

  const labels = trend.map((item) => item.month || item.month_short || '');
  const fullMonths = trend.map((item) => item.month_full || item.month || '');
  const collections = trend.map((item) => Number(item.collections) || 0);
  const expenses = trend.map((item) => Number(item.expenses) || 0);

  const ctx = canvas.getContext('2d');
  window.dashboardFinancialChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Fee Collections (₹)',
          data: collections,
          backgroundColor: 'rgba(16, 185, 129, 0.85)',
          hoverBackgroundColor: '#059669',
          borderColor: '#10b981',
          borderWidth: 1.5,
          borderRadius: 6,
          borderSkipped: false,
          barPercentage: 0.7,
          categoryPercentage: 0.75,
        },
        {
          label: 'Operating Expenses (₹)',
          data: expenses,
          backgroundColor: 'rgba(244, 63, 94, 0.85)',
          hoverBackgroundColor: '#e11d48',
          borderColor: '#f43f5e',
          borderWidth: 1.5,
          borderRadius: 6,
          borderSkipped: false,
          barPercentage: 0.7,
          categoryPercentage: 0.75,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 650,
        easing: 'easeOutQuart',
      },
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            pointStyle: 'rectRounded',
            padding: 16,
            font: {
              size: 12,
              weight: '600',
              family: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            },
            color: '#475569',
          },
        },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.94)',
          titleColor: '#f8fafc',
          titleFont: {
            size: 13,
            weight: '700',
          },
          bodyColor: '#e2e8f0',
          bodyFont: {
            size: 12,
          },
          padding: 12,
          cornerRadius: 8,
          boxPadding: 4,
          callbacks: {
            title: function (items) {
              if (items.length && fullMonths[items[0].dataIndex]) {
                return fullMonths[items[0].dataIndex];
              }
              return items[0]?.label || '';
            },
            label: function (context) {
              const val = Number(context.raw) || 0;
              return ` ${context.dataset.label}: ₹${val.toLocaleString('en-IN')}`;
            },
            afterBody: function (items) {
              if (items.length >= 2) {
                const coll = Number(items[0].raw) || 0;
                const exp = Number(items[1].raw) || 0;
                const net = coll - exp;
                const sign = net >= 0 ? '+' : '-';
                return `\n Net Cashflow: ${sign}₹${Math.abs(net).toLocaleString('en-IN')}`;
              }
              return '';
            },
          },
        },
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
          ticks: {
            font: {
              size: 12,
              weight: '600',
              family: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            },
            color: '#64748b',
          },
        },
        y: {
          beginAtZero: true,
          suggestedMax: 10000,
          grid: {
            color: 'rgba(148, 163, 184, 0.15)',
            drawTicks: false,
          },
          ticks: {
            font: {
              size: 11,
              family: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            },
            color: '#64748b',
            padding: 8,
            callback: function (val) {
              if (val >= 100000) return '₹' + (val / 100000).toFixed(1) + 'L';
              if (val >= 1000) return '₹' + (val / 1000).toFixed(0) + 'k';
              return '₹' + val;
            },
          },
        },
      },
    },
  });
}

// Helper to render/refresh icons dynamically
window.renderIcons = function () {
  if (typeof lucide !== 'undefined' && lucide.createIcons) {
    lucide.createIcons();
  }
};

// Re-render Lucide icons, charts and searchable selects on any HTMX DOM content swap
document.addEventListener('htmx:afterSwap', function (e) {
  window.renderIcons();
  initMonthlyFinancialChart();
  if (window.SearchableSelect && e.detail && e.detail.target) {
    window.SearchableSelect.initAll(e.detail.target);
  }
});

// Configure HTMX CSRF token from cookie or hidden input if needed
document.addEventListener('htmx:configRequest', function (e) {
  const cookieMatch = document.cookie.match(/csrftoken=([\w-]+)/);
  const token = cookieMatch ? cookieMatch[1] : (document.querySelector('[name=csrfmiddlewaretoken]')?.value);
  if (token && !e.detail.headers['X-CSRFToken']) {
    e.detail.headers['X-CSRFToken'] = token;
  }
});

// -------------------------------------------------------------------
// Sidebar Collapsing & Expanding
// -------------------------------------------------------------------

function initSidebar() {
  // Listen for Ctrl+B shortcut to toggle sidebar
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      window.toggleSidebar();
    }
  });
}

window.toggleSidebar = function () {
  const sidebar = document.getElementById('app-sidebar');
  if (!sidebar) return;

  const isCollapsed = sidebar.classList.contains('is-collapsed') || sidebar.classList.contains('w-[72px]');
  const brandHeader = document.getElementById('sidebar-brand-header');

  if (isCollapsed) {
    // Expand
    sidebar.classList.remove('w-[72px]', 'is-collapsed');
    sidebar.classList.add('w-64');
    if (brandHeader) {
      brandHeader.classList.remove('justify-center', 'px-2');
      brandHeader.classList.add('justify-between', 'px-4');
    }
    document.querySelectorAll('.sidebar-label').forEach((el) => el.classList.remove('hidden'));
    document.querySelectorAll('.sidebar-icon-only').forEach((el) => el.classList.add('hidden'));
    document.querySelectorAll('.sidebar-nav-item').forEach((el) => {
      el.classList.remove('justify-center');
      el.classList.add('gap-3', 'px-3');
    });
  } else {
    // Collapse
    sidebar.classList.remove('w-64');
    sidebar.classList.add('w-[72px]', 'is-collapsed');
    if (brandHeader) {
      brandHeader.classList.remove('justify-between', 'px-4');
      brandHeader.classList.add('justify-center', 'px-2');
    }
    document.querySelectorAll('.sidebar-label').forEach((el) => el.classList.add('hidden'));
    document.querySelectorAll('.sidebar-icon-only').forEach((el) => el.classList.remove('hidden'));
    document.querySelectorAll('.sidebar-nav-item').forEach((el) => {
      el.classList.remove('gap-3', 'px-3');
      el.classList.add('justify-center');
    });
  }

  window.renderIcons();

  // Persist state to session
  fetch('/toggle-sidebar/', { credentials: 'same-origin' }).catch(() => {});
};

// -------------------------------------------------------------------
// Header Quick Search with Autocomplete Dropdown
// -------------------------------------------------------------------

function initHeaderSearch() {
  const input = document.getElementById('header-quick-search-input');
  const clearBtn = document.getElementById('header-quick-search-clear');
  const resultsContainer = document.getElementById('header-search-results');
  const itemsList = document.getElementById('header-search-items-list');
  const headerTitle = document.getElementById('header-search-header-title');
  const searchContainer = document.getElementById('header-search-container');

  if (!input || !resultsContainer || !itemsList) return;

  let debounceTimer = null;

  input.addEventListener('input', function () {
    const query = input.value.trim();
    if (clearBtn) {
      if (query) {
        clearBtn.classList.remove('hidden');
      } else {
        clearBtn.classList.add('hidden');
      }
    }

    clearTimeout(debounceTimer);
    if (!query) {
      resultsContainer.classList.add('hidden');
      return;
    }

    debounceTimer = setTimeout(() => {
      fetch(`/api/quick-search/?q=${encodeURIComponent(query)}`)
        .then((res) => res.json())
        .then((data) => {
          renderSearchResults(data, query);
        })
        .catch((err) => {
          console.error('Quick search error:', err);
        });
    }, 200);
  });

  input.addEventListener('focus', function () {
    if (input.value.trim() && itemsList.children.length > 0) {
      resultsContainer.classList.remove('hidden');
    }
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      const query = input.value.trim();
      if (query) {
        location.href = `/students/?q=${encodeURIComponent(query)}`;
      }
    } else if (e.key === 'Escape') {
      resultsContainer.classList.add('hidden');
      if (searchContainer && searchContainer.classList.contains('is-mobile-active')) {
        searchContainer.classList.remove('is-mobile-active');
      }
    }
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      input.value = '';
      clearBtn.classList.add('hidden');
      resultsContainer.classList.add('hidden');
      input.focus();
    });
  }

  // Close dropdown on outside click
  document.addEventListener('click', function (e) {
    if (!e.target.closest('#header-search-container')) {
      resultsContainer.classList.add('hidden');
    }
  });

  // Automatically dismiss floating dropdown when scrolling main page content
  const mainViewport = document.querySelector('main');
  if (mainViewport) {
    mainViewport.addEventListener('scroll', function () {
      if (resultsContainer && !resultsContainer.classList.contains('hidden')) {
        resultsContainer.classList.add('hidden');
      }
    }, { passive: true });
  }

  function renderSearchResults(students, query) {
    itemsList.innerHTML = '';
    if (headerTitle) {
      headerTitle.innerHTML = `<i data-lucide="users" class="w-3.5 h-3.5 text-primary"></i><span>Matching Students (${students.length})</span>`;
    }
    const viewAllLink = document.getElementById('header-search-view-all-link');
    if (viewAllLink) {
      viewAllLink.href = `/students/?q=${encodeURIComponent(query)}`;
    }

    if (students.length === 0) {
      itemsList.innerHTML = `
        <div class="p-6 text-center text-xs text-muted-foreground flex flex-col items-center justify-center gap-1.5 bg-card">
          <i data-lucide="search-x" class="w-6 h-6 text-muted-foreground/60"></i>
          <p class="font-medium text-foreground">No students matching "${escapeHtml(query)}"</p>
          <p class="text-[11px] text-muted-foreground">Check spelling or search by student ID, roll number, or phone.</p>
        </div>
      `;
    } else {
      students.forEach((s) => {
        const item = document.createElement('div');
        item.className = 'p-2.5 px-3.5 flex items-center justify-between gap-3 hover:bg-muted/50 cursor-pointer transition-colors bg-card';
        const initial = s.full_name ? s.full_name.trim().charAt(0).toUpperCase() : '?';
        const photoMarkup = s.photo_url
          ? `<img src="${s.photo_url}" class="w-full h-full object-cover" onerror="this.onerror=null; this.parentElement.innerText='${initial}';">`
          : initial;

        item.innerHTML = `
          <div class="flex items-center gap-3 min-w-0 flex-1" onclick="location.href='/students/${s.id}/'">
            <div class="w-8 h-8 rounded-full overflow-hidden bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0 border border-border">
              ${photoMarkup}
            </div>
            <div class="min-w-0 flex-1">
              <div class="font-semibold truncate text-foreground flex items-center gap-1.5 text-xs">
                <span class="truncate">${escapeHtml(s.full_name)}</span>
                <span class="font-mono text-[10px] text-muted-foreground shrink-0">(${escapeHtml(s.roll_number)})</span>
              </div>
              <div class="text-[10px] text-muted-foreground truncate">
                ${escapeHtml(s.standard)} • ${escapeHtml(s.branch_name)}
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            ${
              s.pending_fees > 0
                ? `<span class="text-[10px] text-rose-600 font-bold whitespace-nowrap bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 px-2 py-0.5 rounded-md">Due: ₹${Math.round(s.pending_fees).toLocaleString('en-IN')}</span>`
                : `<span class="text-[10px] text-emerald-600 font-semibold whitespace-nowrap bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/50 px-2 py-0.5 rounded-md">Cleared</span>`
            }
            <a
              href="/fees/collect/?student_id=${s.id}&admission_id=${s.admission_id || ''}&amount=${s.pending_fees > 0 ? s.pending_fees : ''}"
              class="h-6.5 px-2.5 text-[10px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-1 shadow-2xs whitespace-nowrap transition-colors"
              title="Collect fees for ${escapeHtml(s.full_name)}"
              onclick="event.stopPropagation();"
            >
              <i data-lucide="credit-card" class="w-3 h-3"></i>
              <span>Fee</span>
            </a>
          </div>
        `;
        itemsList.appendChild(item);
      });
    }

    resultsContainer.classList.remove('hidden');
    window.renderIcons();
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// -------------------------------------------------------------------
// Modal Open & Close Helpers
// -------------------------------------------------------------------

window.openModal = function (modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('overflow-hidden');
    window.renderIcons();
    if (window.SearchableSelect) {
      setTimeout(() => {
        window.SearchableSelect.initAll(modal);
      }, 30);
    }
  }
};

window.closeModal = function (modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
  }
};

// Universal Close on Escape Key
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    const openModals = document.querySelectorAll('[data-modal].flex');
    openModals.forEach((m) => {
      m.classList.add('hidden');
      m.classList.remove('flex');
    });
    document.body.classList.remove('overflow-hidden');
  }
});

// -------------------------------------------------------------------
// Universal Print Helper
// -------------------------------------------------------------------

window.printDocument = function (mode) {
  if (mode === 'receipt') {
    document.body.classList.add('printing-receipt');
    window.print();
    setTimeout(() => {
      document.body.classList.remove('printing-receipt');
    }, 1000);
  } else if (mode === 'thermal') {
    document.body.classList.add('printing-thermal');
    window.print();
    setTimeout(() => {
      document.body.classList.remove('printing-thermal');
    }, 1000);
  } else if (mode === 'report') {
    document.body.classList.add('printing-report');
    window.print();
    setTimeout(() => {
      document.body.classList.remove('printing-report');
    }, 1000);
  } else {
    window.print();
  }
};

// ===================================================================
// Universal Single-Click Button Loading & Submission Protection Engine
// ===================================================================
(function () {
  'use strict';

  // Spinner SVG matching font size and text color
  function createSpinnerSvg() {
    return (
      '<svg class="btn-loading-spinner animate-spin w-4 h-4 shrink-0 inline-block mr-1.5" ' +
      'xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="vertical-align:-0.15em;">' +
      '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
      '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>' +
      '</svg>'
    );
  }

  // Derive intelligent loading label from button text
  function deriveLoadingLabel(rawText) {
    if (!rawText) return 'Processing...';
    const text = rawText.trim().toLowerCase();

    if (text.includes('filter')) return 'Filtering...';
    if (text.includes('collect') || text.includes('record payment')) return 'Recording Payment...';
    if (text.includes('payment') || text.includes('pay')) return 'Processing Payment...';
    if (text.includes('save') || text.includes('saved')) return 'Saving...';
    if (text.includes('create') || text.includes('add')) return 'Creating...';
    if (text.includes('update') || text.includes('edit')) return 'Updating...';
    if (text.includes('delete') || text.includes('remove') || text.includes('void')) return 'Deleting...';
    if (text.includes('export') || text.includes('download')) return 'Exporting...';
    if (text.includes('generate')) return 'Generating...';
    if (text.includes('verify') || text.includes('otp')) return 'Verifying...';
    if (text.includes('sign in') || text.includes('login')) return 'Signing In...';
    if (text.includes('promote')) return 'Promoting...';
    if (text.includes('backup') || text.includes('restore')) return 'Processing Backup...';
    if (text.includes('search')) return 'Searching...';
    if (text.includes('apply')) return 'Applying...';
    if (text.includes('send') || text.includes('notify')) return 'Sending...';
    if (text.includes('reset')) return 'Resetting...';
    if (text.includes('submit')) return 'Submitting...';

    return 'Processing...';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Track the most recently clicked submit button
  let lastClickedSubmitBtn = null;
  document.addEventListener('mousedown', function (e) {
    const btn = e.target.closest('button, input[type="submit"]');
    if (btn && (btn.type === 'submit' || btn.classList.contains('btn-submit') || btn.hasAttribute('data-single-click'))) {
      lastClickedSubmitBtn = btn;
    }
  }, true);

  // Lock button and transition to animated spinner state
  function lockButton(btn, customText) {
    if (!btn || btn.classList.contains('btn-loading') || btn.dataset.originalHtml) {
      return false;
    }

    // Capture button width before modifying DOM to prevent layout shift
    const currentWidth = btn.offsetWidth;
    if (currentWidth > 0) {
      btn.style.minWidth = currentWidth + 'px';
    }

    // Preserve original state for clean restoration
    btn.dataset.originalHtml = btn.innerHTML;
    btn.dataset.originalDisabled = btn.disabled ? 'true' : 'false';

    const loadingText = customText || btn.getAttribute('data-loading-text') || deriveLoadingLabel(btn.textContent);

    btn.innerHTML = createSpinnerSvg() + '<span>' + escapeHtml(loadingText) + '</span>';
    btn.classList.add('btn-loading');
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');

    return true;
  }

  // Restore button back to initial state
  function restoreButton(btn) {
    if (!btn || !btn.dataset.originalHtml) return;

    btn.innerHTML = btn.dataset.originalHtml;
    btn.disabled = btn.dataset.originalDisabled === 'true';
    btn.classList.remove('btn-loading');
    btn.removeAttribute('aria-busy');
    btn.style.minWidth = '';
    delete btn.dataset.originalHtml;
    delete btn.dataset.originalDisabled;

    if (window.renderIcons) {
      window.renderIcons();
    }
  }

  function resetAllLoadingButtons() {
    document.querySelectorAll('.btn-loading').forEach(restoreButton);
    document.querySelectorAll('.__dynamic_submit_action__').forEach(function (el) {
      el.remove();
    });
  }

  // Handle Form Submissions (Both standard full-page POSTs and HTMX)
  document.addEventListener('submit', function (e) {
    const form = e.target;
    if (!form || form.hasAttribute('data-no-loading') || form.classList.contains('no-loading')) {
      return;
    }

    // Verify HTML5 validation status - do NOT lock if browser validation blocks submission
    if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
      return;
    }

    // Identify the submit button that triggered this submission
    let submitBtn = e.submitter;
    if (!submitBtn || submitBtn.tagName !== 'BUTTON') {
      submitBtn = lastClickedSubmitBtn && form.contains(lastClickedSubmitBtn)
        ? lastClickedSubmitBtn
        : form.querySelector('button[type="submit"]:not([disabled]), input[type="submit"]:not([disabled])');
    }

    if (!submitBtn) return;

    // Preserve button name and value so Django request.POST gets the action parameter (e.g. name="action" value="create")
    if (submitBtn.name && !form.querySelector('input[type="hidden"][name="' + CSS.escape(submitBtn.name) + '"]')) {
      const hiddenInput = document.createElement('input');
      hiddenInput.type = 'hidden';
      hiddenInput.name = submitBtn.name;
      hiddenInput.value = submitBtn.value || '';
      hiddenInput.className = '__dynamic_submit_action__';
      form.appendChild(hiddenInput);
    }

    // Lock the button immediately with animated loading spinner
    lockButton(submitBtn);

    // If form is non-HTMX, safety timer resets button in case submission was cancelled or downloaded as file
    const isHtmx = form.hasAttribute('hx-get') || form.hasAttribute('hx-post') || form.hasAttribute('hx-put') || form.hasAttribute('hx-patch');
    if (!isHtmx) {
      const isExport = (form.action && form.action.includes('export')) || (submitBtn.value && submitBtn.value.includes('export')) || submitBtn.textContent.toLowerCase().includes('export');
      if (isExport) {
        setTimeout(function () {
          restoreButton(submitBtn);
        }, 4000);
      }
    }
  }, true);

  // Handle Standalone Click Action Buttons (e.g. data-single-click or .btn-single-click)
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('button[data-single-click], .btn-single-click, button[type="button"][data-loading-text]');
    if (!btn || btn.disabled || btn.classList.contains('btn-loading')) return;

    if (!btn.hasAttribute('hx-get') && !btn.hasAttribute('hx-post')) {
      lockButton(btn);
    }
  }, true);

  // HTMX Integration Hooks
  document.addEventListener('htmx:beforeRequest', function (e) {
    const elt = e.detail && e.detail.elt;
    if (elt) {
      if (elt.tagName === 'BUTTON') {
        lockButton(elt);
      } else if (elt.tagName === 'FORM') {
        const btn = elt.querySelector('button[type="submit"]:not([disabled])');
        if (btn) lockButton(btn);
      }
    }
  });

  document.addEventListener('htmx:afterRequest', function (e) {
    const elt = e.detail && e.detail.elt;
    if (elt) {
      if (elt.tagName === 'BUTTON') {
        restoreButton(elt);
      } else if (elt.tagName === 'FORM') {
        elt.querySelectorAll('.btn-loading').forEach(restoreButton);
      }
    }
    resetAllLoadingButtons();
  });

  document.addEventListener('htmx:responseError', resetAllLoadingButtons);
  document.addEventListener('htmx:sendError', resetAllLoadingButtons);
  document.addEventListener('htmx:afterSwap', function () {
    resetAllLoadingButtons();
  });

  // Restore when navigating back through Back/Forward cache (BFCache)
  window.addEventListener('pageshow', function () {
    resetAllLoadingButtons();
  });

  // Expose Global API on window
  window.ButtonLoadingEngine = {
    lock: lockButton,
    restore: restoreButton,
    resetAll: resetAllLoadingButtons,
  };
})();

/* ==========================================================================
   SMART, NON-IRRITATING PAGE LOADER ENGINE
   - Top-edge progress bar (YouTube/GitHub style): runs smoothly on navigation,
     form submits, and HTMX requests. Completely non-intrusive.
   - Smart Delayed Screen Overlay: Appears ONLY when an operation takes longer
     than 750ms (or when explicitly requested for bulk/stress jobs).
     Prevents irritating flickering on fast operations.
   ========================================================================== */
(function () {
  let progressBar = null;
  let screenOverlay = null;
  let screenOverlayText = null;
  let progress = 0;
  let trickleTimer = null;
  let overlayDelayTimer = null;
  let safetyTimeout = null;
  let isRunning = false;

  function ensureElements() {
    if (!progressBar) {
      progressBar = document.getElementById('app-page-progress-bar');
      if (!progressBar) {
        progressBar = document.createElement('div');
        progressBar.id = 'app-page-progress-bar';
        progressBar.className = 'page-progress-bar';
        progressBar.setAttribute('role', 'progressbar');
        progressBar.setAttribute('aria-hidden', 'true');
        document.body.appendChild(progressBar);
      }
    }
    if (!screenOverlay) {
      screenOverlay = document.getElementById('app-screen-loader');
      if (!screenOverlay) {
        screenOverlay = document.createElement('div');
        screenOverlay.id = 'app-screen-loader';
        screenOverlay.className = 'screen-loader-overlay';
        screenOverlay.setAttribute('aria-hidden', 'true');
        screenOverlay.setAttribute('role', 'status');
        screenOverlay.innerHTML = (
          '<div class="screen-loader-card">' +
            '<div class="screen-loader-spinner-wrap">' +
              '<div class="screen-loader-spinner-ring"></div>' +
              '<div class="screen-loader-brand-icon">' +
                '<svg style="width:26px;height:26px;color:#059669;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
                  '<path d="M22 10v6M2 10l10-5 10 5-10 5z"></path>' +
                  '<path d="M6 12v5c3 3 9 3 12 0v-5"></path>' +
                '</svg>' +
              '</div>' +
            '</div>' +
            '<div class="screen-loader-text" id="app-screen-loader-text">Loading Sutawane Classes...</div>' +
            '<div class="screen-loader-subtext">Please wait a moment</div>' +
          '</div>'
        );
        document.body.appendChild(screenOverlay);
      }
      screenOverlayText = document.getElementById('app-screen-loader-text');
    }
  }

  function setProgress(n) {
    ensureElements();
    progress = Math.max(0, Math.min(100, n));
    if (!progressBar) return;
    progressBar.style.opacity = '1';
    progressBar.style.width = progress + '%';
  }

  function trickle() {
    if (progress < 25) {
      setProgress(progress + Math.random() * 15 + 10);
    } else if (progress < 60) {
      setProgress(progress + Math.random() * 8 + 3);
    } else if (progress < 85) {
      setProgress(progress + Math.random() * 3 + 1);
    } else if (progress < 96) {
      setProgress(progress + 0.5);
    }
  }

  function start(options) {
    ensureElements();
    if (isRunning) return;
    isRunning = true;

    if (progressBar) {
      progressBar.style.transition = 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease';
      progressBar.style.opacity = '1';
    }
    setProgress(12);

    clearInterval(trickleTimer);
    trickleTimer = setInterval(trickle, 200);

    clearTimeout(overlayDelayTimer);
    clearTimeout(safetyTimeout);

    const message = (options && options.message) || 'Loading Sutawane Classes...';
    const immediateOverlay = options && options.immediateOverlay;

    if (immediateOverlay) {
      showOverlay(message);
    } else {
      // 750ms threshold: Fast operations finish with NO screen overlay at all!
      overlayDelayTimer = setTimeout(function () {
        if (isRunning) {
          showOverlay(message);
        }
      }, 750);
    }

    // Safety timeout: Never stay stuck for more than 12s
    safetyTimeout = setTimeout(function () {
      done();
    }, 12000);
  }

  function done() {
    clearInterval(trickleTimer);
    clearTimeout(overlayDelayTimer);
    clearTimeout(safetyTimeout);

    if (progressBar) {
      setProgress(100);
      setTimeout(function () {
        if (progressBar) {
          progressBar.style.opacity = '0';
          setTimeout(function () {
            if (progressBar && !isRunning) {
              progressBar.style.width = '0%';
            }
          }, 250);
        }
      }, 150);
    }

    hideOverlay();
    isRunning = false;
    progress = 0;
  }

  function showOverlay(customMessage) {
    ensureElements();
    if (screenOverlayText && customMessage) {
      screenOverlayText.textContent = customMessage;
    }
    if (screenOverlay) {
      screenOverlay.classList.add('active');
      screenOverlay.setAttribute('aria-hidden', 'false');
    }
  }

  function hideOverlay() {
    if (screenOverlay) {
      screenOverlay.classList.remove('active');
      screenOverlay.setAttribute('aria-hidden', 'true');
    }
  }

  // Intercept Page Navigation Clicks
  document.addEventListener('click', function (e) {
    const link = e.target.closest('a[href]');
    if (!link) return;

    if (
      e.defaultPrevented ||
      e.button !== 0 ||
      e.ctrlKey || e.metaKey || e.shiftKey || e.altKey ||
      link.hasAttribute('download') ||
      link.target === '_blank' ||
      link.hasAttribute('data-no-loader') ||
      link.classList.contains('no-loader')
    ) {
      return;
    }

    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('tel:') || href.startsWith('mailto:')) {
      return;
    }

    try {
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return;
    } catch (err) {
      return;
    }

    start();
  }, true);

  // Form Submission Trigger
  document.addEventListener('submit', function (e) {
    const form = e.target;
    if (!form || form.hasAttribute('data-no-loader') || form.classList.contains('no-loader')) {
      return;
    }

    if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
      return;
    }

    const isExplicitHeavy = form.hasAttribute('data-screen-loader') || form.hasAttribute('data-loading-overlay');
    const customMsg = form.getAttribute('data-loading-message') || (isExplicitHeavy ? 'Processing request...' : null);

    start({
      immediateOverlay: isExplicitHeavy,
      message: customMsg
    });
  }, true);

  // HTMX Integration
  document.addEventListener('htmx:beforeRequest', function (e) {
    const elt = e.detail && e.detail.elt;
    if (elt && (elt.tagName === 'INPUT' || elt.hasAttribute('data-no-loader') || elt.closest('#header-search'))) {
      return;
    }

    const isExplicitHeavy = elt && (elt.hasAttribute('data-screen-loader') || elt.hasAttribute('data-loading-overlay'));
    const customMsg = elt && (elt.getAttribute('data-loading-message') || (isExplicitHeavy ? 'Processing...' : null));

    start({
      immediateOverlay: isExplicitHeavy,
      message: customMsg
    });
  });

  document.addEventListener('htmx:afterRequest', done);
  document.addEventListener('htmx:afterSwap', done);
  document.addEventListener('htmx:responseError', done);
  document.addEventListener('htmx:sendError', done);

  // BFCache / Back-Forward Navigation Safety
  window.addEventListener('pageshow', done);

  // Escape Key to dismiss hung overlay
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isRunning) {
      hideOverlay();
    }
  });

  // Finish on initial document ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', done);
  } else {
    done();
  }

  // Expose Global API
  window.PageLoader = {
    start: start,
    set: setProgress,
    done: done,
    showOverlay: showOverlay,
    hideOverlay: hideOverlay,
  };
})();
