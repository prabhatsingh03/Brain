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
    camera.position.set(0, 150, 450); // Adjusted for wider layout

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

    // Improved Camera Controls for manual inspection
    controls.target.set(0, 0, 0);
    controls.minDistance = 50;
    controls.maxDistance = 1500;
    controls.autoRotate = false;

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
    const gridSize = 1600;
    const divisions = 160;

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
        group.userData = { name: name, type: 'STORAGE UNIT', desc: `Standard containment vessel for ${name}.` };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createBin: (name, width, height, pos, color) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Hopper Shape 
        const binGeo = new THREE.BoxGeometry(width, height, width);
        const binMat = builder.getHoloMat(COLORS.steel);
        const bin = new THREE.Mesh(binGeo, binMat);
        bin.position.y = height / 2 + 5;
        group.add(bin);

        // Funnel bottom
        const funnelGeo = new THREE.ConeGeometry(width * 0.7, 5, 4);
        const funnelMat = new THREE.MeshBasicMaterial({ color: color, wireframe: true });
        const funnel = new THREE.Mesh(funnelGeo, funnelMat);
        funnel.rotation.y = Math.PI / 4;
        funnel.position.y = 2.5;
        group.add(funnel);

        addLabel(group, name, height + 8);
        group.userData = { name: name, type: 'RAW MATERIAL BIN', desc: `Storage for ${name}.` };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createDrum: (name, type, length, radius, pos, color) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Main Drum 
        const drumGeo = new THREE.CylinderGeometry(radius, radius, length, 32);
        const drumMat = builder.getHoloMat(COLORS.steel);
        const drum = new THREE.Mesh(drumGeo, drumMat);
        drum.rotation.z = Math.PI / 2;
        drum.position.y = radius + 2;
        group.add(drum);

        // Drive Mechanism
        const driveGeo = new THREE.BoxGeometry(4, 4, 4);
        const driveMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const drive = new THREE.Mesh(driveGeo, driveMat);
        drive.position.set(-length / 2 - 2, 2, 0);
        group.add(drive);

        // Neon Rings
        const ringGeo = new THREE.TorusGeometry(radius + 0.2, 0.1, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: color });

        const r1 = new THREE.Mesh(ringGeo, ringMat);
        r1.rotation.y = Math.PI / 2;
        r1.position.set(-length / 3, radius + 2, 0);
        group.add(r1);
        const r2 = r1.clone();
        r2.position.set(length / 3, radius + 2, 0);
        group.add(r2);

        addLabel(group, name, radius * 2 + 5);
        group.userData = { name: name, type: type, desc: `Process unit: ${name}` };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createScreen: (name, pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);

        // Shaker box
        const boxGeo = new THREE.BoxGeometry(8, 6, 8);
        const boxMat = builder.getHoloMat(COLORS.steel);
        const box = new THREE.Mesh(boxGeo, boxMat);
        box.position.y = 8;
        group.add(box);

        // Legs
        const legGeo = new THREE.CylinderGeometry(0.5, 0.5, 8);
        const legMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        for (let x of [-3, 3]) {
            for (let z of [-3, 3]) {
                const leg = new THREE.Mesh(legGeo, legMat);
                leg.position.set(x, 4, z);
                group.add(leg);
            }
        }

        addLabel(group, name, 13);
        group.userData = { name: name, type: 'SCREENING', desc: 'Separates material by size.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createScrubber: (name, pos, height, hasStack = false) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const r = 3;

        const sump = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 5, 32), new THREE.MeshStandardMaterial({ color: COLORS.slurry, emissive: COLORS.slurry, emissiveIntensity: 0.4 }));
        sump.position.y = 2.5;
        group.add(sump);

        const bodyHeight = height - 5;
        const body = new THREE.Mesh(
            new THREE.CylinderGeometry(r, r, bodyHeight, 32),
            builder.getHoloMat(0x444444)
        );
        body.position.y = 5 + bodyHeight / 2;
        group.add(body);

        const wire = new THREE.Mesh(
            new THREE.CylinderGeometry(r * 1.01, r * 1.01, bodyHeight, 16),
            builder.getWireframeMat(COLORS.ammonia)
        );
        wire.position.y = 5 + bodyHeight / 2;
        group.add(wire);

        addLabel(group, name, height + 4);
        group.userData = { name: name, type: 'FILTRATION', desc: 'Atmospheric cleansing module.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createFan: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const housing = new THREE.Mesh(new THREE.BoxGeometry(4, 4, 2), builder.getHoloMat(COLORS.darkSteel));
        housing.position.y = 2;
        group.add(housing);
        const cage = new THREE.Mesh(new THREE.BoxGeometry(4.2, 4.2, 2.2), builder.getWireframeMat(COLORS.ammonia));
        cage.position.y = 2;
        group.add(cage);
        const motor = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, 3), new THREE.MeshBasicMaterial({ color: COLORS.highlight, wireframe: true }));
        motor.rotation.z = Math.PI / 2;
        motor.position.set(3, 2, 0);
        group.add(motor);
        addLabel(group, 'SYSTEM FAN', 6);
        group.userData = { name: 'SYSTEM FAN', type: 'AIR HANDLER', desc: 'Main exhaust propulsion.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createHorizontalTank: (name, radius, length, pos, color) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const cylinderGeo = new THREE.CylinderGeometry(radius, radius, length, 32);
        const cylinderMat = builder.getHoloMat(COLORS.steel);
        const cylinder = new THREE.Mesh(cylinderGeo, cylinderMat);
        cylinder.rotation.z = Math.PI / 2;
        cylinder.position.y = radius + 1;
        group.add(cylinder);
        // Saddles
        const saddleGeo = new THREE.BoxGeometry(1, 1.5, radius * 1.5);
        const saddleMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const s1 = new THREE.Mesh(saddleGeo, saddleMat); s1.position.set(-length / 3, radius / 2, 0); group.add(s1);
        const s2 = new THREE.Mesh(saddleGeo, saddleMat); s2.position.set(length / 3, radius / 2, 0); group.add(s2);
        // Rings
        const ringGeo = new THREE.TorusGeometry(radius + 0.1, 0.04, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: color });
        for (let x of [-length / 3, 0, length / 3]) {
            const band = new THREE.Mesh(ringGeo, ringMat); band.position.set(x, radius + 1, 0); group.add(band);
        }
        addLabel(group, name, radius * 2 + 4);
        group.userData = { name: name, type: 'STORAGE TANK', desc: 'Horizontal storage vessel.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createGranulator: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const radius = 5;
        const length = 15;
        const drumGeo = new THREE.CylinderGeometry(radius, radius, length, 32);
        const drumMat = builder.getHoloMat(COLORS.steel);
        const drum = new THREE.Mesh(drumGeo, drumMat);
        drum.rotation.z = Math.PI / 2;
        drum.position.y = radius + 2;
        group.add(drum);
        const flightsGeo = new THREE.BoxGeometry(length, 1, radius * 1.8);
        const flightsMat = new THREE.MeshBasicMaterial({ color: COLORS.slurry, wireframe: true, transparent: true, opacity: 0.3 });
        const f1 = new THREE.Mesh(flightsGeo, flightsMat); f1.position.y = radius + 2; group.add(f1);
        const f2 = new THREE.Mesh(flightsGeo, flightsMat); f2.rotation.x = Math.PI / 2; f2.position.y = radius + 2; group.add(f2);
        const driveGeo = new THREE.BoxGeometry(4, 4, 4);
        const driveMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const drive = new THREE.Mesh(driveGeo, driveMat);
        drive.position.set(-length / 2 - 2, 2, 0);
        group.add(drive);
        const ringGeo = new THREE.TorusGeometry(radius + 0.2, 0.1, 16, 100);
        const ringMat = new THREE.MeshBasicMaterial({ color: COLORS.ammonia });
        const r1 = new THREE.Mesh(ringGeo, ringMat); r1.rotation.y = Math.PI / 2; r1.position.set(-length / 3, radius + 2, 0); group.add(r1);
        const r2 = r1.clone(); r2.position.set(length / 3, radius + 2, 0); group.add(r2);
        addLabel(group, 'GRANULATOR', radius * 2 + 5);
        group.userData = { name: 'GRANULATOR', type: 'GRANULATION', desc: 'Converts slurry into solid granules.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createElevator: (name, height, pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const shaftGeo = new THREE.BoxGeometry(4, height, 4);
        const shaftMat = builder.getHoloMat(COLORS.steel);
        const shaft = new THREE.Mesh(shaftGeo, shaftMat);
        shaft.position.y = height / 2;
        group.add(shaft);
        const headGeo = new THREE.BoxGeometry(6, 5, 6);
        const headMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const head = new THREE.Mesh(headGeo, headMat);
        head.position.y = height + 2.5;
        group.add(head);
        const bootGeo = new THREE.BoxGeometry(5, 5, 5);
        const boot = new THREE.Mesh(bootGeo, headMat);
        boot.position.y = 2.5;
        group.add(boot);
        addLabel(group, name, height + 6);
        group.userData = { name: name, type: 'BUCKET ELEVATOR', desc: 'Vertical alignment transport system.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createCyclone: (name, pos, scale = 1) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const cylGeo = new THREE.CylinderGeometry(3 * scale, 3 * scale, 6 * scale, 32);
        const mat = builder.getHoloMat(COLORS.steel);
        const cyl = new THREE.Mesh(cylGeo, mat);
        cyl.position.y = 6 * scale + (3 * scale);
        group.add(cyl);
        const coneGeo = new THREE.ConeGeometry(3 * scale, 6 * scale, 32, 1, true);
        const cone = new THREE.Mesh(coneGeo, mat);
        cone.geometry.rotateX(Math.PI);
        cone.position.y = 3 * scale;
        group.add(cone);
        const pipeGeo = new THREE.CylinderGeometry(0.5 * scale, 0.5 * scale, 12 * scale, 16);
        const pipe = new THREE.Mesh(pipeGeo, new THREE.MeshBasicMaterial({ color: COLORS.darkSteel }));
        pipe.position.y = 6 * scale;
        group.add(pipe);
        addLabel(group, name, 10 * scale);
        group.userData = { name: name, type: 'CYCLONE', desc: 'Gas/Solid separation unit.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createConveyor: (name, length, pos, rotationY = 0, incline = 0) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        group.rotation.y = rotationY;
        group.rotation.z = incline;
        const frameGeo = new THREE.BoxGeometry(length, 1, 3);
        const frameMat = new THREE.MeshStandardMaterial({ color: COLORS.darkSteel });
        const frame = new THREE.Mesh(frameGeo, frameMat);
        frame.position.x = length / 2;
        group.add(frame);
        const beltGeo = new THREE.BoxGeometry(length, 0.2, 2.5);
        const beltMat = new THREE.MeshBasicMaterial({ color: COLORS.concrete });
        const belt = new THREE.Mesh(beltGeo, beltMat);
        belt.position.x = length / 2;
        belt.position.y = 0.6;
        group.add(belt);
        const legGeo = new THREE.CylinderGeometry(0.2, 0.2, 10);
        const legMat = new THREE.MeshBasicMaterial({ color: COLORS.darkSteel });
        const numLegs = Math.max(2, Math.floor(length / 10));
        for (let i = 0; i <= numLegs; i++) {
            const leg = new THREE.Mesh(legGeo, legMat);
            leg.position.x = (i * (length / numLegs));
            leg.position.y = -5;
            group.add(leg);
        }
        addLabel(group, name, 3);
        group.userData = { name: name, type: 'CONVEYOR', desc: 'Material transport belt.' };
        interactables.push(group);
        scene.add(group);
        return group;
    },

    createChillerCluster: (pos) => {
        const group = new THREE.Group();
        group.position.copy(pos);
        const base = new THREE.Mesh(new THREE.BoxGeometry(20, 1, 15), new THREE.MeshStandardMaterial({ color: COLORS.concrete }));
        group.add(base);
        const chillerGeo = new THREE.BoxGeometry(5, 6, 10);
        const chillerMat = builder.getHoloMat(COLORS.ammonia);
        const unit1 = new THREE.Mesh(chillerGeo, chillerMat);
        unit1.position.set(-5, 3.5, 0);
        group.add(unit1);
        const unit2 = new THREE.Mesh(chillerGeo, chillerMat);
        unit2.position.set(5, 3.5, 0);
        group.add(unit2);
        const fanGeo = new THREE.CylinderGeometry(2, 2, 0.5, 16);
        const fanMat = new THREE.MeshBasicMaterial({ color: COLORS.steel });
        const f1 = new THREE.Mesh(fanGeo, fanMat); f1.position.set(-5, 6.5, 0); group.add(f1);
        const f2 = new THREE.Mesh(fanGeo, fanMat); f2.position.set(5, 6.5, 0); group.add(f2);
        addLabel(group, "AMMONIA CHILLER", 9);
        group.userData = { name: "AMMONIA CHILLER", type: "REFRIGERATION", desc: "Cooling system for liquid ammonia feed." };
        interactables.push(group);
        scene.add(group);
        return group;
    }
};

// --- PLANT LAYOUT ---
function buildPlant() {
    // ==================================================================================
    // QUADRANT 1: RAW MATERIALS (Top-Left: -X, -Z)
    // ==================================================================================
    const q1_x = -120;
    const q1_z = -120;

    // 1. Storage Bins (Arranged in a row along X)
    const Bin1 = builder.createBin('POTASH BIN', 8, 12, new THREE.Vector3(q1_x, 20, q1_z), COLORS.yellow);
    const Bin2 = builder.createBin('FILLER BIN', 8, 12, new THREE.Vector3(q1_x + 15, 20, q1_z), COLORS.yellow);
    const Bin3 = builder.createBin('UREA BIN', 8, 12, new THREE.Vector3(q1_x + 30, 20, q1_z), COLORS.yellow);
    const Bin4 = builder.createBin('OFF-SPEC BIN', 8, 12, new THREE.Vector3(q1_x + 45, 20, q1_z), COLORS.yellow);

    // 2. Feed Conveyor (Under bins)
    const RMConveyor = builder.createConveyor('RM FEED CONVEYOR', 60, new THREE.Vector3(q1_x + 22, 13, q1_z));

    // 3. Diverter (End of conveyor)
    const RMDiverter = builder.createTank('RM DIVERTER', 3, 4, new THREE.Vector3(q1_x + 60, 10, q1_z), COLORS.highlight);

    registerObject(Bin1, 1);
    registerObject(Bin2, 1);
    registerObject(Bin3, 1);
    registerObject(Bin4, 1);
    registerObject(RMConveyor, 1);
    registerObject(RMDiverter, 1);


    // ==================================================================================
    // QUADRANT 2: REACTION & GRANULATION (Bottom-Left: -X, +Z)
    // ==================================================================================
    const q2_x = -80;
    const q2_z = 80;

    // 1. Liquid Handling
    const LiquidSection = builder.createTank('LIQUID SECTION', 4, 8, new THREE.Vector3(q2_x - 40, 0, q2_z), COLORS.acid, true);
    const Combustion = builder.createTank('COMBUSTION CHAMBER', 5, 8, new THREE.Vector3(q2_x - 20, 0, q2_z - 20), COLORS.acid);

    // 2. Granulator (The Heart)
    const Granulator = builder.createGranulator(new THREE.Vector3(q2_x + 20, 0, q2_z));

    registerObject(LiquidSection, 2);
    registerObject(Combustion, 2);
    registerObject(Granulator, 2);


    // ==================================================================================
    // QUADRANT 3: DRYING & SCREENING (Top-Right: +X, -Z)
    // ==================================================================================
    const q3_x = 80;
    const q3_z = -80;

    // 1. Rotary Dryer (Aligned along Z axis for flow from Granulator)
    const RotaryDryer = builder.createDrum('ROTARY DRYER', 'DRYING', 50, 8, new THREE.Vector3(q3_x, 5, q3_z + 40), COLORS.steam);
    RotaryDryer.rotation.y = Math.PI / 2; // Rotate to align with Z

    // 2. Dryer Cyclone
    const DryerCyclone = builder.createCyclone('DRYER CYCLONE', new THREE.Vector3(q3_x + 40, 30, q3_z + 40), 1.5);

    // 3. Elevators (Clustered)
    const InputDryerElevator = builder.createElevator('INPUT DRYER ELV', 50, new THREE.Vector3(q3_x + 20, 0, q3_z));
    const RecycleElevator = builder.createElevator('RECYCLE ELV', 60, new THREE.Vector3(q3_x + 40, 0, q3_z));

    // 4. Screens (High up)
    const OScreen1 = builder.createScreen('OS SCREEN 1', new THREE.Vector3(q3_x + 40, 40, q3_z - 20));
    const FScreen1 = builder.createScreen('FINES SCREEN 1', new THREE.Vector3(q3_x + 40, 25, q3_z - 20));

    // 5. Mills
    const Mill1 = builder.createTank('OVERSIZE MILL', 2, 4, new THREE.Vector3(q3_x + 60, 15, q3_z - 20), COLORS.highlight);

    registerObject(RotaryDryer, 2);
    registerObject(DryerCyclone, 2);
    registerObject(InputDryerElevator, 2);
    registerObject(RecycleElevator, 3);
    registerObject(OScreen1, 3);
    registerObject(FScreen1, 3);
    registerObject(Mill1, 3);


    // ==================================================================================
    // QUADRANT 4: FINISHING & PACKAGING (Bottom-Right: +X, +Z)
    // ==================================================================================
    const q4_x = 80;
    const q4_z = 80;

    // 1. Product Handling
    const ProductElevator = builder.createElevator('PRODUCT ELV', 50, new THREE.Vector3(q4_x, 0, q4_z - 40));

    // 2. Polish Screen
    const PolishScreen = builder.createScreen('POLISHING SCREEN', new THREE.Vector3(q4_x + 20, 30, q4_z));

    // 3. Cooler
    const ProdCooler = builder.createDrum('PRODUCT COOLER', 'COOLING', 30, 6, new THREE.Vector3(q4_x + 60, 0, q4_z), COLORS.ammonia);

    // 4. Coater
    const Coater = builder.createDrum('COATER DRUM', 'COATING', 20, 5, new THREE.Vector3(q4_x + 100, 0, q4_z), COLORS.highlight);
    const OilTank = builder.createTank('COATING OIL', 3, 5, new THREE.Vector3(q4_x + 100, 0, q4_z + 20), COLORS.yellow);

    // 5. Final Output
    const FinalConv = builder.createConveyor('TO STORAGE', 30, new THREE.Vector3(q4_x + 140, 0, q4_z));

    // 6. Dedusting System (Shared/Corner)
    const DedustCyclone = builder.createCyclone('DEDUST CYCLONE', new THREE.Vector3(q4_x + 80, 25, q4_z + 40));
    const DedustScrub = builder.createScrubber('DE-DUST SCRUBBER', new THREE.Vector3(q4_x + 100, 0, q4_z + 40), 20, true);
    const DedustSys = builder.createFan(new THREE.Vector3(q4_x + 110, 30, q4_z + 40));

    registerObject(ProductElevator, 4);
    registerObject(PolishScreen, 4);
    registerObject(ProdCooler, 4);
    registerObject(Coater, 4);
    registerObject(OilTank, 4);
    registerObject(FinalConv, 6);
    registerObject(DedustCyclone, 5);
    registerObject(DedustScrub, 5);
    registerObject(DedustSys, 5);


    // ==================================================================================
    // AMMONIA REFRIGERATION (Outlier - Far South)
    // ==================================================================================
    const amm_x = 0;
    const amm_z = 160;

    const Chiller = builder.createChillerCluster(new THREE.Vector3(amm_x, 0, amm_z));
    const LiqAmmTank = builder.createHorizontalTank('LIQUID AMM TANK', 4, 15, new THREE.Vector3(amm_x + 40, 0, amm_z), COLORS.ammonia);

    registerObject(Chiller, 5);
    registerObject(LiqAmmTank, 1);


    // ==================================================================================
    // --- PIPING & FLOWS (CORRECTED PER PFD) ---
    // ==================================================================================

    // 1. Q1 Raw Materials -> Q2 Granulator
    registerObject(createPipe([
        new THREE.Vector3(q1_x + 60, 10, q1_z), // Diverter
        new THREE.Vector3(q1_x + 80, 10, q1_z),
        new THREE.Vector3(q2_x + 10, 10, q2_z) // To Granulator
    ], COLORS.yellow), 1);

    // 2. Q2 Liquid -> Q2 Granulator
    registerObject(createPipe([
        new THREE.Vector3(q2_x - 40, 5, q2_z), // Liquid Section
        new THREE.Vector3(q2_x + 10, 5, q2_z)  // Granulator
    ], COLORS.slurry), 2);

    // 3. Q2 Granulator -> Q3 Dryer
    registerObject(createPipe([
        new THREE.Vector3(q2_x + 30, 0, q2_z), // Granulator Out
        new THREE.Vector3(0, 0, 0), // Center Point
        new THREE.Vector3(q3_x, 5, q3_z + 20) // Dryer In
    ], COLORS.slurry), 2);

    // 4. Q3 Dryer -> Q3 Input Elevator
    registerObject(createPipe([
        new THREE.Vector3(q3_x, 5, q3_z + 65), // Dryer Out
        new THREE.Vector3(q3_x + 20, 0, q3_z + 65),
        new THREE.Vector3(q3_x + 20, 0, q3_z)  // Input ELV Base
    ], COLORS.steam), 2);

    // 5. Q3 Input Elevator -> Screens
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 20, 50, q3_z), // Input ELV Top
        new THREE.Vector3(q3_x + 20, 55, q3_z),
        new THREE.Vector3(q3_x + 40, 55, q3_z - 20), // To Top Screen
        new THREE.Vector3(q3_x + 40, 45, q3_z - 20)
    ], COLORS.slurry), 3);

    // 6. Screens (Oversize) -> Mills
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 40, 40, q3_z - 20), // Screen O/S Out
        new THREE.Vector3(q3_x + 60, 40, q3_z - 20),
        new THREE.Vector3(q3_x + 60, 20, q3_z - 20) // Mill In
    ], COLORS.slurry), 3);

    // 7. Mills -> Recycle Elevator
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 60, 10, q3_z - 20), // Mill Out
        new THREE.Vector3(q3_x + 60, 5, q3_z),
        new THREE.Vector3(q3_x + 40, 5, q3_z) // Recycle ELV Base
    ], COLORS.slurry), 3);

    // 8. Screens (Fines) -> Recycle Elevator
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 40, 20, q3_z - 20), // Screen Fines Out
        new THREE.Vector3(q3_x + 40, 5, q3_z) // Recycle ELV Base
    ], COLORS.slurry), 3);

    // 9. Recycle Elevator -> Granulator (Recycle Return)
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 40, 60, q3_z), // Recycle ELV Top
        new THREE.Vector3(q3_x + 40, 70, q3_z),
        new THREE.Vector3(0, 70, 0), // High overhead return
        new THREE.Vector3(q2_x, 70, q2_z),
        new THREE.Vector3(q2_x + 10, 15, q2_z) // Granulator In
    ], COLORS.slurry), 3);

    // 10. Screens (Product) -> Product Cooler
    registerObject(createPipe([
        new THREE.Vector3(q3_x + 40, 30, q3_z - 20), // Screen Product Out
        new THREE.Vector3(q3_x + 80, 30, q3_z - 20),
        new THREE.Vector3(q4_x + 40, 30, q4_z), // Cross to Q4
        new THREE.Vector3(q4_x + 50, 10, q4_z) // Cooler In
    ], COLORS.ammonia), 4);

    // 11. Product Cooler -> Product Elevator
    registerObject(createPipe([
        new THREE.Vector3(q4_x + 75, 5, q4_z), // Cooler Out
        new THREE.Vector3(q4_x + 80, 5, q4_z),
        new THREE.Vector3(q4_x + 80, 5, q4_z - 30), // Back towards ELV
        new THREE.Vector3(q4_x, 5, q4_z - 40) // Product ELV Base
    ], COLORS.ammonia), 4);

    // 12. Product Elevator -> Polishing Screen
    registerObject(createPipe([
        new THREE.Vector3(q4_x, 50, q4_z - 40), // Product ELV Top
        new THREE.Vector3(q4_x, 55, q4_z - 40),
        new THREE.Vector3(q4_x + 20, 55, q4_z),
        new THREE.Vector3(q4_x + 20, 35, q4_z) // Polish Screen In
    ], COLORS.ammonia), 4);

    // 13. Polishing Screen -> Coater
    registerObject(createPipe([
        new THREE.Vector3(q4_x + 20, 25, q4_z), // Polish Screen Product
        new THREE.Vector3(q4_x + 40, 25, q4_z),
        new THREE.Vector3(q4_x + 90, 10, q4_z) // Coater In
    ], COLORS.ammonia), 4);

    // 14. Polishing Screen (Rejects) -> Recycle Return
    // (Connecting back to the overhead recycle line roughly)
    registerObject(createPipe([
        new THREE.Vector3(q4_x + 20, 25, q4_z),
        new THREE.Vector3(q4_x + 20, 25, q4_z - 20),
        new THREE.Vector3(q3_x + 50, 5, q3_z) // To Recycle ELV Base area
    ], COLORS.slurry), 4);

    // 15. Coater -> Storage
    registerObject(createPipe([
        new THREE.Vector3(q4_x + 110, 5, q4_z), // Coater Out
        new THREE.Vector3(q4_x + 140, 5, q4_z) // Final Conv
    ], COLORS.ammonia), 6);

    // 16. Ammonia Feed
    registerObject(createPipe([
        new THREE.Vector3(amm_x + 40, 5, amm_z), // Tank
        new THREE.Vector3(amm_x, 5, amm_z),      // Chiller
        new THREE.Vector3(q2_x - 40, 5, q2_z)    // To Liquid Section
    ], COLORS.ammonia), 1);

    // 17. Gas Lines
    registerObject(createPipe([
        new THREE.Vector3(q3_x, 10, q3_z + 40), // Dryer Top
        new THREE.Vector3(q3_x + 40, 30, q3_z + 40) // Dryer Cyclone
    ], COLORS.gas), 5);

    registerObject(createPipe([
        new THREE.Vector3(q4_x + 60, 10, q4_z), // Cooler Top
        new THREE.Vector3(q4_x + 80, 25, q4_z + 40) // Dedust Cyclone
    ], COLORS.gas), 5);

}

function addLabel(parent, text, yOffset) {
    const div = document.createElement('div');
    div.className = 'label';
    div.textContent = text;
    const label = new CSS2DObject(div);
    label.position.set(0, yOffset + 3, 0);
    parent.add(label);
}

function createInputMarker(text, position, color) {
    const div = document.createElement('div');
    div.className = 'input-label';
    div.style.color = '#' + color.getHexString();
    div.style.borderColor = '#' + color.getHexString();
    div.innerHTML = `INPUT: ${text}`;
    const label = new CSS2DObject(div);
    label.position.copy(position);
    scene.add(label);
    interactables.push(label);
    return label;
}

function createPipe(points, color) {
    const group = new THREE.Group();
    const curve = new THREE.CatmullRomCurve3(points);
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
    const particleCount = 60;
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(particleCount * 3);
    const offsets = [];
    for (let i = 0; i < particleCount; i++) {
        offsets.push(Math.random());
        pos[i * 3] = 0; pos[i * 3 + 1] = 0; pos[i * 3 + 2] = 0;
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
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

function setupInteraction() {
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    window.addEventListener('click', onClick);
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
    if (orbitalRing) orbitalRing.rotation.z += 0.001;
    if (reactorCore) reactorCore.material.uniforms.time.value = time;
    if (dustParticles) dustParticles.rotation.y = time * 0.02;
    if (scene.userData.planeMaterial) scene.userData.planeMaterial.uniforms.time.value = time;
    if (scene.userData.accentGrid) scene.userData.accentGrid.material.opacity = 0.3 + 0.2 * Math.sin(time * 0.5);
    controls.update();
    if (isFlowActive) {
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
window.animate = animate;

window.setMode = (mode) => {
    const btnComplete = document.getElementById('btn-complete');
    const btnStep = document.getElementById('btn-step');
    const btnNext = document.getElementById('btn-next-step');
    const title = document.querySelector('.title');
    if (mode === 'complete') {
        btnComplete.classList.add('active');
        btnStep.classList.remove('active');
        btnNext.style.display = 'none';
        stepRegistry.forEach(item => {
            if (item.object) item.object.visible = true;
        });
        title.textContent = "SOLID SECTION";
        currentStep = MAX_STEPS;
    } else if (mode === 'step') {
        btnComplete.classList.remove('active');
        btnStep.classList.add('active');
        btnNext.style.display = 'inline-block';
        if (!labelVisible) toggleLabels();
        currentStep = 1;
        updateStepView();
    }
};

window.nextStep = () => {
    if (currentStep < MAX_STEPS) {
        currentStep++;
        updateStepView();
    } else {
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
        item.object.traverse(child => {
            if (child.isCSS2DObject) child.visible = isVisible;
        });
    });
    const stepDescriptions = [
        "INITIALIZING...",
        "STEP 1: RAW MATERIALS",
        "STEP 2: GRANULATION & DRYING",
        "STEP 3: SCREENING & RECYCLE",
        "STEP 4: FINISHING",
        "STEP 5: GAS & AMMONIA SYSTEMS",
        "STEP 6: FINAL PRODUCT"
    ];
    const title = document.querySelector('.title');
    if (title) {
        title.textContent = stepDescriptions[currentStep] || `STEP ${currentStep}`;
        title.style.opacity = 0.5;
        setTimeout(() => title.style.opacity = 1, 200);
    }
}

function registerObject(object, step) {
    if (!object) return;
    stepRegistry.push({ object, step });
    object.visible = true;
}

init();
