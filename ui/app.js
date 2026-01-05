/**
 * Loom OSINT Orchestration Platform - Frontend Application v3.0
 * Philosophy-aligned: Intent → Plan → Confirm → Execute
 * No anthropomorphism, no blind execution, full interruptibility
 */

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8787'
    : `http://${window.location.hostname}:8787`;

let API_KEY = localStorage.getItem('loom_api_key') || '';
let availableTools = [];
let allCases = [];
let currentReport = null;
let currentCaseId = null;  // Track current executing case for abort

// Tool location mapping (local vs remote)
const TOOL_LOCATIONS = {
    'searxng': { type: 'local', endpoint: 'pi-core:8888' },
    'recon-ng': { type: 'local', endpoint: 'pi-core (SSH)' },
    'theharvester': { type: 'local', endpoint: 'Docker (local)' },
    'sherlock': { type: 'local', endpoint: 'Docker (local)' },
    'spiderfoot': { type: 'remote', endpoint: 'spider.lan (API)' },
    'intelowl': { type: 'remote', endpoint: 'intelowl.lan (API)' }
};

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

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers
        });

        if (!response.ok) {
            if (response.status === 403) {
                const key = prompt('API Key required. Enter API key:');
                if (key) {
                    API_KEY = key;
                    localStorage.setItem('loom_api_key', key);
                    return apiRequest(endpoint, options);
                }
                throw new Error('API key required');
            }
            throw new Error(`API request failed: ${response.statusText}`);
        }

        return response.json();
    } catch (error) {
        showToast(`Request failed: ${error.message}`, 'error');
        throw error;
    }
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
        max-width: 400px;
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function copyToClipboard(text, buttonId = null) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard', 'success');
        if (buttonId) {
            const button = document.getElementById(buttonId);
            if (button) {
                const originalText = button.textContent;
                button.textContent = '✓ Copied';
                button.disabled = true;
                setTimeout(() => {
                    button.textContent = originalText;
                    button.disabled = false;
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
    showToast('Report exported', 'success');
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

    if (filtered.length > 0) {
        showToast(`Found ${filtered.length} case(s)`, 'info');
    } else {
        showToast('No matching cases', 'info');
    }
}

// ============================================================================
// Markdown Rendering
// ============================================================================

function renderMarkdown(text) {
    let html = text
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/gim, '<em>$1</em>')
        .replace(/```([^`]+)```/gim, '<pre><code>$1</code></pre>')
        .replace(/`([^`]+)`/gim, '<code>$1</code>')
        .replace(/\[([^\]]+)\]\(([^\)]+)\)/gim, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        .replace(/^\s*\-\s+(.*)$/gim, '<li>$1</li>')
        .replace(/\n\n/gim, '</p><p>')
        .replace(/\n/gim, '<br>');

    html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');

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

    toolGrid.innerHTML = availableTools.map(tool => {
        const location = TOOL_LOCATIONS[tool.name] || { type: 'unknown', endpoint: 'Unknown' };
        const locationBadge = location.type === 'local'
            ? `<span class="location-badge local">⚡ Local: ${location.endpoint}</span>`
            : `<span class="location-badge remote">🌐 Remote: ${location.endpoint}</span>`;

        return `
            <label class="tool-option" title="${tool.description}">
                <input
                    type="checkbox"
                    name="tools"
                    value="${tool.name}"
                    ${tool.name === 'searxng' ? 'checked' : ''}
                >
                <div class="tool-info">
                    <div class="tool-name">${tool.name}</div>
                    ${locationBadge}
                    <div class="tool-desc">${tool.description}</div>
                </div>
            </label>
        `;
    }).join('');
}

function getSelectedTools() {
    const checkboxes = document.querySelectorAll('input[name="tools"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// ============================================================================
// Execution Plan Generation
// ============================================================================

function generateExecutionPlan(caseData) {
    const selectedTools = caseData.tools;
    const target = caseData.target;

    // Analyze target type
    let targetType = 'Unknown';
    let assumptions = [];

    if (/^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(target)) {
        targetType = 'Domain';
        assumptions.push('DNS resolution available');
        assumptions.push('WHOIS lookup permitted');
    } else if (/^(\d{1,3}\.){3}\d{1,3}$/.test(target)) {
        targetType = 'IPv4 Address';
        assumptions.push('Network reachability');
    } else if (/^@/.test(target)) {
        targetType = 'Username/Handle';
        assumptions.push('Social media platforms accessible');
    } else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(target)) {
        targetType = 'Email Address';
        assumptions.push('Email enumeration permitted');
    }

    // Calculate dependencies and external calls
    const externalCalls = selectedTools.map(tool => {
        const location = TOOL_LOCATIONS[tool] || { type: 'unknown', endpoint: 'Unknown' };
        return {
            tool,
            type: location.type,
            endpoint: location.endpoint
        };
    });

    // Estimate duration (rough heuristic: 30s-90s per tool)
    const minDuration = selectedTools.length * 30;
    const maxDuration = selectedTools.length * 90;
    const estimate = `${Math.floor(minDuration / 60)}-${Math.ceil(maxDuration / 60)} minutes`;

    return {
        target,
        targetType,
        tools: selectedTools,
        toolCount: selectedTools.length,
        externalCalls,
        assumptions,
        estimate,
        caseData
    };
}

function showExecutionPlan(plan) {
    const planContainer = document.getElementById('execution-plan');

    const externalCallsList = plan.externalCalls.map(call => {
        const icon = call.type === 'local' ? '⚡' : '🌐';
        return `<li><code>${call.tool}</code> → ${icon} ${call.endpoint}</li>`;
    }).join('');

    const assumptionsList = plan.assumptions.length > 0
        ? plan.assumptions.map(a => `<li>${a}</li>`).join('')
        : '<li>None identified</li>';

    planContainer.innerHTML = `
        <div class="plan-header">
            <h3>Execution Plan Review</h3>
            <p class="plan-subtitle">Review before execution. No action taken until confirmed.</p>
        </div>

        <div class="plan-section">
            <h4>Target</h4>
            <p><code class="target-id">${plan.target}</code></p>
            <p class="meta">Type: ${plan.targetType}</p>
        </div>

        <div class="plan-section">
            <h4>External Calls</h4>
            <p class="meta">${plan.toolCount} tool(s) will execute</p>
            <ul class="plan-list">${externalCallsList}</ul>
        </div>

        <div class="plan-section">
            <h4>Assumptions</h4>
            <ul class="plan-list">${assumptionsList}</ul>
        </div>

        <div class="plan-section">
            <h4>Estimated Duration</h4>
            <p>${plan.estimate}</p>
        </div>

        <div class="plan-actions">
            <button class="btn btn-secondary" id="cancel-plan-btn">Cancel</button>
            <button class="btn btn-primary" id="confirm-plan-btn">Confirm Execute</button>
        </div>
    `;

    // Show plan, hide form
    hideElement('case-form');
    showElement('execution-plan');

    // Add event handlers
    document.getElementById('cancel-plan-btn').addEventListener('click', () => {
        hideElement('execution-plan');
        showElement('case-form');
        showToast('Execution cancelled', 'info');
    });

    document.getElementById('confirm-plan-btn').addEventListener('click', async () => {
        await executeCase(plan.caseData);
    });
}

// ============================================================================
// Case Execution (After Confirmation)
// ============================================================================

async function executeCase(caseData) {
    const planContainer = document.getElementById('execution-plan');
    const statusDiv = document.getElementById('pipeline-status');
    const statusMessage = document.getElementById('status-message');
    const toolProgress = document.getElementById('tool-progress');

    try {
        // Hide plan, show execution status
        hideElement('execution-plan');
        showElement('pipeline-status');
        statusMessage.textContent = 'Executing OSINT pipeline...';

        // Show tool progress with abort button
        toolProgress.innerHTML = `
            <div class="execution-header">
                <span>Running ${caseData.tools.length} tool(s)...</span>
                <button class="btn btn-abort" id="abort-btn">Abort Execution</button>
            </div>
            ${caseData.tools.map(tool => `
                <div class="tool-status-item" id="tool-status-${tool}">
                    <span class="tool-name">${tool}</span>
                    <span class="tool-state">Queued</span>
                </div>
            `).join('')}
        `;

        // Add abort handler (note: backend doesn't support abort yet, but UI is ready)
        document.getElementById('abort-btn').addEventListener('click', () => {
            showToast('Abort requested (not yet implemented in backend)', 'warning');
            // TODO: Implement abort API endpoint
        });

        // Execute case
        const result = await apiRequest('/cases', {
            method: 'POST',
            body: JSON.stringify(caseData)
        });

        currentCaseId = result.case_id;

        if (result.status === 'completed') {
            statusMessage.textContent = 'Pipeline completed. Loading results...';
            showToast('Investigation complete', 'success');

            const caseDetails = await apiRequest(`/cases/${result.case_id}`);
            const report = await apiRequest(`/cases/${result.case_id}/report`);

            displayResults(caseDetails, report.report);
            loadCases();

            // Reset form
            document.getElementById('case-form').reset();
            renderToolSelection();
        } else {
            throw new Error(result.message || 'Pipeline failed');
        }

    } catch (error) {
        console.error('Execution error:', error);
        statusMessage.innerHTML = `
            <span class="error-message">Execution failed</span>
            <p>What failed: ${error.message}</p>
            <p>What remains safe: Form inputs preserved, no data written</p>
        `;
        showToast(`Execution failed: ${error.message}`, 'error');

        // Show form again
        setTimeout(() => {
            hideElement('pipeline-status');
            showElement('case-form');
        }, 5000);
    } finally {
        currentCaseId = null;
    }
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
// Results Display
// ============================================================================

function displayResults(caseData, report) {
    currentReport = { caseId: caseData.case_id, report: report };

    document.getElementById('result-case-id').textContent = caseData.case_id;
    document.getElementById('result-title').textContent = caseData.title;
    document.getElementById('result-target').textContent = caseData.target;
    document.getElementById('result-status').textContent = caseData.status;
    document.getElementById('result-status').className = `status-badge ${caseData.status}`;

    const toolResults = caseData.tool_results || [];
    const toolsSuccessful = toolResults.filter(r => r.status === 'success').map(r => r.tool);
    const toolsFailed = toolResults.filter(r => r.status === 'error').map(r => r.tool);

    document.getElementById('result-tools').innerHTML = `
        ${toolsSuccessful.length > 0 ? `<span class="success">${toolsSuccessful.join(', ')}</span>` : ''}
        ${toolsFailed.length > 0 ? `<span class="error"> (Failed: ${toolsFailed.join(', ')})</span>` : ''}
    `;

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
                    <p class="error-message">
                        <strong>What failed:</strong> ${toolResult.error}<br>
                        <strong>What was attempted:</strong> ${toolResult.tool} execution on target<br>
                        <strong>What remains safe:</strong> Other tool results preserved
                    </p>
                `}
            </div>
        </div>
    `).join('');

    const reportActions = `
        <div class="report-actions">
            <button class="btn btn-secondary" id="copy-report-btn" onclick="copyToClipboard(currentReport.report, 'copy-report-btn')">
                Copy Report
            </button>
            <button class="btn btn-secondary" onclick="exportReport(currentReport.caseId, currentReport.report)">
                Export Markdown
            </button>
        </div>
    `;

    document.getElementById('report-content').innerHTML = reportActions + renderMarkdown(report);

    hideElement('new-case-section');
    hideElement('pipeline-status');
    showElement('results-section');

    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth' });
}

// ============================================================================
// Case List Management
// ============================================================================

async function loadCases() {
    const caseList = document.getElementById('case-list');

    try {
        const data = await apiRequest('/cases');

        if (data.cases.length === 0) {
            caseList.innerHTML = '<p class="loading">No cases yet. Create one above.</p>';
            allCases = [];
            return;
        }

        allCases = data.cases.sort((a, b) =>
            new Date(b.created_at) - new Date(a.created_at)
        );

        renderCaseList(allCases);

    } catch (error) {
        console.error('Error loading cases:', error);
        caseList.innerHTML = '<p class="error-message">Failed to load cases</p>';
    }
}

function renderCaseList(cases) {
    const caseList = document.getElementById('case-list');

    if (cases.length === 0) {
        caseList.innerHTML = '<p class="loading">No matching cases found</p>';
        return;
    }

    caseList.innerHTML = cases.map(caseItem => `
        <div class="case-item" data-case-id="${caseItem.case_id}">
            <div class="case-item-header">
                <div class="case-item-title">${caseItem.title}</div>
                <div class="case-item-status ${caseItem.status}">${caseItem.status}</div>
            </div>
            <div class="case-item-meta">
                Case ID: <code>${caseItem.case_id}</code> | Target: <code>${caseItem.target}</code> | Created: ${formatDate(caseItem.created_at)}
            </div>
            <div class="case-item-tools">
                Tools: ${(caseItem.tools_used || []).join(', ')}
            </div>
            ${caseItem.description ? `<div class="case-item-description">${caseItem.description}</div>` : ''}
        </div>
    `).join('');

    document.querySelectorAll('.case-item').forEach(item => {
        item.addEventListener('click', async () => {
            const caseId = item.dataset.caseId;
            await loadCaseDetails(caseId);
        });
    });
}

async function loadCaseDetails(caseId) {
    try {
        showToast('Loading case details...', 'info');
        const caseData = await apiRequest(`/cases/${caseId}`);
        const report = await apiRequest(`/cases/${caseId}/report`);

        displayResults(caseData, report.report);
    } catch (error) {
        console.error('Error loading case details:', error);
        showToast('Failed to load case details', 'error');
    }
}

// ============================================================================
// Query System (formerly "AI Assistant")
// ============================================================================

async function sendQuery() {
    const queryInput = document.getElementById('query-input');
    const message = queryInput.value.trim();

    if (!message) {
        showToast('Enter a query', 'error');
        return;
    }

    const queryMessages = document.getElementById('query-messages');

    const userMessageDiv = document.createElement('div');
    userMessageDiv.className = 'query-message user';
    userMessageDiv.innerHTML = `<strong>Query:</strong> <code>${message}</code>`;
    queryMessages.appendChild(userMessageDiv);

    queryInput.value = '';

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'query-message system loading';
    loadingDiv.innerHTML = '<strong>System:</strong> <span class="processing">Processing...</span>';
    queryMessages.appendChild(loadingDiv);

    queryMessages.scrollTop = queryMessages.scrollHeight;

    try {
        const context = {};
        const currentTarget = document.getElementById('result-target');
        if (currentTarget && currentTarget.textContent) {
            context.target = currentTarget.textContent;
        }

        const response = await apiRequest('/chat', {
            method: 'POST',
            body: JSON.stringify({
                message: message,
                context: context
            })
        });

        loadingDiv.remove();

        const systemMessageDiv = document.createElement('div');
        systemMessageDiv.className = 'query-message system';
        systemMessageDiv.innerHTML = `<strong>System:</strong> ${renderMarkdown(response.response)}`;
        queryMessages.appendChild(systemMessageDiv);

        queryMessages.scrollTop = queryMessages.scrollHeight;

    } catch (error) {
        loadingDiv.remove();
        showToast('Query failed', 'error');
        console.error('Query error:', error);
    }
}

// ============================================================================
// Event Handlers
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Form submission - generate plan instead of executing
    document.getElementById('case-form').addEventListener('submit', (e) => {
        e.preventDefault();

        const formData = new FormData(e.target);
        const selectedTools = getSelectedTools();

        if (selectedTools.length === 0) {
            showToast('Select at least one tool', 'error');
            return;
        }

        const caseData = {
            title: formData.get('title'),
            description: formData.get('description') || null,
            target: formData.get('target'),
            tools: selectedTools,
            tool_options: {}
        };

        // Generate and show execution plan (don't execute yet)
        const plan = generateExecutionPlan(caseData);
        showExecutionPlan(plan);
    });

    // New case button
    document.getElementById('new-case-btn').addEventListener('click', () => {
        hideElement('results-section');
        showElement('new-case-section');
        document.getElementById('new-case-section').scrollIntoView({ behavior: 'smooth' });
    });

    // Search input
    const caseHistorySection = document.querySelector('#case-list').parentElement;
    const searchContainer = document.createElement('div');
    searchContainer.className = 'search-container';
    searchContainer.innerHTML = `
        <input
            type="text"
            id="case-search"
            placeholder="Search cases by title, target, ID, or description..."
            class="search-input"
        />
    `;
    caseHistorySection.insertBefore(searchContainer, caseHistorySection.querySelector('h2').nextSibling);

    document.getElementById('case-search').addEventListener('input', (e) => {
        filterCases(e.target.value);
    });

    // Query system
    document.getElementById('send-query-btn').addEventListener('click', sendQuery);
    document.getElementById('query-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuery();
        }
    });

    // Initialize
    init();
});

// ============================================================================
// Initialization
// ============================================================================

async function init() {
    console.log('Loom OSINT Orchestration Platform - Initializing...');

    await loadAvailableTools();
    await checkHealth();
    await loadCases();

    setInterval(checkHealth, 30000);

    console.log('Loom initialized');
    showToast('Loom ready', 'success');
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }

    .search-container {
        margin: 1rem 0;
    }

    .search-input {
        width: 100%;
        padding: 0.75rem;
        background: var(--bg-tertiary);
        border: 1px solid var(--border);
        border-radius: 0.375rem;
        color: var(--text);
        font-size: 1rem;
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        transition: border-color 0.2s;
    }

    .search-input:focus {
        outline: none;
        border-color: var(--primary);
    }

    .report-actions {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1rem;
        flex-wrap: wrap;
    }

    .report-actions .btn {
        flex: 0 0 auto;
    }

    /* Location badges */
    .location-badge {
        display: inline-block;
        padding: 0.125rem 0.5rem;
        font-size: 0.75rem;
        border-radius: 0.25rem;
        margin: 0.25rem 0;
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
    }

    .location-badge.local {
        background: var(--success);
        color: white;
    }

    .location-badge.remote {
        background: var(--warning);
        color: white;
    }

    /* Execution plan */
    #execution-plan {
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        border-radius: 0.5rem;
        padding: 2rem;
    }

    .plan-header h3 {
        margin: 0 0 0.5rem 0;
    }

    .plan-subtitle {
        color: var(--text-secondary);
        margin-bottom: 1.5rem;
    }

    .plan-section {
        margin-bottom: 1.5rem;
        padding: 1rem;
        background: var(--bg-tertiary);
        border-radius: 0.375rem;
        border-left: 4px solid var(--primary);
    }

    .plan-section h4 {
        margin: 0 0 0.75rem 0;
        color: var(--text-secondary);
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .plan-section .meta {
        color: var(--text-secondary);
        font-size: 0.9rem;
    }

    .plan-list {
        list-style: none;
        padding: 0;
        margin: 0.5rem 0 0 0;
    }

    .plan-list li {
        padding: 0.5rem 0;
        border-bottom: 1px solid var(--border);
    }

    .plan-list li:last-child {
        border-bottom: none;
    }

    .plan-actions {
        display: flex;
        gap: 0.5rem;
        justify-content: flex-end;
        margin-top: 1.5rem;
    }

    .target-id {
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        background: var(--bg);
        padding: 0.5rem;
        border-radius: 0.25rem;
        display: inline-block;
    }

    /* Abort button */
    .btn-abort {
        background: var(--error);
        color: white;
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 0.375rem;
        cursor: pointer;
        font-weight: 600;
    }

    .btn-abort:hover {
        opacity: 0.8;
    }

    .execution-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border);
    }

    /* System identifiers in monospace */
    .case-info code,
    .case-item-meta code,
    .tool-name {
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
    }

    /* Query system (non-anthropomorphic) */
    .query-message {
        margin-bottom: 1rem;
        padding: 0.75rem;
        border-radius: 0.375rem;
        line-height: 1.5;
    }

    .query-message.user {
        background: var(--bg);
        border-left: 3px solid var(--primary);
    }

    .query-message.system {
        background: var(--bg-tertiary);
        border-left: 3px solid var(--success);
    }

    .query-message.loading {
        opacity: 0.7;
    }

    .processing {
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        font-style: normal;
    }
`;
document.head.appendChild(style);
