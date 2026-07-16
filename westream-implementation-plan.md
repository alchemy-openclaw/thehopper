# WeStream Implementation Plan: NanoClaw + Jitsi VideoBridge on Raspberry Pi 5

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 5 (Orange Pi)               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  NanoClaw    │  │  Jitsi Meet  │  │  Video Capture  │   │
│  │  Core        │  │  Client      │  │  (USB HDMI)     │   │
│  │              │  │  (lib-jitsi) │  │                 │   │
│  │ ┌──────────┐ │  │              │  │  TV Input →     │   │
│  │ │Voice Agent│ │  │  WebRTC      │  │  V4L2 Device    │   │
│  │ │(Wake Word)│ │  │  Connection  │  │                 │   │
│  │ └──────────┘ │  │  to SFU      │  └─────────────────┘   │
│  │ ┌──────────┐ │  │              │  ┌─────────────────┐   │
│  │ │Assistant │ │  └──────────────┘  │  Audio I/O      │   │
│  │ │Agent     │ │         │          │  (USB Mic/Speaker)│  │
│  │ └──────────┘ │         │          └─────────────────┘   │
│  │ ┌──────────┐ │         │                                 │
│  │ │Video Chat│ │         ▼                                 │
│  │ │Agent     │ │  ┌──────────────────────┐                 │
│  │ └──────────┘ │  │  Docker Containers   │                 │
│  └──────────────┘  │  (Per-agent isolation)│                 │
│         │          └──────────────────────┘                 │
│         │                    │                              │
│         └────────────────────┘                              │
│                              │                              │
│  ┌───────────────────────────┴──────────────────────────┐   │
│  │                   SQLite (Local)                      │   │
│  │  - Conversation history                               │   │
│  │  - Contact lists                                      │   │
│  │  - Health monitoring logs                             │   │
│  └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ WebRTC (Media Plane)
                              ▼
                    ┌─────────────────┐
                    │  Jitsi          │
                    │  VideoBridge    │  (SFU Server)
                    │  (Cloud/Hosted) │
                    └─────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │ Family Pi   │   │ Class Pi    │   │ Mobile App  │
    │ (Daughter)  │   │ (Studio)    │   │ (Remote)    │
    └─────────────┘   └─────────────┘   └─────────────┘

Control Plane (Tailscale WireGuard Mesh):
- Pi ↔ Cloud APIs (Claude, vision models)
- Pi ↔ Management Dashboard
- Pi ↔ Pi (direct family connections)
```

---

## Phase 1: Core Infrastructure (Week 1-2)

### 1.1 NanoClaw Base Installation

```bash
# On Raspberry Pi 5 (Orange Pi compatible)
# Install Docker
sudo apt update
sudo apt install docker.io docker-compose

# Clone NanoClaw
git clone https://github.com/qwibitai/nanoclaw.git /opt/nanoclaw
cd /opt/nanoclaw

# Run setup (Claude Code handles dependencies)
claude
/setup
```

**NanoClaw Configuration for Pi 5:**
```json
{
  "nanoclaw": {
    "container_runtime": "docker",
    "isolation_level": "container",
    "voice": {
      "wake_word": "Hey Hearth",
      "audio_input": "plughw:1,0",
      "audio_output": "plughw:0,0",
      "vad_aggressiveness": 2
    },
    "memory": {
      "backend": "sqlite",
      "path": "/opt/nanoclaw/data/memory.db"
    },
    "agents": [
      "voice-controller",
      "video-chat",
      "assistant",
      "health-monitor"
    ]
  }
}
```

### 1.2 Jitsi Client Setup

**Install Jitsi Meet Low-Level Client:**
```bash
# Install Node.js 18+ (required for lib-jitsi-meet)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install lib-jitsi-meet dependencies
npm install lib-jitsi-meet

# Install Chromium for any web-based UI (headless)
sudo apt install chromium-browser
```

**Jitsi Client Configuration:**
```javascript
// /opt/nanoclaw/agents/video-chat/jitsi-config.js
const JitsiConfig = {
  connection: {
    hosts: {
      domain: 'meet.we-stream.org',
      muc: 'conference.meet.we-stream.org',
      focus: 'focus.meet.we-stream.org'
    },
    serviceUrl: 'wss://meet.we-stream.org/xmpp-websocket',
    websocketKeepAlive: 10
  },
  conference: {
    p2p: {
      enabled: false  // Force SFU for Pi efficiency
    },
    enableLayerSuspension: true,  // Save bandwidth
    startVideoMuted: false,
    startAudioMuted: false
  },
  constraints: {
    video: {
      height: {
        ideal: 720,
        max: 720,
        min: 360
      }
    },
    audio: {
      autoGainControl: true,
      echoCancellation: true,
      noiseSuppression: true
    }
  }
};
```

---

## Phase 2: Agent Implementation (Week 3-4)

### 2.1 Voice Controller Agent

**Purpose:** Wake word detection, speech-to-text, command routing

```python
# /opt/nanoclaw/agents/voice-controller/agent.py
import pvporcupine  # Wake word engine
import speech_recognition as sr
from nanoclaw import Agent

class VoiceControllerAgent(Agent):
    WAKE_WORD = "Hey Hearth"
    
    def __init__(self):
        self.porcupine = pvporcupine.create(
            keyword_paths=["hey-hearth.ppn"],
            access_key=os.getenv("PICOVOICE_KEY")
        )
        self.recognizer = sr.Recognizer()
        
    async def run(self):
        """Main voice loop"""
        while True:
            # 1. Wake word detection (local, no cloud)
            if self.detect_wake_word():
                # 2. Audio capture
                audio = self.capture_audio(timeout=5.0)
                
                # 3. Speech-to-text (whisper.cpp local or cloud)
                text = await self.transcribe(audio)
                
                # 4. Command routing
                await self.route_command(text)
    
    async def route_command(self, text):
        """Route to appropriate agent"""
        if "call" in text or "video" in text:
            await self.dispatch_to("video-chat", text)
        elif "help" in text or "question" in text:
            await self.dispatch_to("assistant", text)
        elif "medicine" in text or "pill" in text:
            await self.dispatch_to("health-monitor", text)
```

**Hardware Acceleration:**
- Use Whisper.cpp compiled for ARM64 (local STT)
- Fallback to cloud Whisper API for complex queries
- Pi 5's audio jack + USB mic array (ReSpeaker 4-mic HAT recommended)

### 2.2 Video Chat Agent

**Purpose:** Manage Jitsi connections, handle video calls, UI overlay

```javascript
// /opt/nanoclaw/agents/video-chat/video-agent.js
import JitsiMeetJS from 'lib-jitsi-meet';

class VideoChatAgent {
  constructor(config) {
    this.connection = null;
    this.conference = null;
    this.localTracks = [];
    this.remoteTracks = {};
  }
  
  async connect(roomName) {
    // Initialize Jitsi
    JitsiMeetJS.init();
    
    // Create connection
    this.connection = new JitsiMeetJS.JitsiConnection(
      null,  // No token for now
      null,
      JitsiConfig.connection
    );
    
    // Connect and join conference
    await this.connect();
    this.conference = this.connection.initJitsiConference(
      roomName,
      JitsiConfig.conference
    );
    
    // Set up event handlers
    this.setupConferenceHandlers();
    
    // Join with audio/video
    await this.createLocalTracks();
    await this.conference.join();
  }
  
  async createLocalTracks() {
    // Pi 5 camera or HDMI capture
    const tracks = await JitsiMeetJS.createLocalTracks({
      devices: ['audio', 'video'],
      cameraDeviceId: 'usb_capture_device',  // HDMI capture
      micDeviceId: 'default'
    });
    
    tracks.forEach(track => {
      this.conference.addTrack(track);
      this.localTracks.push(track);
    });
  }
  
  setupConferenceHandlers() {
    // Remote participant joined
    this.conference.on(
      JitsiMeetJS.events.conference.USER_JOINED,
      (id, user) => {
        console.log('User joined:', user.getDisplayName());
        // Notify via voice: "Sarah has joined the call"
        this.speak(`${user.getDisplayName()} has joined`);
      }
    );
    
    // Remote track received
    this.conference.on(
      JitsiMeetJS.events.conference.TRACK_ADDED,
      (track) => {
        if (!track.isLocal()) {
          this.remoteTracks[track.getParticipantId()] = track;
          // Attach to video element
          const video = document.createElement('video');
          track.attach(video);
          this.updateGridLayout();
        }
      }
    );
  }
  
  // Voice commands
  async handleVoiceCommand(command) {
    if (command.includes("call")) {
      const contact = this.extractContact(command);
      await this.connect(`family-${contact}`);
    } else if (command.includes("hang up")) {
      await this.hangup();
    } else if (command.includes("mute")) {
      this.toggleMute();
    }
  }
}
```

### 2.3 Assistant Agent

**Purpose:** General queries, screen content interpretation, companion conversation

```python
# /opt/nanoclaw/agents/assistant/assistant.py
from nanoclaw import Agent
import cv2  # For USB capture frame grabs

class AssistantAgent(Agent):
    def __init__(self):
        self.memory = SQLiteMemory()
        self.vision_client = None  # Claude/GPT-4o for vision
        
    async def handle_query(self, text, context=None):
        """Handle general assistant queries"""
        
        # Check if query is about screen content
        if self.is_screen_query(text):
            # Grab frame from HDMI capture
            frame = self.capture_screen_frame()
            response = await self.vision_query(text, frame)
        else:
            # Standard conversation
            response = await self.conversation(text, context)
        
        # Speak response
        await self.speak(response)
        
        # Store in memory
        self.memory.add_exchange(text, response)
    
    def capture_screen_frame(self):
        """Grab current frame from TV via USB HDMI capture"""
        cap = cv2.VideoCapture('/dev/video0')
        ret, frame = cap.read()
        cap.release()
        return frame
    
    async def vision_query(self, question, frame):
        """Send frame + question to vision model"""
        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        image_base64 = base64.b64encode(buffer).decode()
        
        # Query Claude/GPT-4o
        response = await self.vision_client.query(
            image=image_base64,
            question=question
        )
        return response
```

### 2.4 Health Monitor Agent

**Purpose:** Medication reminders, check-ins, emergency detection

```python
# /opt/nanoclaw/agents/health-monitor/health.py
from nanoclaw import Agent
from datetime import datetime, timedelta

class HealthMonitorAgent(Agent):
    def __init__(self):
        self.schedule = SQLiteSchedule()
        
    async def run(self):
        """Background health monitoring loop"""
        while True:
            await self.check_medication_reminders()
            await self.check_daily_checkin()
            await asyncio.sleep(60)  # Check every minute
    
    async def check_medication_reminders(self):
        """Check if any medications are due"""
        due_meds = self.schedule.get_due_medications()
        
        for med in due_meds:
            # Voice reminder
            await self.speak(
                f"It's time to take your {med.name}. "
                f"Dosage: {med.dosage}. "
                f"Say 'taken' when you've taken it."
            )
            
            # Wait for confirmation (with timeout)
            response = await self.listen_for_confirmation(timeout=300)
            
            if response and "taken" in response.lower():
                self.schedule.mark_taken(med.id)
            else:
                # Escalate: notify family member
                await self.notify_family(med)
    
    async def emergency_detection(self, audio_stream):
        """Monitor for emergency keywords (fall, help, etc.)"""
        # Continuous audio analysis
        keywords = ["help", "fallen", "can't get up", "emergency"]
        
        if any(kw in audio_stream for kw in keywords):
            await self.trigger_emergency_protocol()
    
    async def trigger_emergency_protocol(self):
        """Emergency: Contact family, notify services"""
        await self.speak(
            "Emergency detected. Contacting your emergency contact."
        )
        
        # Auto-dial family member via video
        await self.dispatch_to("video-chat", "emergency-call-family")
        
        # Log incident
        self.log_emergency(datetime.now())
```

---

## Phase 3: Hardware Integration (Week 5)

### 3.1 USB HDMI Capture Setup

```bash
# Identify capture device
v4l2-ctl --list-devices

# Should show: USB Video (HDMI capture dongle)

# Test capture
ffmpeg -f v4l2 -i /dev/video0 -vframes 1 test.jpg

# Configure for Jitsi (720p30, hardware accelerated)
v4l2-ctl --device=/dev/video0 --set-fmt-video=width=1280,height=720,pixelformat=MJPG
```

### 3.2 Audio Configuration

```bash
# ReSpeaker 4-mic HAT setup (recommended)
# Install drivers
git clone https://github.com/respeaker/seeed-voicecard.git
cd seeed-voicecard
sudo ./install.sh

# Configure audio
# /etc/asound.conf
pcm.!default {
    type asym
    playback.pcm "playback"
    capture.pcm "capture"
}

pcm.playback {
    type plug
    slave.pcm "hw:0,0"  # HDMI audio out
}

pcm.capture {
    type plug
    slave.pcm "hw:1,0"  # ReSpeaker mic array
}
```

### 3.3 Hardware Acceleration

**Video Decode:**
- Pi 5 has hardware H.264 decoder
- Jitsi should use hardware-accelerated decode when available
- Reduces CPU usage from 80% to ~20% for 720p

**Configuration:**
```javascript
// Enable hardware acceleration in Jitsi
config.videoQuality = {
  preferredCodec: 'H264',
  disabledCodec: 'VP8,VP9',  // Pi handles H264 better
  enableHardwareAcceleration: true
};
```

---

## Phase 4: Network & Security (Week 6)

### 4.1 Tailscale Mesh VPN

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate (one-time setup)
sudo tailscale up --advertise-exit-node

# Verify Pi is on mesh
tailscale status
```

**Why Tailscale:**
- No port forwarding needed (elder's home router untouched)
- WireGuard encryption (fast on Pi 5)
- Direct Pi-to-Pi connections (lowest latency for family calls)
- Remote management access for support

### 4.2 Container Isolation (NanoClaw Security)

```yaml
# /opt/nanoclaw/docker-compose.yml
version: '3.8'

services:
  voice-controller:
    build: ./agents/voice-controller
    container_name: nanoclaw-voice
    devices:
      - /dev/snd:/dev/snd  # Audio devices only
    volumes:
      - ./data/voice:/data  # Isolated storage
    networks:
      - nanoclaw-internal
    
  video-chat:
    build: ./agents/video-chat
    container_name: nanoclaw-video
    devices:
      - /dev/video0:/dev/video0  # HDMI capture only
      - /dev/snd:/dev/snd
    volumes:
      - ./data/video:/data
    networks:
      - nanoclaw-internal
      - tailscale-net  # Only video needs external
    
  assistant:
    build: ./agents/assistant
    container_name: nanoclaw-assistant
    volumes:
      - ./data/assistant:/data
    networks:
      - nanoclaw-internal
      - tailscale-net
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    
  health-monitor:
    build: ./agents/health-monitor
    container_name: nanoclaw-health
    volumes:
      - ./data/health:/data
    networks:
      - nanoclaw-internal

networks:
  nanoclaw-internal:
    internal: true  # No external access
  tailscale-net:
    external: true  # Managed by Tailscale
```

---

## Phase 5: Testing & Deployment (Week 7-8)

### 5.1 Testing Matrix

| Test | Scenario | Expected Result |
|------|----------|----------------|
| Voice wake | Say "Hey Hearth" | Agent wakes, listens for command |
| Video call | "Call my daughter" | Connects to family member's Pi |
| Screen query | "What's that ingredient?" | Captures TV frame, answers via voice |
| Medication reminder | Scheduled time | Voice reminder, waits for confirmation |
| Emergency keyword | "I've fallen" | Auto-calls emergency contact |
| Network failure | Disconnect WiFi | Graceful degradation, reconnection |
| Multi-party | Join class with 10 people | Grid layout, audio prioritization |

### 5.2 Deployment Script

```bash
#!/bin/bash
# /opt/nanoclaw/deploy.sh

set -e

echo "=== WeStream NanoClaw Deployment ==="

# 1. System prep
sudo apt update
sudo apt install -y docker.io docker-compose nodejs npm

# 2. Install NanoClaw
git clone https://github.com/qwibitai/nanoclaw.git /opt/nanoclaw
cd /opt/nanoclaw

# 3. Build agents
docker-compose build

# 4. Start services
docker-compose up -d

# 5. Configure Tailscale
sudo tailscale up --authkey ${TAILSCALE_AUTH_KEY}

# 6. Test voice
python3 test-voice.py

# 7. Test video
node test-video.js

echo "=== Deployment Complete ==="
echo "Tailscale IP: $(tailscale ip -4)"
echo "Status: $(docker-compose ps)"
```

---

## Resource Requirements

### Raspberry Pi 5 (4GB)
- **CPU:** 30-50% during video call (hardware decode)
- **RAM:** 1.5GB baseline, 2.5GB during video
- **Storage:** 16GB microSD minimum, 32GB recommended
- **Network:** 5 Mbps upstream minimum for 720p

### Cloud Infrastructure
- **Jitsi VideoBridge:** 1 vCPU, 2GB RAM per 100 concurrent users
- **Tailscale:** Free tier sufficient (up to 20 devices)
- **Claude API:** ~$0.01-0.05 per vision query

---

## Cost Breakdown (Per Unit)

| Component | Cost |
|-----------|------|
| Raspberry Pi 5 (4GB) | $60 |
| ReSpeaker 4-mic HAT | $25 |
| USB HDMI Capture | $20 |
| Case + PSU | $15 |
| microSD 32GB | $10 |
| **Total Hardware** | **$130** |
| Tailscale (free tier) | $0 |
| Claude API (vision queries) | ~$5/mo |
| Jitsi hosting (self-hosted) | $10/mo |
| **Total Monthly** | **~$15** |

---

## Next Steps

1. **Week 1:** Order Pi 5 hardware, set up development environment
2. **Week 2:** Install NanoClaw base, configure Docker
3. **Week 3:** Implement Voice Controller agent
4. **Week 4:** Integrate Jitsi VideoBridge client
5. **Week 5:** Hardware integration (audio, HDMI capture)
6. **Week 6:** Security hardening, Tailscale mesh
7. **Week 7:** End-to-end testing with family beta
8. **Week 8:** Production deployment, support documentation

---

## Key Advantages of This Architecture

1. **Privacy First:** All elder data stays local (SQLite), only video traverses network
2. **Fault Isolation:** Each agent in separate container, one crash doesn't bring down system
3. **Voice-First:** Zero UI complexity for elderly users
4. **Family-Connected:** Direct Pi-to-Pi calls via Tailscale mesh
5. **Scalable:** New agents can be added (games, telehealth, etc.) without affecting core
6. **Affordable:** $130 hardware, $15/month operational cost

---

*Implementation Plan for WeStream/Hearth*
*Target: Raspberry Pi 5 / Orange Pi*
*Platform: NanoClaw with Jitsi VideoBridge*
*Date: February 27, 2026*