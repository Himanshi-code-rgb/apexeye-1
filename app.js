// --- ApexEye Telemetry HUD Client (Phase 1 Ground Truth Engine) ---

const API_BASE = (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin.startsWith('http'))
    ? window.location.origin
    : 'http://localhost:5000';

// 2023 Formula 1 Driver Roster
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

const trackData = {
    spielberg: {
        title: "Red Bull Ring (Spielberg)",
        isCalibrated: true,
        apiEndpoint: `${API_BASE}/api/track/spielberg`
    },
    monza: {
        title: "Autodromo Nazionale Monza",
        isCalibrated: false,
    },
    silverstone: {
        title: "Silverstone Circuit",
        isCalibrated: false,
    },
    spa: {
        title: "Circuit de Spa-Francorchamps",
        isCalibrated: false,
    }
};

// --- State ---
let currentTrack = 'spielberg';
let currentSearch = '';
let currentAdjudication = 'all'; // 'all' | 'gt_only' | 'sub_threshold'
let violationsCache = [];

// --- DOM Elements ---
const svgWrapper = document.getElementById('svgWrapper');
const currentTrackTitle = document.getElementById('currentTrackTitle');
const violationsList = document.getElementById('violationsList');
const trackBtns = document.querySelectorAll('.track-btn');
const searchInput = document.getElementById('searchInput');
const adjudicationFilter = document.getElementById('adjudicationFilter');
const totalViolationsEl = document.getElementById('totalViolations');
const worstTurnEl = document.getElementById('worstTurn');
const confirmedCountEl = document.getElementById('confirmedCount');
const precisionRateEl = document.getElementById('precisionRate');

// Modal Elements
const incidentModal = document.getElementById('incidentModal');
const closeModalBtn = document.getElementById('closeModalBtn');
const modalId = document.getElementById('modalId');
const modalSession = document.getElementById('modalSession');
const modalDriverNum = document.getElementById('modalDriverNum');
const modalDriverName = document.getElementById('modalDriverName');
const modalTeam = document.getElementById('modalTeam');
const modalTurn = document.getElementById('modalTurn');
const modalLap = document.getElementById('modalLap');
const modalSpeed = document.getElementById('modalSpeed');
const modalBreach = document.getElementById('modalBreach');
const modalDuration = document.getElementById('modalDuration');
const modalConfidence = document.getElementById('modalConfidence');
const modalFiaReason = document.getElementById('modalFiaReason');

// --- Initialization ---
async function init() {
    setupEventListeners();
    await loadTrack(currentTrack);
    await loadStats();
    await loadViolations();
}

// --- Event Listeners ---
function setupEventListeners() {
    trackBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const trackId = btn.getAttribute('data-track');
            if (trackId === currentTrack) return;

            if (!trackData[trackId] || !trackData[trackId].isCalibrated) {
                alert(`${trackData[trackId] ? trackData[trackId].title : trackId} is uncalibrated in Phase 1. Please use the Spielberg (Red Bull Ring) dataset.`);
                return;
            }

            trackBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            currentTrack = trackId;
            await loadTrack(currentTrack);
            await loadStats();
            await loadViolations();
        });
    });

    searchInput.addEventListener('input', (e) => {
        currentSearch = e.target.value.trim().toLowerCase();
        renderViolations();
    });

    adjudicationFilter.addEventListener('change', async (e) => {
        currentAdjudication = e.target.value;
        await loadViolations();
    });

    closeModalBtn.addEventListener('click', closeModal);
    incidentModal.addEventListener('click', (e) => {
        if (e.target === incidentModal) closeModal();
    });
}

// --- Track Loading ---
async function loadTrack(trackId) {
    svgWrapper.innerHTML = '<div class="loader">Loading Track Survey Data...</div>';
    currentTrackTitle.textContent = trackData[trackId].title;

    try {
        const response = await fetch(`${API_BASE}/api/track/${trackId}`);
        if (!response.ok) throw new Error("Failed to load circuit data");
        const data = await response.json();

        if (data.svg_available && data.svg_content) {
            svgWrapper.innerHTML = data.svg_content;
            const svg = svgWrapper.querySelector('svg');
            if (svg) {
                svg.setAttribute('viewBox', '0 0 500 500');
                svg.style.width = '100%';
                svg.style.height = '100%';
            }

            const paths = svgWrapper.querySelectorAll('path');
            paths.forEach(p => {
                const length = p.getTotalLength();
                p.style.strokeDasharray = length;
                p.style.strokeDashoffset = length;
                p.style.animation = 'drawTrack 2s ease forwards';
            });
        } else {
            svgWrapper.innerHTML = '<div style="color: #888;">Circuit layout survey data loaded.</div>';
        }
    } catch (error) {
        svgWrapper.innerHTML = `<div style="color: #e10600;">Error loading circuit layout: ${error.message}</div>`;
    }
}

// --- High-Level Stats ---
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/violations/stats`);
        if (!response.ok) throw new Error("Failed to load summary stats");
        const stats = await response.json();

        totalViolationsEl.textContent = stats.total_violations || 0;
        confirmedCountEl.textContent = stats.fia_confirmed_count || 0;
        precisionRateEl.textContent = `${Math.round((stats.precision_rate || 0) * 100)}%`;

        if (stats.corner_breakdown && Object.keys(stats.corner_breakdown).length > 0) {
            const sortedCorners = Object.entries(stats.corner_breakdown).sort((a, b) => b[1] - a[1]);
            worstTurnEl.textContent = sortedCorners[0][0];
        } else {
            worstTurnEl.textContent = "-";
        }
    } catch (error) {
        console.error("Error loading stats:", error);
    }
}

// --- Violations Data Fetching ---
async function loadViolations() {
    violationsList.innerHTML = '<div class="loader">Querying Incidents...</div>';

    let url = `${API_BASE}/api/violations?limit=250`;
    if (currentAdjudication === 'gt_only') {
        url += '&ground_truth_only=true';
    }

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to fetch violations");
        const data = await response.json();
        violationsCache = data.violations || [];
        renderViolations();
    } catch (error) {
        violationsList.innerHTML = `<div style="color: #e10600; padding: 1rem;">Failed to fetch violations: ${error.message}</div>`;
    }
}

// --- Formatting Helpers ---
function formatRaceTime(seconds) {
    if (!seconds && seconds !== 0) return "--:--";
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(1);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

// --- Rendering Violations ---
function renderViolations() {
    const filtered = violationsCache.filter(v => {
        // Adjudication filter for sub_threshold
        if (currentAdjudication === 'sub_threshold' && v.fia_ground_truth) {
            return false;
        }

        if (!currentSearch) return true;

        const driverMeta = F1_DRIVERS[v.driver] || { name: v.driver, num: '' };
        const query = currentSearch;
        return (
            v.driver.toLowerCase().includes(query) ||
            driverMeta.name.toLowerCase().includes(query) ||
            v.corner.toLowerCase().includes(query) ||
            String(v.lap_number).includes(query) ||
            v.violation_id.toLowerCase().includes(query)
        );
    });

    if (filtered.length === 0) {
        violationsList.innerHTML = '<div style="padding: 1.5rem; color: #888; text-align: center;">No matching incidents found.</div>';
        return;
    }

    violationsList.innerHTML = filtered.map(v => {
        const meta = F1_DRIVERS[v.driver] || { num: '?', name: v.driver, team: 'Formula 1' };
        const isGt = Boolean(v.fia_ground_truth);
        const badgeClass = isGt ? 'badge-gt' : 'badge-sub';
        const badgeLabel = isGt ? 'FIA Deletion' : 'Sub-Threshold';
        const breachDepth = `+${Number(v.peak_breach_m).toFixed(2)}m`;

        return `
            <div class="violation-card" onclick="openModal('${v.violation_id}')">
                <div class="v-card-header">
                    <span>${formatRaceTime(v.start_time_sec)}</span>
                    <span class="v-card-badge ${badgeClass}">${badgeLabel}</span>
                </div>
                <div class="v-card-driver">
                    <div class="v-number">${meta.num}</div>
                    <div class="v-name">${meta.name}</div>
                </div>
                <div class="v-card-footer">
                    <div>${v.corner}</div>
                    <div>Lap <span>${v.lap_number}</span></div>
                    <div class="v-breach-depth">${breachDepth}</div>
                </div>
            </div>
        `;
    }).join('');
}

// --- Modal Handling ---
window.openModal = async function(violationId) {
    try {
        const response = await fetch(`${API_BASE}/api/violations/${encodeURIComponent(violationId)}`);
        if (!response.ok) throw new Error("Could not load incident details");
        const data = await response.json();
        const v = data.violation;
        const report = data.forensic_report;
        const meta = F1_DRIVERS[v.driver] || { num: '?', name: v.driver, team: 'Formula 1' };

        modalId.textContent = v.violation_id;
        modalSession.textContent = "2023 Austrian GP (Race)";
        modalDriverNum.textContent = meta.num;
        modalDriverName.textContent = meta.name;
        modalTeam.textContent = meta.team;
        modalTurn.textContent = v.corner;
        modalLap.textContent = v.lap_number;
        modalSpeed.textContent = `${v.speed_kph} km/h`;
        modalBreach.textContent = `+${v.peak_breach_m} m`;
        modalDuration.textContent = `${v.duration_sec} s`;
        modalConfidence.textContent = `${Math.round(v.confidence_score * 100)}%`;
        modalFiaReason.textContent = report.fia_official_adjudication;

        incidentModal.classList.remove('hidden');
    } catch (err) {
        alert(`Error: ${err.message}`);
    }
};

function closeModal() {
    incidentModal.classList.add('hidden');
}

// Inject keyframe animation for SVG stroke animation
const style = document.createElement('style');
style.innerHTML = `
    @keyframes drawTrack {
        to { stroke-dashoffset: 0; }
    }
`;
document.head.appendChild(style);

// Start
init();
