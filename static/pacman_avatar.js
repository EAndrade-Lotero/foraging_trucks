// Avatars: a pac-man with a colour, a hat and eyes (avatar.py holds the same lists).
// One drawing, in SVG, serves the pages (PacAvatar.svg) and the board (PacAvatar.mesh, as
// textures). On the board the pac-man turns with its direction; hats always stay upright.
(function () {
    // Okabe-Ito, with white for black and a lighter blue (see avatar.py).
    var COLORS = {
        yellow: "#F0E442", orange: "#E69F00", red: "#D55E00", sky: "#56B4E9",
        blue: "#3D7FE0", green: "#009E73", pink: "#CC79A7", white: "#F2F2F2",
    };
    var BODIES = ["pacman"];
    var HATS = ["none", "cap", "top_hat", "crown", "party", "beanie", "cowboy", "viking", "bow"];
    var EYES = ["dot", "happy", "wink", "cool", "hearts"];
    var LABELS = {
        pacman: "Pac-man",
        none: "No hat", cap: "Cap", top_hat: "Top hat", crown: "Crown", party: "Party hat",
        beanie: "Beanie", cowboy: "Cowboy", viking: "Viking", bow: "Bow",
        dot: "Classic", happy: "Happy", wink: "Wink", cool: "Cool", hearts: "Love",
        yellow: "Yellow", orange: "Orange", red: "Red", sky: "Sky blue",
        blue: "Blue", green: "Green", pink: "Pink", white: "White",
    };
    var INK = "#1a1a1a";
    var PUPIL = "#1a3fb0";

    function pick(list, value) { return list.indexOf(value) >= 0 ? value : list[0]; }

    function clean(a) {
        a = a || {};
        return {
            body: pick(BODIES, a.body),
            color: COLORS[a.color] ? a.color : "yellow",
            hat: pick(HATS, a.hat),
            eyes: pick(EYES, a.eyes),
        };
    }

    function hex(a) { return COLORS[clean(a).color]; }

    function random() {
        function any(list) { return list[Math.floor(Math.random() * list.length)]; }
        return { body: any(BODIES), color: any(Object.keys(COLORS)), hat: any(HATS), eyes: any(EYES) };
    }

    // Eyes after emojis: classic dot, happy ^ (😊), wink (😉), sunglasses (😎) and hearts (😍).
    function heart(x, y, r) {
        return '<path d="M' + x + ' ' + (y + r * 0.9) + ' C' + (x - r * 1.5) + ' ' + (y + r * 0.05) + ' '
            + (x - r * 0.9) + ' ' + (y - r * 1.15) + ' ' + x + ' ' + (y - r * 0.35) + ' C' + (x + r * 0.9) + ' '
            + (y - r * 1.15) + ' ' + (x + r * 1.5) + ' ' + (y + r * 0.05) + ' ' + x + ' ' + (y + r * 0.9)
            + ' Z" fill="#e8203f" stroke="#fff" stroke-width="1.6"/>';
    }
    function happy(x, y, r) {
        return '<path d="M' + (x - r) + ' ' + (y + r * 0.45) + ' Q' + x + ' ' + (y - r * 1.1) + ' ' + (x + r) + ' '
            + (y + r * 0.45) + '" fill="none" stroke="' + INK + '" stroke-width="' + (r * 0.55) + '" stroke-linecap="round"/>';
    }
    // A closed eye for the wink: a lid curving down, with a lash at its outer end.
    function shut(x, y, r) {
        return '<path d="M' + (x - r) + ' ' + (y - r * 0.2) + ' Q' + x + ' ' + (y + r * 0.9) + ' ' + (x + r) + ' '
            + (y - r * 0.2) + ' L' + (x + r * 1.35) + ' ' + (y - r * 0.75) + '" fill="none" stroke="' + INK
            + '" stroke-width="' + (r * 0.5) + '" stroke-linecap="round" stroke-linejoin="round"/>';
    }
    function lens(x, y, r) {
        return '<rect x="' + (x - r * 1.25) + '" y="' + (y - r * 0.8) + '" width="' + (r * 2.5) + '" height="'
            + (r * 1.6) + '" rx="' + (r * 0.55) + '" fill="#111"/>'
            + '<path d="M' + (x - r * 0.75) + ' ' + (y - r * 0.3) + ' L' + (x - r * 0.15) + ' ' + (y - r * 0.3)
            + '" stroke="#fff" stroke-width="' + (r * 0.25) + '" stroke-linecap="round" opacity="0.8"/>';
    }

    // The pac-man faces right and fills the circle centred on (50, 50) with radius 34 (top
    // at y = 16, where hats sit), in a 100 x 100 box, seen side on (one eye).
    function pacmanShapes(a, fill) {
        var eyes = {
            dot: '<circle cx="54" cy="32" r="5.5" fill="' + INK + '"/>',
            happy: happy(54, 32, 7),
            wink: shut(54, 31, 7),
            cool: '<path d="M18 31 L44 30" stroke="#111" stroke-width="3"/>' + lens(56, 31, 7.5),
            hearts: heart(55, 31, 7.5),
        };
        return '<path d="M50 50 L80.3 34.6 A34 34 0 1 0 80.3 65.4 Z" fill="' + fill + '"/>' + eyes[a.eyes];
    }

    function bodyShapes(a, fill) {
        return pacmanShapes(a, fill);
    }

    // Hats sit on the top of the head (y = 16) and may rise to y = -30.
    var HAT_SHAPES = {
        none: "",
        cap: '<path d="M29 21 Q30 1 50 1 Q70 1 71 21 Z" fill="#2c3e50"/>'
            + '<path d="M64 16 L91 18 Q94 22 89 23 L64 22 Z" fill="#1b2631"/>'
            + '<circle cx="50" cy="2" r="2.6" fill="#1b2631"/>',
        top_hat: '<rect x="34" y="-16" width="32" height="32" rx="2" fill="#222"/>'
            + '<rect x="34" y="7" width="32" height="5" fill="#c0392b"/>'
            + '<rect x="25" y="14" width="50" height="6" rx="3" fill="#111"/>',
        crown: '<path d="M30 19 L29 -3 L40 8 L50 -10 L60 8 L71 -3 L70 19 Z" fill="#f5c518"'
            + ' stroke="#a67c00" stroke-width="2" stroke-linejoin="round"/>'
            + '<circle cx="50" cy="11" r="3.4" fill="#e74c3c"/>',
        party: '<path d="M36 20 L50 -20 L64 20 Z" fill="#e91e63"/>'
            + '<path d="M41 6 L59 6 M45 -6 L55 -6" stroke="#ffeb3b" stroke-width="3"/>'
            + '<circle cx="50" cy="-22" r="5" fill="#ffeb3b"/>',
        beanie: '<path d="M29 21 Q29 -3 50 -3 Q71 -3 71 21 Z" fill="#2e7d6b"/>'
            + '<rect x="27" y="14" width="46" height="8" rx="3" fill="#1d5246"/>'
            + '<circle cx="50" cy="-6" r="6" fill="#f2f2f2"/>',
        cowboy: '<ellipse cx="50" cy="18" rx="33" ry="5.5" fill="#7a4a1e"/>'
            + '<path d="M35 18 Q33 -8 44 -5 Q50 -1 56 -5 Q67 -8 65 18 Z" fill="#9c6630"/>'
            + '<rect x="35" y="10" width="30" height="4" fill="#4a2c10"/>',
        viking: '<path d="M33 12 Q16 8 17 -14 Q24 2 37 3 Z" fill="#efe6cf" stroke="#9c8f6c" stroke-width="1.5"/>'
            + '<path d="M67 12 Q84 8 83 -14 Q76 2 63 3 Z" fill="#efe6cf" stroke="#9c8f6c" stroke-width="1.5"/>'
            + '<path d="M30 21 Q30 -1 50 -1 Q70 -1 70 21 Z" fill="#8e9aa6"/>'
            + '<rect x="47" y="-1" width="6" height="22" fill="#6b7682"/>'
            + '<rect x="29" y="15" width="42" height="6" rx="2" fill="#6b7682"/>',
        bow: '<path d="M50 11 L30 0 L30 22 Z" fill="#e84393"/>'
            + '<path d="M50 11 L70 0 L70 22 Z" fill="#e84393"/>'
            + '<circle cx="50" cy="11" r="5" fill="#b8236e"/>',
    };

    function bodySVG(a, opts) {
        a = clean(a); opts = opts || {};
        var fill = opts.grey ? "#777777" : COLORS[a.color];
        return '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100">'
            + bodyShapes(a, fill) + "</svg>";
    }

    function hatSVG(hat) {
        if (!HAT_SHAPES[hat]) return "";
        return '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="154" viewBox="0 -30 100 60">'
            + HAT_SHAPES[hat] + "</svg>";
    }

    // The whole avatar for a page. opts.ring marks your own pac-man, as on the board.
    function svg(a, opts) {
        a = clean(a); opts = opts || {};
        var size = opts.size || 64;
        var ring = opts.ring
            ? '<circle cx="50" cy="50" r="44" fill="none" stroke="' + (opts.ringColor || "#333")
              + '" stroke-width="4" stroke-dasharray="' + (opts.dashed ? "6 5" : "none") + '"/>'
            : "";
        return '<svg class="pac-avatar" xmlns="http://www.w3.org/2000/svg" viewBox="0 -30 100 130"'
            + ' width="' + size + '" height="' + Math.round(size * 1.3) + '" aria-hidden="true">'
            + ring + bodyShapes(a, opts.grey ? "#777777" : COLORS[a.color]) + HAT_SHAPES[a.hat] + "</svg>";
    }

    // ---- Board (three.js) ----
    var materials = {};
    function material(svgText) {
        if (materials[svgText]) return materials[svgText];
        var texture = new THREE.TextureLoader().load(
            "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgText)
        );
        if ("colorSpace" in texture) texture.colorSpace = THREE.SRGBColorSpace;
        var mat = new THREE.MeshBasicMaterial({
            map: texture, transparent: true, depthWrite: false, side: THREE.DoubleSide,
        });
        materials[svgText] = mat;
        return mat;
    }

    // Same footprint as CaveView.pacman: the body radius is 0.34 board units.
    function mesh(avatar, isSelf, connected, angle) {
        var a = clean(avatar);
        var g = new THREE.Group();
        var shadow = new THREE.Mesh(
            new THREE.CircleGeometry(0.36, 32),
            new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 })
        );
        shadow.position.set(0.04, -0.05, -0.01);
        g.add(shadow);
        var body = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material(bodySVG(a, { grey: !connected })));
        var facingLeft = Math.cos(angle || 0) < -0.5;
        body.rotation.z = angle || 0;
        // Keep the eyes on top when facing left.
        if (facingLeft) body.scale.y = -1;
        g.add(body);
        var hat = hatSVG(a.hat);
        if (hat) {
            var hatMesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 0.6), material(hat));
            hatMesh.position.set(0, 0.5, 0.01);  // hat box centre (y = 0) is 50 units above the body's
            g.add(hatMesh);
        }
        if (isSelf) {
            var ring = new THREE.Mesh(
                new THREE.RingGeometry(0.4, 0.47, 40),
                new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide })
            );
            ring.position.z = 0.02;
            g.add(ring);
        }
        return g;
    }

    window.PacAvatar = {
        COLORS: COLORS, BODIES: BODIES, HATS: HATS, EYES: EYES, LABELS: LABELS,
        clean: clean, hex: hex, random: random, svg: svg, bodySVG: bodySVG, hatSVG: hatSVG, mesh: mesh,
    };
})();
