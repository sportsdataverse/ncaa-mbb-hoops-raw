# stats.ncaa.org scraping — everything we know

Hard-won operational knowledge for the NCAA raw scraper. Last updated **2026-08-11**.
Written after a backfill stalled at 38% and burned two proxy subnets; every claim
here is either measured live or explicitly flagged as unproven.

**READ THIS WHOLE FILE BEFORE ANY SCRAPE RUN.** The 2026-08-01 campaign burned
~3 hours re-deriving facts already recorded here.

---

## 2026-08-11 — WORKERS must be COPRIME to the worker count that left the gap

**Measured, 11x speedup.** Re-running a season's stragglers went from ~3
captures/min to **34.6/min** by changing one number: `WORKERS` 8 -> **23**.
Raising it to 24 would have changed *nothing*.

**Why.** `capture.shard()` splits the season by `k % n` over the SORTED
contest-id list. If an earlier campaign ran with `n` workers and ONE shard
died (ban, hard-stop, round cap), the contests it never captured are exactly
the positions `k ≡ r (mod n)` — a **stride-n residual**. Re-running with any
worker count that shares a factor with `n` maps that whole block back onto a
single worker, so one process does every remaining fetch sequentially while
the rest exit instantly with `captured=0 skipped=NNN`.

The August run used `WORKERS=24`. Measured distribution of what it left:

| WORKERS | shards with work | deepest shard (= wall clock) |
|---|---|---|
| 8 | 2 of 8 | 172 fetches |
| 12 | 2 of 12 | 172 |
| 16 | 3 of 16 | 86 |
| 24 | 2 of 24 | 172 |
| **23** | **23 of 23** | **9** |

**The rule: pick a `WORKERS` value coprime to the one that created the gap**
(and to its divisors). Against a stride-24 residual, 23 works; so would 25,
7, or 5. The driver's guard allows 1..24, so **23 is the practical choice**.
Check the port budget too — keep >=2 proxy ports per worker (the Decodo
vendor reported 50 ports, so 23 workers is ~2.2 each).

**The tell, in the log:** most workers printing `captured=0 skipped=~N/n` and
exiting within seconds, while one or two keep running. That is NOT "the
season is nearly done" — it is the whole remainder queued behind one process.

**Diagnose before turning the dial** — the shard math is cheap to compute:

```python
ids = sorted(master.filter(season==S).contest_id)          # from schedule_master
have = {p.name.split(".")[0] for p in os.scandir(f"mbb/raw/{S}")}
miss = [k for k, c in enumerate(ids) if c not in have]
for n in (8, 16, 23, 24):
    deepest = max(sum(1 for k in miss if k % n == r) for r in range(n))
    print(n, "->", deepest, "fetches deep")
```

Also confirmed this run: the 2017 residual (105 contests the August campaign
gave up on at `MAX_ROUNDS`) captured cleanly down to **1** remaining once the
work was spread. Those contests were never "un-capturable" — they were a
dead shard. Do not read a `MAX_ROUNDS` abandonment as evidence a contest has
no page.

---

## 2026-08-01 — multi-season campaign: session ceiling, tolerant discovery, port pool

Backfill campaign 2025→2010 (`scripts/run_mbb_backfill_range.sh`). Three failed
launches before a stable recipe; every fix below is committed.

**The winning stack (use this, don't re-derive):**

- **Transport:** patchright new-headless + real Chrome UA (unchanged from 07-16).
- **Proxy pool:** `decodo_patchright` vendor in `canary_vendors.toml` now holds
  **20 port-pinned sticky endpoints** `us.decodo.com:10001–10020`.
  **Geo-canary PASSED 2026-08-01**: all sampled ports egress US residential
  (AT&T / Verizon / T-Mobile / Spectrum / Frontier). This CORRECTS the 07-16
  note "port-based `:10001` = random-geo Spain" — that applied to a different
  hostname/cred; the `us.decodo.com` host pins country=US. Port style beats the
  single `gate.decodo.com:7000 -session-` URL for a pool: 20 independent sticky
  IPs, each auto-refreshed by Decodo, rotation = pick another port.
- **Discovery rides the same vendor seam**: `NCAA_VENDOR=decodo_patchright`
  (`754ed1a`). Team pages are bm-verify-challenged like game pages; the
  ProxyBonanza datacenter pool stopped clearing them entirely.

**Failure modes found (and their fixes):**

1. **Sticky-session aging ceiling (~70 min).** One browser context on one sticky
   session serves a whole ~350-team discovery sweep; past ~40–65 min bm-verify
   stops clearing on that session and every retry re-fails the same IP. Fix
   (`bc0d42e`): an exhausted solve **closes the browser context**, and every
   (re)launch **re-mints the `-session-` id** in a gate-style username — with the
   port pool, the fetcher's rotation moves to a different port = different IP.
   Matches the 07-13 observation (`31.14.9.13` died at ~70 min) — this is a
   session/IP property, not a code bug.
2. **Hard-stop discovery is mathematically doomed.** bm-verify clearing flakes
   ~5%/page even on a healthy vendor; a 350-page sweep that aborts on first
   failure completes with probability ≈ 0.95^350 ≈ 0. Fix (`945a1a5`): per-team
   retries (3), skip-after-retries, abort only on **5 consecutive** failed teams
   (real-ban signature). Skips are nearly lossless — every game appears on TWO
   teams' pages.
3. **Cold-start flake is worst on the first navigation** of a fresh profile
   (`413cfe4` added warm-up + range-script discover retry with ban cooldown; the
   range script must `continue`, not `break`, on a failed discover or the season
   silently never backfills).
4. **Orphan processes from stopped tasks** (bash children survive TaskStop) cause
   store collisions. Kill by `Name -match "^(python|chrome)"` + script-name
   pattern only — a broad CommandLine match self-kills the cleanup shell.

**Worker ceiling CORRECTED (user-verified):** the "WORKERS 1–2 max, 4 = ban"
rule in §5 was measured on the shared ProxyBonanza datacenter pool — it is
**pool-relative, not absolute**. With per-worker DISJOINT sticky residential
ports, up to 8 workers have run clean (request-session runs). What matters is
**per-IP pacing**, not process count. `_vendor_fetcher` now shards the port
pool by worker index (`shard_i/shard_n` — offset rotation) so parallel workers
never pile onto one port; launcher cap raised to 16 (keep ≥2 ports/worker).

**Resumability (2026-08-01):** BOTH stages are now disk-checkpointed. Capture
always was (file-exists per contest). Discovery now checkpoints each swept team
page to `{league}/.discover/{season}/{team_id}.json` — an aborted sweep resumes
instead of restarting (the 08-01 round-1 abort threw away 67 min of team pages;
never again). Delete that dir to force a fresh sweep.

**2025 season result (2026-08-01):** 6,293/6,296 captured (3 contests are
pageless — cancelled games), all parsed. **4.5% of games (282) parse to empty
`lineups`+`shots` — RESOLVED as an upstream data limitation, not a defect:**
all 282 are games vs non-NCAA opponents (NAIA etc.) whose individual_stats
page carries only ONE team block (classified exhaustively: 282/282 one-title,
0 name-match failures). `parse_team_name` requires both team titles, so the
engine cannot build 5-on-5 stints — correctly. `pbp`/`box`/`possessions`
still land for these games. This supersedes BOTH prior attributions (§6's
"individual_stats page failure" and the earlier "engine bails on broken
substitution data"). Expect the same few-percent rate every season.

**Campaign shape:** `run_mbb_backfill_range.sh START END` — seasons descending,
per-season rounds of (discover-if-needed → capture CHUNK=1400 → parse), cooldowns
between chunks (300 s) and after hard stops (1800 s), `MAX_ROUNDS=12`/season.
All knobs env-only. Watch: `tail -f logs/backfill_range_<ts>.log`. Scale:
~90–95k games 2010–2025 ≈ 75–80 h at ~1200 bundles/hr serial; N workers on
disjoint ports multiply that (16 workers ≈ a season's capture in well under
an hour — keep per-IP volume ≤ ~1400/session and canary first).

---

## 2026-07-16 — bm-verify SOLVED (supersedes the "buy a better service" framing below)

**A local browser DOES clear stats.ncaa.org bm-verify — cheaply, no paid service.**
Winning transport, proven live (10-game canary PASS: 19/20 pages clean, ~11s/page
warm, one sticky US residential IP, zero degradation):

- **patchright** — anti-detect Playwright fork (`navigator.webdriver=false`,
  `Runtime.enable` CDP leak patched). `uv pip install patchright && patchright install chromium`.
- `launch_persistent_context(headless=False, args=["--headless=new"])` → real
  GPU/ANGLE render (verified RTX 3090 D3D11, **not** SwiftShader). Needs a real-GPU host.
- **`user_agent` = a real Chrome UA** — **THE fix.** New-headless leaks `HeadlessChrome`
  in `navigator.userAgent`; that single tell was why every prior browser attempt failed.
- **US residential sticky proxy.** Decodo: `user-<sub>-country-us-session-<id>@gate.decodo.com:7000`
  (the port-based `:10001` cred handed out random-geo Spain → flagged).
- **Navigate once per URL**, then poll the in-page `fetch()` until `_abck` mints;
  **nav_timeout ≥45 s** (residential is slow; 25 s times out the cold solve). Cold
  ~45–80 s, warm ~11 s (the cookie is reused across pages in the same browser).

**This corrects the sections below.** The datacenter finding stands (§4/§7 —
ProxyBonanza is datacenter, ASN-confirmed), but the remedy is **not** a managed
browser or a paid sensor API. Ruled out en route: datacenter proxies (403), vanilla
Playwright new-headless (challenge — `webdriver=true`), `curl_cffi` fingerprint-only
`chrome146` (2310-byte challenge — the site REQUIRES JS-sensor execution, so JA3Proxy
and the OSS "fingerprint-only HTTP client" class can't work either), and OSS sensor
generators (none is a working/safe/maintained Python web generator).

**Cost:** ~$9–45 per 6300-game season (patchright free + residential ~$3/GB).
Tooling: `python/ncaa_mbb_98_canary_probe.py` (`proxy_patchright` vendor). **Production TODO:**
fold this transport into sdv-py's fetch layer (replace `mbb_ncaa_fetch._PlaywrightTransport`).

---

## 1. The access model

Two page classes, and they behave completely differently:

| Class | Pages | Transport |
|---|---|---|
| Un-challenged | `/`, `/team/{id}`, `/season_divisions` (~10–20 KB) | `curl_cffi` (Chrome impersonation) works |
| **Game detail** | `.../play_by_play`, `.../box_score`, `.../individual_stats` | Akamai **bm-verify** JS proof-of-work. `curl_cffi` **cannot** clear it — needs the Playwright browser |

`curl_cffi` clears the TLS/JA3 edge but cannot run the sensor. Game detail requires
`NcaaFetcher.with_browser()` (Chromium, `--headless=new` — old headless's SwiftShader
WebGL renderer is an Akamai tell).

## 2. Response classes — the classification that broke us

There are **four**, not two. Misreading this caused the entire outage:

| Class | Shape | Detect via |
|---|---|---|
| Real content | **100 KB+** (pbp 135–144 KB, box 285–319 KB, individual_stats 219–228 KB) | size + `<tr>` count |
| Ban | HTTP **403**, ~413 B, `Access Denied` | status + ban marker |
| Unsolved — **navigation** | ~2310 B interstitial carrying `bm-verify` / `_abck` | markers |
| Unsolved — **in-page XHR** | **THIN stub**, no markers, no ban text | **size only** |

**The asymmetry that hides the bug:** Akamai answers a *navigation* with the full
marker-bearing interstitial (what `curl_cffi` sees, cookie-less), but answers an
*in-page `fetch()`* carrying an invalid `_abck` with a thin stub.

**The stub size VARIES** — observed at **15 bytes** (`NCAA Statistics`) and **411 bytes**
in the same session. Never match its signature; use a size floor. No real
stats.ncaa.org page is under 1 KB.

Why it slipped through: the stub is HTTP **200** with **no ban marker**, so
`_ban_check` calls it `"clean"`. The fetch layer returned it as a *successful fetch*.
Callers rejected it as too-small and logged `"challenge not cleared"` — while the
fetcher, believing it had succeeded, never re-solved and never rotated.

> ⚠️ `ncaa_mbb_02_games_scrape`'s `"challenge not cleared"` warning is emitted for **any** page
> failing `_is_clean`. It is not evidence of a challenge. It misled a whole
> debugging session. Do not trust that log line — inspect the actual bytes.

## 3. Bugs found and fixed (all merged 2026-07-16)

| # | Bug | Consequence | Fixed in |
|---|---|---|---|
| 1 | `_ensure_page` early-returned if a page existed; **Playwright binds the proxy at launch** | Browser egressed from its FIRST proxy forever while `_proxy_idx` "rotated" to no effect. One IP absorbed a whole run | sdv-py #264 |
| 2 | `_solve_challenge` set `_challenge_solved = True` after a **blind wait**, never verifying | A failed solve latched "solved"; every later fetch returned unsolved responses **forever** (1485 in one run) — the storm that earned the ban | sdv-py #266 |
| 3 | Unsolved responses classified as success (see §2) | Fetcher never rotated off a non-solving IP | sdv-py #266 |
| 4 | Rotation only on failure — i.e. **after** the IP was already dead | No way to retire an IP while healthy | sdv-py #264 (`rotate_every`, default 200) |
| 5 | Rotation cycled back into known-banned proxies | Re-earned 403s | sdv-py #264 (`_dead` set) |
| 6 | No breaker on a failure storm | Hammered **1262 failures in one hour**, zero yield | raw #1 (`max_consecutive_failures`, default 25) |
| 7 | Launchers ended with `echo "EXIT=..."` → **always exited 0** | Backfill reported "DONE ✓" on a ban | raw #1 (`exit "${rc}"`) |
| 8 | `inf` accepted for `SDV_PY_NCAA_ROTATION_BACKOFF` → `time.sleep` OverflowError | — | sdv-py #264 (`math.isfinite`) |
| 9 | No chunking | Couldn't bound a session | raw #1 (`--max-contests`) |

## 4. Measured behavior

**Capture rate (healthy):** ~1200 bundles/hr, 1 worker, ~20/min. Real payloads
135–319 KB/page.

**IP lifetime — the numbers collapsed between runs:**

| Date | IP | Volume before it stopped solving | Subnet outcome |
|---|---|---|---|
| 2026-07-13 | `31.14.9.13` | **~1412 bundles / ~4236 requests** (70 min) | subnet mostly survived (24/25 healthy) |
| 2026-07-16 | `23.239.174.2` | **~35 bundles / ~105 requests** (3 min) | **entire /24 → 403** |
| 2026-07-16 | `154.81.58.x` | ~20 bundles | stopped solving (411 B stubs), incl. untouched IPs w/ fresh browsers |

A ~40× collapse in tolerance with no code change on their side. **Cause not
established** — see Open questions.

> **This falsifies the 2026-07-13 rate-probe conclusion.** That probe concluded
> "paced requests are SAFE; the ban was a BURST artifact, not a volume limit" and
> budgeted a season at ~6h on 1 worker / ~50 req/min. On 2026-07-16 a single
> self-paced worker at ~20/min stopped solving after **35 games**. Volume/duration
> on one IP matters after all — or something changed on their side between the two
> dates. The probe's *concurrency* finding (1–2 workers OK, 4 = ban) is untouched;
> its *"spacing doesn't matter, just go"* conclusion is not safe to rely on.

**Do bans lift?** No evidence they do. 26/50 of one pool still 403 after **62 hours**;
`23.239.174.x` still 403 after ~1 hour. Treat IPs as **consumable**.

**Concurrency:** the ProxyBonanza pool refuses ~**10 concurrent** connections
(`ProxyError` storm). **Serial is flawless.** Earlier finding: 1–2 browser workers
safe, 4 = ban.

## 5. Operational rules

1. **ProxyBonanza IPs only — NEVER the residential IP.** (Binding user directive.)
   The home IP cannot be rotated; given bans don't appear to lift, it's the one
   asset you can't replace. The fetcher is proxy-bound by design: no direct-fetch mode.
2. **Canary before scale.** Run `CHUNK=10` and confirm clean captures *before*
   `CHUNK=1500`. A 1500-chunk launched with no canary burned a subnet in 3 minutes.
3. **WORKERS 1–2 max.** Never 4.
4. **Resume is free** — `is_captured` is file-exists based, so re-running skips
   captured contests. Ctrl-C is always safe.
   - Note: `schedule_master`'s `captured` column is **vestigial** (always `False`);
     resume is purely file-exists.
5. **Pull sdv-py main before running.** The launchers import sportsdataverse from the
   **working tree** via `PYTHONPATH="${SDV_PY}:${ROOT}/python"` — *not* a version pin.
   If that checkout sits on someone's feature branch, the backfill silently runs old
   code. This nearly re-ran the IP-burning version.
6. **Raw data IS committed** (the plan mandates it; the `-data` ingest reads
   `raw.githubusercontent.com/.../main/mbb/json/{cid}.json`). Do **not** gitignore
   `mbb/`. `.gitattributes` marks `.json.gz` binary — verified: 25/25 bundles read
   back out of git pass `gzip -t`.

## 6. Data facts (season 2026)

- **6300** contests discovered; **2457** captured, 2437 parsed + published.
- Per game: pbp 400–540 rows, lineups 34–58, player_box 16–24, team_box 2,
  shots 104–177, possessions 133–198.
- ~**3.3%** of games have empty lineups+shots (individual_stats page failure) —
  parser swallows per-family, so the game still lands.
- Sizes: bundle ~52 KB gzipped, parsed json ~850 KB. **JSON compresses 20.8:1**, so
  2.0 GB of json is only **~98 MB** in git (222 MB total repo).
- End-to-end verified: `ingest.read_parsed` pulls a published game over HTTP and
  returns the full 7-key dict.

## 7. Open questions — resolve before buying proxies

1. **Can these IPs sustain this at all?** Fresh IPs solved for only 20–35 games before
   stopping. The fetch layer's docstring warns **"datacenter IPs defeat bm-verify"**,
   which *would* explain it — **but the pool type is UNVERIFIED**. The 2026-07-13
   rate-probe notes describe the pool as **residential** ("Residential ProxyBonanza
   pool size = 50"). If it is already residential, "buy residential" is the wrong
   remedy and the real cause is elsewhere. **Confirm the ProxyBonanza package type
   (and ASN-check a live IP) before spending anything.** Do not repeat the
   datacenter assumption without evidence — it was asserted in this session without
   being checked.
2. **Ban vs. can't-solve.** Not established whether the 403s are true per-IP/subnet
   bans, the whole provider ASN being flagged after our 07-13 storm, or bm-verify
   simply failing on datacenter IPs. These imply different remedies. The 07-13 →
   07-16 collapse is consistent with the ASN being flagged.
3. **Does anything decay?** Every check so far says no, but the longest observation is
   62 hours. Worth one cheap probe before assuming permanence.

## 8. Debugging lessons (process)

- **The failure message lied.** `"challenge not cleared"` is emitted for any not-clean
  page. Three successive diagnoses were wrong because they trusted it instead of the
  bytes. **Dump the actual response** (status, length, first 300 chars) first.
- **Don't state a hypothesis as a conclusion.** "Subnet ban" was asserted on
  circumstantial evidence and was probably wrong; the challenge-not-passing read fit
  better and came from the user.
- **Canary before scale**, and **fail fast** — the fixed code now raises loudly rather
  than grinding, which makes a canary cheap.
- **Exit codes**: a trailing `echo` makes a shell script exit 0. It masked a ban as
  success in the launchers, and then again in an ad-hoc `cmd; echo "EXIT=$?"` wrapper.

## 9. Current state (2026-07-16)

- **2457/6300** captured; published on `main` (222 MB, uncorrupted, HTTP-readable).
- All 9 fixes merged and live in the tree the scraper imports (sdv-py `main`).
- **Blocked on IP supply, not software.** Both subnets of the current pool are
  unusable (`23.239.174.x` → 403; `154.81.58.x` → won't solve).
- Next: provision fresh IPs → `CHUNK=10` canary → if clean, `CHUNK=1500` (≈3 sessions
  for the remaining 3843).
