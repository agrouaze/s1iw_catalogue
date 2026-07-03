// filters.js - Reads filter form state, wires up form/pagination events,
// and orchestrates the initial page load. Relies on rendering/fetching
// functions defined in browse.js (loaded before this file).

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('filter-form');
    const resetBtn = form?.querySelector('button[type="reset"]');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');

    function getFilterState() {
        const datasetSelect = document.getElementById('dataset-filter');
        const selectedDatasets = datasetSelect
            ? Array.from(datasetSelect.selectedOptions).map(opt => opt.value)
            : [];

        return {
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
    }

    function renderAll() {
        const filters = getFilterState();
        window.updateResultsTable(filters);
        window.fetchAggregatesAndRender(filters);
        window.updateHsTpHeatmap(filters);
        window.updateWindHeatmap(filters);
        window.updateCategoryPieChart(filters);
        window.updateMonthlyBarChart(filters);  // <-- ADD
        window.updateMap(filters);
    }

    function applyFilters() {
        window.resetPageToFirst();
        renderAll();
    }

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
            window.updateDatasetDescriptionBox();
            applyFilters();
        });
    }

    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            if (window.getCurrentPage() > 0) {
                window.decrementPage();
                window.updateResultsTable(getFilterState());
            }
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            window.incrementPage();
            window.updateResultsTable(getFilterState());
        });
    }

    // Expose for debugging / potential reuse by other scripts
    window.getFilterState = getFilterState;

    // Initial load: fetch dataset metadata (populates the dataset select + colors),
    // then render everything with the default (empty) filter state.
    window.loadDatasetMetadata().then(() => {
        renderAll();
    });
});