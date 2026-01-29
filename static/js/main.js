/**
 * TSG Builder - Main Application JavaScript
 * 
 * Handles core application functionality:
 * - State management
 * - TSG generation via streaming
 * - Image upload
 * - Display and clipboard operations
 */

/* ==========================================================================
   Application State
   ========================================================================== */

let currentThreadId = null;
let currentTSG = '';
let eventSource = null;
let isMarkdownPreview = localStorage.getItem('tsgPreviewMode') === 'true';

// Image storage
let uploadedImages = [];
const MAX_IMAGES = 10;

// Run cancellation support
let currentRunId = null;

/* ==========================================================================
   Initialization
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    initImageUpload();
    initPreviewToggle();
});

/* ==========================================================================
   Preview Toggle
   ========================================================================== */

function initPreviewToggle() {
    // Apply saved preference on load
    if (isMarkdownPreview) {
        document.getElementById('rawToggle').classList.remove('active');
        document.getElementById('previewToggle').classList.add('active');
        document.getElementById('tsgOutput').classList.add('preview-mode');
    }
}

function setPreviewMode(preview) {
    isMarkdownPreview = preview;
    localStorage.setItem('tsgPreviewMode', preview);
    
    // Update toggle buttons
    document.getElementById('rawToggle').classList.toggle('active', !preview);
    document.getElementById('previewToggle').classList.toggle('active', preview);
    
    // Update output display
    const output = document.getElementById('tsgOutput');
    output.classList.toggle('preview-mode', preview);
    
    // Re-render current TSG if we have content
    if (currentTSG) {
        displayTSG(currentTSG);
    }
}

/* ==========================================================================
   Image Upload
   ========================================================================== */

function initImageUpload() {
    const dropZone = document.getElementById('imageDropZone');
    const fileInput = document.getElementById('imageInput');
    
    // Drag and drop handlers
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
        fileInput.value = ''; // Reset to allow same file again
    });
    
    // Note: Clipboard paste for images is intentionally disabled to avoid
    // conflicts with pasting text from rich-text sources like OneNote.
    // Use drag-and-drop or the file picker to add images.
}

function handleFiles(files) {
    const fileArray = Array.from(files);
    
    // Filter for images only
    const imageFiles = fileArray.filter(f => f.type.startsWith('image/'));
    
    if (imageFiles.length === 0) {
        showError('Please select image files only.');
        return;
    }
    
    // Check max limit
    if (uploadedImages.length + imageFiles.length > MAX_IMAGES) {
        showError(`Maximum ${MAX_IMAGES} images allowed. You have ${uploadedImages.length} already.`);
        return;
    }
    
    // Process each file
    imageFiles.forEach(file => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const dataUrl = e.target.result;
            // Extract base64 data and type
            const [header, base64Data] = dataUrl.split(',');
            const mimeType = header.match(/data:(.*?);/)[1];
            
            uploadedImages.push({
                name: file.name,
                type: mimeType,
                data: base64Data,
                preview: dataUrl
            });
            
            updateImagePreviews();
        };
        reader.readAsDataURL(file);
    });
}

function updateImagePreviews() {
    const container = document.getElementById('imagePreviews');
    const countSpan = document.getElementById('imageCount');
    
    container.innerHTML = uploadedImages.map((img, index) => `
        <div class="image-preview">
            <img src="${img.preview}" alt="${img.name}">
            <button class="remove-btn" onclick="removeImage(${index})" title="Remove">×</button>
            <div class="image-name">${img.name}</div>
        </div>
    `).join('');
    
    countSpan.textContent = uploadedImages.length > 0 ? `(${uploadedImages.length}/${MAX_IMAGES})` : '';
}

function removeImage(index) {
    uploadedImages.splice(index, 1);
    updateImagePreviews();
}

function clearImages() {
    uploadedImages = [];
    updateImagePreviews();
}

/* ==========================================================================
   Status Check
   ========================================================================== */

async function checkStatus(retryCount = 0) {
    const maxRetries = 3;
    const retryDelay = 500; // ms
    
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const indicator = document.getElementById('statusIndicator');
        const text = document.getElementById('statusText');
        const btn = document.getElementById('generateBtn');
        
        if (data.ready) {
            indicator.className = 'status-indicator ready';
            const prefix = data.agents?.name_prefix || 'TSG';
            text.textContent = `3 agents ready (${prefix})`;
            btn.disabled = false;
        } else {
            indicator.className = 'status-indicator error';
            text.textContent = data.error || 'Setup required';
            btn.disabled = true;
            
            // Auto-open setup if needs configuration
            if (data.needs_setup) {
                openSetup();
            }
        }
    } catch (error) {
        // Retry a few times on startup in case server isn't ready yet
        if (retryCount < maxRetries) {
            console.log(`Status check failed, retrying in ${retryDelay}ms... (${retryCount + 1}/${maxRetries})`);
            setTimeout(() => checkStatus(retryCount + 1), retryDelay);
            return;
        }
        document.getElementById('statusIndicator').className = 'status-indicator error';
        document.getElementById('statusText').textContent = 'Failed to check status';
    }
}

/* ==========================================================================
   Activity Feed
   ========================================================================== */

function addActivity(icon, message, type = 'status') {
    const feed = document.getElementById('activityFeed');
    const item = document.createElement('div');
    item.className = `activity-item ${type}`;
    
    const time = new Date().toLocaleTimeString();
    item.innerHTML = `
        <span class="activity-icon">${icon}</span>
        <span class="activity-message">${message}</span>
        <span class="activity-time">${time}</span>
    `;
    
    feed.appendChild(item);
    feed.scrollTop = feed.scrollHeight;
}

function clearActivity() {
    document.getElementById('activityFeed').innerHTML = '';
}

/* ==========================================================================
   Streaming TSG Generation
   ========================================================================== */

function generateTSGWithStreaming(endpoint, body) {
    return new Promise((resolve, reject) => {
        clearActivity();
        addActivity('🚀', 'Starting agent...', 'status');
        
        // Track last event time for "still working" indicator
        let lastEventTime = Date.now();
        let waitingInterval = null;
        const startTime = Date.now();
        
        function updateWaitingIndicator() {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const sinceLast = Math.floor((Date.now() - lastEventTime) / 1000);
            if (sinceLast > 10) {
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                document.getElementById('loadingText').textContent = `⏳ Still working... (${timeStr} elapsed)`;
            }
        }
        
        function cleanup() {
            if (waitingInterval) {
                clearInterval(waitingInterval);
                waitingInterval = null;
            }
        }
        
        // Check every 5 seconds if we haven't received events
        waitingInterval = setInterval(updateWaitingIndicator, 5000);
        
        // Use fetch with streaming for SSE
        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(response => {
            if (!response.ok) {
                cleanup();
                return response.json().then(err => {
                    throw new Error(err.error || 'Request failed');
                });
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            function processText(text) {
                buffer += text;
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            // Update last event time (except for keepalives)
                            if (event.type !== 'keepalive') {
                                lastEventTime = Date.now();
                            }
                            handleStreamEvent(event, 
                                (data) => { cleanup(); resolve(data); },
                                (err) => { cleanup(); reject(err); }
                            );
                        } catch (e) {
                            // Ignore parse errors for malformed events
                        }
                    }
                }
            }
            
            function read() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        cleanup();
                        if (buffer.startsWith('data: ')) {
                            try {
                                const event = JSON.parse(buffer.slice(6));
                                handleStreamEvent(event, resolve, reject);
                            } catch (e) {}
                        }
                        return;
                    }
                    processText(decoder.decode(value, { stream: true }));
                    read();
                }).catch(err => {
                    cleanup();
                    // Handle network errors (incomplete chunked read, connection reset, etc.)
                    const errorMsg = err.message || 'Unknown error';
                    if (errorMsg.includes('chunked') || errorMsg.includes('network') || errorMsg.includes('aborted')) {
                        reject(new Error('Connection lost during generation. This may be due to a timeout or network issue. Try again or use a shorter input.'));
                    } else {
                        reject(err);
                    }
                });
            }
            
            read();
        }).catch(err => {
            cleanup();
            reject(err);
        });
    });
}

function handleStreamEvent(event, resolve, reject) {
    switch (event.type) {
        case 'run_started':
            // Store run ID for cancellation support
            currentRunId = event.data.run_id;
            // Enable cancel button now that we have a run ID
            const cancelBtn = document.getElementById('cancelBtn');
            cancelBtn.disabled = false;
            cancelBtn.textContent = '✕ Cancel';
            break;
        
        case 'thread_created':
            currentThreadId = event.data.thread_id;
            break;
        
        case 'cancelled':
            // Run was cancelled by user
            currentRunId = null;
            addActivity('🛑', 'Run cancelled by user', 'status');
            reject(new Error('Generation cancelled'));
            break;
            
        case 'status':
            // Use icon from event data if provided, otherwise derive from status
            const statusIcons = {
                'queued': '⏳',
                'in_progress': '🔄',
                'requires_action': '⚡',
                'completed': '✅',
                'failed': '❌'
            };
            const statusIcon = event.data.icon || statusIcons[event.data.status] || '•';
            addActivity(statusIcon, event.data.message, 'status');
            document.getElementById('loadingText').textContent = event.data.message;
            break;
        
        case 'stage_start':
            // New stage beginning
            addActivity(event.data.icon || '▶️', event.data.message, 'stage-start');
            document.getElementById('loadingText').textContent = event.data.message;
            break;
        
        case 'stage_complete':
            // Stage finished
            addActivity(event.data.icon || '✅', event.data.message, 'stage-complete');
            document.getElementById('loadingText').textContent = event.data.message;
            break;
        
        case 'progress':
            // Progress update (don't add to activity feed, just update loading text)
            document.getElementById('loadingText').textContent = event.data.message;
            break;
            
        case 'tool':
            const toolClass = event.data.status === 'completed' ? 'tool completed' : 'tool';
            addActivity(event.data.icon || '🔧', event.data.message, toolClass);
            // Also update loading text for tool calls
            if (event.data.status === 'running') {
                document.getElementById('loadingText').textContent = event.data.message;
            }
            break;
        
        case 'tool_call':
            // Legacy tool_call event - convert to new format
            const legacyIcon = event.data.type === 'mcp' ? '📚' : '🌐';
            const legacyMsg = event.data.status === 'completed' 
                ? `✅ ${event.data.name}` 
                : `${legacyIcon} ${event.data.name}...`;
            addActivity(event.data.status === 'completed' ? '✅' : legacyIcon, legacyMsg, 'tool');
            break;
            
        case 'activity':
            addActivity('📝', event.data.message, 'status');
            break;
            
        case 'error':
            handleErrorEvent(event, reject);
            break;
        
        case 'debug_info':
            // Track debug info for display in activity feed
            if (event.data.thread_id || event.data.run_id) {
                const infoMsg = `Session: ${event.data.thread_id || 'N/A'} | Run: ${event.data.run_id || 'N/A'}`;
                addActivity('🔗', infoMsg, 'status');
            }
            break;
            
        case 'result':
            currentRunId = null;  // Clear run ID on success
            currentThreadId = event.data.thread_id;
            currentTSG = event.data.tsg;
            resolve(event.data);
            break;
            
        case 'done':
            addActivity('✓', 'Agent completed', 'status');
            break;
            
        case 'keepalive':
            // Ignore keepalives
            break;
    }
}

function handleErrorEvent(event, reject) {
    // Check if this is a retryable error vs fatal error
    // Use is_retryable from backend if available, fallback to error_type check
    const errorType = event.data.error_type;
    const isRetryable = event.data.is_retryable !== undefined 
        ? event.data.is_retryable 
        : ['rate_limit', 'timeout', 'mcp_error', 'tool_error'].includes(errorType);
    
    if (isRetryable) {
        // Retryable error - show warning style, don't reject
        const cssClass = errorType === 'rate_limit' ? 'rate-limit' : 'error';
        addActivity(event.data.icon || '⚠️', event.data.message, cssClass);
        document.getElementById('loadingText').textContent = event.data.message;
    } else {
        // Fatal error - reject the promise
        currentRunId = null;  // Clear run ID on error
        
        // Show error with hint in activity feed if available
        let activityMsg = event.data.message;
        if (event.data.hint) {
            activityMsg += ` 💡 ${event.data.hint}`;
        }
        addActivity('❌', activityMsg, 'error');
        
        // Build comprehensive error message with debug info
        let errorMsg = event.data.message;
        
        // Add hint if available
        if (event.data.hint) {
            errorMsg += `\n\n💡 ${event.data.hint}`;
        }
    
        // Add debug info section
        const debugParts = [];
        if (event.data.thread_id) debugParts.push(`Thread ID: ${event.data.thread_id}`);
        if (event.data.run_id) debugParts.push(`Run ID: ${event.data.run_id}`);
        if (event.data.agent_id) debugParts.push(`Agent ID: ${event.data.agent_id}`);
        if (event.data.error_code) debugParts.push(`Error Code: ${event.data.error_code}`);
    
        if (debugParts.length > 0) {
            errorMsg += '\n\n--- Debug Information ---\n' + debugParts.join('\n');
        }
    
        // Include raw_response if available
        if (event.data.raw_response) {
            errorMsg += '\n\n--- Raw Agent Response ---\n' + event.data.raw_response;
        }
    
        reject(new Error(errorMsg));
    }
}

/* ==========================================================================
   Run Cancellation
   ========================================================================== */

async function cancelRun() {
    if (!currentRunId) {
        console.log('No active run to cancel');
        return;
    }
    
    const cancelBtn = document.getElementById('cancelBtn');
    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelling...';
    
    try {
        const response = await fetch(`/api/cancel/${currentRunId}`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            const err = await response.json();
            console.error('Cancel failed:', err.error);
        }
        // The stream will receive a 'cancelled' event and handle cleanup
    } catch (error) {
        console.error('Cancel request failed:', error);
    }
}

/* ==========================================================================
   TSG Generation & Answer Submission
   ========================================================================== */

async function generateTSG() {
    const notes = document.getElementById('notesInput').value.trim();
    if (!notes) {
        showError('Please enter some notes first.');
        return;
    }

    showLoading(true);
    hideMessages();
    document.getElementById('questionsPanel').classList.add('hidden');

    try {
        // Prepare request body with notes and images
        const requestBody = { notes };
        
        // Include images if any were uploaded
        if (uploadedImages.length > 0) {
            requestBody.images = uploadedImages.map(img => ({
                data: img.data,
                type: img.type
            }));
            addActivity('🖼️', `Including ${uploadedImages.length} image(s) in request`, 'status');
        }
        
        const data = await generateTSGWithStreaming('/api/generate/stream', requestBody);
        
        displayTSG(data.tsg);

        // Check if we need feedback (MISSING items or review notes)
        const hasQuestions = data.questions && !data.complete;
        const hasWarnings = data.warnings && data.warnings.length > 0;
        
        if (hasQuestions || hasWarnings) {
            showFeedbackPanel(hasQuestions ? data.questions : null, data.warnings);
        } else {
            showSuccess('TSG generated successfully!');
        }

    } catch (error) {
        showError(getUserFriendlyError(error));
        // Enable Clear Session so user can reset after errors
        if (currentThreadId || document.getElementById('notesInput').value.trim()) {
            document.getElementById('clearSessionBtn').disabled = false;
        }
    } finally {
        showLoading(false);
    }
}

async function submitAnswers() {
    const answers = document.getElementById('answersInput').value.trim();
    if (!answers) {
        showError('Please provide answers to the questions.');
        return;
    }

    showLoading(true);
    hideMessages();

    try {
        const data = await generateTSGWithStreaming('/api/answer/stream', {
            thread_id: currentThreadId,
            answers
        });

        displayTSG(data.tsg);

        // Check if we need more feedback (MISSING items or review notes)
        const hasQuestions = data.questions && !data.complete;
        const hasWarnings = data.warnings && data.warnings.length > 0;
        
        if (hasQuestions || hasWarnings) {
            showFeedbackPanel(hasQuestions ? data.questions : null, data.warnings);
            document.getElementById('answersInput').value = '';
        } else {
            document.getElementById('questionsPanel').classList.add('hidden');
            showSuccess('TSG updated and complete!');
        }

    } catch (error) {
        showError(getUserFriendlyError(error));
        // Enable Clear Session so user can reset after errors
        document.getElementById('clearSessionBtn').disabled = false;
    } finally {
        showLoading(false);
    }
}

function skipQuestions() {
    document.getElementById('questionsPanel').classList.add('hidden');
    showSuccess('TSG saved with current content.');
}

/* ==========================================================================
   Session Management
   ========================================================================== */

async function clearSession() {
    // Cancel any active run first
    if (currentRunId) {
        try {
            await fetch(`/api/cancel/${currentRunId}`, { method: 'POST' });
        } catch (e) {
            // Ignore errors - run may have already finished
        }
        currentRunId = null;
    }
    
    // Clear server-side session if we have one
    if (currentThreadId) {
        try {
            await fetch(`/api/session/${currentThreadId}`, { method: 'DELETE' });
        } catch (e) {
            // Ignore errors - just clearing local state
        }
    }
    
    // Reset local state
    currentThreadId = null;
    currentTSG = '';
    
    // Reset UI - clear input notes, output, and questions
    document.getElementById('notesInput').value = '';
    document.getElementById('tsgOutput').innerHTML = '<span style="color: var(--text-secondary);">Your generated TSG will appear here...</span>';
    document.getElementById('copyBtn').disabled = true;
    document.getElementById('downloadBtn').disabled = true;
    document.getElementById('clearSessionBtn').disabled = true;
    document.getElementById('questionsPanel').classList.add('hidden');
    document.getElementById('answersInput').value = '';
    hideMessages();
    
    // Clear uploaded images
    clearImages();
    
    showSuccess('Session cleared. Ready for a fresh start!');
    setTimeout(() => hideMessages(), 3000);
}

/* ==========================================================================
   Display Functions
   ========================================================================== */

function displayTSG(tsg) {
    const output = document.getElementById('tsgOutput');
    if (isMarkdownPreview) {
        output.innerHTML = marked.parse(tsg);
    } else {
        output.textContent = tsg;
    }
    document.getElementById('copyBtn').disabled = false;
    document.getElementById('downloadBtn').disabled = false;
    document.getElementById('clearSessionBtn').disabled = false;
}

function showQuestions(questions) {
    document.getElementById('questionsText').textContent = questions;
    document.getElementById('questionsPanel').classList.remove('hidden');
}

/**
 * Shows the unified feedback panel with MISSING items and/or review notes.
 * @param {string|null} questions - MISSING item questions from the pipeline
 * @param {string[]|null} warnings - Review notes/suggestions from the review stage
 */
function showFeedbackPanel(questions, warnings) {
    const content = document.getElementById('feedbackContent');
    let html = '';
    
    // Add MISSING items section if present
    if (questions) {
        html += `
            <div class="feedback-section">
                <h4>⚠️ Missing Information</h4>
                <pre class="questions-text">${escapeHtml(questions)}</pre>
            </div>
        `;
    }
    
    // Add review notes section if present
    if (warnings && warnings.length > 0) {
        const warningItems = warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('');
        html += `
            <div class="feedback-section">
                <h4>📋 Review Notes</h4>
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                    The reviewer flagged these items. Address them if needed:
                </p>
                <ul class="review-notes-list">${warningItems}</ul>
            </div>
        `;
    }
    
    content.innerHTML = html;
    document.getElementById('questionsPanel').classList.remove('hidden');
    // Hide the standalone warning banner since we're showing warnings in the panel
    document.getElementById('warningBanner').classList.add('hidden');
}

function showLoading(show) {
    const loading = document.getElementById('loadingIndicator');
    const btn = document.getElementById('generateBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const submitBtn = document.getElementById('submitAnswersBtn');
    const skipBtn = document.getElementById('skipBtn');
    
    if (show) {
        loading.classList.remove('hidden');
        btn.disabled = true;
        // Disable feedback buttons during generation
        if (submitBtn) submitBtn.disabled = true;
        if (skipBtn) skipBtn.disabled = true;
        // Reset cancel button state (will be enabled when run_started event arrives)
        cancelBtn.disabled = true;
        cancelBtn.textContent = '✕ Cancel';
        // Clear activity feed for new run
        document.getElementById('activityFeed').innerHTML = '';
    } else {
        loading.classList.add('hidden');
        btn.disabled = false;
        // Re-enable feedback buttons
        if (submitBtn) submitBtn.disabled = false;
        if (skipBtn) skipBtn.disabled = false;
        // Clear run ID when loading hides
        currentRunId = null;
    }
}

function showError(message) {
    const el = document.getElementById('errorMessage');
    
    // Parse message for debug info and raw response sections
    const debugSeparator = '--- Debug Information ---';
    const rawSeparator = '--- Raw Agent Response ---';
    
    let errorPart = message;
    let debugPart = null;
    let rawPart = null;
    
    // Extract debug info section
    if (message.includes(debugSeparator)) {
        const idx = message.indexOf(debugSeparator);
        errorPart = message.substring(0, idx).trim();
        let remainder = message.substring(idx + debugSeparator.length);
        
        // Check if raw response follows debug info
        if (remainder.includes(rawSeparator)) {
            const rawIdx = remainder.indexOf(rawSeparator);
            debugPart = remainder.substring(0, rawIdx).trim();
            rawPart = remainder.substring(rawIdx + rawSeparator.length).trim();
        } else {
            debugPart = remainder.trim();
        }
    } else if (message.includes(rawSeparator)) {
        const idx = message.indexOf(rawSeparator);
        errorPart = message.substring(0, idx).trim();
        rawPart = message.substring(idx + rawSeparator.length).trim();
    }
    
    // Build the HTML
    let html = `<div style="margin-bottom: 10px;">${escapeHtml(errorPart)}</div>`;
    
    // Add debug info section (always visible for easier debugging)
    if (debugPart) {
        html += `
            <div style="margin-top: 10px; padding: 10px; background: #2d2d2d; border-radius: 4px; border-left: 3px solid var(--primary);">
                <strong style="color: var(--primary);">🔍 Debug Information</strong>
                <pre style="margin-top: 8px; font-size: 12px; white-space: pre-wrap; color: #ccc;">${escapeHtml(debugPart)}</pre>
            </div>
        `;
    }
    
    // Add raw response in collapsible section
    if (rawPart) {
        html += `
            <details style="margin-top: 10px;">
                <summary style="cursor: pointer; color: var(--primary);">Show raw agent response</summary>
                <pre style="margin-top: 8px; padding: 10px; background: #1e1e1e; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; max-height: 300px; overflow-y: auto;">${escapeHtml(rawPart)}</pre>
            </details>
        `;
    }
    
    el.innerHTML = html;
    el.classList.remove('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Converts technical fetch/network errors into user-friendly messages.
 * Used by generateTSG and submitAnswers to handle server disconnections gracefully.
 */
function getUserFriendlyError(error) {
    const msg = (error.message || '').toLowerCase();
    
    // Detect server disconnection / network errors
    if (msg.includes('failed to fetch') ||
        msg.includes('networkerror') ||
        msg.includes('network error') ||
        msg.includes('connection refused') ||
        msg.includes('net::err_connection_refused') ||
        msg.includes('net::err_connection_reset') ||
        msg.includes('load failed')) {
        return 'Connection to server lost. Please restart TSG Builder and try again.';
    }
    
    // Already has a user-friendly message from our code
    if (msg.includes('connection lost during generation')) {
        return error.message;
    }
    
    // Return original message for other errors
    return error.message;
}

function showSuccess(message) {
    const el = document.getElementById('successMessage');
    el.textContent = message;
    el.classList.remove('hidden');
}

function hideMessages() {
    document.getElementById('errorMessage').classList.add('hidden');
    document.getElementById('successMessage').classList.add('hidden');
    document.getElementById('warningBanner').classList.add('hidden');
}

function showWarnings(warnings) {
    if (!warnings || warnings.length === 0) return;
    
    const el = document.getElementById('warningBanner');
    const warningItems = warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('');
    el.innerHTML = `
        <h4>⚠️ Review Notes</h4>
        <ul>${warningItems}</ul>
    `;
    el.classList.remove('hidden');
}

/* ==========================================================================
   Input & Clipboard
   ========================================================================== */

function clearInput() {
    document.getElementById('notesInput').value = '';
    document.getElementById('tsgOutput').innerHTML = 
        '<span style="color: var(--text-secondary);">Your generated TSG will appear here...</span>';
    document.getElementById('questionsPanel').classList.add('hidden');
    document.getElementById('copyBtn').disabled = true;
    document.getElementById('downloadBtn').disabled = true;
    document.getElementById('clearSessionBtn').disabled = true;
    hideMessages();
    currentThreadId = null;
    currentTSG = '';
    // Also clear uploaded images
    clearImages();
}

async function copyTSG() {
    if (!currentTSG) return;
    
    try {
        await navigator.clipboard.writeText(currentTSG);
        const btn = document.getElementById('copyBtn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Copied!';
        setTimeout(() => { btn.innerHTML = originalText; }, 2000);
    } catch (error) {
        showError('Failed to copy to clipboard');
    }
}

function downloadTSG() {
    if (!currentTSG) return;
    
    // Extract title from TSG content (looks for # **Title** section)
    let filename = null;
    const titleMatch = currentTSG.match(/^#\s*\*\*(.+?)\*\*\s*$/m);
    if (titleMatch && titleMatch[1]) {
        // Sanitize title for filesystem: remove/replace invalid characters
        filename = titleMatch[1]
            .trim()
            .replace(/[<>:"/\\|?*]/g, '-')  // Replace invalid filename chars
            .replace(/\s+/g, '-')             // Replace spaces with dashes
            .replace(/-+/g, '-')              // Collapse multiple dashes
            .replace(/^-|-$/g, '')            // Remove leading/trailing dashes
            .substring(0, 100);               // Limit length
    }
    
    // Fallback to timestamp if title extraction failed or resulted in empty string
    if (!filename) {
        const now = new Date();
        const timestamp = now.toISOString().replace(/[:.]/g, '-').substring(0, 19);
        filename = `tsg-${timestamp}`;
    }
    
    filename += '.md';
    
    // Create blob and trigger download
    const blob = new Blob([currentTSG], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    // Show success message with filename
    showSuccess(`TSG downloaded as "${filename}"`);
    setTimeout(() => hideMessages(), 4000);
}

// Example input embedded directly to avoid file bundling issues in executable
const EXAMPLE_INPUT = `Problem/questions:

When I try to create an Agent in my project (with the GA version in an Azure AI Foundry project, not a hub-based project), I can only use model deployments deployed in my current Azure AI Foundry resource, despite having connected Azure OpenAI resources.


	1. When the OAI model is deployed on project level, the option to select a model is available when trying to create an agent from the studio. But the models deployed on the connected OpenAI resource does not show up. Is this a limitation?
	2. Even if we create the agent via SDK using a model deployment from the connected OpenAI resource, there is no option to select the deployments from the OpenAI resource. The only model available in the dropdown are the models deployed on the project level and not on the connect OAI resource level. 

Generally: "When using an Agent in my project, why can't I use it/see it with a model deployment in a connected Azure OpenAI resource?" 


Background:

https://learn.microsoft.com/en-us/azure/ai-foundry/agents/environment-setup?view=foundry-classic
https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/capability-hosts?view=foundry-classic
https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry?view=foundry-classic#microsoft-foundry-portals 


Limitation:

Known issue with Agents seeing connected OpenAI resource deployments in the UI. Agents deployed by template also can't use connected resources unless their capability host is configured to see that resource. This applies to Foundry Classic UI. 

There is a known feature gap with Agents being able to see connected OpenAI resource model deployments. Specifically, Currently, we lack a UX for managing capability hosts. (Classic Foundry UI).
 
The project capability host is only configured by default with the project AI Services resource by default and in the templates we publish. It can be deleted/recreated to point to an Azure OpenAI resource instead of the AI Services resource so that all Agents in the project see the OpenAI resource deployments instead. 



Workaround: 

Create new capability host that points at an OpenAI resource instead of the AI Services resource using the aiServicesConnections property:
https://github.com/orgs/azure-ai-foundry/discussions/59

As of now there's no easy way to do this. However, this is a way.
	1. The connected OpenAI resource should be in the same region as the AIServices resource.
	2. You would need to create capability host. This could disrupt any existing agents under the AIServices resource.
How to create capability host?
Below is a python code - replace everywhere you see {something}.

import requests
import json
from azure.identity import DefaultAzureCredential
token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token 
 
 
 ## Create account capability host
url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/capabilityHosts/{any-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {"properties": {"capabilityHostKind": "Agents"}}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "insomnia/11.0.1"
}
response = requests.request("PUT", url, json=payload, headers=headers, params=querystring)
print(response.text)
## Create project capability host
url = "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/{res-group-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-resource}/projects/{project-name}/capabilityHosts/{any-proj-cap-host-name}/"
querystring = {"api-version":"2025-04-01-preview"}
payload = {"properties": {
        "capabilityHostKind": "Agents",
        "aiServicesConnections": ["{connection-name-of-aoai-resource}"]
    }}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "insomnia/11.0.1"
}
response = requests.request("PUT", url, json=payload, headers=headers, params=querystring)
print(response.text)
The above would let you use Agents ONLY with the connected AOAI resource mentioned in the "aiServicesConnections" parameter. You could update or delete the capability host to be able to use deployments from other AOAI resource connection or from the parent AIServices resource.



NOTE: you cannot update a capability host, only delete and recreate.`;

function loadExample() {
    document.getElementById('notesInput').value = EXAMPLE_INPUT;
}
