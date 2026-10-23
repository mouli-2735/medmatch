import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import {
  Sparkles,
  Volume2,
  VolumeX,
  Stethoscope,
  Smile,
  ShieldAlert,
  Search,
  Upload,
  RotateCcw
} from 'lucide-react';

export default function ProperDoctorAvatar3D({
  activePrescription,
  loading,
  processingStage,
  hoveredLineId,
  onOpenUpload,
}) {
  const mountRef = useRef(null);
  const [avatarMode, setAvatarMode] = useState('avatar'); // 'avatar' | 'tablet'
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [activePose, setActivePose] = useState('ready');
  const [speechText, setSpeechText] = useState(
    "Hello! I'm Dr. Alex (Pharm.D). Click or drop any handwritten prescription to begin NLEM clinical verification!"
  );

  // References for WebGL 3D animation loop
  const animRefs = useRef({
    scene: null,
    camera: null,
    renderer: null,
    avatarMesh: null,
    capsules: [],
    particles: null,
    pedestalRing: null,
    cursorLight: null,
    targetRotX: 0,
    targetRotY: 0,
    currentRotX: 0,
    currentRotY: 0,
    isDragging: false,
    prevMouseX: 0,
    dragRotY: 0,
    clock: new THREE.Clock(),
    animId: null,
    textureLoaded: false,
  });

  // Reactive speech update based on prescription or processing state
  useEffect(() => {
    let text = "";
    if (loading) {
      text = `Analyzing prescription: ${processingStage || 'Enhancing handwriting strokes'}...`;
      setActivePose('inspect');
    } else if (activePrescription) {
      if (!activePrescription.quality_check?.passed) {
        text = `Optical alert: Photo failed quality gating (${activePrescription.quality_check?.message || 'blurry'}). Please re-scan with good lighting!`;
        setActivePose('alert');
      } else {
        const lookalikes = activePrescription.lines?.filter(l => l.lookalike?.is_flagged) || [];
        const redLines = activePrescription.lines?.filter(l => l.confidence?.level === 'red' && l.status === 'pending') || [];

        if (hoveredLineId) {
          const l = activePrescription.lines.find(x => x.line_id === hoveredLineId);
          if (l) {
            if (l.lookalike?.is_flagged) {
              text = `Caution on Line #${l.line_id}: ${l.selected_candidate?.brand_name} looks similar to ${l.lookalike.paired_drug}. Check patient record!`;
              setActivePose('alert');
            } else if (l.confidence?.level === 'red') {
              text = `Line #${l.line_id}: Cursive characters ambiguous (${l.confidence?.score}%). Pharmacist confirmation needed.`;
              setActivePose('inspect');
            } else {
              text = `Line #${l.line_id}: ${l.selected_candidate?.brand_name} matched against NLEM standards.`;
              setActivePose('approve');
            }
          }
        } else if (lookalikes.length > 0) {
          text = `Safety Alert: Detected ${lookalikes.length} Look-Alike drug pair(s). Check 1-click swap options!`;
          setActivePose('alert');
        } else if (redLines.length > 0) {
          text = `Prescription ingested: ${redLines.length} red-flagged cursive line(s) require clinical sign-off.`;
          setActivePose('inspect');
        } else {
          text = `All prescription lines reviewed and ready for pharmacist sign-off!`;
          setActivePose('approve');
        }
      }
    } else {
      text = "Welcome to MedMatch Rx! I'm Dr. Alex. Drop your prescription to begin pharmacist review assistance.";
      setActivePose('ready');
    }

    setSpeechText(text);
    if (soundEnabled && text) {
      speakAloud(text);
    }
  }, [loading, processingStage, activePrescription, hoveredLineId, soundEnabled]);

  // Voice speech synthesis using Web Speech API
  const speakAloud = (textToSpeak) => {
    if (!('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;

      const voices = window.speechSynthesis.getVoices();
      const englishVoice = voices.find(v => v.lang.includes('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Alex')));
      if (englishVoice) utterance.voice = englishVoice;

      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      setIsSpeaking(false);
    }
  };

  const toggleVoice = (e) => {
    e.stopPropagation();
    if (!soundEnabled) {
      setSoundEnabled(true);
      speakAloud(speechText);
    } else {
      setSoundEnabled(false);
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setIsSpeaking(false);
    }
  };

  const handlePoseChange = (e, pose, customText) => {
    e.stopPropagation();
    setActivePose(pose);
    setSpeechText(customText);
    if (soundEnabled) speakAloud(customText);
  };

  // --- THREE.JS 3D INITIALIZATION & RENDERING ---
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 380;
    const height = container.clientHeight || 320;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    animRefs.current.scene = scene;

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    camera.position.set(0, 0, 5.2);
    animRefs.current.camera = camera;

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      container.innerHTML = '';
      container.appendChild(renderer.domElement);
      animRefs.current.renderer = renderer;
    } catch (err) {
      console.warn("WebGL init failed:", err);
      return;
    }

    // 2. Lighting Setup
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.3);
    scene.add(ambientLight);

    const mainKeyLight = new THREE.DirectionalLight(0xffffff, 2.0);
    mainKeyLight.position.set(2, 4, 4);
    scene.add(mainKeyLight);

    const cyanRimLight = new THREE.DirectionalLight(0x06b6d4, 3.5);
    cyanRimLight.position.set(-4, 2, -2);
    scene.add(cyanRimLight);

    const cursorLight = new THREE.PointLight(0x38bdf8, 2.0, 8);
    cursorLight.position.set(0, 0, 3);
    scene.add(cursorLight);
    animRefs.current.cursorLight = cursorLight;

    // 3. Central 3D Avatar Hologram Group
    const avatarGroup = new THREE.Group();
    scene.add(avatarGroup);

    // Load Doctor Texture
    const textureLoader = new THREE.TextureLoader();
    const activeImageSrc = avatarMode === 'avatar' ? '/assets/doctor_3d_avatar.jpg' : '/assets/doctor_tablet_desk.jpg';

    textureLoader.load(activeImageSrc, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.generateMipmaps = true;
      texture.minFilter = THREE.LinearMipmapLinearFilter;

      // Doctor Curved Hologram Mesh
      const planeGeo = new THREE.PlaneGeometry(2.8, 3.4, 24, 24);
      // Slight cylindrical curve for high-tech holographic screen curvature
      const posAttr = planeGeo.attributes.position;
      for (let i = 0; i < posAttr.count; i++) {
        const x = posAttr.getX(i);
        posAttr.setZ(i, -Math.pow(x, 2) * 0.08);
      }
      planeGeo.computeVertexNormals();

      const planeMat = new THREE.MeshPhysicalMaterial({
        map: texture,
        roughness: 0.2,
        metalness: 0.05,
        clearcoat: 0.6,
        clearcoatRoughness: 0.1,
        transparent: true,
        opacity: 0.98,
      });

      const avatarMesh = new THREE.Mesh(planeGeo, planeMat);
      avatarMesh.position.set(0, 0.05, 0);
      avatarGroup.add(avatarMesh);
      animRefs.current.avatarMesh = avatarMesh;
      animRefs.current.textureLoaded = true;
    });

    // Back Glow Panel
    const backGeo = new THREE.PlaneGeometry(3.0, 3.6);
    const backMat = new THREE.MeshBasicMaterial({
      color: 0x06b6d4,
      transparent: true,
      opacity: 0.12,
      side: THREE.DoubleSide
    });
    const backMesh = new THREE.Mesh(backGeo, backMat);
    backMesh.position.set(0, 0, -0.15);
    avatarGroup.add(backMesh);

    // Glowing Neon Dais / Pedestal Ring
    const ringGeo = new THREE.TorusGeometry(1.6, 0.035, 16, 64);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x06b6d4 });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 2;
    ringMesh.position.y = -1.65;
    avatarGroup.add(ringMesh);
    animRefs.current.pedestalRing = ringMesh;

    // 4. Orbiting 3D Medical Capsules
    const capsules = [];
    const capsuleGeo = new THREE.CapsuleGeometry(0.12, 0.28, 12, 24);

    for (let i = 0; i < 5; i++) {
      const isCyan = i % 2 === 0;
      const capsuleMat = new THREE.MeshPhysicalMaterial({
        color: isCyan ? 0x06b6d4 : 0x10b981,
        roughness: 0.15,
        metalness: 0.1,
        transmission: 0.65,
        thickness: 0.4,
        clearcoat: 1.0,
      });

      const mesh = new THREE.Mesh(capsuleGeo, capsuleMat);
      scene.add(mesh);

      capsules.push({
        mesh,
        angle: (i / 5) * Math.PI * 2,
        radiusX: 1.9 + (i % 2) * 0.3,
        radiusZ: 1.1 + (i % 2) * 0.2,
        speed: 0.7 + (i * 0.15),
        yOffset: -0.8 + (i * 0.4),
        rotX: 0.02,
        rotY: 0.03,
      });
    }
    animRefs.current.capsules = capsules;

    // 5. 3D Particle Constellation (Molecular DNA)
    const particleCount = 75;
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount * 3; i += 3) {
      positions[i] = (Math.random() - 0.5) * 6;
      positions[i + 1] = (Math.random() - 0.5) * 4.5;
      positions[i + 2] = (Math.random() - 0.5) * 3;
    }
    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const particleMat = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.07,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
    });
    const particlePoints = new THREE.Points(particleGeo, particleMat);
    scene.add(particlePoints);
    animRefs.current.particles = particlePoints;

    // 6. Mouse Tracking & Drag Interaction Listeners
    const handlePointerMove = (e) => {
      const rect = container.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const y = -(((e.clientY - rect.top) / rect.height) * 2 - 1);

      animRefs.current.targetRotY = x * 0.45;
      animRefs.current.targetRotX = -y * 0.35;

      if (animRefs.current.cursorLight) {
        animRefs.current.cursorLight.position.x = x * 3;
        animRefs.current.cursorLight.position.y = y * 2;
      }

      if (animRefs.current.isDragging) {
        const deltaX = e.clientX - animRefs.current.prevMouseX;
        animRefs.current.dragRotY += deltaX * 0.012;
        animRefs.current.prevMouseX = e.clientX;
      }
    };

    const handlePointerDown = (e) => {
      animRefs.current.isDragging = true;
      animRefs.current.prevMouseX = e.clientX;
    };

    const handlePointerUp = () => {
      animRefs.current.isDragging = false;
    };

    window.addEventListener('pointermove', handlePointerMove);
    container.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointerup', handlePointerUp);

    // 7. Render Loop
    let animId;
    const render = () => {
      animId = requestAnimationFrame(render);
      const time = animRefs.current.clock.getElapsedTime();
      const speedMultiplier = loading ? 2.5 : 1.0;

      // Smooth damping for tilt
      const r = animRefs.current;
      r.currentRotX += (r.targetRotX - r.currentRotX) * 0.07;
      r.currentRotY += (r.targetRotY - r.currentRotY) * 0.07;

      if (!r.isDragging) {
        r.dragRotY += (0 - r.dragRotY) * 0.04;
      }

      avatarGroup.rotation.y = r.currentRotY + r.dragRotY;
      avatarGroup.rotation.x = r.currentRotX;

      // Gentle floating breathing animation
      avatarGroup.position.y = Math.sin(time * 1.8) * 0.04;

      // Rotate Pedestal Ring
      if (r.pedestalRing) {
        r.pedestalRing.rotation.z = time * 0.5 * speedMultiplier;
      }

      // Orbiting capsules
      capsules.forEach((item) => {
        const curAngle = item.angle + time * item.speed * speedMultiplier;
        item.mesh.position.x = Math.cos(curAngle) * item.radiusX;
        item.mesh.position.z = Math.sin(curAngle) * item.radiusZ;
        item.mesh.position.y = item.yOffset + Math.sin(time * 2 + item.angle) * 0.15;
        item.mesh.rotation.x += item.rotX;
        item.mesh.rotation.y += item.rotY;
      });

      // DNA Particle swirl
      if (r.particles) {
        r.particles.rotation.y = time * 0.08 * speedMultiplier;
      }

      renderer.render(scene, camera);
    };

    render();

    // Resize Handler
    const handleResize = () => {
      if (!container || !renderer) return;
      const w = container.clientWidth || 380;
      const h = container.clientHeight || 320;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('pointermove', handlePointerMove);
      container.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('resize', handleResize);
      if (renderer && container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      if (renderer) renderer.dispose();
    };
  }, [avatarMode, loading]);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: 320,
        maxHeight: 320,
        borderRadius: 22,
        overflow: 'hidden',
        background: 'radial-gradient(circle at 50% 30%, rgba(6, 182, 212, 0.22) 0%, rgba(7, 16, 34, 0.96) 80%)',
        border: '1.5px solid rgba(6, 182, 212, 0.4)',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), 0 0 30px rgba(6, 182, 212, 0.25)',
        cursor: 'pointer',
        userSelect: 'none',
      }}
      onClick={onOpenUpload}
      title="Dr. Alex Reed (Pharm.D) · Interactive 3D Avatar — Click to Ingest Prescription"
    >
      {/* 3D WebGL Canvas Container */}
      <div
        ref={mountRef}
        style={{
          width: '100%',
          height: '100%',
          position: 'absolute',
          top: 0,
          left: 0,
          zIndex: 1,
        }}
      />

      {/* Top Overlay: Telemetry & Controls */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          right: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          zIndex: 10,
        }}
      >
        {/* Status Badge */}
        <div
          style={{
            background: 'rgba(7, 18, 38, 0.88)',
            backdropFilter: 'blur(12px)',
            padding: '5px 12px',
            borderRadius: 9999,
            border: '1px solid rgba(6, 182, 212, 0.45)',
            color: '#38bdf8',
            fontSize: '0.72rem',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span className="pulse-dot" style={{ background: '#10b981', width: 7, height: 7 }} />
          <span>DR. ALEX · 3D AVATAR</span>
        </div>

        {/* Mode Switcher & Voice Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} onClick={(e) => e.stopPropagation()}>
          <div
            style={{
              display: 'flex',
              background: 'rgba(7, 18, 38, 0.85)',
              backdropFilter: 'blur(12px)',
              padding: '3px',
              borderRadius: 9999,
              border: '1px solid rgba(255, 255, 255, 0.14)',
            }}
          >
            <button
              onClick={() => setAvatarMode('avatar')}
              style={{
                background: avatarMode === 'avatar' ? '#06b6d4' : 'transparent',
                color: avatarMode === 'avatar' ? '#080d1a' : '#94a3b8',
                border: 'none',
                borderRadius: 9999,
                padding: '3px 9px',
                fontSize: '0.68rem',
                fontWeight: 700,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              Avatar
            </button>
            <button
              onClick={() => setAvatarMode('tablet')}
              style={{
                background: avatarMode === 'tablet' ? '#06b6d4' : 'transparent',
                color: avatarMode === 'tablet' ? '#080d1a' : '#94a3b8',
                border: 'none',
                borderRadius: 9999,
                padding: '3px 9px',
                fontSize: '0.68rem',
                fontWeight: 700,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              Desk
            </button>
          </div>

          <button
            onClick={toggleVoice}
            style={{
              background: soundEnabled ? 'rgba(16, 185, 129, 0.2)' : 'rgba(7, 18, 38, 0.85)',
              border: `1px solid ${soundEnabled ? '#10b981' : 'rgba(255, 255, 255, 0.15)'}`,
              borderRadius: 9999,
              padding: '4px 8px',
              color: soundEnabled ? '#10b981' : '#94a3b8',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: '0.68rem',
              fontWeight: 700,
              backdropFilter: 'blur(12px)',
            }}
            title={soundEnabled ? 'Voice is Active (Click to Mute)' : 'Enable Speech Voice'}
          >
            {soundEnabled ? <Volume2 size={13} color="#10b981" /> : <VolumeX size={13} />}
          </button>
        </div>
      </div>

      {/* Laser Scanning Line during Ingestion */}
      {loading && <div className="laser-scanner-line" />}

      {/* Bottom Speech / Clinical Dialogue Ribbon */}
      <div
        style={{
          position: 'absolute',
          bottom: 10,
          left: 10,
          right: 10,
          zIndex: 10,
          background: 'rgba(6, 14, 30, 0.92)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(6, 182, 212, 0.35)',
          borderRadius: 14,
          padding: '8px 12px',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.65)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Stethoscope size={13} color="#06b6d4" />
            <span style={{ fontSize: '0.66rem', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.04em' }}>
              DR. ALEX REED (PHARM.D)
            </span>
          </div>
          <span style={{ fontSize: '0.64rem', color: '#10b981', fontWeight: 700 }}>
            ● CLICK TO INGEST
          </span>
        </div>

        <p style={{ fontSize: '0.74rem', color: '#f8fafc', lineHeight: 1.35, margin: '0 0 6px 0', fontWeight: 500 }}>
          {speechText}
        </p>

        {/* Interactive Gesture Action Chips */}
        <div
          style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={(e) => handlePoseChange(e, 'wave', "Hi! I verify each prescription stroke against NLEM standard dosages.")}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: 9999,
              padding: '2px 8px',
              color: '#94a3b8',
              fontSize: '0.64rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Smile size={11} color="#06b6d4" /> Hello
          </button>

          <button
            onClick={(e) => handlePoseChange(e, 'inspect', "Inspecting cursive script handwriting for strength, dose, and frequency.")}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: 9999,
              padding: '2px 8px',
              color: '#94a3b8',
              fontSize: '0.64rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Search size={11} color="#38bdf8" /> Inspect
          </button>

          <button
            onClick={(e) => handlePoseChange(e, 'alert', "LASA Shield Active: Preventing Celebrex vs Celexa and look-alike swaps!")}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: 9999,
              padding: '2px 8px',
              color: '#94a3b8',
              fontSize: '0.64rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <ShieldAlert size={11} color="#fbbf24" /> LASA
          </button>

          <button
            onClick={onOpenUpload}
            style={{
              background: 'rgba(6, 182, 212, 0.25)',
              border: '1px solid rgba(6, 182, 212, 0.6)',
              borderRadius: 9999,
              padding: '2px 9px',
              color: '#38bdf8',
              fontSize: '0.64rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              marginLeft: 'auto',
            }}
          >
            <Upload size={11} /> Ingest Rx
          </button>
        </div>
      </div>
    </div>
  );
}
