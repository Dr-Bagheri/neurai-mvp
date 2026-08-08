// Microphone → WebSocket upstream for the live meeting (D2 live pass).
// The server expects binary frames of PCM16 @ 16 kHz mono on
// /ws/meetings/{id}/audio; a JSON text frame {"type":"stop"} ends the meeting.

import { wsUrl } from "../api/client";

export interface MicStream {
  /** Sends the stop control frame and releases mic + socket. */
  stop: () => Promise<void>;
}

const TARGET_RATE = 16_000;

function downsampleTo16k(input: Float32Array, inputRate: number): Int16Array {
  const ratio = inputRate / TARGET_RATE;
  const outLen = Math.floor(input.length / ratio);
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    // nearest-sample decimation — good enough for speech ASR input
    const sample = input[Math.floor(i * ratio)];
    const clamped = Math.max(-1, Math.min(1, sample));
    out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return out;
}

export async function startMicStream(meetingId: number, micId?: number): Promise<MicStream> {
  let media: MediaStream;
  try {
    media = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (e) {
    const name = e instanceof DOMException ? e.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new Error("دسترسی به میکروفون داده نشد — اجازهٔ میکروفون را در مرورگر فعال کنید.");
    }
    if (name === "NotFoundError") {
      throw new Error("میکروفونی پیدا نشد — یک دستگاه ورودی صدا وصل کنید.");
    }
    throw e;
  }

  // v0.3 named multi-mic: ?mic_id=N binds this stream to a registered mic;
  // omitted → the server uses the first mic. Parallel connections (one per
  // mic) are supported.
  const path =
    micId !== undefined
      ? `/ws/meetings/${meetingId}/audio?mic_id=${micId}`
      : `/ws/meetings/${meetingId}/audio`;
  const socket = new WebSocket(wsUrl(path));
  socket.binaryType = "arraybuffer";
  await new Promise<void>((resolve, reject) => {
    socket.onopen = () => resolve();
    socket.onerror = () => reject(new Error("اتصال صوتی به سرور برقرار نشد"));
  });

  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(media);
  // ScriptProcessor is deprecated but universally supported and needs no
  // worklet asset; replace with an AudioWorklet when the bundle grows one.
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(processor);
  processor.connect(ctx.destination);

  processor.onaudioprocess = (e) => {
    if (socket.readyState !== WebSocket.OPEN) return;
    const pcm = downsampleTo16k(e.inputBuffer.getChannelData(0), ctx.sampleRate);
    socket.send(pcm.buffer);
  };

  const stop = async () => {
    processor.disconnect();
    source.disconnect();
    media.getTracks().forEach((t) => t.stop());
    await ctx.close();
    if (socket.readyState === WebSocket.OPEN) {
      // server stops the session and replies {"type":"stopped"}
      socket.send(JSON.stringify({ type: "stop" }));
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 2000);
        socket.onmessage = () => {
          clearTimeout(timer);
          resolve();
        };
        socket.onclose = () => {
          clearTimeout(timer);
          resolve();
        };
      });
    }
    socket.close();
  };

  return { stop };
}
