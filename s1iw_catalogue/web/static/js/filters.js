// filters.js - Reads filter form state, wires up form/pagination events,
// and orchestrates the initial page load.

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('filter-form');
    const resetBtn = form?.querySelector('button[type="reset"]');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    const exportBtn = document.getElementById('export-csv-btn');
    const filterToggleBtn = document.getElementById('filter-toggle-btn');
    const filterPanel = document.getElementById('filter-panel');
    const filterCountBadge = document.getElementById('filter-count-badge');

    // ---- Filter panel toggle ----

    let filterPanelOpen = true;
    filterToggleBtn?.addEventListener('click', function() {
        filterPanelOpen = !filterPanelOpen;
        filterPanel.style.display = filterPanelOpen ? 'block' : 'none';
        document.getElementById('filter-toggle-icon').textContent = filterPanelOpen ? '▼' : '▶';
    });

    // ---- Toggle buttons (3 states) ----

    const toggleBtns = document.querySelectorAll('.toggle-btn');

    toggleBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const currentState = this.dataset.state;
            let nextState;
            if (currentState === 'neutral') nextState = 'with';
            else if (currentState === 'with') nextState = 'without';
            else nextState = 'neutral';
            this.dataset.state = nextState;
            updateToggleIcon(this);
        });
    });

    function updateToggleIcon(btn) {
        const icon = btn.querySelector('.toggle-icon');
        const state = btn.dataset.state;
        if (state === 'neutral') {
            icon.textContent = '⚪';
            btn.title = 'Neutral (no filter)';
        } else if (state === 'with') {
            icon.textContent = '✅';
            btn.title = 'With (IS NOT NULL)';
        } else {
            icon.textContent = '❌';
            btn.title = 'Without (IS NULL)';
        }
    }

    function getToggleState(col) {
        const btn = document.querySelector(`.toggle-group[data-col="${col}"] .toggle-btn`);
        if (!btn) return null;
        const state = btn.dataset.state;
        if (state === 'with') return true;
        if (state === 'without') return false;
        return null;
    }

    function resetToggles() {
        toggleBtns.forEach(btn => {
            btn.dataset.state = 'neutral';
            updateToggleIcon(btn);
        });
    }

    // ---- Filter state ----

    function getFilterState() {
        const datasetSelect = document.getElementById('dataset-filter');
        const selectedDatasets = datasetSelect
            ? Array.from(datasetSelect.selectedOptions).map(opt => opt.value)
            : [];

        const hasSlc = getToggleState('slc');
        const hasGrd = getToggleState('grd');
        const hasOcn = getToggleState('ocn');
        const hasL1b = getToggleState('l1b');
        const hasL1c = getToggleState('l1c');

        const state = {
            slc_name: document.getElementById('slc-filter').value || null,
            grd_name: document.getElementById('grd-filter').value || null,
            datasets: selectedDatasets,
            polarization: Array.from(document.getElementById('polarization-filter').selectedOptions).map(opt => opt.value),
            satellites: Array.from(document.getElementById('satellite-filter').selectedOptions).map(opt => opt.value),
            date_start: document.getElementById('date-start').value || null,
            date_end: document.getElementById('date-end').value || null,
            limit: window.pageSize,
            offset: window.getCurrentPage() * window.pageSize
        };

        if (hasSlc !== null) state.has_slc = hasSlc;
        if (hasGrd !== null) state.has_grd = hasGrd;
        if (hasOcn !== null) state.has_ocn = hasOcn;
        if (hasL1b !== null) state.has_l1b = hasL1b;
        if (hasL1c !== null) state.has_l1c = hasL1c;

        return state;
    }

    function updateTotalCount(total) {
        const el = document.getElementById('total-results-count');
        if (el) {
            el.textContent = total === 0 ? 'No products found' : `${total} product${total > 1 ? 's' : ''}`;
        }
        // Update badge
        if (filterCountBadge) {
            filterCountBadge.textContent = total > 0 ? total : '';
            filterCountBadge.style.display = total > 0 ? 'inline-block' : 'none';
        }
    }

    function renderAll() {
        const filters = getFilterState();
        window.updateResultsTable(filters, updateTotalCount);
        window.fetchAggregatesAndRender(filters);
        window.updateHsTpHeatmap(filters);
        window.updateWindHeatmap(filters);
        window.updateCategoryPieChart(filters);
        window.updateMonthlyBarChart(filters);
        window.updateMap(filters);
    }

    function applyFilters() {
        window.resetPageToFirst();
        renderAll();
    }

    // ---- Event Listeners ----

    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            applyFilters();
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', function(e) {
            e.preventDefault();
            form.reset();
            resetToggles();
            window.updateDatasetDescriptionBox();
            applyFilters();
        });
    }

    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            if (window.getCurrentPage() > 0) {
                window.decrementPage();
                window.updateResultsTable(getFilterState(), updateTotalCount);
            }
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            window.incrementPage();
            window.updateResultsTable(getFilterState(), updateTotalCount);
        });
    }

    // ---- Export CSV ----

    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            const filters = getFilterState();
            window.exportCSV(filters);
        });
    }

    // ---- Expose for debugging ----

    window.getFilterState = getFilterState;
    window.resetToggles = resetToggles;
    window.updateTotalCount = updateTotalCount;

    // ---- Initial load ----

    window.loadDatasetMetadata().then(() => {
        renderAll();
    });
});