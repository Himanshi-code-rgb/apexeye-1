// --- Mock Data ---
const mockViolations = [
    { id: '104', driverNum: '1', driverName: 'Max Verstappen', team: 'Red Bull Racing', turn: 'T4', lap: 12, time: '14:23:45', session: 'Race', track: 'monza' },
    { id: '105', driverNum: '4', driverName: 'Lando Norris', team: 'McLaren', turn: 'T11', lap: 15, time: '14:28:12', session: 'Race', track: 'monza' },
    { id: '106', driverNum: '44', driverName: 'Lewis Hamilton', team: 'Mercedes', turn: 'T4', lap: 22, time: '14:39:05', session: 'Race', track: 'monza' },
    { id: '107', driverNum: '16', driverName: 'Charles Leclerc', team: 'Ferrari', turn: 'T8', lap: 5, time: '15:10:22', session: 'Qualifying', track: 'silverstone' },
    { id: '108', driverNum: '63', driverName: 'George Russell', team: 'Mercedes', turn: 'T9', lap: 18, time: '15:32:10', session: 'Qualifying', track: 'silverstone' },
    { id: '109', driverNum: '81', driverName: 'Oscar Piastri', team: 'McLaren', turn: 'T1', lap: 2, time: '14:05:30', session: 'FP2', track: 'spa' },
    { id: '110', driverNum: '11', driverName: 'Sergio Perez', team: 'Red Bull Racing', turn: 'T14', lap: 8, time: '14:18:45', session: 'FP2', track: 'spa' },
    { id: '111', driverNum: '1', driverName: 'Max Verstappen', team: 'Red Bull Racing', turn: 'T4', lap: 44, time: '15:12:00', session: 'Race', track: 'monza' },
    { id: '112', driverNum: '55', driverName: 'Carlos Sainz', team: 'Ferrari', turn: 'T15', lap: 12, time: '14:23:11', session: 'Race', track: 'silverstone' },
];

const trackData = {
    monza: {
        title: "Autodromo Nazionale Monza",
        svgUrl: "https://raw.githubusercontent.com/julesr0y/f1-circuits-svg/main/circuits/detailed/white-outline/monza-7.svg",
    },
    silverstone: {
        title: "Silverstone Circuit",
        svgUrl: "https://raw.githubusercontent.com/julesr0y/f1-circuits-svg/main/circuits/detailed/white-outline/silverstone-8.svg",
    },
    spa: {
        title: "Circuit de Spa-Francorchamps",
        svgUrl: "https://raw.githubusercontent.com/julesr0y/f1-circuits-svg/main/circuits/detailed/white-outline/spa-francorchamps-4.svg",
    }
};

// --- State ---
let currentTrack = 'monza';
let currentSearch = '';
let currentSession = 'all';

// --- DOM Elements ---
const svgWrapper = document.getElementById('svgWrapper');
const currentTrackTitle = document.getElementById('currentTrackTitle');
const violationsList = document.getElementById('violationsList');
const trackBtns = document.querySelectorAll('.track-btn');
const searchInput = document.getElementById('searchInput');
const sessionFilter = document.getElementById('sessionFilter');
const totalViolationsEl = document.getElementById('totalViolations');
const worstTurnEl = document.getElementById('worstTurn');

// Modal Elements
const incidentModal = document.getElementById('incidentModal');
const closeModalBtn = document.getElementById('closeModalBtn');

// --- Initialization ---
async function init() {
    setupEventListeners();
    await loadTrack(currentTrack);
    renderViolations();
}

// --- Event Listeners ---
function setupEventListeners() {
    trackBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const trackId = btn.getAttribute('data-track');
            if(trackId === currentTrack) return;
            
            // Update UI
            trackBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            currentTrack = trackId;
            await loadTrack(currentTrack);
            renderViolations();
        });
    });

    searchInput.addEventListener('input', (e) => {
        currentSearch = e.target.value.toLowerCase();
        renderViolations();
    });

    sessionFilter.addEventListener('change', (e) => {
        currentSession = e.target.value;
        renderViolations();
    });

    closeModalBtn.addEventListener('click', closeModal);
    incidentModal.addEventListener('click', (e) => {
        if(e.target === incidentModal) closeModal();
    });
}

// --- Track Loading ---
async function loadTrack(trackId) {
    svgWrapper.innerHTML = '<div class="loader">Loading Track Data...</div>';
    currentTrackTitle.textContent = trackData[trackId].title;
    
    try {
        const response = await fetch(trackData[trackId].svgUrl);
        if(!response.ok) throw new Error("Failed to load SVG");
        let svgContent = await response.text();
        
        // Inject SVG
        svgWrapper.innerHTML = svgContent;
        
        // Optional: Animate SVG paths
        const paths = svgWrapper.querySelectorAll('path');
        paths.forEach(p => {
            const length = p.getTotalLength();
            p.style.strokeDasharray = length;
            p.style.strokeDashoffset = length;
            p.style.animation = 'drawTrack 2s ease forwards';
        });

    } catch (error) {
        svgWrapper.innerHTML = '<div style="color: #e10600;">Failed to load track map. Using placeholder.</div>';
    }
}

// --- Rendering Violations ---
function renderViolations() {
    const filtered = mockViolations.filter(v => {
        const matchTrack = v.track === currentTrack;
        const matchSession = currentSession === 'all' || v.session === currentSession;
        const matchSearch = v.driverName.toLowerCase().includes(currentSearch) || 
                            v.turn.toLowerCase().includes(currentSearch) ||
                            v.driverNum.includes(currentSearch);
        return matchTrack && matchSession && matchSearch;
    });

    updateStats(filtered);

    if(filtered.length === 0) {
        violationsList.innerHTML = '<div style="padding: 1rem; color: #888; text-align: center;">No violations found.</div>';
        return;
    }

    violationsList.innerHTML = filtered.map(v => `
        <div class="violation-card" onclick="openModal('${v.id}')">
            <div class="v-card-header">
                <span>${v.time}</span>
                <span>${v.session}</span>
            </div>
            <div class="v-card-driver">
                <div class="v-number">${v.driverNum}</div>
                <div class="v-name">${v.driverName}</div>
            </div>
            <div class="v-card-footer">
                <div>Turn <span>${v.turn}</span></div>
                <div>Lap <span>${v.lap}</span></div>
            </div>
        </div>
    `).join('');
}

function updateStats(violations) {
    totalViolationsEl.textContent = violations.length;
    
    if(violations.length === 0) {
        worstTurnEl.textContent = "-";
        return;
    }

    const turnCounts = {};
    let worst = violations[0].turn;
    let max = 0;

    violations.forEach(v => {
        turnCounts[v.turn] = (turnCounts[v.turn] || 0) + 1;
        if(turnCounts[v.turn] > max) {
            max = turnCounts[v.turn];
            worst = v.turn;
        }
    });

    worstTurnEl.textContent = worst;
}

// --- Modal Handling ---
window.openModal = function(id) {
    const v = mockViolations.find(x => x.id === id);
    if(!v) return;

    document.getElementById('modalId').textContent = v.id;
    document.getElementById('modalSession').textContent = v.session;
    document.getElementById('modalDriverNum').textContent = v.driverNum;
    document.getElementById('modalDriverName').textContent = v.driverName;
    document.getElementById('modalTeam').textContent = v.team;
    document.getElementById('modalTurn').textContent = v.turn;
    document.getElementById('modalLap').textContent = v.lap;
    document.getElementById('modalTime').textContent = v.time;

    incidentModal.classList.remove('hidden');
}

function closeModal() {
    incidentModal.classList.add('hidden');
}

// Add CSS animation for SVG
const style = document.createElement('style');
style.innerHTML = `
    @keyframes drawTrack {
        to { stroke-dashoffset: 0; }
    }
`;
document.head.appendChild(style);

// Start
init();
