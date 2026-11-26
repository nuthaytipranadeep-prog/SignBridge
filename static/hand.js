import { HandLandmarker, FilesetResolver, DrawingUtils }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

export { HandLandmarker, DrawingUtils };

export async function createLandmarker() {
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  return HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    },
    runningMode: "VIDEO",
    numHands: 1
  });
}

// Turns 21 points into 42 numbers that do not depend on where your hand is
// in the frame or how far it is from the camera.
export function normalize(hand) {
  const wrist = hand[0];
  const scale = Math.hypot(hand[9].x - wrist.x, hand[9].y - wrist.y) || 1;
  const out = [];
  for (const p of hand) {
    out.push((p.x - wrist.x) / scale, (p.y - wrist.y) / scale);
  }
  return out;
}

export async function startCamera(video, statusEl) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusEl.textContent = "Camera not supported here. Use http://localhost:5000 or HTTPS.";
    throw new Error("No camera API");
  }
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({ video: true });
    await video.play();
  } catch (e) {
    statusEl.textContent = "Camera not available: " + e.message + ". Allow camera access and reload.";
    throw e;
  }
}