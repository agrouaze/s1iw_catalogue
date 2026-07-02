// filters.js - Handles filter form submission and state

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('filter-form');
    const resetBtn = form.querySelector('button[type="reset"]');

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        applyFilters();
    });

    resetBtn.addEventListener('click', function() {
        form.reset();
        applyFilters();
    });

    // Debounce for text inputs
    const textInputs = form.querySelectorAll('input[type="text"]');
    textInputs.forEach(input => {
        input.addEventListener('input', debounce(applyFilters, 300));
    });

    // Apply filters on select change
    const selects = form.querySelectorAll('select');
    selects.forEach(select => {
        select.addEventListener('change', applyFilters);
    });

    function applyFilters() {
        const filters = getFilterState();
        // Update visualizations and table
        updateVisualizations(filters);
        updateResultsTable(filters);
    }

    function getFilterState() {
        return {
            slc_name: document.getElementById('slc-filter').value || null,
            grd_name: document.getElementById('grd-filter').value || null,
            datasets: Array.from(document.getElementById('dataset-filter').selectedOptions).map(opt => opt.value),
            polarization: Array.from(document.getElementById('polarization-filter').selectedOptions).map(opt => opt.value),
            satellites: Array.from(document.getElementById('satellite-filter').selectedOptions).map(opt => opt.value),
            date_start: document.getElementById('date-start').value || null,
            date_end: document.getElementById('date-end').value || null,
            limit: 100,
            offset: 0
        };
    }

    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    // Expose functions globally
    window.getFilterState = getFilterState;
    window.applyFilters = applyFilters;
});
