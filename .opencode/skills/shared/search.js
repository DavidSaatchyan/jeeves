#!/usr/bin/env node
const path = require('path');
const { SkillEngine } = require('./engine.js');

const args = process.argv.slice(2);
const queryIndex = args.findIndex(a => !a.startsWith('--'));
const query = queryIndex >= 0 ? args[queryIndex] : '';
const flags = {};
const shortFlags = { '-p': 'project', '-n': 'limit', '-f': 'format', '-s': 'skill' };
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith('--')) {
    const key = args[i].slice(2);
    const val = (i + 1 < args.length && !args[i + 1].startsWith('--')) ? args[i + 1] : true;
    flags[key] = val;
  } else if (shortFlags[args[i]]) {
    const key = shortFlags[args[i]];
    const val = (i + 1 < args.length && !args[i + 1].startsWith('--') && !args[i + 1].startsWith('-')) ? args[i + 1] : true;
    flags[key] = val;
  }
}

const skillName = flags.skill || 'ux-designer';
const domain = flags.domain || null;
const designSystem = flags['design-system'] || false;
const limit = parseInt(flags.limit) || 5;
const format = flags.format || 'ascii';
const projectName = flags.p || flags.project || 'Untitled';

const skillDir = path.join(__dirname, '..', skillName);
const engine = new SkillEngine(skillDir);

if (designSystem) {
  const ds = engine.designSystem(query, projectName);
  if (format === 'json') {
    console.log(JSON.stringify(ds, null, 2));
  } else {
    console.log(`+----------------------------------------------------------------------------------------+`);
    console.log(`|  PROJECT: ${ds.project.padEnd(74)}|`);
    console.log(`+----------------------------------------------------------------------------------------+`);
    console.log(`|  PATTERN: ${ds.pattern.padEnd(64)}|`);
    console.log(`|  Product Type: ${ds.productType.padEnd(60)}|`);
    console.log(`|                                                                                        |`);
    console.log(`|  STYLE: ${(ds.style.name || '').padEnd(67)}|`);
    console.log(`|  ${(ds.style.description || '').padEnd(87)}|`);
    console.log(`|                                                                                        |`);
    if (ds.colors) {
      console.log(`|  COLORS:`);
      console.log(`|     Primary:    ${(ds.colors.primary || '').padEnd(68)}|`);
      console.log(`|     Secondary:  ${(ds.colors.secondary || '').padEnd(68)}|`);
      console.log(`|     Background: ${(ds.colors.background || '').padEnd(68)}|`);
      console.log(`|     Text:       ${(ds.colors.text || '').padEnd(68)}|`);
    }
    console.log(`|                                                                                        |`);
    if (ds.typography) {
      console.log(`|  TYPOGRAPHY: ${(ds.typography.headings || '')} / ${(ds.typography.body || '')}`);
      console.log(`|  Mood: ${(ds.typography.mood || '').padEnd(80)}`);
      if (ds.typography.import) console.log(`|  Google Fonts: ${ds.typography.import}`);
    }
    console.log(`|                                                                                        |`);
    console.log(`|  KEY EFFECTS: ${(ds.effects || '').padEnd(66)}|`);
    console.log(`|                                                                                        |`);
    console.log(`|  AVOID (Anti-patterns):`);
    (ds.antiPatterns || []).forEach(ap => {
      console.log(`|     - ${ap.padEnd(72)}|`);
    });
    console.log(`|                                                                                        |`);
    console.log(`|  PRE-DELIVERY CHECKLIST:`);
    (ds.checklist || []).forEach((item, i) => {
      console.log(`|     [${i+1}] ${item.padEnd(68)}|`);
    });
    console.log(`+----------------------------------------------------------------------------------------+`);
  }
} else if (domain) {
  const results = engine.search(domain, query, { limit });
  if (format === 'json') {
    console.log(JSON.stringify(results, null, 2));
  } else {
    results.forEach((r, i) => {
      console.log(`\n${'='.repeat(70)}`);
      console.log(`Result ${i + 1} (score: ${r._score.toFixed(2)})`);
      console.log(`Name: ${r.name}`);
      if (r.description) console.log(`Description: ${r.description}`);
      if (r.bestFor) console.log(`Best For: ${r.bestFor}`);
      if (r.tags) console.log(`Tags: ${r.tags}`);
      if (r.dos) console.log(`Do: ${r.dos}`);
      if (r.donts) console.log(`Don't: ${r.donts}`);
      if (r.priority) console.log(`Priority: ${r.priority}`);
    });
  }
} else {
  console.log('Usage:');
  console.log('  node search.js "<query>" --design-system [-p "Project"]');
  console.log('  node search.js "<query>" --domain <domain> [--limit N]');
  console.log('  Domains: styles, colors, fonts, ux-rules, products, charts');
  console.log('  Flags: --skill <name> --format json|ascii --project "Name"');
}
