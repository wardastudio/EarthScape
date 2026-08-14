// EarthScape AI Climate Intelligence Platform — Main Application Logic

// Force scroll to top on every page load when there is no hash anchor.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
if (!window.location.hash) {
    window.scrollTo(0, 0);
}

document.addEventListener('DOMContentLoaded', () => {

    // ── Hero Quote Card 3D Tilt (GSAP quickTo) ───────────────────────────────
    // Adapted from GSAPify: perspective tilt on .hero-quote-card,
    // with inner .quote-items shifting for parallax depth effect.
    const quoteCard = document.querySelector('.hero-quote-card');
    if (quoteCard && typeof gsap !== 'undefined') {
        gsap.set(quoteCard, { perspective: 650 });

        const cardRX  = gsap.quickTo(quoteCard, "rotationX", { duration: 0.6, ease: "power3" });
        const cardRY  = gsap.quickTo(quoteCard, "rotationY", { duration: 0.6, ease: "power3" });
        const innerX  = gsap.quickTo('.hero-quote-card .quote-items', "x", { duration: 0.6, ease: "power3" });
        const innerY  = gsap.quickTo('.hero-quote-card .quote-items', "y", { duration: 0.6, ease: "power3" });

        quoteCard.addEventListener("pointermove", (e) => {
            const rect = quoteCard.getBoundingClientRect();
            const cx = (e.clientX - rect.left) / rect.width;   // 0 → 1 across card
            const cy = (e.clientY - rect.top)  / rect.height;  // 0 → 1 down card

            cardRX(gsap.utils.interpolate( 12, -12, cy));  // tilt up/down
            cardRY(gsap.utils.interpolate(-12,  12, cx));  // tilt left/right
            innerX(gsap.utils.interpolate(-20,  20, cx));  // inner shift X
            innerY(gsap.utils.interpolate(-20,  20, cy));  // inner shift Y
        });

        quoteCard.addEventListener("pointerleave", () => {
            cardRX(0); cardRY(0);
            innerX(0); innerY(0);
        });
    }

    // ── Active Nav Highlight on Scroll ─────────────────────────────────────────
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

    // ── Three.js Renderer Setup ───────────────────────────────────────────────
    const canvas = document.getElementById("scene");
    if (!canvas) return;

    console.log('[EarthScape] Creating renderer from: js/main.js');
    console.log('[EarthScape] canvas:', canvas);
    console.log('[EarthScape] canvas size:', canvas.clientWidth, canvas.clientHeight);
    console.log('[EarthScape] renderer stack:', new Error().stack);

    const renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    console.log('[EarthScape] Renderer created');

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
        35,
        window.innerWidth / window.innerHeight,
        0.1,
        2000
    );
    camera.position.set(0, 0, 11);
    camera.lookAt(0, 0, 0);
    const clock = new THREE.Clock();
    console.log('[EarthScape] Scene created');

    const world = createEarth(scene);
    const earthGroup = scene.earthGroup;
    const cloudMesh = scene.cloudMesh;
    const satPoints = scene.satPoints;
    const satelliteGroup = scene.satelliteGroup;

    console.log('[EarthScape] Earth created, earthGroup:', !!earthGroup);

    // Force shader compilation and texture upload before first render.
    // Without this, ShaderMaterial uniforms that reference not-yet-decoded
    // textures produce a black/invisible Earth on fast refreshes.
    try {
        renderer.compile(scene, camera);
        console.log('[EarthScape] Shaders compiled');
    } catch(e) {
        console.warn('[EarthScape] renderer.compile warning:', e);
    }

    function updateEarthPosition() {
        if (window.innerWidth < 992) {
            earthGroup.position.set(0, 0, 0);
        } else {
            earthGroup.position.set(3.2, -0.3, 0);
        }
    }
    updateEarthPosition();

    // ── Smooth Scroll (Lenis) ────────────────────────────────────────────────
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

    // ── GSAP & ScrollTrigger ─────────────────────────────────────────────────
    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
        gsap.registerPlugin(ScrollTrigger);

        if (lenis) {
            lenis.on('scroll', ScrollTrigger.update);
            gsap.ticker.add((time) => { lenis.raf(time * 1000); });
            gsap.ticker.lagSmoothing(0);
        }

        const isElement = (target) => target && target.nodeType === 1;
        const resolveTrigger = (target) => {
            if (!target) return null;
            if (typeof target === 'string') return document.querySelector(target);
            return isElement(target) ? target : null;
        };

        const createSafeTimeline = (config) => {
            const trigger = resolveTrigger(config.scrollTrigger?.trigger);
            if (!trigger) {
                console.warn('[EarthScape] ScrollTrigger skipped missing trigger', config.scrollTrigger);
                return null;
            }
            return gsap.timeline(config);
        };

        const setupScrollAnimations = () => {
            console.log('[EarthScape] Initializing ScrollTrigger animations');

            // 1. Dual 3D Earth Globe & 3D Satellite Multi-Stage Parallax Timeline
            console.log('[EarthScape] ST: master3dTl trigger=body');
            const master3dTl = gsap.timeline({
                scrollTrigger: {
                    trigger: document.body,
                    start: "top top",
                    end: "bottom bottom",
                    scrub: 1.2
                }
            });

            // STAGE 1: Hero -> Section 2 (Real-Time Ingestion)
            master3dTl
                .to(earthGroup.position, { x: (window.innerWidth >= 992) ? -2.2 : 0, y: -0.2, z: 1.0, duration: 1 }, 0)
                .to(earthGroup.rotation, { y: Math.PI * 1.5, x: 0.2, duration: 1 }, 0);

            if (satelliteGroup) {
                master3dTl
                    .to(satelliteGroup.position, { x: 1.2, y: 0.3, z: 3.5, duration: 1 }, 0)
                    .to(satelliteGroup.rotation, { y: -Math.PI * 0.8, x: 0.5, duration: 1 }, 0);
            }

            // STAGE 2: Section 2 -> Section 4 (Big Data & AI Analysis)
            master3dTl
                .to(earthGroup.position, { x: 0, y: 0.5, z: 2.8, duration: 1.5 })
                .to(earthGroup.rotation, { y: Math.PI * 3.0, x: -0.3, duration: 1.5 }, "<");

            if (satelliteGroup) {
                master3dTl
                    .to(satelliteGroup.position, { x: -3.0, y: 1.5, z: 1.0, duration: 1.5 }, "<")
                    .to(satelliteGroup.rotation, { y: Math.PI * 1.2, x: -0.2, duration: 1.5 }, "<");
            }

            // STAGE 3: Section 4 -> Section 6 (Dashboard Command Center)
            master3dTl
                .to(earthGroup.position, { x: (window.innerWidth >= 992) ? 2.5 : 0, y: -0.3, z: 0.5, duration: 1.5 })
                .to(earthGroup.rotation, { y: Math.PI * 4.2, x: 0.1, duration: 1.5 }, "<");

            if (satelliteGroup) {
                master3dTl
                    .to(satelliteGroup.position, { x: 2.2, y: -0.8, z: 2.0, duration: 1.5 }, "<")
                    .to(satelliteGroup.rotation, { y: Math.PI * 2.8, x: 0.4, duration: 1.5 }, "<");
            }

            // STAGE 4: Section 6 -> Section 8 (CTA)
            master3dTl
                .to(earthGroup.position, { x: 0, y: 0, z: -1.0, duration: 1 })
                .to(earthGroup.rotation, { y: Math.PI * 5.0, x: 0, duration: 1 }, "<");

            if (satelliteGroup) {
                master3dTl
                    .to(satelliteGroup.position, { x: 0, y: 2.5, z: 0, duration: 1 }, "<")
                    .to(satelliteGroup.rotation, { y: Math.PI * 3.5, x: 0, duration: 1 }, "<");
            }

            // ── Section heading entrance animation ──────────────────────────────
            // Animate the whole heading as a single element, not per character.
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

            document.querySelectorAll('.section-header .badge-tag, #section2-header .hero-chip').forEach(el => {
                gsap.set(el, { opacity: 0, y: 20, scale: 0.85 });
            });
            document.querySelectorAll('.section-header p, #section2-header .hero-sub').forEach(el => {
                gsap.set(el, { opacity: 0, y: 20 });
            });
            document.querySelectorAll('.section-header .hero-line, #section2-header .hero-line').forEach(el => {
                gsap.set(el, { width: 0, opacity: 1 });
            });

            document.querySelectorAll('.section-header, #section2-header').forEach((header) => {
                if (!header || !document.body.contains(header)) return;
                const badge   = header.querySelector('.badge-tag, .hero-chip');
                const para    = header.querySelector('p, .hero-sub');
                const line    = header.querySelector('.hero-line');

                const tl = gsap.timeline({
                    scrollTrigger: {
                        trigger: header,
                        start: 'top 78%',
                        once: true
                    }
                });

                if (badge) {
                    tl.to(badge, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'back.out(1.7)' }, 0);
                }
                if (para) {
                    tl.to(para, { opacity: 1, y: 0, duration: 0.6, ease: 'power2.out' }, '-=0.3');
                }
                if (line) {
                    tl.to(line, { width: '60%', duration: 0.9, ease: 'power3.out' }, '-=0.35');
                    tl.to(line, { opacity: 0.5, duration: 1.2, ease: 'sine.inOut', yoyo: true, repeat: -1 }, '+=0.05');
                }
            });

            // 4. Section 8 CTA Stagger Animation
            const ctaBox = document.querySelector('.cta-box');
            if (ctaBox && document.body.contains(ctaBox)) {
                console.log('[EarthScape] ST: CTA trigger=.section-cta');
                const ctaTrigger = ctaBox.closest('.section-cta');
                if (!ctaTrigger) {
                    console.warn('[EarthScape] ST: missing .section-cta wrapper for CTA animations. Falling back to ctaBox.');
                }

                const label    = ctaBox.querySelector('.badge-tag');
                const lines    = ctaBox.querySelectorAll('.demo-line');
                const subText  = ctaBox.querySelector('.cta-line-sub');
                const btnWrap  = ctaBox.querySelector('.cta-line-btn');

                const ctaTl = gsap.timeline({
                    scrollTrigger: {
                        trigger: ctaTrigger || ctaBox,
                        start: "top 75%",
                        toggleActions: "play none none reverse"
                    }
                });

                if (label)            ctaTl.from(label,   { y: 30, autoAlpha: 0, duration: 0.8, ease: "back.out(1.7)", immediateRender: false }, 0);
                if (lines.length > 0) ctaTl.from(lines,   { y: 40, autoAlpha: 0, duration: 0.9, ease: "back.out(1.7)", stagger: 0.12, immediateRender: false }, 0.15);
                if (subText)          ctaTl.from(subText,  { y: 25, autoAlpha: 0, duration: 0.7, ease: "power2.out", immediateRender: false }, "-=0.3");
                if (btnWrap)          ctaTl.from(btnWrap,  { y: 20, autoAlpha: 0, scale: 0.9, duration: 0.7, ease: "back.out(1.7)", immediateRender: false }, "-=0.3");
            }

            // 5. Pipeline Step Highlight on Scroll
            document.querySelectorAll('.pipeline-step').forEach((step) => {
                if (!step) return;
                console.log('[EarthScape] ST: pipeline step trigger=', step.id);
                ScrollTrigger.create({
                    trigger: step,
                    start: "top 75%",
                    end: "bottom 35%",
                    onEnter:     () => step.classList.add('active'),
                    onLeaveBack: () => step.classList.remove('active')
                });
            });

            // 6. Subtle Card Parallax (Section 2)
            document.querySelectorAll('[data-parallax]').forEach((card) => {
                if (!card) return;
                const speed = parseFloat(card.getAttribute('data-parallax')) || 0.1;
                console.log('[EarthScape] ST: parallax card trigger=', card.className.split(' ')[0]);
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
                    console.log('[EarthScape] ScrollTrigger refreshed');
                } catch (e) {
                    console.warn('[EarthScape] ScrollTrigger.refresh error', e);
                }
            });
        };

        if (document.readyState === 'complete') {
            setupScrollAnimations();
            refreshScrollTrigger();
        } else {
            window.addEventListener('load', () => {
                setupScrollAnimations();
                refreshScrollTrigger();
                updateActiveNav();
            }, { once: true });
        }
    }


    // ── Render Loop ───────────────────────────────────────────────────────────
    let frameCount = 0;
    function animate() {
        requestAnimationFrame(animate);
        if (earthGroup)  earthGroup.rotation.y += 0.0012;
        if (cloudMesh)   cloudMesh.rotation.y  += 0.0016;
        if (satPoints) { satPoints.rotation.y  -= 0.0008; satPoints.rotation.x += 0.0003; }
        if (satelliteGroup) { satelliteGroup.rotation.z += 0.0015; }
        renderer.render(scene, camera);
        if (frameCount === 0) console.log('[EarthScape] First render frame OK');
        frameCount++;
    }
    // Defer animate() by one rAF so the browser has committed the first layout
    // and all texture ImageBitmaps have had a chance to upload to the GPU.
    requestAnimationFrame(() => {
        console.log('[EarthScape] Starting render loop');
        animate();
    });

    // ── Window Resize ─────────────────────────────────────────────────────────
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        updateEarthPosition();
    });
});
