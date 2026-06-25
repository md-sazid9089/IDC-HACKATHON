/**
 * FaceExpressionOverlay.jsx
 * ---------------------------------------------------------------
 * Live webcam → Hugging Face vit-face-expression (browser direct).
 *
 * UI no longer shows emotion labels (happy / sad / angry / surprise / …).
 * Instead, every detection frame is mapped to a single actionable interview
 * coaching tip, surfaced as a rolling 3-tip queue under the camera.
 *
 * Architecture: The current build does NOT use face-api.js (banned by the
 * project's "no local ML model" architecture). Per-frame `expressions` come
 * from Hugging Face Inference API (HF returns label/score pairs). Per-frame
 * `landmarks` are not available, so the landmark-driven eye-contact tip is
 * implemented as a graceful no-op (the same priority chain is preserved).
 *
 * Exports:
 *   default — the FaceExpressionOverlay component
 *   getExpressionCoaching(distribution) — kept for back-compat with
 *     MockInterview.jsx, which still calls it on the finalised emotion
 *     percentage distribution at end-of-interview.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertCircle, Eye } from 'lucide-react';
import { hfInference, HFError } from '../services/hfClient';

const EXPRESSION_MODEL = 'trpakov/vit-face-expression';
const SAMPLE_INTERVAL_MS = 3000;
const TIP_FADE_AFTER_MS = 4000;
const NEGATIVE_EMOTIONS = new Set(['angry', 'disgust', 'fear', 'sad']);

function isInsecureContext() {
  if (typeof window === 'undefined') return false;
  const { protocol, hostname } = window.location;
  if (protocol === 'https:') return false;
  return !['localhost', '127.0.0.1', '::1'].includes(hostname);
}

// =====================================================================
// Per-frame coaching priority chain (matches the redesigned spec).
//
// Input shape: { happy, sad, angry, fear, surprise, disgust, neutral }
// where each value is a fractional score 0..1 from HF Inference output.
// Aliases (fearful/surprised/disgusted) are added so the priority chain
// reads naturally if expressions ever come from a face-api.js source.
//
// Returns: { tip: string, type: 'positive'|'warning'|'info', icon: string }
// =====================================================================
function _normalizeScores(hfList) {
  // hfList example: [{label:'happy', score:0.82}, ...]
  const out = {};
  for (const { label, score } of hfList || []) {
    out[label] = score;
  }
  // Alias HF names → face-api.js names
  if ('fear' in out)     out.fearful   = out.fear;
  if ('surprise' in out) out.surprised = out.surprise;
  if ('disgust' in out)  out.disgusted = out.disgust;
  return out;
}

function _pickRealtimeTip(expressions) {
  if (!expressions || Object.keys(expressions).length === 0) {
    return { tip: 'Move closer to the camera — face not detected', type: 'warning', icon: 'Eye' };
  }
  if ((expressions.neutral || 0) > 0.85) {
    return { tip: 'Great composure — you look calm and professional', type: 'positive', icon: 'CheckCircle2' };
  }
  if ((expressions.happy || 0) > 0.6) {
    return { tip: 'Natural warmth showing — keep that confident energy', type: 'positive', icon: 'CheckCircle2' };
  }
  if ((expressions.fearful || 0) > 0.35 || (expressions.surprised || 0) > 0.5) {
    return { tip: 'Take a breath — slow down and speak with intention', type: 'warning', icon: 'AlertCircle' };
  }
  if ((expressions.disgusted || 0) > 0.3 || (expressions.angry || 0) > 0.3) {
    return { tip: 'Relax your jaw and brow — aim for an open, neutral face', type: 'warning', icon: 'AlertCircle' };
  }
  if ((expressions.sad || 0) > 0.35) {
    return { tip: 'Lift your chin slightly and maintain an upright posture', type: 'warning', icon: 'AlertCircle' };
  }
  return { tip: 'Hold your position — looking good', type: 'positive', icon: 'CheckCircle2' };
}

function _iconFor(name) {
  if (name === 'CheckCircle2') return CheckCircle2;
  if (name === 'AlertCircle')  return AlertCircle;
  if (name === 'Eye')          return Eye;
  return CheckCircle2;
}

function _colorClasses(type) {
  if (type === 'positive') return { border: 'border-l-emerald-500', icon: 'text-emerald-400' };
  if (type === 'info')     return { border: 'border-l-purple-400', icon: 'text-purple-400' };
  return                        { border: 'border-l-amber-400',   icon: 'text-amber-400' };
}

// =====================================================================
// Legacy export — consumed by MockInterview.jsx at end-of-interview.
// Receives the CUMULATIVE percent distribution (0-100 per label).
// Returns an array of coaching cards summarising the whole session.
// =====================================================================
export function getExpressionCoaching(distribution) {
  if (!distribution || Object.keys(distribution).length === 0) return [];

  const coaching = [];
  const negativeTotal =
    (distribution.sad || 0) + (distribution.fear || 0) +
    (distribution.angry || 0) + (distribution.disgust || 0);

  if (negativeTotal > 50) {
    coaching.push({ icon: '😟', priority: 'high',
      tip: 'Relax your facial muscles — you appeared tense overall. Practise slow breathing before answering.' });
  }
  if ((distribution.sad || 0) > 30) {
    coaching.push({ icon: '💪', priority: 'high',
      tip: 'Try to lift the corners of your mouth slightly — a neutral-to-positive expression reads more confident.' });
  }
  if ((distribution.fear || 0) > 25) {
    coaching.push({ icon: '🧘', priority: 'high',
      tip: 'You looked anxious. Slow your speech, look at the lens, and pause before answering.' });
  }
  if ((distribution.angry || 0) > 15) {
    coaching.push({ icon: '😌', priority: 'medium',
      tip: 'Your expression read as intense at times. Soften your brow and keep an open face.' });
  }
  if ((distribution.happy || 0) > 40) {
    coaching.push({ icon: '✅', priority: 'good',
      tip: 'Great positive energy — keep that going.' });
  } else if ((distribution.happy || 0) < 10 && negativeTotal < 40) {
    coaching.push({ icon: '😊', priority: 'medium',
      tip: 'Try to show more enthusiasm — a small smile signals engagement.' });
  }
  return coaching;
}

// =====================================================================
// Canvas: subtle bounding-box overlay drawn in #A855F7 (no text).
// =====================================================================
function _drawBoundingBox(canvas, video) {
  if (!canvas || !video) return;
  const rect = video.getBoundingClientRect();
  canvas.width  = rect.width  || video.videoWidth  || 640;
  canvas.height = rect.height || video.videoHeight || 480;

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Estimated face area — centered, ~50% wide, ~75% tall.
  const x = canvas.width  * 0.25;
  const y = canvas.height * 0.10;
  const w = canvas.width  * 0.50;
  const h = canvas.height * 0.75;
  const r = 14;

  ctx.strokeStyle = '#A855F7';
  ctx.lineWidth   = 1.5;
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, w, h, r);
  } else {
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y,     x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x,     y + h, r);
    ctx.arcTo(x,     y + h, x,     y,     r);
    ctx.arcTo(x,     y,     x + w, y,     r);
    ctx.closePath();
  }
  ctx.stroke();
}

// =====================================================================
// Component
// =====================================================================
const FaceExpressionOverlay = forwardRef(function FaceExpressionOverlay(
  { active, onCoachingUpdate },
  ref,
) {
  const videoRef         = useRef(null);
  const canvasRef        = useRef(null);   // hidden — used for HF capture
  const overlayCanvasRef = useRef(null);   // visible — bounding box
  const streamRef        = useRef(null);
  const intervalRef      = useRef(null);
  const inFlightRef      = useRef(false);
  const emotionLogRef    = useRef([]);
  const lastTipKeyRef    = useRef('');     // dedup onCoachingUpdate calls

  const [tipQueue,      setTipQueue]      = useState([]); // [{ tip, type, icon, addedAt }]
  const [, _setTick]    = useState(0);                    // ticker for fade re-render
  const [camError,      setCamError]      = useState(null);
  const [hfError,       setHfError]       = useState(null); // transient HF problem (non-blocking)
  const [updating,      setUpdating]      = useState(false);
  const [cameraStarted, setCameraStarted] = useState(false);
  const [faceVisible,   setFaceVisible]   = useState(false);
  const [httpsWarning]                    = useState(isInsecureContext());

  // Periodic re-render so the "fade after 4s" opacity check stays current.
  useEffect(() => {
    if (!tipQueue.length) return;
    const id = setInterval(() => _setTick((t) => (t + 1) % 1_000_000), 1000);
    return () => clearInterval(id);
  }, [tipQueue.length]);

  const _pushTip = useCallback((tipObj) => {
    const key = `${tipObj.type}::${tipObj.tip}`;
    if (key === lastTipKeyRef.current) return; // dedup: same tip → no update
    lastTipKeyRef.current = key;

    setTipQueue((prev) => [{ ...tipObj, addedAt: Date.now() }, ...prev].slice(0, 3));
    if (typeof onCoachingUpdate === 'function') {
      onCoachingUpdate({ tip: tipObj.tip, type: tipObj.type, icon: tipObj.icon });
    }
  }, [onCoachingUpdate]);

  const stopAll = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
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
        // Log the dominant label for the cumulative summary (powers
        // MockInterview.jsx's end-of-interview ReasoningCard).
        emotionLogRef.current.push(list[0]);
        setHfError(null); // clear any stale error indicator

        // Draw bounding box (no text per redesign spec).
        setFaceVisible(true);
        _drawBoundingBox(overlayCanvasRef.current, videoRef.current);

        // Map this frame to a single coaching tip (priority chain).
        const expressions = _normalizeScores(list);
        const tip = _pickRealtimeTip(expressions);
        _pushTip(tip);
      } else {
        _pushTip({ tip: 'Move closer to the camera — face not detected',
                   type: 'warning', icon: 'Eye' });
      }
    } catch (err) {
      if (err instanceof HFError && err.status === 401) {
        setCamError('Hugging Face token missing or invalid. Set VITE_HF_API_TOKEN.');
        stopAll();
        setCameraStarted(false);
      } else {
        // Non-401 — surface so the user knows something failed, but keep
        // sampling. Most are 503 cold-starts that resolve in a few seconds.
        const msg = err instanceof HFError
          ? `HF ${err.status}: ${err.message}`
          : `${err?.name || 'Error'}: ${err?.message || err}`;
        console.warn('[FaceExpressionOverlay] HF call failed:', msg);
        setHfError(msg.slice(0, 120));
      }
    } finally {
      inFlightRef.current = false;
      setUpdating(false);
    }
  }

  const startCamera = useCallback(async () => {
    setCamError(null);
    emotionLogRef.current = [];
    setTipQueue([]);
    lastTipKeyRef.current = '';
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
      // Kick off the first capture quickly so the user sees a tip within ~1s.
      // The video element typically reaches readyState 2 within ~300-500ms.
      setTimeout(() => { captureAndAnalyze(); }, 600);
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

  // Parent flagged inactive → stop the camera.
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
      return _computeSummary(emotionLogRef.current);
    },
  }));

  function _computeSummary(log) {
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

  // =====================================================================
  // Render
  // =====================================================================
  const now = Date.now();

  return (
    <div className="w-full space-y-3">
      {/* Webcam frame */}
      <div className="relative w-full rounded-xl overflow-hidden bg-[#11152B] border border-purple-900/40">
        {/* Hidden canvas — used for HF capture only */}
        <canvas ref={canvasRef} className="hidden" />

        {httpsWarning && (
          <div className="px-3 py-2 text-xs text-amber-300 bg-amber-950/40 border-b border-amber-900/40">
            ⚠ Camera requires HTTPS in production. On localhost this should work — check browser permissions.
          </div>
        )}

        {/* Video element is always rendered so videoRef is valid at startCamera time. */}
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

        {/* Bounding-box overlay (no text). */}
        {cameraStarted && !camError && faceVisible && (
          <canvas
            ref={overlayCanvasRef}
            className="absolute inset-0 w-full h-full pointer-events-none"
            style={{ transform: 'scaleX(-1)' }}
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
            <p className="text-sm text-[#B3B3C7]">Enable your webcam for live expression coaching.</p>
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

      {/* Tip queue — under the camera, NOT overlaid */}
      <AnimatePresence initial={false}>
        {tipQueue.map((t, idx) => {
          const Icon = _iconFor(t.icon);
          const { border, icon: iconColor } = _colorClasses(t.type);
          const stale = idx > 0 || (now - t.addedAt) > TIP_FADE_AFTER_MS;
          const opacity = stale ? 0.5 : 1;
          return (
            <motion.div
              key={t.addedAt}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.3 }}
              className={`flex items-start gap-2 bg-white/5 rounded-lg px-3 py-2 text-xs border-l-2 ${border}`}
            >
              <Icon size={14} className={`${iconColor} flex-shrink-0 mt-0.5`} />
              <p className="text-white/80 leading-snug">{t.tip}</p>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {tipQueue.length === 0 && cameraStarted && !camError && (
        <div className="text-[11px] italic px-1">
          {updating ? (
            <span className="text-purple-300/80">Analysing your expression…</span>
          ) : hfError ? (
            <span className="text-amber-300/90">
              Hugging Face is warming up the model — first tip can take up to 20s. ({hfError})
            </span>
          ) : (
            <span className="text-white/40">Waiting for the first frame…</span>
          )}
        </div>
      )}
    </div>
  );
});

export default FaceExpressionOverlay;
