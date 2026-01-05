/**
 * Loom OSINT Orchestration Platform - Frontend Application v2.0
 * Enhanced with improved UX, search, export, and error handling
 */

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8787'
    : `http://${window.location.hostname}:8787`;

let API_KEY = localStorage.getItem('loom_api_key') || '';
let availableTools = [];
let allCases = [];  // Store all cases for filtering

// ============================================================================
// Utility Functions
// ============================================================================

function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

async function apiRequest(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (API_KEY) {
        headers['X-API-Key'] = API_KEY;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers
    });

    if (!response.ok) {
        if (response.status === 403) {
            const key = prompt('API Key required. Please enter your API key:');
            if (key) {
                API_KEY = key;
                localStorage.setItem('loom_api_key', key);
                return apiRequest(endpoint, options);
            }
        }
        throw new Error(`API request failed: ${response.statusText}`);
    }

    return response.json();
}

function showElement(id) {
    document.getElementById(id).style.display = 'block';
}

function hideElement(id) {
    document.getElementById(id).style.display = 'none';
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? 'var(--error)' : type === 'success' ? 'var(--success)' : 'var(--primary)'};
        color: white;
        border-radius: 0.375rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function copyToClipboard(text, elementId = null) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
        if (elementId) {
            const element = document.getElementById(elementId);
            if (element) {
                element.textContent = '✓ Copied!';
                setTimeout(() => {
                    element.textContent = 'Copy';
                }, 2000);
            }
        }
    }).catch(err => {
        showToast('Failed to copy', 'error');
        console.error('Copy failed:', err);
    });
}

function exportReport(caseId, report) {
    const blob = new Blob([report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `loom-report-${caseId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Report exported successfully', 'success');
}

function filterCases(searchTerm) {
    const term = searchTerm.toLowerCase().trim();

    if (!term) {
        renderCaseList(allCases);
        return;
    }

    const filtered = allCases.filter(caseItem =>
        caseItem.title.toLowerCase().includes(term) ||
        caseItem.target.toLowerCase().includes(term) ||
        caseItem.case_id.toLowerCase().includes(term) ||
        (caseItem.description && caseItem.description.toLowerCase().includes(term))
    );

    renderCaseList(filtered);
    showToast(`Found ${filtered.length} matching case(s)`, 'info');
}

// ============================================================================
// Markdown Rendering
// ============================================================================

function renderMarkdown(text) {
    let html = text
        // Headers
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        // Bold
        .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
        // Italic
        .replace(/\*(.*?)\*/gim, '<em>$1</em>')
        // Code blocks
        .replace(/```([^`]+)```/gim, '<pre><code>$1</code></pre>')
        // Inline code
        .replace(/`([^`]+)`/gim, '<code>$1</code>')
        // Links
        .replace(/\[([^\]]+)\]\(([^\)]+)\)/gim, '<a href="$2" target="_blank">$1</a>')
        // Line breaks
        .replace(/\n\n/gim, '</p><p>')
        .replace(/\n/gim, '<br>');

    return `<p>${html}</p>`;
}

// ============================================================================
// Tool Management
// ============================================================================

async function loadAvailableTools() {
    try {
        const config = await apiRequest('/config');
        availableTools = config.available_tools || [];

        renderToolSelection();
    } catch (error) {
        console.error('Error loading tools:', error);
        document.getElementById('tool-grid').innerHTML =
            '<p class="error-message">Failed to load tools</p>';
    }
}

function renderToolSelection() {
    const toolGrid = document.getElementById('tool-grid');

    if (availableTools.length === 0) {
        toolGrid.innerHTML = '<p>No tools available</p>';
        return;
    }

    toolGrid.innerHTML = availableTools.map(tool => `
        <label class="tool-option">
            <input
                type="checkbox"
                name="tools"
                value="${tool.name}"
                ${tool.name === 'searxng' ? 'checked' : ''}
            >
            <div class="tool-info">
                <div class="tool-name">${tool.name}</div>
                <div class="tool-desc">${tool.description}</div>
            </div>
        </label>
    `).join('');
}

function getSelectedTools() {
    const checkboxes = document.querySelectorAll('input[name="tools"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// ============================================================================
// Health Check
// ============================================================================

async function checkHealth() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    try {
        const health = await apiRequest('/health');

        const servicesUp = Object.values(health).filter(v => v === 'ok').length;
        const servicesTotal = Object.keys(health).length;

        if (servicesUp === servicesTotal) {
            statusDot.className = 'status-dot healthy';
            statusText.textContent = 'All systems operational';
        } else if (servicesUp > 0) {
            statusDot.className = 'status-dot degraded';
            statusText.textContent = `${servicesUp}/${servicesTotal} services operational`;
        } else {
            statusDot.className = 'status-dot error';
            statusText.textContent = 'Services offline';
        }
    } catch (error) {
        statusDot.className = 'status-dot error';
        statusText.textContent = 'API unreachable';
    }
}

// ============================================================================
// Case Management
// ============================================================================

async function createCase(caseData) {
    const submitBtn = document.getElementById('submit-btn');
    const statusDiv = document.getElementById('pipeline-status');
    const statusMessage = document.getElementById('status-message');
    const toolProgress = document.getElementById('tool-progress');

    try {
        // Disable form
        submitBtn.disabled = true;
        showElement('pipeline-status');
        statusMessage.textContent = 'Starting OSINT pipeline...';

        // Show tool progress
        toolProgress.innerHTML = caseData.tools.map(tool => `
            <div class="tool-status-item" id="tool-status-${tool}">
                <span class="tool-name">${tool}</span>
                <span class="tool-state">Queued</span>
            </div>
        `).join('');

        // Create case
        const result = await apiRequest('/cases', {
            method: 'POST',
            body: JSON.stringify(caseData)
        });

        if (result.status === 'completed') {
            statusMessage.textContent = 'Pipeline completed! Loading results...';

            // Load full case details
            const caseDetails = await apiRequest(`/cases/${result.case_id}`);
            const report = await apiRequest(`/cases/${result.case_id}/report`);

            // Show results
            displayResults(caseDetails, report.report);

            // Refresh case list
            loadCases();

            // Reset form
            document.getElementById('case-form').reset();
            renderToolSelection(); // Re-check default tools
        } else {
            throw new Error(result.message || 'Pipeline failed');
        }

    } catch (error) {
        console.error('Error creating case:', error);
        statusMessage.innerHTML = `<span class="error-message">Error: ${error.message}</span>`;
    } finally {
        submitBtn.disabled = false;
        setTimeout(() => {
            hideElement('pipeline-status');
            toolProgress.innerHTML = '';
        }, 2000);
    }
}

function displayResults(caseData, report) {
    // Basic info
    document.getElementById('result-case-id').textContent = caseData.case_id;
    document.getElementById('result-title').textContent = caseData.title;
    document.getElementById('result-target').textContent = caseData.target;
    document.getElementById('result-status').textContent = caseData.status;
    document.getElementById('result-status').className = `status-badge ${caseData.status}`;

    // Tools used
    const toolResults = caseData.tool_results || [];
    const toolsSuccessful = toolResults.filter(r => r.status === 'success').map(r => r.tool);
    const toolsFailed = toolResults.filter(r => r.status === 'error').map(r => r.tool);

    document.getElementById('result-tools').innerHTML = `
        ${toolsSuccessful.length > 0 ? `<span class="success">${toolsSuccessful.join(', ')}</span>` : ''}
        ${toolsFailed.length > 0 ? `<span class="error"> (Failed: ${toolsFailed.join(', ')})</span>` : ''}
    `;

    // Individual tool results
    const toolResultsDiv = document.getElementById('individual-tool-results');
    toolResultsDiv.innerHTML = toolResults.map(toolResult => `
        <div class="tool-result-card ${toolResult.status}">
            <div class="tool-result-header">
                <h4>${toolResult.tool}</h4>
                <span class="status-badge ${toolResult.status}">${toolResult.status}</span>
            </div>
            <div class="tool-result-body">
                ${toolResult.status === 'success' ? `
                    <p><strong>Results found:</strong> ${(toolResult.results || []).length}</p>
                    <details>
                        <summary>View raw results</summary>
                        <pre><code>${JSON.stringify(toolResult.results, null, 2)}</code></pre>
                    </details>
                ` : `
                    <p class="error-message"><strong>Error:</strong> ${toolResult.error}</p>
                `}
            </div>
        </div>
    `).join('');

    // Unified report
    document.getElementById('report-content').innerHTML = renderMarkdown(report);

    hideElement('new-case-section');
    showElement('results-section');

    // Scroll to results
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth' });
}

async function loadCases() {
    const caseList = document.getElementById('case-list');

    try {
        const data = await apiRequest('/cases');

        if (data.cases.length === 0) {
            caseList.innerHTML = '<p class="loading">No cases yet. Create one above!</p>';
            return;
        }

        // Sort by created date (newest first)
        const sortedCases = data.cases.sort((a, b) =>
            new Date(b.created_at) - new Date(a.created_at)
        );

        caseList.innerHTML = sortedCases.map(caseItem => `
            <div class="case-item" data-case-id="${caseItem.case_id}">
                <div class="case-item-header">
                    <div class="case-item-title">${caseItem.title}</div>
                    <div class="case-item-status ${caseItem.status}">${caseItem.status}</div>
                </div>
                <div class="case-item-meta">
                    Case ID: ${caseItem.case_id} | Target: ${caseItem.target} | Created: ${formatDate(caseItem.created_at)}
                </div>
                <div class="case-item-tools">
                    Tools: ${(caseItem.tools_used || []).join(', ')}
                </div>
                ${caseItem.description ? `<div class="case-item-description">${caseItem.description}</div>` : ''}
            </div>
        `).join('');

        // Add click handlers
        document.querySelectorAll('.case-item').forEach(item => {
            item.addEventListener('click', async () => {
                const caseId = item.dataset.caseId;
                await loadCaseDetails(caseId);
            });
        });

    } catch (error) {
        console.error('Error loading cases:', error);
        caseList.innerHTML = '<p class="error-message">Failed to load cases</p>';
    }
}

async function loadCaseDetails(caseId) {
    try {
        const caseData = await apiRequest(`/cases/${caseId}`);
        const report = await apiRequest(`/cases/${caseId}/report`);

        displayResults(caseData, report.report);
    } catch (error) {
        console.error('Error loading case details:', error);
        alert('Failed to load case details');
    }
}

// ============================================================================
// Event Handlers
// ============================================================================

document.getElementById('case-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    const selectedTools = getSelectedTools();

    if (selectedTools.length === 0) {
        alert('Please select at least one OSINT tool');
        return;
    }

    const caseData = {
        title: formData.get('title'),
        description: formData.get('description') || null,
        target: formData.get('target'),
        tools: selectedTools,
        tool_options: {}
    };

    await createCase(caseData);
});

document.getElementById('new-case-btn').addEventListener('click', () => {
    hideElement('results-section');
    showElement('new-case-section');
    document.getElementById('new-case-section').scrollIntoView({ behavior: 'smooth' });
});

// ============================================================================
// Initialization
// ============================================================================

async function init() {
    console.log('Loom OSINT Orchestration Platform v2.0 - Initializing...');

    // Load available tools
    await loadAvailableTools();

    // Check health
    await checkHealth();

    // Load existing cases
    await loadCases();

    // Refresh health every 30 seconds
    setInterval(checkHealth, 30000);

    console.log('Loom initialized successfully');
}

// Start the app
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
