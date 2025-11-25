import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from telegram import Bot
import asyncio
import threading
import time

app = Flask(__name__)
CORS(app)

# Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USER_ID = os.getenv('TELEGRAM_USER_ID')
bot = Bot(token=BOT_TOKEN)

last_notified_signal_id = 0

def get_db_connection():
    conn = sqlite3.connect('signals.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_latest_signals(limit=50):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM signals ORDER BY rowid DESC LIMIT ?''', (limit,))
    signals = c.fetchall()
    conn.close()
    return [dict(signal) for signal in signals]

def get_security_logs(limit=20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM security_logs ORDER BY rowid DESC LIMIT ?''', (limit,))
    logs = c.fetchall()
    conn.close()
    return [dict(log) for log in logs]

def get_stats():
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

async def send_telegram_notification(signal):
    try:
        message = f"""
🚨 NEW SIGNAL ALERT 🚨

📍 Channel: {signal['channel_name']}
💱 Pair: {signal['pair']}
{'🟢' if signal['direction'] == 'BUY' else '🔴'} Direction: {signal['direction']}

📊 Entry: {signal['entry']}
🛑 Stop Loss: {signal['sl']}

📈 Take Profits:
TP1: {signal['tp1'] or 'N/A'}
TP2: {signal['tp2'] or 'N/A'}
TP3: {signal['tp3'] or 'N/A'}

⏰ Time: {signal['timestamp']}
"""
        await bot.send_message(
            chat_id=USER_ID,
            text=message
        )
        print(f"✅ Notification sent for {signal['pair']}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

async def send_security_alert(event_type, description, severity):
    try:
        alert_emoji = '🚨' if severity == 'CRITICAL' else '⚠️'
        message = f"""
{alert_emoji} SECURITY ALERT {alert_emoji}

Type: {event_type}
Severity: {severity}
Description: {description}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await bot.send_message(
            chat_id=USER_ID,
            text=message
        )
        print(f"🚨 Security alert sent: {event_type}")
    except Exception as e:
        print(f"❌ Failed to send security alert: {e}")

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
                
                if signal:
                    asyncio.run(send_telegram_notification(dict(signal)))
                    last_notified_signal_id = max_id
            
            conn.close()
            time.sleep(5)
            
        except Exception as e:
            print(f"Error in monitoring: {e}")
            time.sleep(10)

def monitor_security():
    last_checked_id = 0
    
    while True:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            
            c.execute("""
                SELECT * FROM security_logs 
                WHERE rowid > ? 
                ORDER BY rowid DESC
            """, (last_checked_id,))
            
            logs = c.fetchall()
            
            for log in logs:
                log_dict = dict(log)
                if log_dict['severity'] in ['CRITICAL', 'HIGH']:
                    asyncio.run(send_security_alert(
                        log_dict['event_type'],
                        log_dict['description'],
                        log_dict['severity']
                    ))
                last_checked_id = log_dict['rowid']
            
            conn.close()
            time.sleep(10)
            
        except Exception as e:
            print(f"Error in security monitoring: {e}")
            time.sleep(15)

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
    # Serve the dashboard HTML from FILE 3
    return "<h1>SIGNAL TRADE Dashboard</h1><p>Server is running!</p>"

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    if not USER_ID:
        print("WARNING: TELEGRAM_USER_ID environment variable not set. Notifications disabled!")
    
    signal_monitor_thread = threading.Thread(target=monitor_signals, daemon=True)
    security_monitor_thread = threading.Thread(target=monitor_security, daemon=True)
    
    signal_monitor_thread.start()
    security_monitor_thread.start()
    
    print("🚀 SIGNAL TRADE SERVER STARTING...")
    print("📊 Dashboard available at: http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
