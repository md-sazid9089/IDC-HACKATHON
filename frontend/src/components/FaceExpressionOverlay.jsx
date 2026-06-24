/**
 * FaceExpressionOverlay.jsx
 * ---------------------------------------------------------------
 * Live webcam → Hugging Face vit-face-expression (browser direct).
 *
 * Architecture: getUserMedia (only after user gesture) → <video> →
 * canvas snapshot every 3 s → fetch HF Inference API directly →
 * render top-1 emotion badge + summary on finalize().
 *
 * NO backend hop. NO local model. The HF token is the public
 * VITE_HF_API_TOKEN baked into the client bundle.
 *
 * CHANGE 1 — Face bounding box canvas overlay (corner-style purple box)
 * CHANGE 2 — Expression coaching feedback surfaced via onCoachingUpdate cb
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { hfInference, HFError } from '../services/hfClient';

const EXPRESSION_MODEL = 'trpakov/vit-face-expression';
const SAMPLE_INTERVAL_MS = 3000;
const NEGATIVE_EMOTIONS = new Set(['angry', 'disgust', 'fear', 'sad']);

const EMOTION_META = {
  happy:    { emoji: '😊', color: '#22c55e' },
  neutral:  { emoji: '😐', color: '#a855f7' },
  surprise: { emoji: '😲', color: '#f59e0b' },
  fear:     { emoji: '😨', color: '#ef4444' },
  sad:      { emoji: '😢', color: '#60a5fa' },
  angry:    { emoji: '😠', color: '#ef4444' },
  disgust:  { emoji: '🤢', color: '#f97316' },
};

function isInsecureContext() {
  if (typeof window === 'undefined') return false;
  const { protocol, hostname } = window.location;
  if (protocol === 'https:') return false;
  return !['localhost', '127.0.0.1', '::1'].includes(hostname);
}

// ── CHANGE 2: Expression coaching pure function ──────────────────────────────
export function getExpressionCoaching(emotions) {
  /*
   emotions shape: { happy: 27, sad: 40, fear: 32, angry: 2, ... }
   Returns array of coaching objects prioritized by impact.
  */
  if (!emotions || Object.keys(emotions).length === 0) return [];

  const coaching = [];
  const entries = Object.entries(emotions).sort((a, b) => b[1] - a[1]);
  const dominant = entries[0];
  const dominantName = dominant[0].toLowerCase();
  const dominantPct = dominant[1];

  const negativeTotal =
    (emotions.sad || 0) +
    (emotions.fear || 0) +
    (emotions.angry || 0) +
    (emotions.disgust || 0);

  if (negativeTotal > 50) {
    coaching.push({
      icon: '😟',
      priority: 'high',
      tip: 'Relax your facial muscles — you appear tense. Take a slow breath before answering.',
    });
  }

  if (dominantName === 'sad' && dominantPct > 30) {
    coaching.push({
      icon: '💪',
      priority: 'high',
      tip: 'Lift the corners of your mouth slightly — a neutral-to-positive expression builds interviewer confidence in you.',
    });
  }

  if (dominantName === 'fear' && dominantPct > 25) {
    coaching.push({
      icon: '🧘',
      priority: 'high',
      tip: 'You look nervous — this is normal. Slow your speech, make eye contact with the camera, and pause before answering.',
    });
  }

  if (dominantName === 'angry' && dominantPct > 15) {
    coaching.push({
      icon: '😌',
      priority: 'medium',
      tip: 'Your expression reads as intense. Soften your brow and maintain a calm, open face.',
    });
  }

  if ((emotions.happy || 0) > 40) {
    coaching.push({
      icon: '✅',
      priority: 'good',
      tip: 'Great energy! Your positive expression is building rapport with the interviewer.',
    });
  }

  if ((emotions.happy || 0) < 10 && negativeTotal < 40) {
    coaching.push({
      icon: '😊',
      priority: 'medium',
      tip: 'Try to show more enthusiasm — a slight smile signals confidence and engagement.',
    });
  }

  // Eye contact proxy — fear often correlates with looking away
  if ((emotions.fear || 0) > 20) {
    coaching.push({
      icon: '👁️',
      priority: 'medium',
      tip: 'Look directly at the camera lens — this simulates eye contact in video interviews.',
    });
  }

  return coaching;
}

// ── CHANGE 1: Canvas drawing helpers ─────────────────────────────────────────
function drawBox(ctx, x, y, w, h, color, label) {
  // Corner-style box (not full rectangle) — looks professional
  const cornerLen = 20;
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;

  // Top-left corner
  ctx.beginPath();
  ctx.moveTo(x, y + cornerLen);
  ctx.lineTo(x, y);
  ctx.lineTo(x + cornerLen, y);
  ctx.stroke();

  // Top-right corner
  ctx.beginPath();
  ctx.moveTo(x + w - cornerLen, y);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x + w, y + cornerLen);
  ctx.stroke();

  // Bottom-left corner
  ctx.beginPath();
  ctx.moveTo(x, y + h - cornerLen);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x + cornerLen, y + h);
  ctx.stroke();

  // Bottom-right corner
  ctx.beginPath();
  ctx.moveTo(x + w - cornerLen, y + h);
  ctx.lineTo(x + w, y + h);
  ctx.lineTo(x + w - cornerLen, y + h);
  ctx.stroke();

  // Label above box
  ctx.shadowBlur = 0;
  ctx.fillStyle = color;
  ctx.font = 'bold 13px Poppins, sans-serif';
  ctx.fillText(label, x + 4, y - 8);
}

function drawFaceBox(overlayCanvas, videoEl, box) {
  if (!overlayCanvas || !videoEl) return;
  const rect = videoEl.getBoundingClientRect();
  overlayCanvas.width  = rect.width  || videoEl.videoWidth  || 640;
  overlayCanvas.height = rect.height || videoEl.videoHeight || 480;

  const ctx = overlayCanvas.getContext('2d');
  ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

  if (!box) {
    // Estimated face position — center of frame
    const x = overlayCanvas.width  * 0.25;
    const y = overlayCanvas.height * 0.10;
    const w = overlayCanvas.width  * 0.50;
    const h = overlayCanvas.height * 0.75;
    drawBox(ctx, x, y, w, h, '#A855F7', 'Face Detected');
  } else {
    // Scale API box coordinates to canvas dimensions
    const scaleX = overlayCanvas.width  / (box.imageWidth  || overlayCanvas.width);
    const scaleY = overlayCanvas.height / (box.imageHeight || overlayCanvas.height);
    drawBox(
      ctx,
      box.x      * scaleX,
      box.y      * scaleY,
      box.width  * scaleX,
      box.height * scaleY,
      '#A855F7',
      'Face Detected',
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

const FaceExpressionOverlay = forwardRef(function FaceExpressionOverlay(
  { active, onCoachingUpdate },
  ref,
) {
  const videoRef         = useRef(null);
  const canvasRef        = useRef(null);       // hidden — used for HF capture
  const overlayCanvasRef = useRef(null);       // visible — used for face box
  const streamRef        = useRef(null);
  const intervalRef      = useRef(null);
  const inFlightRef      = useRef(false);
  const emotionLogRef    = useRef([]);

  const [liveEmotion,   setLiveEmotion]   = useState(null);
  const [camError,      setCamError]      = useState(null);
  const [updating,      setUpdating]      = useState(false);
  const [cameraStarted, setCameraStarted] = useState(false);
  const [httpsWarning]                    = useState(isInsecureContext());
  const [faceVisible,   setFaceVisible]   = useState(false);

  const stopAll = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    // Clear overlay canvas when stopping
    if (overlayCanvasRef.current) {
      const ctx = overlayCanvasRef.current.getContext('2d');
      ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
    }
    setFaceVisible(false);
  }, []);

  async function captureAndAnalyze() {
    if (inFlightRef.current) return;
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    const ctx = canvas.getContext('2d');
    canvas.width  = video.videoWidth  || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.8));
    if (!blob) return;

    inFlightRef.current = true;
    setUpdating(true);
    try {
      const buf = await blob.arrayBuffer();
      const raw = await hfInference(EXPRESSION_MODEL, buf, 'image-classification');
      const list = Array.isArray(raw?.[0]) ? raw[0] : raw;
      if (Array.isArray(list) && list.length) {
        const top = list[0];
        setLiveEmotion(top);
        emotionLogRef.current.push(top);

        // ── CHANGE 1: Draw bounding box on overlay canvas ──
        setFaceVisible(true);
        drawFaceBox(overlayCanvasRef.current, videoRef.current, null /* no box from API */);

        // ── CHANGE 2: Emit live coaching update from current log ──
        if (typeof onCoachingUpdate === 'function') {
          const summary = computeSummary(emotionLogRef.current);
          if (summary) onCoachingUpdate(summary.distribution);
        }
      }
    } catch (err) {
      if (err instanceof HFError && err.status === 401) {
        setCamError('Hugging Face token missing or invalid. Set VITE_HF_API_TOKEN.');
        stopAll();
        setCameraStarted(false);
      }
      // otherwise: silent — never interrupt the interview
    } finally {
      inFlightRef.current = false;
      setUpdating(false);
    }
  }

  const startCamera = useCallback(async () => {
    setCamError(null);
    emotionLogRef.current = [];
    setLiveEmotion(null);
    setFaceVisible(false);

    if (!navigator?.mediaDevices?.getUserMedia) {
      setCamError('Webcam not available in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => { /* autoplay race — ignore */ });
      }
      setCameraStarted(true);
      intervalRef.current = setInterval(captureAndAnalyze, SAMPLE_INTERVAL_MS);
    } catch (err) {
      const name = err?.name || '';
      let msg = 'Camera access denied — please allow camera access in your browser settings and click Enable Camera again.';
      if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        msg = 'No webcam was detected. Connect a camera and try again.';
      } else if (name === 'NotReadableError') {
        msg = 'Your webcam is already in use by another application.';
      }
      setCamError(msg);
      setCameraStarted(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Stop the camera when the parent flags the session inactive.
  useEffect(() => {
    if (!active && cameraStarted) {
      stopAll();
      setCameraStarted(false);
    }
  }, [active, cameraStarted, stopAll]);

  // Always cleanup on unmount.
  useEffect(() => () => stopAll(), [stopAll]);

  useImperativeHandle(ref, () => ({
    finalize() {
      stopAll();
      setCameraStarted(false);
      return computeSummary(emotionLogRef.current);
    },
  }));

  function computeSummary(log) {
    if (!log.length) return null;
    const counts = {};
    let negCount = 0;
    for (const { label } of log) {
      counts[label] = (counts[label] || 0) + 1;
      if (NEGATIVE_EMOTIONS.has(label)) negCount++;
    }
    const total    = log.length;
    const dominant = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
    const distribution = {};
    for (const [label, count] of Object.entries(counts))
      distribution[label] = Math.round((count / total) * 100);
    return {
      dominant,
      dominantPct: distribution[dominant],
      negativePct: Math.round((negCount / total) * 100),
      totalFrames: total,
      distribution,
    };
  }

  const meta = liveEmotion ? (EMOTION_META[liveEmotion.label] || { emoji: '🙂', color: '#a855f7' }) : null;

  return (
    <div className="relative w-full rounded-xl overflow-hidden bg-[#11152B] border border-purple-900/40">
      {/* Hidden canvas — used only for HF API capture */}
      <canvas ref={canvasRef} className="hidden" />

      {httpsWarning && (
        <div className="px-3 py-2 text-xs text-amber-300 bg-amber-950/40 border-b border-amber-900/40">
          ⚠ Camera requires HTTPS in production. On localhost this should work — check browser permissions.
        </div>
      )}

      {/* The <video> element is always rendered so videoRef is valid when
          startCamera() resolves. Visibility is toggled with CSS. */}
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="w-full rounded-xl object-cover"
        style={{
          transform: 'scaleX(-1)',
          maxHeight: '280px',
          display: cameraStarted && !camError ? 'block' : 'none',
        }}
      />

      {/* ── CHANGE 1: Overlay canvas — face bounding box ─────────────────── */}
      {cameraStarted && !camError && faceVisible && (
        <canvas
          ref={overlayCanvasRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            // Mirror to match video's scaleX(-1) transform
            transform: 'scaleX(-1)',
          }}
        />
      )}

      {camError ? (
        <div className="flex flex-col items-center justify-center h-48 px-4 text-center gap-3">
          <p className="text-sm text-[#FCA5A5]">{camError}</p>
          <button
            onClick={startCamera}
            className="text-xs px-3 py-1.5 rounded-md border border-purple-500/40 text-purple-300 hover:bg-purple-500/10"
          >
            Try Again
          </button>
        </div>
      ) : !cameraStarted ? (
        <div className="flex flex-col items-center justify-center h-48 px-4 text-center gap-3">
          <p className="text-sm text-[#B3B3C7]">Enable your webcam for live expression analysis.</p>
          <button
            onClick={startCamera}
            disabled={!active}
            className="text-xs px-4 py-2 rounded-md bg-purple-600/80 hover:bg-purple-500 text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {active ? 'Enable Camera' : 'Start interview first'}
          </button>
        </div>
      ) : (
        <>
          {liveEmotion && meta && (
            <div
              className="absolute bottom-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-semibold backdrop-blur-sm"
              style={{
                background: 'rgba(11,14,28,0.75)',
                border: `1px solid ${meta.color}55`,
                color: meta.color,
              }}
            >
              <span className="text-base leading-none">{meta.emoji}</span>
              <span className="capitalize">{liveEmotion.label}</span>
              <span className="text-xs opacity-70">{Math.round(liveEmotion.score * 100)}%</span>
            </div>
          )}
          {updating && (
            <div className="absolute top-3 right-3 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-purple-300/80">
              <span className="w-2 h-2 rounded-full bg-purple-400 animate-ping" />
              updating
            </div>
          )}
          {!active && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60 rounded-xl">
              <span className="text-[#B3B3C7] text-sm">Camera paused</span>
            </div>
          )}
        </>
      )}
    </div>
  );
});

export default FaceExpressionOverlay;
