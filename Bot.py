import os
import re
import json
import sqlite3
import hashlib
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database initialization
def init_db():
    conn = sqlite3.connect('signals.db')
    c = conn.cursor()
    
    # Signals table
    c.execute('''CREATE TABLE IF NOT EXISTS signals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  channel_name TEXT,
                  pair TEXT,
                  direction TEXT,
                  entry TEXT,
                  tp1 TEXT, tp2 TEXT, tp3 TEXT, tp4 TEXT, tp5 TEXT, tp6 TEXT,
                  sl TEXT,
                  leverage TEXT,
                  timestamp TEXT,
                  signal_hash TEXT UNIQUE,
                  message_text TEXT)''')
    
    # Security logs table
    c.execute('''CREATE TABLE IF NOT EXISTS security_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_type TEXT,
                  description TEXT,
                  timestamp TEXT,
                  severity TEXT)''')
    
    # Performance tracking
    c.execute('''CREATE TABLE IF NOT EXISTS performance
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  signal_id INTEGER,
                  tp_hit TEXT,
                  sl_hit BOOLEAN,
                  pips_gained REAL,
                  update_time TEXT,
                  FOREIGN KEY(signal_id) REFERENCES signals(id))''')
    
    conn.commit()
    conn.close()

# Signal parsing
def parse_signal(text, channel_name):
    text = text.upper()
    signal = {
        'channel': channel_name,
        'pair': None,
        'direction': None,
        'entry': None,
        'tp1': None, 'tp2': None, 'tp3': None, 'tp4': None, 'tp5': None, 'tp6': None,
        'sl': None,
        'leverage': None,
        'timestamp': datetime.now().strftime('%H:%M'),
        'date': datetime.now().strftime('%d %B %Y').upper(),
        'raw_text': text
    }
    
    # Extract trading pair
    pairs = re.findall(r'(XAU[A-Z]+|BTC[A-Z]+|ETH[A-Z]+|EUR[A-Z]+|GBP[A-Z]+|USD[A-Z]+|AUD[A-Z]+|CAD[A-Z]+|JPY[A-Z]+|[A-Z]{3,}USD[A-Z]?|GOLD|US30|CYBER|WOO|STORJ|GAS|SUSHI|ID|ICP)', text)
    if pairs:
        signal['pair'] = pairs[0]
    
    # Extract direction
    if 'BUY' in text or 'LONG' in text:
        signal['direction'] = 'BUY'
    elif 'SELL' in text or 'SHORT' in text:
        signal['direction'] = 'SELL'
    
    # Extract entry
    entry_patterns = [
        r'ENTRY[:\s@-]*([0-9.]+)',
        r'ENTER[:\s@]*([0-9.]+)',
        r'ENTRY PRICE[:\s]*([0-9.]+)',
        r'ENTRY ZONE[:\s]*([0-9.-]+)',
        r'BUY[:\s@]*([0-9.]+)',
        r'SELL[:\s@]*([0-9.]+)',
        r'@ ?([0-9.]+)',
    ]
    for pattern in entry_patterns:
        match = re.search(pattern, text)
        if match:
            signal['entry'] = match.group(1)
            break
    
    # Extract TPs
    tp_patterns = [
        r'TP[:\s]*?([1-6])[:\s-]*([0-9.]+)',
        r'TAKE PROFIT[:\s]*?([1-6])[:\s-]*([0-9.]+)',
        r'TARGET[:\s]*?([1-6])[:\s-]*([0-9.]+)',
    ]
    
    for pattern in tp_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            tp_num = int(match[0])
            if 1 <= tp_num <= 6:
                signal[f'tp{tp_num}'] = match[1]
    
    # Extract Stop Loss
    sl_patterns = [
        r'SL[:\s@-]*([0-9.]+)',
        r'STOP LOSS[:\s@-]*([0-9.]+)',
        r'STOPLOSS[:\s@]*([0-9.]+)',
    ]
    for pattern in sl_patterns:
        match = re.search(pattern, text)
        if match:
            signal['sl'] = match.group(1)
            break
    
    # Extract Leverage
    leverage_patterns = [
        r'LEVERAGE[:\s]*X?([0-9.]+)',
        r'CROSS[:\s]*X?([0-9.]+)',
        r'X([0-9.]+)',
    ]
    for pattern in leverage_patterns:
        match = re.search(pattern, text)
        if match:
            signal['leverage'] = match.group(1)
            break
    
    return signal

# Generate signal hash for duplicate detection
def generate_signal_hash(pair, entry):
    hash_string = f"{pair}_{entry}"
    return hashlib.md5(hash_string.encode()).hexdigest()

# Check if signal is duplicate
def is_duplicate_signal(pair, entry):
    if not pair or not entry:
        return False
    
    signal_hash = generate_signal_hash(pair, entry)
    conn = sqlite3.connect('signals.db')
    c = conn.cursor()
    c.execute("SELECT id FROM signals WHERE signal_hash = ?", (signal_hash,))
    result = c.fetchone()
    conn.close()
    
    return result is not None

# Save signal to database
def save_signal(signal):
    if not signal['pair'] or not signal['entry']:
        return False
    
    # Check for duplicates
    if is_duplicate_signal(signal['pair'], signal['entry']):
        logger.info(f"⚠️ DUPLICATE DETECTED: {signal['pair']} @ {signal['entry']}")
        return False
    
    signal_hash = generate_signal_hash(signal['pair'], signal['entry'])
    
    conn = sqlite3.connect('signals.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO signals 
                     (channel_name, pair, direction, entry, tp1, tp2, tp3, tp4, tp5, tp6, sl, leverage, timestamp, signal_hash, message_text)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (signal['channel'], signal['pair'], signal['direction'], signal['entry'],
                   signal['tp1'], signal['tp2'], signal['tp3'], signal['tp4'], signal['tp5'], signal['tp6'],
                   signal['sl'], signal['leverage'], signal['timestamp'], signal_hash, signal['raw_text']))
        conn.commit()
        logger.info(f"✅ SIGNAL SAVED: {signal['pair']} {signal['direction']} @ {signal['entry']} from {signal['channel']}")
        return True
    except sqlite3.IntegrityError:
        logger.info(f"⚠️ DUPLICATE SIGNAL HASH: {signal['pair']}")
        return False
    finally:
        conn.close()

# Log security events
def log_security_event(event_type, description, severity):
    conn = sqlite3.connect('signals.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''INSERT INTO security_logs (event_type, description, timestamp, severity)
                 VALUES (?, ?, ?, ?)''',
              (event_type, description, timestamp, severity))
    conn.commit()
    conn.close()
    logger.warning(f"🚨 SECURITY ALERT [{severity}]: {event_type} - {description}")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        channel_name = update.channel_post.chat.title or "Unknown"
        message_text = update.channel_post.text or ""
        
        # Security: Detect unusual bot commands
        if message_text.startswith('/'):
            log_security_event(
                'COMMAND_DETECTED',
                f'Unusual command in {channel_name}',
                'MEDIUM'
            )
        
        # Signal keywords
        signal_keywords = ['BUY', 'SELL', 'LONG', 'SHORT', 'TP', 'SL', 'ENTRY', 'XAUUSD', 'GOLD', 'BTC']
        if any(keyword in message_text.upper() for keyword in signal_keywords):
            signal = parse_signal(message_text, channel_name)
            
            if signal['pair'] and (signal['entry'] or signal['tp1']):
                if save_signal(signal):
                    # Write to signals file
                    write_to_signal_file(signal)

# Write signal to text file
def write_to_signal_file(signal):
    signals_file = 'SIGNAL_TRADE.txt'
    
    # Check if file exists and read last date
    last_date = None
    if os.path.exists(signals_file):
        with open(signals_file, 'r') as f:
            content = f.read()
            if content:
                last_date = content.split('\n')[-5] if len(content) > 100 else None
    
    current_date = signal['date']
    
    with open(signals_file, 'a') as f:
        # Add date header if new day
        if last_date != current_date:
            if os.path.getsize(signals_file) > 0:
                f.write('\n\n')
            f.write(f"{'='*50}\n")
            f.write(f"📅 {current_date}\n")
            f.write(f"{'='*50}\n\n")
        
        # Write signal
        f.write(f"⏰ {signal['timestamp']} | 📍 {signal['channel']}\n")
        f.write(f"💱 {signal['pair']} | {'🟢 BUY' if signal['direction'] == 'BUY' else '🔴 SELL'}\n")
        f.write(f"Entry: {signal['entry']} | SL: {signal['sl']}\n")
        
        tps = [signal[f'tp{i}'] for i in range(1, 7) if signal[f'tp{i}']]
        if tps:
            f.write(f"TP: {' | '.join(tps)}\n")
        
        f.write("\n")

def main():
    init_db()
    
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("ERROR: TELEGRAM_BOT_TOKEN not set!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    logger.info("🤖 Signal Bot ONLINE - Monitoring 53 channels...")
    log_security_event('BOT_STARTED', 'Signal tracking bot initialized', 'INFO')
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
