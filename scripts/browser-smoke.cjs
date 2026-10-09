const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 fs.mkdirSync('evidence',{recursive:true});
 const browser=await chromium.launch({headless:true,channel:"chromium"});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const base=process.env.BASE_URL||'http://127.0.0.1:8092';
 try{
  await page.goto(base+'/login/');
  await page.getByLabel('Username',{exact:true}).fill('demo-owner');
  await page.getByLabel('Password',{exact:true}).fill('Fictional-demo-password-2026');
  await page.getByRole('button',{name:'Sign in →'}).click();
  await page.getByRole('heading',{name:'Your opportunity board'}).waitFor();
  await page.screenshot({path:'evidence/desk-desktop.png',fullPage:true});
  await page.getByRole('link',{name:'2022 Toyota Camry',exact:true}).click();
  await page.getByRole('button',{name:'Prepare SMS draft'}).click();
  await page.getByRole('link',{name:'Open review queue →'}).click();
  await page.getByRole('button',{name:'Approve SMS'}).click();
  await page.getByText('SMS / QUEUED',{exact:true}).waitFor();
  await page.getByText('Live dispatch disabled',{exact:true}).waitFor();
  await page.screenshot({path:'evidence/outbox-review.png',fullPage:true});
  await page.goto(base+'/');
  await page.getByRole('link',{name:'2022 Toyota Camry',exact:true}).click();
  await page.getByLabel('Move lead to').selectOption('contacted');
  await page.getByLabel('Decision note').fill('Fictional browser test: seller contacted manually.');
  await page.getByRole('button',{name:'Update stage'}).click();
  await page.getByText('Fictional browser test: seller contacted manually.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Prepare CRM sync'}).click();
  await page.goto(base+'/outbox/');
  await page.getByRole('button',{name:'Approve CRM'}).click();
  await page.getByText('CRM / QUEUED',{exact:true}).waitFor();
  await page.goto(base+'/');await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'No mobile horizontal overflow');
  await page.screenshot({path:'evidence/desk-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync('evidence/browser-result.json',JSON.stringify({login:true,draftApproval:true,stageChange:true,crmQueue:true,mobile:true,liveMessagesSent:0},null,2));
 }catch(error){await page.screenshot({path:'evidence/failure.png',fullPage:true});console.error(await page.locator('body').innerText());throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
