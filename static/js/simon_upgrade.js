/**
 * SIMON AI BRAIN - UPGRADE LAYER (ADDITIVE)
 * This script injects new content, transforms existing modals, and adds modern SaaS features.
 * strictly additive: Does not modify original source files.
 */

document.addEventListener('turbo:load', () => {
    initSimonUpgrade();
    initHeroAnimations(); // [NEW] Start GSAP animations
    initTypewriterEffect(); // [NEW] Start typewriter effect for brand text
    initChatSearch(); // [NEW] Search functionality for sidebar chats
});

/* =========================================
   10. CHAT SEARCH FUNCTIONALITY
   ========================================= */
function initChatSearch() {
    const searchToggle = document.getElementById('chat-search-toggle');
    const searchContainer = document.getElementById('chat-search-container');
    const searchInput = document.getElementById('chat-search-input');
    const chatsList = document.getElementById('your-chats-list');

    if (!searchToggle || !searchContainer || !searchInput || !chatsList) return;

    // Toggle search bar
    searchToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        searchContainer.classList.toggle('hidden');
        if (!searchContainer.classList.contains('hidden')) {
            setTimeout(() => searchInput.focus(), 100);
        } else {
            // Clear search when closing
            searchInput.value = '';
            filterChats('');
        }
    });

    // Handle search input
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        filterChats(query);
    });

    function filterChats(query) {
        const chatItems = chatsList.querySelectorAll('.sidebar-chat-item');

        chatItems.forEach(item => {
            // Find text content within the chat item (usually in a span or div)
            // Adjust selector based on actual chat item structure
            const textContent = item.textContent.toLowerCase();

            if (textContent.includes(query)) {
                item.style.display = 'flex'; // Assuming flex layout for chat items
            } else {
                item.style.display = 'none';
            }
        });
    }

    // Close search on Escape
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            searchContainer.classList.add('hidden');
            searchInput.value = '';
            filterChats('');
        }
    });
}

function initSimonUpgrade() {
    console.log("Initializing Simon AI Upgrade Layer...");

    // Skip all upgrade features on admin pages and dashboard
    if (window.location.pathname.includes('/admin') ||
        window.location.pathname.includes('/dashboard')) {
        console.log("Skipping Simon Upgrade on admin/dashboard pages");
        return;
    }

    // 1. Inject New Content Sections
    injectNewSections();

    // 2. Enhance Modals (Transform to Split Layout)
    // enhanceModals();



    // 5. Initialize Intersection Observer for Animations
    // 5. Initialize Intersection Observer for Animations
    initScrollReveal();

    // 6. Apply Dynamic Backgrounds
    applyDynamicBackgrounds();

    // 7. Dynamic Neural Pulses
    applyNeuralPulses();
}

/* =========================================
   1. CONTENT INJECTION
   ========================================= */
function injectNewSections() {
    // Double-check: never inject on admin or dashboard pages
    if (window.location.pathname.includes('/admin') ||
        window.location.pathname.includes('/dashboard')) {
        return;
    }

    const featuresSection = document.querySelector('.grid.grid-cols-1.md\\:grid-cols-3'); // Target the features grid
    if (!featuresSection) return;

    const upgradeContainer = document.createElement('div');
    upgradeContainer.id = 'simon-upgrade-container';

    // HTML Content Strings
    const logosHTML = '';

    const howItWorksHTML = `
        <div class="simon-section-container relative">
            <h2 class="simon-section-title simon-reveal">How Simon AI Works</h2>
            
            <!-- Process Background Visual -->
            <div class="absolute right-[-10%] top-[-20%] opacity-20 pointer-events-none z-0">
                 <img src="${window.simonAssets ? window.simonAssets.ghost_turbine : '#'}" class="w-[800px] animate-pulse-slow" alt="Process Turbine">
            </div>

            <div class="simon-flow-grid relative z-10">
                <!-- Step 1 -->
                <div class="simon-step-card simon-glass simon-reveal">
                    <span class="simon-step-number">01</span>
                    <h3 class="text-xl font-bold text-white mb-2">Ingest & Index</h3>
                    <p class="text-textSoft">Simon autonomously connects to your SAP, DAP, and PDF repositories, indexing over 1M+ technical data points securely.</p>
                </div>
                <!-- Step 2 -->
                <div class="simon-step-card simon-glass simon-reveal" style="transition-delay: 0.1s;">
                    <span class="simon-step-number">02</span>
                    <h3 class="text-xl font-bold text-white mb-2">Understand Context</h3>
                    <p class="text-textSoft">Using advanced LLMs, it builds a knowledge graph of your engineering assets, linking parts to procurement specs.</p>
                </div>
                <!-- Step 3 -->
                <div class="simon-step-card simon-glass simon-reveal" style="transition-delay: 0.2s;">
                    <span class="simon-step-number">03</span>
                    <h3 class="text-xl font-bold text-white mb-2">Instant Answers</h3>
                    <p class="text-textSoft">Ask complex questions like "Show me the DAP spec for the turbine blades" and get instant, cited answers.</p>
                </div>
            </div>
        </div>
    `;

    const useCasesHTML = `
        <div class="simon-section-container">
             <h2 class="simon-section-title simon-reveal">Enterprise Use Cases</h2>
             <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mt-12">
                <div class="simon-glass-high p-8 rounded-xl border border-white/10 simon-reveal">
                    <div class="rounded-full bg-accent/20 w-14 h-14 flex items-center justify-center mb-6 text-accent border border-accent/40 shadow-[0_0_15px_rgba(109,93,252,0.3)]">
                        <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    </div>
                    <h3 class="text-2xl font-bold text-white mb-2">Technical Procurement</h3>
                    <p class="text-textSoft leading-relaxed">Reduce "Request for Information" (RFI) cycles by 40% by instantly surfacing technical specs.</p>
                </div>
                <div class="simon-glass-high p-8 rounded-xl border border-white/10 simon-reveal">
                    <div class="rounded-full bg-secondary/20 w-14 h-14 flex items-center justify-center mb-6 text-secondary border border-secondary/40 shadow-[0_0_15px_rgba(46,230,255,0.3)]">
                        <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
                    </div>
                    <h3 class="text-2xl font-bold text-white mb-2">Compliance Audits</h3>
                    <p class="text-textSoft">Trace every decision back to the original source document. Full audit logs for enterprise security.</p>
                </div>
             </div>
        </div>
    `;

    const roadmapVisualHTML = `
        <div class="simon-section-container text-center pt-24 pb-32">
            <span class="simon-live-badge mb-4">Coming Q3 2026</span>
            <h2 class="text-4xl font-bold text-white mb-6">Generative Schematics</h2>
            <p class="text-xl text-textSoft max-w-2xl mx-auto">
                Simon won't just find diagrams. It will generate new schematics based on parameters you define.
            </p>
             <div class="mt-12 relative max-w-4xl mx-auto h-64 rounded-xl overflow-hidden border border-white/5 flex items-center justify-center group">
                 <!-- Glass Background -->
                 <div class="absolute inset-0 z-0">
                     <img src="${window.simonAssets ? window.simonAssets.glass_bg : '#'}" class="w-full h-full object-cover opacity-60" alt="System Preview">
                     <div class="absolute inset-0 bg-[#02040a]/80 backdrop-blur-sm"></div>
                 </div>
                 
                 <div class="absolute inset-0 bg-gradient-to-r from-accent/20 to-secondary/20 opacity-50 blur-3xl group-hover:opacity-70 transition duration-1000 z-0"></div>
                 <div class="z-10 text-white/30 font-mono text-sm relative">
                    [ SYSTEM PREVIEW - CONFIDENTIAL ] <br>
                    > Generating Schematic... 42%
                 </div>
             </div>
        </div>
    `;

    // Append all chunks
    upgradeContainer.innerHTML = logosHTML + howItWorksHTML + useCasesHTML + roadmapVisualHTML;

    // Insert AFTER the features section (parent of features section)
    featuresSection.parentElement.insertAdjacentElement('afterend', upgradeContainer);
}

/* =========================================
   2. MODAL ENHANCEMENT (SPLIT LAYOUT)
   ========================================= */
function enhanceModals() {
    // We attach a mutation observer or just hook into the existing 'window.openLoginModal' if possible.
    // Since we can't change the original file, we'll wrap the original function.

    const originalOpenLogin = window.openLoginModal;
    if (originalOpenLogin) {
        window.openLoginModal = function () {
            transformLoginModalDOM(); // Apply transform just before opening
            originalOpenLogin();
        };
    }

    const originalOpenSignup = window.openSignupModal;
    if (originalOpenSignup) {
        window.openSignupModal = function () {
            transformSignupModalDOM();
            originalOpenSignup();
        };
    }
}

function transformLoginModalDOM() {
    const modal = document.getElementById('login-modal');
    if (!modal || modal.dataset.upgraded === 'true') return;

    // Apply the grid container class
    modal.classList.add('simon-modal-split-container', 'simon-glass-high');

    // Create the visual column
    const visualCol = document.createElement('div');
    visualCol.className = 'simon-modal-visual';
    visualCol.innerHTML = `
        <div class="mb-auto w-full">
             <div class="flex items-center gap-2 mb-6">
                 <img src="${window.simonAssets ? window.simonAssets.logo : '#'}" alt="Simon Logo" class="h-8 w-auto">
             </div>
             <img src="${window.simonAssets ? window.simonAssets.login_ai : '#'}" alt="Access Terminal" class="w-full rounded-lg border border-accent/20 mb-4 opacity-90 shadow-[0_0_15px_rgba(100,255,218,0.1)]">
        </div>
        <div>
            <h3 class="text-2xl font-bold text-white mb-3">Welcome Back, Engineer.</h3>
            <p class="text-sm text-textSoft leading-relaxed mb-6">
                Your workspace is ready. New procurement data from Q1 has been indexed.
            </p>
            <div class="flex items-center gap-3 text-xs text-textSoft/70">
                <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-green-500"></span> System Online</span>
                <span>•</span>
                <span>v2.4.0 (Stable)</span>
            </div>
        </div>
    `;

    // Wrap existing content in a right-column div
    // We need to move all current children into a new 'div'
    const rightCol = document.createElement('div');
    rightCol.className = 'simon-modal-form-side';

    while (modal.firstChild) {
        rightCol.appendChild(modal.firstChild);
    }

    // Assemble split layout
    modal.appendChild(visualCol);
    modal.appendChild(rightCol);

    modal.dataset.upgraded = 'true';
}

function transformSignupModalDOM() {
    const modal = document.getElementById('signup-modal');
    if (!modal || modal.dataset.upgraded === 'true') return;

    modal.classList.add('simon-modal-split-container', 'simon-glass-high');

    const visualCol = document.createElement('div');
    visualCol.className = 'simon-modal-visual';
    visualCol.innerHTML = `
        <div class="mb-auto w-full">
             <div class="flex items-center gap-2 mb-6">
                 <img src="${window.simonAssets ? window.simonAssets.logo : '#'}" alt="Simon Logo" class="h-8 w-auto">
             </div>
             <img src="${window.simonAssets ? window.simonAssets.signup_ai : '#'}" alt="Join Network" class="w-full rounded-lg border border-accent/20 mb-4 opacity-90 shadow-[0_0_15px_rgba(100,255,218,0.1)]">
        </div>
        <div>
            <h3 class="text-2xl font-bold text-white mb-3">Join the Intelligence Network.</h3>
            <ul class="space-y-3 text-sm text-textSoft mb-6">
                <li class="flex items-center gap-2">
                    <svg class="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
                    Unlimited Queries
                </li>
                <li class="flex items-center gap-2">
                    <svg class="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
                    Access to SAP & DAP Connectors
                </li>
                <li class="flex items-center gap-2">
                    <svg class="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
                    Enterprise Security Shield
                </li>
            </ul>
        </div>
    `;

    const rightCol = document.createElement('div');
    rightCol.className = 'simon-modal-form-side';

    while (modal.firstChild) {
        rightCol.appendChild(modal.firstChild);
    }

    modal.appendChild(visualCol);
    modal.appendChild(rightCol);

    modal.dataset.upgraded = 'true';
}





/* =========================================
   5. ANIMATION & OBSERVER
   ========================================= */
function initScrollReveal() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target); // Only animate once
            }
        });
    }, observerOptions);

    // Observe all elements with .simon-reveal class (injected above)
    // We need to wait a tick for DOM injection
    setTimeout(() => {
        const targets = document.querySelectorAll('.simon-reveal');
        targets.forEach(target => observer.observe(target));
    }, 100);
}

/* =========================================
   6. DYNAMIC NEURAL PULSES
   ========================================= */
function applyNeuralPulses() {
    const container = document.querySelector('.simon-bg-glow-container');
    if (!container) return;

    setInterval(() => {
        const line = document.createElement('div');
        line.className = 'simon-neural-line simon-pulse-animation';

        // Random position
        const top = Math.random() * 100;
        const left = Math.random() * 100;
        const rotate = Math.random() * 360;

        line.style.top = `${top}%`;
        line.style.left = `${left}%`;
        line.style.transform = `rotate(${rotate}deg)`;

        container.appendChild(line);

        // Cleanup
        setTimeout(() => {
            line.remove();
        }, 3000);
    }, 2000);
}

function applyDynamicBackgrounds() {
    const canvas = document.getElementById('neuro-bg-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width, height;
    let particles = [];

    // Check for dark mode to adjust colors
    const isDark = document.documentElement.classList.contains('dark');
    const particleColor = isDark ? 'rgba(100, 200, 255, 0.3)' : 'rgba(0, 0, 0, 0.1)';
    const lineColor = isDark ? 'rgba(100, 200, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)';

    function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
        initParticles();
    }

    function initParticles() {
        particles = [];
        const count = Math.floor((width * height) / 20000); // Reasonable density
        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5,
                size: Math.random() * 2 + 1
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = particleColor;
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 0.5;

        for (let i = 0; i < particles.length; i++) {
            let p = particles[i];
            p.x += p.vx;
            p.y += p.vy;

            // Bounce off edges
            if (p.x < 0 || p.x > width) p.vx *= -1;
            if (p.y < 0 || p.y > height) p.vy *= -1;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fill();

            // Connect nearby particles
            for (let j = i + 1; j < particles.length; j++) {
                let p2 = particles[j];
                let dx = p.x - p2.x;
                let dy = p.y - p2.y;
                let dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 120) {
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(p2.x, p2.y);
                    // Fade out connection as distance increases
                    ctx.globalAlpha = 1 - (dist / 120);
                    ctx.stroke();
                    ctx.globalAlpha = 1.0;
                }
            }
        }
        requestAnimationFrame(draw);
    }

    window.addEventListener('resize', resize);
    resize();
    draw();
}

/* =========================================
   7. GSAP MOTION (Syncra)
   ========================================= */
function initHeroAnimations() {
    // Skip all animations on admin and dashboard pages
    if (window.location.pathname.includes('/admin') ||
        window.location.pathname.includes('/dashboard')) {
        return;
    }

    if (typeof gsap === 'undefined') {
        console.warn("GSAP not loaded");
        return;
    }

    // Hero Stagger - only run when target exists (e.g. landing page)
    const heroFade = document.querySelector(".gsap-hero-fade");
    if (heroFade) {
        gsap.from(".gsap-hero-fade", {
            y: 50,
            opacity: 0,
            duration: 1.2,
            stagger: 0.15,
            ease: "power3.out",
            delay: 0.2
        });
    }

    // Magnetic Buttons (EXCLUDE admin panel and chat elements)
    const buttons = document.querySelectorAll('button, .glass-card, .bento-card, .simon-sticky-cta');
    buttons.forEach(btn => {
        // Skip if element is inside admin panel, chat container, or is on admin page
        if (btn.closest('#admin-dashboard') ||
            btn.closest('.simon-chat-container') ||
            btn.closest('.simon-chat-form-inner') ||
            window.location.pathname.includes('/admin')) {
            return;
        }

        btn.addEventListener('mousemove', (e) => {
            const rect = btn.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            // Magnetic Pull
            gsap.to(btn, {
                x: (x - rect.width / 2) / 10,
                y: (y - rect.height / 2) / 10,
                duration: 0.3,
                ease: "power2.out"
            });
        });

        btn.addEventListener('mouseleave', () => {
            gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: "elastic.out(1, 0.3)" });
        });
    });
}

/* =========================================
   8. CRAZY CHAT ENHANCEMENTS
   ========================================= */
function initCrazyChat() {
    // Skip chat effects on admin pages
    if (window.location.pathname.includes('/admin')) {
        return;
    }

    const chatContainer = document.querySelector('.simon-chat-container');
    if (!chatContainer) return;

    // 1. Glitch Effect for Assistant Messages
    const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.classList && node.classList.contains('simon-message-group') && node.classList.contains('assistant')) {
                    const bubble = node.querySelector('.simon-chat-bubble');
                    if (bubble) applyGlitchEffect(bubble);
                }
            });
        });
    });

    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages) {
        observer.observe(chatMessages, { childList: true });
    }

    // 2. Magnetic Chat Console - DISABLED (floating effect not needed)
    // const chatInput = document.querySelector('.simon-chat-form-inner');
    // Commented out to prevent floating/3D tilt effects on chat input
}

function applyGlitchEffect(element) {
    if (!element || !document.contains(element) || typeof gsap === 'undefined') return;
    // Only glitch on arrival
    element.classList.add('glitch-active');

    // Create random "jumps" in opacity and translation
    const timeline = gsap.timeline();
    timeline.to(element, {
        x: () => (Math.random() - 0.5) * 5,
        opacity: 0.5,
        duration: 0.05,
        repeat: 5,
        yoyo: true,
        ease: "none"
    }).to(element, {
        x: 0,
        opacity: 1,
        duration: 0.2
    });

    setTimeout(() => {
        element.classList.remove('glitch-active');
    }, 1000);
}

// Ensure initCrazyChat runs
document.addEventListener('turbo:load', () => {
    initCrazyChat();
});

/* =========================================
   9. TYPEWRITER EFFECT
   ========================================= */
function initTypewriterEffect() {
    // Target landing page hero title
    const heroTitle = document.querySelector('.antigravity-text');
    if (heroTitle && window.location.pathname === '/') {
        const fullText = "Simon Intelligence\nAssistant";
        heroTitle.innerHTML = ''; // Clear for animation
        typeWriter(heroTitle, fullText, 80);
    }

    // Target search/chat page header
    const chatTitle = document.getElementById('chat-header-title');
    if (chatTitle && (window.location.pathname.includes('/search') || window.location.pathname.includes('/chat'))) {
        const fullText = "Simon Intelligence\nAssistant";
        chatTitle.innerHTML = ''; // Clear for animation
        typeWriter(chatTitle, fullText, 60);
    }
}

function typeWriter(element, text, speed) {
    let i = 0;
    element.innerHTML = '';

    // Add a blinking cursor
    const cursor = document.createElement('span');
    cursor.className = 'typewriter-cursor';
    cursor.innerHTML = '|';
    cursor.style.color = 'var(--simon-accent)';
    cursor.style.marginLeft = '2px';
    cursor.style.animation = 'blink 0.7s infinite';

    function type() {
        if (i < text.length) {
            if (text.charAt(i) === '\n') {
                element.appendChild(document.createElement('br'));
            } else {
                element.appendChild(document.createTextNode(text.charAt(i)));
            }
            element.appendChild(cursor);
            i++;
            setTimeout(type, speed);
        } else {
            // Optional: Remove cursor or stop blinking after finish
            cursor.style.animation = 'none';
            cursor.style.opacity = '0';
        }
    }

    // Add blink keyframes if not present
    if (!document.getElementById('typewriter-styles')) {
        const style = document.createElement('style');
        style.id = 'typewriter-styles';
        style.innerHTML = `
            @keyframes blink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0; }
            }
            .typewriter-cursor {
                display: inline-block;
                vertical-align: middle;
            }
        `;
        document.head.appendChild(style);
    }

    type();
}
