// Split scene: two pac-men, each with a row of the points they collected, and the contract
// moving points from one row to the other (slides 11-13, Andrade's ultimatum tabletop).
// Used by the contract tutorial, the round result and the contract proposal, so players see
// the same picture every round. Nobody has to compute anything: the rows and counters do it.
//
//   var scene = SplitScene(document.getElementById("box"), {you: 12, partner: 4});
//   scene.set(0.5, true);        // contract (0 = commission, 1 = wages), animate
//   scene.example(4, 12);        // new collected points
(function () {
    var CSS = `
    .split-scene { position: relative; background: #0b0b0b; border-radius: 12px; overflow: hidden;
        user-select: none; margin: 0.5rem 0 0.4rem; }
    .split-scene .ss-who { position: absolute; left: 10px; width: 62px; display: flex; flex-direction: column;
        align-items: center; gap: 2px; color: #fff; font-size: 0.8rem; font-weight: 600; }
    .split-scene .ss-who svg { width: 34px; height: 34px; }
    .split-scene .ss-lane { position: absolute; left: 80px; right: 86px; height: 46px; border-radius: 10px;
        background: #1b1b1b; }
    .split-scene .ss-count { position: absolute; right: 12px; width: 70px; text-align: right; color: #fff;
        font-size: 1.9rem; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums;
        transition: transform 0.25s; }
    .split-scene .ss-count small { display: block; font-size: 0.68rem; font-weight: 500; color: #bbb; }
    .split-scene .ss-count.bump { transform: scale(1.22); }
    .split-scene .ss-equal { position: absolute; width: 0; height: 30px; border-left: 2px dashed #ffffff66; }
    .split-scene .ss-equal span { position: absolute; top: -15px; left: -24px; width: 48px; text-align: center;
        font-size: 0.62rem; color: #ffffffaa; }
    .split-scene .ss-dot { position: absolute; width: var(--dot, 20px); height: var(--dot, 20px);
        margin: calc(var(--dot, 20px) / -2) 0 0 calc(var(--dot, 20px) / -2); box-sizing: border-box;
        border-radius: 50%; background: #00008a; border: var(--ring, 4px) solid; box-shadow: 0 0 0 2px #0b0b0b;
        transition: left 0.6s cubic-bezier(.3,.7,.3,1), top 0.6s cubic-bezier(.3,.7,.3,1), box-shadow 0.3s; }
    .split-scene .ss-dot.half-keep { clip-path: inset(0 50% 0 0); }
    .split-scene .ss-dot.half-give { clip-path: inset(0 0 0 50%); }
    .split-scene .ss-dot.moved { box-shadow: 0 0 0 2px #0b0b0b, 0 0 12px 3px #ffffffaa; }
    .split-legend { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; font-size: 0.8rem; color: #666; }
    .split-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #00008a;
        border: 3px solid; vertical-align: -2px; margin-right: 4px; }
    .split-caption { text-align: center; color: #555; font-size: 0.92rem; margin-top: 0.3rem; min-height: 1.3em; }
    .split-caption strong { color: #111; }
    .split-mini { display: inline-grid; gap: 3px; background: #0b0b0b; padding: 8px 10px; border-radius: 8px;
        vertical-align: middle; }
    .split-mini div { display: flex; gap: 2px; align-items: center; }
    .split-mini em { font-style: normal; font-size: 0.7rem; width: 46px; color: #ddd; }
    .split-mini b { width: 9px; height: 9px; border-radius: 50%; background: #00008a; border: 2px solid;
        display: inline-block; }
    `;
    if (!document.getElementById("split-scene-css")) {
        var style = document.createElement("style");
        style.id = "split-scene-css";
        style.textContent = CSS;
        document.head.appendChild(style);
    }

    // The game's rule (experiment.py, transfer()): the player who collected more gives
    // contract * gap / 2 points to the other, counted in moves and rounded to a whole move.
    // Returned in points, to the nearest half point, which is what the scene can draw.
    function transfer(w, own, other, pointMoves) {
        var pm = pointMoves || 6, gap = w * (own - other) * pm / 2;
        var moves = Math.floor(Math.abs(gap) + 0.5 + 1e-9) * (gap >= 0 ? 1 : -1);
        return Math.round(moves / pm * 2) / 2;
    }

    function amount(n) {
        var whole = Math.floor(n + 1e-9), half = n - whole > 0.25;
        return (whole || !half ? String(whole) : "") + (half ? "\u00bd" : "");
    }

    function pacman(color, ring) {
        return '<svg viewBox="-1 -1 2 2">'
            + (ring ? '<circle r=".92" fill="none" stroke="#fff" stroke-width=".12"/>' : "")
            + '<path d="M0 0 L.68 -.37 A.78 .78 0 1 0 .68 .37 Z" fill="' + color + '"/></svg>';
    }

    function colors(opts) {
        return {
            you: opts.youColor || "#f1c40f",
            partner: opts.partnerColor || "#e74c3c",
            youLabel: opts.youLabel || "You",
            partnerLabel: opts.partnerLabel || "Partner",
        };
    }

    function SplitScene(root, opts) {
        opts = opts || {};
        var c = colors(opts);
        var height = 200, laneY = {you: 52, partner: 148};
        root.classList.add("split-scene");
        root.style.height = height + "px";
        root.innerHTML =
            '<div class="ss-who" style="top:' + (laneY.you - 26) + 'px">' + pacman(c.you, true) + c.youLabel + "</div>"
            + '<div class="ss-who" style="top:' + (laneY.partner - 26) + 'px">' + pacman(c.partner, false) + c.partnerLabel + "</div>"
            + '<div class="ss-lane" style="top:' + (laneY.you - 23) + 'px"></div>'
            + '<div class="ss-lane" style="top:' + (laneY.partner - 23) + 'px"></div>'
            + '<div class="ss-equal" data-row="you" style="top:' + (laneY.you - 15) + 'px"><span>equal</span></div>'
            + '<div class="ss-equal" data-row="partner" style="top:' + (laneY.partner - 15) + 'px"><span>equal</span></div>'
            + '<div class="ss-count" data-row="you" style="top:' + (laneY.you - 18) + 'px">0<small>points</small></div>'
            + '<div class="ss-count" data-row="partner" style="top:' + (laneY.partner - 18) + 'px">0<small>points</small></div>';
        var dots = [], have = {you: 0, partner: 0}, contract = 0, x0 = 100, gap = 26, halfEl = null;

        // Spacing and dot size so that a full row (everything both collected) stays clear of
        // the counters, however many points there are.
        function fit() {
            var width = root.clientWidth || 600, room = width - x0 - 100;
            var most = Math.max(have.you + have.partner, 1);
            gap = Math.max(4, Math.min(26, room / most));
            var dot = Math.max(6, Math.min(20, gap - 4));
            root.style.setProperty("--dot", dot + "px");
            root.style.setProperty("--ring", Math.max(2, Math.round(dot / 5)) + "px");
        }

        function example(you, partner) {
            dots.forEach(function (d) { d.el.remove(); });
            dots = [];
            if (halfEl) { halfEl.remove(); halfEl = null; }
            have = {you: Math.max(0, Math.round(you)), partner: Math.max(0, Math.round(partner))};
            fit();
            ["you", "partner"].forEach(function (who) {
                for (var i = 0; i < have[who]; i++) {
                    var el = document.createElement("div");
                    el.className = "ss-dot";
                    el.style.borderColor = c[who];
                    el.style.left = (x0 + i * gap) + "px";
                    el.style.top = laneY[who] + "px";
                    root.appendChild(el);
                    dots.push({owner: who, el: el});
                }
            });
            var equalX = x0 + ((have.you + have.partner) / 2 - 0.5) * gap;
            root.querySelectorAll(".ss-equal").forEach(function (e) {
                e.style.left = equalX + "px";
                e.style.display = have.you === have.partner ? "none" : "";
            });
            set(contract, false);
        }

        function place(el, x, who, k, animate) {
            el.style.transitionDelay = animate && k >= 0 ? (k * 0.1) + "s" : "0s";
            if (!animate) el.style.transition = "none";
            el.style.left = x + "px";
            el.style.top = laneY[who] + "px";
            if (!animate) { el.offsetWidth; el.style.transition = ""; }
        }

        function set(w, animate) {
            contract = Math.max(0, Math.min(1, Number(w) || 0));
            var t = transfer(contract, have.you, have.partner, opts.pointMoves);
            var giver = t >= 0 ? "you" : "partner", taker = giver === "you" ? "partner" : "you";
            var whole = Math.floor(Math.abs(t)), half = Math.abs(t) - whole > 0.25;
            var own = dots.filter(function (d) { return d.owner === giver; });
            var moving = own.slice(own.length - whole);
            var halved = half ? own[own.length - whole - 1] : null;
            var rows = {you: [], partner: []};
            dots.forEach(function (d) { if (moving.indexOf(d) < 0) rows[d.owner].push(d); });
            moving.slice().reverse().forEach(function (d) { rows[taker].push(d); });
            ["you", "partner"].forEach(function (who) {
                rows[who].forEach(function (d, i) {
                    var k = moving.indexOf(d);
                    place(d.el, x0 + i * gap, who, k, animate);
                    d.el.classList.toggle("moved", k >= 0);
                    d.el.classList.toggle("half-keep", d === halved);
                });
            });
            // Half a point: the giver keeps the left half of a dot, the taker gets the right half.
            if (half) {
                if (!halfEl) {
                    halfEl = document.createElement("div");
                    halfEl.className = "ss-dot half-give moved";
                    root.appendChild(halfEl);
                }
                halfEl.style.borderColor = c[giver];
                var from = rows[giver].indexOf(halved);
                if (!halfEl.dataset.row || halfEl.dataset.row !== taker) {
                    place(halfEl, x0 + from * gap, giver, -1, false);
                }
                halfEl.dataset.row = taker;
                place(halfEl, x0 + rows[taker].length * gap, taker, whole, animate);
            } else if (halfEl) {
                halfEl.remove();
                halfEl = null;
            }
            var counts = {you: rows.you.length, partner: rows.partner.length};
            if (half) { counts[giver] -= 0.5; counts[taker] += 0.5; }
            ["you", "partner"].forEach(function (who) {
                var counter = root.querySelector('.ss-count[data-row="' + who + '"]');
                var before = counter.firstChild.nodeValue, now = amount(counts[who]);
                counter.firstChild.nodeValue = now;
                if (animate && before !== now) {
                    counter.classList.add("bump");
                    setTimeout(function () { counter.classList.remove("bump"); }, 250);
                }
            });
            if (opts.onChange) opts.onChange({contract: contract, transfer: t,
                you: counts.you, partner: counts.partner});
            return rows;
        }

        example(opts.you || 0, opts.partner || 0);
        if (opts.contract) set(opts.contract, false);
        var lastWidth = root.clientWidth;
        window.addEventListener("resize", function () {
            if (root.clientWidth === lastWidth) return;
            lastWidth = root.clientWidth;
            example(have.you, have.partner);  // re-lays out the dots and keeps the contract
        });
        return {set: set, example: example, get: function () { return contract; }};
    }

    // One line under the scene saying what the contract does, in words.
    SplitScene.caption = function (info) {
        var w = Math.round(info.contract * 100), n = Math.abs(info.transfer);
        var head = "<strong>" + (100 - w) + "% commission · " + w + "% wages</strong>";
        if (!n) return head + ": everyone keeps what they collected";
        return head + ": " + (info.transfer > 0 ? "you give " : "your partner gives ") + amount(n)
            + (n <= 1 ? " point" : " points") + (info.transfer > 0 ? " to your partner" : " to you");
    };
    SplitScene.legend = function (opts) {
        var c = colors(opts || {});
        return '<div class="split-legend"><span><i style="border-color:' + c.you + '"></i>collected by you</span>'
            + '<span><i style="border-color:' + c.partner + '"></i>collected by your partner</span>'
            + "<span>glowing points were moved by the contract</span></div>";
    };
    SplitScene.transfer = transfer;
    window.SplitScene = SplitScene;
})();
