function createEarth(scene) {

    const EARTH_X    = 0.0;
    const R          = 3.05;
    const SUN_DIR    = new THREE.Vector3(6, 2.2, 5).normalize();

    // Earth root group
    const earthGroup = new THREE.Group();
    earthGroup.name  = 'EarthRoot';
    earthGroup.position.set(0, -0.2, 0);
    scene.add(earthGroup);

    // Textures
    const loader = new THREE.TextureLoader();
    const TEX    = 'https://threejs.org/examples/textures/planets/';

    function tex(name, srgb) {
        const t = loader.load(
            TEX + name,
            undefined,
            undefined,
            () => { console.warn('[EarthScape] Texture fallback applied for:', name); }
        );
        if (srgb && t) t.encoding = THREE.sRGBEncoding;
        return t;
    }

    const dayMap   = tex('earth_atmos_2048.jpg',   true);
    const nightMap = tex('earth_lights_2048.png',  true);
    const specMap  = tex('earth_specular_2048.jpg', false);
    const cloudMap = tex('earth_clouds_1024.png',  false);

    // Earth Shader Uniforms
    const earthUniforms = {
        dayTexture:      { value: dayMap   },
        nightTexture:    { value: nightMap },
        specularTexture: { value: specMap  },
        sunDirection:    { value: SUN_DIR  },
        revealMix:       { value: 1.0 },
        nightFade:       { value: 0.1 }
    };

    // Planet Body Shader
    const earthMesh = new THREE.Mesh(
        new THREE.SphereGeometry(R, 64, 64),
        new THREE.ShaderMaterial({
            uniforms: earthUniforms,
            vertexShader: `
                varying vec3 vNormal;
                varying vec2 vUv;
                varying vec3 vWorldPosition;
                void main(){
                    vNormal = normalize(normalMatrix * normal);
                    vUv = uv;
                    vec4 wp = modelMatrix * vec4(position, 1.0);
                    vWorldPosition = wp.xyz;
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                precision highp float;
                uniform sampler2D dayTexture;
                uniform sampler2D nightTexture;
                uniform sampler2D specularTexture;
                uniform vec3  sunDirection;
                uniform float revealMix;
                uniform float nightFade;
                varying vec3 vNormal;
                varying vec2 vUv;
                varying vec3 vWorldPosition;
                void main(){
                    vec3 n       = normalize(vNormal);
                    float lam    = dot(n, normalize(sunDirection));
                    float loEdge = mix(-0.28,  0.05, nightFade);
                    float hiEdge = mix( 0.32,  0.02, nightFade);
                    float mix01  = smoothstep(loEdge, hiEdge, lam);
                    vec3 day     = texture2D(dayTexture,   vUv).rgb;
                    vec3 night   = texture2D(nightTexture, vUv).rgb;
                    float spec   = texture2D(specularTexture, vUv).r;
                    vec3 viewDir = normalize(cameraPosition - vWorldPosition);
                    vec3 refl    = reflect(-normalize(sunDirection), n);
                    float sa     = pow(max(dot(viewDir, refl), 0.0), 26.0) * spec * clamp(lam, 0.0, 1.0);
                    vec3 litDay  = day * (0.35 + 0.95 * clamp(lam, 0.0, 1.0)) + vec3(1.0, 0.97, 0.9) * sa * 0.65;
                    vec3 nightGl = night * 1.4 * (1.0 - nightFade * 0.85);
                    vec3 color   = mix(nightGl, litDay, mix01);
                    color       += vec3(0.02, 0.05, 0.09) * (1.0 - mix01);
                    color       *= revealMix;
                    gl_FragColor = vec4(color, 1.0);
                }
            `
        })
    );
    earthMesh.name = 'PlanetBody';
    earthGroup.add(earthMesh);

    // Cloud Layer
    const cloudMesh = new THREE.Mesh(
        new THREE.SphereGeometry(R * 1.008, 64, 64),
        new THREE.MeshBasicMaterial({
            map: cloudMap, transparent: true, opacity: 0.4,
            depthWrite: false, blending: THREE.NormalBlending
        })
    );
    cloudMesh.name = 'CloudLayer';
    earthGroup.add(cloudMesh);

    // Atmosphere Rim Glow
    const atmosphereMat = new THREE.ShaderMaterial({
        uniforms: { sunDirection: { value: SUN_DIR } },
        vertexShader: `
            varying vec3 vNormal;
            varying vec3 vWorldPos;
            void main(){
                vNormal   = normalize(normalMatrix * normal);
                vWorldPos = (modelMatrix * vec4(position,1.0)).xyz;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
            }
        `,
        fragmentShader: `
            precision highp float;
            uniform vec3 sunDirection;
            varying vec3 vNormal;
            varying vec3 vWorldPos;
            void main(){
                vec3 view  = normalize(cameraPosition - vWorldPos);
                vec3 n     = normalize(vNormal);
                float rim  = 1.0 - abs(dot(view, n));
                float glow = pow(rim, 12.0);
                float sun  = clamp(dot(n, normalize(sunDirection)) * 0.35 + 0.72, 0.0, 1.0);
                vec3 col   = mix(vec3(0.12, 0.28, 0.55), vec3(0.55, 0.78, 1.0), sun);
                gl_FragColor = vec4(col, glow * 0.18);
            }
        `,
        side: THREE.FrontSide,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending
    });
    const atmosphereMesh = new THREE.Mesh(
        new THREE.SphereGeometry(R * 1.02, 128, 128),
        atmosphereMat
    );
    atmosphereMesh.name = 'AtmosphereRim';
    earthGroup.add(atmosphereMesh);

    // Lighting
    const sunLight = new THREE.DirectionalLight(0xfff1de, 1.5);
    sunLight.position.copy(SUN_DIR).multiplyScalar(40);
    scene.add(sunLight);

    const ambient = new THREE.AmbientLight(0x1a2638, 0.5);
    scene.add(ambient);

    // Starfield Background
    const starCount = 3000;
    const starPos = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
        const r = 150 + Math.random() * 300;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        starPos[i*3]   = r * Math.sin(phi) * Math.cos(theta);
        starPos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
        starPos[i*3+2] = r * Math.cos(phi);
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    const starMat = new THREE.PointsMaterial({
        color: 0xffffff,
        size: 1.2,
        transparent: true,
        opacity: 0.7
    });
    const starField = new THREE.Points(starGeo, starMat);
    scene.add(starField);

    // Satellite Constellation Dots
    const SC = 80;
    const sPos = new Float32Array(SC * 3);
    for (let i = 0; i < SC; i++) {
        const r = R * 1.15;
        const t = Math.random() * Math.PI * 2;
        const p = Math.acos(2 * Math.random() - 1);
        sPos[i*3]   = r * Math.sin(p) * Math.cos(t);
        sPos[i*3+1] = r * Math.sin(p) * Math.sin(t);
        sPos[i*3+2] = r * Math.cos(p);
    }
    const satGeo = new THREE.BufferGeometry();
    satGeo.setAttribute('position', new THREE.BufferAttribute(sPos, 3));
    const satMat = new THREE.PointsMaterial({
        color: 0xa3e635,
        size: 0.04,
        transparent: true,
        opacity: 0.8
    });
    const satPoints = new THREE.Points(satGeo, satMat);
    earthGroup.add(satPoints);

    // =========================================================
    // HIGH-DETAIL REALISTIC SATELLITE PROCEDURAL MODEL
    // =========================================================
    const satelliteGroup = new THREE.Group();
    satelliteGroup.name = 'SatelliteRoot';

    // 1. Shared High-Metallic PBR Materials
    const goldFoilMat = new THREE.MeshStandardMaterial({
        color: 0xd4af37,        // Gold / Multi-Layer Insulation Foil
        metalness: 0.95,
        roughness: 0.25
    });

    const polishedMetalMat = new THREE.MeshStandardMaterial({
        color: 0xe2e8f0,        // Silver Chrome / Anodized Aluminum
        metalness: 0.9,
        roughness: 0.15
    });

    const darkMetalMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,        // Dark Titanium framing
        metalness: 0.8,
        roughness: 0.4
    });

    const solarCellMat = new THREE.MeshStandardMaterial({
        color: 0x07192f,        // Deep Photovoltaic Blue
        metalness: 0.85,
        roughness: 0.1,
        emissive: 0x0284c7,
        emissiveIntensity: 0.15
    });

    // 2. Central Satellite Body (Octagonal Metallic Bus)
    const busMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.5, 8), goldFoilMat);
    busMesh.rotation.x = Math.PI / 2;
    satelliteGroup.add(busMesh);

    // Aluminum end caps on satellite bus
    const capGeo = new THREE.CylinderGeometry(0.225, 0.225, 0.02, 8);
    const capFront = new THREE.Mesh(capGeo, polishedMetalMat);
    capFront.position.z = 0.25;
    capFront.rotation.x = Math.PI / 2;
    satelliteGroup.add(capFront);

    const capBack = new THREE.Mesh(capGeo, polishedMetalMat);
    capBack.position.z = -0.25;
    capBack.rotation.x = Math.PI / 2;
    satelliteGroup.add(capBack);

    // 3. Solar Panel Wings Assembly
    const solarWingsGroup = new THREE.Group();
    solarWingsGroup.name = 'SolarWingsGroup';

    // Panel structural mounts (Connecting rods extending from body)
    const mountGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.6);
    const mountMesh = new THREE.Mesh(mountGeo, polishedMetalMat);
    mountMesh.rotation.z = Math.PI / 2;
    solarWingsGroup.add(mountMesh);

    // Solar Panel Arrays (Left and Right)
    const createSolarWing = (xDirection) => {
        const wingGroup = new THREE.Group();
        
        // Dark Backing Frame
        const frame = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.015, 0.45), darkMetalMat);
        wingGroup.add(frame);

        // Blue Photovoltaic Grid Layer (Slight offset to sit on frame)
        const cells = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.02, 0.43), solarCellMat);
        cells.position.y = 0.005;
        wingGroup.add(cells);

        // Grid Separators (Metallic panel lines across solar cells)
        for (let i = -0.4; i <= 0.4; i += 0.2) {
            const seam = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.025, 0.43), polishedMetalMat);
            seam.position.set(i, 0.006, 0);
            wingGroup.add(seam);
        }

        wingGroup.position.x = xDirection * 0.85;
        return wingGroup;
    };

    solarWingsGroup.add(createSolarWing(1));   // Right Wing
    solarWingsGroup.add(createSolarWing(-1));  // Left Wing
    satelliteGroup.add(solarWingsGroup);

    // 4. Parabolic High-Gain Dish Antenna
    const dishGroup = new THREE.Group();
    const dishReflector = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.02, 0.08, 32, 1, true),
        polishedMetalMat
    );
    dishGroup.add(dishReflector);

    // Sub-reflector feed horn
    const feedHorn = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.18), polishedMetalMat);
    feedHorn.position.y = -0.05;
    dishGroup.add(feedHorn);

    const feedTip = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.05, 12), goldFoilMat);
    feedTip.position.y = -0.12;
    feedTip.rotation.x = Math.PI;
    dishGroup.add(feedTip);

    dishGroup.rotation.x = Math.PI / 2.5;
    dishGroup.position.set(0, 0.28, 0.15);
    satelliteGroup.add(dishGroup);

    // 5. Sensors & Thruster Nozzles
    const thrusterGeo = new THREE.ConeGeometry(0.04, 0.08, 12, 1, true);
    const thruster = new THREE.Mesh(thrusterGeo, darkMetalMat);
    thruster.rotation.x = -Math.PI / 2;
    thruster.position.set(0, 0, -0.28);
    satelliteGroup.add(thruster);

    // Magnetometer Probe Boom
    const boomMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.6), polishedMetalMat);
    boomMesh.position.set(0, -0.28, 0);
    satelliteGroup.add(boomMesh);

    // Force Satellite meshes to always render OVER Earth/Atmosphere
    satelliteGroup.traverse((child) => {
        if (child.isMesh) {
            child.material.depthTest = false;
            child.material.depthWrite = false;
            child.renderOrder = 999;
        }
    });

    // Initial scale and position (attached directly to scene)
    satelliteGroup.scale.set(0.4, 0.4, 0.4);
    satelliteGroup.position.set(5.5, 3.0, 2.0);
    scene.add(satelliteGroup);

    // Export properties to scene object
    scene.earthGroup       = earthGroup;
    scene.earthMesh        = earthMesh;
    scene.cloudMesh        = cloudMesh;
    scene.atmosphereMesh   = atmosphereMesh;
    scene.satPoints        = satPoints;
    scene.satelliteGroup   = satelliteGroup;
    scene.solarWingsGroup  = solarWingsGroup;

    return scene;
}