import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

// --- CONFIGURATION: ELEGANT LIGHT THEME ---
const COLORS = {
    steel: 0xd1d5db,       // Matte Light Gray (Steel)
    darkSteel: 0x475569,   // Matte Charcoal
    concrete: 0xcbd5e1,    // Light Concrete
    ammonia: 0x38bdf8,     // Soft Sky Blue (Cooling/Ammonia)
    acid: 0xf59e0b,        // Warm Amber (Acids)
    slurry: 0xa855f7,      // Soft Purple (Mixed Slurry)
    gas: 0x10b981,         // Sage Green (Vapors/Gas)
    steam: 0xffffff,       // Clean White (Steam)
    yellow: 0xeab308,      // Muted Yellow
    highlight: 0x2563eb,   // Primary Blue Focus
    grid: 0xe2e8f0         // Very faint grid lines
};

// --- GLOBAL STATE ---
let scene, camera, renderer, labelRenderer, controls, composer;
let raycaster, mouse;
let interactables = [];
let flowParticles = [];
let orbitalRing, reactorCore; // Environment elements
let dustParticles;
let isFlowActive = true;
let labelVisible = true;

// --- STEP-BY-STEP VIEW STATE ---
let stepRegistry = []; // { object: THREE.Object3D, step: number }
let currentStep = 0;
const MAX_STEPS = 6;
let headerTimeout;

const clock = new THREE.Clock();

// --- INITIALIZATION ---
function init() {
    // Scene - Elegant Studio Void
    scene = new THREE.Scene();
    // Distance fog for soft depth
    scene.fog = new THREE.FogExp2(0xf8fafc, 0.001);

    // Camera
    camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 1, 3000);
    camera.position.set(0, 150, 350); // Adjusted for quadrant layout

    // Renderer
    const canvasContainer = document.getElementById('canvas-container');
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); // Alpha true for background CSS gradient
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true; // Enable soft shadows
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // Set clear color to transparent to see the CSS background
    renderer.setClearColor(0x000000, 0);
    canvasContainer.appendChild(renderer.domElement);

    // Label Renderer
    labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(window.innerWidth, window.innerHeight);
    labelRenderer.domElement.style.position = 'absolute';
    labelRenderer.domElement.style.top = '0px';
    labelRenderer.domElement.style.pointerEvents = 'none';
    document.querySelector('.ui-layer').appendChild(labelRenderer.domElement);

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 + 0.1; // Allow slight look under

    // Improved Camera Controls for manual inspection - adjusted for wider spacing
    controls.target.set(0, 0, 0); // Center on the quadrants
    controls.minDistance = 50;       // Don't clip into objects
    controls.maxDistance = 1000;      // Keep the wider plant in view
    controls.autoRotate = false;     // Disable auto-rotate for manual control

    setupPostProcessing();
    setupLighting();
    createEnvironment(); // Grid floor
    createOrbitalBackground(); // New Orbital Environment
    buildPlant();
    setupInteraction();

    window.addEventListener('resize', onWindowResize);

    // Fade out loader
    setTimeout(() => {
        const loader = document.getElementById('loading-screen');
        if (loader) {
            loader.style.opacity = 0;
            setTimeout(() => loader.remove(), 1000);
        }
    }, 500);

    animate();
}

function setupPostProcessing() {
    const renderScene = new RenderPass(scene, camera);
    // Almost invisible bloom just for highlights
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.0, 0.1, 0.95);
    bloomPass.threshold = 0.8;
    bloomPass.strength = 0.15; // Very subtle
    bloomPass.radius = 0.2;

    composer = new EffectComposer(renderer);
    composer.addPass(renderScene);
    composer.addPass(bloomPass);
}

function setupLighting() {
    // Elegant Studio Lighting Setup
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7); // Bright soft ambient
    scene.add(ambientLight);

    // Main Studio Key Light (Warm white)
    const mainLight = new THREE.DirectionalLight(0xfffbf0, 1.0);
    mainLight.position.set(150, 200, 150);
    mainLight.castShadow = true;
    mainLight.shadow.camera.top = 200;
    mainLight.shadow.camera.bottom = -200;
    mainLight.shadow.camera.left = -200;
    mainLight.shadow.camera.right = 200;
    mainLight.shadow.mapSize.width = 2048;
    mainLight.shadow.mapSize.height = 2048;
    mainLight.shadow.bias = -0.001;
    scene.add(mainLight);

    // Studio Fill Light (Cool white, from opposite side)
    const fillLight = new THREE.DirectionalLight(0xe0f2fe, 0.5);
    fillLight.position.set(-150, 100, -150);
    scene.add(fillLight);

    // Subtle Underlight to soften stark shadows on the bottom
    const bottomLight = new THREE.DirectionalLight(0xffffff, 0.3);
    bottomLight.position.set(0, -100, 0);
    scene.add(bottomLight);
}

function createEnvironment() {
    // Very subtle, clean floor grid
    const gridSize = 1200;
    const divisions = 120;

    const gridHelper = new THREE.GridHelper(gridSize, divisions, COLORS.grid, COLORS.grid);
    gridHelper.position.y = -0.9;
    gridHelper.material.transparent = true;
    gridHelper.material.opacity = 0.6; // Light grid on light floor
    scene.add(gridHelper);

    // Clean white studio floor to catch soft shadows
    const planeGeo = new THREE.PlaneGeometry(gridSize, gridSize);
    const planeMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        roughness: 0.1, // Semi-glossy
        metalness: 0.05,
        transparent: true,
        opacity: 0.9 // Let some of the CSS gradient bleed through
    });
    const plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = -1.0;
    plane.receiveShadow = true;
    scene.add(plane);
}

function createOrbitalBackground() {
    // Transparent background, CSS handles the elegant gradient
    // We already set renderer.setClearColor(0x000000, 0); 
    // Just ensure fog is elegant
    scene.fog = new THREE.FogExp2(0xf8fafc, 0.0012);
}



// --- ASSET BUILDER (ELEGANT/MODERN STYLE) ---
const builder = {
    // Beautiful frosted glass / plastic
    getHoloMat: (color) => {
        return new THREE.MeshPhysicalMaterial({
            color: color,
            metalness: 0.1,
            roughness: 0.2,
            transmission: 0.9,     // Highly transparent glass
            thickness: 0.5,        // Refraction thickness
            ior: 1.5,              // Glass index of refraction
            opacity: 1.0,
            transparent: true,
            side: THREE.DoubleSide
        });
    },

    getWireframeMat: (color) => {
        return new THREE.MeshBasicMaterial({
            color: color,
            wireframe: true,
            transparent: true,
            opacity: 0.15 // Very faint elegant wireframes
        });
    },

    createTank: (name, radius, height, pos, color, hasMixer = false) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Inner Solid Core (Solid matte color)
        const coreGeo = new THREE.CylinderGeometry(radius * 0.95, radius * 0.95, height, 32);
        const coreMat = new THREE.MeshStandardMaterial({
            color: color,
            roughness: 0.6,
            metalness: 0.1
        });
        const core = new THREE.Mesh(coreGeo, coreMat);
        core.position.y = height / 2;
        core.castShadow = true;
        core.receiveShadow = true;
        group.add(core);

        // Outer Glass Shell
        const shellGeo = new THREE.CylinderGeometry(radius, radius, height, 32);
        const shellMat = builder.getHoloMat(0xffffff); // Clear glass shell
        const shell = new THREE.Mesh(shellGeo, shellMat);
        shell.position.y = height / 2;
        shell.receiveShadow = true;
        group.add(shell);

        // Clean Trim Rings (No neon)
        const ringGeo = new THREE.TorusGeometry(radius + 0.1, 0.05, 16, 100);
        const ringMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel, roughness: 0.5 });

        const topRing = new THREE.Mesh(ringGeo, ringMat);
        topRing.rotation.x = Math.PI / 2;
        topRing.position.y = height;
        group.add(topRing);

        const bottomRing = new THREE.Mesh(ringGeo, ringMat);
        bottomRing.rotation.x = Math.PI / 2;
        bottomRing.position.y = 0;
        group.add(bottomRing);

        if (hasMixer) {
            const motorGeo = new THREE.BoxGeometry(2, 2, 2);
            const motorMat = new THREE.MeshStandardMaterial({ color: color, emissive: color, emissiveIntensity: 0.5 });
            const motor = new THREE.Mesh(motorGeo, motorMat);
            motor.position.y = height + 1;
            group.add(motor);
        }

        addLabel(group, name, height + 4);
        group.userData = { name: name, type: 'STORAGE UNIT', desc: `Standard containment vessel for ${name}. Monitor levels strictly.` };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createPipeReactor: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        const mat = builder.getHoloMat(0xffffff);
        const pipe = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, 25, 32), mat);
        pipe.rotation.z = Math.PI / 2;
        pipe.castShadow = true;
        group.add(pipe);

        // Solid Helix inside
        const curve = new THREE.CatmullRomCurve3([
            new THREE.Vector3(-12, 0, 0), new THREE.Vector3(12, 0, 0)
        ]);
        const helixGeo = new THREE.TubeGeometry(curve, 20, 0.2, 8, false);
        const helixMat = new THREE.MeshStandardMaterial({ color: COLORS.highlight, roughness: 0.4 });
        const helix = new THREE.Mesh(helixGeo, helixMat);
        group.add(helix);

        addLabel(group, 'PIPE REACTOR', 5);
        group.userData = { name: 'PIPE REACTOR', type: 'CORE PROCESS', desc: 'High-pressure conversion unit. Critical path.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createScrubber: (name, pos, height, hasStack = false) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const r = 3;

        // Glowing Base
        const sump = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 5, 32), new THREE.MeshStandardMaterial({ color: COLORS.slurry, emissive: COLORS.slurry, emissiveIntensity: 0.4 }));
        sump.position.y = 2.5;
        group.add(sump);

        // Transparent Stack
        const bodyHeight = height - 5;
        const body = new THREE.Mesh(
            new THREE.CylinderGeometry(r, r, bodyHeight, 32),
            builder.getHoloMat(0x444444)
        );
        body.position.y = 5 + bodyHeight / 2;
        group.add(body);

        // Wireframe Overlay
        const wire = new THREE.Mesh(
            new THREE.CylinderGeometry(r * 1.01, r * 1.01, bodyHeight, 16),
            builder.getWireframeMat(COLORS.ammonia)
        );
        wire.position.y = 5 + bodyHeight / 2;
        group.add(wire);

        addLabel(group, name, height + 4);
        group.userData = { name: name, type: 'FILTRATION', desc: 'Atmospheric cleansing module. Operating at 98% efficiency.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createFan: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Housing (Holographic Box)
        const housing = new THREE.Mesh(
            new THREE.BoxGeometry(4, 4, 2),
            builder.getHoloMat(COLORS.darkSteel)
        );
        housing.position.y = 2;
        group.add(housing);

        // Wireframe cage
        const cage = new THREE.Mesh(
            new THREE.BoxGeometry(4.2, 4.2, 2.2),
            builder.getWireframeMat(COLORS.ammonia)
        );
        cage.position.y = 2;
        group.add(cage);

        // Motor (Neon Cylinder)
        const motor = new THREE.Mesh(
            new THREE.CylinderGeometry(1.5, 1.5, 3),
            new THREE.MeshBasicMaterial({ color: COLORS.highlight, wireframe: true })
        );
        motor.rotation.z = Math.PI / 2;
        motor.position.set(3, 2, 0);

        // Spinning animation hook could be added here if we tracked it
        group.add(motor);

        addLabel(group, 'SYSTEM FAN', 6);
        group.userData = { name: 'SYSTEM FAN', type: 'AIR HANDLER', desc: 'Main exhaust propulsion. RPM: 1200.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createJacketedTank: (name, radius, height, pos, color) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Inner vessel (main tank)
        const innerGeo = new THREE.CylinderGeometry(radius * 0.9, radius * 0.9, height, 32);
        const innerMat = builder.getHoloMat(COLORS.steel);
        const inner = new THREE.Mesh(innerGeo, innerMat);
        inner.position.y = height / 2;
        group.add(inner);

        // Outer jacket (transparent shell)
        const jacketGeo = new THREE.CylinderGeometry(radius, radius, height * 0.8, 32);
        const jacketMat = new THREE.MeshPhysicalMaterial({
            color: color,
            metalness: 0.2,
            roughness: 0.3,
            transmission: 0.7,
            opacity: 0.4,
            transparent: true,
            emissive: color,
            emissiveIntensity: 0.15
        });
        const jacket = new THREE.Mesh(jacketGeo, jacketMat);
        jacket.position.y = height / 2;
        group.add(jacket);

        // Heat exchange coil (helix)
        const coilCurve = new THREE.CatmullRomCurve3([
            new THREE.Vector3(0, 2, 0),
            new THREE.Vector3(radius * 0.7, height * 0.3, 0),
            new THREE.Vector3(-radius * 0.7, height * 0.5, 0),
            new THREE.Vector3(radius * 0.7, height * 0.7, 0),
            new THREE.Vector3(0, height - 2, 0)
        ]);
        const coilGeo = new THREE.TubeGeometry(coilCurve, 20, 0.15, 8, false);
        const coilMat = new THREE.MeshBasicMaterial({ color: COLORS.acid });
        const coil = new THREE.Mesh(coilGeo, coilMat);
        group.add(coil);

        // Neon accent rings
        const ringGeo = new THREE.TorusGeometry(radius + 0.1, 0.05, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: color });
        const topRing = new THREE.Mesh(ringGeo, ringMat);
        topRing.rotation.x = Math.PI / 2;
        topRing.position.y = height;
        group.add(topRing);

        addLabel(group, name, height + 4);
        group.userData = { name: name, type: 'JACKETED REACTOR', desc: 'Temperature-controlled reaction vessel with heating jacket.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createEvaporatorDryer: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        const width = 8, height = 12, depth = 8;

        // Main housing (box structure)
        const housingGeo = new THREE.BoxGeometry(width, height, depth);
        const housingMat = builder.getHoloMat(COLORS.darkSteel);
        const housing = new THREE.Mesh(housingGeo, housingMat);
        housing.position.y = height / 2;
        group.add(housing);

        // Internal grid structure (visible through transparent housing)
        const gridMat = new THREE.MeshBasicMaterial({
            color: COLORS.yellow,
            wireframe: true,
            transparent: true,
            opacity: 0.6
        });

        // Create grid pattern (horizontal and vertical plates)
        for (let i = 1; i < 4; i++) {
            const plate = new THREE.Mesh(
                new THREE.BoxGeometry(width * 0.8, 0.1, depth * 0.8),
                gridMat
            );
            plate.position.y = (height / 4) * i;
            group.add(plate);
        }

        // Vertical heat elements (glowing)
        for (let x = -2; x <= 2; x += 2) {
            for (let z = -2; z <= 2; z += 2) {
                const element = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.2, 0.2, height * 0.7, 8),
                    new THREE.MeshStandardMaterial({
                        color: COLORS.yellow,
                        emissive: COLORS.yellow,
                        emissiveIntensity: 0.5
                    })
                );
                element.position.set(x, height / 2, z);
                group.add(element);
            }
        }

        // Inlet/outlet ports
        const portGeo = new THREE.CylinderGeometry(0.8, 0.8, 2, 16);
        const portMat = new THREE.MeshBasicMaterial({ color: COLORS.slurry });

        // Top inlet
        const topPort = new THREE.Mesh(portGeo, portMat);
        topPort.position.set(0, height + 1, 0);
        group.add(topPort);

        // Bottom outlet
        const bottomPort = new THREE.Mesh(portGeo, portMat);
        bottomPort.position.set(0, -1, 0);
        group.add(bottomPort);

        // Wireframe cage
        const cage = new THREE.Mesh(
            new THREE.BoxGeometry(width + 0.4, height + 0.4, depth + 0.4),
            builder.getWireframeMat(COLORS.highlight)
        );
        cage.position.y = height / 2;
        group.add(cage);

        addLabel(group, 'EVAPORATOR/DRYER', height + 5);
        group.userData = { name: 'EVAPORATOR/DRYER', type: 'DRYING UNIT', desc: 'Multi-stage evaporation and drying system. Heat source: steam/electric.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createHorizontalTank: (name, radius, length, pos, color) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Main horizontal cylinder
        const cylinderGeo = new THREE.CylinderGeometry(radius, radius, length, 32);
        const cylinderMat = builder.getHoloMat(COLORS.steel);
        const cylinder = new THREE.Mesh(cylinderGeo, cylinderMat);
        cylinder.rotation.z = Math.PI / 2;
        cylinder.position.y = radius + 1;
        group.add(cylinder);

        // Support saddles
        const saddleGeo = new THREE.BoxGeometry(1, 1.5, radius * 1.5);
        const saddleMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });

        const saddle1 = new THREE.Mesh(saddleGeo, saddleMat);
        saddle1.position.set(-length / 3, radius / 2, 0);
        group.add(saddle1);

        const saddle2 = new THREE.Mesh(saddleGeo, saddleMat);
        saddle2.position.set(length / 3, radius / 2, 0);
        group.add(saddle2);

        // Neon accent bands
        const bandGeo = new THREE.TorusGeometry(radius + 0.1, 0.04, 16, 100);
        const bandMat = new THREE.MeshBasicMaterial({ color: color });

        for (let x of [-length / 3, 0, length / 3]) {
            const band = new THREE.Mesh(bandGeo, bandMat);
            band.position.set(x, radius + 1, 0);
            group.add(band);
        }

        // Nozzles (inlets/outlets)
        const nozzleGeo = new THREE.CylinderGeometry(0.3, 0.3, 1, 8);
        const nozzleMat = new THREE.MeshBasicMaterial({ color: color });

        const nozzleTop = new THREE.Mesh(nozzleGeo, nozzleMat);
        nozzleTop.position.set(0, radius * 2 + 1.5, 0);
        group.add(nozzleTop);

        addLabel(group, name, radius * 2 + 4);
        group.userData = { name: name, type: 'STORAGE TANK', desc: 'Horizontal storage vessel for liquids and slurries.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createStabilizer: (name, pos, height) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const r = 2.5;

        // Main vessel
        const bodyGeo = new THREE.CylinderGeometry(r, r, height, 32);
        const bodyMat = builder.getHoloMat(COLORS.steel);
        const body = new THREE.Mesh(bodyGeo, bodyMat);
        body.position.y = height / 2;
        group.add(body);

        // Internal baffles (visible through transparent wall)
        const baffleGeo = new THREE.PlaneGeometry(r * 1.8, 0.1);
        const baffleMat = new THREE.MeshBasicMaterial({
            color: COLORS.slurry,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.5
        });

        for (let i = 1; i < 4; i++) {
            const baffle = new THREE.Mesh(baffleGeo, baffleMat);
            baffle.position.y = (height / 4) * i;
            baffle.rotation.y = (Math.PI / 4) * i;
            group.add(baffle);
        }

        // Neon rings
        const ringGeo = new THREE.TorusGeometry(r + 0.1, 0.05, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: COLORS.slurry });

        const topRing = new THREE.Mesh(ringGeo, ringMat);
        topRing.rotation.x = Math.PI / 2;
        topRing.position.y = height;
        group.add(topRing);

        const bottomRing = new THREE.Mesh(ringGeo, ringMat);
        bottomRing.rotation.x = Math.PI / 2;
        bottomRing.position.y = 0;
        group.add(bottomRing);

        addLabel(group, name, height + 4);
        group.userData = { name: name, type: 'STABILIZATION UNIT', desc: 'Product stabilization and conditioning vessel.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },
    createGranulator: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        const radius = 5;
        const length = 15;

        // Main Drum (Rotating)
        const drumGeo = new THREE.CylinderGeometry(radius, radius, length, 32);
        const drumMat = builder.getHoloMat(COLORS.steel);
        const drum = new THREE.Mesh(drumGeo, drumMat);
        drum.rotation.z = Math.PI / 2;
        drum.position.y = radius + 2;
        group.add(drum);

        // Internal lifting flights (visible)
        const flightsGeo = new THREE.BoxGeometry(length, 1, radius * 1.8);
        const flightsMat = new THREE.MeshBasicMaterial({ color: COLORS.slurry, wireframe: true, transparent: true, opacity: 0.3 });
        const flights1 = new THREE.Mesh(flightsGeo, flightsMat);
        flights1.position.y = radius + 2;
        group.add(flights1);

        const flights2 = new THREE.Mesh(flightsGeo, flightsMat);
        flights2.rotation.x = Math.PI / 2;
        flights2.position.y = radius + 2;
        group.add(flights2);

        // Drive Mechanism
        const driveGeo = new THREE.BoxGeometry(4, 4, 4);
        const driveMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const drive = new THREE.Mesh(driveGeo, driveMat);
        drive.position.set(-length / 2 - 2, 2, 0);
        group.add(drive);

        // Neon Rings
        const ringGeo = new THREE.TorusGeometry(radius + 0.2, 0.1, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: COLORS.ammonia });

        const r1 = new THREE.Mesh(ringGeo, ringMat);
        r1.rotation.y = Math.PI / 2;
        r1.position.set(-length / 3, radius + 2, 0);
        group.add(r1);

        const r2 = r1.clone();
        r2.position.set(length / 3, radius + 2, 0);
        group.add(r2);

        addLabel(group, 'GRANULATOR', radius * 2 + 5);
        group.userData = { name: 'GRANULATOR', type: 'GRANULATION', desc: 'Converts slurry into solid granules. Central unit.' };
        interactables.push(group);
        scene.add(group);
        return group;
    }
};

function addLabel(parent, text, yOffset) {
    const div = document.createElement('div');
    div.className = 'label';
    div.textContent = text;
    const label = new CSS2DObject(div);
    // Increased offset for better spacing
    label.position.set(0, yOffset + 3, 0);
    parent.add(label);
}

function createInputMarker(text, position, color) {
    const div = document.createElement('div');
    div.className = 'input-label';
    div.style.color = '#' + color.getHexString();
    div.style.borderColor = '#' + color.getHexString();

    // Icon + Text
    div.innerHTML = `INPUT: ${text}`;

    const label = new CSS2DObject(div);
    label.position.copy(position);
    scene.add(label);
    interactables.push(label); // Allow potential interaction
    return label;
}

// --- PLANT LAYOUT ---
function buildPlant() {
    // ==================================================================================
    // QUADRANT 2 (NW) - REACTION & WET END
    // Coordinates: X < 0, Z > 0
    // ==================================================================================

    // 1. Pre-Neutralizer (Main Reactor)
    // Positioned deep in NW quadrant
    const PreNeut = builder.createTank('PRE-NEUT', 6, 14, new THREE.Vector3(-100, 0, 100), COLORS.ammonia, true);
    registerObject(PreNeut, 2);

    // 2a. Pipe Reactor 1 (Main)
    // Suspended above/near Pre-Neut
    const PipeReactor1 = builder.createPipeReactor(new THREE.Vector3(-60, 45, 80));
    registerObject(PipeReactor1, 2);

    // 2b. Sulphuric Acid Pipe Reactor
    const PipeReactor2 = builder.createPipeReactor(new THREE.Vector3(-60, 55, 80));
    registerObject(PipeReactor2, 2);

    // 3. PR Tank (Process Receiver)
    const PRTank = builder.createTank('PR TANK', 2.5, 5, new THREE.Vector3(-140, 0, 130), COLORS.slurry, true);
    registerObject(PRTank, 2);

    // 4. Defoamer Tank
    const DefoamerTank = builder.createTank('DEFOAMER', 1.5, 3, new THREE.Vector3(-100, 0, 150), COLORS.acid, false);
    registerObject(DefoamerTank, 2);


    // ==================================================================================
    // QUADRANT 1 (NE) - GRANULATION & DRYING
    // Coordinates: X > 0, Z > 0
    // ==================================================================================

    // 6. Granulator
    const Granulator = builder.createGranulator(new THREE.Vector3(60, 0, 80));
    registerObject(Granulator, 3);

    // 14. Rotary Dryer
    const RotaryDryer = builder.createEvaporatorDryer(new THREE.Vector3(140, 0, 80));
    registerObject(RotaryDryer, 4);


    // ==================================================================================
    // QUADRANT 3 (SW) - RECYCLE & TANKS
    // Coordinates: X < 0, Z < 0
    // ==================================================================================

    // 5. Pre-Scrubber Tank
    const PreScrubberTank = builder.createTank('PRE-SCRUB TANK', 3, 6, new THREE.Vector3(-20, 0, -50), COLORS.yellow, true);
    registerObject(PreScrubberTank, 2);

    // 13. Scrubber Tank
    const ScrubberTank = builder.createHorizontalTank('SCRUBBER TANK', 2.5, 10, new THREE.Vector3(-50, 0, -50), COLORS.yellow);
    registerObject(ScrubberTank, 5);


    // ==================================================================================
    // QUADRANT 4 (SE) - GAS TREATMENT (SCRUBBERS)
    // Coordinates: X > 0, Z < 0
    // ==================================================================================

    // 9. Fumes Pre-Scrubber
    const FumesPre = builder.createScrubber('FUMES PRE', new THREE.Vector3(50, 0, -60), 16);
    registerObject(FumesPre, 5);

    // 10. Fumes Scrubber
    const FumesScrub = builder.createScrubber('FUMES SCRUB', new THREE.Vector3(90, 0, -60), 18);
    registerObject(FumesScrub, 5);

    // 11. Dedusting & Cooling Scrubber
    const DedustScrub = builder.createScrubber('DEDUST & COOL', new THREE.Vector3(130, 0, -60), 20);
    registerObject(DedustScrub, 5);

    // 12. Dryer Scrubber
    const DryerScrub = builder.createScrubber('DRYER SCRUB', new THREE.Vector3(170, 0, -60), 20);
    registerObject(DryerScrub, 5);

    // 13. Tail Gas Absorber
    const TailGas = builder.createScrubber('TAIL GAS', new THREE.Vector3(210, 0, -90), 32, true);
    registerObject(TailGas, 5);

    // 14. System Fan
    const Fan = builder.createFan(new THREE.Vector3(190, 35, -80));
    registerObject(Fan, 5);


    // ===================================================================
    // --- INPUT STREAMS (External feeds to process) ---
    // ===================================================================

    // I1: LIQUID AMMONIA (Direct to Pipe Reactor 1 in NW)
    const ammLiqStart = new THREE.Vector3(-200, 18, 80);
    registerObject(createInputMarker('LIQUID NH3', ammLiqStart, new THREE.Color(COLORS.ammonia)), 1);
    registerObject(createPipe([
        ammLiqStart,
        new THREE.Vector3(-100, 18, 80),
        new THREE.Vector3(-60, 40, 80) // To Pipe Reactor 1
    ], COLORS.ammonia), 1);

    // I2: GASEOUS AMMONIA (To Pre-Neut in NW)
    const ammGasStart = new THREE.Vector3(-200, 25, 100);
    registerObject(createInputMarker('GASEOUS NH3', ammGasStart, new THREE.Color(COLORS.gas)), 1);
    registerObject(createPipe([
        ammGasStart,
        new THREE.Vector3(-120, 25, 100),
        new THREE.Vector3(-100, 16, 100) // To Pre-Neut
    ], COLORS.gas), 1);

    // I3: PHOSPHORIC ACID (Direct to Pre-Neut in NW)
    const acidStart = new THREE.Vector3(-200, 10, 120);
    registerObject(createInputMarker('H3PO4 ACID', acidStart, new THREE.Color(COLORS.acid)), 1);
    registerObject(createPipe([
        acidStart,
        new THREE.Vector3(-100, 10, 120),
        new THREE.Vector3(-100, 12, 100) // To Pre-Neut
    ], COLORS.acid), 1);

    // I4: SULFURIC ACID (To Pipe Reactor 2 in NW)
    const sulfuricStart = new THREE.Vector3(-200, 55, 60);
    registerObject(createInputMarker('H2SO4 FEED', sulfuricStart, new THREE.Color(COLORS.acid)), 1);
    registerObject(createPipe([
        sulfuricStart,
        new THREE.Vector3(-80, 55, 60),
        new THREE.Vector3(-60, 55, 80) // To Pipe Reactor 2
    ], COLORS.acid), 1);

    // I5: UPFLOW/RECYCLE (To Granulator in NE)
    const upflowStart = new THREE.Vector3(0, 5, 150);
    registerObject(createInputMarker('RAW MAT/RECYCLE', upflowStart, new THREE.Color(COLORS.slurry)), 1);
    registerObject(createPipe([
        upflowStart,
        new THREE.Vector3(60, 5, 150),
        new THREE.Vector3(60, 5, 85) // To Granulator
    ], COLORS.slurry), 1);

    // I6: MP STEAM (To Rotary Dryer in NE)
    const steamStart = new THREE.Vector3(200, 35, 150);
    registerObject(createInputMarker('MP STEAM', steamStart, new THREE.Color(COLORS.steam)), 1);
    registerObject(createPipe([
        steamStart,
        new THREE.Vector3(140, 35, 150),
        new THREE.Vector3(140, 15, 85) // To Dryer
    ], COLORS.steam), 1);


    // ===================================================================
    // --- INTERNAL FLOWS (Process connections) ---
    // ===================================================================

    // F3: Pre-Neutralizer (NW) → Granulator (NE)
    registerObject(createPipe([
        new THREE.Vector3(-100, 10, 100),
        new THREE.Vector3(0, 10, 100),
        new THREE.Vector3(40, 10, 80),
        new THREE.Vector3(55, 5, 80)  // To Granulator
    ], COLORS.slurry), 3);

    // F4: Pipe Reactors (NW) → Granulator (NE)
    registerObject(createPipe([
        new THREE.Vector3(-60, 45, 80), // From Pipe 1
        new THREE.Vector3(0, 45, 80),
        new THREE.Vector3(55, 15, 80)   // To Granulator
    ], COLORS.slurry), 3);

    // F5: Granulator (NE) → Rotary Dryer (NE)
    registerObject(createPipe([
        new THREE.Vector3(65, 5, 80),   // From Granulator
        new THREE.Vector3(100, 5, 80),
        new THREE.Vector3(135, 5, 80)    // To Dryer
    ], COLORS.slurry), 4);


    // F7: Defoamer (NW) → Pre-Neut (NW)
    registerObject(createPipe([
        new THREE.Vector3(-100, 4, 150),
        new THREE.Vector3(-100, 14, 105)
    ], COLORS.acid), 2);

    // F8: Scrubber Recycle (SW) → Pre-Scrubber (SE)
    // Connecting Tanks in Q3 to Scrubbers in Q4
    registerObject(createPipe([
        new THREE.Vector3(-50, 2, -50), // Scrubber Tank
        new THREE.Vector3(0, 2, -50),
        new THREE.Vector3(50, 5, -60) // To Pre-Scrubber
    ], COLORS.yellow), 5);

    registerObject(createPipe([
        new THREE.Vector3(-20, 2, -50),  // Pre-Scrubber Tank
        new THREE.Vector3(40, 8, -50),
        new THREE.Vector3(50, 8, -60)  // To Pre-Scrubber
    ], COLORS.yellow), 5);


    // ===================================================================
    // --- GAS FLOWS (Fume treatment system) ---
    // ===================================================================

    // G1: Reactor/Granulator Fumes → Pre-Scrubber (SE)
    // PreNeut (NW) -> PreScrubber (SE) - Long crossover overhead
    registerObject(createPipe([
        new THREE.Vector3(-100, 15, 100), // Pre-Neut Fumes
        new THREE.Vector3(-100, 60, 100),
        new THREE.Vector3(50, 60, -60),   // Diagonal cross
        new THREE.Vector3(50, 18, -60)
    ], COLORS.gas), 5);

    // Granulator (NE) -> PreScrubber (SE)
    registerObject(createPipe([
        new THREE.Vector3(60, 10, 80),  // Granulator Fumes
        new THREE.Vector3(60, 40, 80),
        new THREE.Vector3(60, 40, -60),
        new THREE.Vector3(50, 18, -60)
    ], COLORS.gas), 5);

    // G2: Scrubber Train (SE) - Linear connection
    registerObject(createPipe([
        new THREE.Vector3(50, 12, -60), // Pre
        new THREE.Vector3(90, 12, -60)  // To FumesScrub
    ], COLORS.gas), 5);

    registerObject(createPipe([
        new THREE.Vector3(90, 14, -60), // FumesScrub
        new THREE.Vector3(130, 14, -60) // To Dedust
    ], COLORS.gas), 5);

    registerObject(createPipe([
        new THREE.Vector3(130, 16, -60), // Dedust
        new THREE.Vector3(170, 16, -60)  // To DryerScrub
    ], COLORS.gas), 5);

    // G3: Dryer Off-Gas (NE) → Dryer Scrubber (SE)
    registerObject(createPipe([
        new THREE.Vector3(140, 12, 80), // From Dryer
        new THREE.Vector3(140, 30, 80),
        new THREE.Vector3(170, 30, -60), // Cross to SE
        new THREE.Vector3(170, 18, -60) // To Dryer Scrubber
    ], COLORS.steam), 5);

    // G4: Dryer Scrubber → Fan → Tail Gas (SE)
    registerObject(createPipe([
        new THREE.Vector3(170, 18, -60),
        new THREE.Vector3(190, 35, -80) // To Fan
    ], COLORS.gas), 5);

    registerObject(createPipe([
        new THREE.Vector3(190, 35, -80), // Fan
        new THREE.Vector3(210, 20, -90)  // To Tail Gas
    ], COLORS.gas), 5);


    // ===================================================================
    // --- OUTPUT STREAMS (Final products and emissions) ---
    // ===================================================================

    // O2: Dried Product (NE)
    registerObject(createInputMarker('DRIED PRODUCT', new THREE.Vector3(180, 12, 80), new THREE.Color(COLORS.yellow)), 6);
    registerObject(createPipe([
        new THREE.Vector3(145, 5, 80), // From Dryer
        new THREE.Vector3(180, 5, 80)
    ], COLORS.yellow), 6);

    // O3: Tail Gas to Stack (SE)
    registerObject(createInputMarker('STACK FM1', new THREE.Vector3(210, 55, -90), new THREE.Color(COLORS.steam)), 6);
    registerObject(createPipe([
        new THREE.Vector3(210, 32, -90), // Top of TailGas
        new THREE.Vector3(210, 55, -90)
    ], COLORS.steam), 6);

}

function createPipe(points, color) {
    const group = new THREE.Group();
    const curve = new THREE.CatmullRomCurve3(points);

    // Simple pipe
    const geometry = new THREE.TubeGeometry(curve, 64, 0.35, 8, false);
    const material = new THREE.MeshPhysicalMaterial({
        color: color,
        transparent: true,
        opacity: 0.8,
        roughness: 0.1,
        transmission: 0.5,
        thickness: 0.5
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    group.add(mesh);

    const particles = createFlowParticles(curve, color);
    group.add(particles);

    scene.add(group);
    return group;
}

function createFlowParticles(curve, color) {
    const particleCount = 60; // Simple, clean particle count
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(particleCount * 3);
    const offsets = [];

    for (let i = 0; i < particleCount; i++) {
        offsets.push(Math.random());
        pos[i * 3] = 0; pos[i * 3 + 1] = 0; pos[i * 3 + 2] = 0;
    }

    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));

    // Flow particles (elegant glowing dots)
    const mat = new THREE.PointsMaterial({
        color: color,
        size: 3.5,
        transparent: true,
        opacity: 0.8,
        map: createCircleTexture(color),
        alphaTest: 0.1,
        depthWrite: false
    });
    const particles = new THREE.Points(geo, mat);
    // scene.add(particles); // Added to group in createPipe instead

    flowParticles.push({
        mesh: particles,
        curve: curve,
        offsets: offsets,
        speed: 0.005
    });

    return particles;
}



function createCircleTexture(color) {
    const size = 64;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');

    // Draw a sharp glowing circle
    const center = size / 2;
    ctx.beginPath();
    ctx.arc(center, center, center - 4, 0, 2 * Math.PI, false);
    ctx.fillStyle = '#' + new THREE.Color(color).getHexString();
    ctx.fill();

    const texture = new THREE.CanvasTexture(canvas);
    return texture;
}

// --- INTERACTION ---
function setupInteraction() {
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    window.addEventListener('click', onClick);
    // document.addEventListener('mousemove', onMouseMove); // Optional hover effect
}

function onClick(event) {
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(scene.children, true);

    if (hits.length > 0) {
        let target = hits[0].object;
        while (target.parent && !interactables.includes(target)) target = target.parent;
        if (interactables.includes(target)) showInfo(target.userData);
    }
}

function showInfo(data) {
    const panel = document.getElementById('info-panel');
    document.getElementById('panel-title').textContent = data.name;
    document.getElementById('panel-subtitle').textContent = data.type;
    document.getElementById('panel-content').textContent = data.desc;
    panel.classList.add('visible');
}

window.toggleFlow = () => {
    isFlowActive = !isFlowActive;
    flowParticles.forEach(fp => fp.mesh.visible = isFlowActive);
    document.getElementById('btn-flow').classList.toggle('active');
};

window.toggleLabels = () => {
    labelVisible = !labelVisible;
    labelRenderer.domElement.style.display = labelVisible ? 'block' : 'none';
    document.getElementById('btn-labels').classList.toggle('active');
};

window.toggleOrbit = () => {
    if (controls) {
        controls.autoRotate = !controls.autoRotate;
        document.getElementById('btn-orbit').classList.toggle('active');
    }
};

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    labelRenderer.setSize(window.innerWidth, window.innerHeight);
    if (composer) composer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);

    const delta = clock.getDelta();
    const time = clock.getElapsedTime();

    // 1. Rotate Orbital Ring
    if (orbitalRing) {
        orbitalRing.rotation.z += 0.001; // Very slow rotation
    }

    // 2. Pulse Reactor Core
    if (reactorCore) {
        reactorCore.material.uniforms.time.value = time;
    }

    // 3. Animate Dust Particles
    if (dustParticles) {
        dustParticles.rotation.y = time * 0.02;
    }

    // 4. Animate Floor
    if (scene.userData.planeMaterial) {
        scene.userData.planeMaterial.uniforms.time.value = time;
    }

    // 5. Subtle grid pulse
    if (scene.userData.accentGrid) {
        scene.userData.accentGrid.material.opacity = 0.3 + 0.2 * Math.sin(time * 0.5);
    }

    controls.update();

    if (isFlowActive) {
        // Simple, clean flow animation
        flowParticles.forEach(fp => {
            const positions = fp.mesh.geometry.attributes.position.array;

            for (let i = 0; i < fp.offsets.length; i++) {
                fp.offsets[i] += fp.speed;
                if (fp.offsets[i] > 1) fp.offsets[i] -= 1;
                const pt = fp.curve.getPoint(fp.offsets[i]);
                positions[i * 3] = pt.x; positions[i * 3 + 1] = pt.y; positions[i * 3 + 2] = pt.z;
            }
            fp.mesh.geometry.attributes.position.needsUpdate = true;
        });
    }

    composer.render();
    labelRenderer.render(scene, camera);
}

window.animate = animate; // Expose for debugging

// --- STEP-BY-STEP LOGIC ---
window.setMode = (mode) => {
    const btnComplete = document.getElementById('btn-complete');
    const btnStep = document.getElementById('btn-step');
    const btnNext = document.getElementById('btn-next-step');
    const title = document.querySelector('.title');

    if (mode === 'complete') {
        btnComplete.classList.add('active');
        btnStep.classList.remove('active');
        btnNext.style.display = 'none';

        // Show everything
        stepRegistry.forEach(item => {
            if (item.object) item.object.visible = true;
        });

        title.textContent = "LIQUID SECTION";
        currentStep = MAX_STEPS;

    } else if (mode === 'step') {
        btnComplete.classList.remove('active');
        btnStep.classList.add('active');
        btnNext.style.display = 'inline-block'; // Show next button

        // Force Labels ON for guided view
        if (!labelVisible) {
            toggleLabels();
        }

        // Start at Step 1
        currentStep = 1;
        updateStepView();
    }
};

window.nextStep = () => {
    if (currentStep < MAX_STEPS) {
        currentStep++;
        updateStepView();
    } else {
        // Optional: Loop back or shake button
        const btnNext = document.getElementById('btn-next-step');
        btnNext.style.transform = "translateX(5px)";
        setTimeout(() => btnNext.style.transform = "translateX(0)", 100);
    }
};

function updateStepView() {
    stepRegistry.forEach(item => {
        if (!item.object) return;

        const isVisible = item.step <= currentStep;
        item.object.visible = isVisible;

        // Force CSS2DObject children to match visibility (safeguard)
        item.object.traverse(child => {
            if (child.isCSS2DObject) {
                child.visible = isVisible;
            }
        });
    });

    const stepDescriptions = [
        "INITIALIZING...",
        "STEP 1: INPUT FEEDS & RAW MATERIALS",
        "STEP 2: REACTION & PRE-TREATMENT",
        "STEP 3: GRANULATION PROCESS",
        "STEP 4: DRYING Process",
        "STEP 5: GAS TREATMENT & SCRUBBING",
        "STEP 6: PRODUCT OUTPUT"
    ];

    const title = document.querySelector('.title');
    if (title) {
        title.textContent = stepDescriptions[currentStep] || `STEP ${currentStep}`;
        // Blink effect
        title.style.opacity = 0.5;
        setTimeout(() => title.style.opacity = 1, 200);
    }
}

function registerObject(object, step) {
    if (!object) return;
    stepRegistry.push({ object, step });
    // Default visibility depends on current mode, but init is complete mode
    object.visible = true;
}

init();
