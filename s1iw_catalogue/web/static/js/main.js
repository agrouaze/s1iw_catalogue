// main.js - Shared JavaScript for the web interface

// Helper function to get color class based on percentage
function getColorClass(value) {
    if (value >= 80) return 'badge-green';
    else if (value >= 50) return 'badge-yellow';
    else if (value > 0) return 'badge-red';
    else return 'badge-grey';
}

// Helper function to get emoji based on percentage
function getEmoji(value) {
    if (value >= 80) return '🟢';
    else if (value >= 50) return '🟡';
    else if (value > 0) return '🔴';
    else return '⚪';
}

// Render a cell with badge
function renderCell(value) {
    if (value === undefined || value === null) {
        return `<td><span class="badge badge-grey">⚪ 0%</span></td>`;
    }
    const emoji = getEmoji(value);
    const cls = getColorClass(value);
    return `<td><span class="badge ${cls}">${emoji} ${value.toFixed(1)}%</span></td>`;
}

// Render overall cell with bold styling
function renderOverallCell(value) {
    if (value === undefined || value === null) {
        return `<td><span class="badge badge-grey" style="font-weight:bold;">⚪ 0%</span></td>`;
    }
    const emoji = getEmoji(value);
    const cls = getColorClass(value);
    return `<td><span class="badge ${cls}" style="font-weight:bold;">${emoji} ${value.toFixed(1)}%</span></td>`;
}

// Make functions globally available
window.getColorClass = getColorClass;
window.getEmoji = getEmoji;
window.renderCell = renderCell;
window.renderOverallCell = renderOverallCell;