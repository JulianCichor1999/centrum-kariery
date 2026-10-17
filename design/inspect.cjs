const { chromium } = require('C:/Users/Julian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const output = path.join(__dirname, 'screenshots');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const checks = [];
  async function fitFrame(frame) {
    const height=await frame.locator('#career-design').evaluate(el=>Math.ceil(el.getBoundingClientRect().height)+16);
    await page.setViewportSize({width:page.viewportSize().width,height:Math.max(height,900)});
    await page.locator('iframe').evaluate((el,h)=>el.style.height=h+'px',height);
    await frame.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.mouse.move(0,0);
  }
  const screens = ['today','offers','applications','detail','plan','profile','materials','assistant','settings'];
  for (const width of [390,1440,768,360]) {
    await page.setViewportSize({ width, height: width===1440 ? 900 : width===768 ? 1024 : 844 });
    await page.goto(pathToFileURL(path.join(__dirname,'preview.html')).href);
    await page.addStyleTag({content:'body{padding:0!important}iframe{width:100%!important}'});
    const frame = page.frames().find(f => f !== page.mainFrame());
    await frame.waitForSelector('#career-design .cd-main h1');
    const root = frame.locator('#career-design');
    for (const screen of screens) {
      if (width<=640) {
        const menu = root.locator('#cd-menu');
        if (await menu.getAttribute('aria-expanded') !== 'true') await menu.click();
      }
      if (screen==='detail') {
        await root.locator('.cd-nav [data-screen="applications"]').click();
        await root.getByRole('button', {name:'Otwórz aplikację', exact:true}).click();
      } else await root.locator('.cd-nav [data-screen="'+screen+'"]').click();
      const size = await root.evaluate(el => ({width:el.clientWidth, scroll:el.scrollWidth, documentWidth:document.documentElement.clientWidth, documentScroll:document.documentElement.scrollWidth}));
      checks.push({viewport:width,screen,...size});
      if (size.scroll>size.width+1 || size.documentScroll>size.documentWidth+1) throw new Error('Overflow: '+JSON.stringify(checks.at(-1)));
      if (width===1440 || screen==='today' || (width===390 && ['detail','assistant'].includes(screen))) {
        await fitFrame(frame);
        await root.screenshot({path:path.join(output,screen+'-'+width+'.png')});
      }
      if (screen==='detail' && width===1440) {
        for (const tab of ['match','documents','history']) {
          await root.locator('[data-detail-tab="'+tab+'"]').click();
          await fitFrame(frame);
          await root.screenshot({path:path.join(output,'application-'+tab+'-'+width+'.png')});
        }
      }
      if (screen==='assistant' && width===1440) {
        for (const step of ['research','match','materials','check','approval']) {
          await root.locator('[data-ai-step="'+step+'"]').click();
          await fitFrame(frame);
          await root.screenshot({path:path.join(output,'ai-'+step+'-'+width+'.png')});
        }
      }
    }
    await root.locator('#cd-state-select').selectOption('sample');
    if (width===390 || width===1440) {
      for (const state of ['empty','loading','error','offline']) {
        await root.locator('#cd-state-select').selectOption(state);
        await fitFrame(frame);
        await root.screenshot({path:path.join(output,'state-'+state+'-'+width+'.png')});
        const overflow=await root.evaluate(el=>el.scrollWidth>el.clientWidth+1);
        if(overflow) throw new Error('State overflow: '+state+' '+width);
      }
      await root.locator('#cd-state-select').selectOption('sample');
      await root.locator('#cd-add').click();
      await root.locator('#cd-add-dialog').screenshot({path:path.join(output,'add-dialog-'+width+'.png')});
      await page.keyboard.press('Escape');
      if (await root.locator('#cd-add-dialog').evaluate(el=>el.open)) throw new Error('Dialog did not close with Escape');
    }
    if(width===390) {
      const smallTargets = await root.evaluate(el => [...el.querySelectorAll('button,select,input,summary')].filter(n=>n.getClientRects().length && !n.disabled).map(n=>({label:n.textContent.trim()||n.getAttribute('aria-label'),width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height})).filter(n=>n.width<44 || n.height<44));
      if(smallTargets.length) throw new Error('Small mobile targets: '+JSON.stringify(smallTargets));
    }
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  const frame=page.frames().find(f=>f!==page.mainFrame());
  const motion=await frame.locator('#career-design #cd-add').evaluate(el=>getComputedStyle(el).transitionDuration);
  if(motion!=='0s') throw new Error('Reduced motion failed: '+motion);
  await page.setViewportSize({width:1440,height:900});
  await page.goto(pathToFileURL(path.join(__dirname,'preview.html')).href);
  await page.addStyleTag({content:'body{padding:0!important}iframe{width:100%!important}'});
  const focusFrame=page.frames().find(f=>f!==page.mainFrame());
  await focusFrame.waitForSelector('#career-design .cd-main h1');
  const tabStops=[];
  for(let i=0;i<20;i++) {
    await page.keyboard.press('Tab');
    const stop=await focusFrame.evaluate(()=>{const el=document.activeElement;return {tag:el.tagName,label:el.textContent?.trim().slice(0,60)||el.getAttribute('aria-label'),outline:getComputedStyle(el).outlineStyle,outlineWidth:getComputedStyle(el).outlineWidth};});
    if(stop.tag!=='BODY')tabStops.push(stop);
  }
  if(tabStops.filter(s=>s.tag==='BUTTON').some(s=>s.outline==='none'||s.outlineWidth==='0px')) throw new Error('Invisible keyboard focus');
  if(errors.length) throw new Error('Runtime errors: '+errors.join('; '));
  function luminance(hex) {
    const rgb=hex.match(/[0-9a-f]{2}/gi).map(h=>parseInt(h,16)/255).map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4);
    return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;
  }
  const contrastPairs=[['#111111','#ffffff'],['#555555','#ffffff'],['#555555','#f7f7f5'],['#ffffff','#2563eb'],['#166534','#ffffff'],['#92400e','#ffffff']];
  const contrast=contrastPairs.map(([foreground,background])=>{const a=luminance(foreground),b=luminance(background);return {foreground,background,ratio:Math.round((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05)*100)/100};});
  if(contrast.some(c=>c.ratio<4.5)) throw new Error('Text contrast failure');
  const result={checks,errors,reducedMotion:motion,keyboardStops:tabStops,contrast,screenshotDirectory:output};
  fs.writeFileSync(path.join(__dirname,'render-report.json'),JSON.stringify(result,null,2));
  await browser.close();
  console.log(JSON.stringify({checked:checks.length,errors,reducedMotion:motion,keyboardStops:tabStops.length,screenshots:output}));
})().catch(e=>{console.error(e);process.exit(1);});
