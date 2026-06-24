/* clemtock theme registry.
 *
 * A theme overrides the palette + the scene BACKDROP so a whole ad adopts a
 * brand look without touching templates. Resolved by ad-script `doc.theme`.
 *
 *   window.CLEMTOCK_THEMES[name] = {
 *     palette: { ink, cream, text, muted, lime, orange, line, line2 },
 *     backdrop(h, C, ctx) -> array of React nodes,   // ctx = { assets, tint, alpha }
 *     fonts?: { cond, mono, sten },
 *     // prompt presets (used by tooling / asset generation):
 *     stylePrompt?: string,        // prepended to gen-asset prompts
 *     backdropPrompt?: string,     // prompt to (re)generate the backdrop image
 *   }
 *
 * The renderer falls back to its built-in grid backdrop when no theme matches.
 */
(function () {
  const T = (window.CLEMTOCK_THEMES = window.CLEMTOCK_THEMES || {});

  /* ── Madd Hatchery ──────────────────────────────────────────────
     Mad-Hatter farmhouse: deep teal→plum night with a warm gingham
     wash + amber glow, so cream/teal/amber type pops. A generated
     backdrop image (asset id "backdrop"), if present, is laid in soft. */
  T.maddhatchery = {
    palette: {
      ink: "#15323a",          // deep teal base
      cream: "#f6eedb",        // headlines
      text: "#f3ece0",
      muted: "#cbe0db",
      lime: "#52e0d6",         // bright mint-teal accent (kicker / cta text)
      orange: "#f0a83a",       // amber accent (last line / cta border)
      line: "#234a52",
      line2: "#2c5a62",
    },
    stylePrompt:
      "Bold vintage cartoon sticker style, thick clean outlines, bright flat " +
      "colors with subtle halftone shading. Madd Hatchery palette: teal, deep " +
      "purple, cream, and warm amber. Wholesome hippy-country farmhouse mood.",
    backdropPrompt:
      "Soft blurred background pattern for a farm brand: deep teal and plum night " +
      "tones with a faint cream gingham check, scattered jam jars, peacock-feather " +
      "swirls, eggs and tiny chicks, warm amber glow, vignette. Muted, low-contrast, " +
      "no text — meant to sit behind headline type. Madd Hatchery look.",
    backdrop: function (h, C, ctx) {
      ctx = ctx || {};
      const assets = ctx.assets || {};
      const back = assets.backdrop && assets.backdrop.src;
      const nodes = [];
      // base teal→plum gradient (skip solid in alpha/compositing mode)
      if (!ctx.alpha)
        nodes.push(h("div", { key: "base", style: { position: "absolute", inset: 0,
          background: "linear-gradient(160deg, #15323a 0%, #1c2f44 48%, #3a1d4a 100%)" } }));
      // generated backdrop image, soft
      if (back)
        nodes.push(h("div", { key: "img", style: { position: "absolute", inset: 0,
          backgroundImage: "url(" + back + ")", backgroundSize: "cover",
          backgroundPosition: "center", opacity: 0.28, filter: "saturate(1.05)" } }));
      // gingham check wash
      nodes.push(h("div", { key: "gham", style: { position: "absolute", inset: 0, opacity: 0.10,
        backgroundImage:
          "linear-gradient(rgba(246,238,219,.9) 2px, transparent 2px)," +
          "linear-gradient(90deg, rgba(246,238,219,.9) 2px, transparent 2px)",
        backgroundSize: "120px 120px" } }));
      // warm amber glow, upper-center
      nodes.push(h("div", { key: "glow", style: { position: "absolute", left: "50%", top: 540,
        width: 1100, height: 1100, marginLeft: -550, marginTop: -550,
        background: "radial-gradient(circle, rgba(240,168,58,.20), transparent 60%)" } }));
      // optional tint + vignette
      if (ctx.tint)
        nodes.push(h("div", { key: "tint", style: { position: "absolute", inset: 0, background: ctx.tint } }));
      nodes.push(h("div", { key: "vig", style: { position: "absolute", inset: 0,
        background: "radial-gradient(120% 78% at 50% 42%, transparent 36%, rgba(6,12,14,.78))" } }));
      return nodes;
    },
  };
})();
