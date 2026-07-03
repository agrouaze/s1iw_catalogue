// browse.js - Data fetching and rendering logic for the Browse Catalogue page.
//
// This file only DEFINES functions and exposes them on `window` so that
// filters.js (the orchestrator) can call them once the DOM/filters are ready.
// It does not wire up any event listeners itself.

let datasetMetadata = {};
let currentPage = 0;
const pageSize = 100;

// ---------- Dataset metadata & description box ----------

function loadDatasetMetadata() {
    return fetch('/api/stats/datasets_metadata')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            datasetMetadata = data.metadata || {};
            populateDatasetFilter(datasetMetadata);
            return datasetMetadata;
        })
        .catch(error => {
            console.error('Error loading dataset metadata:', error);
            const select = document.getElementById('dataset-filter');
            if (select) {
                select.innerHTML = '<option value="" disabled>Error loading datasets</option>';
            }
            return {};
        });
}

// Populate the dataset filter list, tinting each option by type (SLC/GRD),
// and wire the description box to update when the selection changes.
function populateDatasetFilter(metadata) {
    const select = document.getElementById('dataset-filter');
    if (!select) return;

    const datasetNames = Object.keys(metadata);
    if (datasetNames.length === 0) {
        select.innerHTML = '<option value="" disabled>No datasets found</option>';
        return;
    }

    // Light, non-aggressive background tint per dataset type.
    const typeColors = {
        'slc': '#eaf2fb',   // light blue
        'grd': '#eaf7ee'    // light green
    };
    const defaultColor = '#f5f5f5'; // light grey fallback for unknown types

    let html = '';
    datasetNames.forEach(name => {
        const type = (metadata[name]?.type || '').toLowerCase();
        const label = type ? `${name} [${type}]` : name;
        const bgColor = typeColors[type] || defaultColor;
        html += `<option value="${name}" style="background-color: ${bgColor};">${label}</option>`;
    });
    select.innerHTML = html;

    select.addEventListener('change', updateDatasetDescriptionBox);
}

// Show description(s) for the currently selected dataset(s), or a placeholder if none selected.
function updateDatasetDescriptionBox() {
    const select = document.getElementById('dataset-filter');
    const box = document.getElementById('dataset-description-box');
    if (!select || !box) return;

    const selected = Array.from(select.selectedOptions).map(opt => opt.value);

    if (selected.length === 0) {
        box.innerHTML = '<p class="dataset-description-placeholder">Select one or more datasets to see their description here.</p>';
        return;
    }

    let html = '';
    selected.forEach(name => {
        const meta = datasetMetadata[name] || {};
        const description = meta.description || 'No description available.';
        const category = meta.category || '';
        const type = meta.type || '';
        const metaParts = [type, category].filter(Boolean).join(' · ');
        html += `<div class="dataset-desc-item">
            <div class="dataset-desc-name">${name}</div>
            ${metaParts ? `<div class="dataset-desc-meta">${metaParts}</div>` : ''}
            <div>${description}</div>
        </div>`;
    });
    box.innerHTML = html;
}

// ---------- Results table ----------

function updateResultsTable(filters) {
    const tableDiv = document.getElementById('results-table');
    const countDiv = document.getElementById('results-count');
    if (!tableDiv) return;
    tableDiv.innerHTML = '<p class="loading">Loading...</p>';

    fetch('/api/browse/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        const rows = data.rows || [];
        const total = data.total || 0;
        if (countDiv) {
            countDiv.textContent = `Showing ${filters.offset + 1}-${Math.min(filters.offset + rows.length, total)} of ${total} results`;
        }

        let html = '<table class="table"><thead><tr><th>SAFE SLC</th><th>SAFE GRD</th><th>Dataset</th><th>Start Date</th><th>Polarization</th><th>Satellite</th></tr></thead><tbody>';
        if (rows.length === 0) {
            html += '<tr><td colspan="6">No results found</td></tr>';
        } else {
            rows.forEach(row => {
                const datasets = row['datasets'] || [];
                // Map dataset names to display names with descriptions
                const displayDatasets = datasets.map(ds => {
                    const desc = datasetMetadata[ds]?.description || '';
                    return desc ? `${ds} (${desc})` : ds;
                });
                html += `<tr>
                    <td>${row['SAFE SLC'] || ''}</td>
                    <td>${row['SAFE GRD'] || ''}</td>
                    <td>${displayDatasets.join(', ')}</td>
                    <td>${row['start date SAFE'] || ''}</td>
                    <td>${row['polarization'] || ''}</td>
                    <td>${row['unit'] || ''}</td>
                </tr>`;
            });
        }
        html += '</tbody></table>';
        tableDiv.innerHTML = html;

        const totalPages = Math.ceil(total / pageSize);
        const pageInfo = document.getElementById('page-info');
        if (pageInfo) {
            pageInfo.textContent = `Page ${currentPage + 1} of ${totalPages || 1}`;
        }
        const prevBtn = document.getElementById('prev-page');
        const nextBtn = document.getElementById('next-page');
        if (prevBtn) prevBtn.disabled = currentPage === 0;
        if (nextBtn) nextBtn.disabled = currentPage >= totalPages - 1 || totalPages === 0;
    })
    .catch(error => {
        console.error('Error fetching results:', error);
        if (tableDiv) {
            tableDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
        }
    });
}

// ---------- Dataset bar chart & polarization/satellite pie chart ----------
// Both charts are derived from the same fetch (single request, up to 1000 rows)
// to avoid firing two separate network calls for the same underlying data.

function fetchAggregatesAndRender(filters) {
    fetch('/api/browse/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...filters, limit: 1000, offset: 0 })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        const rows = data.rows || [];
        const total = data.total || 0;
        renderDatasetBarChart(rows, total);
        renderPolarizationSatellitePieChart(rows, total);
    })
    .catch(error => {
        console.error('Error fetching aggregate data:', error);
        const barDiv = document.getElementById('dataset-bar-chart');
        const pieDiv = document.getElementById('pie-plot');
        if (barDiv) barDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
        if (pieDiv) pieDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}

function renderDatasetBarChart(rows, total) {
    const plotDiv = document.getElementById('dataset-bar-chart');
    if (!plotDiv) return;

    if (rows.length === 0) {
        plotDiv.innerHTML = '<p class="loading">No data available</p>';
        return;
    }

    const datasetCounts = {};
    rows.forEach(row => {
        const datasets = row['datasets'] || [];
        datasets.forEach(ds => {
            datasetCounts[ds] = (datasetCounts[ds] || 0) + 1;
        });
    });

    const labels = Object.keys(datasetCounts);
    const values = Object.values(datasetCounts);

    if (labels.length === 0) {
        plotDiv.innerHTML = '<p class="loading">No dataset data available</p>';
        return;
    }

    // Use display names with descriptions for labels
    const displayLabels = labels.map(ds => {
        const desc = datasetMetadata[ds]?.description || '';
        return desc ? `${ds} (${desc})` : ds;
    });

    const trace = {
        x: displayLabels,
        y: values,
        type: 'bar',
        marker: {
            color: ['#1a365d', '#2c5282', '#48bb78', '#f6ad55', '#fc8181', '#9f7aea'],
        },
        text: values.map(v => v.toString()),
        textposition: 'outside'
    };

    const layout = {
        title: `Dataset Distribution (${total} products)`,
        xaxis: { title: 'Dataset' },
        yaxis: { title: 'Count' },
        height: 250,
        margin: { l: 50, r: 20, t: 40, b: 60 }
    };

    Plotly.newPlot('dataset-bar-chart', [trace], layout);
}

function updateCategoryPieChart(filters) {
    const plotDiv = document.getElementById('category-pie-plot');
    if (!plotDiv) return;

    fetch('/api/browse/category_counts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        const counts = data.counts || {};
        const total = data.total || 0;

        const labels = Object.keys(counts);
        const values = Object.values(counts);

        if (labels.length === 0) {
            plotDiv.innerHTML = '<p class="loading">No category data available</p>';
            return;
        }

        // Light, non-aggressive palette for categories
        const categoryColors = {
            'test': '#f2a8a8',     // soft red
            'train': '#a8c8ec',    // soft blue
            'val': '#a8e0c4',      // soft green
            'undefined': '#d0d0d0' // soft grey
        };
        const defaultColor = '#c9b8ea'; // purple fallback

        const colors = labels.map(cat => categoryColors[cat] || defaultColor);

        const trace = {
            type: 'pie',
            labels: labels,
            values: values,
            marker: { colors: colors },
            textinfo: 'label+percent',
            hole: 0.35,
            sort: false
        };

        const layout = {
            title: `Category Distribution (${total} products)`,
            height: 280,
            margin: { l: 10, r: 10, t: 40, b: 10 },
            showlegend: false
        };

        Plotly.newPlot('category-pie-plot', [trace], layout);
    })
    .catch(error => {
        console.error('Error fetching category data:', error);
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}

function renderPolarizationSatellitePieChart(rows, total) {
    const plotDiv = document.getElementById('pie-plot');
    if (!plotDiv) return;

    if (rows.length === 0) {
        plotDiv.innerHTML = '<p class="loading">No data available</p>';
        return;
    }

    const polarizationCounts = {};
    const satelliteCounts = {};

    rows.forEach(row => {
        const pol = row['polarization'];
        if (pol) polarizationCounts[pol] = (polarizationCounts[pol] || 0) + 1;

        const sat = row['unit'];
        if (sat) satelliteCounts[sat] = (satelliteCounts[sat] || 0) + 1;
    });

    if (Object.keys(polarizationCounts).length === 0 && Object.keys(satelliteCounts).length === 0) {
        plotDiv.innerHTML = '<p class="loading">No polarization/satellite data available</p>';
        return;
    }

    // Light, non-aggressive palette
    const softColors = ['#a8c8ec', '#a8e0c4', '#f6cf9e', '#f2a8a8', '#c9b8ea', '#f6e39e'];

    const polTrace = {
        type: 'pie',
        labels: Object.keys(polarizationCounts),
        values: Object.values(polarizationCounts),
        domain: { x: [0, 0.48] },
        name: 'Polarization',
        marker: { colors: softColors },
        textinfo: 'label+percent',
        hole: 0.35,
        sort: false
    };

    const satTrace = {
        type: 'pie',
        labels: Object.keys(satelliteCounts),
        values: Object.values(satelliteCounts),
        domain: { x: [0.52, 1] },
        name: 'Satellite',
        marker: { colors: softColors },
        textinfo: 'label+percent',
        hole: 0.35,
        sort: false
    };

    const layout = {
        height: 260,
        margin: { l: 10, r: 10, t: 30, b: 10 },
        showlegend: false,
        annotations: [
            { text: 'Polarization', x: 0.22, y: 1.15, showarrow: false, font: { size: 12 } },
            { text: 'Satellite', x: 0.78, y: 1.15, showarrow: false, font: { size: 12 } }
        ]
    };

    Plotly.newPlot('pie-plot', [polTrace, satTrace], layout);
}

// ---------- Map ----------

function updateMap(filters) {
    const plotDiv = document.getElementById('map-plot');
    if (!plotDiv) return;
    plotDiv.innerHTML = '<p class="loading">Loading map data...</p>';

    fetch('/api/browse/map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filter: filters,
            max_polygons: 100
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        const features = data.features || [];

        if (features.length === 0) {
            plotDiv.innerHTML = '<p class="loading">No footprints available for the selected filters</p>';
            return;
        }

        const satelliteColors = {
            'S1A': '#1a365d',
            'S1B': '#2c5282',
            'S1C': '#48bb78',
            'S1D': '#f6ad55'
        };
        const defaultColor = '#9f7aea';

        const lons = [];
        const lats = [];
        const hoverTexts = [];
        const colors = [];

        features.forEach(feature => {
            const geom = feature.geometry;
            const props = feature.properties;

            let lon, lat;
            if (geom.type === 'Point') {
                lon = geom.coordinates[0];
                lat = geom.coordinates[1];
            } else if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') {
                try {
                    const coords = geom.type === 'Polygon' ? geom.coordinates[0] : geom.coordinates[0][0];
                    let sumLon = 0, sumLat = 0;
                    coords.forEach(coord => {
                        sumLon += coord[0];
                        sumLat += coord[1];
                    });
                    lon = sumLon / coords.length;
                    lat = sumLat / coords.length;
                } catch (e) {
                    return;
                }
            } else {
                return;
            }

            const datasets = (props.dataset || []).join(', ');
            const hoverText =
                `<b>SAFE SLC:</b> ${props.safe_slc || 'N/A'}<br>` +
                `<b>SAFE GRD:</b> ${props.safe_grd || 'N/A'}<br>` +
                `<b>Satellite:</b> ${props.satellite || 'N/A'}<br>` +
                `<b>Start Date:</b> ${props.start_date || 'N/A'}<br>` +
                `<b>Datasets:</b> ${datasets || 'N/A'}`;
            hoverTexts.push(hoverText);

            const satellite = props.satellite || 'unknown';
            colors.push(satelliteColors[satellite] || defaultColor);

            lons.push(lon);
            lats.push(lat);
        });

        let centerLon = 0;
        let centerLat = 20;
        let zoom = 2;

        if (lons.length > 0) {
            centerLon = lons.reduce((a, b) => a + b, 0) / lons.length;
            centerLat = lats.reduce((a, b) => a + b, 0) / lats.length;
            const lonSpread = Math.max(...lons) - Math.min(...lons);
            const latSpread = Math.max(...lats) - Math.min(...lats);
            const maxSpread = Math.max(lonSpread, latSpread);
            if (maxSpread < 10) zoom = 6;
            else if (maxSpread < 30) zoom = 4;
            else if (maxSpread < 60) zoom = 3;
            else zoom = 2;
        }

        const trace = {
            type: 'scattermapbox',
            lon: lons,
            lat: lats,
            mode: 'markers',
            marker: {
                size: 12,
                color: colors,
                opacity: 0.8,
                symbol: 'circle'
            },
            text: hoverTexts,
            hoverinfo: 'text',
            hoverlabel: {
                bgcolor: 'white',
                font: { size: 12 }
            },
            name: 'Products'
        };

        const layout = {
            mapbox: {
                style: 'open-street-map',
                center: {
                    lon: centerLon,
                    lat: centerLat
                },
                zoom: zoom,
            },
            margin: { l: 0, r: 0, t: 0, b: 0 },
            height: 280,
            hovermode: 'closest',
            showlegend: false
        };

        const titleElement = document.querySelector('#map-plot')?.parentElement?.querySelector('h3');
        if (titleElement) {
            titleElement.textContent = `🌍 Products (${features.length} shown, colored by satellite)`;
        }

        Plotly.react('map-plot', [trace], layout, { responsive: true });
    })
    .catch(error => {
        console.error('Error fetching map data:', error);
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}

// ---------- Hs/Tp heatmap ----------

function updateHsTpHeatmap(filters) {
    const plotDiv = document.getElementById('hs-tp-plot');
    if (!plotDiv) return;

    fetch('/api/browse/heatmap/hs_tp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filter: filters,
            variable: "hs_tp"
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.data && data.data.hs && data.data.hs.length > 0) {
            const trace = {
                x: data.data.hs,
                y: data.data.tp,
                mode: 'markers',
                marker: {
                    size: 6,
                    color: data.data.density,
                    colorscale: 'Viridis',
                    showscale: true,
                    colorbar: { title: 'Density' },
                    opacity: 0.8
                },
                type: 'scatter',
                hoverinfo: 'x+y'
            };
            const layout = {
                title: `Hs vs Tp (${data.count} points, colored by density)`,
                xaxis: { title: 'Hs (m)' },
                yaxis: { title: 'Tp (s)' },
                height: 250,
                margin: { l: 50, r: 20, t: 40, b: 50 }
            };
            Plotly.newPlot('hs-tp-plot', [trace], layout);
        } else {
            plotDiv.innerHTML = '<p class="loading">No Hs/Tp data available</p>';
        }
    })
    .catch(error => {
        console.error('Error fetching Hs/Tp data:', error);
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}


function updateWindHeatmap(filters) {
    const plotDiv = document.getElementById('wind-plot');
    if (!plotDiv) return;

    fetch('/api/browse/heatmap/wind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filter: filters,
            variable: "wind"
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        const plotDiv = document.getElementById('wind-plot');
        if (data.data && data.data.speed && data.data.speed.length > 0) {
            const trace = {
                x: data.data.direction,
                y: data.data.speed,
                mode: 'markers',
                marker: {
                    size: 6,
                    color: data.data.density,   // <-- density as color
                    colorscale: 'Viridis',
                    showscale: true,
                    colorbar: { title: 'Density' },
                    opacity: 0.8
                },
                type: 'scatter',
                hoverinfo: 'x+y'
            };
            const layout = {
                title: `Wind Speed vs Direction (${data.count} points, colored by density)`,
                xaxis: { title: 'Wind Direction (°)', range: [0, 360] },
                yaxis: { title: 'Wind Speed (m/s)' },
                height: 250,
                margin: { l: 50, r: 20, t: 40, b: 50 }
            };
            Plotly.newPlot('wind-plot', [trace], layout);
        } else {
            plotDiv.innerHTML = '<p class="loading">No wind data available</p>';
        }
    })
    .catch(error => {
        console.error('Error fetching wind data:', error);
        const plotDiv = document.getElementById('wind-plot');
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}

// ---------- count per day ----------

function updateDailyBarChart(filters) {
    const plotDiv = document.getElementById('daily-bar-chart');
    if (!plotDiv) return;

    fetch('/api/browse/daily_counts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${data.error}</p>`;
            return;
        }

        const dates = data.dates || [];
        const series = data.series || {};
        const datasetNames = data.datasets || [];

        if (dates.length === 0 || datasetNames.length === 0) {
            plotDiv.innerHTML = '<p class="loading">No daily data available</p>';
            return;
        }

        // Build traces: one per dataset
        // Use a light, distinct color palette
        const colors = ['#a8c8ec', '#a8e0c4', '#f6cf9e', '#f2a8a8', '#c9b8ea', '#f6e39e', '#b8d4e3', '#d4b8d4'];
        const traces = datasetNames.map((ds, idx) => ({
            x: dates,
            y: series[ds],
            name: ds,
            type: 'bar',
            marker: { color: colors[idx % colors.length] },
            text: series[ds].map(v => v.toString()),
            textposition: 'inside',
            insidetextanchor: 'middle',
            hovertemplate: `%{x}<br>%{fullData.name}: %{y}<extra></extra>`,
        }));

        const layout = {
            barmode: 'stack',
            title: `Daily Product Counts (${dates.length} days)`,
            xaxis: { title: 'Date', type: 'category' },
            yaxis: { title: 'Number of products' },
            height: 300,
            margin: { l: 50, r: 20, t: 40, b: 50 },
            legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' },
            hovermode: 'x unified',
        };

        Plotly.newPlot('daily-bar-chart', traces, layout, { responsive: true });
    })
    .catch(error => {
        console.error('Error fetching daily counts:', error);
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}



function updateMonthlyBarChart(filters) {
    const plotDiv = document.getElementById('daily-bar-chart');
    if (!plotDiv) return;

    fetch('/api/browse/monthly_counts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${data.error}</p>`;
            return;
        }

        const months = data.months || [];
        const series = data.series || {};
        const datasetNames = data.datasets || [];

        if (months.length === 0 || datasetNames.length === 0) {
            plotDiv.innerHTML = '<p class="loading">No monthly data available</p>';
            return;
        }

        const colors = ['#a8c8ec', '#a8e0c4', '#f6cf9e', '#f2a8a8', '#c9b8ea', '#f6e39e', '#b8d4e3', '#d4b8d4'];
        const traces = datasetNames.map((ds, idx) => ({
            x: months,
            y: series[ds],
            name: ds,
            type: 'bar',
            marker: { color: colors[idx % colors.length] },
            text: series[ds].map(v => v.toString()),
            textposition: 'inside',
            insidetextanchor: 'middle',
            hovertemplate: `%{x}<br>%{fullData.name}: %{y}<extra></extra>`,
        }));

        const layout = {
            barmode: 'stack',
            title: `Monthly Product Counts (${months.length} months)`,
            xaxis: { title: 'Month', type: 'category' },
            yaxis: { title: 'Number of products' },
            height: 300,
            margin: { l: 50, r: 20, t: 40, b: 50 },
            legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' },
            hovermode: 'x unified',
        };

        Plotly.newPlot('daily-bar-chart', traces, layout, { responsive: true });
    })
    .catch(error => {
        console.error('Error fetching monthly counts:', error);
        plotDiv.innerHTML = `<p class="loading" style="color: #dc3545;">Error: ${error.message}</p>`;
    });
}

// ---------- Pagination helpers (state lives here, driven by filters.js) ----------

function getCurrentPage() {
    return currentPage;
}

function decrementPage() {
    if (currentPage > 0) currentPage--;
}

function incrementPage() {
    currentPage++;
}

function resetPageToFirst() {
    currentPage = 0;
}

// ---------- Expose the public API used by filters.js / browse.html ----------

window.loadDatasetMetadata = loadDatasetMetadata;
window.updateDatasetDescriptionBox = updateDatasetDescriptionBox;
window.updateResultsTable = updateResultsTable;
window.fetchAggregatesAndRender = fetchAggregatesAndRender;
window.updateMap = updateMap;
window.updateHsTpHeatmap = updateHsTpHeatmap;
window.getCurrentPage = getCurrentPage;
window.decrementPage = decrementPage;
window.incrementPage = incrementPage;
window.resetPageToFirst = resetPageToFirst;
window.pageSize = pageSize;
window.getDatasetMetadata = () => datasetMetadata;