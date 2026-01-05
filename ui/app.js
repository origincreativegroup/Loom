/**
 * Loom OSINT Orchestration Platform - Frontend Application v2.1
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
let currentReport = null;  // Store current report for export

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
                const key = prompt('API Key required. Please enter your API key:');
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
        showToast('Copied to clipboard!', 'success');
        if (buttonId) {
            const button = document.getElementById(buttonId);
            if (button) {
                const originalText = button.textContent;
                button.textContent = '✓ Copied!';
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
    showToast('Report exported successfully!', 'success');
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
        showToast(`Found ${filtered.length} matching case(s)`, 'info');
    } else {
        showToast('No matching cases found', 'info');
    }
}

// ============================================================================
// Markdown Rendering (Improved)
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
        .replace(/\[([^\]]+)\]\(([^\)]+)\)/gim, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        // Lists (unordered)
        .replace(/^\s*\-\s+(.*)$/gim, '<li>$1</li>')
        // Line breaks
        .replace(/\n\n/gim, '</p><p>')
        .replace(/\n/gim, '<br>');

    // Wrap lists
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

    toolGrid.innerHTML = availableTools.map(tool => `
        <label class="tool-option" title="${tool.description}">
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
        showToast('Starting investigation...', 'info');

        // Show tool progress
        toolProgress.innerHTML = caseData.tools.map(tool => `
            <div class="tool-status-item" id="tool-status-${tool}">
                <span class="tool-name">${tool}</span>
                <span class="tool-state">Queued</span>
            </div>
        `).join('');

        // Create case (returns immediately with queued status)
        const result = await apiRequest('/cases', {
            method: 'POST',
            body: JSON.stringify(caseData)
        });

        const caseId = result.case_id;
        statusMessage.textContent = result.message || 'Pipeline started...';

        // Poll for status updates
        await pollCaseStatus(caseId, statusMessage, toolProgress, caseData.tools);

    } catch (error) {
        console.error('Error creating case:', error);
        statusMessage.innerHTML = `<span class="error-message">Error: ${error.message}</span>`;
        showToast(`Investigation failed: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        setTimeout(() => {
            hideElement('pipeline-status');
            toolProgress.innerHTML = '';
        }, 2000);
    }
}

async function pollCaseStatus(caseId, statusMessage, toolProgress, tools) {
    const maxAttempts = 300; // 5 minutes max (1 second intervals)
    let attempts = 0;
    let pollInterval;

    return new Promise((resolve, reject) => {
        pollInterval = setInterval(async () => {
            attempts++;

            try {
                const status = await apiRequest(`/cases/${caseId}/status`);

                // Update status message
                statusMessage.textContent = status.message || `Status: ${status.status}`;

                // Update tool progress based on completed/failed lists
                tools.forEach(tool => {
                    const toolElement = document.getElementById(`tool-status-${tool}`);
                    if (toolElement) {
                        const stateSpan = toolElement.querySelector('.tool-state');
                        if (status.tools_completed.includes(tool)) {
                            stateSpan.textContent = 'Completed';
                            stateSpan.className = 'tool-state completed';
                        } else if (status.tools_failed.includes(tool)) {
                            stateSpan.textContent = 'Failed';
                            stateSpan.className = 'tool-state failed';
                        } else if (status.status === 'processing' || status.status === 'synthesizing') {
                            stateSpan.textContent = 'Running...';
                            stateSpan.className = 'tool-state running';
                        } else if (status.status === 'queued') {
                            stateSpan.textContent = 'Queued';
                            stateSpan.className = 'tool-state queued';
                        }
                    }
                });

                // Check if pipeline is complete
                if (status.status === 'completed') {
                    clearInterval(pollInterval);
                    statusMessage.textContent = 'Pipeline completed! Loading results...';
                    showToast('Investigation complete!', 'success');

                    // Load full case details
                    const caseDetails = await apiRequest(`/cases/${caseId}`);
                    const report = await apiRequest(`/cases/${caseId}/report`);

                    // Show results
                    displayResults(caseDetails, report.report);

                    // Refresh case list
                    loadCases();

                    // Reset form
                    document.getElementById('case-form').reset();
                    renderToolSelection(); // Re-check default tools

                    resolve(status);
                } else if (status.status === 'error') {
                    clearInterval(pollInterval);
                    throw new Error(status.message || 'Pipeline failed');
                }

                // Timeout after max attempts
                if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    throw new Error('Pipeline timeout - check status manually');
                }

            } catch (error) {
                clearInterval(pollInterval);
                reject(error);
            }
        }, 1000); // Poll every second
    });
}

function displayResults(caseData, report) {
    // Store current report for export
    currentReport = { caseId: caseData.case_id, report: report };

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

    // Unified report with action buttons
    const reportActions = `
        <div class="report-actions">
            <button class="btn btn-secondary" id="copy-report-btn" onclick="copyToClipboard(currentReport.report, 'copy-report-btn')">
                📋 Copy Report
            </button>
            <button class="btn btn-secondary" onclick="exportReport(currentReport.caseId, currentReport.report)">
                💾 Export Markdown
            </button>
        </div>
    `;

    document.getElementById('report-content').innerHTML = reportActions + renderMarkdown(report);

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
            allCases = [];
            return;
        }

        // Sort by created date (newest first) and store globally
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
// AI Research Assistant
// ============================================================================

async function sendChatMessage() {
    const chatInput = document.getElementById('chat-input');
    const message = chatInput.value.trim();

    if (!message) {
        showToast('Please enter a message', 'error');
        return;
    }

    const chatMessages = document.getElementById('chat-messages');

    // Add user message to chat
    const userMessageDiv = document.createElement('div');
    userMessageDiv.className = 'chat-message user';
    userMessageDiv.innerHTML = `<strong>You:</strong> ${message}`;
    chatMessages.appendChild(userMessageDiv);

    // Clear input
    chatInput.value = '';

    // Show loading indicator
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'chat-message assistant loading';
    loadingDiv.innerHTML = '<strong>Assistant:</strong> <span class="typing-indicator">Thinking...</span>';
    chatMessages.appendChild(loadingDiv);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        // Get current context (if viewing a case)
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

        // Remove loading indicator
        loadingDiv.remove();

        // Add assistant response
        const assistantMessageDiv = document.createElement('div');
        assistantMessageDiv.className = 'chat-message assistant';
        assistantMessageDiv.innerHTML = `<strong>Assistant:</strong> ${renderMarkdown(response.response)}`;
        chatMessages.appendChild(assistantMessageDiv);

        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;

    } catch (error) {
        loadingDiv.remove();
        showToast('Failed to get response from AI assistant', 'error');
        console.error('Chat error:', error);
    }
}

// ============================================================================
// Event Handlers
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Form submission
    document.getElementById('case-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(e.target);
        const selectedTools = getSelectedTools();

        if (selectedTools.length === 0) {
            showToast('Please select at least one OSINT tool', 'error');
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

    // New case button
    document.getElementById('new-case-btn').addEventListener('click', () => {
        hideElement('results-section');
        showElement('new-case-section');
        document.getElementById('new-case-section').scrollIntoView({ behavior: 'smooth' });
    });

    // Search input (create if doesn't exist)
    const caseHistorySection = document.querySelector('#case-list').parentElement;
    const searchContainer = document.createElement('div');
    searchContainer.className = 'search-container';
    searchContainer.innerHTML = `
        <input
            type="text"
            id="case-search"
            placeholder="🔍 Search cases by title, target, ID, or description..."
            class="search-input"
        />
    `;
    caseHistorySection.insertBefore(searchContainer, caseHistorySection.querySelector('h2').nextSibling);

    document.getElementById('case-search').addEventListener('input', (e) => {
        filterCases(e.target.value);
    });

    // AI Chat Assistant
    document.getElementById('send-chat-btn').addEventListener('click', sendChatMessage);
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // Initialize the app
    init();
});

// ============================================================================
// Initialization
// ============================================================================

async function init() {
    console.log('🕸️ Loom OSINT Orchestration Platform v2.1 - Initializing...');

    // Load available tools
    await loadAvailableTools();

    // Check health
    await checkHealth();

    // Load existing cases
    await loadCases();

    // Refresh health every 30 seconds
    setInterval(checkHealth, 30000);

    console.log('✅ Loom initialized successfully');
    showToast('Loom OSINT Platform Ready', 'success');
}

// Add CSS animations for toasts
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
`;
document.head.appendChild(style);
