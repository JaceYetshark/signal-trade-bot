import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
from telegram import Bot
import asyncio
import threading
import time

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_ID = os.getenv('TELEGRAM_USER_ID')
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

last_notified_signal_id = 0

def get_db_connection():
    conn = sqlite3.connect('signals.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_latest_signals(limit=50):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM signals ORDER BY rowid DESC LIMIT ?''', (limit,))
        signals = c.fetchall()
        conn.close()
        return [dict(signal) for signal in signals]
    except:
        return []

def get_security_logs(limit=20):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM security_logs ORDER BY rowid DESC LIMIT ?''', (limit,))
        logs = c.fetchall()
        conn.close()
        return [dict(log) for log in logs]
    except:
        return []

def get_stats():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) as total FROM signals")
        total = c.fetchone()['total']
        
        c.execute("SELECT COUNT(*) as buy FROM signals WHERE direction = 'BUY'")
        buy = c.fetchone()['buy']
        
        c.execute("SELECT COUNT(*) as sell FROM signals WHERE direction = 'SELL'")
        sell = c.fetchone()['sell']
        
        c.execute("SELECT COUNT(*) as critical FROM security_logs WHERE severity = 'CRITICAL'")
        critical_alerts = c.fetchone()['critical']
        
        conn.close()
        
        return {
            'total_signals': total,
            'buy_signals': buy,
            'sell_signals': sell,
            'critical_alerts': critical_alerts
        }
    except:
        return {'total_signals': 0, 'buy_signals': 0, 'sell_signals': 0, 'critical_alerts': 0}

async def send_telegram_notification(signal):
    if not bot or not USER_ID:
        return
    try:
        message = f"""
🚨 NEW SIGNAL ALERT 🚨

📍 Channel: {signal.get('channel_name', 'Unknown')}
💱 Pair: {signal.get('pair', 'N/A')}
{'🟢' if signal.get('direction') == 'BUY' else '🔴'} Direction: {signal.get('direction', 'N/A')}

📊 Entry: {signal.get('entry', 'N/A')}
🛑 Stop Loss: {signal.get('sl', 'N/A')}

📈 Take Profits:
TP1: {signal.get('tp1') or 'N/A'}
TP2: {signal.get('tp2') or 'N/A'}
TP3: {signal.get('tp3') or 'N/A'}

⏰ Time: {signal.get('timestamp', 'N/A')}
"""
        await bot.send_message(chat_id=USER_ID, text=message)
        print(f"✅ Notification sent for {signal.get('pair')}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

def monitor_signals():
    global last_notified_signal_id
    
    while True:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            
            c.execute("SELECT MAX(rowid) as max_id FROM signals")
            result = c.fetchone()
            max_id = result['max_id'] or 0
            
            if max_id > last_notified_signal_id:
                c.execute("SELECT * FROM signals WHERE rowid = ?", (max_id,))
                signal = c.fetchone()
                
                if signal and bot and USER_ID:
                    asyncio.run(send_telegram_notification(dict(signal)))
                    last_notified_signal_id = max_id
            
            conn.close()
            time.sleep(5)
            
        except Exception as e:
            print(f"Error in monitoring: {e}")
            time.sleep(10)

@app.route('/api/signals', methods=['GET'])
def api_signals():
    signals = get_latest_signals()
    return jsonify(signals)

@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = get_stats()
    return jsonify(stats)

@app.route('/api/security-logs', methods=['GET'])
def api_security_logs():
    logs = get_security_logs()
    return jsonify(logs)

@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'bot_token_set': bool(BOT_TOKEN),
        'user_id_set': bool(USER_ID)
    })

@app.route('/', methods=['GET'])
def index():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SIGNAL TRADE</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #fff;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            text-align: center;
        }
        h1 { font-size: 32px; margin-bottom: 10px; }
        .status { display: flex; align-items: center; justify-content: center; gap: 10px; margin: 15px 0; }
        .status-dot {
            width: 10px; height: 10px;
            background: #00ff00;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-top: 15px;
        }
        .stat-box {
            background: rgba(0, 0, 0, 0.3);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-number { font-size: 20px; font-weight: bold; color: #00ff88; }
        .stat-label { font-size: 11px; opacity: 0.8; margin-top: 5px; }
        .signal-card {
            background: rgba(255, 255, 255, 0.08);
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 12px;
        }
        .signal-card.buy { border-left: 4px solid #00ff00; }
        .signal-card.sell { border-left: 4px solid #ff4444; }
        .signal-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .signal-pair { font-size: 18px; font-weight: bold; }
        .signal-direction {
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
            font-weight: bold;
        }
        .signal-direction.buy { background: rgba(0, 255, 0, 0.2); color: #00ff88; }
        .signal-direction.sell { background: rgba(255, 68, 68, 0.2); color: #ff6666; }
        .signal-meta { font-size: 12px; opacity: 0.8; margin-bottom: 10px; }
        .signal-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-size: 13px;
        }
        .detail-item {
            background: rgba(0, 0, 0, 0.2);
            padding: 8px;
            border-radius: 6px;
        }
        .detail-label { opacity: 0.7; font-size: 11px; }
        .detail-value { font-weight: bold; color: #ffff88; margin-top: 3px; }
        .empty { text-align: center; padding: 40px; opacity: 0.6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SIGNAL TRADE</h1>
            <div class="status">
                <div class="status-dot"></div>
                <span>LIVE MONITORING</span>
            </div>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number" id="totalSignals">0</div>
                    <div class="stat-label">Total</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="buySignals">0</div>
                    <div class="stat-label">Buy</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="sellSignals">0</div>
                    <div class="stat-label">Sell</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="alertsCount">0</div>
                    <div class="stat-label">🚨</div>
                </div>
            </div>
        </div>
        <div id="signalsContainer"></div>
    </div>

    <script>
        async function loadData() {
            try {
                const [signalsRes, statsRes] = await Promise.all([
                    fetch('/api/signals'),
                    fetch('/api/stats')
                ]);
                const signals = await signalsRes.json();
                const stats = await statsRes.json();

                document.getElementById('totalSignals').textContent = stats.total_signals || 0;
                document.getElementById('buySignals').textContent = stats.buy_signals || 0;
                document.getElementById('sellSignals').textContent = stats.sell_signals || 0;
                document.getElementById('alertsCount').textContent = stats.critical_alerts || 0;

                const container = document.getElementById('signalsContainer');
                if (!signals || signals.length === 0) {
                    container.innerHTML = '<div class="empty">📡 Waiting for signals...</div>';
                    return;
                }

                container.innerHTML = signals.slice(0, 20).map(signal => `
                    <div class="signal-card ${(signal.direction || '').toLowerCase()}">
                        <div class="signal-header">
                            <div class="signal-pair">${signal.pair || 'N/A'}</div>
                            <div class="signal-direction ${(signal.direction || '').toLowerCase()}">
                                ${signal.direction || 'N/A'}
                            </div>
                        </div>
                        <div class="signal-meta">
                            ⏰ ${signal.timestamp || 'N/A'} | 📍 ${signal.channel_name || 'N/A'}
                        </div>
                        <div class="signal-details">
                            <div class="detail-item">
                                <div class="detail-label">ENTRY</div>
                                <div class="detail-value">${signal.entry || 'N/A'}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">STOP LOSS</div>
                                <div class="detail-value">${signal.sl || 'N/A'}</div>
                            </div>
                            ${signal.tp1 ? `<div class="detail-item">
                                <div class="detail-label">TP1</div>
                                <div class="detail-value">${signal.tp1}</div>
                            </div>` : ''}
                            ${signal.tp2 ? `<div class="detail-item">
                                <div class="detail-label">TP2</div>
                                <div class="detail-value">${signal.tp2}</div>
                            </div>` : ''}
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Error:', e);
            }
        }

        loadData();
        setInterval(loadData, 5000);
    </script>
</body>
</html>'''

def main():
    if not BOT_TOKEN:
        print("WARNING: TELEGRAM_BOT_TOKEN not set!")
    
    if not USER_ID:
        print("WARNING: TELEGRAM_USER_ID not set!")
    
    if BOT_TOKEN and USER_ID:
        signal_monitor_thread = threading.Thread(target=monitor_signals, daemon=True)
        signal_monitor_thread.start()
    
    print("🚀 SIGNAL TRADE SERVER STARTING...")
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
