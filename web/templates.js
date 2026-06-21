/* clemtock scene template library.
 *
 * Each template is a pure function (h, t, scene, ctx) -> array of React nodes, where:
 *   h     = React.createElement
 *   t     = global timeline seconds
 *   scene = the ad-script scene object (start, end, copy, assets, motion, params)
 *   ctx   = { C (palette), F (fonts), assets (id->descriptor), canvas, helpers... }
 *
 * This is the data-driven generalization of the hand-authored Local 81 promo scenes.
 * Registry is exposed as window.CLEMTOCK_TEMPLATES and resolved by scene.template.
 */
(function () {
  const reg = {};

  // local progress helpers bound to a scene
  function local(scene, ctx) {
    const u = (t) => t - scene.start;
    const dur = scene.end - scene.start;
    return { u, dur };
  }

  /* title — kicker / headline / sub, stamped in. */
  reg.title = function (h, t, scene, ctx) {
    const { C, F, prog, eo, lerp, stamp } = ctx;
    const c = scene.copy || {};
    const nodes = [];
    nodes.push(...ctx.bg(scene.params && scene.params.tint));
    if (c.kicker)
      nodes.push(ctx.txt("k", c.kicker, {
        position: "absolute", top: 150, left: 80, fontFamily: F.mono, fontSize: 30,
        letterSpacing: 4, color: C.lime, opacity: prog(t, scene.start, scene.start + 0.3),
      }));
    const lines = (c.headline || "").split("\n");
    nodes.push(h("div", { key: "hl", style: { position: "absolute", left: 80, right: 80, top: 360 } },
      lines.map((ln, i) => {
        const at = scene.start + 0.25 + i * 0.18;
        const p = prog(t, at, at + 0.22);
        return h("div", { key: i, style: {
          fontFamily: F.cond, fontWeight: 800, fontSize: 120, lineHeight: 1.02,
          letterSpacing: -2, color: i === lines.length - 1 ? C.orange : C.cream,
          opacity: p, transform: "scale(" + stamp(p) + ")", transformOrigin: "left center",
        } }, ln);
      })));
    if (c.sub) {
      const sp = prog(t, scene.start + 0.6, scene.start + 0.95);
      nodes.push(ctx.txt("s", c.sub, {
        position: "absolute", left: 80, right: 80, bottom: 320, fontFamily: F.mono,
        fontSize: 36, lineHeight: 1.4, color: C.muted, opacity: sp,
        transform: "translateY(" + lerp(30, 0, eo(sp)) + "px)",
      }));
    }
    return nodes;
  };

  /* photo — full-bleed image with Ken-Burns, caption at the bottom. */
  reg.photo = function (h, t, scene, ctx) {
    const { C, F, prog, lerp, eo } = ctx;
    const { u, dur } = local(scene, ctx);
    const a = (scene.assets || []).map((id) => ctx.assets[id]).filter(Boolean)[0];
    const m = scene.motion || {};
    const from = m.from != null ? m.from : 1.0;
    const to = m.to != null ? m.to : 1.12;
    const k = lerp(from, to, Math.max(0, Math.min(1, u(t) / dur)));
    const nodes = [h("div", { key: "bg", style: { position: "absolute", inset: 0, background: C.ink } })];
    if (a && a.src)
      nodes.push(h("div", { key: "im", style: { position: "absolute", inset: 0, overflow: "hidden" } },
        h("img", { src: a.src, style: {
          width: "100%", height: "100%", objectFit: "cover", display: "block",
          transform: "scale(" + k + ")", transformOrigin: "50% 40%",
        } })));
    else
      nodes.push(ctx.txt("ph", "[ image: " + ((scene.assets || [])[0] || "?") + " ]", {
        position: "absolute", inset: 0, display: "flex", alignItems: "center",
        justifyContent: "center", fontFamily: F.mono, fontSize: 40, color: C.line2,
      }));
    nodes.push(h("div", { key: "scrim", style: { position: "absolute", inset: 0,
      background: "linear-gradient(transparent 45%, rgba(6,9,14,.85))" } }));
    const c = scene.copy || {};
    if (c.headline) {
      const p = prog(t, scene.start + 0.2, scene.start + 0.55);
      nodes.push(ctx.txt("cap", c.headline, {
        position: "absolute", left: 80, right: 80, bottom: 220, fontFamily: F.cond,
        fontWeight: 800, fontSize: 96, lineHeight: 0.95, letterSpacing: -1, color: C.cream,
        opacity: p, transform: "translateY(" + lerp(40, 0, eo(p)) + "px)",
      }));
    }
    return nodes;
  };

  /* video — full-bleed real clip with copy over it.
   * In alpha/compositing mode the clip is supplied by the ffmpeg base layer, so we render
   * ONLY the copy and leave the media region transparent ("hole"). In live preview we show
   * the <video> element so scrubbing looks right. */
  reg.video = function (h, t, scene, ctx) {
    const { C, F, prog } = ctx;
    const a = (scene.assets || []).map((id) => ctx.assets[id]).filter(Boolean)[0];
    const nodes = [];
    if (!ctx.alpha) {
      nodes.push(h("div", { key: "bg", style: { position: "absolute", inset: 0, background: C.ink } }));
      if (a && a.src)
        nodes.push(h("video", { key: "v", src: a.src, autoPlay: true, muted: true, loop: true,
          playsInline: true, style: { position: "absolute", inset: 0, width: "100%",
            height: "100%", objectFit: "cover" } }));
      else
        nodes.push(ctx.txt("vh", "[ video: " + ((scene.assets || [])[0] || "?") + " ]", {
          position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", fontFamily: F.mono, fontSize: 40, color: C.line2 }));
    }
    const c = scene.copy || {};
    if (c.headline) {
      const scrim = ctx.alpha
        ? h("div", { key: "sc", style: { position: "absolute", inset: 0,
            background: "linear-gradient(transparent 55%, rgba(6,9,14,.8))" } })
        : null;
      if (scrim) nodes.push(scrim);
      nodes.push(ctx.txt("cap", c.headline, { position: "absolute", left: 80, right: 80,
        bottom: 240, fontFamily: F.cond, fontWeight: 800, fontSize: 88, color: C.cream,
        opacity: prog(t, scene.start + 0.2, scene.start + 0.5) }));
    }
    return nodes;
  };

  /* terminal — types copy.headline as a command, reveals copy.sub lines as output. */
  reg.terminal = function (h, t, scene, ctx) {
    const { C, F, prog } = ctx;
    const c = scene.copy || {};
    const cmd = c.headline || "";
    const cp = prog(t, scene.start + 0.1, scene.start + 0.1 + Math.max(0.4, cmd.length * 0.03));
    const shown = cmd.slice(0, Math.floor(cmd.length * cp));
    const lines = (c.sub || "").split("\n").filter(Boolean);
    const nodes = ctx.bg(null);
    if (c.kicker)
      nodes.push(ctx.txt("k", c.kicker, { position: "absolute", top: 150, left: 80,
        fontFamily: F.mono, fontSize: 30, letterSpacing: 4, color: C.lime,
        opacity: prog(t, scene.start, scene.start + 0.3) }));
    nodes.push(h("div", { key: "con", style: { position: "absolute", left: 80, right: 80,
      top: 340, background: "rgba(8,13,18,.95)", border: "1px solid " + C.line2,
      borderRadius: 16, padding: "28px 30px", fontFamily: F.mono, fontSize: 36 } }, [
      h("div", { key: "cmd" }, [
        h("span", { key: "p", style: { color: C.lime, fontWeight: 700 } }, "$ "),
        h("span", { key: "c", style: { color: C.text } }, shown),
        h("span", { key: "cur", style: { color: C.lime, opacity: cp < 1 ? 1 : 0 } }, "█"),
      ]),
      ...lines.map((ln, i) => {
        const at = scene.start + 0.6 + i * 0.25;
        return h("div", { key: "o" + i, style: { marginTop: 16, color: C.muted,
          opacity: prog(t, at, at + 0.2) } }, ln);
      }),
    ]));
    return nodes;
  };

  /* cta — wordmark/headline, optional asset badge, glowing CTA banner. */
  reg.cta = function (h, t, scene, ctx) {
    const { C, F, prog, lerp, eo, back } = ctx;
    const c = scene.copy || {};
    const p = prog(t, scene.start, scene.start + 0.4);
    const nodes = ctx.bg(null);
    nodes.push(h("div", { key: "gl", style: { position: "absolute", left: "50%", top: 700,
      width: 900, height: 900, marginLeft: -450, marginTop: -450,
      background: "radial-gradient(circle,rgba(166,232,74,.16),transparent 60%)", opacity: p } }));
    if (c.headline)
      nodes.push(h("div", { key: "w", style: { position: "absolute", left: 80, right: 80,
        top: 620, textAlign: "center", fontFamily: F.cond, fontWeight: 800, fontStyle: "italic",
        fontSize: 170, lineHeight: 0.9, letterSpacing: -4, color: C.cream,
        transform: "scale(" + lerp(0.86, 1, back(p)) + ")", opacity: p } }, c.headline));
    if (c.sub)
      nodes.push(ctx.txt("s", c.sub, { position: "absolute", left: 0, right: 0, top: 880,
        textAlign: "center", fontFamily: F.mono, fontSize: 30, letterSpacing: 6, color: C.lime,
        opacity: prog(t, scene.start + 0.3, scene.start + 0.6) }));
    if (c.cta) {
      const pulse = 0.85 + 0.15 * Math.sin(t * 4);
      nodes.push(h("div", { key: "cta", style: { position: "absolute", left: 80, right: 80,
        top: 1120, textAlign: "center", opacity: prog(t, scene.start + 0.5, scene.start + 0.8) } },
        h("span", { style: { display: "inline-block", background: "rgba(20,12,6,.92)",
          border: "3px solid " + C.orange, borderRadius: 14, padding: "24px 36px",
          fontFamily: F.mono, fontSize: 44, color: C.lime, fontWeight: 700,
          boxShadow: "0 0 " + (46 * pulse).toFixed(1) + "px rgba(239,106,40,.5)" } }, c.cta)));
    }
    return nodes;
  };

  /* split — media on the top half, stacked copy on the bottom (or reversed). */
  reg.split = function (h, t, scene, ctx) {
    const { C, F, prog, lerp, eo } = ctx;
    const c = scene.copy || {};
    const p = (scene.params && scene.params.reverse) ? true : false;
    const a = (scene.assets || []).map((id) => ctx.assets[id]).filter(Boolean)[0];
    const enter = prog(t, scene.start + 0.15, scene.start + 0.5);
    const media = h("div", { key: "m", style: { position: "absolute", left: 0, right: 0,
      top: p ? "50%" : 0, height: "50%", overflow: "hidden", background: C.ink } },
      a && a.src
        ? h("img", { src: a.src, style: { width: "100%", height: "100%", objectFit: "cover",
            transform: "scale(" + lerp(1.0, 1.08, Math.max(0, Math.min(1, (t - scene.start) / (scene.end - scene.start)))) + ")" } })
        : ctx.txt("ph", "[ " + ((scene.assets || [])[0] || "media") + " ]", { position: "absolute",
            inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: F.mono, fontSize: 36, color: C.line2 }));
    const copyPanel = h("div", { key: "c", style: { position: "absolute", left: 0, right: 0,
      top: p ? 0 : "50%", height: "50%", display: "flex", flexDirection: "column",
      justifyContent: "center", padding: "0 80px", opacity: enter,
      transform: "translateY(" + lerp(p ? -30 : 30, 0, eo(enter)) + "px)" } }, [
      c.kicker ? ctx.txt("k", c.kicker, { fontFamily: F.mono, fontSize: 28, letterSpacing: 3,
        color: C.lime, marginBottom: 20 }) : null,
      c.headline ? ctx.txt("h", c.headline, { fontFamily: F.cond, fontWeight: 800, fontSize: 88,
        lineHeight: 0.95, letterSpacing: -1, color: C.cream }) : null,
      c.sub ? ctx.txt("s", c.sub, { marginTop: 18, fontFamily: F.mono, fontSize: 32,
        lineHeight: 1.4, color: C.muted }) : null,
    ]);
    return [h("div", { key: "bg", style: { position: "absolute", inset: 0, background: C.ink } }),
      media, copyPanel];
  };

  window.CLEMTOCK_TEMPLATES = reg;
})();
