/**
 * BeamDrop Client Application
 * Reactive, zero-dependency, mobile-first controller.
 */

(function () {
  'use strict';

  // State
  let filesData = [];
  let currentFilter = 'all';
  let hostInfo = null;
  let lastClipUpdated = 0;
  let activePin = localStorage.getItem('beamdrop_pin') || '';

  // Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const fileInput = document.getElementById('file-input');
  const cameraInput = document.getElementById('camera-input');
  const fileList = document.getElementById('file-list');
  const badgeFileCount = document.getElementById('badge-file-count');
  const filterPills = document.querySelectorAll('.pill');
  const btnRefreshFiles = document.getElementById('btn-refresh-files');
  const btnDownloadAll = document.getElementById('btn-download-all');
  const btnShowQr = document.getElementById('btn-show-qr');
  const qrModal = document.getElementById('qr-modal');
  const qrBackdrop = document.getElementById('qr-backdrop');
  const qrClose = document.getElementById('qr-close');
  const qrUrlText = document.getElementById('qr-url-text');
  const btnCopyUrl = document.getElementById('btn-copy-url');
  const previewModal = document.getElementById('preview-modal');
  const previewBackdrop = document.getElementById('preview-backdrop');
  const previewClose = document.getElementById('preview-close');
  const previewTitle = document.getElementById('preview-title');
  const previewBody = document.getElementById('preview-body');
  const dropOverlay = document.getElementById('drop-overlay');
  const uploadProgressCard = document.getElementById('upload-progress-container');
  const progressFilename = document.getElementById('progress-filename');
  const progressPercent = document.getElementById('progress-percent');
  const progressFill = document.getElementById('progress-fill');
  const clipboardTextarea = document.getElementById('clipboard-textarea');
  const btnSendClip = document.getElementById('btn-send-clip');
  const btnCopyClip = document.getElementById('btn-copy-clip');
  const btnClearClip = document.getElementById('btn-clear-clip');
  const clipMeta = document.getElementById('clip-meta');
  const clipboardHistory = document.getElementById('clipboard-history');
  const pinOverlay = document.getElementById('pin-overlay');
  const pinInput = document.getElementById('pin-input');
  const pinSubmit = document.getElementById('pin-submit');
  const pinError = document.getElementById('pin-error');
  const quickLinkInput = document.getElementById('quick-link-input');
  const btnQuickSend = document.getElementById('btn-quick-send');
  const hostAddressLabel = document.getElementById('host-address');
  const toastEl = document.getElementById('toast');

  // Helpers
  function showToast(message, duration = 3000) {
    toastEl.textContent = message;
    toastEl.classList.remove('hidden');
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(() => {
      toastEl.classList.add('hidden');
    }, duration);
  }

  function apiHeaders(extra = {}) {
    const headers = { ...extra };
    if (activePin) {
      headers['X-Beam-PIN'] = activePin;
    }
    return headers;
  }

  // Check auth
  async function checkAuth() {
    try {
      const res = await fetch('/api/auth', { headers: apiHeaders() });
      const data = await res.json();
      if (data.pin_required && !data.authenticated) {
        pinOverlay.classList.remove('hidden');
        pinInput.focus();
        return false;
      } else {
        pinOverlay.classList.add('hidden');
        return true;
      }
    } catch (e) {
      return false;
    }
  }

  pinSubmit.addEventListener('click', async () => {
    const pin = pinInput.value.trim();
    if (!pin) return;
    try {
      const res = await fetch('/api/verify-pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: pin })
      });
      const data = await res.json();
      if (data.success) {
        activePin = pin;
        localStorage.setItem('beamdrop_pin', pin);
        pinOverlay.classList.add('hidden');
        pinError.classList.add('hidden');
        showToast('🔓 Connected securely');
        init();
      } else {
        pinError.classList.remove('hidden');
      }
    } catch (err) {
      pinError.classList.remove('hidden');
    }
  });

  // Tab Switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const tabId = 'tab-' + btn.getAttribute('data-tab');
      const targetPane = document.getElementById(tabId);
      if (targetPane) targetPane.classList.add('active');
    });
  });

  // Load Status & Info
  async function loadStatus() {
    try {
      const res = await fetch('/api/status', { headers: apiHeaders() });
      if (!res.ok) return;
      hostInfo = await res.json();
      hostAddressLabel.textContent = hostInfo.url.replace('http://', '');
      qrUrlText.textContent = hostInfo.url;
    } catch (e) {
      console.warn('Status error:', e);
    }
  }

  // Load Files
  async function loadFiles() {
    try {
      const res = await fetch('/api/files', { headers: apiHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      filesData = data.files || [];
      badgeFileCount.textContent = filesData.length;
      renderFiles();
    } catch (e) {
      console.warn('Load files error:', e);
    }
  }

  function getFileIcon(category) {
    switch (category) {
      case 'image': return '🖼️';
      case 'video': return '🎬';
      case 'audio': return '🎵';
      case 'pdf':   return '📕';
      case 'text':  return '📄';
      default:      return '📦';
    }
  }

  function renderFiles() {
    const filtered = filesData.filter(file => {
      if (currentFilter === 'all') return true;
      if (currentFilter === 'docs') return file.category === 'pdf' || file.category === 'text';
      return file.category === currentFilter;
    });

    if (filtered.length === 0) {
      fileList.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📂</div>
          <h4>No files matching filter</h4>
          <p>Drop any files above to transfer across your devices.</p>
        </div>
      `;
      return;
    }

    fileList.innerHTML = filtered.map(file => {
      const canPreview = ['image', 'video', 'audio', 'text', 'pdf'].includes(file.category);
      return `
        <div class="file-card glass-panel" data-name="${encodeURIComponent(file.name)}">
          <div class="file-top">
            <div class="file-type-icon">${getFileIcon(file.category)}</div>
            <div class="file-info">
              <div class="file-name" title="${file.name}">${file.name}</div>
              <div class="file-meta">${file.size_formatted} • ${file.modified_iso}</div>
            </div>
          </div>
          <div class="file-actions">
            ${canPreview ? `<button class="btn btn-secondary btn-sm btn-preview" data-name="${encodeURIComponent(file.name)}" data-cat="${file.category}">👁️ View</button>` : ''}
            <a href="/api/download/${encodeURIComponent(file.name)}" download="${file.name}" class="btn btn-primary btn-sm">⬇️ Download</a>
            <button class="btn btn-danger btn-sm btn-delete" data-name="${encodeURIComponent(file.name)}" title="Delete file">🗑️</button>
          </div>
        </div>
      `;
    }).join('');

    // Attach actions
    fileList.querySelectorAll('.btn-preview').forEach(btn => {
      btn.addEventListener('click', () => {
        openPreview(decodeURIComponent(btn.getAttribute('data-name')), btn.getAttribute('data-cat'));
      });
    });

    fileList.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', () => {
        deleteFile(decodeURIComponent(btn.getAttribute('data-name')));
      });
    });
  }

  // Filter Pills
  filterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      filterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      currentFilter = pill.getAttribute('data-filter');
      renderFiles();
    });
  });

  btnRefreshFiles.addEventListener('click', loadFiles);

  // File Upload Logic
  async function uploadFiles(fileListItems) {
    if (!fileListItems || fileListItems.length === 0) return;

    uploadProgressCard.classList.remove('hidden');
    const totalFiles = fileListItems.length;

    for (let i = 0; i < totalFiles; i++) {
      const file = fileListItems[i];
      progressFilename.textContent = `(${i + 1}/${totalFiles}) ${file.name}`;
      progressPercent.textContent = '0%';
      progressFill.style.width = '0%';

      const formData = new FormData();
      formData.append('file', file, file.name);

      await new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        if (activePin) {
          xhr.setRequestHeader('X-Beam-PIN', activePin);
        }

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            progressPercent.textContent = `${pct}%`;
            progressFill.style.width = `${pct}%`;
          }
        };

        xhr.onload = () => {
          resolve();
        };

        xhr.onerror = () => {
          showToast(`❌ Failed uploading ${file.name}`);
          resolve();
        };

        xhr.send(formData);
      });
    }

    setTimeout(() => {
      uploadProgressCard.classList.add('hidden');
      showToast(`⚡ Finished beaming ${totalFiles} file(s)!`);
      loadFiles();
    }, 400);
  }

  fileInput.addEventListener('change', (e) => {
    uploadFiles(e.target.files);
    fileInput.value = '';
  });

  cameraInput.addEventListener('change', (e) => {
    uploadFiles(e.target.files);
    cameraInput.value = '';
  });

  // Drag and Drop (Global + Zone)
  let dragCounter = 0;
  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    dropOverlay.classList.remove('hidden');
  });

  window.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) {
      dropOverlay.classList.add('hidden');
      dragCounter = 0;
    }
  });

  window.addEventListener('dragover', (e) => {
    e.preventDefault();
  });

  window.addEventListener('drop', (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.add('hidden');
    if (e.dataTransfer && e.dataTransfer.files) {
      uploadFiles(e.dataTransfer.files);
    }
  });

  // Delete File
  async function deleteFile(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return;
    try {
      const res = await fetch(`/api/files/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: apiHeaders()
      });
      const data = await res.json();
      if (data.success) {
        showToast(`🗑️ Deleted ${filename}`);
        loadFiles();
      } else {
        showToast(`Error: ${data.error}`);
      }
    } catch (e) {
      showToast('Failed to delete file');
    }
  }

  // Previews
  async function openPreview(filename, category) {
    previewTitle.textContent = filename;
    previewBody.innerHTML = '<p>Loading preview...</p>';
    previewModal.classList.remove('hidden');

    const previewUrl = `/api/preview/${encodeURIComponent(filename)}`;
    if (category === 'image') {
      previewBody.innerHTML = `<img src="${previewUrl}" alt="${filename}">`;
    } else if (category === 'video') {
      previewBody.innerHTML = `<video controls autoplay src="${previewUrl}"></video>`;
    } else if (category === 'audio') {
      previewBody.innerHTML = `<audio controls autoplay src="${previewUrl}"></audio>`;
    } else if (category === 'pdf') {
      previewBody.innerHTML = `<iframe src="${previewUrl}" style="width:100%;height:60vh;border:none;"></iframe>`;
    } else if (category === 'text') {
      try {
        const res = await fetch(previewUrl, { headers: apiHeaders() });
        const text = await res.text();
        const escaped = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        previewBody.innerHTML = `<pre>${escaped}</pre>`;
      } catch (err) {
        previewBody.innerHTML = `<p>Failed reading file content.</p>`;
      }
    }
  }

  function closePreview() {
    previewModal.classList.add('hidden');
    previewBody.innerHTML = '';
  }
  previewClose.addEventListener('click', closePreview);
  previewBackdrop.addEventListener('click', closePreview);

  // QR Modal
  btnShowQr.addEventListener('click', () => {
    qrModal.classList.remove('hidden');
  });
  function closeQr() {
    qrModal.classList.add('hidden');
  }
  qrClose.addEventListener('click', closeQr);
  qrBackdrop.addEventListener('click', closeQr);

  btnCopyUrl.addEventListener('click', () => {
    if (hostInfo && hostInfo.url) {
      navigator.clipboard.writeText(hostInfo.url).then(() => {
        showToast('📋 Copied connection link!');
      });
    }
  });

  // Download All as Zip
  btnDownloadAll.addEventListener('click', () => {
    window.location.href = '/api/download-all.zip';
  });

  // Live Clipboard
  async function loadClipboard(silent = false) {
    try {
      const res = await fetch('/api/clipboard', { headers: apiHeaders() });
      if (!res.ok) return;
      const json = await res.json();
      const data = json.data;
      if (data.last_updated > lastClipUpdated) {
        lastClipUpdated = data.last_updated;
        if (document.activeElement !== clipboardTextarea) {
          clipboardTextarea.value = data.current || '';
        }
        clipMeta.textContent = `Synced • ${data.current.length} chars`;
        renderHistory(data.history || []);
      }
    } catch (e) {
      if (!silent) console.warn('Clipboard poll error:', e);
    }
  }

  function renderHistory(history) {
    if (!history || history.length === 0) {
      clipboardHistory.innerHTML = '<p class="history-empty">No recent snippets.</p>';
      return;
    }
    clipboardHistory.innerHTML = history.slice(0, 8).map(item => {
      const timeStr = new Date(item.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return `
        <div class="history-item">
          <span class="history-text" title="${item.text}">${item.text}</span>
          <span class="subtext">${timeStr}</span>
          <button class="btn btn-secondary btn-sm btn-hist-copy" data-text="${encodeURIComponent(item.text)}">Copy</button>
        </div>
      `;
    }).join('');

    clipboardHistory.querySelectorAll('.btn-hist-copy').forEach(btn => {
      btn.addEventListener('click', () => {
        const text = decodeURIComponent(btn.getAttribute('data-text'));
        navigator.clipboard.writeText(text).then(() => {
          showToast('📋 Copied from history!');
        });
      });
    });
  }

  btnSendClip.addEventListener('click', async () => {
    const text = clipboardTextarea.value;
    try {
      const res = await fetch('/api/clipboard', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text: text })
      });
      const data = await res.json();
      if (data.success) {
        showToast('⚡ Clipboard synced to all devices!');
        loadClipboard(true);
      }
    } catch (e) {
      showToast('❌ Failed syncing clipboard');
    }
  });

  btnCopyClip.addEventListener('click', () => {
    navigator.clipboard.writeText(clipboardTextarea.value).then(() => {
      showToast('📋 Copied to device clipboard!');
    }).catch(() => {
      showToast('❌ Unable to access clipboard');
    });
  });

  btnClearClip.addEventListener('click', async () => {
    if (!confirm('Clear shared clipboard?')) return;
    try {
      await fetch('/api/clipboard', { method: 'DELETE', headers: apiHeaders() });
      clipboardTextarea.value = '';
      showToast('🗑️ Cleared clipboard');
      loadClipboard(true);
    } catch (e) {
      showToast('Failed clearing clipboard');
    }
  });

  // Quick Mobile Link Send
  btnQuickSend.addEventListener('click', async () => {
    const text = quickLinkInput.value.trim();
    if (!text) return;
    try {
      await fetch('/api/clipboard', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text: text })
      });
      quickLinkInput.value = '';
      showToast('⚡ Sent to PC clipboard!');
      loadClipboard(true);
    } catch (e) {
      showToast('Failed sending text');
    }
  });

  // Init
  async function init() {
    const authorized = await checkAuth();
    if (!authorized) return;
    await loadStatus();
    await loadFiles();
    await loadClipboard();

    // Regular polling for real-time clipboard updates & file updates
    setInterval(() => loadClipboard(true), 2500);
    setInterval(() => loadFiles(), 5000);
  }

  init();
})();
