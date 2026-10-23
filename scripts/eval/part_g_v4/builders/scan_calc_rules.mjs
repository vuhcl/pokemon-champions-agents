// Scan the vendored @smogon/calc (Champions = Generations.get(0)) for the places where its damage
// calculation departs from the plain type chart or from the legality blob. Prints JSON on stdout.
// Run via extract_calc_rules.py; the result is committed as key_artifacts/calc_move_rules.v1.json.
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..', '..', '..');
const require = createRequire(path.join(root, 'vendor', 'smogon-calc', 'package.json'));
const c = require('./dist/index.js');
const u = require('./dist/mechanics/util.js');
const leg = JSON.parse(fs.readFileSync(path.join(root, 'data/legality/champions.v1.json')));
const st = JSON.parse(fs.readFileSync(path.join(root, 'data/moves/static.v1.json'))).moves;
const gen = c.Generations.get(0);
const TYPES = ['Normal','Fire','Water','Electric','Grass','Ice','Fighting','Poison','Ground','Flying','Psychic','Bug','Rock','Ghost','Dragon','Dark','Steel','Fairy'];
const legal = Object.keys(leg.species).filter((k) => leg.species[k].is_nonstandard === null).sort();
const moveIds = Object.keys(st).sort();
const abilitiesOf = (sid) => Object.values(leg.species[sid].abilities).filter(Boolean);

// 1. Move rules: calc effectiveness vs the plain chart (no Scrappy, no Gravity).
const moveExceptions = {};
const dexGaps = {moves: [], species: []};
for (const id of moveIds) {
  const L = leg.moves[id];
  const m = new c.Move(gen, L.name);
  if (m.type !== L.type || (m.bp || 0) !== L.basePower || m.category !== L.category) {
    dexGaps.moves.push({id, name: L.name, legality: [L.type, L.basePower, L.category], calc: [m.type ?? null, m.bp ?? null, m.category]});
  }
  if (!m.type || m.type === '???') continue;
  for (const t of TYPES) {
    const plain = gen.types.get(c.toID(m.type)).effectiveness[t];
    const e = u.getMoveEffectiveness(gen, m, t, false, false, false);
    if (e !== plain) (moveExceptions[L.name] = moveExceptions[L.name] || {})[t] = e;
  }
}

// 2. Attacker abilities that reveal Ghost (Normal move into a Ghost-type that would otherwise be immune).
const ghostProbe = new c.Pokemon(gen, 'Froslass', {level: 50, nature: 'Hardy', ability: 'Snow Cloak', evs: {hp: 32}});
const ghostReveal = new Set();
const calcSpeciesOk = [];
for (const sid of legal) {
  const sp = leg.species[sid];
  let ok = true;
  for (const ab of abilitiesOf(sid)) {
    let atk;
    try { atk = new c.Pokemon(gen, sp.name, {level: 50, nature: 'Adamant', ability: ab, evs: {atk: 32}}); } catch (e) { ok = false; break; }
    const r = c.calculate(gen, atk, ghostProbe, new c.Move(gen, 'Close Combat'));
    const d = r.damage;
    const pos = Array.isArray(d) ? d.some((x) => (Array.isArray(x) ? x.some((y) => y > 0) : x > 0)) : d > 0;
    if (pos) ghostReveal.add(ab);
  }
  if (!ok) dexGaps.species.push(sid); else calcSpeciesOk.push(sid);
}

// 3. Attacker abilities / forms that change the final move type.
const refDef = new c.Pokemon(gen, 'Garchomp', {level: 50, nature: 'Hardy', ability: 'Rough Skin', evs: {hp: 32}});
const typeChanges = {};
const damaging = moveIds.filter((m) => leg.moves[m].category !== 'Status');
for (const sid of calcSpeciesOk) {
  const sp = leg.species[sid];
  for (const ab of abilitiesOf(sid)) {
    const atk = new c.Pokemon(gen, sp.name, {level: 50, nature: 'Adamant', ability: ab, evs: {atk: 32, spa: 32}});
    for (const m of damaging) {
      const mv = new c.Move(gen, leg.moves[m].name);
      const t = c.calculate(gen, atk, refDef, mv).move.type;
      if (t && t !== '???' && t !== leg.moves[m].type) typeChanges[`${sid}|${ab}|${m}`] = t;
    }
  }
}

// 4. Defender abilities with no effect on the rolls for any probe (the calc does not model them).
const probes = [['Body Slam', 'Adamant', 'atk'], ['Earthquake', 'Adamant', 'atk'], ['Surf', 'Modest', 'spa'], ['Flamethrower', 'Modest', 'spa'], ['Thunderbolt', 'Modest', 'spa'], ['Energy Ball', 'Modest', 'spa'], ['Psychic', 'Modest', 'spa'], ['Close Combat', 'Adamant', 'atk'], ['Aerial Ace', 'Adamant', 'atk'], ['Dragon Claw', 'Adamant', 'atk']];
const bigAtk = (nat, key) => new c.Pokemon(gen, 'Garchomp', {level: 50, nature: nat, ability: 'Rough Skin', evs: {[key]: 32}});
const defAbilities = new Set();
for (const sid of legal) for (const ab of abilitiesOf(sid)) defAbilities.add(ab);
const affects = {};
for (const ab of [...defAbilities].sort()) {
  let changed = false;
  for (const sid of ['skarmory', 'arcanine', 'milotic', 'dragonite', 'froslass', 'gyarados']) {
    for (const [mn, nat, key] of probes) {
      const mk = () => new c.Move(gen, mn);
      const a = bigAtk(nat, key);
      const base = new c.Pokemon(gen, leg.species[sid].name, {level: 50, nature: 'Hardy', ability: 'Pressure', evs: {hp: 32}});
      const test = new c.Pokemon(gen, leg.species[sid].name, {level: 50, nature: 'Hardy', ability: ab, evs: {hp: 32}});
      const r1 = JSON.stringify(c.calculate(gen, a, base, mk()).damage);
      const r2 = JSON.stringify(c.calculate(gen, a, test, mk()).damage);
      if (r1 !== r2) { changed = true; break; }
    }
    if (changed) break;
  }
  affects[ab] = changed;
}
const noEffect = Object.keys(affects).filter((a) => !affects[a]);

const out = {
  schema: 'part_g_v4_calc_move_rules',
  calc_version: JSON.parse(fs.readFileSync(path.join(root, 'vendor/smogon-calc/package.json'))).version,
  generation: 'Generations.get(0) (Champions)',
  move_effectiveness_exceptions: moveExceptions,
  ghost_revealing_abilities: [...ghostReveal].sort(),
  type_changes: typeChanges,
  calc_dex_gaps: {moves: dexGaps.moves, species: dexGaps.species},
  defender_abilities_without_effect_on_probe_rolls: noEffect,
  probe_note: 'a defender ability is listed when its rolls equal the inert-ability rolls for every probe (6 defenders x 10 moves)',
};
const sortKeys = (o) => (Array.isArray(o) ? o.map(sortKeys) : o && typeof o === 'object' ? Object.fromEntries(Object.keys(o).sort().map((k) => [k, sortKeys(o[k])])) : o);
console.log(JSON.stringify(sortKeys(out)));
