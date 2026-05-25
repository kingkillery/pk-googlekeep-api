(() => {
  'use strict';

  const extractBtn = document.getElementById('extractBtn');
  const saveSelectedBtn = document.getElementById('saveSelectedBtn');
  const saveAllBtn = document.getElementById('saveAllBtn');
  const selectAllCheckbox = document.getElementById('selectAll');
  const statusEl = document.getElementById('status');
  const resultsEl = document.getElementById('results');
  const countEl = document.getElementById('count');
  const noteListEl = document.getElementById('noteList');
  const errorEl = document.getElementById('error');

  let currentNotes = [];
  const hasFileSystemAccess = typeof window.showDirectoryPicker === 'function';

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove('hidden');
  }
  function hideError() {
    errorEl.classList.add('hidden');
  }

  function sanitizeFilename(name) {
    name = name.replace(/[<>:"/\\|?*]/g, '_').trim();
    name = name.replace(/^[.\s]+|[.\s]+$/g, '');
    return name.substring(0, 100) || 'untitled';
  }

  function noteToMarkdown(note) {
    const fm = {
      title: note.title || '',
      source: 'google_keep',
      source_section: note.source_section || 'main',
      color: note.color || '',
      pinned: !!note.pinned,
      archived: !!note.archived,
      labels: note.labels || [],
      is_list: !!note.is_list,
    };
    let md = '---\n';
    for (const [k, v] of Object.entries(fm)) {
      if (Array.isArray(v)) {
        md += `${k}:\n` + v.map(i => `  - ${i}\n`).join('');
      } else if (typeof v === 'boolean') {
        md += `${k}: ${String(v).toLowerCase()}\n`;
      } else {
        md += `${k}: ${v}\n`;
      }
    }
    md += '---\n\n';
    if (fm.title) md += `# ${fm.title}\n\n`;
    if (fm.is_list && note.items && note.items.length) {
      for (const [txt, checked] of note.items) {
        md += `- ${checked ? '[x]' : '[ ]'} ${txt}\n`;
      }
      md += '\n';
    } else if (note.text) {
      md += `${note.text}\n\n`;
    }
    md += '---\n*Imported from Google Keep*';
    return md;
  }

  function renderNoteList() {
    noteListEl.innerHTML = '';
    currentNotes.forEach((note, idx) => {
      const item = document.createElement('label');
      item.className = 'note-item';
      item.title = note.title || '(no title)';

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.index = idx;
      cb.checked = true;

      const text = document.createElement('span');
      text.className = 'note-text';
      text.textContent = note.title || '(no title)';

      const tag = document.createElement('span');
      tag.className = 'note-tag';
      tag.textContent = note.source_section || 'main';

      item.appendChild(cb);
      item.appendChild(text);
      item.appendChild(tag);
      noteListEl.appendChild(item);
    });
    updateSelectAllState();
  }

  function getSelectedIndices() {
    const boxes = noteListEl.querySelectorAll('input[type="checkbox"]');
    return Array.from(boxes).filter(cb => cb.checked).map(cb => parseInt(cb.dataset.index, 10));
  }

  function updateSelectAllState() {
    const boxes = noteListEl.querySelectorAll('input[type="checkbox"]');
    const checked = noteListEl.querySelectorAll('input[type="checkbox"]:checked');
    selectAllCheckbox.checked = boxes.length > 0 && boxes.length === checked.length;
  }

  noteListEl.addEventListener('change', (e) => {
    if (e.target.tagName === 'INPUT' && e.target.type === 'checkbox') {
      updateSelectAllState();
    }
  });

  selectAllCheckbox.addEventListener('change', () => {
    const boxes = noteListEl.querySelectorAll('input[type="checkbox"]');
    boxes.forEach(cb => cb.checked = selectAllCheckbox.checked);
  });

  async function extractNotes() {
    hideError();
    extractBtn.disabled = true;
    statusEl.textContent = 'Scanning notes on this page...';
    resultsEl.classList.add('hidden');
    currentNotes = [];

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.url || !tab.url.includes('keep.google.com')) {
        showError('Please navigate to keep.google.com first.');
        extractBtn.disabled = false;
        return;
      }

      const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractNotes' });
      if (!response || !response.notes) {
        showError('Could not extract notes. Try refreshing the page.');
        extractBtn.disabled = false;
        return;
      }

      currentNotes = response.notes;
      if (currentNotes.length === 0) {
        statusEl.textContent = 'No notes found on this page.';
        extractBtn.disabled = false;
        return;
      }

      statusEl.textContent = 'Select the notes you want to save, then click Save.';
      countEl.textContent = `${currentNotes.length} note${currentNotes.length === 1 ? '' : 's'} found (${response.section}).`;
      renderNoteList();
      resultsEl.classList.remove('hidden');
      extractBtn.disabled = false;

      if (!hasFileSystemAccess) {
        showError('Your browser does not support folder picking. Use the Keep Live Extractor Python script instead.');
      }
    } catch (err) {
      showError('Error: ' + err.message);
      extractBtn.disabled = false;
    }
  }

  async function saveNotes(indices, btn) {
    hideError();
    if (!hasFileSystemAccess) {
      showError('Folder saving is not supported in this browser. Use Keep Live Extractor (Python) instead.');
      return;
    }
    if (indices.length === 0) {
      showError('No notes selected.');
      return;
    }

    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';

    try {
      const dirHandle = await window.showDirectoryPicker();
      const usedNames = new Set();
      let saved = 0;

      for (const idx of indices) {
        const note = currentNotes[idx];
        const md = noteToMarkdown(note);
        let baseName = sanitizeFilename(note.title || 'untitled');
        if (note.source_section && note.source_section !== 'main') {
          baseName = `${note.source_section}_${baseName}`;
        }
        let fileName = `${baseName}.md`;
        let counter = 1;
        while (usedNames.has(fileName.toLowerCase())) {
          fileName = `${baseName}_${counter}.md`;
          counter++;
        }
        usedNames.add(fileName.toLowerCase());

        const fileHandle = await dirHandle.getFileHandle(fileName, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write(md);
        await writable.close();
        saved++;
      }

      btn.textContent = `✅ Saved ${saved}`;
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    } catch (err) {
      if (err.name === 'AbortError') {
        // User cancelled picker
        btn.textContent = originalText;
        btn.disabled = false;
        return;
      }
      showError('Save failed: ' + err.message);
      btn.textContent = originalText;
      btn.disabled = false;
    }
  }

  extractBtn.addEventListener('click', extractNotes);

  saveSelectedBtn.addEventListener('click', () => {
    saveNotes(getSelectedIndices(), saveSelectedBtn);
  });

  saveAllBtn.addEventListener('click', () => {
    const allIndices = currentNotes.map((_, i) => i);
    saveNotes(allIndices, saveAllBtn);
  });
})();
