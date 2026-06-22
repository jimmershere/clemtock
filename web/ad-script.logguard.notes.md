# Log Guard launch ad — brief

`web/ad-script.logguard.json` is a data-driven clemtock ad-script (schema:
`schema/ad-script.schema.json`, validated) for launching **Local-81 Log Guard**.

- **Format:** vertical 9:16, 1080×1920, 30fps, ~20s.
- **Mascot:** `portwr-clem` → `assets/mascots/portwr-clem.png`.
- **Arc:** hook → Agentjacking threat (terminal scene shows an injected log line
  being BLOCKED by `local81 scan`) → "Clem stands watch" mascot beat → the two
  controls (Merkle integrity + sanitization) → CTA to the repo.
- **No `source:gen` assets** — it deliberately uses only the uploaded mascot and
  text templates, so it can render without any AI image/video spend.

## Messaging guardrails

- Lead with the honest differentiator: integrity proves bytes are *unchanged
  since capture*; **sanitization is what actually stops injection**. Don't imply
  the hash alone blocks the attack.
- No fabricated metrics, customers, or endorsements.

## Rendering (requires a human)

`clemtock` is a Phase-0 scaffold; rendering is not wired here. To produce the MP4
on a host that has the implemented package + system chromium + ffmpeg:

```bash
source scripts/load-env.sh          # only needed if regenerating source:gen assets (none here)
python -m clemtock export --script web/ad-script.logguard.json --out out/logguard-ad.mp4
```

Then review the MP4 and post via your normal channel. Publishing, targeting, and
any ad spend stay a human decision.
