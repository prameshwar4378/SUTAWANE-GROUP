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

// Re-render Lucide icons and charts on any HTMX DOM content swap
document.addEventListener('htmx:afterSwap', function (e) {
  window.renderIcons();
  initMonthlyFinancialChart();
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

  function renderSearchResults(students, query) {
    itemsList.innerHTML = '';
    if (headerTitle) {
      headerTitle.textContent = `Matching Students (${students.length})`;
    }

    if (students.length === 0) {
      itemsList.innerHTML = `
        <div class="p-4 text-center text-xs text-muted-foreground">
          No students matching "${escapeHtml(query)}"
        </div>
      `;
    } else {
      students.forEach((s) => {
        const item = document.createElement('div');
        item.className = 'p-2.5 px-3 flex items-center justify-between gap-2 hover:bg-muted/50 cursor-pointer transition-colors';
        item.innerHTML = `
          <div class="flex items-center gap-2.5 min-w-0" onclick="location.href='/students/${s.id}/'">
            <div class="w-7 h-7 rounded-full overflow-hidden bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0 border">
              ${s.photo_url ? `<img src="${s.photo_url}" class="w-full h-full object-cover">` : s.full_name.charAt(0)}
            </div>
            <div class="min-w-0">
              <div class="font-semibold truncate text-foreground flex items-center gap-1.5">
                <span>${escapeHtml(s.full_name)}</span>
                <span class="font-mono text-[10px] text-muted-foreground">(${escapeHtml(s.roll_number)})</span>
              </div>
              <div class="text-[10px] text-muted-foreground truncate">
                ${escapeHtml(s.standard)} • ${escapeHtml(s.branch_name)}
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            ${
              s.pending_fees > 0
                ? `<span class="text-[10px] text-rose-600 font-bold">Due: ₹${Math.round(s.pending_fees).toLocaleString('en-IN')}</span>`
                : `<span class="text-[10px] text-emerald-600 font-semibold">Cleared</span>`
            }
            <a
              href="/fees/collect/?student_id=${s.id}&admission_id=${s.admission_id || ''}&amount=${s.pending_fees > 0 ? s.pending_fees : ''}"
              class="h-6 px-2 text-[10px] font-semibold rounded bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-1 shadow-sm"
              title="Collect fees"
            >
              <i data-lucide="credit-card" class="w-3 h-3"></i>
              Fee
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
