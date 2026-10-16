// Optional development test. npm install, npx playwright install chromium, npm run test:browser.
const {chromium}=require('playwright');
const fs=require('fs'), os=require('os'), path=require('path'), {spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'ahas-ui-'));
 const source=path.join(temp,'Source');fs.mkdirSync(source);
 fs.writeFileSync(path.join(source,'note.txt'),'AHAS test content\n'.repeat(20000));
 fs.copyFileSync(path.join(source,'note.txt'),path.join(source,'copy.txt'));
 const archive=path.join(temp,'Example.ahas'),restored=path.join(temp,'Restored');
 const child=spawn(process.env.PYTHON||'python3',['-m','compactlocal','--preview','--no-browser','--port','0'],{cwd:root});
 let browser;
 try{
  const url=await new Promise((resolve,reject)=>{let log='';const timer=setTimeout(()=>reject(Error('Server startup timeout')),15000);child.stdout.on('data',b=>{log+=b;const match=log.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0])}});child.on('exit',n=>{clearTimeout(timer);reject(Error('Server exited '+n))})});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.getByText('Made by Ahas Nimsandu',{exact:true}).first().waitFor();
  if(process.env.SCREENSHOTS){fs.mkdirSync(path.join(root,'docs/screenshots'),{recursive:true});await page.screenshot({path:path.join(root,'docs/screenshots/archive.png'),fullPage:true})}
  await page.locator('[data-op="media"]').click();
  await page.locator('#consentBox').waitFor();
  if(process.env.SCREENSHOTS)await page.screenshot({path:path.join(root,'docs/screenshots/media.png'),fullPage:true});
  await page.locator('summary').click();await page.locator('#manual').fill(source);await page.locator('#addPaths').click();await page.locator('#output').fill(path.join(temp,'Optimized'));await page.locator('#start').click();
  await page.getByText('Confirm that you accept quality loss before optimizing media.',{exact:true}).waitFor();
  await page.locator('[data-op="compress"]').click();await page.locator('#output').fill(archive);await page.locator('#start').click();await page.getByText('AHAS archive created.',{exact:true}).waitFor();
  await page.locator('[data-op="verify"]').click();await page.locator('#archive').fill(archive);await page.locator('#start').click();await page.getByText('All content checks passed.',{exact:true}).waitFor();
  await page.locator('[data-op="extract"]').click();await page.locator('#output').fill(restored);await page.locator('#start').click();await page.getByText('Files restored and content checks passed.',{exact:true}).waitFor();
  if(!fs.readFileSync(path.join(source,'note.txt')).equals(fs.readFileSync(path.join(restored,'Source/note.txt'))))throw Error('Restored bytes mismatch');
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: branded UI, both mode choices, lossy consent gate, .ahas create → verify → extract, byte match, mobile layout, no JS page errors.');
 }finally{if(browser)await browser.close();child.kill('SIGINT');await new Promise(resolve=>child.on('exit',resolve));fs.rmSync(temp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
