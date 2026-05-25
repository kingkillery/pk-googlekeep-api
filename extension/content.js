(() => {
  'use strict';

  const COLORS = ['White','Red','Orange','Yellow','Green','Teal','Blue','DarkBlue','Purple','Pink','Brown','Gray'];

  function detectSection() {
    const hash = window.location.hash;
    if (hash.includes('archive')) return 'archive';
    if (hash.includes('trash')) return 'trash';
    return 'main';
  }

  function getColor(card) {
    const cls = card.className || '';
    for (const c of COLORS) {
      if (cls.includes(c)) return c;
    }
    return '';
  }

  function getLabels(card) {
    // Best-effort label extraction from visible chips
    const labels = [];
    // Keep label chips often have specific classes; try a few common patterns
    const chips = card.querySelectorAll('[role="button"], .hPiwDb, .r4nke-YPqjbf');
    chips.forEach(el => {
      const text = el.innerText?.trim();
      if (text && text.length > 0 && text.length < 50 && !el.querySelector('input')) {
        // Heuristic: small text elements that aren't checkboxes or main body
        // Avoid duplicating title/body by excluding elements that match the main text
        labels.push(text);
      }
    });
    // Deduplicate
    return [...new Set(labels)];
  }

  function extractNotes() {
    const section = detectSection();
    const cards = document.querySelectorAll('.IZ65Hb-n0tgWb');
    const notes = [];
    const seenTexts = new Set();

    cards.forEach(card => {
      try {
        const fullText = card.innerText?.trim() || '';
        if (!fullText || fullText.startsWith('Take a note')) return;

        // Deduplicate by first 200 chars of text
        const key = fullText.substring(0, 200);
        if (seenTexts.has(key)) return;
        seenTexts.add(key);

        const lines = fullText.split('\n').map(l => l.trim()).filter(Boolean);
        const title = lines[0]?.substring(0, 200) || '';
        const bodyLines = lines.slice(1);
        let text = bodyLines.join('\n').trim();
        if (!text) text = fullText;

        // Checkboxes / lists
        const checkboxes = card.querySelectorAll('input[type="checkbox"]');
        const isList = checkboxes.length > 0;
        const items = [];
        if (isList) {
          checkboxes.forEach(cb => {
            const checked = cb.checked;
            // Try to find associated text
            let textEl = null;
            let row = cb.closest('div');
            if (row) {
              textEl = row.querySelector('.IZ65Hb-YPqjbf, span, [contenteditable]');
              if (!textEl && row.nextElementSibling) {
                textEl = row.nextElementSibling.querySelector('.IZ65Hb-YPqjbf, span, [contenteditable]');
              }
            }
            const itemText = textEl ? textEl.innerText.trim() : '';
            if (itemText) {
              items.push([itemText, checked]);
            }
          });
        }

        const color = getColor(card);
        const pinned = !!card.querySelector('[data-tooltip-text*="Unpin"], [aria-label*="Unpin"]');
        const archived = !!card.querySelector('[data-tooltip-text*="Unarchive"], [aria-label*="Unarchive"]');
        const labels = getLabels(card);

        notes.push({
          title,
          text,
          is_list: isList,
          items,
          color,
          pinned,
          archived,
          labels,
          source_section: section,
          url: window.location.href
        });
      } catch (e) {
        // Skip problematic cards
      }
    });

    return notes;
  }

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'extractNotes') {
      const notes = extractNotes();
      sendResponse({ notes, section: detectSection() });
    }
    return true; // Keep channel open for async
  });
})();
