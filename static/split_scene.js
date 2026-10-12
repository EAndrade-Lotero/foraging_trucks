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
    .split-scene .ss-dot { position: absolute; width: 20px; height: 20px; margin: -10px 0 0 -10px;
        border-radius: 50%; background: #00008a; border: 4px solid; box-shadow: 0 0 0 2px #0b0b0b;
        transition: left 0.6s cubic-bezier(.3,.7,.3,1), top 0.6s cubic-bezier(.3,.7,.3,1), box-shadow 0.3s; }
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

    // The game's rule: the player who collected more gives contract * gap / 2 points to the
    // other, rounded to a whole point (experiment.py, transfer()).
    function transfer(w, own, other) {
        var gap = w * (own - other) / 2, whole = Math.floor(Math.abs(gap) + 0.5 + 1e-9);
        return gap >= 0 ? whole : -whole;
    }

    function pacman(color, ring) {
        return '<svg viewBox="-1 -1 2 2">'
            + (ring ? '<circle r=".92" fill="none" stroke="#fff" stroke-width=".12"/>' : "")
            + '<path d="M0 0 L.68 -.37 A.78 .78 0 1 0 .68 .37 Z" fill="' + color + '"/></svg>';
    }

    // A small static picture of a split, for quiz options: rows of dots coloured by finder.
    function mini(opts, you, partner, contract) {
        var t = transfer(contract, you, partner), c = colors(opts);
        function row(label, own, color, given, givenColor) {
            var s = "<div><em>" + label + "</em>";
            for (var i = 0; i < own; i++) s += '<b style="border-color:' + color + '"></b>';
            for (var j = 0; j < given; j++) s += '<b style="border-color:' + givenColor + '"></b>';
            return s + "</div>";
        }
        return '<span class="split-mini">'
            + row(c.youLabel, you - Math.max(t, 0), c.you, Math.max(-t, 0), c.partner)
            + row(c.partnerLabel, partner - Math.max(-t, 0), c.partner, Math.max(t, 0), c.you)
            + "</span>";
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
        var dots = [], have = {you: 0, partner: 0}, contract = 0, x0 = 100, gap = 26;

        function fit() {
            var width = root.clientWidth || 600, room = width - x0 - 100;
            var most = Math.max(have.you + have.partner, 1);
            gap = Math.max(8, Math.min(26, room / most));
        }

        function example(you, partner) {
            dots.forEach(function (d) { d.el.remove(); });
            dots = [];
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

        function set(w, animate) {
            contract = Math.max(0, Math.min(1, Number(w) || 0));
            var t = transfer(contract, have.you, have.partner);
            var giver = t >= 0 ? "you" : "partner", taker = giver === "you" ? "partner" : "you";
            var own = dots.filter(function (d) { return d.owner === giver; });
            var moving = own.slice(own.length - Math.abs(t));
            var rows = {you: [], partner: []};
            dots.forEach(function (d) { if (moving.indexOf(d) < 0) rows[d.owner].push(d); });
            moving.slice().reverse().forEach(function (d) { rows[taker].push(d); });
            ["you", "partner"].forEach(function (who) {
                rows[who].forEach(function (d, i) {
                    var k = moving.indexOf(d);
                    d.el.style.transitionDelay = animate && k >= 0 ? (k * 0.1) + "s" : "0s";
                    if (!animate) d.el.style.transition = "none";
                    d.el.style.left = (x0 + i * gap) + "px";
                    d.el.style.top = laneY[who] + "px";
                    d.el.classList.toggle("moved", k >= 0);
                    if (!animate) { d.el.offsetWidth; d.el.style.transition = ""; }
                });
                var counter = root.querySelector('.ss-count[data-row="' + who + '"]');
                var before = counter.firstChild.nodeValue;
                counter.firstChild.nodeValue = rows[who].length;
                if (animate && before != rows[who].length) {
                    counter.classList.add("bump");
                    setTimeout(function () { counter.classList.remove("bump"); }, 250);
                }
            });
            if (opts.onChange) opts.onChange({contract: contract, transfer: t,
                you: rows.you.length, partner: rows.partner.length});
            return rows;
        }

        example(opts.you || 0, opts.partner || 0);
        if (opts.contract) set(opts.contract, false);
        return {set: set, example: example, get: function () { return contract; }};
    }

    // One line under the scene saying what the contract does, in words.
    SplitScene.caption = function (info, youLabel) {
        var w = Math.round(info.contract * 100), n = Math.abs(info.transfer);
        var head = "<strong>" + (100 - w) + "% commission · " + w + "% wages</strong>";
        if (!n) return head + ": everyone keeps what they collected";
        var from = info.transfer > 0 ? (youLabel || "you") + " give" : "your partner gives";
        return head + ": " + from + " " + n + (n === 1 ? " point" : " points")
            + (info.transfer > 0 ? " to your partner" : " to you");
    };
    SplitScene.legend = function (opts) {
        var c = colors(opts || {});
        return '<div class="split-legend"><span><i style="border-color:' + c.you + '"></i>collected by you</span>'
            + '<span><i style="border-color:' + c.partner + '"></i>collected by your partner</span>'
            + "<span>glowing points were moved by the contract</span></div>";
    };
    SplitScene.mini = mini;
    SplitScene.transfer = transfer;
    window.SplitScene = SplitScene;
})();
