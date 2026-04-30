Evil Mentor — Complete Frontend & Backend Architecture

Based on the real ArmorClaw/OpenClaw integration, here's the exact architecture with clear separation of frontend and backend components.

---

Complete System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DEVELOPER'S MACHINE                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐    │
│  │                         FRONTEND LAYER (User Interface)                 │    │
│  ├────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                         │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │    │
│  │  │   Telegram   │  │    Slack     │  │   Discord    │  │  Web Dash- │ │    │
│  │  │     Bot      │  │     Bot      │  │     Bot      │  │   board    │ │    │
│  │  │  (Primary)   │  │  (Optional)  │  │  (Optional)  │  │  (React)   │ │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘ │    │
│  │         │                 │                 │                 │       │    │
│  │         └─────────────────┴─────────────────┴─────────────────┘       │    │
│  │                                    │                                   │    │
│  │                              HTTP/WebSocket                            │    │
│  └────────────────────────────────────┼───────────────────────────────────┘    │
│                                       │                                        │
│  ┌────────────────────────────────────┼───────────────────────────────────┐    │
│  │                         BACKEND LAYER (OpenClaw + Plugins)              │    │
│  ├────────────────────────────────────┼───────────────────────────────────┤    │
│  │                                    ▼                                   │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │    │
│  │  │                    OPENCLAW GATEWAY (Core)                       │   │    │
│  │  │  • Message Router                                                │   │    │
│  │  │  • Plugin Manager                                                │   │    │
│  │  │  • Session Management                                            │   │    │
│  │  │  • Tool Registry                                                 │   │    │
│  │  └────────────────────────────┬────────────────────────────────────┘   │    │
│  │                               │                                         │    │
│  │  ┌────────────────────────────┼────────────────────────────────────┐   │    │
│  │  │                    EVIL MENTOR PLUGIN (Your Backend)             │   │    │
│  │  ├─────────────────────────────────────────────────────────────────┤   │    │
│  │  │                                                                  │   │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │   │    │
│  │  │  │              MESSAGE HANDLERS (Chat Interface)            │  │   │    │
│  │  │  │  • /train - Trigger vulnerability injection              │  │   │    │
│  │  │  │  • /grade - Grade scan results                           │  │   │    │
│  │  │  │  • /stats - Show user statistics                         │  │   │    │
│  │  │  │  • /leaderboard - Show rankings                          │  │   │    │
│  │  │  │  • /optout - Disable training                            │  │   │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │   │    │
│  │  │                                                                  │   │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │   │    │
│  │  │  │           VULNERABILITY ENGINE (Core Logic)               │  │   │    │
│  │  │  │  • Code Context Analyzer                                  │  │   │    │
│  │  │  │  • LLM Prompt Manager                                     │  │   │    │
│  │  │  │  • Injection Generator                                    │  │   │    │
│  │  │  │  • File System Modifier                                   │  │   │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │   │    │
│  │  │                                                                  │   │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │   │    │
│  │  │  │              GRADING ENGINE (Assessment)                  │  │   │    │
│  │  │  │  • Scan Result Parser                                     │  │   │    │
│  │  │  │  • Scoring Algorithm                                      │  │   │    │
│  │  │  │  • Feedback Generator                                     │  │   │    │
│  │  │  │  • Statistics Calculator                                  │  │   │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │   │    │
│  │  │                                                                  │   │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │   │    │
│  │  │  │              DATABASE ACCESS LAYER                         │  │   │    │
│  │  │  │  • User Repository                                         │  │   │    │
│  │  │  │  • Injection Repository                                    │  │   │    │
│  │  │  │  • Score Repository                                        │  │   │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │   │    │
│  │  └─────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                          │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │    │
│  │  │                    ARMORCLAW SECURITY PLUGIN                      │   │    │
│  │  │  • Intent Token Requestor                                        │   │    │
│  │  │  • Policy Verifier                                               │   │    │
│  │  │  • Cryptographic Proof Generator                                 │   │    │
│  │  │  • Audit Logger                                                  │   │    │
│  │  └─────────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                       │                                        │
│                                       ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         EXTERNAL SERVICES                                 │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │    │
│  │  │   ArmorIQ    │  │   OpenAI/    │  │  PostgreSQL  │  │   Redis    │  │    │
│  │  │   Backend    │  │   Gemini     │  │   Database   │  │   Cache    │  │    │
│  │  │              │  │              │  │              │  │            │  │    │
│  │  │ • IAP        │  │ • LLM API    │  │ • Users      │  │ • Sessions │  │    │
│  │  │ • Policies   │  │ • Embeddings │  │ • Scores     │  │ • Rate     │  │    │
│  │  │ • Audit Logs │  │              │  │ • Injections │  │   Limiting │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │    │
│  │                                                                          │    │
│  │  ┌──────────────┐  ┌──────────────┐                                    │    │
│  │  │   GitHub/    │  │   Docker     │                                    │    │
│  │  │   GitLab     │  │   Registry   │                                    │    │
│  │  │              │  │              │                                    │    │
│  │  │ • Webhooks   │  │ • Container  │                                    │    │
│  │  │ • API        │  │   Deployment │                                    │    │
│  │  └──────────────┘  └──────────────┘                                    │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

Exact Backend Components Needed

1. OpenClaw Gateway (Existing - Just Configure)

```yaml
# ~/.openclaw/config.yaml
gateway:
  port: 3000
  host: localhost
  
plugins:
  - name: evil-mentor
    enabled: true
    path: ./plugins/evil-mentor
    
  - name: armorclaw
    enabled: true
    config:
      apiKey: ${ARMORIQ_API_KEY}
      iapUrl: https://iap.armoriq.ai

chat:
  telegram:
    enabled: true
    botToken: ${TELEGRAM_BOT_TOKEN}
    
  webhook:
    enabled: true
    port: 8080
```

2. Evil Mentor Plugin Backend (You Build This)

File Structure:

```
~/.openclaw/plugins/evil-mentor/
├── package.json
├── index.js                 # Plugin entry point
├── src/
│   ├── handlers/
│   │   ├── messageHandler.js    # Chat command handlers
│   │   ├── trainingHandler.js   # /train command logic
│   │   ├── gradeHandler.js      # /grade command logic
│   │   └── statsHandler.js      # /stats, /leaderboard
│   ├── core/
│   │   ├── vulnerabilityEngine.js   # LLM injection generation
│   │   ├── gradingEngine.js         # Scoring algorithms
│   │   ├── contextAnalyzer.js       # Code context extraction
│   │   └── fileModifier.js          # Safe file injection
│   ├── database/
│   │   ├── models.js           # PostgreSQL models
│   │   ├── repositories.js     # Data access layer
│   │   └── migrations/         # Alembic migrations
│   ├── services/
│   │   ├── armorClawService.js # ArmorClaw API wrapper
│   │   ├── llmService.js       # OpenAI/Gemini wrapper
│   │   └── cacheService.js     # Redis caching
│   └── utils/
│       ├── logger.js           # Winston logging
│       ├── security.js         # Input validation
│       └── helpers.js          # Utility functions
├── tests/
└── dashboard/                  # Optional web dashboard (see frontend)
```

3. Database Schema (PostgreSQL)

```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_id VARCHAR(255) UNIQUE NOT NULL,  -- Telegram/Slack user ID
    platform_type VARCHAR(50) NOT NULL,        -- 'telegram', 'slack', 'discord'
    username VARCHAR(255),
    display_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    opt_out BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Training sessions (each /train creates a session)
CREATE TABLE training_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    intent_id VARCHAR(255) UNIQUE NOT NULL,     -- From ArmorIQ
    repo_path TEXT,
    branch VARCHAR(255),
    status VARCHAR(50) DEFAULT 'injected',      -- 'injected', 'scanned', 'graded'
    injected_at TIMESTAMP DEFAULT NOW(),
    scanned_at TIMESTAMP,
    graded_at TIMESTAMP
);

-- Injected vulnerabilities
CREATE TABLE injections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES training_sessions(id),
    injection_type VARCHAR(50),                 -- 'SQL_INJECTION', 'XSS', etc.
    difficulty VARCHAR(20),                     -- 'EASY', 'MEDIUM', 'HARD'
    file_path TEXT,
    line_number INTEGER,
    original_code TEXT,
    injected_code TEXT,
    description TEXT,
    detected BOOLEAN DEFAULT false,
    detection_time_ms INTEGER
);

-- Scan results (from ArmorClaw)
CREATE TABLE scan_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES training_sessions(id),
    scan_duration_seconds INTEGER,
    total_findings INTEGER,
    detected_injections INTEGER,
    false_positives INTEGER,
    raw_output JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Grades and scores
CREATE TABLE grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES training_sessions(id),
    score INTEGER,
    letter_grade VARCHAR(2),
    speed_bonus INTEGER,
    missed_penalty INTEGER,
    fp_penalty INTEGER,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Leaderboard cache (denormalized for performance)
CREATE TABLE leaderboard (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    total_score INTEGER DEFAULT 0,
    sessions_completed INTEGER DEFAULT 0,
    avg_score DECIMAL(5,2),
    best_score INTEGER,
    weakest_area VARCHAR(50),
    rank INTEGER,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sessions_user ON training_sessions(user_id);
CREATE INDEX idx_sessions_status ON training_sessions(status);
CREATE INDEX idx_injections_session ON injections(session_id);
CREATE INDEX idx_injections_detected ON injections(detected);
CREATE INDEX idx_grades_score ON grades(score);
```

4. Redis Cache Structure

```javascript
// Redis key patterns for caching
const RedisKeys = {
  // User session cache (TTL: 1 hour)
  userSession: (userId) => `user:session:${userId}`,
  
  // Rate limiting (TTL: 24 hours)
  rateLimit: (userId) => `ratelimit:${userId}:${new Date().toDateString()}`,
  
  // LLM response cache (TTL: 1 hour)
  llmCache: (promptHash) => `llm:cache:${promptHash}`,
  
  // Leaderboard cache (TTL: 5 minutes)
  leaderboard: 'leaderboard:cache',
  
  // Active training sessions (TTL: 2 hours)
  activeSession: (sessionId) => `session:active:${sessionId}`
};
```

---

Exact Frontend Components Needed

Option A: Chat Interface (Primary - Required)

No frontend code needed! The chat platforms are the frontend:

· Telegram Bot (recommended primary)
· Slack Bot (for enterprise teams)
· Discord Bot (for community)

Option B: Web Dashboard (Optional - For Managers)

If you want a web dashboard, build this React app:

Dashboard Architecture:

```
dashboard/
├── package.json
├── src/
│   ├── App.jsx
│   ├── index.css
│   ├── api/
│   │   └── client.js          # Axios configuration
│   ├── components/
│   │   ├── Layout/
│   │   │   ├── Header.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   └── Footer.jsx
│   │   ├── Dashboard/
│   │   │   ├── StatsCards.jsx      # KPI cards
│   │   │   ├── Leaderboard.jsx     # Rankings table
│   │   │   ├── ProgressChart.jsx   # Recharts line chart
│   │   │   └── WeakAreasChart.jsx  # Bar chart
│   │   ├── Training/
│   │   │   ├── SessionHistory.jsx
│   │   │   ├── SessionDetails.jsx
│   │   │   └── VulnerabilityList.jsx
│   │   └── User/
│   │       ├── UserProfile.jsx
│   │       ├── UserStats.jsx
│   │       └── UserSettings.jsx
│   ├── pages/
│   │   ├── DashboardPage.jsx
│   │   ├── TrainingPage.jsx
│   │   ├── LeaderboardPage.jsx
│   │   └── SettingsPage.jsx
│   ├── hooks/
│   │   ├── useAuth.js
│   │   ├── useWebSocket.js
│   │   └── useTraining.js
│   └── utils/
│       └── formatters.js
```

Dashboard Backend API Endpoints (Add to Plugin):

```javascript
// Add to evil-mentor plugin: src/api/routes.js
// These endpoints serve the React dashboard

const express = require('express');
const router = express.Router();

// Auth middleware (verify ArmorIQ token)
router.use(async (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'No token' });
  
  const valid = await armorClaw.verifyToken(token);
  if (!valid) return res.status(401).json({ error: 'Invalid token' });
  
  req.userId = valid.userId;
  next();
});

// Get user statistics
router.get('/api/user/stats', async (req, res) => {
  const stats = await gradeRepo.getUserStats(req.userId);
  res.json(stats);
});

// Get leaderboard
router.get('/api/leaderboard', async (req, res) => {
  const limit = req.query.limit || 50;
  const leaderboard = await gradeRepo.getLeaderboard(limit);
  res.json(leaderboard);
});

// Get training sessions
router.get('/api/sessions', async (req, res) => {
  const { page = 1, limit = 20 } = req.query;
  const sessions = await sessionRepo.getUserSessions(req.userId, page, limit);
  res.json(sessions);
});

// Get session details
router.get('/api/sessions/:sessionId', async (req, res) => {
  const session = await sessionRepo.getSessionWithDetails(req.params.sessionId);
  if (!session) return res.status(404).json({ error: 'Not found' });
  res.json(session);
});

// Get real-time updates (WebSocket)
const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8081 });

wss.on('connection', (ws, req) => {
  const userId = req.headers['x-user-id'];
  ws.on('message', async (data) => {
    const { type, sessionId } = JSON.parse(data);
    if (type === 'subscribe') {
      // Subscribe to session updates
      subscribeToSession(ws, sessionId, userId);
    }
  });
});

module.exports = router;
```

React Dashboard Component Example:

```jsx
// dashboard/src/pages/DashboardPage.jsx
import React, { useState, useEffect } from 'react';
import { StatsCards } from '../components/Dashboard/StatsCards';
import { Leaderboard } from '../components/Dashboard/Leaderboard';
import { ProgressChart } from '../components/Dashboard/ProgressChart';
import { apiClient } from '../api/client';

export const DashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [progress, setProgress] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, leaderboardRes, progressRes] = await Promise.all([
          apiClient.get('/api/user/stats'),
          apiClient.get('/api/leaderboard'),
          apiClient.get('/api/user/progress')
        ]);
        
        setStats(statsRes.data);
        setLeaderboard(leaderboardRes.data);
        setProgress(progressRes.data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
    
    // WebSocket for real-time updates
    const ws = new WebSocket('ws://localhost:8081');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'new_grade') {
        // Refresh dashboard
        fetchData();
      }
    };
    
    return () => ws.close();
  }, []);
  
  if (loading) return <div>Loading dashboard...</div>;
  
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-4xl font-bold mb-8">Evil Mentor Dashboard</h1>
        
        <StatsCards stats={stats} />
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-8">
          <div className="lg:col-span-2">
            <ProgressChart data={progress} />
          </div>
          <div>
            <Leaderboard users={leaderboard} currentUserId={stats?.userId} />
          </div>
        </div>
      </div>
    </div>
  );
};
```

---

Data Flow Diagrams

Flow 1: Vulnerability Injection (/train command)

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐     ┌──────────┐
│  User   │     │ Telegram │     │ OpenClaw │     │ Evil    │     │ ArmorClaw│
│         │     │   Bot    │     │ Gateway  │     │ Mentor  │     │ Plugin   │
└────┬────┘     └────┬─────┘     └────┬─────┘     └────┬────┘     └────┬─────┘
     │               │                │                │              │
     │  "/train"     │                │                │              │
     │──────────────>│                │                │              │
     │               │  Webhook POST  │                │              │
     │               │───────────────>│                │              │
     │               │                │  Route to      │              │
     │               │                │  plugin        │              │
     │               │                │───────────────>│              │
     │               │                │                │              │
     │               │                │                │ Request      │
     │               │                │                │ Intent Token │
     │               │                │                │─────────────>│
     │               │                │                │              │
     │               │                │                │ Intent Token │
     │               │                │                │<─────────────│
     │               │                │                │              │
     │               │                │                │ Verify       │
     │               │                │                │ Policies     │
     │               │                │                │─────────────>│
     │               │                │                │              │
     │               │                │                │ Policy Result│
     │               │                │                │<─────────────│
     │               │                │                │              │
     │               │                │                │ Generate     │
     │               │                │                │ Vulnerability│
     │               │                │                │ (LLM)        │
     │               │                │                │              │
     │               │                │                │ Apply to     │
     │               │                │                │ File System  │
     │               │                │                │              │
     │               │                │                │ Log to       │
     │               │                │                │ Database     │
     │               │                │                │              │
     │               │                │  Response      │              │
     │               │                │<───────────────│              │
     │               │  Send Message  │                │              │
     │               │<───────────────│                │              │
     │  Bot Reply    │                │                │              │
     │<──────────────│                │                │              │
     │               │                │                │              │
```

Flow 2: Grading (/grade command)

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  User   │     │ Telegram │     │ OpenClaw │     │  Evil    │     │ ArmorClaw│     │Database  │
│         │     │   Bot    │     │ Gateway  │     │  Mentor  │     │  Plugin  │     │(Postgres)│
└────┬────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │               │                │                │                │               │
     │  "/grade"     │                │                │                │               │
     │──────────────>│                │                │                │               │
     │               │  Webhook       │                │                │               │
     │               │───────────────>│                │                │               │
     │               │                │  Route to      │                │               │
     │               │                │  plugin        │                │               │
     │               │                │───────────────>│                │               │
     │               │                │                │                │               │
     │               │                │                │ Get scan       │               │
     │               │                │                │ results from   │               │
     │               │                │                │ ArmorClaw      │               │
     │               │                │                │───────────────>│               │
     │               │                │                │                │               │
     │               │                │                │ Scan results   │               │
     │               │                │                │<───────────────│               │
     │               │                │                │                │               │
     │               │                │                │ Get injection  │               │
     │               │                │                │ history        │               │
     │               │                │                │───────────────────────────────>│
     │               │                │                │                │               │
     │               │                │                │ Injected vulns │               │
     │               │                │                │<───────────────────────────────│
     │               │                │                │                │               │
     │               │                │                │ Calculate      │               │
     │               │                │                │ score          │               │
     │               │                │                │                │               │
     │               │                │                │ Generate       │               │
     │               │                │                │ feedback (LLM) │               │
     │               │                │                │                │               │
     │               │                │                │ Save grade     │               │
     │               │                │                │───────────────────────────────>│
     │               │                │                │                │               │
     │               │                │                │ Update         │               │
     │               │                │                │ leaderboard    │               │
     │               │                │                │───────────────────────────────>│
     │               │                │                │                │               │
     │               │                │  Response      │                │               │
     │               │                │<───────────────│                │               │
     │               │  Send Score    │                │                │               │
     │               │<───────────────│                │                │               │
     │  Score +      │                │                │                │               │
     │  Feedback     │                │                │                │               │
     │<──────────────│                │                │                │               │
     │               │                │                │                │               │
```

---

Deployment Configuration

Docker Compose (Full Stack)

```yaml
# docker-compose.yml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: evil_mentor
      POSTGRES_USER: evil_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    networks:
      - evil-mentor-network

  # Redis Cache
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    networks:
      - evil-mentor-network

  # OpenClaw Gateway with Evil Mentor Plugin
  openclaw:
    image: openclaw/gateway:latest
    environment:
      ARMORIQ_API_KEY: ${ARMORIQ_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      DATABASE_URL: postgresql://evil_user:${DB_PASSWORD}@postgres:5432/evil_mentor
      REDIS_URL: redis://redis:6379
    volumes:
      - ./plugins/evil-mentor:/app/plugins/evil-mentor
      - ~/workspace:/workspace  # Developer code access
    ports:
      - "3000:3000"  # OpenClaw API
      - "8080:8080"  # Webhook endpoint
    depends_on:
      - postgres
      - redis
    networks:
      - evil-mentor-network

  # React Dashboard (Optional)
  dashboard:
    build: ./dashboard
    environment:
      API_URL: http://openclaw:3000
      WS_URL: ws://openclaw:8081
    ports:
      - "3001:3000"
    depends_on:
      - openclaw
    networks:
      - evil-mentor-network

  # Nginx (Reverse Proxy)
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - openclaw
      - dashboard
    networks:
      - evil-mentor-network

volumes:
  postgres_data:

networks:
  evil-mentor-network:
    driver: bridge
```

Environment Variables (.env)

```bash
# ArmorIQ
ARMORIQ_API_KEY=your_key_here
ARMORIQ_IAP_URL=https://iap.armoriq.ai

# LLM Provider
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Chat Platforms (choose one)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
SLACK_BOT_TOKEN=xoxb-...
DISCORD_BOT_TOKEN=...

# Database
DB_PASSWORD=secure_password_here

# Evil Mentor Settings
TRAINING_START_HOUR=9
TRAINING_END_HOUR=18
MAX_INJECTIONS_PER_DAY=10
BLOCKED_BRANCHES=main,master,production
```

---

Summary Table: What You Actually Need to Build

Component Type Build from Scratch? Complexity
Telegram/Slack/Discord Bot Frontend ❌ No (use existing platforms) Easy
React Dashboard Frontend ✅ Yes (optional) Medium
OpenClaw Gateway Backend ❌ No (install from docs) Easy
ArmorClaw Plugin Backend ❌ No (install from docs) Easy
Evil Mentor Plugin Backend ✅ Yes (your core code) Hard
Vulnerability Engine Backend ✅ Yes (LLM integration) Hard
Grading Engine Backend ✅ Yes (scoring logic) Medium
Database Backend ✅ Yes (schema + repos) Medium
Redis Cache Backend ❌ No (install) Easy
ArmorIQ Integration Backend ❌ No (use their SDK) Easy

Your Development Focus (80% of work):

1. Evil Mentor Plugin (src/core/vulnerabilityEngine.js)
2. Grading Engine (src/core/gradingEngine.js)
3. Database Layer (src/database/repositories.js)
4. Chat Handlers (src/handlers/*.js)
5. React Dashboard (optional, dashboard/src/)

Leveraged Infrastructure (20% of work):

· OpenClaw Gateway (configuration only)
· ArmorClaw Plugin (configuration only)
· PostgreSQL/Redis (docker-compose)
· ChatGPT API (prompt engineering)

Want me to provide the actual code for any specific component from the above architecture?