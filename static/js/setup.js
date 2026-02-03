/**
 * TSG Builder - Setup Modal JavaScript
 * 
 * Handles setup and configuration functionality:
 * - Modal open/close
 * - Configuration save/load
 * - Validation checks
 * - Agent creation
 */

/* ==========================================================================
   Modal Control
   ========================================================================== */

async function openSetup() {
    document.getElementById('setupModal').classList.remove('hidden');
    await loadConfig();
    updateSetupOverallStatus();
}

function closeSetup() {
    document.getElementById('setupModal').classList.add('hidden');
    checkStatus(); // Refresh main status
}

/* ==========================================================================
   Configuration Management
   ========================================================================== */

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        
        document.getElementById('configEndpoint').value = config.PROJECT_ENDPOINT || '';
        document.getElementById('configModel').value = config.MODEL_DEPLOYMENT_NAME || '';
        document.getElementById('configBing').value = config.BING_CONNECTION_NAME || '';
        document.getElementById('configAgentName').value = config.AGENT_NAME || 'TSG-Builder';
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

async function saveConfig() {
    const btn = document.getElementById('saveConfigBtn');
    const status = document.getElementById('configSaveStatus');
    
    btn.disabled = true;
    status.textContent = 'Saving...';
    status.style.color = 'var(--text-secondary)';
    
    const config = {
        PROJECT_ENDPOINT: document.getElementById('configEndpoint').value.trim(),
        MODEL_DEPLOYMENT_NAME: document.getElementById('configModel').value.trim(),
        BING_CONNECTION_NAME: document.getElementById('configBing').value.trim(),
        AGENT_NAME: document.getElementById('configAgentName').value.trim() || 'TSG-Builder',
    };
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
        if (result.success) {
            status.textContent = '✓ Saved!';
            status.style.color = 'var(--success)';
            updateSetupOverallStatus();
        } else {
            status.textContent = '✗ ' + (result.error || 'Failed to save');
            status.style.color = 'var(--error)';
        }
    } catch (error) {
        status.textContent = '✗ ' + error.message;
        status.style.color = 'var(--error)';
    } finally {
        btn.disabled = false;
        setTimeout(() => { status.textContent = ''; }, 3000);
    }
}

/* ==========================================================================
   Validation
   ========================================================================== */

async function runValidation() {
    const btn = document.getElementById('validateBtn');
    const list = document.getElementById('validationList');
    
    btn.disabled = true;
    btn.textContent = '🔄 Validating...';
    list.innerHTML = '<li class="validation-item"><span class="validation-icon">🔄</span><span class="validation-message">Running validation checks...</span></li>';
    
    try {
        const response = await fetch('/api/validate');
        const result = await response.json();
        
        list.innerHTML = '';
        
        for (const check of result.checks) {
            const item = document.createElement('li');
            const statusClass = check.passed ? 'passed' : (check.critical ? 'failed' : 'warning');
            const icon = check.passed ? '✓' : (check.critical ? '✗' : '⚠️');
            
            item.className = `validation-item ${statusClass}`;
            item.innerHTML = `
                <span class="validation-icon">${icon}</span>
                <span class="validation-name">${check.name}</span>
                <span class="validation-message">${check.message}</span>
            `;
            list.appendChild(item);
        }
        
        // Enable/disable create agent button based on validation
        const createBtn = document.getElementById('createAgentBtn');
        createBtn.disabled = !result.ready_for_agent;
        
        updateSetupOverallStatus();
        
    } catch (error) {
        list.innerHTML = `<li class="validation-item failed"><span class="validation-icon">✗</span><span class="validation-message">Validation failed: ${error.message}</span></li>`;
    } finally {
        btn.disabled = false;
        btn.textContent = '🔍 Run Validation';
    }
}

/* ==========================================================================
   Agent Creation
   ========================================================================== */

async function createAgent() {
    const btn = document.getElementById('createAgentBtn');
    const status = document.getElementById('agentCreateStatus');
    const agentStatusDiv = document.getElementById('agentStatus');
    
    // Check if we're recreating existing agents
    const isRecreating = btn.textContent.includes('Recreate');
    
    btn.disabled = true;
    btn.textContent = isRecreating ? '🔄 Recreating...' : '🔄 Creating...';
    status.textContent = 'This may take a moment...';
    status.style.color = 'var(--text-secondary)';
    
    try {
        const response = await fetch('/api/create-agent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            status.textContent = isRecreating ? '✓ Agents recreated!' : '✓ Agents created!';
            status.style.color = 'var(--success)';
            
            // Handle v2 format (object with name/version) or v1 format (string ID)
            const getAgentDisplay = (agent) => {
                if (typeof agent === 'object' && agent.name) {
                    return agent.name.substring(0, 20);
                }
                return String(agent).substring(0, 8);
            };
            
            agentStatusDiv.innerHTML = `
                <div class="agent-info">
                    <span class="icon">🤖</span>
                    <div class="details">
                        <div class="agent-name">3 Agents Ready (${result.agent_name})</div>
                        <div class="agent-id" style="font-size: 0.75em;">
                            Researcher: ${getAgentDisplay(result.agents.researcher)}...<br>
                            Writer: ${getAgentDisplay(result.agents.writer)}...<br>
                            Reviewer: ${getAgentDisplay(result.agents.reviewer)}...
                        </div>
                    </div>
                </div>
            `;
            
            btn.textContent = '🔄 Recreate Agents';
            btn.disabled = false;  // Keep enabled for future recreates
            updateSetupOverallStatus();
        } else {
            // Display error with hint if available
            let errorHtml = `<span style="color: var(--error);">✗ ${result.error}</span>`;
            if (result.hint) {
                errorHtml += `<br><span style="color: var(--text-secondary); font-size: 12px; margin-top: 4px; display: block;">💡 ${result.hint}</span>`;
            }
            status.innerHTML = errorHtml;
            btn.disabled = false;
            btn.textContent = isRecreating ? '🔄 Recreate Agents' : '🤖 Create Agents';
        }
    } catch (error) {
        status.innerHTML = `<span style="color: var(--error);">✗ ${error.message}</span>`;
        btn.disabled = false;
        btn.textContent = isRecreating ? '🔄 Recreate Agents' : '🤖 Create Agents';
    }
}

/* ==========================================================================
   Status Updates
   ========================================================================== */

async function updateSetupOverallStatus() {
    const statusDiv = document.getElementById('setupOverallStatus');
    
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.ready) {
            statusDiv.className = 'setup-status ready';
            statusDiv.innerHTML = '<span>✓</span> <span>Ready to generate TSGs!</span>';
        } else if (data.needs_setup) {
            statusDiv.className = 'setup-status pending';
            statusDiv.innerHTML = '<span>⚠️</span> <span>Setup incomplete</span>';
        } else {
            statusDiv.className = 'setup-status pending';
            statusDiv.innerHTML = '<span>⏳</span> <span>Checking...</span>';
        }
        
        // Update agents status display
        if (data.agents && data.agents.configured) {
            const prefix = data.agents.name_prefix || 'TSG';
            document.getElementById('agentStatus').innerHTML = `
                <div class="agent-info">
                    <span class="icon">🤖</span>
                    <div class="details">
                        <div class="agent-name">3 Agents Ready (${prefix})</div>
                        <div class="agent-id" style="font-size: 0.75em;">
                            Researcher: ${data.agents.researcher}<br>
                            Writer: ${data.agents.writer}<br>
                            Reviewer: ${data.agents.reviewer}
                        </div>
                    </div>
                </div>
            `;
            const createBtn = document.getElementById('createAgentBtn');
            createBtn.textContent = '🔄 Recreate Agents';
            createBtn.disabled = false;  // Keep enabled so user can recreate if needed
        }
        
    } catch (error) {
        statusDiv.className = 'setup-status';
        statusDiv.innerHTML = '<span>⚠️</span> <span>Status check failed</span>';
    }
}
