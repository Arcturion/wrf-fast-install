#!/usr/bin/env node
/* Planted-truth tests for the namelist builder core logic.
 *
 * Extracts the DOM-free <script id="core"> block from index.html, evaluates
 * it in a vm context, and checks the domain maths, the physics suites, the
 * validation warnings and the generated namelists against known values —
 * including the WRF tutorial's own nested-domain case.
 *
 * Run:  node tests/test_builder.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "..", "index.html"), "utf8");
const m = html.match(/<script id="core">([\s\S]*?)<\/script>/);
if (!m) { console.error("core script block not found"); process.exit(1); }
const ctx = vm.createContext({});
vm.runInContext(m[1] + `\n;globalThis.__x = { defaultState, makeProjection,
  computeDomains, snapDim, PHYS, SUITES, validate, generateWPS, generateInput };`, ctx);
const { defaultState, makeProjection, computeDomains, snapDim, PHYS, SUITES,
        validate, generateWPS, generateInput } = ctx.__x;

let pass = 0, fail = 0;
function check(name, ok, detail = "") {
  if (ok) { pass++; console.log(`PASS  ${name}  ${detail}`); }
  else { fail++; console.log(`FAIL  ${name}  ${detail}`); }
}
const approx = (a, b, tol) => Math.abs(a - b) <= tol;

/* ---------- snapDim ---------- */
check("snapDim keeps valid sizes", snapDim(118, 3) === 118 && snapDim(100, 3) === 100);
check("snapDim snaps to nearest valid", snapDim(101, 3) === 100 && snapDim(102, 3) === 103,
      `101->${snapDim(101, 3)}, 102->${snapDim(102, 3)}`);
check("snapDim enforces a minimum", snapDim(1, 3) >= 4);

/* ---------- projection roundtrips ---------- */
function roundtrip(projCfg, lat, lon) {
  const p = makeProjection(projCfg);
  const [x, y] = p.forward(lat, lon);
  const [la, lo] = p.inverse(x, y);
  return approx(la, lat, 1e-6) && approx(lo, lon, 1e-6);
}
check("lambert roundtrip (northern)",
  roundtrip({ proj: "lambert", refLat: 39, refLon: -97, truelat1: 30, truelat2: 45, standLon: -97 }, 41.2, -95.3));
check("lambert roundtrip (southern, mirrored)",
  roundtrip({ proj: "lambert", refLat: -6.5, refLon: 107, truelat1: -10, truelat2: -20, standLon: 107 }, -7.3, 108.1));
check("mercator roundtrip",
  roundtrip({ proj: "mercator", refLat: -6, refLon: 107 }, -8.1, 110.4));
check("polar roundtrip (northern)",
  roundtrip({ proj: "polar", refLat: 70, refLon: 0, truelat1: 60, standLon: 0 }, 72.5, 20.0));
check("polar roundtrip (southern)",
  roundtrip({ proj: "polar", refLat: -75, refLon: 40, truelat1: -70, standLon: 40 }, -72.0, 55.0));

/* ---------- default state computes cleanly ---------- */
{
  const s = defaultState();
  const c = computeDomains(s);
  const v = validate(s, c);
  check("default state: nest dx = 3000 m", c.domains[1].dx === 3000);
  check("default state: nest inside parent (no errors)", v.errors.length === 0,
        v.errors.join("; "));
  check("default state: d01 centre is the reference point",
        approx(c.domains[0].centre[0], s.refLat, 0.02) &&
        approx(c.domains[0].centre[1], s.refLon, 0.02),
        c.domains[0].centre.map(v => v.toFixed(3)).join(", "));
  check("default state: cu warning fires for 3 km nest with cumulus on",
        v.warnings.some(w => w.includes("cumulus")), v.warnings.join(" | "));
}

/* ---------- WRF tutorial nested case ----------
   namelist.wps from the official tutorial: d01 100x100 @ 30 km,
   d02 118x103, ratio 3, i_parent_start 36, j_parent_start 32.
   Place the nest by the centre those values imply; the builder must
   hand back exactly 36 / 32. */
{
  const s = defaultState();
  s.proj = "lambert"; s.refLat = 39; s.refLon = -97;
  s.truelat1 = 30; s.truelat2 = 45; s.standLon = -97; s.dx = 30000;
  const proj = makeProjection(s);
  // child first point and centre in projected metres, from the tutorial values
  const x0p = -(100 - 2) / 2 * 30000, y0p = -(100 - 2) / 2 * 30000;
  const xf = x0p + (36 - 1) * 30000, yf = y0p + (32 - 1) * 30000;
  const [clat, clon] = proj.inverse(xf + (118 - 2) / 2 * 10000, yf + (103 - 2) / 2 * 10000);
  s.domains = [{ e_we: 100, e_sn: 100 },
               { parent: 0, ratio: 3, centreLat: clat, centreLon: clon, e_we: 118, e_sn: 103 }];
  const c = computeDomains(s);
  check("tutorial case: i_parent_start == 36", c.domains[1].iStart === 36,
        `got ${c.domains[1].iStart}`);
  check("tutorial case: j_parent_start == 32", c.domains[1].jStart === 32,
        `got ${c.domains[1].jStart}`);
  const wps = generateWPS(s, c);
  check("tutorial WPS contains the tutorial values",
        wps.includes("e_we = 100, 118,") && wps.includes("i_parent_start = 1, 36,") &&
        wps.includes("j_parent_start = 1, 32,") && wps.includes("parent_grid_ratio = 1, 3,"),
        "");
  const inp = generateInput(s, c);
  check("tutorial input agrees with WPS (starts, ratios, sizes)",
        inp.includes("i_parent_start = 1, 36,") && inp.includes("j_parent_start = 1, 32,") &&
        inp.includes("parent_time_step_ratio = 1, 3,") &&
        inp.includes("e_we = 100, 118,"));
}

/* ---------- suites match the Users Guide ---------- */
check("tropical suite values", SUITES.tropical.mp === 6 && SUITES.tropical.cu === 16 &&
      SUITES.tropical.pbl === 1 && SUITES.tropical.sfclay === 91 && SUITES.tropical.lsm === 2);
check("CONUS suite values", SUITES.CONUS.mp === 8 && SUITES.CONUS.cu === 6 &&
      SUITES.CONUS.pbl === 2 && SUITES.CONUS.sfclay === 2 && SUITES.CONUS.lsm === 2);
check("catalogue has all 7 families with named options",
      ["mp", "cu", "lw", "sw", "pbl", "sfclay", "lsm"].every(k =>
        PHYS[k] && PHYS[k].options.length >= 5 &&
        PHYS[k].options.every(o => Number.isInteger(o[0]) && o[1].length > 0)));

/* ---------- generated namelist content (default state) ---------- */
{
  const s = defaultState();
  const c = computeDomains(s);
  const wps = generateWPS(s, c), inp = generateInput(s, c);
  check("WPS header values", wps.includes("max_dom = 2,") &&
        wps.includes("map_proj = 'lambert',") && wps.includes("dx = 9000,"));
  check("WPS dates formatted for WPS", wps.includes("start_date = '2024-11-17_00:00:00', '2024-11-17_00:00:00',"));
  check("input physics = tropical suite", inp.includes("mp_physics = 6, 6,") &&
        inp.includes("cu_physics = 16, 16,") && inp.includes("sf_sfclay_physics = 91, 91,"));
  check("input radt follows dx per domain (9, 3)", inp.includes("radt = 9, 3,"));
  check("input soil layers follow Noah LSM (= 4)", inp.includes("num_soil_layers = 4,"));
  check("input time_control dates split out",
        inp.includes("start_year = 2024, 2024,") && inp.includes("start_month = 11, 11,") &&
        inp.includes("end_day = 18, 18,"));
  check("both files end sections with /", wps.trimEnd().endsWith("/") && inp.trimEnd().endsWith("/"));
}

/* ---------- validation catches mistakes ---------- */
{
  const s = defaultState();
  s.domains[1].centreLon = s.refLon + 25;   // drag the nest far away
  const v = validate(s, computeDomains(s));
  check("escaping nest is an error", v.errors.some(e => e.includes("outside its parent")),
        v.errors.join("; "));
}
{
  const s = defaultState();
  s.domains[1].e_we = 100;                   // (100-1) divisible by 3, ok
  s.domains[1].e_we = 101;                   // 100 not divisible by 3
  const v = validate(s, computeDomains(s));
  check("non-divisible nest size is an error",
        v.errors.some(e => e.includes("divisible")), v.errors.join("; "));
}
{
  const s = defaultState();
  s.physics.pbl = [2, 2]; s.physics.sfclay = [1, 1];   // MYJ PBL, MM5 surface layer
  const v = validate(s, computeDomains(s));
  check("MYJ pairing warning fires", v.warnings.some(w => w.includes("MYJ")),
        v.warnings.join(" | "));
}
{
  const s = defaultState();
  s.end = s.start;                            // zero-length run
  const v = validate(s, computeDomains(s));
  check("end before start is an error", v.errors.some(e => e.includes("End time")),
        v.errors.join("; "));
}

console.log(`\n${pass}/${pass + fail} checks passed`);
process.exit(fail ? 1 : 0);
