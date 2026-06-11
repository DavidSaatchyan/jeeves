#!/usr/bin/env node
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const pkg = { name: 'openflo-skill', version: '2.0.0' };
const SKILLS_DIR = path.join(__dirname, '..', '.opencode', 'skills');
const SHARED_DIR = path.join(SKILLS_DIR, 'shared');

const SKILL_LIST = [
  'architecture-designer', 'backend-developer', 'consensus', 'devops-engineer',
  'federation', 'frontend-developer', 'goal-planning', 'memory',
  'observability', 'security-engineer', 'self-learning', 'swarm',
  'test-master', 'ux-designer', 'web-ui', 'workers'
];

const args = process.argv.slice(2);
const cmd = args[0];

function help() {
  console.log(`
openflo-skill v${pkg.version} — OpenFlo Skill Manager

Commands:
  init <project-dir> [--ai opencode|all]   Install skills into project
  list                                      List available skills
  search <query> --domain <domain>          Search skill data
  design <query> -p <project>               Generate design system
  version                                   Show version

Search domains: styles, colors, fonts, products, ux-rules, charts

Examples:
  openflo-skill init ./my-project
  openflo-skill search "glassmorphism dark" --domain styles
  openflo-skill design "fintech crypto" -p MyApp
`);
}

function init(projectDir, ai) {
  if (!projectDir || projectDir === '--ai') {
    console.error('Error: specify project directory');
    console.log('  openflo-skill init <project-dir>');
    process.exit(1);
  }

  const targetDir = path.resolve(projectDir);
  if (!fs.existsSync(targetDir)) {
    console.error(`Error: directory not found: ${targetDir}`);
    process.exit(1);
  }

  const targetSkillsDir = path.join(targetDir, '.opencode', 'skills');
  const targetSharedDir = path.join(targetSkillsDir, 'shared');

  console.log(`Installing OpenFlo skills into ${targetDir}...`);

  fs.mkdirSync(targetSharedDir, { recursive: true });

  // Copy shared engine
  const sharedFiles = ['engine.js', 'search.js'];
  for (const file of sharedFiles) {
    const src = path.join(SHARED_DIR, file);
    const dest = path.join(targetSharedDir, file);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, dest);
      console.log(`  ✓ shared/${file}`);
    }
  }

  // Copy individual skills
  for (const skill of SKILL_LIST) {
    const srcSkillDir = path.join(SKILLS_DIR, skill);
    const destSkillDir = path.join(targetSkillsDir, skill);

    if (!fs.existsSync(srcSkillDir)) {
      console.log(`  - ${skill}: source not found, skipping`);
      continue;
    }

    const copyDirRecursive = (src, dest) => {
      fs.mkdirSync(dest, { recursive: true });
      const entries = fs.readdirSync(src, { withFileTypes: true });
      for (const entry of entries) {
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);
        if (entry.isDirectory()) {
          copyDirRecursive(srcPath, destPath);
        } else {
          fs.copyFileSync(srcPath, destPath);
        }
      }
    };

    copyDirRecursive(srcSkillDir, destSkillDir);
    console.log(`  ✓ ${skill}/`);
  }

  console.log('\nDone! Skills installed.');
  console.log(`\nNext steps:`);
  console.log(`  cd ${projectDir}`);
  console.log(`  opencode`);
  console.log(`  /agents list`);
}

function list() {
  console.log(`OpenFlo Skills (v${pkg.version}):\n`);
  const widths = [25, 10, 45];
  console.log(`${'SKILL'.padEnd(widths[0])} ${'LINES'.padEnd(widths[1])} ${'DESCRIPTION'.padEnd(widths[2])}`);
  console.log('-'.repeat(80));

  for (const skill of SKILL_LIST) {
    const skillPath = path.join(SKILLS_DIR, skill, 'SKILL.md');
    if (!fs.existsSync(skillPath)) continue;
    const content = fs.readFileSync(skillPath, 'utf-8');
    const lines = content.split('\n').length;
    const descMatch = content.match(/description:\s*"([^"]+)"/) || content.match(/description:\s*'([^']+)'/);
    const desc = descMatch ? descMatch[1].slice(0, 42) + '...' : '';
    console.log(`${skill.padEnd(widths[0])} ${String(lines).padEnd(widths[1])} ${desc}`);
  }
}

function main() {
  switch (cmd) {
    case 'init':
      const aiIdx = args.indexOf('--ai');
      const ai = aiIdx >= 0 ? args[aiIdx + 1] : 'opencode';
      const projIdx = aiIdx === 1 ? 3 : 1;
      init(args[projIdx], ai);
      break;
    case 'list':
      list();
      break;
    case 'search':
    case 'design':
      const searchArgs = args.slice(1);
      const searchPath = path.join(SHARED_DIR, 'search.js');
      if (cmd === 'design') searchArgs.push('--design-system');
      execSync(`node "${searchPath}" ${searchArgs.join(' ')}`, { stdio: 'inherit' });
      break;
    case 'version':
      console.log(pkg.version);
      break;
    default:
      help();
  }
}

main();
