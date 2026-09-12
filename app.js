// --- ApexEye Steward Scrutineering Workstation (Iteration 9) ---
// Data source: the /api/vision/* endpoints (DEC-012). The dashboard is a thin,
// read-optimized client over the vision store + evidence packages.

const API_BASE = (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin.startsWith('http'))
    ? window.location.origin
    : 'http://localhost:5000';

// Evidence packages are served as static files under /data/incidents/<id>/
// by the Flask catch-all route (conventional root per DEC-013).
const EVIDENCE_URL_BASE = `${API_BASE}/data/incidents/`;

// 2023 Formula 1 Driver Roster (badges & names for incident cards)
const F1_DRIVERS = {
    HAM: { num: '44', name: 'Lewis Hamilton', team: 'Mercedes-AMG F1' },
    VER: { num: '1',  name: 'Max Verstappen', team: 'Red Bull Racing' },
    PER: { num: '11', name: 'Sergio Perez', team: 'Red Bull Racing' },
    GAS: { num: '10', name: 'Pierre Gasly', team: 'Alpine F1 Team' },
    TSU: { num: '22', name: 'Yuki Tsunoda', team: 'AlphaTauri' },
    SAI: { num: '55', name: 'Carlos Sainz', team: 'Scuderia Ferrari' },
    LEC: { num: '16', name: 'Charles Leclerc', team: 'Scuderia Ferrari' },
    NOR: { num: '4',  name: 'Lando Norris', team: 'McLaren F1 Team' },
    PIA: { num: '81', name: 'Oscar Piastri', team: 'McLaren F1 Team' },
    ALB: { num: '23', name: 'Alexander Albon', team: 'Williams Racing' },
    SAR: { num: '2',  name: 'Logan Sargeant', team: 'Williams Racing' },
    MAG: { num: '20', name: 'Kevin Magnussen', team: 'Haas F1 Team' },
    HUL: { num: '27', name: 'Nico Hülkenberg', team: 'Haas F1 Team' },
    OCO: { num: '31', name: 'Esteban Ocon', team: 'Alpine F1 Team' },
    BOT: { num: '77', name: 'Valtteri Bottas', team: 'Alfa Romeo' },
    ZHO: { num: '24', name: 'Zhou Guanyu', team: 'Alfa Romeo' },
    STR: { num: '18', name: 'Lance Stroll', team: 'Aston Martin' },
    ALO: { num: '14', name: 'Fernando Alonso', team: 'Aston Martin' },
    DEV: { num: '21', name: 'Nyck de Vries', team: 'AlphaTauri' },
    RUS: { num: '63', name: 'George Russell', team: 'Mercedes-AMG F1' },
};

const DECISION_LABELS = {
    CONFIRM_DELETION: 'LAP DELETED',
    ISSUE_WARNING: 'B&W WARNING',
    DISMISS: 'DISMISSED',
};
const TIRE_IDS = ['FL', 'FR', 'RL', 'RR'];

// --- State ---
let incidentsCache = [];
let activeFilter = 'ALL';
let selectedId = null;
let selection = null;      // { incident, detail, frames, evidence }
let maskImages = {};       // mask id -> HTMLImageElement
let maskBoxes = {};        // mask id -> {x0, y0, x1, y1} bbox (loupe targeting)
let keyframeImage = null;
let frameIndex = 0;
let playTimer = null;

// --- DOM elements ---
const storeIndicator = document.getElementById('storeIndicator');
const storeStatus = document.getElementById('storeStatus');
const queueCount = document.getElementById('queueCount');
const queueList = document.getElementById('queueList');
const deckDriverNum = document.getElementById('deckDriverNum');
const deckCorner = document.getElementById('deckCorner');
const deckMeta = document.getElementById('deckMeta');
const deckVerdict = document.getElementById('deckVerdict');
const deckEmpty = document.getElementById('deckEmpty');
const canvas = document.getElementById('scrutineerCanvas');
const ctx = canvas.getContext('2d');
const hawkLoupe = document.getElementById('hawkLoupe');
const loupeCanvas = document.getElementById('loupeCanvas');
const loupeCtx = loupeCanvas.getContext('2d');
const loupeLabel = document.getElementById('loupeLabel');
const frameSlider = document.getElementById('frameSlider');
const timecode = document.getElementById('timecode');
const evidenceBadge = document.getElementById('evidenceBadge');
const roBreach = document.getElementById('roBreach');
const roConfidence = document.getElementById('roConfidence');
const roFourOff = document.getElementById('roFourOff');
const roFrames = document.getElementById('roFrames');
const roPriority = document.getElementById('roPriority');
const roReason = document.getElementById('roReason');
const birdseyeBox = document.getElementById('birdseyeBox');
const birdseyeCanvas = document.getElementById('birdseyeCanvas');
const strikesList = document.getElementById('strikesList');
const decisionStatus = document.getElementById('decisionStatus');
const maskOpacity = document.getElementById('maskOpacity');
const playBtn = document.getElementById('playBtn');

// --- Boot & data loading ---
async function init() {
    wireControls();
    await loadIncidents();
    if (incidentsCache.length > 0) await selectIncident(incidentsCache[0].incident_id);
}

async function loadIncidents() {
    try {
        const res = await fetch(`${API_BASE}/api/vision/incidents`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        incidentsCache = data.incidents || [];
        storeIndicator.className = 'status-indicator online';
        storeStatus.textContent = `Vision store: ${incidentsCache.length} incident(s)`;
    } catch (err) {
        incidentsCache = [];
        storeIndicator.className = 'status-indicator offline';
        storeStatus.textContent = 'Vision store unreachable';
    }
    renderQueue();
    renderStrikes();
}

// --- Left: priority triage queue ---
function renderQueue() {
    const filtered = activeFilter === 'ALL'
        ? incidentsCache
        : incidentsCache.filter((i) => i.priority === activeFilter);

    queueCount.textContent = filtered.length;
    if (filtered.length === 0) {
        queueList.innerHTML = '<div class="queue-empty">No incidents in this tier.</div>';
        return;
    }

    queueList.innerHTML = filtered.map((inc) => {
        const meta = F1_DRIVERS[inc.driver] || { num: '?', name: inc.driver };
        const breach = Number(inc.peak_breach_cm || 0);
        const breachClass = breach > 8 ? 'hot' : '';
        const decision = inc.steward_decision
            ? `<div class="ic-decision ${inc.steward_decision.decision}">▸ ${DECISION_LABELS[inc.steward_decision.decision] || inc.steward_decision.decision} · ${inc.steward_decision.steward}</div>`
            : '';
        const evidenceTag = inc.has_evidence ? '<i class="fa-solid fa-box-archive" title="Evidence package available"></i>' : '';
        return `
            <div class="incident-card ${inc.incident_id === selectedId ? 'selected' : ''}" onclick="selectIncident('${inc.incident_id}')">
                <div class="ic-row">
                    <span class="driver-chip">${meta.num} ${inc.driver}</span>
                    <span class="priority-pill ${(inc.priority || 'CLEARED').toLowerCase()}">${inc.priority || 'CLEARED'}</span>
                </div>
                <div class="ic-meta">
                    <span>${inc.corner} · Lap ${inc.lap}</span>
                    <span class="ic-breach ${breachClass}">${breach >= 0 ? '+' : ''}${breach.toFixed(1)} cm ${evidenceTag}</span>
                </div>
                <div class="ic-meta">
                    <span>Conf ${Math.round((inc.confidence || 0) * 100)}%</span>
                    <span>${inc.frame_count} frame(s)</span>
                </div>
                ${decision}
            </div>
        `;
    }).join('');
}

// --- Incident selection & evidence loading ---
window.selectIncident = async function (incidentId) {
    const incident = incidentsCache.find((i) => i.incident_id === incidentId);
    if (!incident) return;
    stopPlay();
    selectedId = incidentId;
    renderQueue();

    selection = { incident, detail: null, frames: [], evidence: null };
    frameIndex = 0;
    maskImages = {};
    maskBoxes = {};
    keyframeImage = null;
    deckEmpty.classList.remove('hidden');

    const base = `${API_BASE}/api/vision/incident/${encodeURIComponent(incidentId)}`;
    const [detailRes, framesRes, evidenceRes] = await Promise.all([
        fetch(base),
        fetch(`${base}/frames`),
        fetch(`${base}/evidence`).catch(() => null),
    ]);
    if (detailRes.ok) selection.detail = await detailRes.json();
    if (framesRes.ok) selection.frames = (await framesRes.json()).frames || [];
    if (evidenceRes && evidenceRes.ok) selection.evidence = await evidenceRes.json();

    deckEmpty.classList.add('hidden');
    renderScrubber();
    renderDossier();
    await loadAssets();
    drawDeck();
};

function evidenceUrl(relPath) {
    return `${EVIDENCE_URL_BASE}${encodeURIComponent(selection.incident.incident_id)}/${relPath}`;
}

function loadAssets() {
    const jobs = [];
    const rendered = selection.evidence && selection.evidence.evidence
        ? selection.evidence.evidence.rendered || [] : [];
    for (const rel of rendered) {
        if (!rel.endsWith('.png')) continue;
        const id = rel.split('/').pop().replace('.png', '');
        jobs.push(new Promise((resolve) => {
            const img = new Image();
            img.onload = () => { maskImages[id] = img; maskBoxes[id] = imageBbox(img); resolve(); };
            img.onerror = () => resolve();
            img.src = evidenceUrl(rel);
        }));
    }
    // Optional keyframe (synthetic demo or future broadcast extraction) at
    // the conventional original/keyframe.jpg slot of the package.
    jobs.push(new Promise((resolve) => {
        const img = new Image();
        img.onload = () => { keyframeImage = img; resolve(); };
        img.onerror = () => resolve();
        img.src = evidenceUrl('original/keyframe.jpg');
    }));
    return Promise.all(jobs);
}

function imageBbox(img) {
    const off = document.createElement('canvas');
    off.width = img.naturalWidth;
    off.height = img.naturalHeight;
    const octx = off.getContext('2d');
    octx.drawImage(img, 0, 0);
    try {
        const data = octx.getImageData(0, 0, off.width, off.height).data;
        let x0 = off.width, y0 = off.height, x1 = -1, y1 = -1;
        for (let y = 0; y < off.height; y++) {
            for (let x = 0; x < off.width; x++) {
                if (data[(y * off.width + x) * 4 + 3] > 10) {
                    if (x < x0) x0 = x;
                    if (x > x1) x1 = x;
                    if (y < y0) y0 = y;
                    if (y > y1) y1 = y;
                }
            }
        }
        if (x1 >= 0) return { x0, y0, x1, y1 };
    } catch (err) { /* tainted canvas: no bbox */ }
    return null;
}

// --- Center: forensic deck rendering ---
function drawDeck() {
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const keyframeOn = document.getElementById('layerKeyframe').checked;
    if (keyframeOn && keyframeImage) {
        drawCover(keyframeImage, w, h);
    } else {
        drawGridBackdrop(w, h);
    }

    const alpha = Number(maskOpacity.value) / 100;
    if (document.getElementById('layerLine').checked && maskImages.line) {
        ctx.globalAlpha = alpha;
        ctx.drawImage(maskImages.line, 0, 0, w, h);
        ctx.globalAlpha = 1;
    }
    if (document.getElementById('layerTires').checked) {
        ctx.globalAlpha = alpha;
        for (const id of TIRE_IDS) {
            if (maskImages[id]) ctx.drawImage(maskImages[id], 0, 0, w, h);
        }
        ctx.globalAlpha = 1;
    }

    drawHudOverlay();
    drawBirdseye();
    drawLoupe();
}

function drawCover(img, w, h) {
    const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
    const dw = img.naturalWidth * scale;
    const dh = img.naturalHeight * scale;
    ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
}

function drawGridBackdrop(w, h) {
    ctx.fillStyle = '#0b1016';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(120, 140, 170, 0.12)';
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y < h; y += 40) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    ctx.fillStyle = 'rgba(125, 138, 160, 0.55)';
    ctx.font = '13px "Roboto Mono", monospace';
    ctx.fillText('NO KEYFRAME — GRID MODE', 16, 26);
}

function drawHudOverlay() {
    if (!selection || selection.frames.length === 0) return;
    const f = selection.frames[Math.min(frameIndex, selection.frames.length - 1)];
    if (!f) return;
    const exc = (f.signed_excursion_cm !== undefined && f.signed_excursion_cm !== null)
        ? ` · ${Number(f.signed_excursion_cm).toFixed(1)} cm` : '';
    const label = `FRAME ${f.frame}${f.is_peak ? ' · PEAK' : ''}${exc}`;
    ctx.font = '12px "Roboto Mono", monospace';
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = 'rgba(5, 7, 11, 0.78)';
    ctx.fillRect(12, canvas.height - 36, tw + 22, 26);
    ctx.fillStyle = f.is_peak ? '#ff3b57' : '#39ff88';
    ctx.fillText(label, 23, canvas.height - 18);
}

// --- Hawk-Eye loupe: zoomed view of the most-excursed tire ---
function loupeTarget() {
    if (!selection.evidence || !selection.evidence.measurements) return null;
    const wheels = selection.evidence.measurements.wheels || {};
    let best = null;
    for (const id of TIRE_IDS) {
        const w = wheels[id];
        if (!w) continue;
        const exc = Number(w.signed_excursion_cm || 0);
        if (!best || exc > best.exc) best = { id, exc };
    }
    return best;
}

function drawLoupe() {
    const loupeOn = document.getElementById('layerLoupe').checked;
    const target = loupeTarget();
    const box = target ? maskBoxes[target.id] : null;
    if (!loupeOn || !target || !box) {
        hawkLoupe.classList.add('hidden');
        return;
    }
    hawkLoupe.classList.remove('hidden');

    const lw = loupeCanvas.width, lh = loupeCanvas.height;
    const zoom = 2.2;
    const sw = lw / zoom, sh = lh / zoom;
    const cx = (box.x0 + box.x1) / 2;
    const cy = (box.y0 + box.y1) / 2;
    const sx = Math.max(0, Math.min(canvas.width - sw, cx - sw / 2));
    const sy = Math.max(0, Math.min(canvas.height - sh, cy - sh / 2));

    loupeCtx.imageSmoothingEnabled = false;
    loupeCtx.fillStyle = '#05070b';
    loupeCtx.fillRect(0, 0, lw, lh);
    loupeCtx.drawImage(canvas, sx, sy, sw, sh, 0, 0, lw, lh);

    // Crosshair on the contact edge under review
    loupeCtx.strokeStyle = 'rgba(57, 255, 136, 0.85)';
    loupeCtx.lineWidth = 1;
    loupeCtx.beginPath();
    loupeCtx.moveTo(lw / 2, 0); loupeCtx.lineTo(lw / 2, lh);
    loupeCtx.moveTo(0, lh / 2); loupeCtx.lineTo(lw, lh / 2);
    loupeCtx.stroke();

    const sign = target.exc >= 0 ? '+' : '';
    loupeLabel.textContent = `HAWK-EYE · ${target.id} ${sign}${target.exc.toFixed(1)}cm`;
}

// --- Bird's-eye: schematic top view driven by per-wheel measurements ---
function drawBirdseye() {
    const show = document.getElementById('layerBird').checked;
    if (!show) { birdseyeBox.style.display = 'none'; return; }
    birdseyeBox.style.display = 'block';

    const c = birdseyeCanvas.getContext('2d');
    const w = birdseyeCanvas.width, h = birdseyeCanvas.height;
    c.fillStyle = '#0b1016';
    c.fillRect(0, 0, w, h);

    // Track edge: white line band on the right
    const lineX = w * 0.62;
    c.fillStyle = 'rgba(230, 230, 235, 0.85)';
    c.fillRect(lineX - 7, 0, 14, h);
    c.fillStyle = 'rgba(125, 138, 160, 0.9)';
    c.font = '9px "Roboto Mono", monospace';
    c.fillText('LINE', lineX + 11, 12);

    // Car body
    const carX = w * 0.40, carY = h * 0.18, carW = w * 0.22, carH = h * 0.6;
    c.fillStyle = 'rgba(150, 158, 170, 0.85)';
    c.fillRect(carX, carY, carW, carH);

    // Wheels colored by assessment (cyan = overlap, amber/red = gap)
    const wheels = selection && selection.evidence && selection.evidence.measurements
        ? selection.evidence.measurements.wheels || {} : {};
    const positions = {
        FL: [carX + carW, carY],
        FR: [carX + carW, carY + carH - 16],
        RL: [carX - 14, carY],
        RR: [carX - 14, carY + carH - 16],
    };
    for (const id of TIRE_IDS) {
        const wd = wheels[id];
        const [wx, wy] = positions[id];
        const overlapping = wd && Number(wd.overlap_area_cm2 || 0) > 0;
        const gap = wd ? Number(wd.gap_cm || 0) : 0;
        c.fillStyle = overlapping ? '#22d3ee' : (gap > 8 ? '#ff3b57' : '#ffb020');
        c.fillRect(wx, wy, 14, 16);
        if (wd) {
            c.fillStyle = 'rgba(219, 228, 240, 0.9)';
            c.font = '9px "Roboto Mono", monospace';
            const tag = !overlapping && gap > 0 ? ` +${gap.toFixed(1)}` : '';
            c.fillText(`${id}${tag}`, wx - 8, wy - 3);
        }
    }
}

// --- Frame scrubber ---
function renderScrubber() {
    const n = selection.frames.length;
    frameSlider.max = Math.max(0, n - 1);
    frameSlider.value = 0;
    frameIndex = 0;
    updateTimecode();
}

function currentFrame() {
    if (!selection || selection.frames.length === 0) return null;
    return selection.frames[Math.min(frameIndex, selection.frames.length - 1)] || null;
}

function updateTimecode() {
    const f = currentFrame();
    if (!f) { timecode.textContent = 'FRAME --'; return; }
    const exc = (f.signed_excursion_cm !== undefined && f.signed_excursion_cm !== null)
        ? ` · ${Number(f.signed_excursion_cm).toFixed(1)}cm` : '';
    timecode.textContent = `FRAME ${f.frame}${f.is_peak ? ' · PEAK' : ''}${exc}`;
}

function stepFrame(delta) {
    if (!selection || selection.frames.length === 0) return;
    frameIndex = Math.min(selection.frames.length - 1, Math.max(0, frameIndex + delta));
    frameSlider.value = frameIndex;
    updateTimecode();
    drawDeck();
}

function togglePlay() {
    if (playTimer) { stopPlay(); return; }
    if (!selection || selection.frames.length === 0) return;
    playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
    playTimer = setInterval(() => {
        if (frameIndex >= selection.frames.length - 1) { stopPlay(); return; }
        stepFrame(1);
    }, 400);
}

function stopPlay() {
    if (playTimer) clearInterval(playTimer);
    playTimer = null;
    playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
}

// --- Right: case dossier readouts ---
function renderDossier() {
    const inc = selection.incident;
    const detail = selection.detail || inc;
    const meta = F1_DRIVERS[inc.driver] || { num: '?', name: inc.driver, team: 'F1' };

    deckDriverNum.textContent = meta.num;
    deckCorner.textContent = `${meta.name} — ${inc.corner}`;
    deckMeta.textContent = `Lap ${inc.lap} · ${inc.frame_count} frame(s) · ${inc.incident_id}`;
    const pr = (inc.priority || 'CLEARED').toLowerCase();
    deckVerdict.textContent = inc.priority || 'CLEARED';
    deckVerdict.className = `deck-verdict ${pr}`;

    const breach = Number(inc.peak_breach_cm || 0);
    roBreach.textContent = `${breach >= 0 ? '+' : ''}${breach.toFixed(1)} cm`;
    roBreach.className = `value ${breach > 8 ? 'hot' : ''}`;
    roConfidence.textContent = `${Math.round((inc.confidence || 0) * 100)}%`;
    const verdict = (selection.evidence && selection.evidence.metadata && selection.evidence.metadata.verdict) || detail;
    const fourOff = Boolean(verdict.four_wheels_off);
    roFourOff.textContent = fourOff ? 'YES' : 'NO';
    roFourOff.className = `value ${fourOff ? 'hot' : ''}`;
    roFrames.textContent = `${inc.frame_count}`;
    roPriority.textContent = inc.priority || '--';

    const reason = (selection.evidence && selection.evidence.measurements && selection.evidence.measurements.reason)
        || detail.reason || 'No written reason in package.';
    roReason.textContent = `Recommendation: ${reason}`;

    evidenceBadge.textContent = selection.evidence ? 'Package loaded' : 'No package';
    renderDecisionStatus();
}

function renderDecisionStatus() {
    const d = selection.incident.steward_decision;
    if (!d) {
        decisionStatus.textContent = 'No adjudication recorded';
        decisionStatus.className = 'decision-status';
        return;
    }
    const notes = d.notes ? ` — ${d.notes}` : '';
    decisionStatus.textContent = `${DECISION_LABELS[d.decision] || d.decision} by ${d.steward}${notes}`;
    decisionStatus.className = `decision-status ${d.decision}`;
}

// --- Driver strike tracker (FIA track-limits ladder) ---
function computeStrikes() {
    const strikes = {};
    for (const inc of incidentsCache) {
        if (inc.steward_decision && inc.steward_decision.decision === 'CONFIRM_DELETION') {
            strikes[inc.driver] = (strikes[inc.driver] || 0) + 1;
        }
    }
    return strikes;
}

function strikeLabel(n) {
    if (n <= 0) return '—';
    if (n === 1) return '1st offence';
    if (n === 2) return 'B&W flag';
    return '5s penalty';
}

function renderStrikes() {
    const entries = Object.entries(computeStrikes()).sort((a, b) => b[1] - a[1]);
    if (entries.length === 0) {
        strikesList.innerHTML = '<div class="box-note">No confirmed deletions yet.</div>';
        return;
    }
    strikesList.innerHTML = entries.map(([driver, n]) => (
        `<div class="strike-row"><span class="who">${driver}</span><span class="what">${strikeLabel(n)}</span><span class="tally">×${n}</span></div>`
    )).join('');
}

// --- Steward adjudication -> POST /api/vision/incident/<id>/decision ---
async function recordDecision(decision) {
    if (!selection) return;
    const steward = document.getElementById('stewardId').value.trim() || 'UNKNOWN';
    const notes = document.getElementById('decisionNotes').value.trim();
    const buttons = ['btnDelete', 'btnWarning', 'btnDismiss'].map((id) => document.getElementById(id));
    buttons.forEach((b) => { b.disabled = true; });
    decisionStatus.textContent = 'Recording…';
    decisionStatus.className = 'decision-status';
    try {
        const res = await fetch(
            `${API_BASE}/api/vision/incident/${encodeURIComponent(selection.incident.incident_id)}/decision`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ decision, steward, notes }),
            },
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        await loadIncidents();
        const fresh = incidentsCache.find((i) => i.incident_id === selection.incident.incident_id);
        if (fresh) selection.incident = fresh;
        renderQueue();
        renderDossier();
    } catch (err) {
        decisionStatus.textContent = `Error: ${err.message}`;
    } finally {
        buttons.forEach((b) => { b.disabled = false; });
    }
}

// --- Export: printable FIA-style decision document ---
function exportDocument() {
    if (!selection) return;
    const inc = selection.incident;
    const d = inc.steward_decision;
    const meas = selection.evidence ? selection.evidence.measurements : null;
    const meta = F1_DRIVERS[inc.driver] || { name: inc.driver, team: 'Formula 1' };

    const wheelRows = (meas && meas.wheels)
        ? TIRE_IDS.map((id) => {
            const w = meas.wheels[id] || {};
            return `<tr><td>${id}</td><td>${w.overlapping ? 'overlap' : 'gap'}</td><td>${Number(w.gap_cm || 0).toFixed(2)} cm</td><td>${Number(w.signed_excursion_cm || 0).toFixed(2)} cm</td></tr>`;
        }).join('')
        : '<tr><td colspan="4">Measurements not present in package.</td></tr>';

    const win = window.open('', '_blank');
    win.document.write(`<!DOCTYPE html><html><head><title>FIA Stewarding Decision — ${inc.incident_id}</title>
<style>body{font-family:Georgia,serif;margin:40px;color:#111}h1{font-size:20px;border-bottom:2px solid #111;padding-bottom:6px}
table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #999;padding:6px 10px;font-size:13px;text-align:left}
.sig{margin-top:48px;display:flex;justify-content:space-between}.sig div{border-top:1px solid #111;padding-top:6px;width:220px;font-size:12px}
.meta{font-size:13px;line-height:1.6}</style></head><body>
<h1>FIA Stewarding Decision Document</h1>
<p class="meta"><strong>Incident:</strong> ${inc.incident_id}<br>
<strong>Driver:</strong> ${meta.name} (${inc.driver})<br>
<strong>Session:</strong> 2023 Austrian Grand Prix — Race<br>
<strong>Location:</strong> ${inc.corner}, Lap ${inc.lap}<br>
<strong>Generated:</strong> ${new Date().toISOString()}<br>
<strong>Adjudication:</strong> ${d ? (DECISION_LABELS[d.decision] || d.decision) + ' — ' + d.steward : 'PENDING'}</p>
<p class="meta"><strong>Optical recommendation:</strong> ${inc.priority} · peak excursion ${Number(inc.peak_breach_cm).toFixed(2)} cm · confidence ${Math.round((inc.confidence || 0) * 100)}%</p>
<table><tr><th>Wheel</th><th>Contact</th><th>Gap</th><th>Excursion</th></tr>${wheelRows}</table>
<p class="meta"><strong>Reasoning:</strong> ${meas && meas.reason ? meas.reason : 'See evidence package.'}${d && d.notes ? '<br><strong>Steward notes:</strong> ' + d.notes : ''}</p>
<div class="sig"><div>Steward Signature</div><div>Timestamp (UTC)</div></div>
<script>window.print()<\/script></body></html>`);
    win.document.close();
}

// --- Control wiring ---
function wireControls() {
    document.getElementById('queueTabs').addEventListener('click', (e) => {
        const btn = e.target.closest('.queue-tab');
        if (!btn) return;
        document.querySelectorAll('.queue-tab').forEach((t) => t.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        renderQueue();
    });
    frameSlider.addEventListener('input', () => {
        frameIndex = Number(frameSlider.value);
        updateTimecode();
        drawDeck();
    });
    document.getElementById('stepBackBtn').addEventListener('click', () => stepFrame(-1));
    document.getElementById('stepFwdBtn').addEventListener('click', () => stepFrame(1));
    playBtn.addEventListener('click', togglePlay);
    maskOpacity.addEventListener('input', drawDeck);
    for (const id of ['layerKeyframe', 'layerLine', 'layerTires', 'layerBird', 'layerLoupe']) {
        document.getElementById(id).addEventListener('change', drawDeck);
    }
    document.getElementById('btnDelete').addEventListener('click', () => recordDecision('CONFIRM_DELETION'));
    document.getElementById('btnWarning').addEventListener('click', () => recordDecision('ISSUE_WARNING'));
    document.getElementById('btnDismiss').addEventListener('click', () => recordDecision('DISMISS'));
    document.getElementById('btnExport').addEventListener('click', exportDocument);
}

init();