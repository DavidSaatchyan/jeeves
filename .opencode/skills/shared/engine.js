const fs = require('fs');
const path = require('path');

class SkillEngine {
  constructor(skillDir) {
    this.skillDir = skillDir;
    this.data = {};
  }

  load(name) {
    const filePath = path.join(this.skillDir, 'data', `${name}.json`);
    if (!fs.existsSync(filePath)) return [];
    const raw = fs.readFileSync(filePath, 'utf-8');
    this.data[name] = JSON.parse(raw);
    return this.data[name];
  }

  get(name) {
    return this.data[name] || this.load(name);
  }

  search(domain, query, options = {}) {
    const records = this.get(domain);
    if (!records || !records.length) return [];
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    const scored = records.map(r => ({
      ...r,
      _score: this._score(r, tokens, options)
    })).filter(r => r._score > 0);
    scored.sort((a, b) => b._score - a._score);
    const limit = options.limit || 5;
    return scored.slice(0, limit);
  }

  _score(record, tokens, options) {
    const fields = options.fields || ['name', 'description', 'keywords', 'tags', 'bestFor', 'category'];
    let score = 0;
    const text = fields.map(f => (record[f] || '').toLowerCase()).join(' ');
    for (const token of tokens) {
      if (text.includes(token)) score += 1;
      if (text.startsWith(token)) score += 0.5;
      if (new RegExp(`\\b${token}\\b`).test(text)) score += 2;
      const count = (text.match(new RegExp(token, 'g')) || []).length;
      score += count * 0.3;
    }
    if (record.priority) {
      const pMap = { critical: 5, high: 3, medium: 2, low: 1 };
      score += (pMap[record.priority] || 0) * 0.5;
    }
    return score;
  }

  designSystem(productType, projectName, options = {}) {
    const products = this.get('products');
    const styles = this.get('styles');
    const colors = this.get('colors');
    const fonts = this.get('fonts');

    const tokens = productType.toLowerCase().split(/\s+/).filter(Boolean);

    let bestProduct = null;
    let bestScore = 0;
    for (const p of products) {
      const s = this._score(p, tokens, { fields: ['name', 'description', 'keywords', 'industry'] });
      if (s > bestScore) { bestScore = s; bestProduct = p; }
    }

    const product = bestProduct || { name: 'General', pattern: 'Hero-Centric', style: 'Minimalism', color: 'Professional', font: 'Inter', effects: 'Clean transitions', antiPatterns: ['Overdesign'] };

    const styleTokens = (product.style || '').toLowerCase().split(/\s+/);
    const bestStyle = styles ? this.search('styles', styleTokens.join(' '), { limit: 1 })[0] : null;

    const colorTokens = (product.colorMood || product.name || '').toLowerCase().split(/\s+/);
    const bestColor = colors ? this.search('colors', colorTokens.join(' '), { limit: 1 })[0] : null;

    const fontTokens = (product.fontMood || product.name || '').toLowerCase().split(/\s+/);
    const bestFont = fonts ? this.search('fonts', fontTokens.join(' '), { limit: 1 })[0] : null;

    return {
      project: projectName || 'Untitled',
      productType: product.name,
      pattern: product.pattern || 'Hero-Centric',
      style: bestStyle ? { name: bestStyle.name, description: bestStyle.description } : { name: product.style, description: '' },
      colors: bestColor ? { palette: bestColor.palette, primary: bestColor.primary, secondary: bestColor.secondary, background: bestColor.background, text: bestColor.text } : null,
      typography: bestFont ? { headings: bestFont.headings, body: bestFont.body, mood: bestFont.mood, import: bestFont.import } : null,
      effects: product.effects || 'Soft shadows, smooth transitions (200-300ms), subtle hover states',
      antiPatterns: product.antiPatterns || ['Cluttered layouts', 'Inconsistent spacing'],
      checklist: [
        'No emojis as icons (use SVG: Heroicons/Lucide)',
        'cursor-pointer on all clickable elements',
        'Hover states with smooth transitions (150-300ms)',
        'Light mode: text contrast 4.5:1 minimum',
        'Focus states visible for keyboard nav',
        'prefers-reduced-motion respected',
        'Responsive: 375px, 768px, 1024px, 1440px'
      ]
    };
  }
}

module.exports = { SkillEngine };
