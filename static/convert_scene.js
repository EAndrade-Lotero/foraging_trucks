// Convert scene: points (food) in your bank turn into moves for this round, live with the
// invest slider (Andrade's sketch, 13-oct: "Food -> Movimientos"). Same look as the board:
// pixel-art sapphire gems on a dark panel. Each gem you invest becomes its row of arrows.
//
//   var scene = ConvertScene(document.getElementById("box"), {bank: 6, perPoint: 6});
//   scene.set(2, true);   // invest 2 points, animated
(function () {
    var GEM = ["...OOOO...", "..OLLBBO..", ".OLWBBBBO.", "OLWBBBBBDO", "OLBBBBBBDO",
               "OBBBBBBBDO", "OBBBBBBDDO", ".OBBBBDDO.", "..ODDDDO..", "...OOOO..."];
    var GEM_COLORS = { O: "#0d1036", L: "#8fb4ff", W: "#ffffff", B: "#2a50f0", D: "#17289a" };
    var ARROW = ["...OO...", "...OGO..", "OOOOGGO.", "OGGGGLGO", "OGGGGGGO", "OOOOGGO.",
                 "...OGO..", "...OO..."];
    var ARROW_COLORS = { O: "#0b2a17", G: "#2fbf62", L: "#a6f5c0" };

    function sprite(rows, colors) {
        var rects = "";
        rows.forEach(function (row, y) {
            row.split("").forEach(function (c, x) {
                if (colors[c]) rects += '<rect x="' + x + '" y="' + y + '" width="1.02" height="1.02" fill="' + colors[c] + '"/>';
            });
        });
        return '<svg viewBox="0 0 ' + rows[0].length + " " + rows.length
            + '" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">' + rects + "</svg>";
    }

    var CSS = `
    .convert-scene { position: relative; background: #0b0b0b; border-radius: 12px; padding: 14px;
        display: grid; grid-template-columns: 1fr auto 1.7fr; gap: 12px; align-items: stretch;
        user-select: none; margin: 0.5rem 0 0.4rem; color: #fff; }
    .convert-scene .cv-box { background: #1b1b1b; border-radius: 10px; padding: 8px 10px;
        display: flex; flex-direction: column; }
    .convert-scene .cv-title { font-size: 0.78rem; color: #bbb; font-weight: 600; margin-bottom: 6px; }
    .convert-scene .cv-points { flex: 1; display: flex; flex-wrap: wrap; align-content: flex-start; gap: 6px; }
    .convert-scene .cv-moves { flex: 1; display: flex; flex-direction: column; gap: 0.32em; }
    .convert-scene .cv-gem { width: 1.75em; height: 1.75em; transition: opacity 0.2s; }
    .convert-scene .cv-gem.empty { opacity: 0.12; }
    .convert-scene .cv-row { display: flex; align-items: center; gap: 0.25em; height: 1.15em; }
    .convert-scene .cv-mini { width: 1.15em; height: 1.15em; margin-right: 2px; }
    .convert-scene .cv-eq { color: #888; font-size: 0.8rem; margin: 0 3px; }
    .convert-scene .cv-arrow { width: 1.15em; height: 1.15em; transform: scale(0); transition: transform 0.25s cubic-bezier(.3,1.6,.5,1); }
    .convert-scene .cv-arrow.in { transform: scale(1); }
    .convert-scene .cv-plus { color: #2fbf62; font-weight: 700; font-size: 0.8rem; margin-left: 6px;
        opacity: 0; transition: opacity 0.3s; }
    .convert-scene .cv-plus.in { opacity: 1; }
    .convert-scene .cv-count { font-size: 1.5rem; font-weight: 700; line-height: 1; margin-top: 8px;
        font-variant-numeric: tabular-nums; transition: transform 0.2s; }
    .convert-scene .cv-count small { font-size: 0.7rem; font-weight: 500; color: #bbb; margin-left: 4px; }
    .convert-scene .cv-count.bump { transform: scale(1.15); }
    .convert-scene .cv-flow { align-self: center; width: 1.9em; opacity: 0.8; }
    .convert-scene .cv-fly { position: absolute; width: 1.75em; height: 1.75em; pointer-events: none; z-index: 2;
        transition: transform 0.45s cubic-bezier(.4,.1,.3,1); }
    `;

    function ConvertScene(root, opts) {
        if (!document.getElementById("convert-scene-css")) {
            var style = document.createElement("style");
            style.id = "convert-scene-css";
            style.textContent = CSS;
            document.head.appendChild(style);
        }
        var bank = opts.bank || 6, perPoint = opts.perPoint || 6;
        root.innerHTML = '<div class="convert-scene">'
            + '<div class="cv-box"><div class="cv-title">Your bank: points (food)</div><div class="cv-points"></div>'
            + '<div class="cv-count cv-pcount"></div></div>'
            + '<div class="cv-flow">' + sprite(ARROW, { O: "#333", G: "#777", L: "#999" }) + "</div>"
            + '<div class="cv-box"><div class="cv-title">Moves for this round</div><div class="cv-moves"></div>'
            + '<div class="cv-count cv-mcount"></div></div></div>';
        var scene = root.querySelector(".convert-scene");
        var pointsBox = root.querySelector(".cv-points"), movesBox = root.querySelector(".cv-moves");
        var pCount = root.querySelector(".cv-pcount"), mCount = root.querySelector(".cv-mcount");
        movesBox.style.minHeight = (bank * 1.47) + "em";
        for (var i = 0; i < bank; i++) {
            pointsBox.insertAdjacentHTML("beforeend", '<div class="cv-gem">' + sprite(GEM, GEM_COLORS) + "</div>");
        }
        var gems = pointsBox.querySelectorAll(".cv-gem");
        var invested = 0;

        function counter(el, n, unit) {
            var text = n + "<small>" + unit + (n === 1 ? "" : "s") + "</small>";
            if (el.innerHTML === text) return;
            el.innerHTML = text;
            el.classList.add("bump");
            setTimeout(function () { el.classList.remove("bump"); }, 200);
        }

        function addRow(animate) {
            var row = document.createElement("div");
            row.className = "cv-row";
            row.innerHTML = '<div class="cv-mini">' + sprite(GEM, GEM_COLORS) + '</div><span class="cv-eq">&rarr;</span>';
            movesBox.appendChild(row);
            for (var k = 0; k < perPoint; k++) {
                var a = document.createElement("div");
                a.className = "cv-arrow";
                a.innerHTML = sprite(ARROW, ARROW_COLORS);
                row.appendChild(a);
                (function (a, k) {
                    if (animate) setTimeout(function () { a.classList.add("in"); }, 60 + k * 45);
                    else a.classList.add("in");
                })(a, k);
            }
            var plus = document.createElement("span");
            plus.className = "cv-plus";
            plus.textContent = "+" + perPoint;
            row.appendChild(plus);
            if (animate) setTimeout(function () { plus.classList.add("in"); }, 60 + perPoint * 45);
            else plus.classList.add("in");
        }

        // A gem flies from the bank to the start of its row (or back).
        function fly(fromEl, toEl) {
            var s = scene.getBoundingClientRect(), f = fromEl.getBoundingClientRect(), t = toEl.getBoundingClientRect();
            var g = document.createElement("div");
            g.className = "cv-fly";
            g.innerHTML = sprite(GEM, GEM_COLORS);
            g.style.left = (f.left - s.left) + "px";
            g.style.top = (f.top - s.top) + "px";
            scene.appendChild(g);
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    g.style.transform = "translate(" + (t.left - f.left - 5) + "px," + (t.top - f.top - 5) + "px) scale(0.65)";
                });
            });
            setTimeout(function () { g.remove(); }, 480);
        }

        function set(n, animate) {
            n = Math.max(0, Math.min(bank, Math.round(n)));
            while (invested < n) {
                var gem = gems[bank - 1 - invested];
                gem.classList.add("empty");
                addRow(animate);
                if (animate) fly(gem, movesBox.lastChild.firstChild);
                invested += 1;
            }
            while (invested > n) {
                var row = movesBox.lastChild;
                var back = gems[bank - invested];
                if (animate) fly(row.firstChild, back);
                row.remove();
                (function (back) {
                    setTimeout(function () { back.classList.remove("empty"); }, animate ? 450 : 0);
                })(back);
                invested -= 1;
            }
            counter(pCount, bank - n, " point");
            counter(mCount, n * perPoint, " move");
        }

        set(0, false);
        return { set: set };
    }

    window.ConvertScene = ConvertScene;
})();
