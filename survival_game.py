from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit
from collections import Counter
import socket
import qrcode
import base64
from io import BytesIO
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'survival_secret')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') 

players = {}       
current_question = ""
round_active = False
answers_locked = False
answers_revealed = False

def generate_qr_code(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def get_player_url():
    # Check if running in production (Railway/cloud)
    railway_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if railway_url:
        return f"https://{railway_url}/play"
    
    # Fallback to local IP for development
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    return f"http://{local_ip}:5000/play"

# [Keep all the HOST_HTML, QR_HTML, and PLAYER_HTML from before - they stay the same]
# I'll include them in the next message since the code is very long

HOST_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Host Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%); 
            color: white; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            padding: 30px;
            min-height: 100vh;
        }
        
        h1 { 
            background: linear-gradient(90deg, #ef4444, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 48px;
            font-weight: 900;
            letter-spacing: 2px;
        }
        
        .top-bar { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(239, 68, 68, 0.3);
        }
        
        .connection-status {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            font-size: 14px;
        }
        
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #4ade80;
            animation: pulse 2s infinite;
        }
        
        .status-dot.disconnected {
            background: #ef4444;
            animation: none;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 10px #4ade80; }
            50% { opacity: 0.6; box-shadow: 0 0 5px #4ade80; }
        }
        
        .grid { 
            display: grid; 
            grid-template-columns: 1fr 1.5fr; 
            gap: 30px;
        }
        
        .card { 
            background: linear-gradient(145deg, #1e1e2e, #2a2a3e);
            padding: 25px; 
            border-radius: 15px; 
            margin-bottom: 25px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .card h2 {
            color: #f97316;
            font-size: 24px;
            margin-bottom: 20px;
        }
        
        input { 
            padding: 15px; 
            background: rgba(255, 255, 255, 0.05);
            color: white; 
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px; 
            width: 100%; 
            font-size: 16px;
            margin-bottom: 15px;
        }
        
        button { 
            padding: 14px 28px; 
            border: none; 
            border-radius: 10px; 
            color: white; 
            cursor: pointer; 
            font-size: 16px; 
            font-weight: bold;
            margin-right: 10px;
            transition: all 0.3s;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
        }
        
        .btn-green { background: linear-gradient(135deg, #16a34a, #22c55e); }
        .btn-yellow { background: linear-gradient(135deg, #ca8a04, #eab308); }
        .btn-reveal { 
            background: linear-gradient(135deg, #2563eb, #3b82f6);
            font-size: 22px;
            padding: 18px 35px;
            width: 100%;
            margin-top: 15px;
        }
        .btn-qr { background: linear-gradient(135deg, #7c3aed, #a855f7); }
        
        .cluster { 
            background: linear-gradient(145deg, #2a2a3e, #3a3a4e);
            padding: 20px; 
            border-radius: 12px; 
            margin-bottom: 15px; 
            cursor: pointer; 
            transition: all 0.3s;
        }
        
        .cluster:hover { 
            transform: scale(1.02);
            box-shadow: 0 8px 25px rgba(239, 68, 68, 0.3);
        }
        
        .badge { 
            background: linear-gradient(135deg, #dc2626, #ef4444);
            padding: 8px 16px; 
            border-radius: 25px; 
            font-weight: bold;
        }
        
        .alive { color: #4ade80; }
        .dead { color: #f87171; text-decoration: line-through; }
        
        .locked-box { 
            text-align: center; 
            padding: 60px 40px; 
            background: linear-gradient(145deg, #1a1a2e, #2a2a3e);
            border-radius: 15px; 
            border: 2px dashed rgba(255, 255, 255, 0.2);
        }
        
        .locked-box .lock-icon { font-size: 80px; margin-bottom: 20px; }
        
        .counter { 
            font-size: 32px; 
            font-weight: 900; 
            color: #facc15;
            margin: 15px 0;
            text-align: center;
        }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4ade80, #22c55e);
            transition: width 0.5s ease-out;
        }
        
        .toast {
            position: fixed;
            top: 30px;
            right: 30px;
            background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
            color: white;
            padding: 20px 30px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
            border-left: 4px solid #f97316;
            z-index: 1000;
            max-width: 400px;
            animation: slideIn 0.3s;
        }
        
        @keyframes slideIn {
            from { transform: translateX(400px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        #playerList { list-style-type: none; }
        #playerList li {
            padding: 12px 15px;
            margin-bottom: 8px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="top-bar">
        <h1>🔪 SURVIVAL</h1>
        <div class="connection-status">
            <div class="status-dot" id="statusDot"></div>
            <span id="statusText">Connected</span>
        </div>
        <button class="btn-qr" onclick="window.open('/qr', '_blank')">📱 Show QR Code</button>
    </div>
    
    <div class="grid">
        <div>
            <div class="card">
                <h2>🎮 Game Controls</h2>
                <input type="text" id="questionInput" placeholder="Type your question...">
                <button class="btn-green" onclick="startRound()">Start Round</button>
                <button class="btn-yellow" id="lockBtn" onclick="lockAnswers()" style="display:none;">🔒 LOCK ANSWERS</button>
                <button class="btn-reveal" id="revealBtn" onclick="revealAnswers()" style="display:none;">🔓 REVEAL ANSWERS</button>
            </div>

            <div class="card">
                <h2>👥 Alive Players (<span id="aliveCount">0</span>)</h2>
                <div class="counter" id="answerCounter" style="display:none;">0 / 0 answered</div>
                <div class="progress-bar" id="progressBar" style="display:none;">
                    <div class="progress-fill" id="progressFill" style="width: 0%"></div>
                </div>
                <ul id="playerList"></ul>
            </div>
        </div>

        <div class="card">
            <h2>📊 Answer Clusters</h2>
            <p style="color: #9ca3af; margin-bottom: 20px;">Click a group to eliminate them.</p>
            <div id="answerClusters">
                <div class="locked-box">
                    <div class="lock-icon">🔒</div>
                    <p style="font-size: 24px; color: #9ca3af;">Answers are hidden</p>
                </div>
            </div>
        </div>
    </div>

    <div id="toastContainer"></div>

    <script>
        const socket = io();
        let roundInProgress = false;
        
        socket.on('connect', () => {
            document.getElementById('statusDot').classList.remove('disconnected');
            document.getElementById('statusText').textContent = 'Connected';
            showToast('✅ Connected to server');
        });
        
        socket.on('disconnect', () => {
            document.getElementById('statusDot').classList.add('disconnected');
            document.getElementById('statusText').textContent = 'Disconnected';
            showToast('❌ Lost connection! Refresh page.');
        });
        
        function showToast(message, duration = 3000) {
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.textContent = message;
            document.getElementById('toastContainer').appendChild(toast);
            setTimeout(() => toast.remove(), duration);
        }
        
        socket.on('host_alert', (data) => {
            showToast(data.msg);
        });
        
        socket.on('update_players', (data) => {
            const list = document.getElementById('playerList');
            list.innerHTML = '';
            let aliveCount = 0;
            data.forEach(p => {
                if(p.status === 'alive') aliveCount++;
                const cls = p.status === 'alive' ? 'alive' : 'dead';
                const icon = p.status === 'alive' ? '✅' : '💀';
                list.innerHTML += `<li class="${cls}">${p.name} ${icon}</li>`;
            });
            document.getElementById('aliveCount').innerText = aliveCount;
        });

        socket.on('update_answer_status', (data) => {
            const list = document.getElementById('playerList');
            list.innerHTML = '';
            let answeredCount = 0;
            let aliveCount = 0;
            
            data.forEach(p => {
                if(p.status === 'alive') {
                    aliveCount++;
                    if(p.answered) answeredCount++;
                    const checkIcon = p.answered ? '✅' : '⏳';
                    list.innerHTML += `<li class="alive" style="display: flex; justify-content: space-between;">
                        <span>${p.name}</span>
                        <span>${checkIcon}</span>
                    </li>`;
                } else {
                    list.innerHTML += `<li class="dead">${p.name} 💀</li>`;
                }
            });
            
            document.getElementById('aliveCount').innerText = aliveCount;
            
            if(roundInProgress) {
                document.getElementById('answerCounter').style.display = 'block';
                document.getElementById('answerCounter').innerText = `${answeredCount} / ${aliveCount} answered`;
                document.getElementById('progressBar').style.display = 'block';
                const percentage = aliveCount > 0 ? (answeredCount / aliveCount) * 100 : 0;
                document.getElementById('progressFill').style.width = percentage + '%';
            }
        });

        socket.on('answers_locked', () => {
            setTimeout(() => {
                document.getElementById('lockBtn').style.display = 'none';
                document.getElementById('revealBtn').style.display = 'block';
                document.getElementById('answerClusters').innerHTML = `
                    <div class="locked-box">
                        <div class="lock-icon">🔓</div>
                        <p style="font-size: 24px; color: #4ade80;">Answers locked!</p>
                        <p style="color: #9ca3af; margin-top: 15px;">Click "REVEAL ANSWERS" to see clusters</p>
                    </div>`;
                showToast('✅ All answers captured!');
            }, 2000);
        });

        socket.on('reveal_answers', (data) => {
            const container = document.getElementById('answerClusters');
            container.innerHTML = '';
            document.getElementById('revealBtn').style.display = 'none';
            
            const sorted = Object.entries(data).sort((a, b) => b[1].length - a[1].length);
            
            sorted.forEach(([answer, names]) => {
                const div = document.createElement('div');
                div.className = 'cluster';
                div.onclick = () => eliminateGroup(names);
                div.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 22px; font-weight: bold;">"${answer}"</span>
                        <span class="badge">${names.length}x</span>
                    </div>
                    <p style="color: #9ca3af; margin-top: 12px;">Players: ${names.join(', ')}</p>
                `;
                container.appendChild(div);
            });
            
            showToast('Answers revealed!');
        });

        function startRound() {
            const q = document.getElementById('questionInput').value;
            if(q) {
                socket.emit('start_round', {question: q});
                roundInProgress = true;
                document.getElementById('lockBtn').style.display = 'block';
                document.getElementById('revealBtn').style.display = 'none';
                document.getElementById('answerClusters').innerHTML = `
                    <div class="locked-box">
                        <div class="lock-icon">🔒</div>
                        <p style="font-size: 24px; color: #facc15;">Collecting answers...</p>
                    </div>`;
                showToast('Round started!');
            }
        }
        
        function lockAnswers() {
            socket.emit('lock_answers');
            document.getElementById('answerClusters').innerHTML = `
                <div class="locked-box">
                    <div class="lock-icon">⏳</div>
                    <p style="font-size: 24px; color: #facc15;">Locking answers...</p>
                </div>`;
            showToast('Locking answers...');
        }
        
        function revealAnswers() { 
            socket.emit('reveal_answers'); 
        }
        
        function eliminateGroup(names) {
            if(confirm(`Eliminate ${names.length} player(s)?`)) {
                socket.emit('eliminate', {names: names});
            }
        }
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
        body { 
            background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%);
            color: white; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            justify-content: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 20px; 
            box-sizing: border-box;
            text-align: center;
        }
        h1 { 
            background: linear-gradient(90deg, #ef4444, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 56px; 
            margin-bottom: 40px;
            font-weight: 900;
            letter-spacing: 3px;
        }
        .qr-container { 
            background: white; 
            padding: 40px; 
            border-radius: 25px; 
            box-shadow: 0 0 60px rgba(239, 68, 68, 0.4);
        }
        .qr-container img { 
            display: block;
            width: 450px; 
            height: 450px;
        }
        .url-text { 
            font-family: 'Courier New', monospace; 
            font-size: 28px; 
            color: #9ca3af; 
            margin-top: 40px; 
            word-break: break-all;
            max-width: 700px;
            font-weight: bold;
        }
        .instructions {
            font-size: 24px;
            color: #facc15;
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <h1>📱 SCAN TO JOIN</h1>
    <div class="qr-container">
        <img src="{{ qr_code }}" alt="QR Code">
    </div>
    <p class="url-text">{{ player_url }}</p>
    <p class="instructions">Point your phone camera at the QR code</p>
</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Survival Game</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            background: linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 100%);
            color: white; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            justify-content: center; 
            min-height: 100vh; 
            padding: 20px; 
            text-align: center;
        }
        h1 { 
            background: linear-gradient(90deg, #ef4444, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 56px;
            font-weight: 900;
            letter-spacing: 3px;
            margin-bottom: 30px;
        }
        h2 { font-size: 32px; margin-bottom: 20px; }
        input { 
            padding: 18px; 
            background: rgba(255, 255, 255, 0.05);
            color: white; 
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px; 
            width: 100%; 
            max-width: 350px;
            font-size: 20px; 
            text-align: center;
            margin-bottom: 15px;
        }
        button { 
            padding: 18px 40px; 
            border: none; 
            border-radius: 12px; 
            color: white; 
            cursor: pointer; 
            font-size: 22px; 
            font-weight: bold;
        }
        .btn-green { background: linear-gradient(135deg, #16a34a, #22c55e); }
        .btn-blue { background: linear-gradient(135deg, #2563eb, #3b82f6); }
        .hidden { display: none; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .tension-counter { 
            font-size: 28px; 
            color: #facc15;
            margin-top: 25px;
            font-weight: 900;
        }
        .connection-warning {
            background: rgba(239, 68, 68, 0.2);
            border: 2px solid #ef4444;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            color: #f87171;
            font-weight: bold;
        }
    </style>
</head>
<body>
    
    <div id="joinScreen">
        <h1>SURVIVAL</h1>
        <input type="text" id="nameInput" placeholder="Enter your name...">
        <br><br>
        <button class="btn-green" onclick="joinGame()">JOIN GAME</button>
    </div>

    <div id="waitingScreen" class="hidden">
        <h2>Welcome, <span id="playerName" style="color: #4ade80;"></span>!</h2>
        <p class="pulse" style="font-size: 22px; color: #9ca3af;">Waiting for the host to start the round...</p>
    </div>

    <div id="answerScreen" class="hidden" style="width: 100%; max-width: 450px;">
        <h2 style="color: #facc15;" id="questionText"></h2>
        <input type="text" id="answerInput" placeholder="Your answer...">
        <br><br>
        <button class="btn-blue" style="width: 100%; max-width: 350px;" onclick="submitAnswer()">SUBMIT</button>
        <p id="answerStatus" style="margin-top: 20px; font-size: 20px; color: #9ca3af;"></p>
        <p id="tensionCounter" class="tension-counter hidden"></p>
        <div id="connectionWarning" class="connection-warning hidden">⚠️ Connection unstable!</div>
    </div>

    <div id="eliminatedScreen" class="hidden">
        <h1 style="font-size: 72px;">💀 ELIMINATED 💀</h1>
        <p style="font-size: 24px; color: #9ca3af;">Better luck next time.</p>
    </div>

    <script>
        const socket = io();
        let myName = "";

        socket.on('connect', () => {
            console.log('✅ Phone connected');
            document.getElementById('connectionWarning').classList.add('hidden');
        });

        socket.on('disconnect', () => {
            console.log('❌ Phone disconnected');
            document.getElementById('connectionWarning').classList.remove('hidden');
            document.getElementById('connectionWarning').textContent = '⚠️ Connection lost! Refresh the page.';
        });

        function joinGame() {
            myName = document.getElementById('nameInput').value;
            if(myName) {
                socket.emit('join_game', {name: myName});
                document.getElementById('joinScreen').classList.add('hidden');
                document.getElementById('waitingScreen').classList.remove('hidden');
                document.getElementById('playerName').innerText = myName;
            }
        }

        function submitAnswer() {
            const ans = document.getElementById('answerInput').value;
            if(ans) {
                socket.emit('submit_answer', {answer: ans});
                document.getElementById('answerStatus').innerText = "✅ Answer locked in!";
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
            document.getElementById('tensionCounter').classList.add('hidden');
        });

        socket.on('answer_count_update', (data) => {
            const counter = document.getElementById('tensionCounter');
            counter.classList.remove('hidden');
            counter.innerText = `${data.count} / ${data.total} players have answered`;
        });

        socket.on('round_locked', () => {
            document.getElementById('answerStatus').innerText = "Host is reviewing answers...";
            document.getElementById('tensionCounter').classList.add('hidden');
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

@app.route('/')
def host_dashboard():
    return render_template_string(HOST_HTML)

@app.route('/qr')
def qr_page():
    # This automatically detects your Render URL!
    host = request.host
    scheme = request.scheme
    player_url = f"{scheme}://{host}/play"   
    qr_code = generate_qr_code(player_url)
    return render_template_string(QR_HTML, qr_code=qr_code, player_url=player_url)

@app.route('/play')
def player_screen():
    return render_template_string(PLAYER_HTML)

@socketio.on('join_game')
def handle_join(data):
    sid = request.sid
    players[sid] = {'name': data['name'], 'status': 'alive', 'answer': ''}
    broadcast_players()
    broadcast_answer_status()

@socketio.on('start_round')
def handle_start_round(data):
    global current_question, round_active, answers_locked, answers_revealed
    
    alive_players = [p for p in players.values() if p['status'] == 'alive']
    if len(alive_players) == 0:
        emit('host_alert', {'msg': '⚠️ Wait for players to join first!'})
        return

    current_question = data['question']
    round_active = True
    answers_locked = False
    answers_revealed = False
    
    for sid, p in players.items():
        if p['status'] == 'alive':
            p['answer'] = ''
            
    emit('round_started', {'question': current_question}, broadcast=True)
    broadcast_answer_status()

@socketio.on('submit_answer')
def handle_answer(data):
    global answers_locked
    if answers_locked: return
    
    sid = request.sid
    if sid in players and players[sid]['status'] == 'alive':
        players[sid]['answer'] = data['answer'].strip().lower()
        broadcast_answer_status()

@socketio.on('lock_answers')
def handle_lock():
    global answers_locked
    answers_locked = True
    emit('answers_locked', broadcast=True)
    broadcast_answer_status()

@socketio.on('reveal_answers')
def handle_reveal():
    global answers_locked, answers_revealed
    answers_locked = True
    answers_revealed = True
    emit('round_locked', broadcast=True)
    emit('reveal_answers', get_answer_groups(), broadcast=True)

@socketio.on('eliminate')
def handle_eliminate(data):
    names_to_eliminate = data['names']
    for sid, p in players.items():
        if p['name'] in names_to_eliminate:
            p['status'] = 'eliminated'
            emit('eliminated', room=sid)
            
    broadcast_players()
    broadcast_answer_status()

def broadcast_players():
    player_list = [{'name': p['name'], 'status': p['status']} for p in players.values()]
    emit('update_players', player_list, broadcast=True)

def broadcast_answer_status():
    status_list = [{'name': p['name'], 'status': p['status'], 'answered': bool(p['answer'])} for p in players.values()]
    emit('update_answer_status', status_list, broadcast=True)
    
    alive_players = [p for p in players.values() if p['status'] == 'alive']
    answered_count = sum(1 for p in alive_players if p['answer'])
    emit('answer_count_update', {'count': answered_count, 'total': len(alive_players)}, broadcast=True)

def get_answer_groups():
    answer_groups = {}
    for p in players.values():
        if p['status'] == 'alive' and p['answer']:
            ans = p['answer']
            if ans not in answer_groups:
                answer_groups[ans] = []
            answer_groups[ans].append(p['name'])
    return answer_groups

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
