#!/usr/bin/env node
/**
 * QA Weekly — Automated visual QA cho vn-rates-weekly dashboard
 * Pattern học từ vn-macro-monthly/scripts/qa_report.js
 *
 * Usage:
 *   node qa_weekly.js --url=file:///path/to/report.html
 *   node qa_weekly.js --url=file:///path/to/report.html --output=./qa-shots
 *
 * Checks:
 *   1. Hero + verdict badge + stance gauge
 *   2. NAV 5 tabs (Tiền tệ/Trái phiếu/Ngoại hối&TG/CK&VN/Tổng hợp)
 *   3. Group sections (5, money active default)
 *   4. Data cards with wow-strip
 *   5. Tab switching works
 *   6. Stance gauge needle
 *   7. No JS console errors
 *   8. Screenshots
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function runQA() {
  const args = process.argv.slice(2);
  const urlArg = args.find(a => a.startsWith('--url='));
  const outputArg = args.find(a => a.startsWith('--output='));
  if (!urlArg) {
    console.error('Usage: node qa_weekly.js --url=file:///path/to/report.html');
    process.exit(1);
  }
  const url = urlArg.replace('--url=', '');
  const outDir = outputArg ? outputArg.replace('--output=', '.') : '/tmp/qa-weekly';
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  const results = { pass: [], warn: [], fail: [] };
  const add = (status, msg) => results[status].push(msg);

  // Check 1: Hero (history report có thể không có verdict/stance)
  const hero = await page.$('.hero, h1');
  add(hero ? 'pass' : 'fail', hero ? 'hero present' : 'hero MISSING');
  // Verdict/stance optional (history report không có)
  const verdict = await page.$('.verdict-badge, .badge');
  add(verdict ? 'pass' : 'warn', verdict ? 'verdict/badge' : 'no verdict badge (history mode)');

  // Check 2: nav tabs (v2: 6 tabs — LNH/Trái phiếu/FX/Global/VN/Tổng hợp)
  const tabs = await page.$$('.nav-tab');
  const tabsOk = tabs.length >= 4;
  add(tabsOk ? 'pass' : 'fail', `${tabs.length} nav tabs`);

  // Check 3: group sections (v2: 6 sections)
  const sections = await page.$$('.group-section');
  add(sections.length >= 4 ? 'pass' : 'warn', `${sections.length} group sections`);
  // Check 3b: first group-section active by default (v2: any first section)
  const firstActive = await page.$('.group-section.active');
  add(firstActive ? 'pass' : 'warn', firstActive ? 'first section active by default' : 'no active section');

  // Check 4: content — paragraphs (history mode) OR data cards/tables (dashboard mode)
  const paragraphs = await page.$$('p, .section-title, .subsection');
  add(paragraphs.length > 10 ? 'pass' : 'warn', `${paragraphs.length} content elements (p/sections)`);
  const cards = await page.$$('.data-card, .prose-card, .table-card');
  add(cards.length > 0 ? 'pass' : 'warn', `${cards.length} content cards`);

  // Check 5: tab switching to last visible tab
  if (tabs.length >= 2) {
    await tabs[1].click(); // 2nd tab (W26 in history mode)
    await page.waitForTimeout(400);
    const anyActive = await page.$('.group-section.active:not(#overview)');
    add(anyActive ? 'pass' : 'fail', anyActive ? 'tab switch OK' : 'tab switch FAILED');
    await tabs[0].click();
    await page.waitForTimeout(200);
  }

  // Stance gauge optional
  const needle = await page.$('.gauge-needle');
  add(needle ? 'pass' : 'warn', needle ? 'stance gauge needle' : 'no needle (history mode)');

  // Check 7: no JS console errors
  add(errors.length === 0 ? 'pass' : 'fail',
      errors.length === 0 ? 'no console errors' : `${errors.length} console errors: ${errors.slice(0, 3).join('; ')}`);

  // Screenshots
  await page.screenshot({ path: path.join(outDir, 'full.png'), fullPage: true });
  await page.screenshot({ path: path.join(outDir, 'money-tab.png') });

  await browser.close();

  // Report
  console.log('\n=== vn-rates-weekly QA ===');
  console.log(`✅ PASS: ${results.pass.length}`);
  results.pass.forEach(p => console.log(`  ✓ ${p}`));
  if (results.warn.length) {
    console.log(`⚠️  WARN: ${results.warn.length}`);
    results.warn.forEach(w => console.log(`  ⚠ ${w}`));
  }
  if (results.fail.length) {
    console.log(`❌ FAIL: ${results.fail.length}`);
    results.fail.forEach(f => console.log(`  ✗ ${f}`));
    process.exit(1);
  }
  console.log(`\nScreenshots: ${outDir}/`);
}

runQA().catch(e => { console.error(e); process.exit(1); });
