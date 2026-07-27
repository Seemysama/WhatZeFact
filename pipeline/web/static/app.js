/**
 * WhatZeFact — Frontend JavaScript
 * Handles script generation, video generation, and real-time progress via WebSocket.
 */

// ─── Socket.IO Connection ────────────────────────────
const socket = io();

// ─── DOM Elements ────────────────────────────────────
const topicInput = document.getElementById('topic-input');
const generateScriptBtn = document.getElementById('generate-script-btn');
const scriptSection = document.getElementById('script-section');
const scriptContent = document.getElementById('script-content');
const generateVideoBtn = document.getElementById('generate-video-btn');
const regenerateBtn = document.getElementById('regenerate-btn');
const progressCard = document.getElementById('progress-card');
const progressBar = document.getElementById('progress-bar');
const previewCard = document.getElementById('preview-card');
const videoPreview = document.getElementById('video-preview');
const configBanner = document.getElementById('config-banner');
const voiceSelect = document.getElementById('voice-select');
const subtitlesToggle = document.getElementById('subtitles-toggle');
const logoToggle = document.getElementById('logo-toggle');
const toastEl = document.getElementById('toast');

// ─── State ───────────────────────────────────────────
let currentScript = null;
let isGenerating = false;

// ─── Init ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await checkConfig();
    await loadVoices();
    await loadGallery();
    setupEventListeners();
});

function setupEventListeners() {
    // Generate script on button click or Enter
    generateScriptBtn.addEventListener('click', handleGenerateScript);
    topicInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleGenerateScript();
    });

    // Quick topic buttons
    document.querySelectorAll('.quick-topic').forEach(btn => {
        btn.addEventListener('click', () => {
            topicInput.value = btn.textContent.trim();
            topicInput.focus();
        });
    });

    // Generate video
    generateVideoBtn.addEventListener('click', handleGenerateVideo);
    regenerateBtn.addEventListener('click', handleGenerateScript);
}

// ─── Config Check ────────────────────────────────────
async function checkConfig() {
    try {
        const res = await fetch('/api/config-status');
        const data = await res.json();
        
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        
        if (!data.configured) {
            configBanner.classList.add('visible');
            statusDot.classList.add('error');
            statusText.textContent = 'Config manquante';
            document.getElementById('config-errors').innerHTML = 
                data.errors.map(e => `<p>${e}</p>`).join('');
        } else {
            statusDot.classList.remove('error');
            statusText.textContent = 'Prêt';
        }
    } catch (err) {
        console.error('Config check failed:', err);
    }
}

// ─── Load Voices ─────────────────────────────────────
async function loadVoices() {
    try {
        const res = await fetch('/api/voices');
        const voices = await res.json();
        
        voiceSelect.innerHTML = voices.map(v => {
            const icon = v.gender === 'Female' ? '👩' : '👨';
            const selected = v.id.includes('Vivienne') ? 'selected' : '';
            return `<option value="${v.id}" ${selected}>${icon} ${v.name}</option>`;
        }).join('');
    } catch (err) {
        console.error('Failed to load voices:', err);
    }
}

// ─── Generate Script ─────────────────────────────────
async function handleGenerateScript() {
    const topic = topicInput.value.trim();
    if (!topic) {
        showToast('Écris un sujet !', 'error');
        topicInput.focus();
        return;
    }

    generateScriptBtn.classList.add('loading');
    generateScriptBtn.disabled = true;

    try {
        const res = await fetch('/api/generate-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic }),
        });

        const data = await res.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        currentScript = data.script;
        renderScript(data.script);
        scriptSection.classList.add('visible');
        
        // Scroll to script
        scriptSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showToast('Script généré !', 'success');

    } catch (err) {
        showToast('Erreur de connexion', 'error');
        console.error(err);
    } finally {
        generateScriptBtn.classList.remove('loading');
        generateScriptBtn.disabled = false;
    }
}

// ─── Render Script ───────────────────────────────────
function renderScript(script) {
    let html = '';

    // Title
    html += `<h2 style="margin-bottom:16px;font-size:20px;">🎬 ${escapeHtml(script.title)}</h2>`;

    // Hook
    html += `<div class="script-hook">🪝 ${escapeHtml(script.hook)}</div>`;

    // Segments
    html += '<div class="script-segments">';
    script.segments.forEach((seg, i) => {
        const emotionEmoji = {
            curious: '🤔', funny: '😂', surprised: '😲',
            dramatic: '🎭', informative: '📚'
        }[seg.emotion] || '📌';

        html += `
            <div class="script-segment" data-index="${i}">
                <div class="segment-number">${emotionEmoji} Segment ${i + 1}</div>
                <div class="segment-text" contenteditable="true" data-field="text">${escapeHtml(seg.text)}</div>
                <div class="segment-keywords">
                    ${(seg.visual_keywords || []).map(k => `<span class="keyword-tag">🔍 ${escapeHtml(k)}</span>`).join('')}
                </div>
            </div>
        `;
    });
    html += '</div>';

    // Outro
    html += `<div class="script-outro">👋 ${escapeHtml(script.outro_text)}</div>`;

    // Hashtags
    if (script.hashtags) {
        html += `<div style="margin-top:12px;color:var(--text-muted);font-size:13px;">${script.hashtags.join(' ')}</div>`;
    }

    scriptContent.innerHTML = html;

    // Listen for edits
    document.querySelectorAll('.segment-text[contenteditable]').forEach(el => {
        el.addEventListener('blur', () => {
            const idx = parseInt(el.closest('.script-segment').dataset.index);
            if (currentScript && currentScript.segments[idx]) {
                currentScript.segments[idx].text = el.textContent.trim();
            }
        });
    });
}

// ─── Generate Video ──────────────────────────────────
async function handleGenerateVideo() {
    if (!currentScript) {
        showToast('Génère un script d\'abord !', 'error');
        return;
    }

    if (isGenerating) return;
    isGenerating = true;

    generateVideoBtn.disabled = true;
    progressCard.classList.add('visible');
    previewCard.classList.remove('visible');
    
    // Reset progress
    updateProgress(0);
    resetProgressSteps();

    try {
        const res = await fetch('/api/generate-video', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script: currentScript,
                voice: voiceSelect.value,
                subtitles: subtitlesToggle.checked,
                logo: logoToggle.checked,
            }),
        });

        const data = await res.json();
        if (data.error) {
            showToast(data.error, 'error');
            isGenerating = false;
            generateVideoBtn.disabled = false;
        }
        // Progress will come via WebSocket

    } catch (err) {
        showToast('Erreur de connexion', 'error');
        isGenerating = false;
        generateVideoBtn.disabled = false;
    }
}

// ─── WebSocket Progress ──────────────────────────────
socket.on('progress', (data) => {
    updateProgress(data.progress);
    
    // Update step states
    const stepMap = {
        voice: 'step-voice',
        search: 'step-search',
        assemble: 'step-assemble',
        done: 'step-done',
    };

    const stepOrder = ['voice', 'search', 'assemble', 'done'];
    const currentIdx = stepOrder.indexOf(data.step);

    stepOrder.forEach((step, idx) => {
        const el = document.getElementById(stepMap[step]);
        if (!el) return;
        
        if (idx < currentIdx) {
            el.className = 'progress-step done';
            el.querySelector('.step-icon').textContent = '✓';
        } else if (idx === currentIdx) {
            el.className = 'progress-step active';
            el.querySelector('.step-icon').textContent = '⟳';
        } else {
            el.className = 'progress-step';
        }
    });
});

socket.on('video_ready', (data) => {
    isGenerating = false;
    generateVideoBtn.disabled = false;
    
    // Mark all steps as done
    document.querySelectorAll('.progress-step').forEach(el => {
        el.className = 'progress-step done';
        el.querySelector('.step-icon').textContent = '✓';
    });
    updateProgress(100);

    // Show preview
    videoPreview.src = `/api/preview/${data.filename}`;
    previewCard.classList.add('visible');
    
    // Setup download button
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.onclick = () => {
        window.location.href = `/api/download/${data.filename}`;
    };
    
    previewCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    showToast('🎉 Vidéo générée !', 'success');
    
    // Refresh gallery
    loadGallery();
});

socket.on('error', (data) => {
    isGenerating = false;
    generateVideoBtn.disabled = false;
    showToast(`Erreur : ${data.message}`, 'error');
});

function updateProgress(percent) {
    progressBar.style.width = `${percent}%`;
}

function resetProgressSteps() {
    document.querySelectorAll('.progress-step').forEach(el => {
        el.className = 'progress-step';
        el.querySelector('.step-icon').textContent = el.dataset.defaultIcon || '○';
    });
}

// ─── Gallery ─────────────────────────────────────────
async function loadGallery() {
    try {
        const res = await fetch('/api/videos');
        const videos = await res.json();
        
        const grid = document.getElementById('gallery-grid');
        
        if (videos.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column:1/-1;">
                    <div class="icon">🎬</div>
                    <p>Aucune vidéo générée pour l'instant.<br>Lance ta première génération !</p>
                </div>
            `;
            return;
        }

        grid.innerHTML = videos.map(v => `
            <div class="gallery-item" onclick="previewGalleryVideo('${v.filename}')">
                <video class="gallery-thumb" src="/api/preview/${v.filename}" muted></video>
                <div class="gallery-info">
                    <div class="gallery-title">${escapeHtml(v.title)}</div>
                    <div class="gallery-meta">${v.size_mb} MB</div>
                </div>
            </div>
        `).join('');

        // Auto-play thumbnails on hover
        grid.querySelectorAll('.gallery-item').forEach(item => {
            const video = item.querySelector('video');
            item.addEventListener('mouseenter', () => video.play());
            item.addEventListener('mouseleave', () => { video.pause(); video.currentTime = 0; });
        });
        
    } catch (err) {
        console.error('Failed to load gallery:', err);
    }
}

function previewGalleryVideo(filename) {
    videoPreview.src = `/api/preview/${filename}`;
    previewCard.classList.add('visible');
    
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.onclick = () => {
        window.location.href = `/api/download/${filename}`;
    };
    
    previewCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ─── Utilities ───────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    toastEl.textContent = message;
    toastEl.className = `toast visible ${type}`;
    
    clearTimeout(toastEl._timeout);
    toastEl._timeout = setTimeout(() => {
        toastEl.classList.remove('visible');
    }, 4000);
}
