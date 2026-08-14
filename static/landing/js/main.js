if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
if (!window.location.hash) {
    window.scrollTo(0, 0);
}

document.addEventListener('DOMContentLoaded', () => {

    // -- GSAP Perspective Tilt on Hero Card --
    const quoteCard = document.querySelector('.hero-quote-card');
    if (quoteCard && typeof gsap !== 'undefined') {
        gsap.set(quoteCard, { perspective: 650 });

        const cardRX = gsap.quickTo(quoteCard, "rotationX", { duration: 0.6, ease: "power3" });
        const cardRY = gsap.quickTo(quoteCard, "rotationY", { duration: 0.6, ease: "power3" });
        const innerX = gsap.quickTo('.hero-quote-card .quote-items', "x", { duration: 0.6, ease: "power3" });
        const innerY = gsap.quickTo('.hero-quote-card .quote-items', "y", { duration: 0.6, ease: "power3" });

        quoteCard.addEventListener("pointermove", (e) => {
            const rect = quoteCard.getBoundingClientRect();
            const cx = (e.clientX - rect.left) / rect.width;
            const cy = (e.clientY - rect.top)  / rect.height;

            cardRX(gsap.utils.interpolate( 12, -12, cy));
            cardRY(gsap.utils.interpolate(-12,  12, cx));
            innerX(gsap.utils.interpolate(-20,  20, cx));
            innerY(gsap.utils.interpolate(-20,  20, cy));
        });

        quoteCard.addEventListener("pointerleave", () => {
            cardRX(0); cardRY(0);
            innerX(0); innerY(0);
        });
    }

    // -- Dynamic Active Navigation Track --
    const navLinks = document.querySelectorAll('.nav-links a[data-section]');
    const navSections = [
        { id: 'platform',  el: document.getElementById('platform') },
        { id: 'analytics', el: document.getElementById('analytics') },
        { id: 'dashboard', el: document.getElementById('dashboard') },
        { id: 'mission',   el: document.getElementById('ml') },
        { id: 'about',     el: document.getElementById('contact') }
    ];

    function updateActiveNav() {
        const scrollY = window.scrollY + window.innerHeight * 0.35;
        let active = null;
        for (const s of navSections) {
            if (s.el && s.el.offsetTop <= scrollY) active = s.id;
        }
        navLinks.forEach(a => {
            a.classList.toggle('active', a.dataset.section === active);
        });
    }
    window.addEventListener('scroll', updateActiveNav, { passive: true });
    updateActiveNav();

    // -- Three.js Canvas Initialization --
    const canvas = document.getElementById("scene");
    if (!canvas) return;

    console.log('[EarthScape] Creating renderer from: js/main.js');

    const renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
        35,
        window.innerWidth / window.innerHeight,
        0.1,
        2000
    );
    camera.position.set(0, 0, 11);
    camera.lookAt(0, 0, 0);

    // Build scene objects using global createEarth builder
    createEarth(scene);
    const earthGroup     = scene.earthGroup;
    const cloudMesh      = scene.cloudMesh;
    const satPoints      = scene.satPoints;
    const satelliteGroup = scene.satelliteGroup;
    const solarWingsGroup = scene.solarWingsGroup;

    // ✅ Fix: Remove depth hacks from satellite – it should write depth to block clouds correctly
    if (satelliteGroup) {
        satelliteGroup.traverse((child) => {
            if (child.isMesh && child.material) {
                child.material.depthTest = true;
                child.material.depthWrite = true;
                // Keep high renderOrder to ensure it's drawn after all other scene elements if needed
                child.renderOrder = 999;
            }
        });
    }

    try {
        renderer.compile(scene, camera);
        console.log('[EarthScape] Shaders compiled');
    } catch(e) {
        console.warn('[EarthScape] renderer.compile warning:', e);
    }

    function updateEarthPosition() {
        if (window.innerWidth < 992) {
            if (earthGroup) earthGroup.position.set(0, 0, 0);
        } else {
            if (earthGroup) earthGroup.position.set(3.2, -0.3, 0);
        }
    }
    updateEarthPosition();

    // -- Lenis Smooth Scroll Engine --
    let lenis = null;
    if (typeof Lenis !== 'undefined') {
        try {
            lenis = new Lenis({
                duration: 0.85,
                easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
                smoothWheel: true
            });
        } catch (e) {
            console.warn('[EarthScape] Lenis warning:', e);
        }
    }

    // -- GSAP ScrollTrigger Sequence & Parallax Pipelines --
    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
        gsap.registerPlugin(ScrollTrigger);

        if (lenis) {
            lenis.on('scroll', ScrollTrigger.update);
            gsap.ticker.add((time) => { lenis.raf(time * 1000); });
            gsap.ticker.lagSmoothing(0);
        }

        const setupScrollAnimations = () => {
            // Master 3D Scrubber Timeline – EARTH ONLY (satellite removed)
            const master3dTl = gsap.timeline({
                scrollTrigger: {
                    trigger: document.body,
                    start: "top top",
                    end: "bottom bottom",
                    scrub: 1.0
                }
            });

            // Earth movement – EXACTLY as original
            if (earthGroup) {
                master3dTl
                    .to(earthGroup.position, { x: (window.innerWidth >= 992) ? -2.2 : 0, y: -0.2, z: 0.5, duration: 1 }, 0)
                    .to(earthGroup.rotation, { y: Math.PI * 1.5, x: 0.2, duration: 1 }, 0)
                    .to(earthGroup.position, { x: 0, y: 0.4, z: 1.8, duration: 1.5 })
                    .to(earthGroup.rotation, { y: Math.PI * 3.0, x: -0.2, duration: 1.5 }, "<")
                    .to(earthGroup.position, { x: (window.innerWidth >= 992) ? 2.5 : 0, y: -0.3, z: 0.2, duration: 1.5 })
                    .to(earthGroup.rotation, { y: Math.PI * 4.2, x: 0.1, duration: 1.5 }, "<")
                    .to(earthGroup.position, { x: 0, y: 0, z: -0.5, duration: 1 })
                    .to(earthGroup.rotation, { y: Math.PI * 5.0, x: 0, duration: 1 }, "<");
            }

            // Section Headers & UI Animations – unchanged
            const sectionHeaders = document.querySelectorAll('.section-header h2, #section2-header .hero-heading');
            sectionHeaders.forEach((heading) => {
                if (!heading || !document.body.contains(heading)) return;
                gsap.set(heading, { opacity: 0, y: 30, filter: 'blur(4px)' });

                const headerSection = heading.closest('.section-header') || heading.closest('#section2-header');
                if (!headerSection) return;

                gsap.timeline({
                    scrollTrigger: {
                        trigger: headerSection,
                        start: 'top 80%',
                        once: true
                    }
                }).to(heading, {
                    opacity: 1,
                    y: 0,
                    filter: 'blur(0px)',
                    duration: 0.8,
                    ease: 'power3.out'
                });
            });

            document.querySelectorAll('.section-header .badge-tag, #section2-header .hero-chip').forEach(el => gsap.set(el, { opacity: 0, y: 20, scale: 0.85 }));
            document.querySelectorAll('.section-header p, #section2-header .hero-sub').forEach(el => gsap.set(el, { opacity: 0, y: 20 }));
            document.querySelectorAll('.section-header .hero-line, #section2-header .hero-line').forEach(el => gsap.set(el, { width: 0, opacity: 1 }));

            document.querySelectorAll('.section-header, #section2-header').forEach((header) => {
                if (!header || !document.body.contains(header)) return;
                const badge = header.querySelector('.badge-tag, .hero-chip');
                const para  = header.querySelector('p, .hero-sub');
                const line  = header.querySelector('.hero-line');

                const tl = gsap.timeline({
                    scrollTrigger: {
                        trigger: header,
                        start: 'top 78%',
                        once: true
                    }
                });

                if (badge) tl.to(badge, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'back.out(1.7)' }, 0);
                if (para)  tl.to(para, { opacity: 1, y: 0, duration: 0.6, ease: 'power2.out' }, '-=0.3');
                if (line) {
                    tl.to(line, { width: '60%', duration: 0.9, ease: 'power3.out' }, '-=0.35');
                    tl.to(line, { opacity: 0.5, duration: 1.2, ease: 'sine.inOut', yoyo: true, repeat: -1 }, '+=0.05');
                }
            });

            const ctaBox = document.querySelector('.cta-box');
            if (ctaBox && document.body.contains(ctaBox)) {
                const ctaTrigger = ctaBox.closest('.section-cta');
                const label   = ctaBox.querySelector('.badge-tag');
                const lines   = ctaBox.querySelectorAll('.demo-line');
                const subText = ctaBox.querySelector('.cta-line-sub');
                const btnWrap = ctaBox.querySelector('.cta-line-btn');

                const ctaTl = gsap.timeline({
                    scrollTrigger: {
                        trigger: ctaTrigger || ctaBox,
                        start: "top 75%",
                        toggleActions: "play none none reverse"
                    }
                });

                if (label)        ctaTl.from(label,   { y: 30, autoAlpha: 0, duration: 0.8, ease: "back.out(1.7)", immediateRender: false }, 0);
                if (lines.length) ctaTl.from(lines,   { y: 40, autoAlpha: 0, duration: 0.9, ease: "back.out(1.7)", stagger: 0.12, immediateRender: false }, 0.15);
                if (subText)      ctaTl.from(subText, { y: 25, autoAlpha: 0, duration: 0.7, ease: "power2.out", immediateRender: false }, "-=0.3");
                if (btnWrap)      ctaTl.from(btnWrap, { y: 20, autoAlpha: 0, scale: 0.9, duration: 0.7, ease: "back.out(1.7)", immediateRender: false }, "-=0.3");
            }

            document.querySelectorAll('.pipeline-step').forEach((step) => {
                if (!step) return;
                ScrollTrigger.create({
                    trigger: step,
                    start: "top 75%",
                    end: "bottom 35%",
                    onEnter:     () => step.classList.add('active'),
                    onLeaveBack: () => step.classList.remove('active')
                });
            });

            document.querySelectorAll('[data-parallax]').forEach((card) => {
                if (!card) return;
                const speed = parseFloat(card.getAttribute('data-parallax')) || 0.1;
                gsap.to(card, {
                    y: -50 * speed * 10,
                    scrollTrigger: {
                        trigger: card,
                        start: "top bottom",
                        end: "bottom top",
                        scrub: true
                    }
                });
            });
        };

        const refreshScrollTrigger = () => {
            requestAnimationFrame(() => {
                try {
                    ScrollTrigger.refresh();
                } catch (e) {
                    console.warn('[EarthScape] ScrollTrigger.refresh error', e);
                }
            });
        };

        setupScrollAnimations();
        refreshScrollTrigger();
    }

    // ============================================================
    // IMPROVED SATELLITE ORBIT – Closer to camera, no cloud clipping
    // ============================================================
    let orbitAngle = 0;

    // Start the satellite **outside** Earth’s clouds, clearly in the foreground
    if (satelliteGroup) {
        satelliteGroup.scale.set(0.7, 0.7, 0.7);          // bigger for better visibility
        satelliteGroup.position.set(5.0, 0.8, 4.0);       // out of cloud sphere, toward camera (+z)
    }

    function updateSatelliteOrbit() {
        if (!satelliteGroup || !earthGroup) return;

        orbitAngle += 0.002;                               // smooth rotation speed

        const earthWorldPos = new THREE.Vector3();
        earthGroup.getWorldPosition(earthWorldPos);

        // Orbit radius – keep it outside the clouds (Earth radius ≈ 3.05, clouds ≈ 3.07)
        const orbitRadius = 3.8;
        // Ellipse that leans **toward the camera** (+z) so the satellite feels closer
        const xOffset = Math.cos(orbitAngle) * orbitRadius * 0.9;
        const zOffset = Math.sin(orbitAngle) * orbitRadius * 0.6 + 2.5;  // positive bias
        const yOffset = Math.sin(orbitAngle * 1.3) * 0.7;

        const targetWorldPos = new THREE.Vector3(
            earthWorldPos.x + xOffset,
            earthWorldPos.y + yOffset,
            earthWorldPos.z + zOffset
        );

        // Smooth motion
        satelliteGroup.position.lerp(targetWorldPos, 0.04);

        // Always face Earth naturally
        const directionToEarth = new THREE.Vector3().copy(earthWorldPos).sub(satelliteGroup.position).normalize();
        const targetQuat = new THREE.Quaternion().setFromUnitVectors(
            new THREE.Vector3(0, 0, 1),
            directionToEarth
        );
        satelliteGroup.quaternion.slerp(targetQuat, 0.05);

        // Subtle solar panel tracking
        if (solarWingsGroup) {
            solarWingsGroup.rotation.x += 0.00015;
        }
    }

    // -- Animation Loop --
    function animate() {
        requestAnimationFrame(animate);

        if (earthGroup)    earthGroup.rotation.y += 0.0012;
        if (cloudMesh)     cloudMesh.rotation.y  += 0.0016;
        if (satPoints)   { satPoints.rotation.y  -= 0.0008; satPoints.rotation.x += 0.0003; }

        updateSatelliteOrbit();

        renderer.render(scene, camera);
    }

    console.log('[EarthScape] Starting render loop');
    animate();

    // -- Resize Handler --
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        updateEarthPosition();
        if (typeof ScrollTrigger !== 'undefined') {
            ScrollTrigger.refresh();
        }
    });
});