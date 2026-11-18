// PREPARED ONLY. Run solely in a newly allocated own Chrome profile after Root gate.
async page=>{
  const cfg={"window": "ROOT_NATIVE_ZOOM_BROWSER_GUARD", "probeOrigin": "http://127.0.0.1:56761", "outputPrefix": "C:\\Users\\jpamb\\AppData\\Local\\Temp\\nexus-hst-browser-y0gtl06t\\native-zoom"};
  if(cfg.window!=='ROOT_NATIVE_ZOOM_BROWSER_GUARD')throw Error('Native zoom guard is not authorized');
  const probe=new URL(cfg.probeOrigin);
  if(probe.protocol!=='http:'||probe.hostname!=='127.0.0.1')throw Error('Own loopback calibration origin required');
  const checks=[],observations={};let stage='webui';
  const check=(id,pass,actual)=>{checks.push({id,pass:!!pass,actual});if(!pass)throw Error(id);};
  // Geometry is established once BEFORE both samples. No deviceScaleFactor,
  // CSS zoom/style transform, pinch/page-scale command or hidden Chrome API.
  await page.setViewportSize({width:720,height:1000});
  const viewport=page.viewportSize();
  const metrics=()=>page.evaluate(()=>({innerWidth,innerHeight,outerWidth,outerHeight,devicePixelRatio,screenWidth:screen.width,screenHeight:screen.height,visualViewport:{width:visualViewport?.width,height:visualViewport?.height,scale:visualViewport?.scale},documentWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}));
  const nativeSelect=async percent=>{
    await page.goto('chrome://settings/appearance');
    // Accessible role from the actual WebUI, never prefs files or private APIs.
    const select=page.getByRole('combobox',{name:/^(Page zoom|Zoom da página):?$/i});
    await select.waitFor({state:'visible',timeout:12000});
    check('native-Page-zoom-control-'+percent,await select.count()===1&&await select.evaluate(e=>e.tagName==='SELECT'),await select.ariaSnapshot());
    check('native-Page-zoom-enabled-'+percent,await select.isEnabled(),true);
    const options=await select.locator('option').evaluateAll(items=>items.map(item=>({value:item.value,label:item.label})));
    const target=options.filter(item=>item.label.replace(/\s/g,'')===percent+'%');
    check('native-option-'+percent,target.length===1,options);
    await select.selectOption({value:target[0].value});
    const selected=await select.evaluate(e=>({value:e.value,label:e.selectedOptions[0]?.label}));
    check('native-selected-'+percent,selected.label?.replace(/\s/g,'')===percent+'%',selected);
    await select.scrollIntoViewIfNeeded();
    await page.screenshot({path:cfg.outputPrefix+'-native-ui-'+percent+'.png'});
    observations['ui'+percent]={selected,ariaSnapshot:await select.ariaSnapshot(),viewport:page.viewportSize()};
  };
  const sample=async percent=>{
    await page.goto(cfg.probeOrigin+'/probe?native_zoom='+percent);
    await page.getByRole('heading',{name:'Own native zoom calibration',exact:true}).waitFor();
    const result=await metrics();await page.screenshot({path:cfg.outputPrefix+'-probe-'+percent+'.png'});return result;
  };
  try{
    await nativeSelect(100);observations.baseline=await sample(100);
    stage='native200';await nativeSelect(200);observations.zoomed=await sample(200);
    stage='effect';const a=observations.baseline,b=observations.zoomed;
    observations.ratios={dpr:b.devicePixelRatio/a.devicePixelRatio,innerWidth:b.innerWidth/a.innerWidth,innerHeight:b.innerHeight/a.innerHeight};
    check('same-requested-viewport',JSON.stringify(viewport)===JSON.stringify(page.viewportSize())&&JSON.stringify(observations.ui100.viewport)===JSON.stringify(observations.ui200.viewport),{viewport,current:page.viewportSize()});
    check('native-DPR-doubled',Math.abs(observations.ratios.dpr-2)<.03,observations.ratios);
    check('native-CSS-width-halved',Math.abs(observations.ratios.innerWidth-.5)<.025,observations.ratios);
    check('native-CSS-360-at-requested720',Math.abs(b.innerWidth-360)<=3,{requestedWidth:720,actualCssWidth:b.innerWidth});
    check('no-pinch-visual-scale',a.visualViewport.scale===1&&b.visualViewport.scale===1,{baseline:a.visualViewport.scale,zoomed:b.visualViewport.scale});
    check('outer-and-screen-geometry-stable',Math.abs(a.outerWidth-b.outerWidth)<=2&&a.screenWidth===b.screenWidth&&a.screenHeight===b.screenHeight,{baseline:{outerWidth:a.outerWidth,screenWidth:a.screenWidth,screenHeight:a.screenHeight},zoomed:{outerWidth:b.outerWidth,screenWidth:b.screenWidth,screenHeight:b.screenHeight}});
    return {status:'PASS_NATIVE_200_ZOOM_GUARD',checks,observations,scope:'Native browser-only proof; no Nexus application or I05 acceptance yet',limits:['No screen reader or Windows settings interaction','Only isolated Chrome profile preference changed through actual Settings UI','Page viewport720 and measured CSS360 are reported separately','No deviceScaleFactor/page-scale/CSS zoom API was used']};
  }catch(error){
    observations.failure={stage,url:page.url(),ariaSnapshot:await page.locator('body').ariaSnapshot().catch(()=>null),viewport:page.viewportSize()};
    return {status:stage==='webui'?'NOT_RUN_CHROME_WEBUI': 'UNQUALIFIED_NATIVE_ZOOM_EFFECT',checks,observations,error:String(error),nexus_started:false,fallback:'None; never substitute CSS/viewport/device-scale for native zoom'};
  }
}
