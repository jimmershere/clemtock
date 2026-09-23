"""vast.ai GPU lifecycle — rent a 4090, run a render, give it back.

Neither fleet host has a discrete GPU (verified 2026-09-23), and the open video models
floor out at 8 GB VRAM. So the heavy half of the pipeline lives on a rented box and the
fleet keeps the orchestration. See /app/portrender/docs/local-ai-options.md.

RENTING SPENDS REAL MONEY. This module follows the house gate convention — local81 is
dry-run unless --apply, tee-empire is dry_run=not args.live — so every billable call here
takes `live: bool = False` and does nothing but describe itself until told otherwise.
Two further guards, because an idle GPU bills exactly like a busy one:

  * `max_dph` is enforced client-side before any ask is accepted.
  * `destroy()` is the only way to stop billing; `rent()` logs that obligation loudly.

API surface (base https://console.vast.ai):
  GET    /api/v0/bundles/?q=<json>     search offers   [verified 2026-09-23]
  GET    /api/v1/instances/            list instances  [verified 2026-09-23 — v0 is 410 deprecated]
  PUT    /api/v0/asks/{offer_id}/      rent an offer   [from vast docs, NOT exercised]
  DELETE /api/v0/instances/{id}/       destroy         [from vast docs, NOT exercised]

Stdlib-only HTTP, matching the rest of the provider layer.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .base import ProviderUnavailable

BASE = "https://console.vast.ai"

# A ComfyUI-bearing image is what the render workers actually need. vast publishes
# templates; this default is a placeholder that MUST be confirmed against the account's
# template list before the first real rent (see docs — open question PR-9).
DEFAULT_IMAGE = os.environ.get("VAST_IMAGE", "vastai/comfy:latest")


@dataclass(frozen=True)
class Offer:
    id: int
    dph: float
    gpu_name: str
    gpu_ram_gb: float
    cpu_ram_gb: float
    disk_gb: float
    inet_down: float
    reliability: float
    location: str

    def __str__(self) -> str:
        return (f"offer {self.id}: {self.gpu_name} {self.gpu_ram_gb:.0f}GB @ "
                f"${self.dph:.3f}/hr, {self.location}, reliability {self.reliability:.3f}")


class VastError(ProviderUnavailable):
    """vast.ai refused, or is unreachable."""


class VastGPU:
    """Thin client over the vast.ai REST API. Read calls are free; writes are gated."""

    def __init__(self, api_key: str = "", *, gpu_name: str = "", max_dph: float = 0.0,
                 timeout: int = 60, log: Callable[[str], None] = print):
        self.api_key = api_key or os.environ.get("VAST_API_KEY", "")
        if not self.api_key:
            raise VastError("VAST_API_KEY is not set (see /app/clemtock/.env)")
        self.gpu_name = gpu_name or os.environ.get("VAST_GPU_NAME", "RTX 4090").replace("_", " ")
        self.max_dph = float(max_dph or os.environ.get("VAST_MAX_DPH", "0.60"))
        self.timeout = timeout
        self.log = log

    # ---------- transport ----------
    def _req(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            BASE + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Accept": "application/json",
                     **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise VastError(f"vast {method} {path} -> HTTP {e.code}: "
                            f"{e.read().decode('utf-8', 'replace')[:300]}") from e
        except urllib.error.URLError as e:
            raise VastError(f"vast unreachable: {e.reason}") from e
        return json.loads(raw) if raw else {}

    # ---------- read (free) ----------
    def account(self) -> dict:
        return self._req("GET", "/api/v0/users/current/")

    def credit(self) -> float:
        me = self.account()
        return float(me.get("credit") or 0.0) + float(me.get("balance") or 0.0)

    def search(self, *, limit: int = 10, min_vram_gb: float = 24,
               min_disk_gb: float = 80, num_gpus: int = 1) -> list[Offer]:
        """Cheapest verified, rentable offers matching the shape, under max_dph."""
        q = {
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "gpu_name": {"eq": self.gpu_name},
            "num_gpus": {"eq": num_gpus},
            # A "24GB" 4090 reports 24564 MiB, which is UNDER 24*1024=24576 — filtering on
            # the nominal figure silently drops every card you actually wanted. 3% slack.
            "gpu_ram": {"gte": int(min_vram_gb * 1024 * 0.97)},
            "disk_space": {"gte": min_disk_gb},
            "dph_total": {"lte": self.max_dph},
            "order": [["dph_total", "asc"]],
            "limit": limit,
            "type": "on-demand",
        }
        d = self._req("GET", "/api/v0/bundles/?q=" + urllib.parse.quote(json.dumps(q)))
        return [Offer(
            id=o.get("id"), dph=float(o.get("dph_total", 0)), gpu_name=o.get("gpu_name", ""),
            gpu_ram_gb=float(o.get("gpu_ram", 0)) / 1024, cpu_ram_gb=float(o.get("cpu_ram", 0)) / 1024,
            disk_gb=float(o.get("disk_space", 0)), inet_down=float(o.get("inet_down", 0)),
            reliability=float(o.get("reliability2", 0)), location=o.get("geolocation") or "?",
        ) for o in d.get("offers", [])]

    def instances(self) -> list[dict]:
        # v0 returns 410 deprecated; v1 is the live endpoint.
        return self._req("GET", "/api/v1/instances/").get("instances", []) or []

    def instance(self, instance_id: int) -> dict | None:
        for i in self.instances():
            if int(i.get("id", -1)) == int(instance_id):
                return i
        return None

    def running_cost(self) -> float:
        """Current $/hr being billed across every instance on the account."""
        return sum(float(i.get("dph_total") or 0) for i in self.instances())

    # ---------- write (billable — gated) ----------
    def rent(self, offer: Offer, *, live: bool = False, image: str = "",
             disk_gb: float = 80, onstart: str = "", env: dict | None = None) -> dict:
        """Rent `offer`. Does nothing unless live=True.

        Billing starts the moment the instance is created and stops only at destroy().
        """
        if offer.dph > self.max_dph:
            raise VastError(f"refusing {offer.id}: ${offer.dph:.3f}/hr exceeds "
                            f"VAST_MAX_DPH=${self.max_dph:.3f}")
        body = {
            "client_id": "me",
            "image": image or DEFAULT_IMAGE,
            "disk": disk_gb,
            "runtype": "ssh",
            "onstart": onstart or "",
            "env": env or {},
        }
        if not live:
            self.log(f"[dry-run] PUT /api/v0/asks/{offer.id}/  {json.dumps(body)[:160]}…")
            self.log(f"[dry-run] would rent {offer} — ${offer.dph:.3f}/hr until destroyed")
            return {"dry_run": True, "offer": offer.id, "body": body}
        credit = self.credit()
        if credit <= 0:
            raise VastError(f"account credit is ${credit:.2f} — not renting")
        res = self._req("PUT", f"/api/v0/asks/{offer.id}/", body)
        self.log(f"RENTED {offer} — billing has STARTED. destroy() is the only stop. "
                 f"credit before: ${credit:.2f}")
        return res

    def destroy(self, instance_id: int, *, live: bool = False) -> dict:
        """Destroy an instance. This is what stops the meter."""
        if not live:
            self.log(f"[dry-run] DELETE /api/v0/instances/{instance_id}/ — would stop billing")
            return {"dry_run": True, "instance": instance_id}
        res = self._req("DELETE", f"/api/v0/instances/{instance_id}/", {})
        self.log(f"destroyed instance {instance_id} — billing stopped")
        return res

    def destroy_all(self, *, live: bool = False) -> list[dict]:
        """Panic button: give every instance back. Cheap insurance against a stuck run."""
        return [self.destroy(int(i["id"]), live=live) for i in self.instances()]

    # ---------- orchestration ----------
    def wait_running(self, instance_id: int, *, timeout: int = 900,
                     poll: int = 15) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            inst = self.instance(instance_id)
            status = (inst or {}).get("actual_status") or (inst or {}).get("cur_state") or "?"
            if status == "running":
                return inst
            self.log(f"  instance {instance_id}: {status} …")
            time.sleep(poll)
        raise VastError(f"instance {instance_id} not running after {timeout}s — "
                        f"destroy it so it stops billing")
