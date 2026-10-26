"""Developer Portal UI for FaceAPI."""

from __future__ import annotations

from fastapi.responses import HTMLResponse

PORTAL_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FaceAPI Developer Portal | Fakhri AI Services</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(17, 24, 39, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.25);
      --primary: #6366f1;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      line-height: 1.6;
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.10) 0px, transparent 50%);
      background-attachment: fixed;
    }
    header {
      border-bottom: 1px solid var(--card-border);
      backdrop-filter: blur(16px);
      position: sticky;
      top: 0;
      z-index: 50;
      background: rgba(11, 15, 25, 0.85);
    }
    .header-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 1rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-weight: 800;
      font-size: 1.25rem;
      letter-spacing: -0.02em;
    }
    .brand-badge {
      font-size: 0.7rem;
      font-weight: 700;
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .nav-links {
      display: flex;
      gap: 1.5rem;
      align-items: center;
    }
    .nav-link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 600;
      transition: color 0.2s;
    }
    .nav-link:hover, .nav-link.active {
      color: #fff;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-family: inherit;
      font-size: 0.875rem;
      font-weight: 600;
      padding: 0.6rem 1.2rem;
      border-radius: 0.5rem;
      cursor: pointer;
      transition: all 0.2s;
      border: none;
      text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
      box-shadow: 0 4px 14px var(--accent-glow);
    }
    .btn-primary:hover {
      background: linear-gradient(135deg, #059669, #047857);
      transform: translateY(-1px);
    }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.06);
      color: #fff;
      border: 1px solid var(--card-border);
    }
    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.12);
    }
    .btn-danger {
      background: rgba(239, 68, 68, 0.15);
      color: #ef4444;
      border: 1px solid rgba(239, 68, 68, 0.25);
    }
    .btn-danger:hover {
      background: #ef4444;
      color: #fff;
    }
    main {
      flex: 1;
      max-width: 1200px;
      margin: 0 auto;
      padding: 2.5rem 1.5rem;
      width: 100%;
    }
    .hero {
      text-align: center;
      margin-bottom: 3.5rem;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.25);
      color: #10b981;
      padding: 0.35rem 0.9rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 1.25rem;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 10px #10b981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .hero h1 {
      font-size: 3rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.15;
      margin-bottom: 1rem;
      background: linear-gradient(135deg, #fff 40%, #94a3b8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero p {
      font-size: 1.15rem;
      color: var(--text-muted);
      max-width: 650px;
      margin: 0 auto 1.75rem auto;
    }
    .base-url-box {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--card-border);
      padding: 0.5rem 1rem;
      border-radius: 0.6rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      color: #38bdf8;
    }
    .tabs {
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 2rem;
      overflow-x: auto;
    }
    .tab-btn {
      background: none;
      border: none;
      font-family: inherit;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.95rem;
      padding: 0.75rem 1.25rem;
      cursor: pointer;
      position: relative;
      transition: color 0.2s;
    }
    .tab-btn:hover { color: #fff; }
    .tab-btn.active {
      color: #10b981;
    }
    .tab-btn.active::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: #10b981;
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      padding: 1.75rem;
      backdrop-filter: blur(12px);
      margin-bottom: 1.5rem;
    }
    .card-title {
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 0.75rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .card-desc {
      color: var(--text-muted);
      font-size: 0.925rem;
      margin-bottom: 1.25rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }
    th, td {
      padding: 0.85rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--card-border);
    }
    th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      background: rgba(255, 255, 255, 0.06);
      padding: 0.2rem 0.4rem;
      border-radius: 0.3rem;
      color: #38bdf8;
    }
    pre {
      background: #070a12;
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      padding: 1.25rem;
      overflow-x: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      color: #e2e8f0;
      line-height: 1.5;
    }
    .endpoint-badge {
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.25rem 0.55rem;
      border-radius: 0.35rem;
      text-transform: uppercase;
    }
    .badge-post { background: rgba(16, 185, 129, 0.2); color: #10b981; }
    .badge-get { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
    .form-group {
      margin-bottom: 1.25rem;
    }
    .form-group label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 0.4rem;
      color: var(--text-muted);
    }
    .form-input {
      width: 100%;
      padding: 0.65rem 0.9rem;
      border-radius: 0.5rem;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--card-border);
      color: #fff;
      font-family: inherit;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.2s;
    }
    .form-input:focus {
      border-color: #10b981;
    }
    .subtabs {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .subtab-btn {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--card-border);
      padding: 0.4rem 0.8rem;
      border-radius: 0.4rem;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
    }
    .subtab-btn.active {
      background: #10b981;
      color: #fff;
      border-color: #10b981;
    }
    .copy-btn {
      position: absolute;
      top: 0.75rem;
      right: 0.75rem;
      padding: 0.35rem 0.7rem;
      font-size: 0.75rem;
    }
    .pre-wrap { position: relative; }
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.7);
      backdrop-filter: blur(8px);
      z-index: 100;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .modal.show { display: flex; }
    .modal-card {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      max-width: 500px;
      width: 100%;
      padding: 1.75rem;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    footer {
      border-top: 1px solid var(--card-border);
      padding: 2rem 1.5rem;
      text-align: center;
      color: var(--text-muted);
      font-size: 0.85rem;
    }
  </style>
</head>
<body>

  <header>
    <div class="header-inner">
      <div class="brand">
        <span>⚡ Fakhri FaceAPI</span>
        <span class="brand-badge">Cloud Engine</span>
      </div>
      <nav class="nav-links">
        <a href="#quickstart" class="nav-link active" onclick="switchTab('quickstart')">Quickstart</a>
        <a href="#keys" class="nav-link" onclick="switchTab('keys')">API Keys</a>
        <a href="#endpoints" class="nav-link" onclick="switchTab('endpoints')">API Reference</a>
        <a href="#code" class="nav-link" onclick="switchTab('code')">Code Snippets</a>
        <a href="#tester" class="nav-link" onclick="switchTab('tester')">Live Tester</a>
        <a href="/faceapi/docs" class="btn btn-secondary" target="_blank">Swagger Docs ↗</a>
      </nav>
    </div>
  </header>

  <main>
    <div class="hero">
      <div class="status-pill">
        <span class="status-dot"></span>
        <span>Face Recognition Engine Online · SFace & YuNet Loaded · Anti-Spoof Active</span>
      </div>
      <h1>Universal Facial Biometrics API</h1>
      <p>High-accuracy Face Recognition, 1:N Identification, and AI Passive Anti-Spoofing. Easily integrate Face Login and Attendance into any Next.js, React, Node.js, or Mobile application.</p>
      <div class="base-url-box">
        <span style="color:var(--text-muted);">API Base:</span>
        <span id="apiUrlTxt">https://hrms.fakhriitservices.com/faceapi</span>
        <button class="btn btn-secondary" style="padding:0.25rem 0.6rem; font-size:0.75rem;" onclick="copyText('https://hrms.fakhriitservices.com/faceapi')">Copy</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('quickstart')">🚀 Quickstart</button>
      <button class="tab-btn" onclick="switchTab('keys')">🔑 API Key Manager</button>
      <button class="tab-btn" onclick="switchTab('endpoints')">📖 API Endpoints</button>
      <button class="tab-btn" onclick="switchTab('code')">💻 Code Integration</button>
      <button class="tab-btn" onclick="switchTab('tester')">🧪 Live Tester</button>
    </div>

    <!-- TAB 1: QUICKSTART -->
    <div id="tab-quickstart" class="tab-pane active">
      <div class="card">
        <h2 class="card-title">⚡ 3-Minute Integration Guide</h2>
        <p class="card-desc">Connect FaceAPI to your website or mobile app in 3 simple steps.</p>
        
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:1.25rem; margin-bottom:1.5rem;">
          <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); padding:1.25rem; border-radius:0.5rem;">
            <div style="font-size:1.75rem; margin-bottom:0.5rem;">1️⃣</div>
            <h3 style="font-size:1.05rem; font-weight:700; margin-bottom:0.4rem;">Get an API Key</h3>
            <p style="color:var(--text-muted); font-size:0.875rem;">Go to the <a href="#keys" onclick="switchTab('keys')" style="color:#10b981;">API Key Manager</a> tab and generate an API key with 1 click.</p>
          </div>
          <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); padding:1.25rem; border-radius:0.5rem;">
            <div style="font-size:1.75rem; margin-bottom:0.5rem;">2️⃣</div>
            <h3 style="font-size:1.05rem; font-weight:700; margin-bottom:0.4rem;">Enrol User Faces</h3>
            <p style="color:var(--text-muted); font-size:0.875rem;">Send user photo + User ID to <code>/v1/enrol</code>. The face vector is generated and saved.</p>
          </div>
          <div style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); padding:1.25rem; border-radius:0.5rem;">
            <div style="font-size:1.75rem; margin-bottom:0.5rem;">3️⃣</div>
            <h3 style="font-size:1.05rem; font-weight:700; margin-bottom:0.4rem;">Face Login / Scan</h3>
            <p style="color:var(--text-muted); font-size:0.875rem;">Capture camera frame and call <code>/v1/identify</code>. Liveness is checked and matching ID returned!</p>
          </div>
        </div>

        <h3 style="font-size:1rem; font-weight:700; margin-bottom:0.75rem;">Quick cURL Test</h3>
        <div class="pre-wrap">
          <pre><code>curl -X POST "https://hrms.fakhriitservices.com/faceapi/v1/identify?collection=default" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "image=@camera_selfie.jpg"</code></pre>
          <button class="btn btn-secondary copy-btn" onclick="copyCode(this)">Copy</button>
        </div>
      </div>
    </div>

    <!-- TAB 2: API KEY MANAGER -->
    <div id="tab-keys" class="tab-pane">
      <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1.25rem;">
          <div>
            <h2 class="card-title">🔑 API Key Management</h2>
            <p class="card-desc">Generate and manage API keys for your external apps and services.</p>
          </div>
          <button class="btn btn-primary" onclick="openCreateKeyModal()">+ Generate New Key</button>
        </div>

        <div id="authPrompt" style="background:rgba(255,255,255,0.03); border:1px solid var(--card-border); border-radius:0.5rem; padding:1.5rem; text-align:center;">
          <h3 style="font-size:1.1rem; margin-bottom:0.5rem;">Enter Admin Token to Manage Keys</h3>
          <p style="color:var(--text-muted); font-size:0.875rem; margin-bottom:1rem;">Key creation is protected by your master admin token.</p>
          <div style="max-width:380px; margin:0 auto; display:flex; gap:0.5rem;">
            <input type="password" id="adminTokenInput" class="form-input" placeholder="Admin token...">
            <button class="btn btn-primary" onclick="verifyAdminToken()">Unlock</button>
          </div>
        </div>

        <div id="keysTableContainer" style="display:none;">
          <table>
            <thead>
              <tr>
                <th>Key Name</th>
                <th>Prefix</th>
                <th>Plan</th>
                <th>Usage (Month)</th>
                <th>Created</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="keysTableBody">
              <!-- Dynamic rows -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 3: API ENDPOINTS -->
    <div id="tab-endpoints" class="tab-pane">
      <div class="card">
        <h2 class="card-title">📖 API Endpoints Reference</h2>
        <p class="card-desc">All requests accept <code>multipart/form-data</code> for images and authenticate via <code>X-API-Key: &lt;key&gt;</code>.</p>

        <!-- Endpoint 1 -->
        <div style="border:1px solid var(--card-border); border-radius:0.5rem; padding:1.25rem; margin-bottom:1.25rem; background:rgba(0,0,0,0.2);">
          <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <span class="endpoint-badge badge-post">POST</span>
            <code style="font-size:1rem; color:#fff;">/v1/identify</code>
            <span style="color:#10b981; font-size:0.8rem; font-weight:600;">★ Core for Login & Attendance</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.875rem; margin-bottom:0.75rem;">Detects face, validates <strong>Passive Liveness (rejects photos / mobile screens)</strong>, and searches for matching user identity in the collection.</p>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem;">
            <div>
              <div style="font-size:0.8rem; font-weight:700; color:var(--text-muted); margin-bottom:0.25rem;">FORM FIELDS</div>
              <ul style="list-style:none; font-size:0.85rem; color:var(--text-muted);">
                <li>• <code>image</code> (File, required): Camera image snapshot</li>
                <li>• <code>collection</code> (Query, opt): e.g. <code>employees</code> or <code>students</code></li>
                <li>• <code>top_k</code> (Query, opt): Number of matches (default: 1)</li>
              </ul>
            </div>
            <div>
              <div style="font-size:0.8rem; font-weight:700; color:var(--text-muted); margin-bottom:0.25rem;">RESPONSE FIELDS</div>
              <ul style="list-style:none; font-size:0.85rem; color:var(--text-muted);">
                <li>• <code>matched</code> (bool): True if recognized</li>
                <li>• <code>external_id</code> (string): Your user/employee ID</li>
                <li>• <code>is_live</code> (bool): Anti-spoof test passed</li>
                <li>• <code>liveness_score</code> (float): 0.0 to 1.0 confidence</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Endpoint 2 -->
        <div style="border:1px solid var(--card-border); border-radius:0.5rem; padding:1.25rem; margin-bottom:1.25rem; background:rgba(0,0,0,0.2);">
          <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <span class="endpoint-badge badge-post">POST</span>
            <code style="font-size:1rem; color:#fff;">/v1/enrol</code>
            <span style="color:var(--text-muted); font-size:0.8rem; font-weight:600;">Register New Face</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.875rem; margin-bottom:0.75rem;">Enroll a user's face photo into a collection linked to an <code>external_id</code> (e.g. User ID, Student ID, Employee Code).</p>
          <ul style="list-style:none; font-size:0.85rem; color:var(--text-muted);">
            <li>• <code>image</code> (File, required): Clear face photo</li>
            <li>• <code>external_id</code> (Form, required): Your app's unique ID for this user</li>
            <li>• <code>collection</code> (Query, optional): Collection name (default: default)</li>
          </ul>
        </div>

        <!-- Endpoint 3 -->
        <div style="border:1px solid var(--card-border); border-radius:0.5rem; padding:1.25rem; margin-bottom:1.25rem; background:rgba(0,0,0,0.2);">
          <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <span class="endpoint-badge badge-post">POST</span>
            <code style="font-size:1rem; color:#fff;">/v1/verify</code>
            <span style="color:var(--text-muted); font-size:0.8rem; font-weight:600;">1-to-1 Match</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.875rem;">Verifies whether two photos belong to the same person (e.g. Live selfie vs ID Card photo).</p>
        </div>

        <!-- Endpoint 4 -->
        <div style="border:1px solid var(--card-border); border-radius:0.5rem; padding:1.25rem; background:rgba(0,0,0,0.2);">
          <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
            <span class="endpoint-badge badge-post">POST</span>
            <code style="font-size:1rem; color:#fff;">/v1/detect</code>
            <span style="color:var(--text-muted); font-size:0.8rem; font-weight:600;">Face Detection & Landmarks</span>
          </div>
          <p style="color:var(--text-muted); font-size:0.875rem;">Returns bounding boxes, landmarks (eyes, nose, mouth corners), and detection confidence for all faces in an image.</p>
        </div>

      </div>
    </div>

    <!-- TAB 4: CODE INTEGRATION -->
    <div id="tab-code" class="tab-pane">
      <div class="card">
        <h2 class="card-title">💻 Ready-to-Use Code Snippets</h2>
        <p class="card-desc">Copy-paste code examples to implement Face Login and Attendance in your projects.</p>

        <div class="subtabs">
          <button class="subtab-btn active" onclick="switchCode('nextjs')">Next.js / React (Face Login)</button>
          <button class="subtab-btn" onclick="switchCode('nodejs')">Node.js / Express</button>
          <button class="subtab-btn" onclick="switchCode('python')">Python</button>
          <button class="subtab-btn" onclick="switchCode('curl')">cURL Terminal</button>
        </div>

        <!-- NEXTJS -->
        <div id="code-nextjs" class="code-pane active">
          <div class="pre-wrap">
            <pre><code>// Next.js Frontend: Camera Face Login
import React, { useRef, useState } from 'react';

export default function FaceLogin() {
  const videoRef = useRef(null);
  const [status, setStatus] = useState('');

  // 1. Start Camera
  const startCamera = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (videoRef.current) videoRef.current.srcObject = stream;
  };

  // 2. Capture and Verify Face
  const handleScan = async () => {
    setStatus('Scanning face & checking liveness...');
    const video = videoRef.current;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);

    canvas.toBlob(async (blob) => {
      const formData = new FormData();
      formData.append('image', blob, 'face.jpg');

      const res = await fetch('https://hrms.fakhriitservices.com/faceapi/v1/identify?collection=users', {
        method: 'POST',
        headers: { 'X-API-Key': 'YOUR_API_KEY' },
        body: formData,
      });

      const data = await res.json();
      
      if (!data.is_live) {
        setStatus('❌ Spoof detected: ' + data.spoof_reason);
      } else if (data.matched) {
        setStatus('✅ Welcome back, User ID: ' + data.external_id);
        // Login successful -> Redirect to dashboard
      } else {
        setStatus('⚠️ Face not recognised');
      }
    }, 'image/jpeg', 0.9);
  };

  return (
    <div>
      <video ref={videoRef} autoPlay playsInline style={{ width: 400, borderRadius: 12 }} />
      <div>
        <button onClick={startCamera}>Start Camera</button>
        <button onClick={handleScan}>Login with Face</button>
      </div>
      <p>{status}</p>
    </div>
  );
}</code></pre>
            <button class="btn btn-secondary copy-btn" onclick="copyCode(this)">Copy</button>
          </div>
        </div>

        <!-- NODEJS -->
        <div id="code-nodejs" class="code-pane" style="display:none;">
          <div class="pre-wrap">
            <pre><code>// Node.js Backend: Verify Face
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

async function verifyFace(imagePath) {
  const form = new FormData();
  form.append('image', fs.createReadStream(imagePath));

  try {
    const response = await axios.post(
      'https://hrms.fakhriitservices.com/faceapi/v1/identify?collection=users',
      form,
      {
        headers: {
          ...form.getHeaders(),
          'X-API-Key': process.env.FACEAPI_KEY,
        },
      }
    );

    const { matched, external_id, is_live, spoof_reason } = response.data;

    if (!is_live) {
      return { success: false, error: 'Fake/Screen photo detected: ' + spoof_reason };
    }
    if (matched) {
      return { success: true, userId: external_id };
    }
    return { success: false, error: 'Face not recognised' };
  } catch (err) {
    console.error('FaceAPI error:', err.response?.data || err.message);
    throw err;
  }
}</code></pre>
            <button class="btn btn-secondary copy-btn" onclick="copyCode(this)">Copy</button>
          </div>
        </div>

        <!-- PYTHON -->
        <div id="code-python" class="code-pane" style="display:none;">
          <div class="pre-wrap">
            <pre><code># Python: Enrol and Identify
import requests

API_BASE = "https://hrms.fakhriitservices.com/faceapi"
API_KEY = "YOUR_API_KEY"

# 1. Enrol a new user face
def enrol_user(user_id, image_path):
    with open(image_path, "rb") as f:
        res = requests.post(
            f"{API_BASE}/v1/enrol?collection=users",
            headers={"X-API-Key": API_KEY},
            data={"external_id": user_id},
            files={"image": f}
        )
    return res.json()

# 2. Identify / Face Login
def identify_face(camera_image_path):
    with open(camera_image_path, "rb") as f:
        res = requests.post(
            f"{API_BASE}/v1/identify?collection=users",
            headers={"X-API-Key": API_KEY},
            files={"image": f}
        )
    data = res.json()
    if not data.get("is_live"):
        print(f"[REJECTED] Photo/Screen spoof: {data.get('spoof_reason')}")
        return None
    if data.get("matched"):
        print(f"[ACCEPTED] Logged in as: {data['external_id']}")
        return data['external_id']
    print("[UNKNOWN] Face not recognised")
    return None</code></pre>
            <button class="btn btn-secondary copy-btn" onclick="copyCode(this)">Copy</button>
          </div>
        </div>

        <!-- CURL -->
        <div id="code-curl" class="code-pane" style="display:none;">
          <div class="pre-wrap">
            <pre><code># 1. Enrol user
curl -X POST "https://hrms.fakhriitservices.com/faceapi/v1/enrol?collection=users" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "external_id=USER_101" \
  -F "image=@avatar.jpg"

# 2. Identify / Face Login
curl -X POST "https://hrms.fakhriitservices.com/faceapi/v1/identify?collection=users" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "image=@webcam_frame.jpg"

# 3. 1:1 Verify
curl -X POST "https://hrms.fakhriitservices.com/faceapi/v1/verify" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "image=@live_selfie.jpg" \
  -F "target_image=@id_card.jpg"</code></pre>
            <button class="btn btn-secondary copy-btn" onclick="copyCode(this)">Copy</button>
          </div>
        </div>

      </div>
    </div>

    <!-- TAB 5: TESTER -->
    <div id="tab-tester" class="tab-pane">
      <div class="card">
        <h2 class="card-title">🧪 Live API Playground</h2>
        <p class="card-desc">Upload a photo to test detection and passive anti-spoofing in real time.</p>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1.5rem;">
          <div>
            <div class="form-group">
              <label>API Key (Optional for internal, required for external)</label>
              <input type="text" id="testerKey" class="form-input" placeholder="fk_live_...">
            </div>
            <div class="form-group">
              <label>Select Photo</label>
              <input type="file" id="testerFile" class="form-input" accept="image/*">
            </div>
            <button class="btn btn-primary" style="width:100%;" onclick="runTester()">Test Liveness & Recognition</button>
          </div>
          <div>
            <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:0.4rem; color:var(--text-muted);">Response Output</label>
            <pre style="height:220px; overflow-y:auto;" id="testerOutput">// Click 'Test' to see output...</pre>
          </div>
        </div>
      </div>
    </div>

  </main>

  <!-- MODAL: CREATE KEY -->
  <div id="createKeyModal" class="modal">
    <div class="modal-card">
      <h3 style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem;">Generate New API Key</h3>
      <p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:1.25rem;">Create an API key for your application.</p>
      
      <div class="form-group">
        <label>Application Name / Label</label>
        <input type="text" id="newKeyName" class="form-input" placeholder="e.g. Attendance App, Student Portal">
      </div>
      <div class="form-group">
        <label>Plan</label>
        <select id="newKeyPlan" class="form-input">
          <option value="personal">Personal (Unlimited)</option>
          <option value="pro">Pro (1,000 req/min)</option>
        </select>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:0.75rem; margin-top:1.5rem;">
        <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="submitCreateKey()">Generate Key</button>
      </div>
    </div>
  </div>

  <!-- MODAL: SHOW NEW KEY -->
  <div id="showKeyModal" class="modal">
    <div class="modal-card">
      <div style="text-align:center; margin-bottom:1rem; font-size:2rem;">🎉</div>
      <h3 style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem; text-align:center;">Your API Key is Ready!</h3>
      <p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:1.25rem; text-align:center;">Save this key safely. You will not be able to view it again.</p>
      
      <div style="background:#070a12; border:1px solid #10b981; border-radius:0.5rem; padding:1rem; display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
        <code id="newKeySecret" style="word-break:break-all; font-size:0.9rem; color:#10b981;"></code>
        <button class="btn btn-secondary" onclick="copyNewKey()">Copy</button>
      </div>

      <button class="btn btn-primary" style="width:100%;" onclick="closeShowKeyModal()">Done</button>
    </div>
  </div>

  <footer>
    Fakhri FaceAPI & Biometrics Cloud Engine · Apache 2.0 ONNX YuNet + SFace · Passive Anti-Spoofing
  </footer>

  <script>
    let currentAdminToken = sessionStorage.getItem('faceapi_admin_token') || '';

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
      
      const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent.toLowerCase().includes(tabId));
      if (btn) btn.classList.add('active');
      const pane = document.getElementById('tab-' + tabId);
      if (pane) pane.classList.add('active');

      if (tabId === 'keys' && currentAdminToken) {
        loadKeys();
      }
    }

    function switchCode(lang) {
      document.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.code-pane').forEach(p => p.style.display = 'none');
      event.target.classList.add('active');
      document.getElementById('code-' + lang).style.display = 'block';
    }

    function copyText(text) {
      navigator.clipboard.writeText(text);
      alert('Copied: ' + text);
    }

    function copyCode(btn) {
      const code = btn.previousElementSibling.textContent;
      navigator.clipboard.writeText(code);
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy', 2000);
    }

    function verifyAdminToken() {
      const token = document.getElementById('adminTokenInput').value.trim();
      if (!token) return alert('Please enter admin token');
      currentAdminToken = token;
      sessionStorage.setItem('faceapi_admin_token', token);
      loadKeys();
    }

    async function loadKeys() {
      try {
        const res = await fetch('/faceapi/admin/keys', {
          headers: { 'X-Admin-Token': currentAdminToken }
        });
        if (!res.ok) {
          document.getElementById('authPrompt').style.display = 'block';
          document.getElementById('keysTableContainer').style.display = 'none';
          sessionStorage.removeItem('faceapi_admin_token');
          currentAdminToken = '';
          alert('Invalid Admin Token');
          return;
        }
        const data = await res.json();
        renderKeysTable(data.keys || []);
        document.getElementById('authPrompt').style.display = 'none';
        document.getElementById('keysTableContainer').style.display = 'block';
      } catch (err) {
        alert('Failed to connect to FaceAPI');
      }
    }

    function renderKeysTable(keys) {
      const tbody = document.getElementById('keysTableBody');
      tbody.innerHTML = '';
      if (!keys.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted);">No keys created yet. Click Generate New Key.</td></tr>';
        return;
      }
      keys.forEach(k => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${k.name}</strong></td>
          <td><code>${k.key_prefix}...</code></td>
          <td><span class="brand-badge" style="background:#334155;">${k.plan}</span></td>
          <td>${k.month_usage || 0} reqs</td>
          <td style="color:var(--text-muted); font-size:0.8rem;">${(k.created_at || '').slice(0, 10)}</td>
          <td><span style="color:${k.active ? '#10b981' : '#ef4444'}; font-weight:700;">${k.active ? '● Active' : '○ Revoked'}</span></td>
          <td>
            ${k.active ? `<button class="btn btn-danger" style="padding:0.25rem 0.6rem; font-size:0.75rem;" onclick="revokeKey('${k.key_id}')">Revoke</button>` : '<span style="color:var(--text-muted); font-size:0.8rem;">Revoked</span>'}
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function openCreateKeyModal() {
      if (!currentAdminToken) {
        alert('Please unlock with Admin Token first');
        return;
      }
      document.getElementById('createKeyModal').classList.add('show');
    }

    function closeModal() {
      document.getElementById('createKeyModal').classList.remove('show');
    }

    async function submitCreateKey() {
      const name = document.getElementById('newKeyName').value.trim();
      const plan = document.getElementById('newKeyPlan').value;
      if (!name) return alert('Please enter key name');

      try {
        const res = await fetch('/faceapi/admin/keys', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Admin-Token': currentAdminToken
          },
          body: JSON.stringify({ name, plan })
        });
        const data = await res.json();
        if (data.api_key) {
          closeModal();
          document.getElementById('newKeySecret').textContent = data.api_key;
          document.getElementById('showKeyModal').classList.add('show');
          loadKeys();
        } else {
          alert('Error: ' + (data.message || 'Failed to create key'));
        }
      } catch (err) {
        alert('Error creating key');
      }
    }

    function copyNewKey() {
      const text = document.getElementById('newKeySecret').textContent;
      navigator.clipboard.writeText(text);
      alert('API Key copied to clipboard!');
    }

    function closeShowKeyModal() {
      document.getElementById('showKeyModal').classList.remove('show');
    }

    async function revokeKey(keyId) {
      if (!confirm('Are you sure you want to revoke this API key?')) return;
      try {
        await fetch(`/faceapi/admin/keys/${keyId}/revoke`, {
          method: 'POST',
          headers: { 'X-Admin-Token': currentAdminToken }
        });
        loadKeys();
      } catch (err) {
        alert('Failed to revoke key');
      }
    }

    async function runTester() {
      const fileInput = document.getElementById('testerFile');
      const key = document.getElementById('testerKey').value.trim();
      const out = document.getElementById('testerOutput');

      if (!fileInput.files.length) return alert('Please choose an image file first');
      out.textContent = '// Analyzing image with YuNet + SFace + Anti-Spoofing...';

      const formData = new FormData();
      formData.append('image', fileInput.files[0]);

      try {
        const headers = {};
        if (key) headers['X-API-Key'] = key;

        const res = await fetch('/faceapi/v1/identify?collection=default', {
          method: 'POST',
          headers: headers,
          body: formData
        });
        const data = await res.json();
        out.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        out.textContent = '// Error: ' + err.message;
      }
    }

    if (currentAdminToken) {
      document.getElementById('adminTokenInput').value = currentAdminToken;
    }
  </script>
</body>
</html>
"""


def render_portal() -> HTMLResponse:
    return HTMLResponse(content=PORTAL_HTML)
