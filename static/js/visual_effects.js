/**
 * Glass Neuro Background & Dot Cursor Motion
 * Premium visual effects for post-login experience.
 * Wrapped so script is safe when re-executed (e.g. Turbo Drive navigation).
 */
(function () {
    if (window.__visualEffectsLoaded) return;
    window.__visualEffectsLoaded = true;

    class NeuroBackground {
    constructor() {
        this.canvas = document.getElementById('neuro-bg-canvas');
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.particles = [];
        this.particleCount = 120; // Increased to 120
        this.maxDist = 220; // Increased to 220
        this.mouse = { x: null, y: null };

        // Theme Configuration - Force Light Mode for "Premium Day Mode" experience
        this.currentTheme = 'light';
        this.updateThemeColors();

        this.init();
        this.animate();
        this.bindEvents();
    }

    updateThemeColors() {
        if (this.currentTheme === 'light') {
            // Softer, more ethereal colors for light mode
            this.particleBaseViolet = 'rgba(129, 140, 248, 0.2)';
            this.particleBaseSky = 'rgba(56, 189, 248, 0.2)';
            this.lineBaseColor = '129, 140, 248';
            this.lineOpacityFactor = 0.15;
            this.mouseBaseColor = '56, 189, 248';
            this.mouseOpacityFactor = 0.1;
        } else {
            // Higher energy neon colors for dark mode
            this.particleBaseViolet = 'rgba(109, 93, 252, 0.3)';
            this.particleBaseSky = 'rgba(14, 165, 233, 0.3)';
            this.lineBaseColor = '109, 93, 252';
            this.lineOpacityFactor = 0.3;
            this.mouseBaseColor = '14, 165, 233';
            this.mouseOpacityFactor = 0.2;
        }
    }

    init() {
        this.resize();
        this.particles = Array.from({ length: this.particleCount }, () => new Particle(this.canvas.width, this.canvas.height));
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    bindEvents() {
        window.addEventListener('resize', () => this.resize());
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });

        // Theme Change Listener
        window.addEventListener('theme-changed', (e) => {
            this.currentTheme = e.detail.theme;
            this.updateThemeColors();
        });
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        this.particles.forEach((p, i) => {
            p.update(this.canvas.width, this.canvas.height);

            // Draw particle with its specific color
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            this.ctx.fillStyle = p.color === 'violet' ? this.particleBaseViolet : this.particleBaseSky;
            this.ctx.fill();

            for (let j = i + 1; j < this.particles.length; j++) {
                const p2 = this.particles[j];
                const dx = p.x - p2.x;
                const dy = p.y - p2.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < this.maxDist) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(p.x, p.y);
                    this.ctx.lineTo(p2.x, p2.y);
                    // Dynamic Opacity based on theme
                    const opacity = this.lineOpacityFactor * (1 - dist / this.maxDist);
                    this.ctx.strokeStyle = `rgba(${this.lineBaseColor}, ${opacity})`;
                    this.ctx.lineWidth = 1;
                    this.ctx.stroke();
                }
            }

            // Mouse interaction
            if (this.mouse.x !== null) {
                const mdx = p.x - this.mouse.x;
                const mdy = p.y - this.mouse.y;
                const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
                if (mdist < 250) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(p.x, p.y);
                    this.ctx.lineTo(this.mouse.x, this.mouse.y);
                    // Dynamic Mouse Opacity
                    const mouseOpacity = this.mouseOpacityFactor * (1 - mdist / 250);
                    this.ctx.strokeStyle = `rgba(${this.mouseBaseColor}, ${mouseOpacity})`;
                    this.ctx.stroke();
                }
            }
        });

        requestAnimationFrame(() => this.animate());
    }
}

class Particle {
    constructor(width, height) {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.size = Math.random() * 2 + 1.5;
        this.vx = (Math.random() - 0.5) * 0.7;
        this.vy = (Math.random() - 0.5) * 0.7;
        // Distribute colors for "Energy Veins" mix
        this.color = Math.random() > 0.5 ? 'violet' : 'sky';
    }

    update(width, height) {
        this.x += this.vx;
        this.y += this.vy;

        if (this.x < 0 || this.x > width) this.vx *= -1;
        if (this.y < 0 || this.y > height) this.vy *= -1;
    }
}

class DotCursor {
    constructor() {
        this.cursor = document.querySelector('.dot-cursor');
        this.outline = document.querySelector('.dot-cursor-outline');
        if (!this.cursor || !this.outline) return;

        this.mouse = { x: 0, y: 0 };
        this.dotPos = { x: 0, y: 0 };
        this.outlinePos = { x: 0, y: 0 };

        this.init();
    }

    init() {
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;

            // Inner dot follows instantly
            this.cursor.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
        });

        // Initial Theme State
        this.updateTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light');

        // Theme Listener
        window.addEventListener('theme-changed', (e) => {
            this.updateTheme(e.detail.theme);
        });

        this.animate();
    }

    updateTheme(theme) {
        if (theme === 'light') {
            this.outline.style.borderColor = 'rgba(109, 93, 252, 0.4)';
            this.cursor.style.backgroundColor = '#6d5dfc';
        } else {
            this.outline.style.borderColor = ''; // Reset to CSS
            this.cursor.style.backgroundColor = ''; // Reset to CSS
        }
    }

    animate() {
        // Outline lags behind (interpolation)
        const lerp = (start, end, factor) => start + (end - start) * factor;

        this.outlinePos.x = lerp(this.outlinePos.x, this.mouse.x, 0.15);
        this.outlinePos.y = lerp(this.outlinePos.y, this.mouse.y, 0.15);

        this.outline.style.transform = `translate(${this.outlinePos.x}px, ${this.outlinePos.y}px)`;

        requestAnimationFrame(() => this.animate());
    }
}

    document.addEventListener('turbo:load', () => {
        new NeuroBackground();
        new DotCursor();
    });
})();
