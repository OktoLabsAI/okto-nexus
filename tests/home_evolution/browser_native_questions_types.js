async page => {
  const assert=(v,m)=>{if(!v)throw Error(m);};
  const home=await(await page.request.get(new URL('/api/v1/home/overview',page.url()).href)).json();
  const occurrence=home.data.attention.items.find(i=>i.kind==='native_question_pending');
  assert(occurrence,'no operator form question');
  const posts=[];
  const observe=r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);};
  page.on('request',observe);
  try {
    await page.getByRole('button',{name:'Open question',exact:true}).click();
    const drawer=page.getByTestId('home-detail');
    const count=drawer.getByRole('spinbutton',{name:'count *',exact:true});
    await count.waitFor();
    const number=await count.evaluate(el=>({type:el.type,min:el.min,max:el.max,step:el.step,required:el.required,value:el.value}));
    const enabled=drawer.getByRole('combobox',{name:'enabled *',exact:true});
    const boolean=await enabled.evaluate(el=>({required:el.required,value:el.value,options:[...el.options].map(o=>({value:o.value,label:o.textContent}))}));
    const note=await drawer.getByRole('textbox',{name:'note (optional)',exact:true}).evaluate(el=>({type:el.type,required:el.required,value:el.value}));
    assert(number.type==='number'&&number.min==='1'&&number.max==='5'&&number.step==='1'&&number.required&&number.value==='','integer constraint/default lost');
    assert(boolean.required&&boolean.value===''&&JSON.stringify(boolean.options.map(o=>o.value))===JSON.stringify(['','true','false']),'boolean type/default lost');
    assert(note.type==='text'&&!note.required&&note.value==='','optional string lost');
    assert((await drawer.innerText()).includes(occurrence.source_id),'form points to a different canonical request');
    assert(posts.length===0,'inspection mutated state');
    return {id:'HOME-T-C01',status:'PASS',kind:'typed elicitation form',request:occurrence.source_id,number,boolean,note,mutationRequests:posts};
  } finally {page.off('request',observe);}
}
