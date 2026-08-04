// main.js — AIForge Technologies
// Handles: mobile nav toggle, active-link highlighting, smooth-scroll
// for in-page anchors, simple form helpers.


document.addEventListener("DOMContentLoaded", () => {
    initMobileNav();
    initActiveLink();
    initSmoothScroll();
    initNavbarScroll();
});


// ------------------------------------------------------------------ //
// Mobile nav toggle                                                   //
// ------------------------------------------------------------------ //
function initMobileNav() {
    const toggle = document.getElementById("navToggle");
    const panel  = document.getElementById("navCollapsible");
    if (!toggle || !panel) return;

    const setOpen = (open) => {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
        panel.classList.toggle("open", open);
        document.body.classList.toggle("nav-open", open);
    };

    toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        const isOpen = toggle.getAttribute("aria-expanded") === "true";
        setOpen(!isOpen);
    });

    // Close the menu when a real link is tapped
    panel.addEventListener("click", (event) => {
        const link = event.target.closest("a");
        if (!link) return;
        const href = link.getAttribute("href") || "";
        if (href === "" || href === "#" || href.startsWith("#")) return;
        setOpen(false);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 820) setOpen(false);
    });
}


// ------------------------------------------------------------------ //
// Active link highlight based on current path                         //
// ------------------------------------------------------------------ //
function initActiveLink() {
    const links = document.querySelectorAll(".nav-menu a");
    if (!links.length) return;
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    links.forEach((link) => {
        const href = (link.getAttribute("href") || "").replace(/\/+$/, "") || "/";
        if (href === path) {
            link.classList.add("active");
            link.setAttribute("aria-current", "page");
        }
    });
}


// ------------------------------------------------------------------ //
// Smooth scroll for in-page anchors                                   //
// ------------------------------------------------------------------ //
function initSmoothScroll() {
    // 1. Same-page hash clicks → smooth scroll, no full navigation.
    //    Cross-page links like `/services#custom-ai` are LEFT ALONE
    //    so the browser navigates normally; once on the target page,
    //    the load handler below takes over.
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener("click", (event) => {
            const id = anchor.getAttribute("href");
            if (!id || id.length < 2) return;
            const target = document.querySelector(id);
            if (!target) return;
            event.preventDefault();
            target.scrollIntoView({ behavior: "smooth", block: "start" });
            // Keep the address bar in sync without a jump.
            history.replaceState(null, "", id);
        });
    });

    // 2. On page load (or full navigation to `/services#xxx`), animate
    //    to the named anchor instead of letting the browser jump.
    if (window.location.hash && window.location.hash.length > 1) {
        const target = document.querySelector(window.location.hash);
        if (target) {
            // Wait one frame so layout/CSS (incl. scroll-margin-top) settles.
            requestAnimationFrame(() => {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        }
    }
}


// ------------------------------------------------------------------ //
// Glassmorphism "is-scrolled" state for the navbar                     //
// ------------------------------------------------------------------ //
function initNavbarScroll() {
    const navbar = document.querySelector(".navbar");
    if (!navbar) return;

    const threshold = 16;
    let ticking = false;

    const update = () => {
        navbar.classList.toggle("is-scrolled", window.scrollY > threshold);
        ticking = false;
    };

    window.addEventListener("scroll", () => {
        if (!ticking) {
            window.requestAnimationFrame(update);
            ticking = true;
        }
    }, { passive: true });

    update(); // initial state in case the page loads already scrolled
}
