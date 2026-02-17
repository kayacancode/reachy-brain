#!/bin/bash
# Demo mode launcher - runs on Mac, orchestrates everything
# Usage: ./demo.sh start | stop | status
set -euo pipefail

ROBOT_IP="10.0.0.68"
ROBOT_USER="pollen"
ROBOT_PASS="root"
MAC_IP="10.0.0.234"
RELAY_PORT="18801"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
RELAY_PID_FILE="/tmp/reachy_relay.pid"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-REDACTED_TELEGRAM_BOT_TOKEN}"

ssh_cmd() {
    sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$ROBOT_USER@$ROBOT_IP" "$@"
}

start_demo() {
    echo "🤖 Starting Reachy Demo Mode..."
    echo ""

    # 0. CLEAN KILL — always start fresh to avoid zombie processes
    echo "0/6 Clean slate — killing leftover processes..."
    ssh_cmd "killall python3 2>/dev/null" 2>/dev/null || true
    if [ -f "$RELAY_PID_FILE" ]; then
        kill "$(cat "$RELAY_PID_FILE")" 2>/dev/null || true
        rm -f "$RELAY_PID_FILE"
    fi
    /usr/sbin/lsof -ti:$RELAY_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    sleep 2
    echo "  ✅ Clean slate"

    # 1. Check robot is reachable
    echo "1/6 Checking robot connectivity..."
    if ! ssh_cmd "echo ok" >/dev/null 2>&1; then
        echo "❌ Cannot reach robot at $ROBOT_IP"
        exit 1
    fi
    echo "  ✅ Robot reachable"

    # 2. Wake daemon
    echo "2/6 Waking robot daemon..."
    DAEMON_STATUS=$(curl -s --connect-timeout 3 "http://$ROBOT_IP:8000/api/daemon/status" 2>/dev/null || echo "")
    if echo "$DAEMON_STATUS" | grep -q '"state"'; then
        echo "  ✅ Daemon already running"
    else
        ssh_cmd "nohup /restore/venvs/mini_daemon/bin/python3 -m reachy_mini.daemon.app.main > ~/daemon.log 2>&1 &"
        sleep 5
    fi
    curl -s -X POST "http://$ROBOT_IP:8000/api/daemon/start?wake_up=true" >/dev/null 2>&1 || true
    sleep 2
    echo "  ✅ Robot awake"

    # 3. Start bridge (always fresh — old bridge may be in bad state)
    echo "3/6 Starting bridge..."
    ssh_cmd "cd /home/pollen/bridge && nohup /restore/venvs/mini_daemon/bin/python3 reachy_bridge.py > /tmp/bridge.log 2>&1 &" 2>/dev/null || true
    sleep 4
    if curl -s --connect-timeout 3 "http://$ROBOT_IP:9000/status" 2>/dev/null | grep -q "bridge"; then
        echo "  ✅ Bridge started"
    else
        echo "  ⚠️  Bridge may not have started — check /tmp/bridge.log on robot"
    fi

    # 4. Start relay on Mac (always fresh)
    echo "4/6 Starting Telegram relay on Mac..."
    TELEGRAM_BOT_TOKEN="$BOT_TOKEN" RELAY_PORT="$RELAY_PORT" \
        nohup python3 "$SKILL_DIR/relay_server.py" > /tmp/reachy_relay.log 2>&1 &
    echo $! > "$RELAY_PID_FILE"
    sleep 2
    if kill -0 "$(cat "$RELAY_PID_FILE")" 2>/dev/null; then
        echo "  ✅ Relay started on port $RELAY_PORT (PID $(cat "$RELAY_PID_FILE"))"
    else
        echo "  ❌ Relay failed to start — check /tmp/reachy_relay.log"
        exit 1
    fi

    # 5. Start talk_wireless on robot
    echo "5/6 Starting voice agent on robot..."
    ssh_cmd "cd /home/pollen && source ~/.kayacan/config.env && export TELEGRAM_RELAY='http://$MAC_IP:$RELAY_PORT/telegram' && nohup python3 talk_wireless.py > ~/talk.log 2>&1 &" 2>/dev/null || true
    sleep 3
    if ssh_cmd "pgrep -f talk_wireless.py" >/dev/null 2>&1; then
        echo "  ✅ Voice agent running"
    else
        echo "  ❌ Voice agent failed — check ~/talk.log on robot"
        exit 1
    fi

    # 6. Verify everything
    echo "6/6 Final health check..."
    sleep 5
    ERRORS=0
    curl -s --connect-timeout 2 "http://$ROBOT_IP:8000/api/daemon/status" >/dev/null 2>&1 || { echo "  ❌ Daemon down"; ERRORS=$((ERRORS+1)); }
    curl -s --connect-timeout 2 "http://$ROBOT_IP:9000/status" >/dev/null 2>&1 || { echo "  ❌ Bridge down"; ERRORS=$((ERRORS+1)); }
    curl -s --connect-timeout 2 "http://127.0.0.1:$RELAY_PORT/health" >/dev/null 2>&1 || { echo "  ❌ Relay down"; ERRORS=$((ERRORS+1)); }
    ssh_cmd "pgrep -f talk_wireless.py" >/dev/null 2>&1 || { echo "  ❌ Voice agent down"; ERRORS=$((ERRORS+1)); }

    if [ $ERRORS -eq 0 ]; then
        echo ""
        echo "========================================="
        echo "  🟢 DEMO MODE ACTIVE"
        echo "========================================="
        echo "  Robot: $ROBOT_IP (daemon + bridge)"
        echo "  Relay: $MAC_IP:$RELAY_PORT → Telegram"
        echo "  Voice: talk_wireless.py running"
        echo ""
        echo "  Reachy is introducing itself now!"
        echo "  Run './demo.sh stop' to shut down"
        echo "========================================="
    else
        echo ""
        echo "  ⚠️  $ERRORS service(s) failed — check logs"
    fi
}

stop_demo() {
    echo "🛑 Stopping Reachy Demo Mode..."
    echo ""

    # Kill everything on robot
    echo "Stopping robot processes..."
    ssh_cmd "killall python3 2>/dev/null" 2>/dev/null || true
    echo "  ✅ Robot processes stopped"

    # Kill relay on Mac
    echo "Stopping relay..."
    if [ -f "$RELAY_PID_FILE" ]; then
        kill "$(cat "$RELAY_PID_FILE")" 2>/dev/null || true
        rm -f "$RELAY_PID_FILE"
    fi
    /usr/sbin/lsof -ti:$RELAY_PORT 2>/dev/null | xargs kill 2>/dev/null || true
    echo "  ✅ Relay stopped"

    # Put robot to sleep
    echo "Putting robot to sleep..."
    curl -s -X POST "http://$ROBOT_IP:8000/api/daemon/stop?goto_sleep=true" >/dev/null 2>&1 || true
    echo "  ✅ Robot sleeping"

    echo ""
    echo "🔴 Demo mode stopped."
}

status_demo() {
    echo "📊 Reachy Demo Status"
    echo ""

    # Daemon
    DAEMON=$(curl -s --connect-timeout 2 "http://$ROBOT_IP:8000/api/daemon/status" 2>/dev/null || echo "unreachable")
    STATE=$(echo "$DAEMON" | grep -o '"state":"[^"]*"' | cut -d'"' -f4 2>/dev/null || echo "unknown")
    echo "  Daemon:  $STATE"

    # Bridge
    BRIDGE=$(curl -s --connect-timeout 2 "http://$ROBOT_IP:9000/status" 2>/dev/null || echo "")
    if echo "$BRIDGE" | grep -q "bridge"; then
        echo "  Bridge:  ✅ running"
    else
        echo "  Bridge:  ❌ down"
    fi

    # Relay
    if [ -f "$RELAY_PID_FILE" ] && kill -0 "$(cat "$RELAY_PID_FILE")" 2>/dev/null; then
        echo "  Relay:   ✅ running (PID $(cat "$RELAY_PID_FILE"))"
    else
        echo "  Relay:   ❌ down"
    fi

    # Talk
    if ssh_cmd "pgrep -f talk_wireless.py" >/dev/null 2>&1; then
        echo "  Voice:   ✅ running"
    else
        echo "  Voice:   ❌ down"
    fi
}

case "${1:-status}" in
    start)  start_demo ;;
    stop)   stop_demo ;;
    status) status_demo ;;
    *)      echo "Usage: $0 {start|stop|status}" ;;
esac
