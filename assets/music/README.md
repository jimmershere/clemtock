# clemtock music library

Optional royalty-free music beds for ads. Tracks are organized by **mood folder**;
the studio's publish panel lists them and `clemtock music` / `clemtock publish --music`
loops/trims the chosen track to the video length and muxes it in.

> **TikTok:** never bake a bed in — TikTok requires sound be added in-app (licensing +
> sound discovery). The TikTok publish path always posts the raw video. Music is for
> YouTube / Facebook / Instagram / X / Lemon8 / Threads, and is always **optional**
> (skip it for narrated/tutorial spots).

## Add your own tracks

Drop `.mp3/.m4a/.wav` files into the right mood folder, e.g.
`assets/music/hip-hop/my_beat.mp3`. They appear in the picker after the next asset
scan (every 15 min, or hit **rescan**, or `GET /api/music`). **You are responsible for
the license of anything you add** — only use tracks cleared for commercial use.

## Sourced tracks (auto-fetched, commercial-safe, attribution recorded)

| Mood | File | License | Attribution / Source |
|------|------|---------|----------------------|
| momentous | `momentous/momentous_maelstrom-the-passage.mp3` | **CC0 1.0** (public domain — no attribution required) | Internet Archive netlabels |
| classic-rock | `classic-rock/classicrock_nicolas-falcon-aaahh.mp3` | **CC BY 3.0** (commercial OK *with credit*) | "Aaahh" — Nicolas Falcon, via Internet Archive netlabels — **credit required in the post/description** |

> CC-BY requires crediting the artist wherever the ad is published. For CC0 no credit is
> needed. Exact source pages are in `_manifest.json`.

## Gaps — theatrical & hip-hop

Auto-sourcing genre-accurate **theatrical** and **hip-hop** beds under a clean
commercial license (CC0 / CC-BY) wasn't reliable from the public-domain pool, so those
folders are intentionally left for you to fill with ear-checked picks. Vetted
royalty-free sources (commercial-OK, most no-attribution):

- **Pixabay Music** — pixabay.com/music — Pixabay license, free for commercial, no attribution. Strong for hip-hop, cinematic/theatrical, rock.
- **YouTube Audio Library** — studio.youtube.com (Audio Library) — free, many no-attribution tracks, mood/genre filters.
- **Uppbeat** — uppbeat.io — free tier with credit; deep hip-hop + cinematic catalogs.
- **Free Music Archive** — freemusicarchive.org — filter to CC-BY / CC0.
- **ccMixter** — dig.ccmixter.org — CC music, check each track's license.

Pick a track, confirm its license allows commercial use, drop it in the mood folder.
