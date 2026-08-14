/* ============================================================
   ORPHANED PROTOTYPE — DO NOT LOAD ON LANDING PAGE
   This file creates a duplicate Lenis instance and a duplicate
   requestAnimationFrame loop. It belongs to an earlier prototype
   that used a different HTML structure (hero-content, #stars).
   The active cinematic controller is: static/js/cinematic_main.js
   ============================================================ */
const lenis = new Lenis({
    duration:1.4,
    smoothWheel:true
})

function raf(time){
    lenis.raf(time)
    requestAnimationFrame(raf)
}

requestAnimationFrame(raf)

gsap.registerPlugin(ScrollTrigger)

gsap.from(".hero-content",{
    y:100,
    opacity:0,
    duration:2,
    ease:"power4.out"
})

gsap.to("#stars",{
    backgroundPositionY:"400px",
    ease:"none",
    scrollTrigger:{
        trigger:"body",
        start:"top top",
        end:"bottom bottom",
        scrub:true
    }
})
