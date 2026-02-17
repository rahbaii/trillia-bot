import websocket, json, time, random, statistics, math, threading, requests, os
from flask import Flask, jsonify, render_template_string

DERIV_TOKEN="0mfIZYL1w9kOAFR"
TELEGRAM_TOKEN="8493739616:AAF0pY3FFuaIkQEvla7DLbAkDvOmoIQPcZ8"
CHAT_ID="7882297855"

SYMBOLS=["R_100","R_75","R_50","R_25","R_10"]

BASE_STAKE=1
MAX_STAKE=50
TARGET=200
MAX_DD=100
CONF=60
VOLMAX=0.4

stake=BASE_STAKE
start_balance=0
peak=0

stats={"balance":0,"profit":0,"trades":0,"wins":0,"loss":0,"winrate":0,
"symbol":"Scanning","confidence":0,"quality":"","regime":"","strength":0}

app=Flask(__name__)

HTML="""
<h1>TRILLIA AI LIVE</h1>
<pre>{{stats}}</pre>
"""

@app.route("/")
def dash():
    return render_template_string(HTML,stats=stats)

# ================= AI =================

class Brain:
    def __init__(self):
        self.w=[random.uniform(-1,1) for _ in range(5)]
        self.b=random.uniform(-1,1)
    def predict(self,x):
        z=sum(w*i for w,i in zip(self.w,x))+self.b
        z=max(min(z,60),-60)
        return 1/(1+math.exp(-z))
    def train(self,x,y):
        p=self.predict(x)
        e=y-p
        for i in range(len(self.w)):
            self.w[i]+=0.01*e*x[i]
        self.b+=0.01*e

brain=Brain()

# ================= DERIV =================

def connect():
    while True:
        try:
            ws=websocket.WebSocket()
            ws.connect("wss://ws.binaryws.com/websockets/v3?app_id=1089")
            ws.send(json.dumps({"authorize":DERIV_TOKEN}))
            ws.recv()
            print("Connected")
            return ws
        except:
            time.sleep(3)

def balance(ws):
    ws.send(json.dumps({"balance":1}))
    while True:
        d=json.loads(ws.recv())
        if "balance" in d:
            return float(d["balance"]["balance"])

def candles(ws,s):
    ws.send(json.dumps({
        "ticks_history":s,
        "count":40,
        "granularity":60,
        "style":"candles",
        "end":"latest"}))
    d=json.loads(ws.recv())
    return d.get("candles")

# ================= ANALYZER =================

def analyze(ws):
    best=None
    best_conf=0
    best_x=None

    for s in SYMBOLS:
        c=candles(ws,s)
        if not c: continue

        closes=[x["close"] for x in c]
        momentum=closes[-1]-closes[-3]
        trend=closes[-1]-closes[0]
        vol=statistics.stdev(closes)
        accel=(closes[-1]-closes[-2])-(closes[-2]-closes[-3])
        strength=abs(trend)/(vol+0.001)

        x=[momentum,trend,vol,accel,strength]
        conf=brain.predict(x)

        if conf>best_conf:
            best_conf=conf
            best=s
            best_x=x
            best_strength=strength
            best_vol=vol

    if not best: return None

    return {
        "symbol":best,
        "side":"CALL" if best_conf>0.5 else "PUT",
        "confidence":best_conf,
        "strength":best_strength,
        "vol":best_vol,
        "x":best_x
    }

# ================= TRADE =================

def trade(ws,s,side):
    ws.send(json.dumps({
        "buy":1,
        "price":stake,
        "parameters":{
            "amount":stake,
            "basis":"stake",
            "contract_type":side,
            "currency":"USD",
            "duration":1,
            "duration_unit":"m",
            "symbol":s}}))

def result(ws):
    time.sleep(65)
    return balance(ws)

# ================= BOT =================

def bot():
    global stake,start_balance,peak

    ws=connect()
    start_balance=balance(ws)
    peak=start_balance

    while True:
        try:
            bal=balance(ws)
            profit=bal-start_balance

            stats["balance"]=bal
            stats["profit"]=round(profit,2)

            peak=max(peak,bal)
            if peak-bal>MAX_DD: return
            if profit>TARGET: return

            r=analyze(ws)
            if not r:
                time.sleep(2)
                continue

            stats["symbol"]=r["symbol"]
            stats["confidence"]=round(r["confidence"]*100,2)
            stats["strength"]=round(r["strength"],2)

            if r["confidence"]*100<CONF or r["vol"]>VOLMAX:
                continue

            before=bal
            trade(ws,r["symbol"],r["side"])
            after=result(ws)

            stats["trades"]+=1
            win=1 if after>before else 0
            brain.train(r["x"],win)

            if win:
                stats["wins"]+=1
                stake=BASE_STAKE
            else:
                stats["loss"]+=1
                stake=min(stake*1.5,MAX_STAKE)

            stats["winrate"]=round(stats["wins"]/stats["trades"]*100,2)

        except:
            ws=connect()

# ================= START =================

threading.Thread(target=bot).start()

port=int(os.environ.get("PORT",8080))
app.run(host="0.0.0.0",port=port)
