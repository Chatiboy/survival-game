from flask import Flask, render_template_string, request, redirect, url_for
from flask_socketio import SocketIO, emit
import socket
import qrcode
import base64
from io import BytesIO
import os
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'survival_secret')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') 

# Global State
active_game = None # 'survival' or 'jumble'

# --- SURVIVAL GAME VARIABLES ---
survival_players = {}       
survival_question = ""
survival_round_active = False
survival_answers_locked = False

# --- JUMBLE GAME VARIABLES ---
jumble_players = {}
jumble_current_scrambled = ""
jumble_current_answer = ""
jumble_round_active = False
jumble_answered_this_round = []
jumble_winners = []
JUMBLE_TARGET_SCORE = 5
JUMBLE_MAX_WINNERS = 3

JUMBLE_WORD_LIST = [
    {"scrambled": "TPHNEALE", "answer": "ELEPHANT"}, {"scrambled": "RATGIU", "answer": "GUITAR"},
    {"scrambled": "AZZIP", "answer": "PIZZA"}, {"scrambled": "CAENO", "answer": "OCEAN"},
    {"scrambled": "REGIT", "answer": "TIGER"}, {"scrambled": "TENLAP", "answer": "PLANET"},
    {"scrambled": "ROTCOD", "answer": "DOCTOR"}, {"scrambled": "LOOHCS", "answer": "SCHOOL"},
    {"scrambled": "NREDAG", "answer": "GARDEN"}, {"scrambled": "WODNIW", "answer": "WINDOW"},
    {"scrambled": "TEKBSA", "answer": "BASKET"}, {"scrambled": "YEKMON", "answer": "MONKEY"},
    {"scrambled": "TIBBAR", "answer": "RABBIT"}, {"scrambled": "REWOLF", "answer": "FLOWER"},
    {"scrambled": "ELTSAC", "answer": "CASTLE"}, {"scrambled": "EGDIRB", "answer": "BRIDGE"},
    {"scrambled": "TSEFOR", "answer": "FOREST"}, {"scrambled": "DNALSI", "answer": "ISLAND"},
    {"scrambled": "ELGNUJ", "answer": "JUNGLE"}, {"scrambled": "NEHCTIK", "answer": "KITCHEN"},
    {"scrambled": "YRBRALI", "answer": "LIBRARY"}, {"scrambled": "MUESUM", "answer": "MUSEUM"},
    {"scrambled": "DICHRO", "answer": "ORCHID"}, {"scrambled": "ECLAPA", "answer": "PALACE"},
    {"scrambled": "REVIR", "answer": "RIVER"}, {"scrambled": "TEKCOR", "answer": "ROCKET"},
    {"scrambled": "LADNAS", "answer": "SANDAL"}, {"scrambled": "ELTRUT", "answer": "TURTLE"},
    {"scrambled": "ALLEBRMU", "answer": "UMBRELLA"}, {"scrambled": "NOITACAV", "answer": "VACATION"}
]

def generate_qr_code(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# ==========================================
# HTML TEMPLATES
# ==========================================

MENU_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Game Hub</title>
    <style>
        body { background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%); color: white; font-family: 'Segoe UI', sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
        h1 { font-size: 64px; margin-bottom: 50px; background: linear-gradient(90deg, #ef4444, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
        .menu-container { display: flex; gap: 40px; }
        .game-card { background: linear-gradient(145deg, #1e1e2e, #2a2a3e); padding: 40px; border-radius: 20px; width: 300px; text-align: center; cursor: pointer; transition: all 0.3s; text-decoration: none; color: white; border: 2px solid transparent; }
        .game-card:hover { transform: translateY(-10px); border-color: #f97316; box-shadow: 0 10px 30px rgba(249, 115, 22, 0.3); }
        .game-card h2 { font-size: 32px; margin-bottom: 15px; }
        .game-card p { color: #9ca3af; font-size: 18px; }
        .icon { font-size: 80px; margin-bottom: 20px; display: block; }
    </style>
</head>
<body>
    <h1>🎮 CHOOSE YOUR GAME</h1>
    <div class="menu-container">
        <a href="/select/survival" class="game-card">
            <span class="icon">🔪</span>
            <h2>SURVIVAL</h2>
            <p>Blend in or get eliminated. Vote out the outliers!</p>
        </a>
        <a href="/select/jumble" class="game-card">
            <span class="icon">🔤</span>
            <h2>JUMBLE RACE</h2>
            <p>Unscramble words fast. First to 5 points wins!</p>
        </a>
    </div>
</body>
</html>
"""

SURVIVAL_HOST_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Survival Host</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        body { background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%); color: white; font-family: 'Segoe UI', sans-serif; padding: 30px; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 2px solid rgba(239, 68, 68, 0.3); padding-bottom: 20px; }
        h1 { color: #ef4444; font-size: 40px; margin: 0; }
        .grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 30px; }
        .card { background: #1e1e2e; padding: 25px; border-radius: 15px; margin-bottom: 25px; }
        input { padding: 15px; background: #333; color: white; border: 2px solid #444; border-radius: 10px; width: 100%; font-size: 16px; margin-bottom: 15px; box-sizing: border-box;}
        button { padding: 14px 28px; border: none; border-radius: 10px; color: white; cursor: pointer; font-size: 16px; font-weight: bold; margin-right: 10px; }
        .btn-green { background: #16a34a; } .btn-yellow { background: #ca8a04; } .btn-reveal { background: #2563eb; width: 100%; margin-top: 10px; font-size: 20px;} .btn-qr { background: #7c3aed; } .btn-back { background: #4b5563; }
        .cluster { background: #2a2a3e; padding: 20px; border-radius: 12px; margin-bottom: 15px; cursor: pointer; }
        .cluster:hover { background: #3a3a4e; }
        .badge { background: #dc2626; padding: 5px 12px; border-radius: 20px; font-weight: bold; float: right;}
        #playerList { list-style-type: none; padding: 0; }
        #playerList li { padding: 10px; background: rgba(255,255,255,0.05); margin-bottom: 8px; border-radius: 8px; display: flex; justify-content: space-between;}
        .locked-box { text-align: center; padding: 40px; background: #1a1a2e; border-radius: 15px; border: 2px dashed #4b5563; }
    </style>
</head>
<body>
    <div class="top-bar">
        <h1>🔪 SURVIVAL HOST</h1>
        <div>
            <button class="btn-qr" onclick="window.open('/qr', '_blank')">📱 Show QR</button>
            <a href="/" style="text-decoration:none;"><button class="btn-back">🏠 Back to Menu</button></a>
        </div>
    </div>
    <div class="grid">
        <div>
            <div class="card">
                <h2>Controls</h2>
                <input type="text" id="questionInput" placeholder="Type your question...">
                <button class="btn-green" onclick="startRound()">Start Round</button>
                <button class="btn-yellow" id="lockBtn" onclick="lockAnswers()" style="display:none;">🔒 LOCK</button>
                <button class="btn-reveal" id="revealBtn" onclick="revealAnswers()" style="display:none;">🔓 REVEAL</button>
            </div>
            <div class="card">
                <h2>Players (<span id="aliveCount">0</span>)</h2>
                <div id="answerCounter" style="font-size: 24px; color: #facc15; text-align: center; display: none;">0/0</div>
                <ul id="playerList"></ul>
            </div>
        </div>
        <div class="card">
            <h2>Answer Clusters (Click to Eliminate)</h2>
            <div id="answerClusters">
                <div class="locked-box"><h2>🔒 Answers Hidden</h2><p>Start a round to begin.</p></div>
            </div>
        </div>
    </div>
    <script>
        const socket = io();
        let roundInProgress = false;
        socket.on('update_players', (data) => {
            const list = document.getElementById('playerList'); list.innerHTML = ''; let aliveCount = 0;
            data.forEach(p => {
                if(p.status === 'alive') aliveCount++;
                const icon = p.status === 'alive' ? '✅' : '💀';
                list.innerHTML += `<li class="${p.status}"><span>${p.name}</span><span>${icon}</span></li>`;
            });
            document.getElementById('aliveCount').innerText = aliveCount;
        });
        socket.on('update_answer_status', (data) => {
            const list = document.getElementById('playerList'); list.innerHTML = ''; let answeredCount = 0; let aliveCount = 0;
            data.forEach(p => {
                if(p.status === 'alive') {
                    aliveCount++; if(p.answered) answeredCount++;
                    const icon = p.answered ? '✅' : '⏳';
                    list.innerHTML += `<li><span>${p.name}</span><span>${icon}</span></li>`;
                } else { list.innerHTML += `<li style="opacity:0.5"><span>${p.name}</span><span>💀</span></li>`; }
            });
            document.getElementById('aliveCount').innerText = aliveCount;
            if(roundInProgress) {
                document.getElementById('answerCounter').style.display = 'block';
                document.getElementById('answerCounter').innerText = `${answeredCount} / ${aliveCount} answered`;
            }
        });
        socket.on('answers_locked', () => {
            setTimeout(() => {
                document.getElementById('lockBtn').style.display = 'none';
                document.getElementById('revealBtn').style.display = 'block';
                document.getElementById('answerClusters').innerHTML = '<div class="locked-box"><h2>🔓 Locked!</h2><p>Click REVEAL to see clusters.</p></div>';
            }, 1500);
        });
        socket.on('reveal_answers', (data) => {
            const container = document.getElementById('answerClusters'); container.innerHTML = '';
            document.getElementById('revealBtn').style.display = 'none';
            const sorted = Object.entries(data).sort((a, b) => b[1].length - a[1].length);
            sorted.forEach(([answer, names]) => {
                const div = document.createElement('div'); div.className = 'cluster';
                div.onclick = () => { if(confirm(`Eliminate ${names.length} players?`)) socket.emit('survival_eliminate', {names: names}); };
                div.innerHTML = `<div style="display:flex; justify-content:space-between;"><span style="font-size:20px; font-weight:bold;">"${answer}"</span><span class="badge">${names.length}x</span></div><p style="color:#9ca3af; margin-top:10px;">${names.join(', ')}</p>`;
                container.appendChild(div);
            });
        });
        function startRound() {
            const q = document.getElementById('questionInput').value;
            if(q) { socket.emit('survival_start_round', {question: q}); roundInProgress = true; document.getElementById('lockBtn').style.display = 'block'; document.getElementById('answerClusters').innerHTML = '<div class="locked-box"><h2>🔒 Collecting...</h2></div>'; }
        }
        function lockAnswers() { socket.emit('survival_lock_answers'); document.getElementById('answerClusters').innerHTML = '<div class="locked-box"><h2>⏳ Locking...</h2></div>'; }
        function revealAnswers() { socket.emit('survival_reveal_answers'); }
    </script>
</body>
</html>
"""

JUMBLE_HOST_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Jumble Host</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        body { background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%); color: white; font-family: 'Segoe UI', sans-serif; padding: 30px; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 2px solid rgba(249, 115, 22, 0.3); padding-bottom: 20px; }
        h1 { color: #f97316; font-size: 40px; margin: 0; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
        .card { background: #1e1e2e; padding: 25px; border-radius: 15px; }
        button { padding: 14px 28px; border: none; border-radius: 10px; color: white; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; margin-bottom: 10px; }
        .btn-green { background: #16a34a; } .btn-red { background: #dc2626; } .btn-qr { background: #7c3aed; width: auto; padding: 10px 20px;} .btn-back { background: #4b5563; width: auto; padding: 10px 20px;}
        .word-display { text-align: center; padding: 40px; background: rgba(255,255,255,0.05); border-radius: 15px; margin-bottom: 20px; }
        .jumbled-word { font-size: 64px; font-weight: 900; letter-spacing: 10px; color: #facc15; }
        .leaderboard-item { display: flex; justify-content: space-between; padding: 15px; background: rgba(255,255,255,0.03); border-radius: 10px; margin-bottom: 10px; font-size: 20px; }
        .score { font-weight: 900; color: #facc15; }
        .winner-row { display: flex; justify-content: space-between; padding: 12px; background: rgba(250, 204, 21, 0.1); border-radius: 8px; margin-bottom: 8px; border-left: 4px solid #facc15; }
    </style>
</head>
<body>
    <div class="top-bar">
        <h1>🔤 JUMBLE RACE HOST</h1>
        <div>
            <button class="btn-qr" onclick="window.open('/qr', '_blank')">📱 Show QR</button>
            <a href="/" style="text-decoration:none;"><button class="btn-back">🏠 Back to Menu</button></a>
        </div>
    </div>
    <div class="grid">
        <div class="card">
            <h2>Current Word</h2>
            <div class="word-display"><div class="jumbled-word" id="jumbledWord">???</div></div>
            <button class="btn-green" id="nextBtn" onclick="socket.emit('jumble_next_word')">NEXT WORD</button>
            <button class="btn-red" onclick="socket.emit('jumble_reset_game')">RESET GAME</button>
        </div>
        <div>
            <div class="card" style="margin-bottom: 20px;">
                <h2>🏆 Leaderboard</h2>
                <div id="leaderboard"></div>
            </div>
            <div class="card">
                <h2>🥇 Winners Podium</h2>
                <div id="podiumList"><p style="color:#9ca3af;">First 3 to 5 points win!</p></div>
            </div>
        </div>
    </div>
    <script>
        const socket = io();
        socket.on('update_word', (data) => { document.getElementById('jumbledWord').innerText = data.scrambled; });
        socket.on('update_leaderboard', (data) => {
            const lb = document.getElementById('leaderboard'); lb.innerHTML = '';
            const sorted = data.players.sort((a, b) => b.score - a.score);
            sorted.forEach(p => { lb.innerHTML += `<div class="leaderboard-item"><span>${p.name}</span><span class="score">${p.score}</span></div>`; });
            const podium = document.getElementById('podiumList'); podium.innerHTML = '';
            data.winners.forEach((w, i) => {
                const medals = ['🥇 1st', '🥈 2nd', '🥉 3rd'];
                podium.innerHTML += `<div class="winner-row"><span>${medals[i]} ${w.name}</span><span class="score">${w.score}</span></div>`;
            });
            document.getElementById('nextBtn').disabled = (data.winners.length === 3);
            document.getElementById('nextBtn').innerText = data.winners.length === 3 ? "GAME OVER" : "NEXT WORD";
        });
        <script>
        const socket = io();
        let myName = "";

        // Helper to create a secret ID card
        function getOrCreatePlayerId() {
            let id = localStorage.getItem('jumble_player_id');
            if (!id) {
                id = 'player_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem('jumble_player_id', id);
            }
            return id;
        }

        window.onload = function() {
            const savedName = localStorage.getItem('jumble_player_name');
            if(savedName) {
                myName = savedName;
                const playerId = getOrCreatePlayerId();
                socket.emit('jumble_join', {name: myName, player_id: playerId}); // Send ID!
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('gameScreen').classList.remove('hidden');
            }
        };

        function joinGame() {
            myName = document.getElementById('nameInput').value.trim();
            if(myName) {
                localStorage.setItem('jumble_player_name', myName);
                const playerId = getOrCreatePlayerId();
                socket.emit('jumble_join', {name: myName, player_id: playerId}); // Send ID!
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('gameScreen').classList.remove('hidden');
            }
        }

        function changeName() {
            localStorage.removeItem('jumble_player_name');
            localStorage.removeItem('jumble_player_id'); // Clear ID card too
            myName = "";
            document.getElementById('joinScreen').classList.remove('hidden');
            document.getElementById('gameScreen').classList.add('hidden');
            document.getElementById('winScreen').classList.add('hidden');
            document.getElementById('nameInput').value = "";
        }

        function submitGuess() {
            const guess = document.getElementById('guessInput').value.trim().toUpperCase();
            if(guess) {
                socket.emit('jumble_submit_guess', {guess: guess});
                document.getElementById('guessInput').value = "";
            }
        }

        document.getElementById('guessInput').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') submitGuess();
        });

        socket.on('update_word', (data) => {
            document.getElementById('playerWord').innerText = data.scrambled;
            document.getElementById('feedback').innerText = "";
            document.getElementById('guessInput').disabled = false;
            document.getElementById('guessInput').focus();
        });

        socket.on('update_my_score', (data) => {
            document.getElementById('myScore').innerText = data.score;
            if(data.won) {
                document.getElementById('gameScreen').classList.add('hidden');
                document.getElementById('winScreen').classList.remove('hidden');
            }
        });

        socket.on('guess_result', (data) => {
            const fb = document.getElementById('feedback');
            fb.innerText = data.correct ? "✅ Correct! +1" : "❌ Wrong!";
            fb.style.color = data.correct ? "#4ade80" : "#f87171";
        });
    </script>
</body>
</html>
"""

SURVIVAL_PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Survival Player</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        body { background: #111; color: white; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 10: 100vh; padding: 20px; text-align: center; }
        h1 { color: #ef4444; font-size: 48px; }
        input { padding: 15px; background: #333; color: white; border: none; border-radius: 10px; width: 100%; max-width: 300px; font-size: 18px; margin-bottom: 15px; text-align: center;}
        button { padding: 15px 30px; border: none; border-radius: 10px; color: white; cursor: pointer; font-size: 20px; font-weight: bold; width: 100%; max-width: 300px; }
        .btn-green { background: #16a34a; } .btn-blue { background: #2563eb; } .btn-gray { background: #6b7280; margin-top: 10px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div id="joinScreen">
        <h1>SURVIVAL</h1>
        <input type="text" id="nameInput" placeholder="Enter your name...">
        <br><br>
        <button class="btn-green" onclick="joinGame()">JOIN</button>
    </div>
    <div id="waitingScreen" class="hidden">
        <h2>Welcome, <span id="playerName"></span>!</h2>
        <p style="color:#9ca3af;">Waiting for host...</p>
        <button class="btn-gray" onclick="changeName()" style="margin-top:20px;">🔄 Change Name</button>
    </div>
    <div id="answerScreen" class="hidden" style="width:100%; max-width:400px;">
        <h2 style="color:#facc15;" id="questionText"></h2>
        <input type="text" id="answerInput" placeholder="Your answer...">
        <br><button class="btn-blue" onclick="submitAnswer()">SUBMIT</button>
        <p id="answerStatus" style="margin-top:15px; color:#9ca3af;"></p>
        <p id="tensionCounter" style="font-size:24px; color:#facc15; margin-top:20px; display:none;"></p>
    </div>
    <div id="eliminatedScreen" class="hidden">
        <h1 style="font-size:60px;">💀 ELIMINATED 💀</h1>
        <button class="btn-gray" onclick="changeName()" style="margin-top:20px;">🔄 Play Again with New Name</button>
    </div>
    <script>
        const socket = io();
        let myName = "";

        // Check if there's a saved name in localStorage
        window.onload = function() {
            const savedName = localStorage.getItem('survival_player_name');
            if(savedName) {
                myName = savedName;
                socket.emit('survival_join', {name: myName});
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('waitingScreen').classList.remove('hidden');
                document.getElementById('playerName').innerText = myName;
            }
        };

        function joinGame() {
            myName = document.getElementById('nameInput').value.trim();
            if(myName) {
                // Save name to localStorage
                localStorage.setItem('survival_player_name', myName);
                socket.emit('survival_join', {name: myName});
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('waitingScreen').classList.remove('hidden');
                document.getElementById('playerName').innerText = myName;
            }
        }

        function changeName() {
            // Clear saved name
            localStorage.removeItem('survival_player_name');
            myName = "";
            document.getElementById('joinScreen').classList.remove('hidden');
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('answerScreen').classList.add('hidden');
            document.getElementById('eliminatedScreen').classList.add('hidden');
            document.getElementById('nameInput').value = "";
        }

        function submitAnswer() {
            const ans = document.getElementById('answerInput').value;
            if(ans) {
                socket.emit('survival_submit_answer', {answer: ans});
                document.getElementById('answerStatus').innerText = "✅ Locked in!";
                document.getElementById('answerInput').disabled = true;
            }
        }

        socket.on('round_started', (data) => {
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('answerScreen').classList.remove('hidden');
            document.getElementById('questionText').innerText = data.question;
            document.getElementById('answerStatus').innerText = "";
            document.getElementById('answerInput').disabled = false;
            document.getElementById('answerInput').value = "";
        });

        socket.on('answer_count_update', (data) => {
            const c = document.getElementById('tensionCounter');
            c.style.display = 'block';
            c.innerText = `${data.count} / ${data.total} answered`;
        });

        socket.on('round_locked', () => {
            document.getElementById('answerStatus').innerText = "Host reviewing...";
            document.getElementById('tensionCounter').style.display = 'none';
        });

        socket.on('eliminated', () => {
            document.getElementById('answerScreen').classList.add('hidden');
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('eliminatedScreen').classList.remove('hidden');
        });
        <script>
        const socket = io(); 
        let myName = "";

        // Helper to create a secret ID card
        function getOrCreatePlayerId() {
            let id = localStorage.getItem('survival_player_id');
            if (!id) {
                id = 'player_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem('survival_player_id', id);
            }
            return id;
        }

        window.onload = function() {
            const savedName = localStorage.getItem('survival_player_name');
            if(savedName) {
                myName = savedName;
                const playerId = getOrCreatePlayerId();
                socket.emit('survival_join', {name: myName, player_id: playerId}); // Send ID!
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('waitingScreen').classList.remove('hidden');
                document.getElementById('playerName').innerText = myName;
            }
        };

        function joinGame() {
            myName = document.getElementById('nameInput').value;
            if(myName) {
                localStorage.setItem('survival_player_name', myName);
                const playerId = getOrCreatePlayerId();
                socket.emit('survival_join', {name: myName, player_id: playerId}); // Send ID!
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('waitingScreen').classList.remove('hidden');
                document.getElementById('playerName').innerText = myName;
            }
        }

        function changeName() {
            localStorage.removeItem('survival_player_name');
            localStorage.removeItem('survival_player_id'); // Clear ID card too
            myName = "";
            document.getElementById('joinScreen').classList.remove('hidden');
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('answerScreen').classList.add('hidden');
            document.getElementById('eliminatedScreen').classList.add('hidden');
            document.getElementById('nameInput').value = "";
        }

        function submitAnswer() {
            const ans = document.getElementById('answerInput').value;
            if(ans) {
                socket.emit('survival_submit_answer', {answer: ans});
                document.getElementById('answerStatus').innerText = "✅ Locked in!";
                document.getElementById('answerInput').disabled = true;
            }
        }

        socket.on('round_started', (data) => {
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('answerScreen').classList.remove('hidden');
            document.getElementById('questionText').innerText = data.question;
            document.getElementById('answerStatus').innerText = "";
            document.getElementById('answerInput').disabled = false;
            document.getElementById('answerInput').value = "";
        });

        socket.on('answer_count_update', (data) => {
            const c = document.getElementById('tensionCounter');
            c.style.display = 'block';
            c.innerText = `${data.count} / ${data.total} answered`;
        });

        socket.on('round_locked', () => {
            document.getElementById('answerStatus').innerText = "Host reviewing...";
            document.getElementById('tensionCounter').style.display = 'none';
        });

        socket.on('eliminated', () => {
            document.getElementById('answerScreen').classList.add('hidden');
            document.getElementById('waitingScreen').classList.add('hidden');
            document.getElementById('eliminatedScreen').classList.remove('hidden');
        });
    </script>
</body>
</html>
"""

JUMBLE_PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Jumble Player</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        body { background: #111; color: white; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; text-align: center; }
        h1 { color: #f97316; font-size: 48px; }
        input { padding: 15px; background: #333; color: white; border: none; border-radius: 10px; width: 100%; max-width: 300px; font-size: 20px; margin-bottom: 15px; text-align: center; text-transform: uppercase;}
        button { padding: 15px 30px; border: none; border-radius: 10px; color: white; cursor: pointer; font-size: 20px; font-weight: bold; width: 100%; max-width: 300px; }
        .btn-green { background: #16a34a; } .btn-blue { background: #2563eb; } .btn-gray { background: #6b7280; margin-top: 10px; }
        .hidden { display: none; }
        .word-box { font-size: 48px; font-weight: 900; letter-spacing: 8px; color: #facc15; margin: 20px 0; }
        .my-score { font-size: 24px; color: #4ade80; margin-top: 20px; }
        .feedback { margin-top: 15px; font-size: 18px; min-height: 24px; }
    </style>
</head>
<body>
    <div id="joinScreen">
        <h1>JUMBLE RACE</h1>
        <input type="text" id="nameInput" placeholder="Enter your name..." style="text-transform:none;">
        <br><br>
        <button class="btn-green" onclick="joinGame()">JOIN</button>
    </div>
    <div id="gameScreen" class="hidden">
        <h2 style="color:#9ca3af;">Unscramble:</h2>
        <div class="word-box" id="playerWord">???</div>
        <input type="text" id="guessInput" placeholder="Your guess..." autocomplete="off">
        <br><button class="btn-blue" onclick="submitGuess()">SUBMIT</button>
        <p class="feedback" id="feedback"></p>
        <div class="my-score">Score: <span id="myScore">0</span> / 5</div>
        <button class="btn-gray" onclick="changeName()" style="margin-top:20px;">🔄 Change Name</button>
    </div>
    <div id="winScreen" class="hidden">
        <h1 style="font-size:60px;">🏆 YOU WIN! 🏆</h1>
        <button class="btn-gray" onclick="changeName()" style="margin-top:20px;">🔄 Play Again with New Name</button>
    </div>
    <script>
        const socket = io();
        let myName = "";

        // Check if there's a saved name in localStorage
        window.onload = function() {
            const savedName = localStorage.getItem('jumble_player_name');
            if(savedName) {
                myName = savedName;
                socket.emit('jumble_join', {name: myName});
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('gameScreen').classList.remove('hidden');
            }
        };

        function joinGame() {
            myName = document.getElementById('nameInput').value.trim();
            if(myName) {
                // Save name to localStorage
                localStorage.setItem('jumble_player_name', myName);
                socket.emit('jumble_join', {name: myName});
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('gameScreen').classList.remove('hidden');
            }
        }

        function changeName() {
            // Clear saved name
            localStorage.removeItem('jumble_player_name');
            myName = "";
            document.getElementById('joinScreen').classList.remove('hidden');
            document.getElementById('gameScreen').classList.add('hidden');
            document.getElementById('winScreen').classList.add('hidden');
            document.getElementById('nameInput').value = "";
        }

        function submitGuess() {
            const guess = document.getElementById('guessInput').value.trim().toUpperCase();
            if(guess) {
                socket.emit('jumble_submit_guess', {guess: guess});
                document.getElementById('guessInput').value = "";
            }
        }

        document.getElementById('guessInput').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') submitGuess();
        });

        socket.on('update_word', (data) => {
            document.getElementById('playerWord').innerText = data.scrambled;
            document.getElementById('feedback').innerText = "";
            document.getElementById('guessInput').disabled = false;
            document.getElementById('guessInput').focus();
        });

        socket.on('update_my_score', (data) => {
            document.getElementById('myScore').innerText = data.score;
            if(data.won) {
                document.getElementById('gameScreen').classList.add('hidden');
                document.getElementById('winScreen').classList.remove('hidden');
            }
        });

        socket.on('guess_result', (data) => {
            const fb = document.getElementById('feedback');
            fb.innerText = data.correct ? "✅ Correct! +1" : "❌ Wrong!";
            fb.style.color = data.correct ? "#4ade80" : "#f87171";
        });
    </script>
</body>
</html>
"""

QR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Scan to Join</title>
    <style>
        body { background: #111; color: white; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; text-align: center; }
        h1 { color: #ef4444; font-size: 48px; margin-bottom: 30px; }
        .qr-container { background: white; padding: 30px; border-radius: 20px; }
        .qr-container img { width: 350px; height: 350px; }
        .url-text { font-family: monospace; font-size: 20px; color: #9ca3af; margin-top: 20px; }
        .btn-back { margin-top: 30px; padding: 10px 20px; background: #4b5563; color: white; text-decoration: none; border-radius: 10px; }
    </style>
</head>
<body>
    <h1>📱 SCAN TO JOIN {{ game_name }}</h1>
    <div class="qr-container"><img src="{{ qr_code }}" alt="QR Code"></div>
    <p class="url-text">{{ player_url }}</p>
    <a href="/" class="btn-back">🏠 Back to Menu</a>
</body>
</html>
"""

# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def menu():
    global active_game
    active_game = None
    return render_template_string(MENU_HTML)

@app.route('/select/<game>')
def select_game(game):
    global active_game
    if game in ['survival', 'jumble']:
        active_game = game
    return redirect('/host')

@app.route('/host')
def host_dashboard():
    if active_game == 'survival':
        return render_template_string(SURVIVAL_HOST_HTML)
    elif active_game == 'jumble':
        return render_template_string(JUMBLE_HOST_HTML)
    return redirect('/')

@app.route('/qr')
def qr_page():
    host = request.host
    scheme = request.scheme
    if active_game == 'survival':
        player_url = f"{scheme}://{host}/play/survival"
        game_name = "SURVIVAL"
    elif active_game == 'jumble':
        player_url = f"{scheme}://{host}/play/jumble"
        game_name = "JUMBLE RACE"
    else:
        player_url = f"{scheme}://{host}/"
        game_name = ""
        
    qr_code = generate_qr_code(player_url)
    return render_template_string(QR_HTML, qr_code=qr_code, player_url=player_url, game_name=game_name)

@app.route('/play/survival')
def play_survival():
    return render_template_string(SURVIVAL_PLAYER_HTML)

@app.route('/play/jumble')
def play_jumble():
    return render_template_string(JUMBLE_PLAYER_HTML)

# ==========================================
# SOCKETIO EVENTS - SURVIVAL
# ==========================================

@socketio.on('survival_join')
def survival_handle_join(data):
    if active_game != 'survival': return
    sid = request.sid
    name = data['name']
    player_id = data.get('player_id') # Get the secret ID card

    # Check if this player_id already exists
    existing_sid = None
    for s, p in survival_players.items():
        if p.get('player_id') == player_id:
            existing_sid = s
            break

    if existing_sid:
        # Player is reloading! Move their data to the new connection
        player_data = survival_players.pop(existing_sid)
        survival_players[sid] = player_data
    else:
        # Brand new player
        survival_players[sid] = {'name': name, 'status': 'alive', 'answer': '', 'player_id': player_id}
        
    survival_broadcast_players()
    survival_broadcast_answer_status()

@socketio.on('survival_start_round')
def survival_handle_start(data):
    if active_game != 'survival': return
    global survival_question, survival_round_active, survival_answers_locked
    survival_question = data['question']
    survival_round_active = True
    survival_answers_locked = False
    for sid, p in survival_players.items():
        if p['status'] == 'alive': p['answer'] = ''
    emit('round_started', {'question': survival_question}, broadcast=True)
    survival_broadcast_answer_status()

@socketio.on('survival_submit_answer')
def survival_handle_answer(data):
    if active_game != 'survival' or survival_answers_locked: return
    sid = request.sid
    if sid in survival_players and survival_players[sid]['status'] == 'alive':
        survival_players[sid]['answer'] = data['answer'].strip().lower()
        survival_broadcast_answer_status()

@socketio.on('survival_lock_answers')
def survival_handle_lock():
    if active_game != 'survival': return
    global survival_answers_locked
    survival_answers_locked = True
    emit('answers_locked', broadcast=True)
    survival_broadcast_answer_status()

@socketio.on('survival_reveal_answers')
def survival_handle_reveal():
    if active_game != 'survival': return
    global survival_answers_locked
    survival_answers_locked = True
    emit('round_locked', broadcast=True)
    answer_groups = {}
    for p in survival_players.values():
        if p['status'] == 'alive' and p['answer']:
            ans = p['answer']
            if ans not in answer_groups: answer_groups[ans] = []
            answer_groups[ans].append(p['name'])
    emit('reveal_answers', answer_groups, broadcast=True)

@socketio.on('survival_eliminate')
def survival_handle_eliminate(data):
    if active_game != 'survival': return
    for sid, p in survival_players.items():
        if p['name'] in data['names']:
            p['status'] = 'eliminated'
            emit('eliminated', room=sid)
    survival_broadcast_players()
    survival_broadcast_answer_status()

def survival_broadcast_players():
    player_list = [{'name': p['name'], 'status': p['status']} for p in survival_players.values()]
    emit('update_players', player_list, broadcast=True)

def survival_broadcast_answer_status():
    status_list = [{'name': p['name'], 'status': p['status'], 'answered': bool(p['answer'])} for p in survival_players.values()]
    emit('update_answer_status', status_list, broadcast=True)
    alive = [p for p in survival_players.values() if p['status'] == 'alive']
    answered = sum(1 for p in alive if p['answer'])
    emit('answer_count_update', {'count': answered, 'total': len(alive)}, broadcast=True)

# ==========================================
# SOCKETIO EVENTS - JUMBLE
# ==========================================

@socketio.on('jumble_join')
def jumble_handle_join(data):
    if active_game != 'jumble': return
    sid = request.sid
    name = data['name'].strip()
    player_id = data.get('player_id') # Get the secret ID card

    # Check if this player_id already exists in our dictionary
    existing_sid = None
    for s, p in jumble_players.items():
        if p.get('player_id') == player_id:
            existing_sid = s
            break

    if existing_sid:
        # Player is reloading! Move their data to the new connection
        player_data = jumble_players.pop(existing_sid)
        jumble_players[sid] = player_data
    else:
        # Brand new player
        jumble_players[sid] = {'name': name, 'score': 0, 'rank': None, 'player_id': player_id}

    jumble_broadcast_leaderboard()
    if jumble_current_scrambled:
        emit('update_word', {'scrambled': jumble_current_scrambled}, room=sid)

@socketio.on('jumble_next_word')
def jumble_handle_next_word():
    if active_game != 'jumble': return
    global jumble_current_scrambled, jumble_current_answer, jumble_round_active, jumble_answered_this_round
    if len(jumble_winners) >= JUMBLE_MAX_WINNERS: return
    jumble_round_active = True
    jumble_answered_this_round = []
    new_word = random.choice(JUMBLE_WORD_LIST)
    while new_word['scrambled'] == jumble_current_scrambled and len(JUMBLE_WORD_LIST) > 1:
        new_word = random.choice(JUMBLE_WORD_LIST)
    jumble_current_scrambled = new_word['scrambled']
    jumble_current_answer = new_word['answer']
    emit('update_word', {'scrambled': jumble_current_scrambled}, broadcast=True)

@socketio.on('jumble_submit_guess')
def jumble_handle_guess(data):
    if active_game != 'jumble' or not jumble_round_active or len(jumble_winners) >= JUMBLE_MAX_WINNERS: return
    sid = request.sid
    if sid not in jumble_players or sid in jumble_answered_this_round: return
    guess = data['guess'].strip().upper()
    if guess == jumble_current_answer:
        jumble_players[sid]['score'] += 1
        jumble_answered_this_round.append(sid)
        emit('guess_result', {'correct': True}, room=sid)
        if jumble_players[sid]['score'] >= JUMBLE_TARGET_SCORE and jumble_players[sid]['rank'] is None:
            jumble_players[sid]['rank'] = f"{len(jumble_winners) + 1}"
            jumble_winners.append(jumble_players[sid])
            emit('update_my_score', {'score': jumble_players[sid]['score'], 'won': True}, room=sid)
        else:
            emit('update_my_score', {'score': jumble_players[sid]['score'], 'won': False}, room=sid)
        jumble_broadcast_leaderboard()
    else:
        emit('guess_result', {'correct': False}, room=sid)

@socketio.on('jumble_reset_game')
def jumble_handle_reset():
    if active_game != 'jumble': return
    global jumble_winners, jumble_current_scrambled, jumble_round_active
    for sid in jumble_players:
        jumble_players[sid]['score'] = 0
        jumble_players[sid]['rank'] = None
    jumble_winners = []
    jumble_current_scrambled = ""
    jumble_round_active = False
    jumble_broadcast_leaderboard()
    emit('update_word', {'scrambled': "???"}, broadcast=True)
    for sid in jumble_players:
        emit('update_my_score', {'score': 0, 'won': False}, room=sid)

def jumble_broadcast_leaderboard():
    player_list = [{'name': p['name'], 'score': p['score'], 'rank': p['rank']} for p in jumble_players.values()]
    winner_list = [{'name': w['name'], 'score': w['score']} for w in jumble_winners]
    emit('update_leaderboard', {'players': player_list, 'winners': winner_list}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
