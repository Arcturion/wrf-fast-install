# WRF Namelist Builder

Design your domains interactively, pick the physics from dropdowns, and
download a **matched `namelist.wps` + `namelist.input` pair** that agree
with each other — same `max_dom`, `e_we`/`e_sn`, ratios and parent starts
in both files, which is where most hand-editing mistakes live.

## Use it

Open `index.html` in any browser. That is all — a single self-contained
file, no server, no build step, no upload: everything runs locally in the
page, so it also works offline and inside restricted networks.

1. **Projection & parent domain** — lambert / mercator / lat-lon / polar,
   reference point, true latitudes, parent dx.
2. **Domains** — add nests, set each nest's parent, ratio (2–5) and centre
   lat/lon, or **drag the nest on the preview map**. Grid sizes snap
   automatically so `(e_we − 1)` and `(e_sn − 1)` stay divisible by the
   ratio, as WRF requires. The preview shows the domains on a graticule
   in projected space, with centre and corner lat/lon per domain.
3. **Run & WPS settings** — start/end, input-data interval, geography
   path, vertical levels, metgrid levels, time step, history interval.
4. **Physics** — one dropdown per scheme family per domain
   (microphysics, cumulus, longwave, shortwave, boundary layer, surface
   layer, land surface), each entry named with its WRF option number.
   The **NCAR CONUS** and **NCAR tropical** suite buttons fill every
   dropdown at once, per the WRF Users Guide; individual schemes can be
   overridden afterwards. `radt` is set from each domain's dx and
   `num_soil_layers` follows the chosen land surface model.
5. **Checks** — live warnings before you export: a nest escaping its
   parent or sitting inside the boundary relaxation margin, cumulus left
   on for a convection-permitting nest (< 4 km), PBL/surface-layer
   pairings that normally clash (MYJ, ACM2, YSU), a time step far from
   the ~6 s per km guideline, and a run length that is not a whole number
   of input intervals. Errors block the download buttons.

## Companion tool

`../../utils/plot_domains.py` does the reverse trip: it plots the domains
of an *existing* `namelist.wps` so you can check a file someone sent you.
Both use the same spherical-earth projection maths (R = 6370 km, the WRF
value); the builder's southern-hemisphere Lambert handling mirrors the
fix in the Python tool.

## Scope and limits

- Positions are setup-grade, for designing and checking domains —
  `geogrid.exe` remains the authority.
- The physics dropdowns list the commonly used schemes with their WRF
  numbers, following the WRF Users Guide; exotic options can still be
  typed into the downloaded files by hand.
- The builder *creates* namelists. Importing and editing an existing
  namelist is not supported (yet).

## Tests

The page's core logic (projections, domain computation, snapping,
validation, namelist generation) is DOM-free and unit-tested headlessly:

```bash
node tests/test_builder.mjs
```

30 checks, including: forward/inverse round-trips for every projection
(both hemispheres), the WRF tutorial's own nested case (the builder must
return `i_parent_start = 1, 36`, `j_parent_start = 1, 32` for it), suite
values against the Users Guide, and each validation rule firing on a
deliberately broken setup.
