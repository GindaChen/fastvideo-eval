/**
 * Markdown Slide Engine
 * 
 * Loads slides.md, splits on <!-- SLIDE --> delimiters,
 * renders each via marked.js, and provides keyboard/touch/click navigation.
 * Supports pluggable CSS themes via <link id="theme-stylesheet">.
 */
(() => {
  /* ──────────────── CONFIG ──────────────── */
  const SLIDE_DELIMITER = /<!-- *SLIDE *-->/i;
  const SECTION_REGEX = /<!-- *SECTION: *(.+?) *-->/i;
  const THEME_STORAGE_KEY = 'slide-theme';
  const FONT_SIZE_KEY = 'slide-font-size';
  const IMG_WIDTH_KEY = 'slide-img-width';
  const MD_FILE = 'slides.md';

  /* ──────────────── THEMES ──────────────── */
  const THEMES = [
    { id: 'midnight', name: 'Midnight', file: 'themes/midnight.css' },
    { id: 'aurora', name: 'Aurora', file: 'themes/aurora.css' },
    { id: 'paper', name: 'Paper', file: 'themes/paper.css' },
    { id: 'sakura', name: 'Sakura', file: 'themes/sakura.css' },
    { id: 'forest', name: 'Forest', file: 'themes/forest.css' },
    { id: 'ocean', name: 'Ocean', file: 'themes/ocean.css' },
    { id: 'sunset', name: 'Sunset', file: 'themes/sunset.css' },
    { id: 'terminal', name: 'Terminal', file: 'themes/terminal.css' },
    { id: 'ivory', name: 'Ivory', file: 'themes/ivory.css' },
    { id: 'neon', name: 'Neon', file: 'themes/neon.css' },
    { id: 'arctic', name: 'Arctic', file: 'themes/arctic.css' },
    { id: 'ember', name: 'Ember', file: 'themes/ember.css' },
    { id: 'lavender', name: 'Lavender', file: 'themes/lavender.css' },
    { id: 'slate', name: 'Slate', file: 'themes/slate.css' },
    { id: 'copper', name: 'Copper', file: 'themes/copper.css' },
    { id: 'mint', name: 'Mint', file: 'themes/mint.css' },
    { id: 'dracula', name: 'Dracula', file: 'themes/dracula.css' },
    { id: 'solarized-dark', name: 'Solarized Dark', file: 'themes/solarized-dark.css' },
    { id: 'solarized-light', name: 'Solarized Light', file: 'themes/solarized-light.css' },
    { id: 'rosepine', name: 'Rosé Pine', file: 'themes/rosepine.css' },
  ];

  /* ──────────────── STATE ──────────────── */
  let current = 0;
  let slides = [];
  let slideEls = [];
  let dotEls = [];
  let slideSections = [];  // section label for each slide index
  let minimapItems = [];   // {el, slideIndex} for each minimap item

  /* ──────────────── DOM REFS ──────────────── */
  const deck = document.getElementById('deck');
  const dotsWrap = document.getElementById('dots');
  const counterEl = document.getElementById('counter');
  const progressEl = document.getElementById('progress');
  const prevBtn = document.getElementById('prev');
  const nextBtn = document.getElementById('next');
  const settingsBtn = document.getElementById('settings-btn');
  const settingsPanel = document.getElementById('settings-panel');
  const themeList = document.getElementById('theme-list');
  const minimapEl = document.getElementById('minimap');
  const minimapTrigger = document.getElementById('minimap-trigger');

  /* ──────────────── THEME ENGINE ──────────────── */
  const themeLink = document.getElementById('theme-stylesheet');

  function setTheme(id) {
    const theme = THEMES.find(t => t.id === id) || THEMES[0];
    themeLink.href = theme.file;
    localStorage.setItem(THEME_STORAGE_KEY, theme.id);
    // Update active state in panel
    themeList.querySelectorAll('.theme-option').forEach(el => {
      el.classList.toggle('active', el.dataset.theme === theme.id);
    });
  }

  function buildThemePanel() {
    THEMES.forEach(theme => {
      const btn = document.createElement('button');
      btn.className = 'theme-option';
      btn.dataset.theme = theme.id;
      btn.textContent = theme.name;
      btn.onclick = (e) => { e.stopPropagation(); setTheme(theme.id); };
      themeList.appendChild(btn);
    });
  }

  /* ──────────────── DISPLAY CONTROLS ──────────────── */
  const fontSlider = document.getElementById('font-size-slider');
  const fontValue = document.getElementById('font-size-value');
  const imgSlider = document.getElementById('img-width-slider');
  const imgValue = document.getElementById('img-width-value');

  function setFontSize(pct) {
    const v = Math.max(60, Math.min(150, Number(pct)));
    document.body.style.setProperty('--slide-font-scale', v / 100);
    fontSlider.value = v;
    fontValue.textContent = v + '%';
    localStorage.setItem(FONT_SIZE_KEY, v);
  }

  function setImgWidth(pct) {
    const v = Math.max(25, Math.min(100, Number(pct)));
    document.body.style.setProperty('--slide-img-width', v);
    imgSlider.value = v;
    imgValue.textContent = v + '%';
    localStorage.setItem(IMG_WIDTH_KEY, v);
  }

  fontSlider.addEventListener('input', () => setFontSize(fontSlider.value));
  imgSlider.addEventListener('input', () => setImgWidth(imgSlider.value));

  /* ──────────────── SETTINGS TOGGLE ──────────────── */
  settingsBtn.onclick = (e) => {
    e.stopPropagation();
    settingsPanel.classList.toggle('open');
  };
  document.addEventListener('click', () => settingsPanel.classList.remove('open'));
  settingsPanel.addEventListener('click', e => e.stopPropagation());

  /* ──────────────── SLIDE RENDERING ──────────────── */
  function renderSlides(md) {
    // Pre-process: extract section markers before splitting
    // We split the raw markdown into chunks, tracking which section each belongs to
    const rawChunks = md.split(SLIDE_DELIMITER);
    let currentSection = '';
    slideSections = [];
    slides = [];

    rawChunks.forEach(chunk => {
      chunk = chunk.trim();
      if (!chunk) return;
      // Check if this chunk starts with a section marker
      const sectionMatch = chunk.match(SECTION_REGEX);
      if (sectionMatch) {
        currentSection = sectionMatch[1];
        chunk = chunk.replace(SECTION_REGEX, '').trim();
      }
      if (!chunk) return;
      slides.push(chunk);
      slideSections.push(currentSection);
    });

    deck.innerHTML = '';
    dotsWrap.innerHTML = '';
    slideEls = [];
    dotEls = [];

    const slideLabels = [];

    slides.forEach((content, i) => {
      const el = document.createElement('div');
      el.className = 'slide' + (i === 0 ? ' active' : '');
      el.innerHTML = marked.parse(content);

      // Convert img tags with video extensions to proper video elements
      el.querySelectorAll('img').forEach(img => {
        const src = img.getAttribute('src') || '';
        if (/\.(mp4|webm|mov)$/i.test(src)) {
          const video = document.createElement('video');
          video.src = src;
          video.autoplay = true;
          video.loop = true;
          video.muted = true;
          video.playsInline = true;
          video.controls = true;
          video.alt = img.alt || '';
          video.style.maxWidth = '100%';
          img.replaceWith(video);
        }
      });

      // Slide number label
      const lbl = document.createElement('div');
      lbl.className = 'slide-label';
      const firstH = el.querySelector('h1, h2');
      const labelText = firstH ? firstH.textContent.substring(0, 30) : `Slide ${i + 1}`;
      lbl.textContent = `${String(i + 1).padStart(2, '0')} · ${labelText}`;
      el.prepend(lbl);
      slideLabels.push(labelText);

      deck.appendChild(el);
      slideEls.push(el);

      const dot = document.createElement('div');
      dot.className = 'dot' + (i === 0 ? ' active' : '');
      dot.onclick = () => goTo(i);
      dot.title = labelText;
      dotsWrap.appendChild(dot);
      dotEls.push(dot);
    });

    // Build minimap
    buildMinimap(slideLabels);

    // ── Sortable tables ──
    // Tables inside <div class="sortable-table"> get clickable column headers
    deck.querySelectorAll('.sortable-table table').forEach(table => {
      const thead = table.querySelector('thead');
      const tbody = table.querySelector('tbody');
      if (!thead || !tbody) return;
      const headers = thead.querySelectorAll('th');
      headers.forEach((th, colIdx) => {
        th.style.cursor = 'pointer';
        th.title = 'Click to sort';
        let asc = true;
        th.addEventListener('click', (e) => {
          e.stopPropagation();
          const rows = Array.from(tbody.querySelectorAll('tr'));
          rows.sort((a, b) => {
            const aText = a.cells[colIdx]?.textContent.trim() || '';
            const bText = b.cells[colIdx]?.textContent.trim() || '';
            const aNum = parseFloat(aText);
            const bNum = parseFloat(bText);
            if (!isNaN(aNum) && !isNaN(bNum)) {
              return asc ? aNum - bNum : bNum - aNum;
            }
            return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
          });
          rows.forEach(r => tbody.appendChild(r));
          headers.forEach(h => h.textContent = h.textContent.replace(/ [▲▼]$/, ''));
          th.textContent += asc ? ' ▲' : ' ▼';
          asc = !asc;
        });
      });
    });

    // ── MathJax re-typeset (if loaded) ──
    if (typeof MathJax !== 'undefined' && MathJax.typeset) {
      try { MathJax.typeset(); } catch (e) { console.warn('MathJax typeset error:', e); }
    }

    current = 0;
    update();
  }

  /* ──────────────── MINIMAP ──────────────── */
  function buildMinimap(labels) {
    minimapEl.innerHTML = '';
    minimapItems = [];
    let lastSection = null;

    labels.forEach((label, i) => {
      const section = slideSections[i];
      if (section && section !== lastSection) {
        const secEl = document.createElement('div');
        secEl.className = 'minimap-section';
        secEl.textContent = section;
        minimapEl.appendChild(secEl);
        lastSection = section;
      }

      const item = document.createElement('div');
      item.className = 'minimap-item' + (i === 0 ? ' active' : '');
      item.textContent = label;
      item.title = label;
      item.onclick = () => goTo(i);
      minimapEl.appendChild(item);
      minimapItems.push({ el: item, slideIndex: i });
    });
  }

  function updateMinimap() {
    minimapItems.forEach(({ el, slideIndex }) => {
      el.classList.toggle('active', slideIndex === current);
    });
    // Scroll active item into view within minimap
    const activeItem = minimapItems.find(m => m.slideIndex === current);
    if (activeItem) {
      activeItem.el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  /* ──────────────── NAVIGATION ──────────────── */
  function update() {
    slideEls.forEach((s, i) => {
      s.classList.remove('active', 'prev');
      if (i === current) s.classList.add('active');
      else if (i < current) s.classList.add('prev');
    });
    dotEls.forEach((d, i) => d.classList.toggle('active', i === current));
    counterEl.textContent = `${current + 1} / ${slideEls.length}`;
    progressEl.style.width = `${((current + 1) / slideEls.length) * 100}%`;
    updateMinimap();
  }

  function goTo(n) {
    current = Math.max(0, Math.min(slideEls.length - 1, n));
    update();
  }

  prevBtn.onclick = () => goTo(current - 1);
  nextBtn.onclick = () => goTo(current + 1);

  document.addEventListener('keydown', e => {
    // Don't hijack if settings panel is open
    if (settingsPanel.classList.contains('open') && e.key === 'Escape') {
      settingsPanel.classList.remove('open');
      return;
    }
    if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); goTo(current + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); goTo(current - 1); }
    if (e.key === 'Home') { e.preventDefault(); goTo(0); }
    if (e.key === 'End') { e.preventDefault(); goTo(slideEls.length - 1); }
  });

  // Touch swipe
  let touchX = 0;
  deck.addEventListener('touchstart', e => touchX = e.touches[0].clientX);
  deck.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) goTo(current + (dx < 0 ? 1 : -1));
  });

  /* ──────────────── NAV BAR AUTO-HIDE ──────────────── */
  const navBar = document.querySelector('.nav-bar');
  let navHideTimer = null;

  function showNav() {
    navBar.classList.add('visible');
    clearTimeout(navHideTimer);
    navHideTimer = setTimeout(() => navBar.classList.remove('visible'), 2000);
  }

  // Show on any mouse movement
  document.addEventListener('mousemove', (e) => {
    // Always show when mouse is in the bottom 120px
    if (e.clientY > window.innerHeight - 120) {
      navBar.classList.add('visible');
      clearTimeout(navHideTimer);
    } else {
      showNav();
    }
  });

  // Hide when mouse leaves bottom zone
  document.addEventListener('mouseleave', () => {
    navHideTimer = setTimeout(() => navBar.classList.remove('visible'), 1000);
  });

  // Show briefly on keyboard navigation
  const origGoTo = goTo;
  goTo = function (n) {
    origGoTo(n);
    showNav();
  };

  // Show initially then auto-hide
  showNav();

  /* ──────────────── MINIMAP SHOW/HIDE ──────────────── */
  let minimapHideTimer = null;

  function showMinimap() {
    minimapEl.classList.add('visible');
    clearTimeout(minimapHideTimer);
  }

  function hideMinimap() {
    minimapHideTimer = setTimeout(() => minimapEl.classList.remove('visible'), 400);
  }

  minimapTrigger.addEventListener('mouseenter', showMinimap);
  minimapEl.addEventListener('mouseenter', () => {
    clearTimeout(minimapHideTimer);
    minimapEl.classList.add('visible');
  });
  minimapTrigger.addEventListener('mouseleave', hideMinimap);
  minimapEl.addEventListener('mouseleave', hideMinimap);

  // Also show minimap on 'm' key toggle
  document.addEventListener('keydown', e => {
    if (e.key === 'm' || e.key === 'M') {
      minimapEl.classList.toggle('visible');
    }
  });

  /* ──────────────── INIT ──────────────── */
  buildThemePanel();

  // Load saved settings
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  setTheme(saved || THEMES[0].id);
  setFontSize(localStorage.getItem(FONT_SIZE_KEY) || 100);
  setImgWidth(localStorage.getItem(IMG_WIDTH_KEY) || 100);

  // ── Multi-file manifest loading ──
  // Try manifest.json first, fall back to slides.md
  async function loadFromManifest(manifest) {
    const parts = [];
    for (const entry of manifest.files) {
      const resp = await fetch(entry.file);
      if (!resp.ok) {
        console.warn(`Failed to load ${entry.file}, skipping`);
        continue;
      }
      let md = await resp.text();
      // Prepend section marker if the manifest entry specifies one
      if (entry.section) {
        md = `<!-- SECTION: ${entry.section} -->\n${md}`;
      }
      parts.push(md);
    }
    if (parts.length === 0) throw new Error('No markdown files loaded from manifest');
    // Update page title if manifest provides one
    if (manifest.title) document.title = manifest.title;
    return parts.join('\n\n');
  }

  async function loadSlides() {
    try {
      const manifestResp = await fetch('manifest.json');
      if (manifestResp.ok) {
        const manifest = await manifestResp.json();
        const md = await loadFromManifest(manifest);
        renderSlides(md);
        return;
      }
    } catch (e) {
      // manifest.json not found or invalid — fall back
    }
    // Fallback: single slides.md
    const resp = await fetch(MD_FILE);
    if (!resp.ok) throw new Error(`Failed to load ${MD_FILE}`);
    const md = await resp.text();
    renderSlides(md);
  }

  loadSlides().catch(err => {
    deck.innerHTML = `<div class="slide active"><h2>Error loading slides</h2><p>${err.message}</p><p>Make sure <code>${MD_FILE}</code> or <code>manifest.json</code> is in the same directory.</p></div>`;
  });
})();
