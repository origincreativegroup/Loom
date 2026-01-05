/**
 * Loom OSINT Console - Frontend Application
 */

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8787'
    : `http://${window.location.hostname}:8787`;

let API_KEY = localStorage.getItem('loom_api_key') || '';

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

// ============================================================================
// Markdown Rendering (Simple)
// ============================================================================

function renderMarkdown(text) {
    // Simple markdown rendering (for a production app, use marked.js or similar)
    let html = text
        // Headers
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        // Bold
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        // Italic
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        // Links
        .replace(/\[([^\]]+)\]\(([^\)]+)\)/gim, '<a href="$2" target="_blank">$1</a>')
        // Line breaks
        .replace(/\n\n/gim, '</p><p>')
        .replace(/\n/gim, '<br>');

    return `<p>${html}</p>`;
}

// ============================================================================
// Health Check
// ============================================================================

async function checkHealth() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    try {
        const health = await apiRequest('/health');

        const ollama = health.ollama === 'ok';
        const searxng = health.searxng === 'ok';

        if (ollama && searxng) {
            statusDot.className = 'status-dot healthy';
            statusText.textContent = 'All systems operational';
        } else if (ollama || searxng) {
            statusDot.className = 'status-dot degraded';
            statusText.textContent = 'Some services unavailable';
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

    try {
        // Disable form
        submitBtn.disabled = true;
        showElement('pipeline-status');
        statusMessage.textContent = 'Starting OSINT pipeline...';

        // Create case
        const result = await apiRequest('/cases', {
            method: 'POST',
            body: JSON.stringify(caseData)
        });

        if (result.status === 'completed') {
            statusMessage.textContent = 'Pipeline completed! Loading report...';

            // Load report
            const report = await apiRequest(`/cases/${result.case_id}/report`);

            // Show results
            displayResults(result.case_id, caseData.title, result.status, report.report);

            // Refresh case list
            loadCases();

            // Reset form
            document.getElementById('case-form').reset();
        } else {
            throw new Error(result.message || 'Pipeline failed');
        }

    } catch (error) {
        console.error('Error creating case:', error);
        statusMessage.innerHTML = `<span class="error-message">Error: ${error.message}</span>`;
    } finally {
        submitBtn.disabled = false;
        hideElement('pipeline-status');
    }
}

function displayResults(caseId, title, status, report) {
    document.getElementById('result-case-id').textContent = caseId;
    document.getElementById('result-title').textContent = title;
    document.getElementById('result-status').textContent = status;
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
                    Case ID: ${caseItem.case_id} | Created: ${formatDate(caseItem.created_at)}
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

        displayResults(caseId, caseData.title, caseData.status, report.report);
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
    const caseData = {
        title: formData.get('title'),
        description: formData.get('description') || null,
        initial_query: formData.get('initial_query')
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
    console.log('Loom OSINT Console - Initializing...');

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
