import { useEffect, useRef } from 'react';

/**
 * PulseLine — animated EKG/heartbeat line that reacts to Sifra's mood.
 * Renders on a canvas element with smooth animation.
 */
export default function PulseLine({ mood = 'neutral', energy = 7 }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const offsetRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    }

    resize();
    window.addEventListener('resize', resize);

    // Mood-based parameters
    const moodConfig = {
      neutral:      { color: '#00ff9d', speed: 1.0, amplitude: 12, frequency: 0.03, spikeChance: 0.005 },
      cheerful:     { color: '#00ff9d', speed: 1.4, amplitude: 18, frequency: 0.04, spikeChance: 0.01 },
      energetic:    { color: '#ffd60a', speed: 1.8, amplitude: 22, frequency: 0.05, spikeChance: 0.015 },
      empathetic:   { color: '#ff3c78', speed: 0.8, amplitude: 10, frequency: 0.025, spikeChance: 0.003 },
      concerned:    { color: '#ff3c78', speed: 0.6, amplitude: 8, frequency: 0.02, spikeChance: 0.002 },
      playful:      { color: '#a855f7', speed: 1.3, amplitude: 16, frequency: 0.04, spikeChance: 0.012 },
      chill:        { color: '#00ff9d', speed: 0.7, amplitude: 8, frequency: 0.02, spikeChance: 0.003 },
      introspective:{ color: '#3b82f6', speed: 0.5, amplitude: 6, frequency: 0.015, spikeChance: 0.001 },
    };

    const config = moodConfig[mood] || moodConfig.neutral;
    const energyMod = energy / 10;

    function draw() {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      const mid = h / 2;

      ctx.clearRect(0, 0, w, h);

      // Draw glow line
      ctx.beginPath();
      ctx.strokeStyle = config.color;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = config.color;
      ctx.shadowBlur = 8;

      for (let x = 0; x < w; x++) {
        const t = (x + offsetRef.current) * config.frequency;
        let y = mid;

        // Base wave
        y += Math.sin(t) * config.amplitude * energyMod;
        // Secondary wave
        y += Math.sin(t * 2.3 + 1.5) * (config.amplitude * 0.3) * energyMod;

        // EKG-style spike
        const spikePos = (x + offsetRef.current) % 200;
        if (spikePos > 80 && spikePos < 85) {
          y -= 25 * energyMod;
        } else if (spikePos > 85 && spikePos < 88) {
          y += 35 * energyMod;
        } else if (spikePos > 88 && spikePos < 92) {
          y -= 15 * energyMod;
        }

        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }

      ctx.stroke();
      ctx.shadowBlur = 0;

      // Faint trailing glow
      ctx.beginPath();
      ctx.strokeStyle = config.color + '20';
      ctx.lineWidth = 6;
      for (let x = 0; x < w; x++) {
        const t = (x + offsetRef.current) * config.frequency;
        let y = mid + Math.sin(t) * config.amplitude * energyMod;
        const spikePos = (x + offsetRef.current) % 200;
        if (spikePos > 80 && spikePos < 85) y -= 25 * energyMod;
        else if (spikePos > 85 && spikePos < 88) y += 35 * energyMod;
        else if (spikePos > 88 && spikePos < 92) y -= 15 * energyMod;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      offsetRef.current += config.speed;
      animRef.current = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      window.removeEventListener('resize', resize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [mood, energy]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full"
      style={{ display: 'block' }}
    />
  );
}
