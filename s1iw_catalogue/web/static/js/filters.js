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
        window.updateMonthlyBarChart(filters);
        window.updateMap(filters);

        // Afficher un toast avec le nombre de résultats
        // On utilise la fonction updateResultsTable qui a déjà récupéré les données.
        // On peut récupérer le total depuis le DOM, ou depuis la dernière requête.
        // Pour simplifier, on peut afficher un message générique.
        // Mais on peut aussi récupérer le total depuis la dernière requête via une variable globale.
        // Je propose d'ajouter un champ "total" dans le JSON retourné par /filter, et de le stocker.
        // Pour l'instant, on affiche un message simple.
        window.showToast('✅ Filtres appliqués – données mises à jour');
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


function showToast(message) {
    const toast = document.getElementById('toast');
    const msgEl = document.getElementById('toast-message');
    if (!toast || !msgEl) return;

    msgEl.textContent = message;
    toast.classList.add('show');

    // Auto-hide after 3.5 seconds
    clearTimeout(window.toastTimeout);
    window.toastTimeout = setTimeout(() => {
        hideToast();
    }, 3500);
}

function hideToast() {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.classList.remove('show');
        clearTimeout(window.toastTimeout);
    }
}

// Expose to global scope
window.showToast = showToast;
window.hideToast = hideToast;