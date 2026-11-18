"""New counterpart: apply held updates through the public UI before G02."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
original=(HERE/'browser-g01-exact.js').read_bytes()
assert hashlib.sha256(original).hexdigest()=='7277aec8462a8f84bfb0fbed36770a13341e891ff9f7f591e637a4a0c9de59a2'
source=original.decode().replace('\r\n','\n')
old="""        await open(cfg.bCard);const select=modal.getByLabel('Choose a session',{exact:true});await select.waitFor();
        check('G02-no-automatic-preview-choice',await select.inputValue()==='',await select.inputValue());"""
new="""        const apply=page.getByRole('button',{name:'Apply updates',exact:true});
        observations.g02Before={url:page.url(),applyVisible:await apply.isVisible().catch(()=>false),homeAX:await page.getByTestId('operational-home').ariaSnapshot()};
        if(observations.g02Before.applyVisible){await apply.click();await apply.waitFor({state:'hidden'});}
        // The canonical UI may intentionally hold a previous snapshot until Apply.
        // Observe the resulting panel/actual relation, never invoke React/controller internals.
        const relationRead=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/home/harness-board/cards/'+cfg.bCard+'/sessions'&&r.request().method()==='GET',{timeout:15000});
        await open(cfg.bCard);
        const relationResponse=await relationRead;const relationRaw=await relationResponse.json();const relation=relationRaw.data??relationRaw;
        await modal.getByRole('region',{name:'Harness activity',exact:true}).waitFor();
        check('G02-current-relation-exact-card-two-sessions',relationResponse.status()===200&&relation.card_id===cfg.bCard&&relation.total===2&&relation.total_is_exact===true,{status:relationResponse.status(),card:relation.card_id,total:relation.total,exact:relation.total_is_exact});
        const select=modal.getByLabel('Choose a session',{exact:true});await select.waitFor();
        observations.g02PanelAX=await modal.ariaSnapshot();
        check('G02-no-automatic-preview-choice',await select.inputValue()==='',await select.inputValue());"""
assert source.count(old)==1;source=source.replace(old,new)
old="""  }catch(error){return {status:checks.some(c=>c.id==='I01-header-menu-accessible-name'&&!c.pass)?'PRODUCT_DEFECT_UNNAMED_HEADER_MENU':'INCOMPLETE',phase:cfg.phase,checks,posts,errors,error:String(error)};}"""
new="""  }catch(error){
    observations.failure={url:page.url(),bodyAX:await page.locator('body').ariaSnapshot().catch(()=>null),openDialogs:await modal.count()};
    await page.screenshot({path:cfg.screenshotPrefix+'-'+cfg.phase+'-failure.png'}).catch(()=>{});
    return {status:checks.some(c=>c.id==='I01-header-menu-accessible-name'&&!c.pass)?'PRODUCT_DEFECT_UNNAMED_HEADER_MENU':'INCOMPLETE',phase:cfg.phase,checks,posts,errors,observations,error:String(error)};
  }"""
assert source.count(old)==1;source=source.replace(old,new)
target=HERE/'browser-g02-apply.js';assert not target.exists();target.write_text(source,encoding='utf-8')
checked=subprocess.run([r'C:/Program Files/nodejs/node.exe','--check',str(target)],capture_output=True,text=True,timeout=10);assert checked.returncode==0,checked.stderr
proof=dict(status='PREPARED_NOT_EXECUTED',original_sha256=hashlib.sha256(original).hexdigest(),variant_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),node_syntax_exit=checked.returncode,change='Only apply pending snapshot through public Apply updates; require real Harness activity and exact relation total2 before no-auto-choice assertion; capture AX/URL/screenshot on failure.',prior_failure='experience-r8-g01-variant/qualification.json')
(HERE/'g02-variant-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
