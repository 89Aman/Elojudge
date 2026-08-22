'use strict';
/* ============================================================
   EloJudge — app.js (v1.0)
   Frontend controller:
   - Live validation + counters
   - CSV / JSON dataset ingestion (header-aware column detection)
   - 6-stage pipeline progress simulation
   - API call with timeout + graceful error recovery
   - Results rendering (tiers, match history, rubric, cleaning)
   - Markdown / CSV export
   ============================================================ */

const API_URL = '/rank';
const API_TIMEOUT_MS = 120000;
const MIN_CONTEXT_CHARS = 20;
const MAX_ITEMS = 20;
const MAX_ITEM_CHARS = 300;
const MAX_CANDIDATES = 8;

/* ---------- DOM references ---------- */
const screens = {
  input: document.getElementById('screen-input'),
  processing: document.getElementById('screen-processing'),
  results: document.getElementById('screen-results'),
};

const formEl = document.getElementById('rank-form');
const contextEl = document.getElementById('product-context');
const feedbackEl = document.getElementById('feedback-items');
const contextCounter = document.getElementById('context-counter');
const itemsCounter = document.getElementById('items-counter');
const contextError = document.getElementById('context-error');
const itemsError = document.getElementById('items-error');
const formError = document.getElementById('form-error');
const submitBtn = document.getElementById('submit-btn');
const uploadCsvBtn = document.getElementById('upload-csv');
const clearBtn = document.getElementById('clear-btn');
const csvInput = document.getElementById('csv-input');
const uploadNote = document.getElementById('upload-note');
const uploadNoteText = document.getElementById('upload-note-text');

// Header Auth & Key Bar
const runsIndicator = document.getElementById('runs-indicator');
const openKeyModalBtn = document.getElementById('open-key-modal-btn');
const keyBtnText = document.getElementById('key-btn-text');
const keyStatusDot = document.getElementById('key-status-dot');
const gSignInBtn = document.getElementById('g-sign-in-btn');
const userProfileChip = document.getElementById('user-profile-chip');
const userAvatar = document.getElementById('user-avatar');
const userName = document.getElementById('user-name');
const signOutBtn = document.getElementById('sign-out-btn');

// Key Dialog
const keyDialog = document.getElementById('api-key-dialog');
const keyDialogClose = document.getElementById('key-dialog-close');
const customGeminiKeyInput = document.getElementById('custom-gemini-key');
const toggleKeyVisibilityBtn = document.getElementById('toggle-key-visibility');
const saveKeyBtn = document.getElementById('save-key-btn');
const clearKeyBtn = document.getElementById('clear-key-btn');
const cancelKeyBtn = document.getElementById('cancel-key-btn');

// Upload dialog
const uploadDialog = document.getElementById('upload-dialog');
const dialogCloseBtn = document.getElementById('dialog-close');
const dropZone = document.getElementById('drop-zone');
const browseBtn = document.getElementById('browse-btn');
const uploadProgressWrap = document.getElementById('upload-progress-wrap');
const uploadProgressFill = document.getElementById('upload-progress-fill');
const uploadProgressText = document.getElementById('upload-progress-text');

// Warning banner
const apiWarning = document.getElementById('api-warning');
const warningTitle = document.getElementById('warning-title');
const warningMessage = document.getElementById('warning-message');
const warningDismiss = document.getElementById('warning-dismiss');

// Processing screen
const stepListEl = document.getElementById('step-list');
const progressBarFill = document.getElementById('progress-bar-fill');
const processingLiveStatus = document.getElementById('processing-live-status');

// Results screen
const bannerEl = document.getElementById('result-banner');
const metricsEl = document.getElementById('metrics-bar');
const tierNavEl = document.getElementById('tier-nav');
const tiersEl = document.getElementById('tiers');
const cleaningBody = document.getElementById('cleaning-body');
const rubricBody = document.getElementById('rubric-body');
const lowerSection = document.getElementById('lower-priority');
const lowerList = document.getElementById('lower-list');
const countAllEl = document.getElementById('count-all');
const countNowEl = document.getElementById('count-now');
const countNextEl = document.getElementById('count-next');
const countLaterEl = document.getElementById('count-later');
const runAgainBtn = document.getElementById('run-again');
const topRunAgainBtn = document.getElementById('top-run-again-btn');
const returnHomeBtn = document.getElementById('return-home');
const copyBacklogBtn = document.getElementById('copy-backlog-btn');
const exportCsvBtn = document.getElementById('export-csv-btn');
const toastEl = document.getElementById('toast');

let activeResultsData = null;
let toastTimeout = null;

/* ---------- Utilities ---------- */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function showScreen(name) {
  Object.entries(screens).forEach(([key, section]) => {
    if (section) section.hidden = key !== name;
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showError(node, message) {
  node.textContent = message;
  node.hidden = false;
}

function hideError(node) {
  node.hidden = true;
  node.textContent = '';
}

function parseItems() {
  return feedbackEl.value
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
}

function showToast(message, variant = '') {
  if (toastTimeout) clearTimeout(toastTimeout);
  toastEl.className = `toast${variant ? ' toast-' + variant : ''}`;
  toastEl.textContent = message;
  toastEl.hidden = false;
  toastTimeout = setTimeout(() => { toastEl.hidden = true; }, 4000);
}

function showWarning(title, message) {
  warningTitle.textContent = title;
  warningMessage.textContent = message;
  apiWarning.hidden = false;
  apiWarning.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideWarning() {
  apiWarning.hidden = true;
}

function showUploadProgress(text, percent) {
  uploadProgressWrap.hidden = false;
  uploadProgressText.textContent = text;
  if (percent === null) {
    uploadProgressFill.className = 'upload-progress-fill indeterminate';
    uploadProgressFill.style.width = '';
  } else {
    uploadProgressFill.className = 'upload-progress-fill';
    uploadProgressFill.style.width = `${percent}%`;
  }
}

function hideUploadProgress() {
  uploadProgressWrap.hidden = true;
  uploadProgressFill.style.width = '0%';
  uploadProgressFill.className = 'upload-progress-fill';
}

function fmtElo(value) {
  return Math.round(Number(value) || 0).toLocaleString('en-US');
}

function normalizeSource(source) {
  const v = String(source || '').toLowerCase();
  if (v.includes('cached')) return 'cached';
  if (v.includes('obvious') || v.includes('rule') || v.includes('local rule')) return 'local';
  if (v.includes('fallback') || v.includes('local fallback')) return 'fallback';
  return 'ai';
}

const SOURCE_LABEL_MAP = {
  ai: 'AI judgment',
  cached: 'Cached AI',
  local: 'Local rule · obvious pair',
  fallback: 'Local fallback',
};

function makeBadge(source, small = false) {
  const key = normalizeSource(source);
  const label = SOURCE_LABEL_MAP[key] || source || 'AI judgment';
  return el('span', `badge badge-${key}${small ? ' badge-sm' : ''}`, label);
}

/* ---------- CSV / JSON ingestion ---------- */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      if (row.some(v => v.trim() !== '')) rows.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  row.push(field);
  if (row.some(v => v.trim() !== '')) rows.push(row);
  return rows;
}

const FEEDBACK_HEADERS = [
  'feedback', 'feedback_item', 'feature_request', 'request', 'suggestion', 'idea',
  'content', 'title', 'note', 'notes', 'text', 'summary', 'comment', 'message',
  'item', 'feature', 'description', 'task', 'issue', 'query', 'body', 'input', 'prompt',
];
const CONTEXT_HEADERS = [
  'context', 'product_context', 'product', 'product_name', 'app',
  'product context', 'goal', 'goals', 'overview',
];

function handleDatasetFile(file) {
  hideError(itemsError);
  uploadNote.hidden = true;
  hideWarning();
  showUploadProgress('Reading file…', null);

  file.text().then(raw => {
    showUploadProgress('Parsing content…', 30);
    const text = raw.replace(/^\ufeff/, '').trim();
    if (!text) {
      hideUploadProgress();
      showWarning('Empty File', `"${file.name}" contains no data. Please select a file with feedback items.`);
      return;
    }

    let items = [];
    let context = '';
    const isJson = file.name.toLowerCase().endsWith('.json') || text.startsWith('{') || text.startsWith('[');

    showUploadProgress('Extracting feedback…', 55);

    if (isJson) {
      try {
        const data = JSON.parse(text);
        if (data && !Array.isArray(data)) {
          if (data.app && data.description) context = `${data.app} — ${data.description}`;
          else if (data.description || data.context || data.product_context) {
            context = data.description || data.context || data.product_context;
          }
          if (Array.isArray(data.notes)) {
            items = data.notes.map(n => (n.content || n.title || n.text || '').trim()).filter(Boolean);
          } else if (Array.isArray(data.feedback)) {
            items = data.feedback.map(f => (typeof f === 'string' ? f : f.text || f.content || f.item || '')).filter(Boolean);
          } else if (Array.isArray(data.items)) {
            items = data.items.map(it => (typeof it === 'string' ? it : it.text || it.content || it.title || '')).filter(Boolean);
          }
        } else if (Array.isArray(data)) {
          items = data
            .map(it => (typeof it === 'string' ? it : it.content || it.text || it.title || it.feedback || ''))
            .filter(Boolean);
        }
      } catch (err) {
        hideUploadProgress();
        showWarning('Invalid JSON', `Failed to parse "${file.name}" — check the file format and try again.`);
        return;
      }
    } else {
      const rows = parseCsv(text);
      if (rows.length === 0) {
        hideUploadProgress();
        showWarning('No Data Found', `Could not extract any rows from "${file.name}".`);
        return;
      }

      const headerCells = rows[0].map(c => c.trim().toLowerCase());

      // Find best feedback column index based on header priority
      let feedbackCol = -1;
      for (const h of FEEDBACK_HEADERS) {
        const idx = headerCells.indexOf(h);
        if (idx >= 0) { feedbackCol = idx; break; }
      }
      const contextCol = headerCells.findIndex(h => CONTEXT_HEADERS.includes(h));
      const hasHeader = feedbackCol >= 0 || contextCol >= 0;
      const dataRows = hasHeader ? rows.slice(1) : rows;

      // No explicit header match → pick the column with the most descriptive text
      let itemCol = feedbackCol;
      if (itemCol < 0) {
        const colScores = (dataRows[0] || []).map((_, cIdx) => {
          let totalLen = 0;
          let spaceCount = 0;
          let count = 0;
          for (let r = 0; r < Math.min(dataRows.length, 10); r++) {
            const cell = (dataRows[r][cIdx] || '').trim();
            if (cell) {
              totalLen += cell.length;
              if (cell.includes(' ')) spaceCount++;
              count++;
            }
          }
          const avgLen = count ? totalLen / count : 0;
          // Heavily penalize short ID-like columns (e.g. note0001, usr001)
          const isIdLike = avgLen < 15 && spaceCount === 0;
          return isIdLike ? -100 : avgLen + spaceCount * 5;
        });
        let bestCol = 0;
        let maxScore = -999;
        colScores.forEach((score, idx) => {
          if (score > maxScore) { maxScore = score; bestCol = idx; }
        });
        itemCol = bestCol;
      }

      items = dataRows.map(r => (r[itemCol] || '').trim()).filter(Boolean);
      if (contextCol >= 0 && dataRows.length > 0) {
        context = (dataRows[0][contextCol] || '').trim();
      }
    }

    showUploadProgress('Validating items…', 80);

    if (context) {
      contextEl.value = context;
      hideError(contextError);
    }

    if (items.length < 2) {
      hideUploadProgress();
      showWarning('Not Enough Items', `Found ${items.length} feedback item(s) in "${file.name}" — need at least 2.`);
      return;
    }

    let note = `Loaded ${items.length} items from "${file.name}".`;
    if (items.length > MAX_ITEMS) {
      items = items.slice(0, MAX_ITEMS);
      note = `"${file.name}" had more than ${MAX_ITEMS} items — kept first ${MAX_ITEMS}.`;
    }

    showUploadProgress('Done!', 100);

    feedbackEl.value = items.join('\n');
    updateCounters();

    // Close dialog after short delay to show 100% completion
    setTimeout(() => {
      hideUploadProgress();
      uploadDialog.close();
      // Show success notification
      uploadNoteText.textContent = `${note} Edit freely, then click Prioritize feedback.`;
      uploadNote.hidden = false;
      showToast(`✅ ${items.length} feedback items imported successfully!`);
    }, 500);
  }).catch(err => {
    hideUploadProgress();
    showWarning('File Read Error', `Failed to read "${file.name}": ${err.message || 'invalid file format'}.`);
  });
}

/* ---------- Counters & validation ---------- */
function updateCounters() {
  const contextLen = contextEl.value.trim().length;
  contextCounter.textContent = `${contextLen} / ${MIN_CONTEXT_CHARS} min`;
  contextCounter.classList.toggle('ok', contextLen >= MIN_CONTEXT_CHARS);

  const count = parseItems().length;
  itemsCounter.textContent = `${count} / ${MAX_ITEMS} items`;
  itemsCounter.classList.toggle('over', count > MAX_ITEMS);
  itemsCounter.classList.toggle('ok', count >= 2 && count <= MAX_ITEMS);
}

function validate(context, items) {
  let ok = true;

  if (context.length < MIN_CONTEXT_CHARS) {
    showError(
      contextError,
      `Product context is too short (${context.length}/${MIN_CONTEXT_CHARS} chars). Please describe product goals and target audience.`
    );
    ok = false;
  }

  if (items.length < 2) {
    showError(itemsError, 'Please enter at least 2 feedback items (one per line).');
    ok = false;
  } else if (items.length > MAX_ITEMS) {
    showError(itemsError, `Too many feedback items (${items.length}). Please limit to ${MAX_ITEMS} items.`);
    ok = false;
  } else {
    const rawLines = feedbackEl.value.split('\n');
    const longIdx = rawLines.findIndex(line => line.trim().length > MAX_ITEM_CHARS);
    if (longIdx >= 0) {
      showError(itemsError, `Line ${longIdx + 1} exceeds ${MAX_ITEM_CHARS} characters — please shorten it.`);
      ok = false;
    }
  }

  return ok;
}

/* ---------- Processing screen: 6-stage simulation ---------- */
const STEP_DEFS = [
  { label: 'Filtering and cleaning feedback locally', ms: 700, progress: 20 },
  { label: 'Building your product rubric', ms: 1400, progress: 40 },
  { label: 'Selecting top candidates', ms: 600, progress: 55 },
  { label: 'Running Swiss comparison', ms: 3800, progress: 80, rounds: true },
  { label: 'Updating Elo ratings', ms: 700, progress: 92 },
  { label: 'Building explainable roadmap', ms: 800, progress: 100 },
];

function estimatedRounds(itemCount) {
  const candidates = Math.max(2, Math.min(itemCount, MAX_CANDIDATES));
  return Math.ceil(Math.log2(candidates)) + 1;
}

const progressController = {
  timers: [],

  start(rounds) {
    this.clear();
    stepListEl.innerHTML = '';
    progressBarFill.style.width = '10%';
    processingLiveStatus.textContent = 'Initializing local cleaning and TF-IDF clustering…';

    const nodes = STEP_DEFS.map((def, i) => {
      const li = el('li', 'step pending');
      const icon = el('span', 'step-icon');
      const textWrap = el('span');
      const count = el('span', 'step-count', `${i + 1}/6`);
      const label = el('span', 'step-label', def.label);
      const sub = el('span', 'step-sub');
      sub.hidden = true;
      textWrap.append(count, label, sub);
      li.append(icon, textWrap);
      stepListEl.appendChild(li);
      return { li, sub, def };
    });

    let cumulativeTime = 0;
    STEP_DEFS.forEach((def, i) => {
      this.timers.push(setTimeout(() => {
        progressBarFill.style.width = `${def.progress}%`;
        processingLiveStatus.textContent = `Stage ${i + 1} of 6 — ${def.label}…`;
        nodes.forEach((node, j) => {
          node.li.classList.toggle('done', j < i);
          node.li.classList.toggle('active', j === i);
          node.li.classList.toggle('pending', j > i);
        });

        if (def.rounds) {
          const perRoundTime = def.ms / rounds;
          for (let r = 1; r <= rounds; r++) {
            this.timers.push(setTimeout(() => {
              nodes[i].sub.hidden = false;
              nodes[i].sub.textContent = `· round ${r} of ${rounds}`;
              processingLiveStatus.textContent = `Running Swiss head-to-head tournament — Round ${r} of ${rounds}`;
            }, perRoundTime * (r - 1)));
          }
        }
      }, cumulativeTime));
      cumulativeTime += def.ms;
    });
  },

  finish() {
    this.clear();
    progressBarFill.style.width = '100%';
    processingLiveStatus.textContent = 'All 6 pipeline stages complete!';
    Array.from(stepListEl.children).forEach(li => {
      li.className = 'step done';
      const sub = li.querySelector('.step-sub');
      if (sub) sub.hidden = true;
    });
    return new Promise(resolve => setTimeout(resolve, 400));
  },

  clear() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  },
};

/* ---------- Submit flow ---------- */
async function handleSubmit(event) {
  event.preventDefault();

  const context = contextEl.value.trim();
  const items = parseItems();
  if (!validate(context, items)) return;

  // Check login / BYOK requirement
  const hasKey = Boolean(getUserApiKey());
  const hasGoogle = Boolean(getGoogleIdToken());
  if (!hasKey && !hasGoogle) {
    showWarning(
      'Sign-in Required',
      'Please sign in with your Google account (top right) to get 5 free daily runs, or add your Gemini API Key in Settings (🔑) to run EloJudge.'
    );
    return;
  }

  submitBtn.disabled = true;
  hideError(formError);
  hideWarning();
  uploadNote.hidden = true;
  showScreen('processing');
  progressController.start(estimatedRounds(items.length));

  let data = null;
  let fetchError = null;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const payload = {
      product_context: context,
      feedback_items: items,
      max_candidates: MAX_CANDIDATES,
    };
    const customKey = getUserApiKey();
    if (customKey) payload.user_api_key = customKey;
    const googleToken = getGoogleIdToken();
    if (googleToken) payload.google_id_token = googleToken;

    const res = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => null);
      const msg = (errJson && (errJson.error || errJson.detail)) || `Server responded with status ${res.status}`;
      throw new Error(msg);
    }

    data = await res.json();
  } catch (err) {
    fetchError = err && err.name === 'AbortError'
      ? new Error('The ranking request timed out — the server may be busy, please try again')
      : err;
  } finally {
    clearTimeout(timeoutId);
  }

  await progressController.finish();
  submitBtn.disabled = false;

  if (data) {
    hideWarning();
    renderResults(data);
  } else {
    showScreen('input');
    const isNetworkError = fetchError && (fetchError.message.includes('Failed to fetch') || fetchError.message.includes('NetworkError'));
    if (isNetworkError) {
      showWarning(
        'Server Unreachable',
        'Cannot connect to the backend. Make sure the server is running on the correct port, then try again.'
      );
    } else {
      showWarning(
        'Ranking Failed',
        fetchError ? fetchError.message : 'An unknown error occurred. Check the server logs for details.'
      );
    }
  }
}

/* ---------- Results rendering ---------- */
function renderResults(data) {
  activeResultsData = data;

  const summary = data.summary || {};
  const cleaning = data.cleaning_summary || {};
  const matches = Array.isArray(data.matches) ? data.matches : [];
  const ranked = Array.isArray(data.ranked_items) ? [...data.ranked_items] : [];

  // Sort descending by Elo rating, then wins
  ranked.sort((a, b) => (b.elo - a.elo) || ((b.wins || 0) - (a.wins || 0)));

  // Map item ID → representative text for match lookups
  const textById = {};
  (cleaning.items || []).forEach(it => { textById[it.id] = it.text; });
  (cleaning.clusters || []).forEach(cl => { textById[cl.id] = cl.representative_text || cl.text; });
  ranked.forEach(it => { textById[it.id] = it.text; });
  (data.lower_priority_candidates || []).forEach(it => { textById[it.id] = it.text; });

  renderBanner(summary);
  renderMetrics(summary, cleaning);
  renderTiers(ranked, matches, textById);
  renderCleaning(cleaning);
  renderRubric(data.rubric);
  renderLowerPriority(data.lower_priority_candidates);

  showScreen('results');
}

/* 1. Banner — fallback / early-stop notices */
function renderBanner(summary) {
  bannerEl.innerHTML = '';

  if ((summary.fallback_decisions || 0) > 0) {
    bannerEl.className = 'banner banner-info';
    bannerEl.appendChild(el('strong', null,
      `${summary.fallback_decisions} of ${summary.pairwise_comparisons || 0} comparisons used local rule fallback`));
    bannerEl.appendChild(el('span', 'banner-detail',
      'Model timeout or budget limits triggered local fallback logic for those pairs. Affected items are clearly labeled Local fallback.'));
    bannerEl.hidden = false;
  } else if (summary.early_stopped) {
    bannerEl.className = 'banner banner-info';
    bannerEl.appendChild(el('strong', null, 'Swiss tournament early stopping triggered'));
    bannerEl.appendChild(el('span', 'banner-detail',
      `${summary.early_stop_reason || ''} Rankings stabilized early — saved unnecessary pairwise comparisons.`));
    bannerEl.hidden = false;
  } else {
    bannerEl.hidden = true;
  }
}

/* 2. Metrics bar */
function renderMetrics(summary, cleaning) {
  const removed =
    (cleaning.removed_empty_or_short || 0) +
    (cleaning.removed_spam || 0) +
    (cleaning.removed_exact_duplicates || 0);

  const chips = [
    { label: 'Submitted', value: summary.raw_items ?? cleaning.raw_items ?? '—' },
    { label: 'Removed', value: removed },
    { label: 'Merged', value: cleaning.merged_near_duplicates ?? 0 },
    { label: 'Clean Items', value: summary.clean_items ?? cleaning.clean_items ?? '—' },
    { label: 'Candidates', value: summary.tournament_candidates ?? '—' },
    { label: 'Comparisons', value: summary.pairwise_comparisons ?? '—' },
    { label: 'API Requests', value: summary.llm_requests ?? 0, highlight: true },
    { label: 'Est. Cost', value: summary.estimated_cost ? `$${summary.estimated_cost.toFixed(5)}` : '$0.001' },
  ];

  metricsEl.innerHTML = '';
  const frag = document.createDocumentFragment();
  chips.forEach(chip => {
    const box = el('div', 'metric-chip');
    box.setAttribute('role', 'listitem');
    box.appendChild(el('span', 'metric-label', chip.label));
    box.appendChild(el('span', `metric-value${chip.highlight ? ' metric-highlight' : ''}`, String(chip.value)));
    frag.appendChild(box);
  });
  metricsEl.appendChild(frag);
}

/* 3. Tiers + ranked cards */
const TIER_CONFIG = [
  { key: 'now', name: 'Now', blurb: 'Top priority — execute in immediate sprint' },
  { key: 'next', name: 'Next', blurb: 'Strong candidates queued for upcoming roadmap' },
  { key: 'later', name: 'Later', blurb: 'Compared, but outranked by higher-impact items' },
];

function assignItemTier(item, idx, total) {
  if (item.tier) {
    const t = String(item.tier).toLowerCase();
    if (t === 'now') return 'now';
    if (t === 'next') return 'next';
    return 'later';
  }
  const nowEnd = Math.ceil(total / 3);
  const nextEnd = Math.ceil((2 * total) / 3);
  if (idx + 1 <= nowEnd) return 'now';
  if (idx + 1 <= nextEnd) return 'next';
  return 'later';
}

function getItemSource(item, matches) {
  if (Array.isArray(item.source_labels) && item.source_labels.length > 0) return item.source_labels[0];
  if (item.source) return item.source;
  const related = matches.filter(m => {
    const a = m.item_a_id ?? m.item_a;
    const b = m.item_b_id ?? m.item_b;
    return a === item.id || b === item.id;
  });
  return related.some(m => normalizeSource(m.source) === 'fallback') ? 'fallback' : 'ai';
}

function renderTiers(ranked, matches, textById) {
  tiersEl.innerHTML = '';
  const total = ranked.length;
  const groups = { now: [], next: [], later: [] };

  ranked.forEach((item, idx) => {
    const tierKey = assignItemTier(item, idx, total);
    groups[tierKey].push({ item, rank: idx + 1 });
  });

  // Update tab counts + reset filter to "all"
  countAllEl.textContent = total;
  countNowEl.textContent = groups.now.length;
  countNextEl.textContent = groups.next.length;
  countLaterEl.textContent = groups.later.length;
  tierNavEl.querySelectorAll('.tier-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.filter === 'all'));

  const frag = document.createDocumentFragment();
  TIER_CONFIG.forEach(tier => {
    const itemsInTier = groups[tier.key];
    if (itemsInTier.length === 0) return;

    const section = el('section', `tier-section tier-${tier.key}`);
    section.dataset.tier = tier.key;

    const header = el('div', 'tier-header');
    header.appendChild(el('span', 'tier-dot'));
    header.appendChild(el('span', 'tier-name', tier.name));
    header.appendChild(el('span', 'tier-count', `${itemsInTier.length} item${itemsInTier.length > 1 ? 's' : ''}`));
    header.appendChild(el('span', 'tier-blurb', tier.blurb));
    section.appendChild(header);

    itemsInTier.forEach(({ item, rank }) =>
      section.appendChild(buildRankedCard(item, rank, matches, textById)));

    frag.appendChild(section);
  });
  tiersEl.appendChild(frag);
}

function buildRankedCard(item, rank, matches, textById) {
  const card = el('article', 'card');
  card.appendChild(el('div', 'card-rank', rank));

  const body = el('div', 'card-body');

  // Title + badges
  const top = el('div', 'card-top');
  top.appendChild(el('h3', 'card-title', item.text));
  const badgesWrap = el('div', 'card-badges-row');
  if (item.severity && item.severity !== 'medium') {
    badgesWrap.appendChild(el('span', `severity-pill severity-${item.severity}`, item.severity));
  }
  badgesWrap.appendChild(makeBadge(getItemSource(item, matches)));
  top.appendChild(badgesWrap);
  body.appendChild(top);

  // Stats row — Elo, W/L, mentions
  const stats = el('div', 'card-stats');
  stats.appendChild(el('span', 'elo-pill', `Elo ${fmtElo(item.elo)}`));
  stats.appendChild(el('span', 'record-pill', `${item.wins ?? 0}W · ${item.losses ?? 0}L`));
  if (item.report_count && item.report_count > 1) {
    stats.appendChild(el('span', 'record-pill', `${item.report_count} mentions`));
  }
  body.appendChild(stats);

  // One-line reason
  const reasonText = Array.isArray(item.reasons) && item.reasons.length > 0 ? item.reasons[0] : item.reason;
  if (reasonText) body.appendChild(el('p', 'card-reason', reasonText));

  // Expandable match history (proof-of-computation)
  const relatedMatches = matches
    .filter(m => {
      const a = m.item_a_id ?? m.item_a;
      const b = m.item_b_id ?? m.item_b;
      return a === item.id || b === item.id;
    })
    .map(m => {
      const a = m.item_a_id ?? m.item_a;
      const isA = a === item.id;
      const oppId = isA ? (m.item_b_id ?? m.item_b) : a;
      const winnerId = m.winner_id ?? m.winner;
      const won = winnerId === item.id;
      const before = isA ? (m.elo_before_a ?? m.rating_a_before ?? 1200) : (m.elo_before_b ?? m.rating_b_before ?? 1200);
      const after = isA ? (m.elo_after_a ?? m.rating_a_after ?? 1200) : (m.elo_after_b ?? m.rating_b_after ?? 1200);
      return { round: m.round, opponent: textById[oppId] || oppId, won, before, after, reason: m.reason, source: m.source };
    });

  const merged = Array.isArray(item.merged_feedback) ? item.merged_feedback : [];

  if (relatedMatches.length > 0 || merged.length > 0) {
    const details = el('details', 'card-why');
    details.appendChild(el('summary', null, 'Why this rank? — match history & proof-of-computation'));

    if (relatedMatches.length > 0) {
      const list = el('ul', 'match-list');
      relatedMatches.forEach(match => {
        const row = el('li', 'match-row');
        const main = el('div', 'match-main');
        main.appendChild(el('span', 'match-round', `Round ${match.round}`));
        main.appendChild(el('span', `match-outcome ${match.won ? 'won' : 'lost'}`, match.won ? 'Beat' : 'Lost to'));
        main.appendChild(el('span', 'match-opponent', match.opponent));

        const delta = Math.round((match.after - match.before) * 10) / 10;
        const deltaFormatted = delta > 0 ? `+${delta}` : `${delta}`;
        const eloSpan = el('span', 'match-elo');
        eloSpan.appendChild(document.createTextNode(`Elo ${fmtElo(match.before)} → ${fmtElo(match.after)} `));
        eloSpan.appendChild(el('span', delta >= 0 ? 'delta-pos' : 'delta-neg', deltaFormatted));
        main.appendChild(eloSpan);
        main.appendChild(makeBadge(match.source, true));
        row.appendChild(main);

        if (match.reason) row.appendChild(el('span', 'match-reason', match.reason));
        list.appendChild(row);
      });
      details.appendChild(list);
    }

    if (merged.length > 0) {
      const mergedBox = el('div', 'merged-feedback-box');
      mergedBox.appendChild(el('strong', null, 'Merged near-duplicates: '));
      mergedBox.appendChild(document.createTextNode(merged.map(m => `“${m}”`).join(', ')));
      details.appendChild(mergedBox);
    }

    body.appendChild(details);
  }

  card.appendChild(body);
  return card;
}

/* 4. Cleaning summary panel */
function renderCleaning(cleaning) {
  cleaningBody.innerHTML = '';

  const stats = [
    ['Too Short / Empty', cleaning.removed_empty_or_short || 0],
    ['Spam Filtered', cleaning.removed_spam || 0],
    ['Exact Duplicates', cleaning.removed_exact_duplicates || 0],
    ['Near-Duplicates Merged', cleaning.merged_near_duplicates || 0],
    ['Clean Candidates', cleaning.clean_items ?? '—'],
  ];

  const grid = el('div', 'clean-grid');
  stats.forEach(([label, val]) => {
    const box = el('div', 'clean-stat');
    box.appendChild(el('span', 'clean-num', String(val)));
    box.appendChild(el('span', 'clean-label', label));
    grid.appendChild(box);
  });
  cleaningBody.appendChild(grid);

  const pairs = [];
  (cleaning.items || []).forEach(it =>
    (it.merged_feedback || []).forEach(m => pairs.push([it.text, m])));
  (cleaning.clusters || []).forEach(cl =>
    (cl.merged_feedback || []).forEach(m => pairs.push([cl.representative_text || cl.text, m])));
  (cleaning.merged_examples || []).forEach(ex => pairs.push([ex.kept, ex.merged]));

  if (pairs.length > 0) {
    cleaningBody.appendChild(el('p', 'helper', 'Resolved near-duplicate feedback clusters:'));
    const frag = document.createDocumentFragment();
    pairs.forEach(([kept, merged]) => {
      const row = el('div', 'merged-pair');
      row.appendChild(el('strong', null, kept));
      row.appendChild(el('span', 'arrow', '← merged with'));
      row.appendChild(document.createTextNode(merged));
      frag.appendChild(row);
    });
    cleaningBody.appendChild(frag);
  } else if (stats.slice(0, 4).every(([, v]) => v === 0)) {
    cleaningBody.appendChild(el('p', 'empty-note',
      'Every submitted feedback item passed all local filtering and deduplication rules cleanly.'));
  }
}

/* 5. Rubric panel */
function renderRubric(rubric) {
  rubricBody.innerHTML = '';
  const dimensions = rubric && rubric.dimensions ? rubric.dimensions : [];

  if (dimensions.length === 0) {
    rubricBody.appendChild(el('p', 'empty-note', 'Default standard product rubric was applied.'));
    return;
  }

  const frag = document.createDocumentFragment();
  dimensions.forEach(dim => {
    const row = el('div', 'rubric-row');

    const head = el('div', 'rubric-head');
    head.appendChild(el('span', 'rubric-name', dim.name));
    head.appendChild(el('span', 'rubric-weight', `${Math.round((dim.weight || 0) * 100)}%`));
    row.appendChild(head);

    const bar = el('div', 'weight-bar');
    const fill = el('div', 'weight-fill');
    fill.style.width = `${Math.round((dim.weight || 0) * 100)}%`;
    bar.appendChild(fill);
    row.appendChild(bar);

    if (dim.description) row.appendChild(el('p', 'rubric-desc', dim.description));
    frag.appendChild(row);
  });
  rubricBody.appendChild(frag);

  const source = normalizeSource(rubric && rubric.source);
  const note = source === 'fallback'
    ? 'Default rubric synthesized from general product principles.'
    : 'Generated dynamically from your product context, then cached.';
  rubricBody.appendChild(el('p', 'rubric-source', note));
}

/* 6. Lower-priority candidates */
function renderLowerPriority(candidates) {
  lowerList.innerHTML = '';

  if (!Array.isArray(candidates) || candidates.length === 0) {
    lowerSection.hidden = true;
    return;
  }
  lowerSection.hidden = false;

  const frag = document.createDocumentFragment();
  candidates.forEach(cand => {
    const li = el('li');
    li.appendChild(el('span', null, cand.text));
    const scoreVal = cand.local_pre_rank_score ?? cand.local_prerank_score ?? cand.local_score;
    if (scoreVal !== undefined && scoreVal !== null) {
      li.appendChild(el('span', 'lower-score', `pre-rank score ${Number(scoreVal).toFixed(2)}`));
    }
    frag.appendChild(li);
  });
  lowerList.appendChild(frag);
}

/* ---------- Export helpers ---------- */
function exportMarkdownBacklog(data) {
  if (!data) return;
  const ranked = data.ranked_items || [];

  let md = '# Prioritized Product Backlog — by EloJudge\n\n';
  ranked.forEach(it => {
    md += `## ${it.rank || ''} [${it.tier || 'Later'}] ${it.text}\n`;
    md += `- Elo Rating: ${fmtElo(it.elo)} (${it.wins || 0}W - ${it.losses || 0}L)\n`;
    if (it.reasons && it.reasons.length > 0) md += `- Reason: ${it.reasons[0]}\n`;
    if (it.merged_feedback && it.merged_feedback.length > 0) {
      md += `- Merged Items: ${it.merged_feedback.join(', ')}\n`;
    }
    md += '\n';
  });

  navigator.clipboard.writeText(md)
    .then(() => showToast('Markdown backlog copied to clipboard!'))
    .catch(() => showToast('Failed to copy to clipboard.'));
}

function exportCsvBacklog(data) {
  if (!data) return;
  const ranked = data.ranked_items || [];

  let csv = 'Rank,Tier,Feedback,Elo,Wins,Losses,PrimaryReason\n';
  ranked.forEach(it => {
    const reason = (it.reasons && it.reasons[0]) || it.reason || '';
    csv += `${it.rank || ''},${it.tier || 'Later'},"${it.text.replace(/"/g, '""')}",${fmtElo(it.elo)},${it.wins || 0},${it.losses || 0},"${reason.replace(/"/g, '""')}"\n`;
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', 'elojudge_backlog.csv');
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  showToast('CSV backlog exported!');
}

/* ---------- Event wiring ---------- */
formEl.addEventListener('submit', handleSubmit);

// Ctrl/Cmd + Enter submits from anywhere in the form
formEl.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

uploadCsvBtn.addEventListener('click', () => uploadDialog.showModal());

// Dialog close
dialogCloseBtn.addEventListener('click', () => { hideUploadProgress(); uploadDialog.close(); });
uploadDialog.addEventListener('click', (e) => {
  if (e.target === uploadDialog) { hideUploadProgress(); uploadDialog.close(); }
});

// Browse button inside dialog
browseBtn.addEventListener('click', () => csvInput.click());
csvInput.addEventListener('change', () => {
  const file = csvInput.files && csvInput.files[0];
  if (file) handleDatasetFile(file);
  csvInput.value = '';
});

// Drag-and-drop on drop zone
dropZone.addEventListener('dragenter', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) handleDatasetFile(file);
});

// Click anywhere on drop zone opens file picker
dropZone.addEventListener('click', (e) => {
  if (e.target !== browseBtn && !browseBtn.contains(e.target)) csvInput.click();
});

// Warning dismiss
warningDismiss.addEventListener('click', hideWarning);

clearBtn.addEventListener('click', () => {
  contextEl.value = '';
  feedbackEl.value = '';
  hideError(contextError);
  hideError(itemsError);
  hideError(formError);
  hideWarning();
  uploadNote.hidden = true;
  updateCounters();
  contextEl.focus();
});

// Navigation actions
runAgainBtn.addEventListener('click', () => { showScreen('input'); contextEl.focus(); });
topRunAgainBtn.addEventListener('click', () => { showScreen('input'); contextEl.focus(); });
returnHomeBtn.addEventListener('click', () => showScreen('input'));
copyBacklogBtn.addEventListener('click', () => exportMarkdownBacklog(activeResultsData));
exportCsvBtn.addEventListener('click', () => exportCsvBacklog(activeResultsData));


// Tier filter tabs (event delegation)
tierNavEl.addEventListener('click', e => {
  const tab = e.target.closest('.tier-tab');
  if (!tab) return;

  tierNavEl.querySelectorAll('.tier-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');

  const filter = tab.dataset.filter;
  tiersEl.querySelectorAll('.tier-section').forEach(sec => {
    sec.hidden = !(filter === 'all' || sec.dataset.tier === filter);
  });
});

// Realtime validation
contextEl.addEventListener('input', () => {
  updateCounters();
  if (contextEl.value.trim().length >= MIN_CONTEXT_CHARS) hideError(contextError);
});

feedbackEl.addEventListener('input', () => {
  updateCounters();
  const n = parseItems().length;
  if (n >= 2 && n <= MAX_ITEMS) hideError(itemsError);
});

/* ---------- Auth & BYOK Key Management ---------- */
const STORAGE_KEY_API_KEY = 'elojudge_gemini_key';
const STORAGE_KEY_GOOGLE_TOKEN = 'elojudge_google_token';
const STORAGE_KEY_GOOGLE_USER = 'elojudge_google_user';

function getUserApiKey() {
  return (localStorage.getItem(STORAGE_KEY_API_KEY) || '').trim();
}

function setUserApiKey(key) {
  const clean = (key || '').trim();
  if (clean) {
    localStorage.setItem(STORAGE_KEY_API_KEY, clean);
  } else {
    localStorage.removeItem(STORAGE_KEY_API_KEY);
  }
  updateAuthUI();
}

function getGoogleIdToken() {
  return localStorage.getItem(STORAGE_KEY_GOOGLE_TOKEN) || '';
}

function getGoogleUser() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY_GOOGLE_USER) || 'null');
  } catch {
    return null;
  }
}

function setGoogleAuth(token, userInfo) {
  localStorage.setItem(STORAGE_KEY_GOOGLE_TOKEN, token);
  localStorage.setItem(STORAGE_KEY_GOOGLE_USER, JSON.stringify(userInfo));
  updateAuthUI();
  refreshAuthStatus();
}

function clearGoogleAuth() {
  localStorage.removeItem(STORAGE_KEY_GOOGLE_TOKEN);
  localStorage.removeItem(STORAGE_KEY_GOOGLE_USER);
  updateAuthUI();
  refreshAuthStatus();
}

async function refreshAuthStatus() {
  const customKey = getUserApiKey();
  if (customKey) {
    runsIndicator.textContent = '⚡ Unlimited (BYOK)';
    runsIndicator.classList.remove('exhausted');
    runsIndicator.title = 'Custom Gemini API Key active — unlimited runs';
    return;
  }

  const token = getGoogleIdToken();
  if (!token) {
    runsIndicator.textContent = '🔒 Sign in with Google';
    runsIndicator.classList.remove('exhausted');
    runsIndicator.title = 'Sign in with Google to get 5 free runs per day, or add your Gemini key.';
  }

  try {
    const url = token ? `/auth/status?google_id_token=${encodeURIComponent(token)}` : '/auth/status';
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      if (data.google_client_id && data.google_client_id !== activeGoogleClientId) {
        initGoogleAuth(data.google_client_id);
      }
      if (token) {
        const rem = data.remaining_runs ?? 5;
        const max = data.max_runs ?? 5;
        runsIndicator.textContent = `⚡ ${rem}/${max} free runs`;
        runsIndicator.classList.toggle('exhausted', rem === 0);
        runsIndicator.title = `${rem} free server runs remaining today. Add a custom key for unlimited runs.`;
        
        if (data.user && !getGoogleUser()) {
          localStorage.setItem(STORAGE_KEY_GOOGLE_USER, JSON.stringify(data.user));
          updateAuthUI();
        }
      }
    }
  } catch (err) {
    console.debug('Auth status check skipped:', err);
  }
}

function updateAuthUI() {
  // 1. Key button state
  const customKey = getUserApiKey();
  if (customKey) {
    openKeyModalBtn.classList.add('has-key');
    keyBtnText.textContent = 'Custom Key';
    openKeyModalBtn.title = 'Custom Gemini API Key active (Click to manage)';
    runsIndicator.textContent = '⚡ Unlimited (BYOK)';
    runsIndicator.classList.remove('exhausted');
    clearKeyBtn.hidden = false;
  } else {
    openKeyModalBtn.classList.remove('has-key');
    keyBtnText.textContent = 'Gemini Key';
    openKeyModalBtn.title = 'Add your own Gemini API Key for unlimited runs';
    clearKeyBtn.hidden = true;
  }

  // 2. Google user chip
  const user = getGoogleUser();
  if (user) {
    gSignInBtn.hidden = true;
    userProfileChip.hidden = false;
    userName.textContent = user.name || user.email || 'User';
    if (user.picture) {
      userAvatar.src = user.picture;
      userAvatar.hidden = false;
    } else {
      userAvatar.hidden = true;
    }
  } else {
    userProfileChip.hidden = true;
    gSignInBtn.hidden = false;
  }
}

// Key modal events
openKeyModalBtn.addEventListener('click', () => {
  customGeminiKeyInput.value = getUserApiKey();
  customGeminiKeyInput.type = 'password';
  keyDialog.showModal();
});

keyDialogClose.addEventListener('click', () => keyDialog.close());
cancelKeyBtn.addEventListener('click', () => keyDialog.close());
keyDialog.addEventListener('click', (e) => {
  if (e.target === keyDialog) keyDialog.close();
});

toggleKeyVisibilityBtn.addEventListener('click', () => {
  const isPass = customGeminiKeyInput.type === 'password';
  customGeminiKeyInput.type = isPass ? 'text' : 'password';
  toggleKeyVisibilityBtn.textContent = isPass ? '🔒' : '👁️';
});

saveKeyBtn.addEventListener('click', () => {
  const key = customGeminiKeyInput.value.trim();
  if (key && key.length < 15) {
    showToast('Key looks too short — please paste a valid Gemini API key', 'warning');
    return;
  }
  setUserApiKey(key);
  keyDialog.close();
  if (key) {
    showToast('✅ Custom Gemini Key saved! Unlimited runs enabled.');
  } else {
    showToast('Custom key removed.');
  }
  refreshAuthStatus();
});

clearKeyBtn.addEventListener('click', () => {
  setUserApiKey('');
  customGeminiKeyInput.value = '';
  keyDialog.close();
  showToast('Custom API key removed.');
  refreshAuthStatus();
});

// Google Sign In / Sign Out
signOutBtn.addEventListener('click', () => {
  clearGoogleAuth();
  showToast('Signed out of Google account.');
});

// Handle Google GIS callback
window.handleGoogleCredentialResponse = function(response) {
  if (response && response.credential) {
    try {
      // Decode JWT payload locally for immediate UI display
      const payloadBase64 = response.credential.split('.')[1];
      const decodedJson = JSON.parse(atob(payloadBase64.replace(/-/g, '+').replace(/_/g, '/')));
      const user = {
        name: decodedJson.name || decodedJson.email,
        email: decodedJson.email,
        picture: decodedJson.picture || '',
      };
      setGoogleAuth(response.credential, user);
      showToast(`👋 Welcome, ${user.name}! You now have 5 daily runs.`);
    } catch (e) {
      setGoogleAuth(response.credential, { name: 'Google User', email: '' });
      showToast('Signed in with Google!');
    }
  }
};

const GOOGLE_CLIENT_ID_DEFAULT = '374080008653-c6a7ml4vgq9r22atrkvnugniff1k4r0s.apps.googleusercontent.com';
let activeGoogleClientId = GOOGLE_CLIENT_ID_DEFAULT;

// Initialize Google GIS button if available
function initGoogleAuth(clientId = activeGoogleClientId) {
  if (window.google && window.google.accounts && window.google.accounts.id) {
    try {
      activeGoogleClientId = clientId || GOOGLE_CLIENT_ID_DEFAULT;
      window.google.accounts.id.initialize({
        client_id: activeGoogleClientId,
        callback: window.handleGoogleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      });
      window.google.accounts.id.renderButton(
        gSignInBtn,
        { theme: 'outline', size: 'small', type: 'standard', shape: 'pill', text: 'signin', logo_alignment: 'left' }
      );
    } catch (err) {
      console.debug('GIS init:', err);
    }
  }
}

// Initial sync
updateCounters();
updateAuthUI();
refreshAuthStatus();

// GIS loads asynchronously
if (window.google) {
  initGoogleAuth();
} else {
  window.addEventListener('load', () => setTimeout(initGoogleAuth, 800));
}
