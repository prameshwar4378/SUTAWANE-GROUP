/**
 * Sutawane Classes ERP - Universal Searchable Dropdown Engine
 * 
 * Transforms all standard HTML <select> elements across the software into 
 * modern, accessible, high-performance searchable dropdowns.
 * 
 * Key Features:
 * - Instant keystroke filtering with substring search & match highlighting
 * - Full 2-way sync with native <select> (form submits, onchange, HTMX events)
 * - Viewport-aware fixed positioning (never clipped by modals or table overflow)
 * - Full keyboard navigation (Arrow Up/Down, Enter, Esc, Tab)
 * - Auto-upgrades on dynamic HTMX content swaps and modal opens
 * - Zero dependencies (vanilla JS)
 */

(function () {
  'use strict';

  // Active open instance
  let activeInstance = null;

  class SearchableSelectInstance {
    constructor(selectElement) {
      this.select = selectElement;
      this.menuEl = null;
      this.searchEl = null;
      this.optionsContainer = null;
      this.focusedOptionIndex = -1;
      this.visibleOptions = [];
      this.allOptions = [];
      this.query = '';
      this.isOpen = false;

      this.init();
    }

    init() {
      if (this.select.dataset.searchableUpgraded === 'true') return;
      this.select.dataset.searchableUpgraded = 'true';

      // 1. Build Custom Trigger Button
      this.triggerEl = document.createElement('div');
      this.triggerEl.className = this.buildTriggerClasses();
      this.triggerEl.tabIndex = this.select.disabled ? -1 : 0;
      this.triggerEl.setAttribute('role', 'combobox');
      this.triggerEl.setAttribute('aria-expanded', 'false');
      this.triggerEl.setAttribute('aria-haspopup', 'listbox');

      // Preserve title or aria-label
      if (this.select.title) this.triggerEl.title = this.select.title;
      if (this.select.getAttribute('aria-label')) {
        this.triggerEl.setAttribute('aria-label', this.select.getAttribute('aria-label'));
      }

      this.labelEl = document.createElement('span');
      this.labelEl.className = 'searchable-select-label';

      this.chevronEl = document.createElement('span');
      this.chevronEl.className = 'searchable-select-chevron';
      this.chevronEl.innerHTML = `
        <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      `;

      this.triggerEl.appendChild(this.labelEl);
      this.triggerEl.appendChild(this.chevronEl);

      // 2. Hide Native Select Visually (Keep in DOM for forms & accessibility)
      this.select.classList.add('searchable-select-hidden');
      this.select.tabIndex = -1;

      // 3. Insert Trigger right after native select
      this.select.parentNode.insertBefore(this.triggerEl, this.select.nextSibling);

      // 4. Initial Sync of Options & Label
      this.readOptions();
      this.updateLabel();

      // 5. Attach Event Listeners
      this.bindEvents();
    }

    buildTriggerClasses() {
      const classList = ['searchable-select-trigger'];

      // Inherit width
      if (this.select.classList.contains('w-full')) {
        classList.push('w-full');
      }

      // Height variants
      if (this.select.classList.contains('h-7')) {
        classList.push('is-h-7');
      } else if (this.select.classList.contains('h-8')) {
        classList.push('is-h-8');
      } else if (this.select.classList.contains('h-10')) {
        classList.push('is-h-10');
      } else if (this.select.classList.contains('h-11')) {
        classList.push('is-h-11');
      }

      // Transparent variant (for dropdowns nested inside search pills, header badges, border-0)
      if (
        this.select.classList.contains('bg-transparent') ||
        this.select.classList.contains('border-0') ||
        this.select.classList.contains('border-none')
      ) {
        classList.push('is-transparent');
      }

      if (this.select.disabled) {
        classList.push('is-disabled');
      }

      return classList.join(' ');
    }

    readOptions() {
      this.allOptions = [];
      const opts = Array.from(this.select.options);

      opts.forEach((opt, idx) => {
        const text = opt.textContent.trim();
        const value = opt.value;
        const disabled = opt.disabled;
        const selected = opt.selected;
        const isPlaceholder = !value && idx === 0 && (opt.getAttribute('data-placeholder') || text.toLowerCase().includes('select') || text.startsWith('--'));

        this.allOptions.push({
          index: idx,
          value: value,
          text: text,
          disabled: disabled,
          selected: selected,
          isPlaceholder: isPlaceholder,
          group: opt.parentElement.tagName === 'OPTGROUP' ? opt.parentElement.label : null,
        });
      });
    }

    updateLabel() {
      const selectedOpt = this.select.options[this.select.selectedIndex];
      if (selectedOpt) {
        const text = selectedOpt.textContent.trim();
        this.labelEl.textContent = text;
        const isPlaceholder = !selectedOpt.value && (selectedOpt.getAttribute('data-placeholder') || text.toLowerCase().includes('select') || text.startsWith('--'));
        if (isPlaceholder) {
          this.labelEl.classList.add('is-placeholder');
        } else {
          this.labelEl.classList.remove('is-placeholder');
        }
      } else {
        this.labelEl.textContent = 'Select...';
        this.labelEl.classList.add('is-placeholder');
      }
    }

    bindEvents() {
      // Toggle on click
      this.triggerEl.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.select.disabled) return;
        this.toggle();
      });

      // Keyboard open from trigger
      this.triggerEl.addEventListener('keydown', (e) => {
        if (this.select.disabled) return;
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          this.open();
        }
      });

      // Forward focus from native select to custom trigger (e.g. when <label for="..."> is clicked)
      this.select.addEventListener('focus', () => {
        if (!this.select.disabled) {
          this.triggerEl.focus();
        }
      });

      // Native select change sync (if modified programmatically by other scripts)
      this.select.addEventListener('change', () => {
        this.readOptions();
        this.updateLabel();
      });

      // Form reset handler
      if (this.select.form) {
        this.select.form.addEventListener('reset', () => {
          setTimeout(() => {
            this.readOptions();
            this.updateLabel();
          }, 10);
        });
      }

      // Mutation observer to detect dynamic option additions/removals
      this.observer = new MutationObserver(() => {
        this.readOptions();
        this.updateLabel();
        if (this.isOpen) {
          this.renderOptionsList();
        }
      });
      this.observer.observe(this.select, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'class'] });
    }

    toggle() {
      if (this.isOpen) {
        this.close();
      } else {
        this.open();
      }
    }

    open() {
      if (this.isOpen || this.select.disabled) return;

      // Close any other open dropdown
      if (activeInstance && activeInstance !== this) {
        activeInstance.close();
      }
      activeInstance = this;

      this.readOptions();
      this.isOpen = true;
      this.triggerEl.classList.add('is-active');
      this.triggerEl.setAttribute('aria-expanded', 'true');

      // Build Menu Element
      this.buildMenu();
      this.positionMenu();

      // Focus Search Input immediately
      requestAnimationFrame(() => {
        if (this.searchEl) {
          this.searchEl.focus();
          this.searchEl.select();
        }
      });

      // Attach global dismiss listeners
      this.bindDismissListeners();
    }

    close() {
      if (!this.isOpen) return;

      this.isOpen = false;
      this.triggerEl.classList.remove('is-active');
      this.triggerEl.setAttribute('aria-expanded', 'false');

      if (this.menuEl && this.menuEl.parentNode) {
        this.menuEl.parentNode.removeChild(this.menuEl);
      }
      this.menuEl = null;
      this.searchEl = null;
      this.optionsContainer = null;
      this.query = '';
      this.focusedOptionIndex = -1;

      this.unbindDismissListeners();
      if (activeInstance === this) {
        activeInstance = null;
      }
    }

    buildMenu() {
      this.menuEl = document.createElement('div');
      this.menuEl.className = 'searchable-select-menu';
      this.menuEl.setAttribute('role', 'listbox');

      // 1. Search Header Box
      const header = document.createElement('div');
      header.className = 'searchable-select-search-header';

      header.innerHTML = `
        <svg class="searchable-select-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
      `;

      this.searchEl = document.createElement('input');
      this.searchEl.type = 'text';
      this.searchEl.className = 'searchable-select-search-input';
      this.searchEl.placeholder = 'Type to search...';
      this.searchEl.autocomplete = 'off';
      this.searchEl.spellcheck = false;

      this.clearSearchBtn = document.createElement('button');
      this.clearSearchBtn.type = 'button';
      this.clearSearchBtn.className = 'searchable-select-search-clear';
      this.clearSearchBtn.style.display = 'none';
      this.clearSearchBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      `;

      header.appendChild(this.searchEl);
      header.appendChild(this.clearSearchBtn);
      this.menuEl.appendChild(header);

      // Search typing logic
      this.searchEl.addEventListener('input', () => {
        this.query = this.searchEl.value.trim().toLowerCase();
        this.clearSearchBtn.style.display = this.query ? 'flex' : 'none';
        this.focusedOptionIndex = 0;
        this.renderOptionsList();
      });

      this.clearSearchBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.searchEl.value = '';
        this.query = '';
        this.clearSearchBtn.style.display = 'none';
        this.searchEl.focus();
        this.renderOptionsList();
      });

      // Search Keyboard Navigation
      this.searchEl.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          this.close();
          this.triggerEl.focus();
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          this.navigateOptions(1);
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          this.navigateOptions(-1);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          this.selectFocusedOption();
        } else if (e.key === 'Tab') {
          this.close();
        }
      });

      // 2. Options Scroll List
      this.optionsContainer = document.createElement('div');
      this.optionsContainer.className = 'searchable-select-options-list';
      this.menuEl.appendChild(this.optionsContainer);

      // Append to document.body to guarantee freedom from modal/card overflow clipping
      document.body.appendChild(this.menuEl);

      // Initial render of options
      this.renderOptionsList();
    }

    renderOptionsList() {
      if (!this.optionsContainer) return;
      this.optionsContainer.innerHTML = '';

      // Filter options by search query
      const filtered = this.allOptions.filter((opt) => {
        if (!this.query) return true;
        return opt.text.toLowerCase().includes(this.query) || (opt.value && opt.value.toLowerCase().includes(this.query));
      });
      this.visibleOptions = filtered;

      if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'searchable-select-empty';
        empty.innerHTML = `No options matching "<strong>${this.escapeHtml(this.searchEl.value)}</strong>"`;
        this.optionsContainer.appendChild(empty);
        return;
      }

      let currentGroup = null;

      filtered.forEach((opt, idx) => {
        // Group Header if optgroup present
        if (opt.group && opt.group !== currentGroup) {
          currentGroup = opt.group;
          const grp = document.createElement('div');
          grp.className = 'searchable-select-group-header';
          grp.textContent = currentGroup;
          this.optionsContainer.appendChild(grp);
        }

        const isSelected = this.select.selectedIndex === opt.index;
        const optEl = document.createElement('div');
        optEl.className = 'searchable-select-option' + (isSelected ? ' is-selected' : '') + (opt.disabled ? ' is-disabled' : '') + (idx === this.focusedOptionIndex ? ' is-focused' : '');
        optEl.setAttribute('role', 'option');
        optEl.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        optEl.dataset.optionIndex = opt.index;

        // Option text with highlighted search match
        const textSpan = document.createElement('span');
        textSpan.className = 'searchable-select-option-text';
        textSpan.innerHTML = this.highlightMatch(opt.text, this.query);
        optEl.appendChild(textSpan);

        // Checkmark Icon on selected item
        if (isSelected) {
          const checkIcon = document.createElement('span');
          checkIcon.className = 'searchable-select-check-icon';
          checkIcon.innerHTML = `
            <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          `;
          optEl.appendChild(checkIcon);
        }

        // Click Selection
        optEl.addEventListener('click', (e) => {
          e.stopPropagation();
          if (opt.disabled) return;
          this.selectOption(opt.index);
        });

        // Hover Focus
        optEl.addEventListener('mouseenter', () => {
          this.setFocusedIndex(idx, false);
        });

        this.optionsContainer.appendChild(optEl);
      });

      // Ensure focused item is in view
      this.scrollFocusedOptionIntoView();
    }

    positionMenu() {
      if (!this.menuEl || !this.triggerEl) return;

      const rect = this.triggerEl.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      // Menu width: at least trigger width, with a minimum of 220px
      const menuWidth = Math.max(rect.width, 220);
      this.menuEl.style.width = `${menuWidth}px`;

      // Horizontal Positioning: clamp within screen bounds
      let left = rect.left;
      if (left + menuWidth > viewportWidth - 10) {
        left = viewportWidth - menuWidth - 10;
      }
      if (left < 10) left = 10;
      this.menuEl.style.left = `${left}px`;

      // Vertical Positioning: check if space below is sufficient
      const estimatedMenuHeight = Math.min(260, (this.allOptions.length * 34) + 60);
      const spaceBelow = viewportHeight - rect.bottom;
      const spaceAbove = rect.top;

      if (spaceBelow < 220 && spaceAbove > spaceBelow) {
        // Flip Above
        this.menuEl.classList.add('is-flipped');
        this.menuEl.style.top = `${Math.max(10, rect.top - estimatedMenuHeight - 4)}px`;
      } else {
        // Open Below
        this.menuEl.classList.remove('is-flipped');
        this.menuEl.style.top = `${rect.bottom + 4}px`;
      }
    }

    navigateOptions(direction) {
      if (this.visibleOptions.length === 0) return;
      let newIdx = this.focusedOptionIndex + direction;
      if (newIdx < 0) newIdx = this.visibleOptions.length - 1;
      if (newIdx >= this.visibleOptions.length) newIdx = 0;

      this.setFocusedIndex(newIdx, true);
    }

    setFocusedIndex(idx, scroll) {
      this.focusedOptionIndex = idx;
      const items = this.optionsContainer.querySelectorAll('.searchable-select-option');
      items.forEach((item, i) => {
        if (i === idx) {
          item.classList.add('is-focused');
        } else {
          item.classList.remove('is-focused');
        }
      });
      if (scroll) {
        this.scrollFocusedOptionIntoView();
      }
    }

    scrollFocusedOptionIntoView() {
      const focusedEl = this.optionsContainer.querySelector('.searchable-select-option.is-focused');
      if (focusedEl) {
        focusedEl.scrollIntoView({ block: 'nearest' });
      }
    }

    selectFocusedOption() {
      if (this.visibleOptions.length === 0) return;
      const target = this.visibleOptions[Math.max(0, this.focusedOptionIndex)];
      if (target && !target.disabled) {
        this.selectOption(target.index);
      }
    }

    selectOption(index) {
      this.select.selectedIndex = index;

      // Update Trigger Label
      this.updateLabel();

      // Close popover
      this.close();

      // Return focus to trigger
      this.triggerEl.focus();

      // Dispatch full suite of events for form submits, HTMX and reactive listeners
      this.select.dispatchEvent(new Event('input', { bubbles: true }));

      // Track if inline onchange fired during dispatchEvent
      let onchangeFired = false;
      const originalOnchange = this.select.onchange;
      if (typeof originalOnchange === 'function') {
        this.select.onchange = function (ev) {
          onchangeFired = true;
          return originalOnchange.call(this, ev);
        };
      }

      this.select.dispatchEvent(new Event('change', { bubbles: true }));

      // If onchange wasn't triggered automatically by dispatchEvent, run it once
      if (typeof originalOnchange === 'function' && !onchangeFired) {
        originalOnchange.call(this.select);
      }
      if (typeof originalOnchange === 'function') {
        this.select.onchange = originalOnchange;
      }
    }

    bindDismissListeners() {
      this._onOutsideClick = (e) => {
        if (!this.isOpen) return;
        if (this.triggerEl.contains(e.target) || (this.menuEl && this.menuEl.contains(e.target))) {
          return;
        }
        this.close();
      };

      this._onWindowResize = () => {
        if (this.isOpen) this.close();
      };

      this._onWindowScroll = (e) => {
        // If scrolling inside the options list itself, do nothing
        if (this.menuEl && this.menuEl.contains(e.target)) return;
        if (this.isOpen) this.close();
      };

      // Delay attachment to avoid immediate trigger click closure
      setTimeout(() => {
        document.addEventListener('click', this._onOutsideClick, true);
        window.addEventListener('resize', this._onWindowResize, { passive: true });
        window.addEventListener('scroll', this._onWindowScroll, { capture: true, passive: true });
      }, 10);
    }

    unbindDismissListeners() {
      if (this._onOutsideClick) {
        document.removeEventListener('click', this._onOutsideClick, true);
        this._onOutsideClick = null;
      }
      if (this._onWindowResize) {
        window.removeEventListener('resize', this._onWindowResize);
        this._onWindowResize = null;
      }
      if (this._onWindowScroll) {
        window.removeEventListener('scroll', this._onWindowScroll, true);
        this._onWindowScroll = null;
      }
    }

    highlightMatch(text, query) {
      if (!query) return this.escapeHtml(text);
      const safeText = this.escapeHtml(text);
      const safeQuery = this.escapeHtml(query);
      const regex = new RegExp(`(${this.escapeRegex(safeQuery)})`, 'gi');
      return safeText.replace(regex, '<mark>$1</mark>');
    }

    escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    escapeRegex(str) {
      return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    destroy() {
      this.close();
      if (this.observer) {
        this.observer.disconnect();
      }
      if (this.triggerEl && this.triggerEl.parentNode) {
        this.triggerEl.parentNode.removeChild(this.triggerEl);
      }
      this.select.classList.remove('searchable-select-hidden');
      delete this.select.dataset.searchableUpgraded;
    }
  }

  // -------------------------------------------------------------------------
  // Global API & Lifecycle Coordinator
  // -------------------------------------------------------------------------

  const SearchableSelect = {
    upgrade: function (selectElement) {
      if (!selectElement || selectElement.tagName !== 'SELECT') return null;
      // Skip hidden/sr-only selects, explicit opt-out selects, and already upgraded selects
      if (
        selectElement.classList.contains('sr-only') ||
        selectElement.hasAttribute('data-no-search') ||
        selectElement.dataset.searchableUpgraded === 'true'
      ) {
        return null;
      }

      // Skip tiny zoom scale select in receipt modal toolbar
      if (selectElement.id === 'receiptZoomSelect') {
        return null;
      }

      return new SearchableSelectInstance(selectElement);
    },

    initAll: function (root = document) {
      if (!root) return;
      const selects = root.querySelectorAll('select:not(.sr-only):not([data-no-search]):not(.searchable-select-hidden)');
      selects.forEach((s) => {
        SearchableSelect.upgrade(s);
      });
    },

    sync: function (selectElement) {
      if (selectElement) {
        selectElement.dispatchEvent(new Event('change', { bubbles: true }));
      }
    },
  };

  window.SearchableSelect = SearchableSelect;

  // Initialize on initial page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      SearchableSelect.initAll(document.body);
    });
  } else {
    SearchableSelect.initAll(document.body);
  }

  // Re-initialize on HTMX content swaps and settle
  document.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail && e.detail.target) {
      SearchableSelect.initAll(e.detail.target);
    }
  });

  document.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail && e.detail.target) {
      SearchableSelect.initAll(e.detail.target);
    }
  });

  // Re-initialize when modal open helper is called
  const originalOpenModal = window.openModal;
  if (typeof originalOpenModal === 'function') {
    window.openModal = function (modalId) {
      originalOpenModal(modalId);
      const m = document.getElementById(modalId);
      if (m) {
        setTimeout(() => {
          SearchableSelect.initAll(m);
        }, 50);
      }
    };
  }

})();
