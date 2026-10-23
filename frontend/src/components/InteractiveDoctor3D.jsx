import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import {
  Sparkles,
  Volume2,
  VolumeX,
  Stethoscope,
  Smile,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  FileText,
  Play
} from 'lucide-react';

export default function InteractiveDoctor3D({
  activePrescription,
  loading,
  processingStage,
  hoveredLineId,
  onUploadClick,
  onLoadSampleClick,
  compact = false
}) {
  const mountRef = useRef(null);
  const [currentPose, setCurrentPose] = useState('idle'); // idle, wave, inspect, approve, alert
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechText, setSpeechText] = useState(
    "Hello! I'm Dr. Alex. Interact with me or drop any handwritten prescription onto my digital tablet!"
  );
  const [soundEnabled, setSoundEnabled] = useState(false);

  // References for 3D animatable body parts
  const animRefs = useRef({
    head: null,
    eyes: [],
    eyelids: [],
    mouth: null,
    rightArm: null,
    rightHand: null,
    leftArm: null,
    stethoscopeChestPiece: null,
    tabletScreenMesh: null,
    updateTabletTextureFn: null,
    ringPlatform: null,
    glowLight: null,
    alertLight: null,
    mouseX: 0,
    mouseY: 0,
    targetMouseX: 0,
    targetMouseY: 0,
    isDragging: false,
    dragPrevX: 0,
    rotY: 0,
    mouthOpen: 0,
    blinkTimer: 0,
    poseTime: 0,
    pose: 'idle'
  });

  // Keep animRefs pose synced with React state
  useEffect(() => {
    animRefs.current.pose = currentPose;
    animRefs.current.poseTime = 0;
  }, [currentPose]);

  // Reactive speech update based on prescription states
  useEffect(() => {
    let text = "";
    let tabletTitle = "MEDMATCH RX";
    let tabletState = "STANDBY";

    if (loading) {
      text = `Analyzing prescription: ${processingStage || 'Processing handwriting strokes'}...`;
      setCurrentPose('inspect');
      tabletTitle = "SCANNING SCRIPT";
      tabletState = "PROCESSING";
    } else if (activePrescription) {
      if (!activePrescription.quality_check?.passed) {
        text = `Optical gate alert: ${activePrescription.quality_check?.message || 'Blurry photo'}. Please re-scan with clearer lighting!`;
        setCurrentPose('alert');
        tabletTitle = "QUALITY REJECT";
        tabletState = "ALERT";
      } else {
        const lookalikes = activePrescription.lines?.filter(l => l.lookalike?.is_flagged) || [];
        const redLines = activePrescription.lines?.filter(l => l.confidence?.level === 'red' && l.status === 'pending') || [];

        if (hoveredLineId) {
          const l = activePrescription.lines.find(x => x.line_id === hoveredLineId);
          if (l) {
            tabletTitle = l.selected_candidate?.brand_name || `LINE #${l.line_id}`;
            if (l.lookalike?.is_flagged) {
              text = `Caution on Line #${l.line_id}: ${l.selected_candidate?.brand_name} looks similar to ${l.lookalike.paired_drug}. Verify patient chart!`;
              setCurrentPose('alert');
              tabletState = "LASA ALERT";
            } else if (l.confidence?.level === 'red') {
              text = `Line #${l.line_id} cursive stroke is low confidence (${l.confidence?.score}%). Pharmacist sign-off required!`;
              setCurrentPose('inspect');
              tabletState = "REVIEW";
            } else {
              text = `Line #${l.line_id}: ${l.selected_candidate?.brand_name} verified against NLEM standards.`;
              setCurrentPose('approve');
              tabletState = "VERIFIED";
            }
          }
        } else if (lookalikes.length > 0) {
          text = `Safety Alert: I detected ${lookalikes.length} Look-Alike drug pair(s). Check the 1-click swap options!`;
          setCurrentPose('alert');
          tabletTitle = "LASA HAZARD";
          tabletState = "ALERT";
        } else if (redLines.length > 0) {
          text = `Ready for verification! There are ${redLines.length} red-flagged cursive lines requiring your clinical review.`;
          setCurrentPose('inspect');
          tabletTitle = `RX #${activePrescription.prescription_id}`;
          tabletState = `${redLines.length} RED LINES`;
        } else {
          text = `Excellent! All prescription lines are verified and ready for digital dispense!`;
          setCurrentPose('approve');
          tabletTitle = `RX #${activePrescription.prescription_id}`;
          tabletState = "READY TO DISPENSE";
        }
      }
    } else {
      text = "Welcome to MedMatch Rx! I'm Dr. Alex. Select a clinical test case or drop your script to begin.";
      setCurrentPose('idle');
      tabletTitle = "READY FOR SCRIPT";
      tabletState = "STANDBY";
    }

    setSpeechText(text);
    if (animRefs.current.updateTabletTextureFn) {
      animRefs.current.updateTabletTextureFn(tabletTitle, tabletState);
    }
    if (soundEnabled && text) {
      speakAloud(text);
    }
  }, [loading, processingStage, activePrescription, hoveredLineId]);

  // Voice speech synthesis
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
      console.error('Speech error:', e);
      setIsSpeaking(false);
    }
  };

  const toggleVoice = () => {
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

  const triggerPose = (poseName, customSpeech) => {
    setCurrentPose(poseName);
    if (customSpeech) {
      setSpeechText(customSpeech);
      if (soundEnabled) speakAloud(customSpeech);
    }
  };

  // 3D Scene Initialization
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || (compact ? 200 : 500);
    const height = container.clientHeight || (compact ? 140 : 480);

    // Scene & Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(compact ? 36 : 40, width / height, 0.1, 100);

    if (compact) {
      camera.position.set(0, 1.45, 3.8);
      camera.lookAt(0, 1.1, 0);
    } else {
      camera.position.set(0, 1.2, 5.2);
      camera.lookAt(0, 0.85, 0);
    }

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      container.appendChild(renderer.domElement);
    } catch (err) {
      console.warn("WebGL initialization fallback:", err);
      return;
    }

    // Lighting Setup
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    scene.add(ambientLight);

    const mainKeyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    mainKeyLight.position.set(3, 5, 4);
    mainKeyLight.castShadow = true;
    scene.add(mainKeyLight);

    const cyanRimLight = new THREE.DirectionalLight(0x06b6d4, 3.2);
    cyanRimLight.position.set(-4, 3, -3);
    scene.add(cyanRimLight);

    const mintWarmFill = new THREE.PointLight(0xa3e635, 1.5, 12);
    mintWarmFill.position.set(0, -1, 3);
    scene.add(mintWarmFill);

    const alertPointLight = new THREE.PointLight(0xef4444, 0, 10);
    alertPointLight.position.set(0, 2.5, 2);
    scene.add(alertPointLight);
    animRefs.current.alertLight = alertPointLight;

    // Doctor Character Root Group
    const doctorGroup = new THREE.Group();
    doctorGroup.position.set(0, compact ? -0.3 : -0.6, 0);
    scene.add(doctorGroup);

    // --- MATERIALS ---
    const skinMat = new THREE.MeshStandardMaterial({
      color: 0xf5d0b5,
      roughness: 0.6,
      metalness: 0.05
    });

    const hairMat = new THREE.MeshStandardMaterial({
      color: 0x2b1d0c,
      roughness: 0.7,
      metalness: 0.1
    });

    const coatMat = new THREE.MeshStandardMaterial({
      color: 0xf8fafc,
      roughness: 0.25,
      metalness: 0.08
    });

    const scrubMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7, // Clinical teal-blue scrubs
      roughness: 0.45
    });

    const stethoscopeTubeMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.4
    });

    const silverMetalMat = new THREE.MeshStandardMaterial({
      color: 0xe2e8f0,
      metalness: 0.85,
      roughness: 0.15
    });

    const glassesFrameMat = new THREE.MeshStandardMaterial({
      color: 0x06b6d4,
      metalness: 0.6,
      roughness: 0.2
    });

    // --- 1. HOLOGRAPHIC DAIS / PEDESTAL ---
    const daisGeo = new THREE.CylinderGeometry(1.6, 1.7, 0.18, 36);
    const daisMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.3,
      metalness: 0.8
    });
    const daisMesh = new THREE.Mesh(daisGeo, daisMat);
    daisMesh.position.y = -0.1;
    daisMesh.receiveShadow = true;
    doctorGroup.add(daisMesh);

    // Glowing Cyan Trim Ring
    const ringGeo = new THREE.TorusGeometry(1.62, 0.03, 16, 48);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x06b6d4 });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 2;
    ringMesh.position.y = -0.01;
    doctorGroup.add(ringMesh);
    animRefs.current.ringPlatform = ringMesh;

    // --- 2. TORSO & CLINICAL LAB COAT ---
    const torsoGroup = new THREE.Group();
    torsoGroup.position.y = 1.35;
    doctorGroup.add(torsoGroup);

    // Torso body
    const bodyGeo = new THREE.CylinderGeometry(0.55, 0.65, 1.3, 24);
    const bodyMesh = new THREE.Mesh(bodyGeo, coatMat);
    bodyMesh.castShadow = true;
    torsoGroup.add(bodyMesh);

    // Inner Scrub Shirt
    const scrubGeo = new THREE.BoxGeometry(0.42, 0.45, 0.25);
    const scrubMesh = new THREE.Mesh(scrubGeo, scrubMat);
    scrubMesh.position.set(0, 0.48, 0.44);
    torsoGroup.add(scrubMesh);

    // Coat Lapels
    const lapelGeo = new THREE.BoxGeometry(0.18, 0.6, 0.06);
    const leftLapel = new THREE.Mesh(lapelGeo, coatMat);
    leftLapel.position.set(-0.25, 0.35, 0.54);
    leftLapel.rotation.z = -0.15;
    torsoGroup.add(leftLapel);

    const rightLapel = new THREE.Mesh(lapelGeo, coatMat);
    rightLapel.position.set(0.25, 0.35, 0.54);
    rightLapel.rotation.z = 0.15;
    torsoGroup.add(rightLapel);

    // Pharmacist ID Badge
    const badgeGeo = new THREE.BoxGeometry(0.22, 0.28, 0.02);
    const badgeMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.1 });
    const badgeMesh = new THREE.Mesh(badgeGeo, badgeMat);
    badgeMesh.position.set(0.32, 0.35, 0.56);
    badgeMesh.rotation.y = 0.1;
    torsoGroup.add(badgeMesh);

    const badgeClip = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.04, 0.03), silverMetalMat);
    badgeClip.position.set(0.32, 0.5, 0.57);
    torsoGroup.add(badgeClip);

    const badgeDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 12, 12), new THREE.MeshBasicMaterial({ color: 0x10b981 }));
    badgeDot.position.set(0.38, 0.43, 0.58);
    torsoGroup.add(badgeDot);

    // --- 3. STETHOSCOPE ---
    const stethCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.25, 0.9, 0.1),
      new THREE.Vector3(-0.35, 0.55, 0.4),
      new THREE.Vector3(-0.15, 0.05, 0.58),
      new THREE.Vector3(0.0, -0.05, 0.6),
      new THREE.Vector3(0.18, 0.1, 0.58),
      new THREE.Vector3(0.35, 0.55, 0.4),
      new THREE.Vector3(0.25, 0.9, 0.1),
    ]);
    const stethGeo = new THREE.TubeGeometry(stethCurve, 32, 0.022, 8, false);
    const stethMesh = new THREE.Mesh(stethGeo, stethoscopeTubeMat);
    torsoGroup.add(stethMesh);

    // Metallic Chest Piece / Bell
    const bellGeo = new THREE.CylinderGeometry(0.07, 0.07, 0.03, 18);
    const bellMesh = new THREE.Mesh(bellGeo, silverMetalMat);
    bellMesh.rotation.x = Math.PI / 2;
    bellMesh.position.set(0.0, -0.05, 0.62);
    torsoGroup.add(bellMesh);
    animRefs.current.stethoscopeChestPiece = bellMesh;

    // --- 4. HEAD, FACE, EYES & GLASSES ---
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.15, 0.05);
    torsoGroup.add(headGroup);
    animRefs.current.head = headGroup;

    // Neck
    const neckMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.22, 0.35, 16), skinMat);
    neckMesh.position.y = -0.22;
    headGroup.add(neckMesh);

    // Head Cranium
    const headMesh = new THREE.Mesh(new THREE.SphereGeometry(0.48, 32, 28), skinMat);
    headMesh.castShadow = true;
    headGroup.add(headMesh);

    // Stylized Doctor Hair
    const hairGeo = new THREE.SphereGeometry(0.51, 24, 20, 0, Math.PI * 2, 0, Math.PI * 0.6);
    const hairMesh = new THREE.Mesh(hairGeo, hairMat);
    hairMesh.rotation.x = -0.3;
    hairMesh.position.set(0, 0.08, -0.06);
    headGroup.add(hairMesh);

    // Quiff
    const quiffMesh = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.35, 8), hairMat);
    quiffMesh.rotation.x = 1.1;
    quiffMesh.rotation.z = -0.3;
    quiffMesh.position.set(0.12, 0.44, 0.34);
    headGroup.add(quiffMesh);

    // Eyes
    const eyeWhiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const pupilMat = new THREE.MeshBasicMaterial({ color: 0x0284c7 });
    const pupilCenterMat = new THREE.MeshBasicMaterial({ color: 0x0f172a });

    const createEye = (x) => {
      const eyeGroup = new THREE.Group();
      eyeGroup.position.set(x, 0.06, 0.42);

      const eyeGlobe = new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 16), eyeWhiteMat);
      eyeGroup.add(eyeGlobe);

      const pupilMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.02, 16), pupilMat);
      pupilMesh.rotation.x = Math.PI / 2;
      pupilMesh.position.z = 0.075;
      eyeGroup.add(pupilMesh);

      const pupilInner = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.024, 0.022, 16), pupilCenterMat);
      pupilInner.rotation.x = Math.PI / 2;
      pupilInner.position.z = 0.078;
      eyeGroup.add(pupilInner);

      const eyelidGeo = new THREE.SphereGeometry(0.085, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.5);
      const eyelidMesh = new THREE.Mesh(eyelidGeo, skinMat);
      eyelidMesh.rotation.x = 0;
      eyelidMesh.position.z = 0.005;
      eyelidMesh.scale.set(1, 0.01, 1);
      eyeGroup.add(eyelidMesh);
      animRefs.current.eyelids.push(eyelidMesh);

      headGroup.add(eyeGroup);
      animRefs.current.eyes.push(eyeGroup);
    };

    createEye(-0.16);
    createEye(0.16);

    // Eyeglasses
    const lensRingGeo = new THREE.TorusGeometry(0.12, 0.016, 12, 32);
    const leftGlass = new THREE.Mesh(lensRingGeo, glassesFrameMat);
    leftGlass.position.set(-0.16, 0.06, 0.48);
    headGroup.add(leftGlass);

    const rightGlass = new THREE.Mesh(lensRingGeo, glassesFrameMat);
    rightGlass.position.set(0.16, 0.06, 0.48);
    headGroup.add(rightGlass);

    const bridgeMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.12, 8), glassesFrameMat);
    bridgeMesh.rotation.z = Math.PI / 2;
    bridgeMesh.position.set(0, 0.08, 0.49);
    headGroup.add(bridgeMesh);

    // Smile / Mouth
    const mouthMesh = new THREE.Mesh(new THREE.TorusGeometry(0.08, 0.02, 8, 16, Math.PI), new THREE.MeshBasicMaterial({ color: 0x9f1239 }));
    mouthMesh.position.set(0, -0.15, 0.44);
    mouthMesh.rotation.x = 0.2;
    headGroup.add(mouthMesh);
    animRefs.current.mouth = mouthMesh;

    // --- 5. LEFT ARM & DIGITAL CLINICAL TABLET ---
    const leftArmGroup = new THREE.Group();
    leftArmGroup.position.set(-0.62, 0.5, 0.05);
    torsoGroup.add(leftArmGroup);
    animRefs.current.leftArm = leftArmGroup;

    const upperArmGeo = new THREE.CylinderGeometry(0.12, 0.11, 0.55, 16);
    const upperArmMesh = new THREE.Mesh(upperArmGeo, coatMat);
    upperArmMesh.position.y = -0.25;
    leftArmGroup.add(upperArmMesh);

    const leftForearmGroup = new THREE.Group();
    leftForearmGroup.position.set(0, -0.5, 0);
    leftForearmGroup.rotation.x = -1.1;
    leftForearmGroup.rotation.y = 0.4;
    leftArmGroup.add(leftForearmGroup);

    const forearmMesh = new THREE.Mesh(upperArmGeo, coatMat);
    forearmMesh.position.y = -0.22;
    leftForearmGroup.add(forearmMesh);

    const leftHandMesh = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 16), skinMat);
    leftHandMesh.position.y = -0.48;
    leftForearmGroup.add(leftHandMesh);

    // THE 3D DIGITAL CLINICAL TABLET
    const tabletGroup = new THREE.Group();
    tabletGroup.position.set(0.05, -0.5, 0.3);
    tabletGroup.rotation.x = 1.25;
    tabletGroup.rotation.z = -0.1;
    leftForearmGroup.add(tabletGroup);

    const tabletBezel = new THREE.Mesh(
      new THREE.BoxGeometry(0.85, 0.62, 0.04),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.2, metalness: 0.8 })
    );
    tabletGroup.add(tabletBezel);

    // Luminous Screen with Canvas Texture
    const tabletScreenGeo = new THREE.PlaneGeometry(0.8, 0.56);
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 360;
    const ctx = canvas.getContext('2d');

    const updateTabletTexture = (title = 'MEDMATCH RX', state = 'STANDBY') => {
      ctx.fillStyle = '#060f1e';
      ctx.fillRect(0, 0, 512, 360);

      ctx.strokeStyle = 'rgba(6, 182, 212, 0.18)';
      ctx.lineWidth = 1;
      for (let x = 0; x < 512; x += 32) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, 360);
        ctx.stroke();
      }
      for (let y = 0; y < 360; y += 32) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(512, y);
        ctx.stroke();
      }

      ctx.fillStyle = '#0284c7';
      ctx.fillRect(0, 0, 512, 45);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 22px system-ui, sans-serif';
      ctx.fillText('Rx CLINICAL TABLET 3.0', 20, 32);

      ctx.strokeStyle = state.includes('ALERT') ? '#ef4444' : '#10b981';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(320, 24);
      ctx.lineTo(360, 24);
      ctx.lineTo(375, 8);
      ctx.lineTo(390, 40);
      ctx.lineTo(405, 16);
      ctx.lineTo(420, 24);
      ctx.lineTo(490, 24);
      ctx.stroke();

      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.strokeStyle = state.includes('ALERT') ? '#ef4444' : 'rgba(6, 182, 212, 0.4)';
      ctx.lineWidth = 2;
      ctx.strokeRect(30, 75, 452, 250);
      ctx.fillRect(30, 75, 452, 250);

      ctx.fillStyle = '#06b6d4';
      ctx.font = 'bold 56px serif';
      ctx.fillText('℞', 50, 140);

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 24px system-ui, sans-serif';
      ctx.fillText(title, 115, 125);

      ctx.fillStyle = state.includes('ALERT') ? '#ef4444' : '#38bdf8';
      ctx.font = '16px monospace';
      ctx.fillText(`STATUS: ${state}`, 115, 155);

      ctx.fillStyle = '#94a3b8';
      ctx.font = '15px system-ui, sans-serif';
      ctx.fillText('Handwriting Reading · NLEM 2022', 115, 185);
      ctx.fillText('LASA Shield Active · 100% Guarded', 115, 210);

      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(32, 245);
      ctx.lineTo(480, 245);
      ctx.stroke();

      if (animRefs.current.tabletScreenMesh?.material?.map) {
        animRefs.current.tabletScreenMesh.material.map.needsUpdate = true;
      }
    };

    updateTabletTexture();
    animRefs.current.updateTabletTextureFn = updateTabletTexture;

    const tabletTexture = new THREE.CanvasTexture(canvas);
    tabletTexture.needsUpdate = true;

    const tabletScreenMesh = new THREE.Mesh(
      tabletScreenGeo,
      new THREE.MeshBasicMaterial({ map: tabletTexture, toneMapped: false })
    );
    tabletScreenMesh.position.z = 0.022;
    tabletGroup.add(tabletScreenMesh);
    animRefs.current.tabletScreenMesh = tabletScreenMesh;

    // --- 6. RIGHT ARM & STYLUS PEN ---
    const rightArmGroup = new THREE.Group();
    rightArmGroup.position.set(0.62, 0.5, 0.05);
    torsoGroup.add(rightArmGroup);
    animRefs.current.rightArm = rightArmGroup;

    const rightUpperArmMesh = new THREE.Mesh(upperArmGeo, coatMat);
    rightUpperArmMesh.position.y = -0.25;
    rightArmGroup.add(rightUpperArmMesh);

    const rightForearmGroup = new THREE.Group();
    rightForearmGroup.position.set(0, -0.5, 0);
    rightArmGroup.add(rightForearmGroup);
    animRefs.current.rightHand = rightForearmGroup;

    const rightForearmMesh = new THREE.Mesh(upperArmGeo, coatMat);
    rightForearmMesh.position.y = -0.22;
    rightForearmGroup.add(rightForearmMesh);

    const rightHandMesh = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 16), skinMat);
    rightHandMesh.position.y = -0.48;
    rightForearmGroup.add(rightHandMesh);

    // Stylus Pen
    const stylusGeo = new THREE.CylinderGeometry(0.016, 0.016, 0.34, 12);
    const stylusMat = new THREE.MeshStandardMaterial({ color: 0x06b6d4, metalness: 0.8, roughness: 0.2 });
    const stylusMesh = new THREE.Mesh(stylusGeo, stylusMat);
    stylusMesh.rotation.x = Math.PI / 2;
    stylusMesh.position.set(0, -0.48, 0.1);
    rightForearmGroup.add(stylusMesh);

    const tipMesh = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 12), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
    tipMesh.position.set(0, -0.48, 0.28);
    rightForearmGroup.add(tipMesh);

    rightForearmGroup.rotation.x = -1.1;
    rightForearmGroup.rotation.y = -0.3;

    // --- MOUSE TRACKING & INTERACTION ---
    const handlePointerMove = (e) => {
      const rect = container.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const y = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
      animRefs.current.targetMouseX = x;
      animRefs.current.targetMouseY = y;

      if (animRefs.current.isDragging) {
        const deltaX = e.clientX - animRefs.current.dragPrevX;
        animRefs.current.rotY += deltaX * 0.01;
        animRefs.current.dragPrevX = e.clientX;
      }
    };

    const handlePointerDown = (e) => {
      animRefs.current.isDragging = true;
      animRefs.current.dragPrevX = e.clientX;
    };

    const handlePointerUp = () => {
      animRefs.current.isDragging = false;
    };

    window.addEventListener('pointermove', handlePointerMove);
    container.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointerup', handlePointerUp);

    // --- ANIMATION LOOP ---
    let animId;
    const clock = new THREE.Clock();

    const renderLoop = () => {
      animId = requestAnimationFrame(renderLoop);
      const delta = clock.getDelta();
      const time = clock.getElapsedTime();

      const r = animRefs.current;
      r.poseTime += delta;

      // Mouse tracking
      r.mouseX += (r.targetMouseX - r.mouseX) * 0.08;
      r.mouseY += (r.targetMouseY - r.mouseY) * 0.08;

      // Ambient breathing
      const breath = Math.sin(time * 2.2) * 0.02;
      torsoGroup.position.y = 1.35 + breath;

      if (r.ringPlatform) {
        r.ringPlatform.rotation.z = time * 0.4;
      }

      if (!r.isDragging) {
        r.rotY += (0 - r.rotY) * 0.03;
      }
      doctorGroup.rotation.y = r.rotY + r.mouseX * 0.35;

      // Head look-at
      if (r.head) {
        r.head.rotation.y = r.mouseX * 0.65;
        r.head.rotation.x = -r.mouseY * 0.35;
      }

      // Blinking
      r.blinkTimer += delta;
      if (r.blinkTimer > 3.5) {
        const blinkProgress = Math.sin((r.blinkTimer - 3.5) * Math.PI * 4);
        const eyelidScale = Math.max(0.01, Math.min(1.0, blinkProgress * 1.2));
        r.eyelids.forEach(lid => lid.scale.set(1, eyelidScale, 1));
        if (r.blinkTimer > 3.8) {
          r.blinkTimer = 0;
          r.eyelids.forEach(lid => lid.scale.set(1, 0.01, 1));
        }
      }

      // Mouth articulation
      if (r.mouth) {
        if (isSpeaking) {
          const speakMod = Math.sin(time * 16) * 0.6 + 0.5;
          r.mouth.scale.set(1 + speakMod * 0.4, 1 + speakMod * 1.4, 1);
        } else {
          r.mouth.scale.set(1, 1, 1);
        }
      }

      // Poses
      if (r.pose === 'wave') {
        if (r.rightArm && r.rightHand) {
          r.rightArm.rotation.z = -1.6;
          r.rightArm.rotation.x = 0.4;
          r.rightHand.rotation.x = -0.5;
          r.rightHand.rotation.z = Math.sin(time * 9) * 0.4;
        }
      } else if (r.pose === 'inspect') {
        if (r.rightArm && r.rightHand && r.head) {
          r.head.rotation.x = 0.28;
          r.rightArm.rotation.z = -0.3;
          r.rightArm.rotation.x = -0.6;
          r.rightHand.rotation.x = -1.2 + Math.sin(time * 7) * 0.12;
          r.rightHand.rotation.y = -0.4 + Math.cos(time * 7) * 0.15;
        }
      } else if (r.pose === 'approve') {
        if (r.rightArm && r.rightHand && r.head) {
          r.head.rotation.x = Math.sin(time * 5) * 0.12;
          r.rightArm.rotation.z = -0.9;
          r.rightArm.rotation.x = -0.4;
          r.rightHand.rotation.x = -0.9;
          r.rightHand.rotation.z = -0.4;
        }
      } else if (r.pose === 'alert') {
        if (r.alertLight) {
          r.alertLight.intensity = Math.sin(time * 8) > 0 ? 3.5 : 0.5;
        }
        if (r.head) {
          r.head.rotation.y = Math.sin(time * 6) * 0.25;
        }
      } else {
        if (r.alertLight) r.alertLight.intensity = 0;
        if (r.rightArm && r.rightHand) {
          r.rightArm.rotation.z = -0.15 + breath;
          r.rightArm.rotation.x = -0.2;
          r.rightHand.rotation.x = -1.0;
          r.rightHand.rotation.y = -0.3;
          r.rightHand.rotation.z = 0;
        }
      }

      renderer.render(scene, camera);
    };

    renderLoop();

    const handleResize = () => {
      if (!container || !renderer) return;
      const w = container.clientWidth || (compact ? 200 : 500);
      const h = container.clientHeight || (compact ? 140 : 480);
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
  }, [compact]);

  // COMPACT SUPERVISORY HUD MODE (Used when a prescription is active)
  if (compact) {
    return (
      <div
        className="glass-panel"
        style={{
          display: 'grid',
          gridTemplateColumns: '200px 1fr auto',
          gap: 20,
          padding: '14px 20px',
          borderRadius: 20,
          background: 'rgba(10, 17, 34, 0.92)',
          border: '1.5px solid rgba(6, 182, 212, 0.35)',
          boxShadow: '0 12px 35px rgba(0, 0, 0, 0.5), 0 0 25px rgba(6, 182, 212, 0.15)',
          alignItems: 'center',
          marginBottom: 20,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* 3D Doctor Viewport in Compact HUD */}
        <div
          ref={mountRef}
          style={{
            height: 140,
            borderRadius: 14,
            overflow: 'hidden',
            background: 'radial-gradient(circle at 50% 40%, rgba(6, 182, 212, 0.22) 0%, rgba(6, 10, 22, 0.9) 70%)',
            border: '1px solid rgba(6, 182, 212, 0.4)',
            cursor: 'grab',
            position: 'relative',
          }}
          title="Dr. Alex (Live 3D AI Clinician) — Drag to rotate"
        />

        {/* Live Speech Guidance & Clinical Recommendation */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span className="pulse-dot" style={{ background: '#10b981', width: 7, height: 7 }} />
            <span style={{ fontSize: '0.74rem', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.04em' }}>
              DR. ALEX · CLINICAL SUPERVISOR ACTIVE
            </span>
            <span className="glass-pill" style={{ padding: '2px 8px', fontSize: '0.68rem', textTransform: 'uppercase' }}>
              {currentPose}
            </span>
          </div>

          <p style={{ fontSize: '0.88rem', color: '#f8fafc', lineHeight: 1.45, fontWeight: 500 }}>
            {speechText}
          </p>
        </div>

        {/* Gesture Buttons & Voice Toggle */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
          <button
            onClick={toggleVoice}
            className="glass-pill"
            style={{
              background: soundEnabled ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.06)',
              borderColor: soundEnabled ? '#10b981' : 'rgba(255, 255, 255, 0.15)',
              color: soundEnabled ? '#10b981' : 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px 12px',
              fontSize: '0.74rem',
              fontWeight: 700,
            }}
          >
            {soundEnabled ? <Volume2 size={14} color="#10b981" /> : <VolumeX size={14} />}
            <span>{soundEnabled ? 'VOICE ON' : 'ENABLE VOICE'}</span>
          </button>

          <div style={{ display: 'flex', gap: 6 }}>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 8px', fontSize: '0.7rem', borderRadius: 8 }}
              onClick={() => triggerPose('wave', "Dr. Alex here! Reviewing every medication stroke against safety guidelines.")}
              title="Wave hello"
            >
              <Smile size={12} color="#06b6d4" />
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 8px', fontSize: '0.7rem', borderRadius: 8 }}
              onClick={() => triggerPose('inspect', "Inspecting cursive lettering and dose ranges.")}
              title="Inspect tablet"
            >
              <FileText size={12} color="#38bdf8" />
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 8px', fontSize: '0.7rem', borderRadius: 8 }}
              onClick={() => triggerPose('approve', "Standard dose confirmed under NLEM 2022.")}
              title="Approve dose"
            >
              <CheckCircle2 size={12} color="#10b981" />
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: '4px 8px', fontSize: '0.7rem', borderRadius: 8 }}
              onClick={() => triggerPose('alert', "High alert: Look-Alike drug confusion intercepted!")}
              title="LASA Alert"
            >
              <AlertTriangle size={12} color="#ef4444" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // FULL HERO 3D DOCTOR STUDIO (Default when landing or no prescription active)
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 480,
        borderRadius: 24,
        overflow: 'hidden',
        background: 'radial-gradient(circle at 50% 35%, rgba(6, 182, 212, 0.18) 0%, rgba(10, 15, 29, 0.95) 75%)',
        border: '1.5px solid rgba(6, 182, 212, 0.35)',
        boxShadow: '0 25px 60px rgba(0, 0, 0, 0.7), 0 0 35px rgba(6, 182, 212, 0.25)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Top Telemetry Overlay */}
      <div
        style={{
          position: 'absolute',
          top: 18,
          left: 18,
          right: 18,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          zIndex: 20,
          pointerEvents: 'none',
        }}
      >
        <div
          className="glass-pill"
          style={{
            pointerEvents: 'auto',
            background: 'rgba(6, 15, 30, 0.85)',
            borderColor: 'rgba(6, 182, 212, 0.4)',
            color: '#38bdf8',
            fontSize: '0.78rem',
            fontWeight: 800,
            letterSpacing: '0.04em',
            gap: 8,
          }}
        >
          <span className="pulse-dot" style={{ background: '#10b981', width: 8, height: 8 }} />
          <span>DR. ALEX · 3D CLINICAL AVATAR</span>
        </div>

        {/* Voice Audio Synthesis Switch */}
        <button
          onClick={toggleVoice}
          className="glass-pill"
          style={{
            pointerEvents: 'auto',
            background: soundEnabled ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.06)',
            borderColor: soundEnabled ? '#10b981' : 'rgba(255, 255, 255, 0.15)',
            color: soundEnabled ? '#10b981' : 'var(--text-muted)',
            cursor: 'pointer',
            padding: '6px 14px',
            fontSize: '0.76rem',
            fontWeight: 700,
          }}
          title={soundEnabled ? 'Click to Mute Doctor Voice' : 'Click to Enable Doctor Voice Speech'}
        >
          {soundEnabled ? (
            <>
              <Volume2 size={15} color="#10b981" />
              <span>VOICE ACTIVE</span>
              {isSpeaking && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', animation: 'pulseDot 0.8s infinite' }} />}
            </>
          ) : (
            <>
              <VolumeX size={15} />
              <span>ENABLE VOICE</span>
            </>
          )}
        </button>
      </div>

      {/* 3D WebGL Canvas Viewport */}
      <div
        ref={mountRef}
        style={{
          flex: 1,
          width: '100%',
          height: '100%',
          cursor: 'grab',
          position: 'relative',
        }}
        title="Click and drag to rotate Dr. Alex in 3D"
      />

      {/* Interactive Speech & Guidance Ribbon */}
      <div
        style={{
          position: 'absolute',
          bottom: 74,
          left: 18,
          right: 18,
          zIndex: 20,
          background: 'rgba(7, 12, 26, 0.88)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(6, 182, 212, 0.35)',
          borderRadius: 16,
          padding: '12px 18px',
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: 'rgba(6, 182, 212, 0.15)',
            border: '1px solid rgba(6, 182, 212, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Stethoscope size={18} color="#06b6d4" />
        </div>
        <p
          style={{
            fontSize: '0.84rem',
            color: '#f8fafc',
            lineHeight: 1.45,
            flex: 1,
            fontWeight: 500,
          }}
        >
          {speechText}
        </p>
      </div>

      {/* Interactive 3D Gesture & Interaction Toolbar */}
      <div
        style={{
          position: 'absolute',
          bottom: 16,
          left: 18,
          right: 18,
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: '0.75rem',
              borderRadius: 9999,
              background: currentPose === 'wave' ? 'rgba(6, 182, 212, 0.25)' : 'rgba(15, 23, 42, 0.85)',
              borderColor: currentPose === 'wave' ? '#06b6d4' : 'rgba(255, 255, 255, 0.12)',
            }}
            onClick={() => triggerPose('wave', "Hello there! I'm Dr. Alex. Let's inspect your prescription together!")}
          >
            <Smile size={13} color="#06b6d4" /> Wave
          </button>

          <button
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: '0.75rem',
              borderRadius: 9999,
              background: currentPose === 'inspect' ? 'rgba(6, 182, 212, 0.25)' : 'rgba(15, 23, 42, 0.85)',
              borderColor: currentPose === 'inspect' ? '#06b6d4' : 'rgba(255, 255, 255, 0.12)',
            }}
            onClick={() => triggerPose('inspect', "Inspecting handwriting strokes on the digital tablet. Checking NLEM catalog...")}
          >
            <FileText size={13} color="#38bdf8" /> Inspect Tablet
          </button>

          <button
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: '0.75rem',
              borderRadius: 9999,
              background: currentPose === 'approve' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(15, 23, 42, 0.85)',
              borderColor: currentPose === 'approve' ? '#10b981' : 'rgba(255, 255, 255, 0.12)',
            }}
            onClick={() => triggerPose('approve', "Prescription verified! All dosages comply with clinical formulary guidelines.")}
          >
            <CheckCircle2 size={13} color="#10b981" /> Approve
          </button>

          <button
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: '0.75rem',
              borderRadius: 9999,
              background: currentPose === 'alert' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(15, 23, 42, 0.85)',
              borderColor: currentPose === 'alert' ? '#ef4444' : 'rgba(255, 255, 255, 0.12)',
            }}
            onClick={() => triggerPose('alert', "High Alert: Celebrex vs Celexa carries major LASA confusion risk. Always double check!")}
          >
            <AlertTriangle size={13} color="#ef4444" /> LASA Alert
          </button>
        </div>

        {/* Quick Sample / Upload trigger on Doctor's tablet */}
        <div style={{ display: 'flex', gap: 6 }}>
          {onLoadSampleClick && (
            <button
              className="btn btn-primary"
              style={{ padding: '6px 14px', fontSize: '0.76rem', borderRadius: 9999 }}
              onClick={onLoadSampleClick}
            >
              <Sparkles size={13} /> Load Sample Script
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
