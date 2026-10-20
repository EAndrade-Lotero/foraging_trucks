// Cave look for the foraging board: a stone floor in the dark and a torch around your
// pac-man. The lit area is the square of cells you can see (VIEW_RADIUS), with soft
// rounded edges, so what looks lit is exactly where points can appear.
(function () {
    // Deterministic noise so the floor looks the same for both players and every round.
    function rng(seed) {
        return function () {
            seed = (seed * 1664525 + 1013904223) % 4294967296;
            return seed / 4294967296;
        };
    }

    function floorTexture(gridSize) {
        var px = 48;                    // pixels per cell
        var border = 0.5;               // rock wall around the board, in cells
        var cells = gridSize + 2 * border;
        var canvas = document.createElement("canvas");
        canvas.width = canvas.height = Math.round(cells * px);
        var ctx = canvas.getContext("2d");
        var rand = rng(12345);

        ctx.fillStyle = "#3b2f25";      // rock wall
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        for (var b = 0; b < cells * 6; b++) {
            ctx.fillStyle = rand() < 0.5 ? "#4a3b2e" : "#2c231b";
            ctx.beginPath();
            ctx.arc(rand() * canvas.width, rand() * canvas.height, px * (0.12 + rand() * 0.22), 0, 2 * Math.PI);
            ctx.fill();
        }

        var o = border * px;
        for (var x = 0; x < gridSize; x++) {
            for (var y = 0; y < gridSize; y++) {
                var x0 = o + x * px, y0 = o + y * px;
                var shade = 150 + Math.floor(rand() * 22);
                ctx.fillStyle = "rgb(" + shade + "," + Math.floor(shade * 0.84) + "," + Math.floor(shade * 0.66) + ")";
                ctx.fillRect(x0, y0, px, px);
                // Bevel: light top-left edge, dark bottom-right edge, so each cell reads as a tile.
                ctx.fillStyle = "rgba(255,240,210,0.18)";
                ctx.fillRect(x0, y0, px, 2);
                ctx.fillRect(x0, y0, 2, px);
                ctx.fillStyle = "rgba(40,25,10,0.35)";
                ctx.fillRect(x0, y0 + px - 3, px, 3);
                ctx.fillRect(x0 + px - 3, y0, 3, px);
                for (var s = 0; s < 7; s++) {
                    ctx.fillStyle = rand() < 0.5 ? "rgba(70,45,20,0.22)" : "rgba(255,235,200,0.16)";
                    ctx.fillRect(x0 + 4 + rand() * (px - 10), y0 + 4 + rand() * (px - 10), 2, 2);
                }
                if (rand() < 0.12) {        // a small crack now and then
                    ctx.strokeStyle = "rgba(60,38,18,0.35)";
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    var cx = x0 + 8 + rand() * (px - 16), cy = y0 + 8 + rand() * (px - 16);
                    ctx.moveTo(cx, cy);
                    ctx.lineTo(cx + (rand() - 0.5) * 18, cy + (rand() - 0.5) * 18);
                    ctx.lineTo(cx + (rand() - 0.5) * 22, cy + (rand() - 0.5) * 22);
                    ctx.stroke();
                }
            }
        }
        var texture = new THREE.CanvasTexture(canvas);
        if ("colorSpace" in texture) texture.colorSpace = THREE.SRGBColorSpace;
        texture.anisotropy = 4;
        return { texture: texture, size: cells };
    }

    var DARK_SHADER = {
        vertex: [
            "varying vec2 vWorld;",
            "void main() {",
            "  vec4 w = modelMatrix * vec4(position, 1.0);",
            "  vWorld = w.xy;",
            "  gl_Position = projectionMatrix * viewMatrix * w;",
            "}",
        ].join("\n"),
        fragment: [
            "uniform vec2 uLight;",
            "uniform float uTime;",
            "uniform float uHalf;",
            "uniform float uShape;",
            "uniform float uDark;",
            "varying vec2 vWorld;",
            "float roundBox(vec2 p, vec2 b, float r) {",
            "  vec2 q = abs(p) - b + r;",
            "  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;",
            "}",
            "void main() {",
            "  vec2 p = vWorld - uLight;",
            "  float flicker = 1.0 + 0.025 * sin(uTime * 7.3) + 0.018 * sin(uTime * 13.7 + 1.7);",
            "  float d;",
            "  if (uShape < 0.5) {",
            "    d = length(p) - (uHalf + 0.05) * flicker;",                    // round torch
            "  } else if (uShape < 1.5) {",
            "    d = roundBox(p, vec2(uHalf) * flicker, 0.55);",                // square of visible cells
            "  } else {",
            "    vec2 q = floor(p * 6.0 + 0.5) / 6.0;",                       // pixel-art circle
            "    d = length(q) - (uHalf + 0.1);",
            "  }",
            "  float lit = uShape > 1.5 ? step(d, 0.0) : 1.0 - smoothstep(-0.12, 0.22, d);",
            "  float glow = exp(-dot(p, p) / (uHalf * uHalf * 2.2));",
            "  vec3 warm = vec3(1.0, 0.62, 0.22);",
            "  float a = mix(uDark, 0.22 * (1.0 - glow), lit);",                  // edges of the lit area a bit dimmer
            "  vec3 c = mix(vec3(0.02, 0.012, 0.0), warm * 0.25, lit);",
            "  gl_FragColor = vec4(c, a);",
            "}",
        ].join("\n"),
    };

    // A warm additive halo on top of the darkness: the torch glow.
    var GLOW_SHADER = {
        fragment: [
            "uniform vec2 uLight;",
            "uniform float uTime;",
            "uniform float uHalf;",
            "varying vec2 vWorld;",
            "void main() {",
            "  vec2 p = vWorld - uLight;",
            "  float flicker = 1.0 + 0.05 * sin(uTime * 9.1) + 0.03 * sin(uTime * 17.3 + 0.4);",
            "  float g = exp(-dot(p, p) / (uHalf * uHalf * 2.6)) * 0.17 * flicker;",
            "  gl_FragColor = vec4(vec3(1.0, 0.58, 0.18) * g, 1.0);",
            "}",
        ].join("\n"),
    };

    // Builds the floor, the darkness and the glow inside `group`. Returns an object whose
    // setLight(x, y) moves the torch (world units) and tick(time) animates it.
    function build(group, gridSize, viewRadius, options) {
        options = options || {};
        var floor = floorTexture(gridSize);
        var floorMesh = new THREE.Mesh(
            new THREE.PlaneGeometry(floor.size, floor.size),
            new THREE.MeshBasicMaterial({ map: floor.texture })
        );
        group.add(floorMesh);

        var uniforms = {
            uLight: { value: new THREE.Vector2(0, 0) },
            uTime: { value: 0 },
            uHalf: { value: viewRadius + 0.5 },
            uShape: { value: options.shape === undefined ? 1 : options.shape },
            uDark: { value: options.dark === undefined ? 0.84 : options.dark },
        };
        var cover = gridSize + 4;
        var dark = new THREE.Mesh(
            new THREE.PlaneGeometry(cover, cover),
            new THREE.ShaderMaterial({
                uniforms: uniforms, vertexShader: DARK_SHADER.vertex,
                fragmentShader: DARK_SHADER.fragment, transparent: true, depthWrite: false,
            })
        );
        dark.position.z = 0.06;
        group.add(dark);

        var glow = new THREE.Mesh(
            new THREE.PlaneGeometry(cover, cover),
            new THREE.ShaderMaterial({
                uniforms: uniforms, vertexShader: DARK_SHADER.vertex,
                fragmentShader: GLOW_SHADER.fragment, transparent: true, depthWrite: false,
                blending: THREE.AdditiveBlending,
            })
        );
        glow.position.z = 0.065;
        group.add(glow);

        return {
            setLight: function (x, y) { uniforms.uLight.value.set(x, y); },
            hideLight: function () { uniforms.uLight.value.set(1e4, 1e4); },
            tick: function (t) { uniforms.uTime.value = t; },
        };
    }

    // Pac-man with an eye, facing where it last moved. Angle in radians (0 = right).
    function pacman(color, isSelf, connected, angle) {
        var g = new THREE.Group();
        var body = new THREE.Group();
        var mat = new THREE.MeshBasicMaterial({
            color: connected ? new THREE.Color(color) : new THREE.Color(0x777777),
            side: THREE.DoubleSide,
        });
        var shadow = new THREE.Mesh(
            new THREE.CircleGeometry(0.36, 32),
            new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 })
        );
        shadow.position.set(0.04, -0.05, -0.01);
        g.add(shadow);
        body.add(new THREE.Mesh(new THREE.CircleGeometry(0.34, 32, 0.15 * Math.PI, 1.7 * Math.PI), mat));
        var eye = new THREE.Mesh(
            new THREE.CircleGeometry(0.055, 16),
            new THREE.MeshBasicMaterial({ color: 0x1a1a1a })
        );
        eye.position.set(0.04, 0.17, 0.001);
        body.add(eye);
        body.rotation.z = angle || 0;
        // Keep the eye on top when facing left.
        if (Math.cos(angle || 0) < -0.5) body.scale.y = -1;
        g.add(body);
        if (isSelf) {
            g.add(new THREE.Mesh(
                new THREE.RingGeometry(0.38, 0.45, 40),
                new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide })
            ));
        }
        return g;
    }

    // A point: a small pixel-art gem (10x10 sprite, dark outline, highlight and shade),
    // drawn with nearest-neighbour filtering so the pixels stay crisp.
    var GEM = [
        "...OOOO...",
        "..OLLBBO..",
        ".OLWBBBBO.",
        "OLWBBBBBDO",
        "OLBBBBBBDO",
        "OBBBBBBBDO",
        "OBBBBBBDDO",
        ".OBBBBDDO.",
        "..ODDDDO..",
        "...OOOO...",
    ];
    // Sapphire: keeps the blue of the original points, readable on the lit stone and for
    // red-green colour blindness (blue against tan).
    var PALETTE = { O: "#0d1036", L: "#8fb4ff", W: "#ffffff", B: "#2a50f0", D: "#17289a" };
    var gemTexture = null;
    // Used food (already eaten): the same gem in greys, so it reads as "used", not as food.
    var USED_PALETTE = { O: "#2b2b2b", L: "#d8d8d8", W: "#f2f2f2", B: "#8e8e8e", D: "#5c5c5c" };
    var usedTexture = null;
    function pointTexture(used) {
        if (used ? usedTexture : gemTexture) return used ? usedTexture : gemTexture;
        var palette = used ? USED_PALETTE : PALETTE;
        var canvas = document.createElement("canvas");
        canvas.width = canvas.height = GEM.length;
        var ctx = canvas.getContext("2d");
        GEM.forEach(function (row, y) {
            row.split("").forEach(function (c, x) {
                if (c === ".") return;
                ctx.fillStyle = palette[c];
                ctx.fillRect(x, y, 1, 1);
            });
        });
        var texture = new THREE.CanvasTexture(canvas);
        texture.magFilter = THREE.NearestFilter;
        texture.minFilter = THREE.NearestFilter;
        texture.generateMipmaps = false;
        if ("colorSpace" in texture) texture.colorSpace = THREE.SRGBColorSpace;
        if (used) usedTexture = texture; else gemTexture = texture;
        return texture;
    }

    function point(used) {
        return new THREE.Mesh(
            new THREE.PlaneGeometry(0.5, 0.5),
            new THREE.MeshBasicMaterial({ map: pointTexture(used), transparent: true })
        );
    }

    // The same gem as inline SVG, for the food bank next to the board.
    function gemSVG() {
        var rects = "";
        GEM.forEach(function (row, y) {
            row.split("").forEach(function (c, x) {
                if (PALETTE[c]) rects += '<rect x="' + x + '" y="' + y + '" width="1.02" height="1.02" fill="' + PALETTE[c] + '"/>';
            });
        });
        return '<svg viewBox="0 0 10 10" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">' + rects + "</svg>";
    }

    window.CaveView = { build: build, pacman: pacman, point: point, gemSVG: gemSVG };
})();
