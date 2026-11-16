import { createRequire } from 'module';
import { homedir } from 'os';
import { join } from 'path';

const require = createRequire(import.meta.url);
const CDP = require(join(homedir(), 'tradingview-mcp', 'node_modules', 'chrome-remote-interface'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ev = async (Runtime, expression, awaitPromise = false) => {
  const { result, exceptionDetails } = await Runtime.evaluate({
    expression,
    returnByValue: true,
    awaitPromise,
  });
  if (exceptionDetails?.text) throw new Error(exceptionDetails.text);
  return result?.value;
};

function pickChartTarget(targets) {
  return (
    targets.find((t) => t.type === 'page' && /symbol=PRMB/i.test(t.url || '')) ||
    targets.find((t) => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url || '')) ||
    null
  );
}

const want = String(process.argv[2] || '').trim();
if (!want) {
  console.log(JSON.stringify({ ok: false, error: 'missing watchlist name' }));
  process.exit(1);
}

const port = Number(process.env.TUBEON_TV_CDP_PORT || process.env.TV_CDP_PORT || 9222);
const targets = await CDP.List({ port });
const target = pickChartTarget(targets);
if (!target) {
  console.log(JSON.stringify({ ok: false, error: 'No chart CDP target' }));
  process.exit(1);
}

const client = await CDP({ port, target: target.id });
const { Runtime } = client;
await Runtime.enable();

const norm = (s) => String(s || '').replace(/\.txt$/i, '').trim();
const wanted = norm(want);

const activeName = async () =>
  ev(
    Runtime,
    `(function(){
      var btn=document.querySelector('[data-name="watchlists-button"]');
      return (btn && btn.textContent) ? String(btn.textContent).trim() : '';
    })()`,
  );

const openPanel = async () => {
  await ev(
    Runtime,
    `(function(){
      var btn=document.querySelector('[data-name="base-watchlist-widget-button"]')
        ||document.querySelector('[aria-label*="Watchlist"]');
      if(btn&&btn.getAttribute('aria-pressed')!=='true')btn.click();
      return true;
    })()`,
  );
  await sleep(400);
};

await openPanel();
let current = norm(await activeName());
if (current === wanted || current.startsWith(wanted)) {
  console.log(JSON.stringify({
    ok: true,
    already_active: true,
    listStem: wanted,
    activeList: current,
  }));
  await client.close();
  process.exit(0);
}

const clicked = await ev(
  Runtime,
  `(async function(){
    var want=${JSON.stringify(wanted)};
    function norm(s){return String(s||'').replace(/\\.txt$/i,'').trim();}
    function match(el){
      var a=norm(el.getAttribute && el.getAttribute('aria-label'));
      var t=norm(el.textContent);
      return a===want || t===want || a.startsWith(want) || t===want;
    }
    function visible(el){
      var r=el.getBoundingClientRect();
      return r.width>0 && r.height>0;
    }
    // Direct labelled control (same pattern as Blue list).
    var direct=document.querySelector('[aria-label="'+want+'"]');
    if(direct && visible(direct)){
      direct.click();
      return {ok:true, how:'aria-label'};
    }
    var menuBtn=document.querySelector('[data-name="watchlists-button"]');
    if(!menuBtn) return {ok:false, error:'no_menu'};
    menuBtn.click();
    await new Promise(function(r){setTimeout(r,700);});
    var cands=[];
    document.querySelectorAll('[role="menuitem"], [aria-label], button, div, span, a').forEach(function(el){
      if(!visible(el)) return;
      if(el.children && el.children.length>6) return;
      var a=norm(el.getAttribute && el.getAttribute('aria-label'));
      var t=norm((el.textContent||'').replace(/\\s+/g,' '));
      if(t.length>80) return;
      if(a===want || t===want) cands.push(el);
    });
    if(!cands.length){
      return {ok:false, not_found:true, error:'list not found in menu', want:want};
    }
    cands[0].click();
    return {ok:true, how:'menu'};
  })()`,
  true,
);

if (!clicked?.ok) {
  console.log(JSON.stringify({
    ok: false,
    not_found: Boolean(clicked?.not_found),
    listStem: wanted,
    error: clicked?.error || 'activate failed',
    clicked,
  }));
  await client.close();
  process.exit(1);
}

await sleep(800);
current = norm(await activeName());
const ok = current === wanted || current.startsWith(wanted);
console.log(JSON.stringify({
  ok,
  already_active: false,
  listStem: wanted,
  activeList: current,
  how: clicked?.how,
  error: ok ? undefined : 'active list did not change to ' + wanted,
}));
await client.close();
if (!ok) process.exit(1);
