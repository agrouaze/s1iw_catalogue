// browse.js - Handles visualization updates

let currentPage = 0;
const pageSize = 100;

function updateVisualizations(filters) {
    // Fetch map data
    fetch('/api/browse/map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter: filters, max_polygons: 100 })
    })
    .then(res => res.json())
    .then(data => {
        // For now, just log; later implement map with Plotly or Leaflet
        console.log('Map data:', data);
    });

    // Fetch Hs/Tp heatmap data
    fetch('/api/browse/heatmap/hs_tp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter: filters })
    })
    .then(res => res.json())
    .then(data => {
        if (data.data && data.data.hs && data.data.tp) {
            const trace = {
                x: data.data.hs,
                y: data.data.tp,
                mode: 'markers',
                marker: { size: 5, color: 'blue', opacity: 0.6 },
                type: 'scatter'
            };
            const layout = {
                title: 'Hs vs Tp',
                xaxis: { title: 'Hs (m)' },
                yaxis: { title: 'Tp (s)' },
                height: 300
            };
            Plotly.newPlot('hs-tp-plot', [trace], layout);
        } else {
            document.getElementById('hs-tp-plot').innerHTML = '<p>No data available</p>';
        }
    });
}

function updateResultsTable(filters) {
    const offset = currentPage * pageSize;
    const req = { ...filters, limit: pageSize, offset: offset };

    fetch('/api/browse/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req)
    })
    .then(res => res.json())
    .then(data => {
        const tableDiv = document.getElementById('results-table');
        const rows = data.rows;
        let html = '<table class="table"><thead><tr><th>SAFE SLC</th><th>SAFE GRD</th><th>Dataset</th><th>Start Date</th><th>Polarization</th><th>Satellite</th></tr></thead><tbody>';
        if (rows.length === 0) {
            html += '<tr><td colspan="6">No results found</td></tr>';
        } else {
            rows.forEach(row => {
                html += `<tr>
                    <td>${row['SAFE SLC'] || ''}</td>
                    <td>${row['SAFE GRD'] || ''}</td>
                    <td>${(row['dataset(s) d\'appartenance'] || []).join(', ')}</td>
                    <td>${row['start date SAFE'] || ''}</td>
                    <td>${row['polarization'] || ''}</td>
                    <td>${row['unité'] || ''}</td>
                </tr>`;
            });
        }
        html += '</tbody></table>';
        tableDiv.innerHTML = html;

        // Update pagination
        const total = data.total || 0;
        const totalPages = Math.ceil(total / pageSize);
        document.getElementById('page-info').textContent = `Page ${currentPage+1} of ${totalPages || 1}`;
        document.getElementById('prev-page').disabled = currentPage === 0;
        document.getElementById('next-page').disabled = currentPage >= totalPages-1;
    });
}

// Pagination controls
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('prev-page').addEventListener('click', function() {
        if (currentPage > 0) {
            currentPage--;
            const filters = window.getFilterState();
            updateResultsTable(filters);
        }
    });
    document.getElementById('next-page').addEventListener('click', function() {
        currentPage++;
        const filters = window.getFilterState();
        updateResultsTable(filters);
    });
});

// Export functions
window.updateVisualizations = updateVisualizations;
window.updateResultsTable = updateResultsTable;