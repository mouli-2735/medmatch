import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

export default function ThreeDMedicalScene({ isScanning = false }) {
  const mountRef = useRef(null);

  useEffect(() => {
    const currentMount = mountRef.current;
    if (!currentMount) return;

    // Scene, Camera, Renderer
    const scene = new THREE.Scene();
    const width = currentMount.clientWidth || window.innerWidth || 800;
    const height = currentMount.clientHeight || window.innerHeight || 600;

    const camera = new THREE.PerspectiveCamera(
      45,
      width / height,
      0.1,
      1000
    );
    camera.position.z = 18;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    currentMount.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    scene.add(ambientLight);

    const pointLight1 = new THREE.PointLight(0x06b6d4, 3, 50);
    pointLight1.position.set(10, 10, 10);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0x10b981, 2.5, 50);
    pointLight2.position.set(-10, -10, 10);
    scene.add(pointLight2);

    // Group for objects
    const group = new THREE.Group();
    scene.add(group);

    // 1. Create 3D Medical Capsules
    const capsules = [];
    const capsuleGeometry = new THREE.CapsuleGeometry(0.7, 1.4, 16, 32);

    for (let i = 0; i < 6; i++) {
      const isCyan = i % 2 === 0;
      const material = new THREE.MeshPhysicalMaterial({
        color: isCyan ? 0x06b6d4 : 0x10b981,
        metalness: 0.1,
        roughness: 0.2,
        transmission: 0.6,
        thickness: 0.5,
        reflectivity: 0.9,
        clearcoat: 1.0,
        clearcoatRoughness: 0.1,
      });

      const mesh = new THREE.Mesh(capsuleGeometry, material);
      const angle = (i / 6) * Math.PI * 2;
      const radius = 5 + (i % 2) * 1.5;
      mesh.position.set(
        Math.cos(angle) * radius,
        Math.sin(angle) * radius * 0.6,
        (Math.random() - 0.5) * 4
      );
      mesh.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, 0);

      capsules.push({
        mesh,
        rotSpeedX: 0.005 + Math.random() * 0.01,
        rotSpeedY: 0.008 + Math.random() * 0.01,
        initialY: mesh.position.y,
        floatSpeed: 0.0015 + Math.random() * 0.001,
      });
      group.add(mesh);
    }

    // 2. Create Floating Molecular DNA Ring / Particle Points
    const particlesCount = 90;
    const positions = new Float32Array(particlesCount * 3);
    for (let i = 0; i < particlesCount * 3; i += 3) {
      positions[i] = (Math.random() - 0.5) * 18;
      positions[i + 1] = (Math.random() - 0.5) * 12;
      positions[i + 2] = (Math.random() - 0.5) * 8;
    }

    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const particleMaterial = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.18,
      transparent: true,
      opacity: 0.7,
      blending: THREE.AdditiveBlending,
    });

    const particleSystem = new THREE.Points(particleGeometry, particleMaterial);
    group.add(particleSystem);

    // Mouse Interaction
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    const handleMouseMove = (event) => {
      const rect = currentMount.getBoundingClientRect();
      mouseX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouseY = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    };

    window.addEventListener('mousemove', handleMouseMove);

    // Animation Loop
    let animationFrameId;
    let clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsedTime = clock.getElapsedTime();

      // Smooth mouse follow
      targetX = mouseX * 0.4;
      targetY = mouseY * 0.3;
      group.rotation.y += (targetX - group.rotation.y) * 0.05;
      group.rotation.x += (-targetY - group.rotation.x) * 0.05;

      // Animate capsules
      capsules.forEach((item, index) => {
        item.mesh.rotation.x += item.rotSpeedX * (isScanning ? 3 : 1);
        item.mesh.rotation.y += item.rotSpeedY * (isScanning ? 3 : 1);
        item.mesh.position.y = item.initialY + Math.sin(elapsedTime * 1.5 + index) * 0.4;
      });

      // Animate particle system
      particleSystem.rotation.y = elapsedTime * 0.04;

      renderer.render(scene, camera);
    };

    animate();

    // Resize Handler
    const handleResize = () => {
      if (!currentMount) return;
      camera.aspect = currentMount.clientWidth / currentMount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(currentMount.clientWidth, currentMount.clientHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
      if (currentMount && renderer.domElement) {
        currentMount.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [isScanning]);

  return (
    <div
      ref={mountRef}
      style={{
        width: '100%',
        height: '100%',
        position: 'absolute',
        top: 0,
        left: 0,
        pointerEvents: 'none',
        zIndex: 1,
      }}
    />
  );
}
